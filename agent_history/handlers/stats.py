"""Handler for session stats command.

This module provides the SessionStatsHandler that computes aggregate
statistics from sessions in a resolved ConcreteScope. It supports
various grouping dimensions and time tracking.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Optional

from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs
from agent_history.core.workspaces import build_scope_metadata, build_workspace_rows
from agent_history.scope.types import ConcreteRecord, ConcreteScope


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

        # If sync was used, overlay token totals from metrics database
        # This ensures accurate token counts that were parsed during sync
        if verb_args.get("sync"):
            try:
                from agent_history.storage.metrics import (
                    get_session_stats_from_db,
                    get_time_stats_from_db,
                    get_tool_usage_stats_from_db,
                )

                db_stats = get_session_stats_from_db()
                db_stats["by_tool"] = get_tool_usage_stats_from_db()
                if include_time:
                    db_stats["time_stats"] = get_time_stats_from_db()
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

    def _compute_stats(
        self, scope: ConcreteScope, group_by: Optional[str], include_time: bool
    ) -> Dict[str, Any]:
        """Compute aggregate statistics from scope.

        Args:
            scope: The resolved concrete scope with sessions.
            group_by: Optional grouping dimension.
            include_time: Whether to include time tracking stats.

        Returns:
            Dictionary containing:
            - sessions: total session count
            - messages: total message count
            - user_messages: count of user messages
            - assistant_messages: count of assistant messages
            - tokens: input/output/cache token counts
            - by_agent: stats per agent
            - by_model: stats per model
            - by_tool: stats per tool (if available)
            - by_home: stats per home
            - by_workspace: stats per workspace
            - by_day: stats per day (if group_by='day')
            - time_stats: time tracking (if include_time=True)
        """
        stats: Dict[str, Any] = {
            "sessions": 0,
            "main_sessions": 0,
            "agent_sessions": 0,
            "messages": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "tokens": {
                "input": 0,
                "output": 0,
                "cache_read": 0,
                "cache_creation": 0,
            },
            "by_agent": defaultdict(lambda: {"sessions": 0, "messages": 0}),
            "by_model": defaultdict(lambda: {"messages": 0, "tokens": 0}),
            "by_tool": defaultdict(lambda: {"uses": 0, "errors": 0}),
            "by_home": defaultdict(lambda: {"sessions": 0, "messages": 0}),
            "by_workspace": defaultdict(lambda: {"sessions": 0, "messages": 0}),
        }

        # Add day grouping if requested
        if group_by == "day":
            stats["by_day"] = defaultdict(lambda: {"sessions": 0, "messages": 0})

        # Process all sessions
        for record in scope:
            for session in record.sessions:
                self._add_session_stats(stats, session, record, group_by)

        # Convert defaultdicts to regular dicts and sort by count
        stats["by_agent"] = self._sort_by_count(dict(stats["by_agent"]), "sessions")
        stats["by_model"] = self._sort_by_count(dict(stats["by_model"]), "messages")
        stats["by_tool"] = self._sort_by_count(dict(stats["by_tool"]), "uses")
        stats["by_home"] = self._sort_by_count(dict(stats["by_home"]), "sessions")
        stats["by_workspace"] = self._sort_by_count(dict(stats["by_workspace"]), "sessions")

        if "by_day" in stats:
            stats["by_day"] = self._sort_by_date(dict(stats["by_day"]))

        # Add time stats if requested
        if include_time:
            stats["time_stats"] = self._compute_time_stats(scope)

        return stats

    def _add_session_stats(
        self,
        stats: Dict[str, Any],
        session: Dict[str, Any],
        record: ConcreteRecord,
        group_by: Optional[str],
    ) -> None:
        """Add a session's stats to the aggregate.

        Args:
            stats: The aggregate stats dictionary to update.
            session: The session dictionary to process.
            record: The ConcreteRecord containing home/workspace info.
            group_by: Optional grouping dimension for extra breakdowns.
        """
        # Session counts
        stats["sessions"] += 1
        is_agent_session = session.get("is_agent", False)
        if is_agent_session:
            stats["agent_sessions"] += 1
        else:
            stats["main_sessions"] += 1

        # Message counts
        message_count = session.get("message_count", 0)
        user_messages = session.get("user_messages", 0)
        assistant_messages = session.get("assistant_messages", 0)

        stats["messages"] += message_count
        stats["user_messages"] += user_messages
        stats["assistant_messages"] += assistant_messages

        # Token counts (from session-level aggregates if available)
        tokens = session.get("tokens", {})
        if isinstance(tokens, dict) and tokens:
            # Use nested tokens dict if present and non-empty
            stats["tokens"]["input"] += tokens.get("input", 0)
            stats["tokens"]["output"] += tokens.get("output", 0)
            stats["tokens"]["cache_read"] += tokens.get("cache_read", 0)
            stats["tokens"]["cache_creation"] += tokens.get("cache_creation", 0)
        else:
            # Fallback: try individual token fields at session level
            stats["tokens"]["input"] += session.get("input_tokens", 0) or 0
            stats["tokens"]["output"] += session.get("output_tokens", 0) or 0
            stats["tokens"]["cache_read"] += session.get("cache_read_tokens", 0) or 0
            stats["tokens"]["cache_creation"] += session.get("cache_creation_tokens", 0) or 0

        # Agent breakdown
        agent = session.get("agent", "unknown")
        stats["by_agent"][agent]["sessions"] += 1
        stats["by_agent"][agent]["messages"] += message_count

        # Model breakdown (from session-level summary if available)
        model = session.get("model") or session.get("primary_model")
        if model:
            output_tokens = (
                tokens.get("output", 0)
                if isinstance(tokens, dict) and tokens
                else session.get("output_tokens", 0) or 0
            )
            stats["by_model"][model]["messages"] += message_count
            stats["by_model"][model]["tokens"] += output_tokens

        # Tool breakdown
        tool_uses = session.get("tool_uses", [])
        if isinstance(tool_uses, list):
            for tool_use in tool_uses:
                tool_name = tool_use.get("name") or tool_use.get("tool_name", "unknown")
                stats["by_tool"][tool_name]["uses"] += 1
                if tool_use.get("is_error") or tool_use.get("error"):
                    stats["by_tool"][tool_name]["errors"] += 1
        elif isinstance(tool_uses, dict):
            # Some formats store tool uses as {tool_name: count}
            for tool_name, count in tool_uses.items():
                stats["by_tool"][tool_name]["uses"] += count

        # Home breakdown
        stats["by_home"][record.home]["sessions"] += 1
        stats["by_home"][record.home]["messages"] += message_count

        # Workspace breakdown
        stats["by_workspace"][record.workspace]["sessions"] += 1
        stats["by_workspace"][record.workspace]["messages"] += message_count

        # Day breakdown (if requested)
        if "by_day" in stats:
            day_key = self._extract_day_key(session)
            if day_key:
                stats["by_day"][day_key]["sessions"] += 1
                stats["by_day"][day_key]["messages"] += message_count

    def _extract_day_key(self, session: Dict[str, Any]) -> Optional[str]:
        """Extract a day key (YYYY-MM-DD) from a session.

        Args:
            session: The session dictionary.

        Returns:
            Date string in YYYY-MM-DD format, or None if no date found.
        """
        # Try various date fields
        for field in ["modified", "created", "start_time", "timestamp"]:
            value = session.get(field)
            if value:
                if isinstance(value, datetime):
                    return value.strftime("%Y-%m-%d")
                elif isinstance(value, str):
                    # Try to parse ISO format
                    try:
                        if "T" in value:
                            return value.split("T")[0]
                        elif len(value) >= 10 and value[4] == "-" and value[7] == "-":
                            return value[:10]
                    except (ValueError, IndexError):
                        pass
        return None

    def _compute_time_stats(self, scope: ConcreteScope) -> Dict[str, Any]:
        """Compute time tracking statistics.

        Args:
            scope: The resolved concrete scope with sessions.

        Returns:
            Dictionary containing time-related statistics:
            - total_duration_seconds: total time across all sessions
            - average_duration_seconds: average session duration
            - sessions_with_time: count of sessions with time data
            - by_day: time spent per day
        """
        time_stats: Dict[str, Any] = {
            "total_duration_seconds": 0,
            "sessions_with_time": 0,
            "by_day": defaultdict(float),
        }

        for record in scope:
            for session in record.sessions:
                duration = session.get("duration_seconds") or session.get("duration")
                if duration:
                    try:
                        duration_float = float(duration)
                        time_stats["total_duration_seconds"] += duration_float
                        time_stats["sessions_with_time"] += 1

                        # Add to day breakdown
                        day_key = self._extract_day_key(session)
                        if day_key:
                            time_stats["by_day"][day_key] += duration_float
                    except (ValueError, TypeError):
                        pass

        # Compute average
        if time_stats["sessions_with_time"] > 0:
            time_stats["average_duration_seconds"] = (
                time_stats["total_duration_seconds"] / time_stats["sessions_with_time"]
            )
        else:
            time_stats["average_duration_seconds"] = 0

        # Convert by_day to regular dict
        time_stats["by_day"] = dict(time_stats["by_day"])

        return time_stats

    def _sort_by_count(
        self, breakdown: Dict[str, Dict[str, Any]], count_key: str
    ) -> Dict[str, Dict[str, Any]]:
        """Sort a breakdown dictionary by count descending.

        Args:
            breakdown: Dictionary of {key: {count_key: value, ...}}.
            count_key: The key to sort by (e.g., "sessions", "messages").

        Returns:
            OrderedDict-like dict sorted by count descending.
        """
        sorted_items = sorted(breakdown.items(), key=lambda x: x[1].get(count_key, 0), reverse=True)
        return dict(sorted_items)

    def _sort_by_date(self, breakdown: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Sort a date-keyed breakdown by date ascending.

        Args:
            breakdown: Dictionary of {date_str: {...}}.

        Returns:
            Dict sorted by date ascending.
        """
        sorted_items = sorted(breakdown.items(), key=lambda x: x[0])
        return dict(sorted_items)

    def _apply_top_limit(self, stats: Dict[str, Any], top_limit: int) -> Dict[str, Any]:
        """Apply top limit to breakdown dictionaries.

        Args:
            stats: The full statistics dictionary.
            top_limit: Maximum number of items to keep in each breakdown.

        Returns:
            Stats dictionary with limited breakdowns.
        """
        breakdown_keys = ["by_agent", "by_model", "by_tool", "by_home", "by_workspace", "by_day"]

        for key in breakdown_keys:
            if key in stats and isinstance(stats[key], dict):
                items = list(stats[key].items())[:top_limit]
                stats[key] = dict(items)

        return stats
