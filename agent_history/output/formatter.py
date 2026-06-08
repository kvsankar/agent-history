"""Output formatters for cagelens command results.

This module provides the OutputFormatter class and concrete formatter
implementations for rendering CommandResult data in various formats
(table, JSON, TSV, etc.).

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from agent_history.handlers.base import CommandResult
from agent_history.scope.context import OutputArgs
from agent_history.types import (
    HomeDict,
    ProjectDict,
    SessionDict,
    StatsDict,
    WorkspaceDict,
)


class FormatterError(Exception):
    """Error formatting command output."""

    pass


def _workspace_display(item: dict[str, Any], display_map: dict[str, str] | None = None) -> str:
    """Pick a workspace display string from an item or display map."""
    if not item:
        return ""
    display = item.get("workspace_display") or item.get("workspace_readable")
    if display:
        return str(display)
    workspace = item.get("workspace") or ""
    if display_map and workspace in display_map:
        return str(display_map[workspace])
    return str(workspace)


def _truncate_tail(value: str, max_len: int) -> str:
    if max_len and len(value) > max_len:
        return "..." + value[-(max_len - 3) :]
    return value


def _format_modified_date(modified: Any, *, date_format: str, truncate: int) -> str:
    if isinstance(modified, datetime):
        return modified.strftime(date_format)
    if isinstance(modified, str):
        return modified[:truncate] if truncate else modified
    return ""


def _format_modified_iso(modified: Any) -> str:
    if isinstance(modified, datetime):
        return modified.isoformat()
    return str(modified) if modified else ""


def _build_session_rows(
    sessions: list[SessionDict],
    *,
    workspace_formatter: Callable[[str], str],
    modified_formatter: Callable[[Any], str],
) -> list[list[str]]:
    rows = []
    for session in sessions:
        workspace = workspace_formatter(_workspace_display(session))
        rows.append(
            [
                session.get("agent", ""),
                session.get("home", "local"),
                workspace,
                session.get("filename", ""),
                str(session.get("message_count", "")),
                modified_formatter(session.get("modified")),
            ]
        )
    return rows


def _build_workspace_rows(
    workspaces: list[WorkspaceDict],
    *,
    workspace_formatter: Callable[[str], str],
    modified_formatter: Callable[[Any], str],
) -> list[list[str]]:
    rows = []
    for workspace in workspaces:
        modified = workspace.get("modified") or workspace.get("last_modified")
        rows.append(
            [
                workspace.get("home", "local"),
                workspace_formatter(_workspace_display(workspace)),
                str(workspace.get("session_count", "")),
                workspace.get("status", "unknown"),
                modified_formatter(modified),
            ]
        )
    return rows


def _format_project_sources(sources: Any) -> str:
    if isinstance(sources, list):
        return ", ".join(sources) if len(sources) <= 3 else f"{len(sources)} sources"
    return str(sources)


def _format_project_workspaces(
    workspaces: Any, display_map: dict[str, str], workspace_count: Any
) -> str:
    if isinstance(workspaces, list):
        display_workspaces = [display_map.get(str(ws), str(ws)) for ws in workspaces]
        return (
            ", ".join(display_workspaces)
            if len(display_workspaces) <= 2
            else f"{len(display_workspaces)} workspaces"
        )
    if workspace_count is not None:
        return str(workspace_count)
    return str(workspaces)


def _stats_group_list(metadata: dict[str, Any]) -> list[str]:
    default_groups = ["agent", "home", "workspace"]
    group_by = metadata.get("group_by") or []
    if isinstance(group_by, str):
        group_list = [group_by]
    else:
        group_list = list(group_by)
    result = list(default_groups)
    for group in group_list:
        if group not in result:
            result.append(group)
    return result


def _stats_count(value: Any, key: str) -> Any:
    if not isinstance(value, dict):
        return value
    for candidate in (key, "sessions", "uses", "messages"):
        if candidate in value:
            return value[candidate]
    return value


def _format_scope_request(scope_request: dict[str, Any] | None) -> str:
    if not isinstance(scope_request, dict):
        return "resolved scope"
    values = [str(value) for value in scope_request.get("values", [])]
    scope_type = scope_request.get("type")
    joined = ", ".join(values)
    if scope_type == "project":
        return f"project {joined}" if len(values) == 1 else f"projects {joined}"
    if scope_type == "current_project":
        return f"current project {joined}"
    if scope_type == "all_workspaces":
        return "all workspaces"
    if scope_type == "workspace_glob":
        return f"workspace glob {joined}" if len(values) == 1 else f"workspace globs {joined}"
    if scope_type == "workspace_regex":
        return f"workspace regex {joined}" if len(values) == 1 else f"workspace regexes {joined}"
    if scope_type == "workspace_name":
        return (
            f"workspace name contains {joined}"
            if len(values) == 1
            else f"workspace name contains any of {joined}"
        )
    if scope_type == "workspace_path":
        return f"workspace path {joined}" if len(values) == 1 else f"workspace paths {joined}"
    if scope_type == "current_workspace":
        return f"current workspace {joined}"
    if scope_type == "cached_default":
        return "cached local metrics"
    return "resolved scope"


def _format_scope_items(values: Any, *, max_items: int = 4) -> str:
    if not values:
        return "0"
    items = [str(value) for value in values]
    count = len(items)
    if count <= max_items:
        return f"{count} ({', '.join(items)})"
    shown = ", ".join(items[:max_items])
    return f"{count} ({shown}, ...)"


def _append_scope_summary(
    lines: list[str],
    stats: Any,
    metadata: dict[str, Any],
) -> None:
    homes = metadata.get("homes") or []
    workspaces = metadata.get("workspaces") or []
    if isinstance(stats, dict):
        total_sessions = stats.get("total_sessions", stats.get("sessions"))
    else:
        total_sessions = metadata.get("total_sessions")

    lines.append("Scope:")
    lines.append(f"  Request: {_format_scope_request(metadata.get('scope_request'))}")
    lines.append(f"  Homes: {_format_scope_items(homes)}")
    lines.append(f"  Workspaces: {_format_scope_items(workspaces)}")
    if total_sessions is not None:
        lines.append(f"  Sessions: {total_sessions}")
    lines.append("")


def _format_stat_number(value: Any, *, human: bool = False) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not human:
        return str(int(number)) if number.is_integer() else str(number)
    abs_number = abs(number)
    for suffix, divisor in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if abs_number >= divisor:
            formatted = number / divisor
            return f"{formatted:.1f}{suffix}".replace(".0", "")
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def _format_duration(value: Any, *, human: bool = False) -> str:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return str(value)
    if not human:
        return f"{seconds}s"
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def _append_simple_stats_group(
    lines: list[str],
    *,
    title: str,
    values: dict[str, Any],
    key: str = "sessions",
    human: bool = False,
) -> None:
    if not values:
        return
    lines.append(f"{title}:")
    for label, value in sorted(values.items()):
        lines.append(f"  {label}: {_format_stat_number(_stats_count(value, key), human=human)}")
    lines.append("")


def _append_workspace_stats_group(
    lines: list[str],
    stats: StatsDict,
    workspace_display_map: dict[str, str],
    *,
    limit: int | str | None = None,
    human: bool = False,
) -> None:
    by_workspace = stats.get("by_workspace", {})
    if not by_workspace:
        return
    lines.append("By Workspace:")
    sorted_ws = sorted(by_workspace.items(), key=lambda x: -_stats_count(x[1], "sessions"))
    display_limit = len(sorted_ws) if limit == "all" else (limit or 10)
    for ws, value in sorted_ws[:display_limit]:
        ws_display = _workspace_display({"workspace": ws}, display_map=workspace_display_map)
        if len(ws_display) > 50:
            ws_display = "..." + ws_display[-47:]
        count = _format_stat_number(_stats_count(value, "sessions"), human=human)
        lines.append(f"  {ws_display}: {count}")
    if len(by_workspace) > display_limit:
        lines.append(
            f"  ... and {len(by_workspace) - display_limit} more "
            "(use --top-ws all or --format json)"
        )
    lines.append("")


def _append_model_stats_group(lines: list[str], stats: StatsDict, *, human: bool = False) -> None:
    by_model = stats.get("by_model", {})
    if not by_model:
        return
    lines.append("By Model:")
    for model, value in sorted(by_model.items()):
        if isinstance(value, dict):
            messages = _format_stat_number(value.get("messages", 0), human=human)
            tokens = _format_stat_number(value.get("tokens", 0), human=human)
            lines.append(f"  {model}: {messages} messages, {tokens} tokens")
        else:
            lines.append(f"  {model}: {value}")
    lines.append("")


def _append_tool_stats_group(lines: list[str], stats: StatsDict, *, human: bool = False) -> None:
    by_tool = stats.get("by_tool", {})
    if not by_tool:
        return
    lines.append("By Tool:")
    for tool, value in sorted(by_tool.items()):
        if isinstance(value, dict):
            uses = _format_stat_number(value.get("uses", 0), human=human)
            errors = _format_stat_number(value.get("errors", 0), human=human)
            lines.append(f"  {tool}: {uses} uses, {errors} errors")
        else:
            lines.append(f"  {tool}: {value}")
    lines.append("")


def _append_time_stats_group(lines: list[str], stats: StatsDict, *, human: bool = False) -> None:
    time_stats = stats.get("time_stats", {})
    if not isinstance(time_stats, dict):
        return
    by_day = time_stats.get("by_day", {})
    if not isinstance(by_day, dict) or not by_day:
        return
    lines.append("Time by Day:")
    for day, seconds in sorted(by_day.items()):
        lines.append(f"  {day}: {_format_duration(seconds, human=human)}")
    lines.append("")


def _append_stats_dashboard(lines: list[str], stats: StatsDict, *, human: bool = False) -> None:
    total_sessions = stats.get("total_sessions", stats.get("sessions", 0))
    total_messages = stats.get("total_messages", stats.get("messages", 0))
    lines.append(
        "Sessions: "
        f"{_format_stat_number(total_sessions, human=human)}  "
        f"Messages: {_format_stat_number(total_messages, human=human)}"
    )

    main_sessions = stats.get("main_sessions", 0)
    agent_sessions = stats.get("agent_sessions", 0)
    if main_sessions or agent_sessions:
        lines.append(
            "Session Types: "
            f"main {_format_stat_number(main_sessions, human=human)}, "
            f"agent {_format_stat_number(agent_sessions, human=human)}"
        )

    user_messages = stats.get("user_messages", 0)
    assistant_messages = stats.get("assistant_messages", 0)
    if user_messages or assistant_messages:
        lines.append(
            "Message Types: "
            f"user {_format_stat_number(user_messages, human=human)}, "
            f"assistant {_format_stat_number(assistant_messages, human=human)}"
        )

    tokens = stats.get("tokens", {})
    if isinstance(tokens, dict) and any(tokens.values()):
        lines.append(
            "Tokens: "
            f"input {_format_stat_number(tokens.get('input', 0), human=human)}, "
            f"output {_format_stat_number(tokens.get('output', 0), human=human)}, "
            f"cache read {_format_stat_number(tokens.get('cache_read', 0), human=human)}, "
            f"cache create {_format_stat_number(tokens.get('cache_creation', 0), human=human)}"
        )

    by_tool = stats.get("by_tool", {})
    if isinstance(by_tool, dict) and by_tool:
        tool_uses = sum(_stats_count(value, "uses") or 0 for value in by_tool.values())
        tool_errors = sum(
            value.get("errors", 0) for value in by_tool.values() if isinstance(value, dict)
        )
        lines.append(
            "Tools: "
            f"{_format_stat_number(tool_uses, human=human)} uses, "
            f"{_format_stat_number(tool_errors, human=human)} errors"
        )

    by_model = stats.get("by_model", {})
    if isinstance(by_model, dict) and by_model:
        top_models = ", ".join(str(model) for model in list(by_model)[:3])
        suffix = f" ({top_models})" if top_models else ""
        lines.append(f"Models: {len(by_model)}{suffix}")

    time_stats = stats.get("time_stats", {})
    if isinstance(time_stats, dict) and time_stats:
        total_time = time_stats.get("total_duration_seconds", 0)
        sessions_with_time = time_stats.get("sessions_with_time", 0)
        average_time = time_stats.get("average_duration_seconds", 0)
        lines.append(
            "Time: "
            f"total {_format_duration(total_time, human=human)}, "
            f"avg {_format_duration(average_time, human=human)}, "
            f"sessions {_format_stat_number(sessions_with_time, human=human)}"
        )

    lines.append("")


def _append_stats_guidance(
    lines: list[str],
    stats: StatsDict,
    metadata: dict[str, Any],
) -> None:
    coverage = [
        "sessions",
        "messages",
        "tokens",
        "tools",
        "models",
        "time",
        "agents",
        "homes",
        "workspaces",
    ]
    if stats.get("by_day"):
        coverage.append("days")
    lines.append("Metric Coverage:")
    lines.append(f"  summarized: {', '.join(coverage)}")

    drilldowns = [
        "--models for per-model messages/tokens",
        "--tools for per-tool uses/errors",
        "--time for time by day",
        "--by-day for session/message counts by day",
        "--top-ws all for all workspace rows",
        "--format json for the full metrics payload",
    ]
    sync_stats = metadata.get("sync_stats")
    if isinstance(sync_stats, dict) and sync_stats.get("errors"):
        drilldowns.append("--sync --force to retry failed metric syncs")
    lines.append("Drilldowns:")
    for item in drilldowns:
        lines.append(f"  {item}")
    lines.append("")


def _rollup_columns(metadata: dict[str, Any]) -> list[str]:
    dimensions = [str(dimension).upper() for dimension in metadata.get("dimensions", [])]
    metric = metadata.get("metric") or "all"
    columns = list(dimensions)
    if metric in ("time", "all"):
        columns.extend(["TIME_HOURS", "TIME_SECONDS"])
    if metric in ("tokens", "all"):
        columns.extend(["INPUT_TOKENS", "OUTPUT_TOKENS", "CACHE_READ", "CACHE_CREATE"])
    if metric == "all":
        columns.extend(["SESSIONS", "MESSAGES"])
    return columns


def _rollup_row_values(row: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    dimensions = [str(dimension) for dimension in metadata.get("dimensions", [])]
    metric = metadata.get("metric") or "all"
    values = [str(row.get(dimension, "")) for dimension in dimensions]
    if metric in ("time", "all"):
        time_hours = row.get("time_hours")
        values.append("" if time_hours is None else f"{float(time_hours):.2f}")
        time_seconds = row.get("time_seconds")
        values.append("" if time_seconds is None else str(int(time_seconds)))
    if metric in ("tokens", "all"):
        values.extend(
            [
                str(row.get("input_tokens", 0)),
                str(row.get("output_tokens", 0)),
                str(row.get("cache_read_tokens", 0)),
                str(row.get("cache_creation_tokens", 0)),
            ]
        )
    if metric == "all":
        values.extend([str(row.get("sessions", 0)), str(row.get("messages", 0))])
    return values


class DataFormatter(ABC):
    """Abstract base class for data formatters.

    Subclasses implement format() to render command data in a specific format.
    """

    @abstractmethod
    def format(self, data: Any, data_type: str, metadata: dict[str, Any]) -> str:
        """Format data for output.

        Args:
            data: The command result data to format.
            data_type: Type hint for determining rendering approach.
            metadata: Additional context about the data.

        Returns:
            Formatted string representation of the data.
        """
        pass


class TableFormatter(DataFormatter):
    """Format data as ASCII table."""

    def __init__(self, width: int | None = 120):
        """Initialize with optional table width.

        Args:
            width: Maximum table width in characters (None for no limit).
        """
        self.width = width
        self._formatters = {
            "session_list": self._format_session_list,
            "workspace_list": self._format_workspace_list,
            "home_list": self._format_home_list,
            "stats": self._format_stats,
            "stats_rollup": self._format_stats_rollup,
            "project_list": self._format_project_list,
            "project_details": self._format_project_details,
            "exported_files": self._format_exported_files,
            "gemini_index": self._format_gemini_index,
            "install_result": self._format_install_result,
        }

    def format(self, data: Any, data_type: str, metadata: dict[str, Any]) -> str:
        """Format data as ASCII table."""
        formatter = self._formatters.get(data_type)
        if formatter:
            # Some formatters need metadata, some don't
            if data_type in (
                "stats",
                "stats_rollup",
                "project_details",
                "exported_files",
                "project_list",
                "home_list",
                "gemini_index",
                "install_result",
            ):
                return formatter(data, metadata)
            return formatter(data)
        return str(data)

    def _format_session_list(self, sessions: list[SessionDict]) -> str:
        """Format session list as table."""
        if not sessions:
            return "No sessions found."

        headers = ["AGENT", "HOME", "WORKSPACE", "FILE", "MESSAGES", "MODIFIED"]
        rows = _build_session_rows(
            sessions,
            workspace_formatter=lambda ws: _truncate_tail(ws, 40) if self.width else ws,
            modified_formatter=lambda value: _format_modified_date(
                value, date_format="%Y-%m-%d", truncate=10
            ),
        )

        return self._render_table(headers, rows)

    def _format_workspace_list(self, workspaces: list[WorkspaceDict]) -> str:
        """Format workspace list as table."""
        if not workspaces:
            return "No workspaces found."

        headers = ["HOME", "WORKSPACE", "SESSIONS", "STATUS", "MODIFIED"]
        rows = _build_workspace_rows(
            workspaces,
            workspace_formatter=lambda ws: _truncate_tail(ws, 50) if self.width else ws,
            modified_formatter=lambda value: _format_modified_date(
                value, date_format="%Y-%m-%d %H:%M", truncate=16
            ),
        )

        return self._render_table(headers, rows)

    def _format_home_list(
        self, homes: list[HomeDict], metadata: dict[str, Any] | None = None
    ) -> str:
        """Format home list as table."""
        if not homes:
            return "No homes configured."

        show_counts = True if metadata is None else metadata.get("show_counts", True)
        headers = ["HOME", "TYPE", "STATUS"]
        if show_counts:
            headers.append("SESSIONS")
        rows = []

        for h in homes:
            row = [
                h.get("home", h.get("name", "")),
                h.get("type", ""),
                h.get("status", ""),
            ]
            if show_counts:
                row.append(str(h.get("session_count", "")))
            rows.append(row)

        return self._render_table(headers, rows)

    def _format_stats(self, stats: StatsDict, metadata: dict[str, Any]) -> str:
        """Format statistics as table."""
        lines = []
        workspace_display_map = (
            metadata.get("workspace_display_map") or stats.get("workspace_display_map") or {}
        )
        human = bool(metadata.get("human"))
        top_ws = metadata.get("top_ws")

        _append_scope_summary(lines, stats, metadata)
        _append_stats_dashboard(lines, stats, human=human)

        group_list = _stats_group_list(metadata)
        if "agent" in group_list:
            _append_simple_stats_group(
                lines,
                title="By Agent",
                values=stats.get("by_agent", {}),
                human=human,
            )

        if "home" in group_list:
            _append_simple_stats_group(
                lines,
                title="By Home",
                values=stats.get("by_home", {}),
                human=human,
            )

        if "workspace" in group_list:
            _append_workspace_stats_group(
                lines,
                stats,
                workspace_display_map,
                limit=top_ws,
                human=human,
            )

        if "model" in group_list:
            _append_model_stats_group(lines, stats, human=human)

        if "tool" in group_list:
            _append_tool_stats_group(lines, stats, human=human)

        if "day" in group_list:
            _append_simple_stats_group(
                lines,
                title="By Day",
                values=stats.get("by_day", {}),
                human=human,
            )

        if metadata.get("include_time"):
            _append_time_stats_group(lines, stats, human=human)

        _append_stats_guidance(lines, stats, metadata)

        return "\n".join(lines)

    def _format_stats_rollup(self, rows: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        """Format stats rollup rows as a stable table."""
        if not rows:
            return "No cached stats matched this scope. Run with --sync to refresh."
        headers = _rollup_columns(metadata)
        table_rows = [_rollup_row_values(row, metadata) for row in rows]
        lines: list[str] = []
        _append_scope_summary(lines, rows, metadata)
        lines.append(self._render_table(headers, table_rows))
        return "\n".join(lines)

    def _format_project_list(
        self, projects: list[ProjectDict], metadata: dict[str, Any] | None = None
    ) -> str:
        """Format project list as table."""
        if not projects:
            return "No projects configured."

        workspace_display_map = (metadata or {}).get("workspace_display_map", {})
        show_counts = True if metadata is None else metadata.get("show_counts", True)
        headers = ["PROJECT", "SOURCE", "WORKSPACE"]
        if show_counts:
            headers.append("SESSIONS")
        rows = []

        for p in projects:
            # Handle both legacy (source/workspace as lists) and new (workspace_count) formats
            sources = p.get("source", p.get("homes", []))
            workspaces = p.get("workspace", [])

            source_str = _format_project_sources(sources)
            workspace_str = _format_project_workspaces(
                workspaces, workspace_display_map, p.get("workspace_count")
            )

            row = [
                p.get("project", p.get("name", "")),
                source_str,
                workspace_str,
            ]
            if show_counts:
                row.append(str(p.get("session_count", "")))
            rows.append(row)

        return self._render_table(headers, rows)

    def _format_project_details(self, data: ProjectDict, metadata: dict[str, Any]) -> str:
        """Format project details."""
        lines = []
        project_name = data.get("project", "")
        lines.append(f"Project: {project_name}")
        lines.append(f"Total Sessions: {data.get('total_sessions', 0)}")
        lines.append("")

        workspaces_by_home = data.get("workspaces_by_home", {})
        workspace_display_map = metadata.get("workspace_display_map", {})
        for home, workspaces in workspaces_by_home.items():
            lines.append(f"  {home}:")
            for ws in workspaces:
                ws_path = _workspace_display(ws, display_map=workspace_display_map)
                session_count = ws.get("session_count", 0)
                lines.append(f"    {ws_path} ({session_count} sessions)")

        return "\n".join(lines)

    def _format_exported_files(self, files: list[Path], metadata: dict[str, Any]) -> str:
        """Format list of exported files."""
        count = metadata.get("count", len(files))
        lines = [f"Exported {count} file(s):"]
        for f in files:
            lines.append(f"  {f}")
        return "\n".join(lines)

    def _format_gemini_index(self, data: dict[str, Any], metadata: dict[str, Any]) -> str:
        """Format Gemini hash index results."""
        action = data.get("action")
        mappings = data.get("mappings", [])
        if action == "list":
            if not mappings:
                return str(metadata.get("message") or "No Gemini mappings found.")
            rows = [[str(item.get("hash", "")), str(item.get("path", ""))] for item in mappings]
            return self._render_table(["HASH", "PATH"], rows)

        lines = [str(metadata.get("message") or f"Gemini index {action or 'updated'}.")]
        for key in ("added", "existing", "no_sessions", "indexed", "scanned"):
            if key in data:
                lines.append(f"{key}: {data[key]}")
        if mappings:
            rows = [
                [
                    str(item.get("status", "")),
                    str(item.get("hash", "")),
                    str(item.get("path", "")),
                ]
                for item in mappings
            ]
            lines.append("")
            lines.append(self._render_table(["STATUS", "HASH", "PATH"], rows))
        return "\n".join(lines)

    def _format_install_result(self, data: dict[str, Any], metadata: dict[str, Any]) -> str:
        """Format install result rows."""
        actions = data.get("installed", [])
        if not actions:
            return str(metadata.get("message") or "No install actions.")

        heading = str(metadata.get("message") or "Install")
        rows = [
            [
                str(item.get("component", "")),
                str(item.get("agent", "")),
                str(item.get("status", "")),
                str(item.get("path", "")),
            ]
            for item in actions
        ]
        return "\n".join(
            [heading, "", self._render_table(["COMPONENT", "AGENT", "STATUS", "PATH"], rows)]
        )

    def _render_table(self, headers: list[str], rows: list[list[str]]) -> str:
        """Render headers and rows as ASCII table."""
        if not rows:
            return ""

        # Calculate column widths
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(cell)))

        # Apply width limit
        if self.width:
            total_width = sum(widths) + len(widths) * 2  # 2 spaces between columns
            if total_width > self.width:
                # Shrink wider columns proportionally
                excess = total_width - self.width
                shrinkable = [i for i, w in enumerate(widths) if w > 15]
                if shrinkable:
                    per_col = excess // len(shrinkable)
                    for i in shrinkable:
                        widths[i] = max(10, widths[i] - per_col)

        # Format header
        header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
        lines = [header_line]

        # Format rows
        for row in rows:
            row_cells = []
            for i, cell in enumerate(row):
                cell_str = str(cell)
                if i < len(widths):
                    if len(cell_str) > widths[i]:
                        cell_str = cell_str[: widths[i] - 3] + "..."
                    row_cells.append(cell_str.ljust(widths[i]))
                else:
                    row_cells.append(cell_str)
            lines.append("  ".join(row_cells))

        return "\n".join(lines)


class JsonFormatter(DataFormatter):
    """Format data as JSON."""

    def __init__(self, indent: int = 2):
        """Initialize with indentation level."""
        self.indent = indent

    def format(self, data: Any, data_type: str, metadata: dict[str, Any]) -> str:
        """Format data as JSON.

        Returns plain array for list data types to match legacy behavior.
        """
        # Return plain array for list-type data (legacy compatibility)
        output = self._serialize(data)
        return json.dumps(output, indent=self.indent, default=str)

    def _serialize(self, obj: Any) -> Any:
        """Convert objects to JSON-serializable form."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Path):
            return str(obj)
        elif isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._serialize(item) for item in obj]
        else:
            return obj


class TsvFormatter(DataFormatter):
    """Format data as tab-separated values."""

    def __init__(self):
        """Initialize with dispatch dictionary."""
        self._formatters = {
            "session_list": self._format_session_list,
            "workspace_list": self._format_workspace_list,
            "home_list": self._format_home_list,
            "project_list": self._format_project_list,
            "stats": self._format_stats,
            "stats_rollup": self._format_stats_rollup,
            "gemini_index": self._format_gemini_index,
            "install_result": self._format_install_result,
        }

    def format(self, data: Any, data_type: str, metadata: dict[str, Any]) -> str:
        """Format data as TSV."""
        formatter = self._formatters.get(data_type)
        if formatter:
            if data_type in ("project_list", "home_list", "stats", "stats_rollup"):
                return formatter(data, metadata)
            return formatter(data)
        # Fallback to JSON for complex types
        return json.dumps(data, default=str)

    def _format_session_list(self, sessions: list[SessionDict]) -> str:
        """Format session list as TSV."""
        if not sessions:
            return ""

        headers = ["AGENT", "HOME", "WORKSPACE", "FILE", "MESSAGES", "MODIFIED"]
        lines = ["\t".join(headers)]
        rows = _build_session_rows(
            sessions,
            workspace_formatter=lambda ws: ws,
            modified_formatter=_format_modified_iso,
        )
        for row in rows:
            lines.append("\t".join(row))

        return "\n".join(lines)

    def _format_workspace_list(self, workspaces: list[WorkspaceDict]) -> str:
        """Format workspace list as TSV."""
        if not workspaces:
            return ""

        headers = ["HOME", "WORKSPACE", "SESSIONS", "STATUS", "MODIFIED"]
        lines = ["\t".join(headers)]
        rows = _build_workspace_rows(
            workspaces,
            workspace_formatter=lambda ws: ws,
            modified_formatter=_format_modified_iso,
        )
        for row in rows:
            lines.append("\t".join(row))

        return "\n".join(lines)

    def _format_home_list(
        self, homes: list[HomeDict], metadata: dict[str, Any] | None = None
    ) -> str:
        """Format home list as TSV."""
        show_counts = True if metadata is None else metadata.get("show_counts", True)
        headers = ["HOME", "TYPE", "STATUS"]
        if show_counts:
            headers.append("SESSIONS")
        lines = ["\t".join(headers)]

        for h in homes:
            row = [
                h.get("home", h.get("name", "")),
                h.get("type", ""),
                h.get("status", ""),
            ]
            if show_counts:
                row.append(str(h.get("session_count", "")))
            lines.append("\t".join(row))

        return "\n".join(lines)

    def _format_project_list(
        self, projects: list[ProjectDict], metadata: dict[str, Any] | None = None
    ) -> str:
        """Format project list as TSV."""
        show_counts = True if metadata is None else metadata.get("show_counts", True)
        headers = ["PROJECT", "SOURCE", "WORKSPACE"]
        if show_counts:
            headers.append("SESSIONS")
        lines = ["\t".join(headers)]
        workspace_display_map = (metadata or {}).get("workspace_display_map", {})

        for p in projects:
            # Handle both legacy (source/workspace as lists) and new (workspace_count) formats
            sources = p.get("source", p.get("homes", []))
            workspaces = p.get("workspace", [])

            source_str = _format_project_sources(sources)
            workspace_str = _format_project_workspaces(
                workspaces, workspace_display_map, p.get("workspace_count")
            )

            row = [
                p.get("project", p.get("name", "")),
                source_str,
                workspace_str,
            ]
            if show_counts:
                row.append(str(p.get("session_count", "")))
            lines.append("\t".join(row))

        return "\n".join(lines)

    def _format_stats(self, stats: StatsDict, metadata: dict[str, Any] | None = None) -> str:
        """Format stats as machine-readable TSV records."""
        metadata = metadata or {}
        workspace_display_map = (
            metadata.get("workspace_display_map") or stats.get("workspace_display_map") or {}
        )
        headers = ["SECTION", "NAME", "SESSIONS", "MESSAGES", "VALUE", "EXTRA"]
        lines = ["\t".join(headers)]

        lines.append(
            "\t".join(
                [
                    "summary",
                    "total",
                    str(stats.get("total_sessions", stats.get("sessions", 0))),
                    str(stats.get("total_messages", stats.get("messages", 0))),
                    "",
                    "",
                ]
            )
        )

        tokens = stats.get("tokens", {})
        if isinstance(tokens, dict):
            for key in ("input", "output", "cache_read", "cache_creation"):
                lines.append("\t".join(["token", key, "", "", str(tokens.get(key, 0)), ""]))

        for section, values, count_key in (
            ("agent", stats.get("by_agent", {}), "sessions"),
            ("home", stats.get("by_home", {}), "sessions"),
            ("workspace", stats.get("by_workspace", {}), "sessions"),
            ("model", stats.get("by_model", {}), "messages"),
            ("tool", stats.get("by_tool", {}), "uses"),
            ("day", stats.get("by_day", {}), "sessions"),
        ):
            if not isinstance(values, dict):
                continue
            section_items = list(values.items())
            if section == "workspace" and isinstance(metadata.get("top_ws"), int):
                section_items = section_items[: metadata["top_ws"]]
            for name, value in section_items:
                display_name = str(name)
                if section == "workspace":
                    display_name = _workspace_display(
                        {"workspace": str(name)}, display_map=workspace_display_map
                    )
                sessions = ""
                messages = ""
                metric = ""
                extra = ""
                if isinstance(value, dict):
                    sessions = str(value.get("sessions", "")) if "sessions" in value else ""
                    messages = str(value.get("messages", "")) if "messages" in value else ""
                    metric = str(_stats_count(value, count_key))
                    if section == "tool":
                        extra = f"errors={value.get('errors', 0)}"
                    elif section == "model":
                        extra = f"tokens={value.get('tokens', 0)}"
                else:
                    metric = str(value)
                lines.append("\t".join([section, display_name, sessions, messages, metric, extra]))

        time_stats = stats.get("time_stats", {})
        if isinstance(time_stats, dict) and time_stats:
            for key in (
                "total_duration_seconds",
                "average_duration_seconds",
                "sessions_with_time",
            ):
                lines.append("\t".join(["time", key, "", "", str(time_stats.get(key, 0)), ""]))
            by_day = time_stats.get("by_day", {})
            if isinstance(by_day, dict):
                for day, seconds in by_day.items():
                    lines.append("\t".join(["time_day", str(day), "", "", str(seconds), ""]))
        return "\n".join(lines)

    def _format_stats_rollup(
        self, rows: list[dict[str, Any]], metadata: dict[str, Any] | None = None
    ) -> str:
        """Format stats rollup rows as TSV."""
        metadata = metadata or {}
        headers = _rollup_columns(metadata)
        lines = ["\t".join(headers)]
        for row in rows:
            lines.append("\t".join(_rollup_row_values(row, metadata)))
        return "\n".join(lines)

    def _format_gemini_index(self, data: dict[str, Any]) -> str:
        """Format Gemini hash index results as TSV."""
        mappings = data.get("mappings", [])
        if not mappings:
            return ""
        if data.get("action") == "list":
            lines = ["HASH\tPATH"]
            lines.extend(f"{item.get('hash', '')}\t{item.get('path', '')}" for item in mappings)
            return "\n".join(lines)

        lines = ["STATUS\tHASH\tPATH"]
        lines.extend(
            f"{item.get('status', '')}\t{item.get('hash', '')}\t{item.get('path', '')}"
            for item in mappings
        )
        return "\n".join(lines)

    def _format_install_result(self, data: dict[str, Any]) -> str:
        """Format install result as TSV."""
        actions = data.get("installed", [])
        if not actions:
            return ""
        lines = ["COMPONENT\tAGENT\tSTATUS\tPATH"]
        lines.extend(
            "\t".join(
                [
                    str(item.get("component", "")),
                    str(item.get("agent", "")),
                    str(item.get("status", "")),
                    str(item.get("path", "")),
                ]
            )
            for item in actions
        )
        return "\n".join(lines)


class OutputFormatter:
    """Format command results for output.

    This class coordinates output formatting based on user preferences,
    delegating to specific formatters (table, JSON, TSV) and handling
    output destination (stdout vs file).

    Example:
        formatter = OutputFormatter()
        formatter.format(result, output_args)
    """

    def __init__(self):
        """Initialize with available formatters."""
        self.formatters: dict[str, DataFormatter] = {
            "table": TableFormatter(),
            "json": JsonFormatter(),
            "tsv": TsvFormatter(),
        }

    def format(self, result: CommandResult, output_args: OutputArgs) -> None:
        """Format and output command result.

        Args:
            result: Command execution result.
            output_args: Output formatting options.
        """
        format_name = self._resolve_format(output_args)
        formatter = self.formatters.get(format_name)
        if not formatter:
            raise FormatterError(f"Unknown format: {format_name}")

        self._configure_table_width(format_name, formatter, output_args)
        if self._handle_empty_result(result):
            return

        output = formatter.format(result.data, result.data_type, result.metadata)
        self._write_output(output, output_args)
        self._write_warnings(result)

    def _resolve_format(self, output_args: OutputArgs) -> str:
        """Return explicit output format or TTY-aware default."""
        if output_args.format is not None:
            return output_args.format
        return "table" if sys.stdout.isatty() else "tsv"

    def _configure_table_width(
        self, format_name: str, formatter: DataFormatter, output_args: OutputArgs
    ) -> None:
        if format_name != "table" or not isinstance(formatter, TableFormatter):
            return
        width = getattr(output_args, "width", None)
        if width is None:
            return
        formatter.width = width if width > 0 else None

    def _handle_empty_result(self, result: CommandResult) -> bool:
        is_empty = (isinstance(result.data, list) and len(result.data) == 0) or (
            result.data is None
        )
        if not is_empty:
            return False
        self._write_errors_and_warnings(result)
        if not (result.errors or result.warnings):
            self._write_empty_message(result.data_type)
        return True

    def _write_errors_and_warnings(self, result: CommandResult) -> None:
        for error in result.errors:
            sys.stderr.write(f"Error: {error}\n")
        self._write_warnings(result)

    def _write_empty_message(self, data_type: str) -> None:
        messages = {
            "session_list": "No sessions found",
            "workspace_list": "No workspaces found",
            "home_list": "No homes found",
            "project_list": "No projects found",
        }
        if message := messages.get(data_type):
            sys.stderr.write(f"{message}\n")

    def _write_output(self, output: str, output_args: OutputArgs) -> None:
        if output_args.output_path:
            output_args.output_path.parent.mkdir(parents=True, exist_ok=True)
            output_args.output_path.write_text(output + "\n")
        else:
            print(output)

    def _write_warnings(self, result: CommandResult) -> None:
        for warning in result.warnings:
            sys.stderr.write(f"Warning: {warning}\n")

        # Write errors to stderr (for partial results)
        for error in result.errors:
            sys.stderr.write(f"Error: {error}\n")

    def get_formatter(self, format_name: str) -> DataFormatter | None:
        """Get a specific formatter by name.

        Args:
            format_name: Name of the formatter ("table", "json", "tsv").

        Returns:
            The formatter instance, or None if not found.
        """
        return self.formatters.get(format_name)

    def register_formatter(self, name: str, formatter: DataFormatter) -> None:
        """Register a custom formatter.

        Args:
            name: Name to register the formatter under.
            formatter: The formatter instance.
        """
        self.formatters[name] = formatter
