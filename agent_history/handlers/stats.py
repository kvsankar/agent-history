"""Handler for session stats command.

This module provides the SessionStatsHandler that computes aggregate
statistics from sessions in a resolved ConcreteScope. It supports
various grouping dimensions and time tracking.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from typing import Any, Dict

from agent_history.core.workspaces import build_scope_metadata, build_workspace_rows
from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs, ResolutionContext, ScopeArgs
from agent_history.scope.types import ConcreteScope
from agent_history.utils.paths import decode_workspace_path, is_encoded_workspace_name
from agent_history.utils.workspace_ref import build_workspace_ref


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
        from agent_history.storage.metrics import get_stats_rollup_from_db

        dimensions = group_list or ["project"]
        rows = get_stats_rollup_from_db(
            filters=self._filters_from_scope(scope),
            by=dimensions,
            metric=verb_args.get("metric") or "all",
            top=verb_args.get("top"),
            sort_by=verb_args.get("sort"),
            sort_direction=verb_args.get("sort_direction") or "default",
        )
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

        db_path = get_metrics_db_path()
        if not db_path.exists():
            return self._missing_cache_result(metadata, group_list, verb_args)

        if verb_args.get("stats_mode") == "rollup":
            return self._execute_cached_rollup(filters, metadata, group_list, verb_args)

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
    ) -> CommandResult:
        from agent_history.storage.metrics import get_scoped_stats_from_db, get_stats_rollup_from_db

        dimensions = group_list or ["project"]
        rows = get_stats_rollup_from_db(
            filters=filters,
            by=dimensions,
            metric=verb_args.get("metric") or "all",
            top=verb_args.get("top"),
            sort_by=verb_args.get("sort"),
            sort_direction=verb_args.get("sort_direction") or "default",
        )
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

        if scope_args.projects:
            homes, workspaces = self._project_filter(scope_args, context)
            filters["homes"] = homes
            filters["workspaces"] = workspaces
            project_homes, project_workspaces, display_map = self._project_metadata(
                scope_args, context
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

    def _scope_request_metadata(
        self, scope_args: ScopeArgs, context: ResolutionContext
    ) -> dict[str, Any]:
        """Describe the user's requested scope for human output."""
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
        self, scope_args: ScopeArgs, context: ResolutionContext
    ) -> tuple[list[str], list[str], dict[str, str]]:
        homes: list[str] = []
        workspaces_by_key: dict[str, str] = {}
        display_map: dict[str, str] = {}
        selected_homes = set(self._selected_homes(scope_args, context))
        home_filter_explicit = bool(
            scope_args.all_homes or scope_args.home_names or scope_args.home_type
        )
        for project in scope_args.projects:
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
        self, scope_args: ScopeArgs, context: ResolutionContext
    ) -> tuple[list[str], list[str]]:
        homes: list[str] = []
        workspaces: list[str] = []
        selected_homes = set(self._selected_homes(scope_args, context))
        home_filter_explicit = bool(
            scope_args.all_homes or scope_args.home_names or scope_args.home_type
        )
        for project in scope_args.projects:
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
