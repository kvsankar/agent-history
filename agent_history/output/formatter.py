"""Output formatters for agent-history command results.

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
from typing import Any, Callable, Dict, List, Optional

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


def _workspace_display(
    item: Dict[str, Any], display_map: Optional[Dict[str, str]] = None
) -> str:
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
    sessions: List[SessionDict],
    *,
    workspace_formatter: Callable[[str], str],
    modified_formatter: Callable[[Any], str],
) -> List[List[str]]:
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
    workspaces: List[WorkspaceDict],
    *,
    workspace_formatter: Callable[[str], str],
    modified_formatter: Callable[[Any], str],
) -> List[List[str]]:
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
    workspaces: Any, display_map: Dict[str, str], workspace_count: Any
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


class DataFormatter(ABC):
    """Abstract base class for data formatters.

    Subclasses implement format() to render command data in a specific format.
    """

    @abstractmethod
    def format(self, data: Any, data_type: str, metadata: Dict[str, Any]) -> str:
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

    def __init__(self, width: Optional[int] = 120):
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
            "project_list": self._format_project_list,
            "project_details": self._format_project_details,
            "exported_files": self._format_exported_files,
        }

    def format(self, data: Any, data_type: str, metadata: Dict[str, Any]) -> str:
        """Format data as ASCII table."""
        formatter = self._formatters.get(data_type)
        if formatter:
            # Some formatters need metadata, some don't
            if data_type in (
                "stats",
                "project_details",
                "exported_files",
                "project_list",
                "home_list",
            ):
                return formatter(data, metadata)
            return formatter(data)
        return str(data)

    def _format_session_list(self, sessions: List[SessionDict]) -> str:
        """Format session list as table."""
        if not sessions:
            return "No sessions found."

        headers = ["AGENT", "HOME", "WORKSPACE", "FILE", "MESSAGES", "DATE"]
        rows = _build_session_rows(
            sessions,
            workspace_formatter=lambda ws: _truncate_tail(ws, 40) if self.width else ws,
            modified_formatter=lambda value: _format_modified_date(
                value, date_format="%Y-%m-%d", truncate=10
            ),
        )

        return self._render_table(headers, rows)

    def _format_workspace_list(self, workspaces: List[WorkspaceDict]) -> str:
        """Format workspace list as table."""
        if not workspaces:
            return "No workspaces found."

        headers = ["HOME", "WORKSPACE", "SESSIONS", "STATUS", "LAST_MODIFIED"]
        rows = _build_workspace_rows(
            workspaces,
            workspace_formatter=lambda ws: _truncate_tail(ws, 50) if self.width else ws,
            modified_formatter=lambda value: _format_modified_date(
                value, date_format="%Y-%m-%d %H:%M", truncate=16
            ),
        )

        return self._render_table(headers, rows)

    def _format_home_list(
        self, homes: List[HomeDict], metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format home list as table."""
        if not homes:
            return "No homes configured."

        headers = ["HOME", "TYPE", "STATUS", "SESSIONS"]
        rows = []

        for h in homes:
            rows.append(
                [
                    h.get("home", h.get("name", "")),
                    h.get("type", ""),
                    h.get("status", ""),
                    str(h.get("session_count", "")),
                ]
            )

        return self._render_table(headers, rows)

    def _format_stats(self, stats: StatsDict, metadata: Dict[str, Any]) -> str:
        """Format statistics as table."""
        lines = []
        workspace_display_map = (
            metadata.get("workspace_display_map") or stats.get("workspace_display_map") or {}
        )

        # Summary line
        total_sessions = stats.get("total_sessions", stats.get("sessions", 0))
        total_messages = stats.get("total_messages", stats.get("messages", 0))
        lines.append(f"Sessions: {total_sessions}  Messages: {total_messages}")
        lines.append("")

        group_by = metadata.get("group_by") or []
        if isinstance(group_by, str):
            group_list = [group_by]
        else:
            group_list = list(group_by)
        if not group_list:
            group_list = ["agent", "home", "workspace"]

        def get_count(value: Any, key: str) -> Any:
            if isinstance(value, dict):
                if key in value:
                    return value[key]
                if "sessions" in value:
                    return value["sessions"]
                if "uses" in value:
                    return value["uses"]
                if "messages" in value:
                    return value["messages"]
            return value

        if "agent" in group_list:
            by_agent = stats.get("by_agent", {})
            if by_agent:
                lines.append("By Agent:")
                for agent, value in sorted(by_agent.items()):
                    lines.append(f"  {agent}: {get_count(value, 'sessions')}")
                lines.append("")

        if "home" in group_list:
            by_home = stats.get("by_home", {})
            if by_home:
                lines.append("By Home:")
                for home, value in sorted(by_home.items()):
                    lines.append(f"  {home}: {get_count(value, 'sessions')}")
                lines.append("")

        if "workspace" in group_list:
            by_workspace = stats.get("by_workspace", {})
            if by_workspace:
                lines.append("By Workspace:")
                sorted_ws = sorted(
                    by_workspace.items(), key=lambda x: -get_count(x[1], "sessions")
                )
                for ws, value in sorted_ws[:10]:
                    ws_display = _workspace_display(
                        {"workspace": ws}, display_map=workspace_display_map
                    )
                    if len(ws_display) > 50:
                        ws_display = "..." + ws_display[-47:]
                    lines.append(f"  {ws_display}: {get_count(value, 'sessions')}")
                if len(by_workspace) > 10:
                    lines.append(f"  ... and {len(by_workspace) - 10} more")
                lines.append("")

        if "model" in group_list:
            by_model = stats.get("by_model", {})
            if by_model:
                lines.append("By Model:")
                for model, value in sorted(by_model.items()):
                    if isinstance(value, dict):
                        lines.append(
                            f"  {model}: {value.get('messages', 0)} messages"
                            f", {value.get('tokens', 0)} tokens"
                        )
                    else:
                        lines.append(f"  {model}: {value}")
                lines.append("")

        if "tool" in group_list:
            by_tool = stats.get("by_tool", {})
            if by_tool:
                lines.append("By Tool:")
                for tool, value in sorted(by_tool.items()):
                    if isinstance(value, dict):
                        lines.append(
                            f"  {tool}: {value.get('uses', 0)} uses"
                            f", {value.get('errors', 0)} errors"
                        )
                    else:
                        lines.append(f"  {tool}: {value}")
                lines.append("")

        if "day" in group_list:
            by_day = stats.get("by_day", {})
            if by_day:
                lines.append("By Day:")
                for day, value in sorted(by_day.items()):
                    lines.append(f"  {day}: {get_count(value, 'sessions')}")
                lines.append("")

        return "\n".join(lines)

    def _format_project_list(
        self, projects: List[ProjectDict], metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format project list as table."""
        if not projects:
            return "No projects configured."

        workspace_display_map = (metadata or {}).get("workspace_display_map", {})
        headers = ["PROJECT", "SOURCE", "WORKSPACE", "SESSIONS"]
        rows = []

        for p in projects:
            # Handle both legacy (source/workspace as lists) and new (workspace_count) formats
            sources = p.get("source", p.get("homes", []))
            workspaces = p.get("workspace", [])

            source_str = _format_project_sources(sources)
            workspace_str = _format_project_workspaces(
                workspaces, workspace_display_map, p.get("workspace_count")
            )

            rows.append(
                [
                    p.get("project", p.get("name", "")),
                    source_str,
                    workspace_str,
                    str(p.get("session_count", "")),
                ]
            )

        return self._render_table(headers, rows)

    def _format_project_details(self, data: ProjectDict, metadata: Dict[str, Any]) -> str:
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

    def _format_exported_files(self, files: List[Path], metadata: Dict[str, Any]) -> str:
        """Format list of exported files."""
        count = metadata.get("count", len(files))
        lines = [f"Exported {count} file(s):"]
        for f in files:
            lines.append(f"  {f}")
        return "\n".join(lines)

    def _render_table(self, headers: List[str], rows: List[List[str]]) -> str:
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

    def format(self, data: Any, data_type: str, metadata: Dict[str, Any]) -> str:
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
        }

    def format(self, data: Any, data_type: str, metadata: Dict[str, Any]) -> str:
        """Format data as TSV."""
        formatter = self._formatters.get(data_type)
        if formatter:
            if data_type in ("project_list", "home_list"):
                return formatter(data, metadata)
            return formatter(data)
        # Fallback to JSON for complex types
        return json.dumps(data, default=str)

    def _format_session_list(self, sessions: List[SessionDict]) -> str:
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

    def _format_workspace_list(self, workspaces: List[WorkspaceDict]) -> str:
        """Format workspace list as TSV."""
        if not workspaces:
            return ""

        headers = ["HOME", "WORKSPACE", "SESSIONS", "STATUS", "LAST_MODIFIED"]
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
        self, homes: List[HomeDict], metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format home list as TSV."""
        headers = ["HOME", "TYPE", "STATUS", "SESSIONS"]
        lines = ["\t".join(headers)]

        for h in homes:
            row = [
                h.get("home", h.get("name", "")),
                h.get("type", ""),
                h.get("status", ""),
                str(h.get("session_count", "")),
            ]
            lines.append("\t".join(row))

        return "\n".join(lines)

    def _format_project_list(
        self, projects: List[ProjectDict], metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format project list as TSV."""
        headers = ["PROJECT", "SOURCE", "WORKSPACE", "SESSIONS"]
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
                str(p.get("session_count", "")),
            ]
            lines.append("\t".join(row))

        return "\n".join(lines)

    def _format_stats(self, stats: StatsDict) -> str:
        """Format stats workspace breakdown as TSV."""
        rows = stats.get("workspace_rows", [])
        if not rows:
            return ""
        headers = ["HOME", "WORKSPACE", "SESSIONS", "MESSAGES"]
        lines = ["\t".join(headers)]
        for row in rows:
            lines.append(
                "\t".join(
                    [
                        str(row.get("home", "")),
                        _workspace_display(row),
                        str(row.get("sessions", 0)),
                        str(row.get("messages", 0)),
                    ]
                )
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
        self.formatters: Dict[str, DataFormatter] = {
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
        # Determine format
        format_name = output_args.format
        if format_name is None:
            # Default: table for TTY, tsv for pipes
            format_name = "table" if sys.stdout.isatty() else "tsv"

        # Get formatter
        formatter = self.formatters.get(format_name)
        if not formatter:
            raise FormatterError(f"Unknown format: {format_name}")

        # Update table width if specified
        if (
            format_name == "table"
            and hasattr(output_args, "width")
            and output_args.width is not None
        ):
            if isinstance(formatter, TableFormatter):
                formatter.width = output_args.width if output_args.width > 0 else None

        # Check for empty data and write appropriate message to stderr
        is_empty = (isinstance(result.data, list) and len(result.data) == 0) or (
            result.data is None
        )
        if is_empty:
            # Write "no data" message to stderr based on data type
            if result.data_type == "session_list":
                sys.stderr.write("No sessions found\n")
            elif result.data_type == "workspace_list":
                sys.stderr.write("No workspaces found\n")
            elif result.data_type == "home_list":
                sys.stderr.write("No homes found\n")
            elif result.data_type == "project_list":
                sys.stderr.write("No projects found\n")
            # Don't print anything to stdout for empty results
            return

        # Format data
        output = formatter.format(result.data, result.data_type, result.metadata)

        # Write output
        if output_args.output_path:
            output_args.output_path.parent.mkdir(parents=True, exist_ok=True)
            output_args.output_path.write_text(output + "\n")
        else:
            print(output)

        # Write warnings to stderr
        for warning in result.warnings:
            sys.stderr.write(f"Warning: {warning}\n")

        # Write errors to stderr (for partial results)
        for error in result.errors:
            sys.stderr.write(f"Error: {error}\n")

    def get_formatter(self, format_name: str) -> Optional[DataFormatter]:
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
