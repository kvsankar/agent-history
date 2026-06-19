"""Handler for session stats command.

This module provides the SessionStatsHandler that computes aggregate
statistics from sessions in a resolved ConcreteScope. It supports
various grouping dimensions and time tracking.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from typing import Any, Dict

from agent_history.core.workspaces import build_scope_metadata, build_workspace_rows
from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.handlers.dispatcher import DispatchError
from agent_history.scope.context import OutputArgs, ResolutionContext, ScopeArgs
from agent_history.scope.types import ConcreteScope
from agent_history.storage.project_tags import (
    UNTAGGED_TAG,
    normalize_tags,
    project_tags_for,
)
from agent_history.utils.paths import decode_workspace_path, is_encoded_workspace_name
from agent_history.utils.workspace_ref import build_workspace_ref

SUMMARY_DIMENSIONS = {"agent", "home", "workspace", "model", "tool", "day"}


class SessionStatsHandler(VerbHandler):
    """Handle 'session stats' command.

    Computes aggregate statistics from sessions in a resolved ConcreteScope.
    The handler receives already-resolved scope with EXACT matching applied,
    so it operates directly on the session dictionaries.

    Supported groupings:
        - by_agent: Statistics grouped by agent (claude, codex, gemini)
        - by_model: Statistics grouped by model name
        - by_tool: Statistics grouped by tool usage
        - by_home: Statistics grouped by home identifier
        - by_workspace: Statistics grouped by workspace path
        - by_day: Statistics grouped by date

    Example:
        handler = SessionStatsHandler()
        result = handler.execute(scope, {"by": "model", "time": True}, output_args)
    """

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """Compute and return statistics for sessions in scope.

        Args:
            scope: Resolved scope with sessions. Each ConcreteRecord contains:
                - home: string identifier (e.g., "local", "wsl:Ubuntu")
                - workspace: absolute path string
                - sessions: list of session dictionaries
            verb_args: Stats options:
                - by: str - grouping dimension (model, tool, day, workspace, home, agent)
                - time: bool - include time tracking statistics
                - sync: bool - sync before display (handled at CLI level)
                - top: int - limit for top N items in breakdowns
            output_args: Output formatting options.

        Returns:
            CommandResult with:
            - success: True
            - data: dictionary containing computed statistics
            - data_type: 'stats'
            - metadata: scope information (total_sessions, homes, workspaces)
        """
        # Extract options
        group_by = verb_args.get("by")
        include_time = verb_args.get("time", False)
        top_limit = verb_args.get("top")
        top_ws = verb_args.get("top_ws")
        human = bool(verb_args.get("human"))

        # Compute statistics
        from agent_history.core.stats import apply_top_limit, compute_stats, overlay_metrics

        group_list = self._group_list(group_by)

        include_day = "day" in group_list

        if verb_args.get("stats_mode") == "rollup":
            return self._execute_rollup(scope, group_list, verb_args, human=human)

        self._validate_summary_dimensions(group_list)
        stats = compute_stats(scope, "day" if include_day else None, include_time)

        # Overlay parsed metrics from the database for the already-resolved scope.
        # Session discovery intentionally skips expensive parsing, so message,
        # token, model, and tool totals should come from DB rows for this scope,
        # not from all rows in the metrics database.
        should_overlay_db = bool(verb_args.get("sync"))
        if not should_overlay_db:
            try:
                from agent_history.storage.metrics import get_metrics_db_path

                should_overlay_db = get_metrics_db_path().exists()
            except Exception:
                should_overlay_db = False

        if should_overlay_db:
            db_stats = self._db_overlay_stats(scope)
            if db_stats:
                stats = overlay_metrics(stats, db_stats)

        # Apply top limit to breakdowns if specified
        if top_limit:
            stats = apply_top_limit(stats, top_limit)

        stats["total_sessions"] = stats.get("sessions", 0)
        stats["total_messages"] = stats.get("messages", 0)

        workspace_rows, _workspace_display_map = build_workspace_rows(scope)
        metadata = build_scope_metadata(scope)
        workspace_display_map = metadata["workspace_display_map"]
        by_workspace_stats = stats.get("by_workspace", {})
        if isinstance(by_workspace_stats, dict):
            for row in workspace_rows:
                workspace_key = row.get("workspace_key") or row.get("workspace")
                if workspace_key in by_workspace_stats:
                    row["messages"] = by_workspace_stats[workspace_key].get(
                        "messages", row.get("messages", 0)
                    )
        workspace_rows.sort(key=lambda r: r["sessions"], reverse=True)
        if isinstance(top_ws, int):
            workspace_rows = workspace_rows[:top_ws]
        stats["workspace_rows"] = workspace_rows
        stats["workspace_display_map"] = workspace_display_map

        # Build metadata
        total_sessions = sum(len(record.sessions) for record in scope)

        return CommandResult(
            success=True,
            data=stats,
            data_type="stats",
            metadata={
                "total_sessions": total_sessions,
                "homes": metadata["homes"],
                "workspaces": metadata["workspaces"],
                "workspace_display_map": workspace_display_map,
                "group_by": group_list,
                "include_time": include_time,
                "top_ws": top_ws,
                "human": human,
                "scope_request": verb_args.get("scope_request"),
                "sync_stats": verb_args.get("sync_stats"),
            },
        )

    def _execute_rollup(
        self,
        scope: ConcreteScope,
        group_list: list[str],
        verb_args: Dict[str, Any],
        *,
        human: bool,
    ) -> CommandResult:
        """Return rollup stats for an already-resolved scope."""
        from agent_history.storage.metrics import get_scoped_stats_from_db, get_stats_rollup_from_db

        dimensions = group_list or ["project"]
        filters = self._filters_from_scope(scope)
        project_map = verb_args.get("project_map")
        tag_map = verb_args.get("tag_map")
        storage_dimensions = self._storage_rollup_dimensions(dimensions, project_map, tag_map)
        storage_top = None if storage_dimensions != dimensions else verb_args.get("top")
        rows = get_stats_rollup_from_db(
            filters=filters,
            by=storage_dimensions,
            metric=verb_args.get("metric") or "all",
            top=storage_top,
            sort_by=verb_args.get("sort"),
            sort_direction=verb_args.get("sort_direction") or "default",
        )
        rows = self._apply_tag_rollup(
            rows,
            dimensions,
            tag_map,
            preserve_workspace="project" in dimensions,
        )
        rows = self._apply_project_rollup(rows, dimensions, project_map)
        if storage_dimensions != dimensions and verb_args.get("top"):
            rows = rows[: verb_args["top"]]
        scoped_summary = get_scoped_stats_from_db(filters=filters)
        metadata = build_scope_metadata(scope)
        return CommandResult(
            success=True,
            data=rows,
            data_type="stats_rollup",
            metadata={
                "homes": metadata["homes"],
                "workspaces": metadata["workspaces"],
                "dimensions": dimensions,
                "metric": verb_args.get("metric") or "all",
                "cached": False,
                "scope_request": verb_args.get("scope_request"),
                "total_sessions": sum(len(record.sessions) for record in scope),
                "total_time_seconds": scoped_summary.get("time_stats", {}).get(
                    "total_duration_seconds", 0
                ),
                "sync_stats": verb_args.get("sync_stats"),
                "human": human,
                "total": bool(verb_args.get("total")),
                "separator": bool(verb_args.get("separator")),
            },
        )

    def _db_overlay_stats(self, scope: ConcreteScope) -> dict[str, Any] | None:
        """Return metrics DB overlays for a resolved scope, if available."""
        try:
            from agent_history.storage.metrics import (
                get_session_stats_from_db,
                get_time_stats_from_db,
                get_tool_usage_stats_from_db,
            )

            file_paths = self._scope_file_paths(scope)
            db_stats = get_session_stats_from_db(file_paths=file_paths)
            db_stats["by_tool"] = get_tool_usage_stats_from_db(file_paths=file_paths)
            db_stats["time_stats"] = get_time_stats_from_db(file_paths=file_paths)
            return db_stats
        except Exception:
            return None

    def execute_cached(
        self,
        scope_args: ScopeArgs,
        context: ResolutionContext,
        verb_args: Dict[str, Any],
        output_args: OutputArgs,
    ) -> CommandResult:
        """Compute statistics directly from the metrics DB without raw session discovery."""
        from agent_history.storage.metrics import (
            get_metrics_db_path,
            get_scoped_stats_from_db,
        )

        group_list = self._group_list(verb_args.get("by"))

        filters, metadata = self._cached_filters(scope_args, context)
        metadata["scope_request"] = self._scope_request_metadata(scope_args, context)
        self._apply_session_filters(filters, scope_args)
        project_map = self._project_membership_map(context, scope_args)
        tag_map = self._tag_membership_map(context, scope_args)

        if verb_args.get("stats_mode") != "rollup":
            self._validate_summary_dimensions(group_list)

        db_path = get_metrics_db_path()
        if not db_path.exists():
            return self._missing_cache_result(metadata, group_list, verb_args)

        if verb_args.get("stats_mode") == "rollup":
            return self._execute_cached_rollup(
                filters,
                metadata,
                group_list,
                verb_args,
                project_map=project_map,
                tag_map=tag_map,
            )

        stats = get_scoped_stats_from_db(filters=filters, include_day="day" in group_list)
        workspace_rows = self._workspace_rows_from_db(stats)
        if verb_args.get("top"):
            from agent_history.core.stats import apply_top_limit

            stats = apply_top_limit(stats, verb_args["top"])
        stats["workspace_rows"] = workspace_rows
        if isinstance(verb_args.get("top_ws"), int):
            stats["workspace_rows"] = stats["workspace_rows"][: verb_args["top_ws"]]
        stats["workspace_display_map"] = {
            workspace: workspace for workspace in stats.get("by_workspace", {})
        }
        warnings = ["Using cached metrics. Run with `--sync` to refresh from source files."]
        cache_warning = "Using cached metrics. Run with --sync to refresh from source files."
        if not stats.get("total_sessions"):
            warnings = [
                "No cached stats matched this scope. Run `cagelens stats --sync` to refresh."
            ]
            cache_warning = "No cached stats matched this scope. Run with --sync to refresh."

        metadata.update(
            {
                "homes": metadata.get("homes", []) or sorted(stats.get("by_home", {}).keys()),
                "workspaces": metadata.get("workspaces", [])
                or sorted(stats.get("by_workspace", {}).keys()),
                "workspace_display_map": metadata.get("workspace_display_map")
                or stats["workspace_display_map"],
                "group_by": group_list,
                "include_time": bool(verb_args.get("time")),
                "top_ws": verb_args.get("top_ws"),
                "human": bool(verb_args.get("human")),
                "cached": True,
                "cache_warning": cache_warning,
            }
        )
        return CommandResult(
            success=True,
            data=stats,
            data_type="stats",
            metadata=metadata,
            warnings=warnings,
        )

    def _group_list(self, group_by: Any) -> list[str]:
        if isinstance(group_by, list):
            return [value for value in group_by if value]
        if isinstance(group_by, str):
            return [group_by]
        return []

    def _apply_session_filters(self, filters: dict[str, Any], scope_args: ScopeArgs) -> None:
        if scope_args.agent:
            filters["agent"] = scope_args.agent
        if scope_args.since:
            filters["since"] = scope_args.since
        if scope_args.until:
            filters["until"] = scope_args.until

    def _missing_cache_result(
        self, metadata: dict[str, Any], group_list: list[str], verb_args: Dict[str, Any]
    ) -> CommandResult:
        return CommandResult(
            success=True,
            data=self._empty_cached_stats(),
            data_type="stats",
            metadata={
                **metadata,
                "group_by": group_list,
                "include_time": bool(verb_args.get("time")),
                "top_ws": verb_args.get("top_ws"),
                "human": bool(verb_args.get("human")),
                "cached": True,
                "cache_warning": "No cached stats found. Run with --sync to build metrics.",
            },
            warnings=["No cached stats found. Run `cagelens stats --sync` to refresh."],
        )

    def _execute_cached_rollup(
        self,
        filters: dict[str, Any],
        metadata: dict[str, Any],
        group_list: list[str],
        verb_args: Dict[str, Any],
        *,
        project_map: dict[str, str] | None = None,
        tag_map: dict[str, list[str]] | None = None,
    ) -> CommandResult:
        from agent_history.storage.metrics import get_scoped_stats_from_db, get_stats_rollup_from_db

        dimensions = group_list or ["project"]
        storage_dimensions = self._storage_rollup_dimensions(dimensions, project_map, tag_map)
        storage_top = None if storage_dimensions != dimensions else verb_args.get("top")
        rows = get_stats_rollup_from_db(
            filters=filters,
            by=storage_dimensions,
            metric=verb_args.get("metric") or "all",
            top=storage_top,
            sort_by=verb_args.get("sort"),
            sort_direction=verb_args.get("sort_direction") or "default",
        )
        rows = self._apply_tag_rollup(
            rows,
            dimensions,
            tag_map,
            preserve_workspace="project" in dimensions,
        )
        rows = self._apply_project_rollup(rows, dimensions, project_map)
        if storage_dimensions != dimensions and verb_args.get("top"):
            rows = rows[: verb_args["top"]]
        scoped_summary = get_scoped_stats_from_db(filters=filters)
        return CommandResult(
            success=True,
            data=rows,
            data_type="stats_rollup",
            metadata={
                **metadata,
                "homes": metadata.get("homes", []) or sorted(scoped_summary.get("by_home", {})),
                "workspaces": metadata.get("workspaces", [])
                or sorted(scoped_summary.get("by_workspace", {})),
                "dimensions": dimensions,
                "metric": verb_args.get("metric") or "all",
                "cached": True,
                "total_sessions": scoped_summary.get("total_sessions", 0),
                "total_time_seconds": scoped_summary.get("time_stats", {}).get(
                    "total_duration_seconds", 0
                ),
                "human": bool(verb_args.get("human")),
                "total": bool(verb_args.get("total")),
                "separator": bool(verb_args.get("separator")),
            },
            warnings=["Using cached metrics. Run with `--sync` to refresh from source files."],
        )

    def _scope_file_paths(self, scope: ConcreteScope) -> list[str]:
        """Return session file paths from the resolved scope."""
        file_paths: list[str] = []
        for record in scope:
            for session in record.sessions:
                file_value = session.get("file")
                if file_value:
                    file_paths.append(str(file_value))
        return file_paths

    def _cached_filters(
        self, scope_args: ScopeArgs, context: ResolutionContext
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        filters: dict[str, Any] = {}
        metadata: dict[str, Any] = {"homes": [], "workspaces": [], "workspace_display_map": {}}

        effective_projects = self._effective_projects(scope_args, context)
        if effective_projects is not None:
            if not effective_projects:
                filters["homes"] = self._selected_homes(scope_args, context)
                filters["workspaces"] = ["__cagelens_no_matching_project_tag__"]
                metadata["homes"] = filters["homes"]
                metadata["workspaces"] = []
                return filters, metadata
            homes, workspaces = self._project_filter(scope_args, context, effective_projects)
            filters["homes"] = homes
            filters["workspaces"] = workspaces
            project_homes, project_workspaces, display_map = self._project_metadata(
                scope_args, context, effective_projects
            )
            metadata["homes"] = project_homes or homes
            metadata["workspaces"] = project_workspaces
            metadata["workspace_display_map"] = display_map
            return filters, metadata

        homes = self._selected_homes(scope_args, context)
        filters["homes"] = homes
        metadata["homes"] = homes

        workspaces = self._workspace_values(scope_args, context)
        if workspaces:
            filters["workspaces"] = workspaces
            metadata["workspaces"] = workspaces

        if scope_args.glob_patterns:
            filters["workspace_globs"] = list(scope_args.glob_patterns)
        if scope_args.regex_patterns:
            filters["workspace_regexes"] = list(scope_args.regex_patterns)
        if scope_args.name_patterns:
            filters["workspace_patterns"] = list(scope_args.name_patterns)

        return filters, metadata

    def _validate_summary_dimensions(self, group_list: list[str]) -> None:
        invalid = [dimension for dimension in group_list if dimension not in SUMMARY_DIMENSIONS]
        if invalid:
            raise DispatchError(f"Unsupported stats dimension(s): {', '.join(invalid)}")

    def _project_membership_map(
        self, context: ResolutionContext, scope_args: ScopeArgs
    ) -> dict[str, str]:
        effective_projects = self._effective_projects(scope_args, context)
        if effective_projects is not None:
            projects = effective_projects
        elif context.cwd_project:
            projects = [context.cwd_project]
        else:
            projects = list(context.project_config.keys())

        selected_homes = set(self._selected_homes(scope_args, context))
        home_filter_explicit = bool(
            scope_args.all_homes or scope_args.home_names or scope_args.home_type
        )
        mapping: dict[str, str] = {}
        for project in projects:
            project_def = context.project_config.get(project, {})
            for home, configured in project_def.items():
                if home_filter_explicit and home not in selected_homes:
                    continue
                values = configured if isinstance(configured, list) else [configured]
                for value in values:
                    for candidate in self._workspace_candidates(str(value)):
                        mapping.setdefault(candidate, project)
        return mapping

    def _tag_membership_map(
        self, context: ResolutionContext, scope_args: ScopeArgs
    ) -> dict[str, list[str]]:
        effective_projects = self._effective_projects(scope_args, context)
        if effective_projects is not None:
            projects = effective_projects
        elif context.cwd_project:
            projects = [context.cwd_project]
        else:
            projects = list(context.project_config.keys())

        requested_tags = set(normalize_tags(scope_args.tags)) if scope_args.tags else set()
        selected_homes = set(self._selected_homes(scope_args, context))
        home_filter_explicit = bool(
            scope_args.all_homes or scope_args.home_names or scope_args.home_type
        )
        config = {
            "projects": context.project_config,
            "project_tags": getattr(context, "project_tags", {}) or {},
        }
        mapping: dict[str, list[str]] = {}
        for project in projects:
            project_def = context.project_config.get(project, {})
            tags = project_tags_for(config, project) or [UNTAGGED_TAG]
            if requested_tags:
                tags = [tag for tag in tags if tag in requested_tags]
            if not tags:
                continue
            for home, configured in project_def.items():
                if home_filter_explicit and home not in selected_homes:
                    continue
                values = configured if isinstance(configured, list) else [configured]
                for value in values:
                    for candidate in self._workspace_candidates(str(value)):
                        mapping.setdefault(candidate, tags)
        return mapping

    def _effective_projects(
        self, scope_args: ScopeArgs, context: ResolutionContext
    ) -> list[str] | None:
        if not scope_args.projects and not scope_args.tags:
            return None
        projects = list(dict.fromkeys(scope_args.projects))
        if not scope_args.tags:
            return projects
        requested = set(normalize_tags(scope_args.tags))
        config = {
            "projects": context.project_config,
            "project_tags": getattr(context, "project_tags", {}) or {},
        }
        tagged = [
            project
            for project in context.project_config
            if requested.intersection(project_tags_for(config, project))
        ]
        if projects:
            project_set = set(projects)
            return [project for project in tagged if project in project_set]
        return tagged

    def _storage_rollup_dimensions(
        self,
        dimensions: list[str],
        project_map: dict[str, str] | None,
        tag_map: dict[str, list[str]] | None = None,
    ) -> list[str]:
        needs_project = bool(project_map and "project" in dimensions)
        needs_tag = "tag" in dimensions
        if not needs_project and not needs_tag:
            return dimensions
        storage_dimensions = [
            "workspace" if dimension in {"project", "tag"} else dimension
            for dimension in dimensions
        ]
        normalized: list[str] = []
        for dimension in storage_dimensions:
            if dimension not in normalized:
                normalized.append(dimension)
        return normalized

    def _apply_tag_rollup(
        self,
        rows: list[dict[str, Any]],
        dimensions: list[str],
        tag_map: dict[str, list[str]] | None,
        *,
        preserve_workspace: bool = False,
    ) -> list[dict[str, Any]]:
        if "tag" not in dimensions:
            return rows
        grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in rows:
            workspace = str(row.get("workspace", ""))
            tags = tag_map.get(workspace) if tag_map else None
            if not tags:
                tags = [UNTAGGED_TAG]
            for tag in tags:
                item = dict(row)
                item["tag"] = tag
                if "workspace" not in dimensions and not preserve_workspace:
                    item.pop("workspace", None)
                key = tuple(item.get(dimension) for dimension in dimensions)
                if key not in grouped:
                    grouped[key] = item
                    continue
                self._merge_rollup_metrics(grouped[key], item)
        return list(grouped.values())

    def _apply_project_rollup(
        self,
        rows: list[dict[str, Any]],
        dimensions: list[str],
        project_map: dict[str, str] | None,
    ) -> list[dict[str, Any]]:
        if not project_map or "project" not in dimensions:
            return rows
        grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            workspace = str(item.get("workspace", ""))
            item["project"] = project_map.get(
                workspace, item.get("project") or workspace or "(none)"
            )
            if "workspace" not in dimensions:
                item.pop("workspace", None)
            key = tuple(item.get(dimension) for dimension in dimensions)
            if key not in grouped:
                grouped[key] = item
                continue
            self._merge_rollup_metrics(grouped[key], item)
        return list(grouped.values())

    def _merge_rollup_metrics(self, existing: dict[str, Any], item: dict[str, Any]) -> None:
        for field in (
            "sessions",
            "messages",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_creation_tokens",
        ):
            existing[field] = (existing.get(field) or 0) + (item.get(field) or 0)
        existing_time = existing.get("time_seconds")
        item_time = item.get("time_seconds")
        if existing_time is None and item_time is None:
            existing["time_seconds"] = None
            existing["time_hms"] = None
            existing["time_hours"] = None
            return
        existing["time_seconds"] = (existing_time or 0) + (item_time or 0)
        existing["time_hms"] = self._format_rollup_seconds(existing.get("time_seconds") or 0)
        existing["time_hours"] = existing.get("time_seconds", 0) / 3600

    def _format_rollup_seconds(self, value: Any) -> str:
        try:
            seconds = int(float(value))
        except (TypeError, ValueError):
            return ""
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    def _scope_request_metadata(
        self, scope_args: ScopeArgs, context: ResolutionContext
    ) -> dict[str, Any]:
        """Describe the user's requested scope for human output."""
        if scope_args.tags:
            return {"type": "tag", "values": list(scope_args.tags)}
        if scope_args.projects:
            return {"type": "project", "values": list(scope_args.projects)}
        if scope_args.all_workspaces:
            return {"type": "all_workspaces", "values": []}
        if scope_args.glob_patterns:
            return {"type": "workspace_glob", "values": list(scope_args.glob_patterns)}
        if scope_args.regex_patterns:
            return {"type": "workspace_regex", "values": list(scope_args.regex_patterns)}
        if scope_args.name_patterns:
            return {"type": "workspace_name", "values": list(scope_args.name_patterns)}
        if scope_args.patterns:
            return {"type": "workspace_path", "values": list(scope_args.patterns)}
        if scope_args.this_only and context.cwd_workspace:
            return {"type": "current_workspace", "values": [context.cwd_workspace]}
        if context.cwd_project:
            return {"type": "current_project", "values": [context.cwd_project]}
        if context.cwd_workspace:
            return {"type": "current_workspace", "values": [context.cwd_workspace]}
        return {"type": "cached_default", "values": []}

    def _selected_homes(self, scope_args: ScopeArgs, context: ResolutionContext) -> list[str]:
        if scope_args.all_homes:
            homes = ["local"]
            if not scope_args.no_wsl:
                homes.extend(f"wsl:{item}" for item in context.available_homes.get("wsl", []))
            if not scope_args.no_windows:
                homes.extend(
                    f"windows:{item}" for item in context.available_homes.get("windows", [])
                )
            if not scope_args.no_remote:
                homes.extend(f"remote:{item}" for item in context.available_homes.get("remote", []))
            if not scope_args.no_web:
                homes.append("web")
            return list(dict.fromkeys(homes))
        if scope_args.home_names:
            return list(dict.fromkeys(scope_args.home_names))
        if scope_args.home_type:
            if scope_args.home_type == "local":
                return ["local"]
            return [
                f"{scope_args.home_type}:{item}"
                for item in context.available_homes.get(scope_args.home_type, [])
            ]
        return ["local"]

    def _workspace_values(self, scope_args: ScopeArgs, context: ResolutionContext) -> list[str]:
        if scope_args.all_workspaces:
            return []
        if scope_args.this_only and context.cwd_workspace:
            return self._workspace_candidates(context.cwd_workspace)
        if scope_args.patterns:
            candidates: list[str] = []
            for pattern in scope_args.patterns:
                candidates.extend(self._workspace_candidates(pattern))
            return list(dict.fromkeys(candidates))
        if context.cwd_project:
            return []
        if context.cwd_workspace:
            return self._workspace_candidates(context.cwd_workspace)
        return []

    def _project_metadata(
        self,
        scope_args: ScopeArgs,
        context: ResolutionContext,
        projects: list[str] | None = None,
    ) -> tuple[list[str], list[str], dict[str, str]]:
        homes: list[str] = []
        workspaces_by_key: dict[str, str] = {}
        display_map: dict[str, str] = {}
        selected_homes = set(self._selected_homes(scope_args, context))
        home_filter_explicit = bool(
            scope_args.all_homes or scope_args.home_names or scope_args.home_type
        )
        for project in projects if projects is not None else scope_args.projects:
            project_def = context.project_config.get(project, {})
            for home, configured in project_def.items():
                if home_filter_explicit and home not in selected_homes:
                    continue
                homes.append(home)
                values = configured if isinstance(configured, list) else [configured]
                for value in values:
                    ref = build_workspace_ref(str(value))
                    workspaces_by_key.setdefault(ref.key, ref.display)
                    display_map.setdefault(ref.key, ref.display)
        return (
            list(dict.fromkeys(homes)),
            sorted(workspaces_by_key.values()),
            display_map,
        )

    def _project_filter(
        self,
        scope_args: ScopeArgs,
        context: ResolutionContext,
        projects: list[str] | None = None,
    ) -> tuple[list[str], list[str]]:
        homes: list[str] = []
        workspaces: list[str] = []
        selected_homes = set(self._selected_homes(scope_args, context))
        home_filter_explicit = bool(
            scope_args.all_homes or scope_args.home_names or scope_args.home_type
        )
        for project in projects if projects is not None else scope_args.projects:
            project_def = context.project_config.get(project, {})
            for home, configured in project_def.items():
                if home_filter_explicit and home not in selected_homes:
                    continue
                homes.append(home)
                values = configured if isinstance(configured, list) else [configured]
                for value in values:
                    workspaces.extend(self._workspace_candidates(str(value)))
        return list(dict.fromkeys(homes)), list(dict.fromkeys(workspaces))

    def _workspace_candidates(self, value: str) -> list[str]:
        candidates = [value]
        decoded = decode_workspace_path(value, verify_local=False)
        if decoded not in candidates:
            candidates.append(decoded)
        if is_encoded_workspace_name(value):
            short = value.strip("-").split("-")[-1]
            if short and short not in candidates:
                candidates.append(short)
        return candidates

    def _workspace_rows_from_db(self, stats: Dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for workspace, values in stats.get("by_workspace", {}).items():
            if not isinstance(values, dict):
                continue
            rows.append(
                {
                    "home": "",
                    "workspace": workspace,
                    "workspace_key": workspace,
                    "workspace_display": workspace,
                    "sessions": values.get("sessions", 0),
                    "messages": values.get("messages", 0),
                }
            )
        rows.sort(key=lambda row: row["sessions"], reverse=True)
        return rows

    def _empty_cached_stats(self) -> Dict[str, Any]:
        return {
            "sessions": 0,
            "total_sessions": 0,
            "messages": 0,
            "total_messages": 0,
            "main_sessions": 0,
            "agent_sessions": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0},
            "by_agent": {},
            "by_home": {},
            "by_workspace": {},
            "by_model": {},
            "by_tool": {},
            "time_stats": {
                "total_duration_seconds": 0,
                "sessions_with_time": 0,
                "average_duration_seconds": 0,
                "by_day": {},
            },
            "workspace_rows": [],
            "workspace_display_map": {},
            "cache": {"cached": True, "last_synced": None},
        }

    def _filters_from_scope(self, scope: ConcreteScope) -> dict[str, Any]:
        homes: list[str] = []
        workspaces: list[str] = []
        for record in scope:
            homes.append(record.home)
            workspaces.append(record.workspace_key or record.workspace)
            if record.workspace not in workspaces:
                workspaces.append(record.workspace)
        filters: dict[str, Any] = {}
        if homes:
            filters["homes"] = list(dict.fromkeys(homes))
        if workspaces:
            filters["workspaces"] = list(dict.fromkeys(workspaces))
        return filters
