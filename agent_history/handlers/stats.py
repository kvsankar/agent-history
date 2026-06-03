"""Handler for session stats command.

This module provides the SessionStatsHandler that computes aggregate
statistics from sessions in a resolved ConcreteScope. It supports
various grouping dimensions and time tracking.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from typing import Any, Dict

from agent_history.core.workspaces import build_scope_metadata, build_workspace_rows
from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope


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

        # Compute statistics
        from agent_history.core.stats import apply_top_limit, compute_stats, overlay_metrics

        group_list = []
        if isinstance(group_by, list):
            group_list = [value for value in group_by if value]
        elif isinstance(group_by, str):
            group_list = [group_by]

        include_day = "day" in group_list
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
            try:
                from agent_history.storage.metrics import (
                    get_session_stats_from_db,
                    get_time_stats_from_db,
                    get_tool_usage_stats_from_db,
                )

                file_paths = self._scope_file_paths(scope)
                db_stats = get_session_stats_from_db(file_paths=file_paths)
                db_stats["by_tool"] = get_tool_usage_stats_from_db(file_paths=file_paths)
                if include_time:
                    db_stats["time_stats"] = get_time_stats_from_db(file_paths=file_paths)
                stats = overlay_metrics(stats, db_stats)
            except Exception:
                pass  # Fall back to scope-based stats if DB query fails

        # Apply top limit to breakdowns if specified
        if top_limit:
            stats = apply_top_limit(stats, top_limit)

        if top_ws:
            by_workspace = stats.get("by_workspace")
            if isinstance(by_workspace, dict):
                stats["by_workspace"] = dict(list(by_workspace.items())[:top_ws])

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
        if top_ws:
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
            },
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
