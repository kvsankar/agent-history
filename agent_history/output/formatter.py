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
from typing import Any, Dict, List, Optional

from agent_history.handlers.base import CommandResult
from agent_history.scope.context import OutputArgs


class FormatterError(Exception):
    """Error formatting command output."""

    pass


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

    def format(self, data: Any, data_type: str, metadata: Dict[str, Any]) -> str:
        """Format data as ASCII table."""
        if data_type == "session_list":
            return self._format_session_list(data)
        elif data_type == "workspace_list":
            return self._format_workspace_list(data)
        elif data_type == "home_list":
            return self._format_home_list(data)
        elif data_type == "stats":
            return self._format_stats(data, metadata)
        elif data_type == "project_list":
            return self._format_project_list(data)
        elif data_type == "project_details":
            return self._format_project_details(data, metadata)
        elif data_type == "exported_files":
            return self._format_exported_files(data, metadata)
        else:
            return str(data)

    def _format_session_list(self, sessions: List[Dict]) -> str:
        """Format session list as table."""
        if not sessions:
            return "No sessions found."

        headers = ["AGENT", "HOME", "WORKSPACE", "FILE", "MESSAGES", "DATE"]
        rows = []

        for s in sessions:
            workspace = s.get("workspace_readable") or s.get("workspace", "")
            # Truncate long workspace paths
            if len(workspace) > 40 and self.width:
                workspace = "..." + workspace[-37:]

            modified = s.get("modified")
            if isinstance(modified, datetime):
                date_str = modified.strftime("%Y-%m-%d")
            elif isinstance(modified, str):
                date_str = modified[:10] if len(modified) >= 10 else modified
            else:
                date_str = ""

            rows.append(
                [
                    s.get("agent", ""),
                    s.get("home", "local"),
                    workspace,
                    s.get("filename", ""),
                    str(s.get("message_count", "")),
                    date_str,
                ]
            )

        return self._render_table(headers, rows)

    def _format_workspace_list(self, workspaces: List[Dict]) -> str:
        """Format workspace list as table."""
        if not workspaces:
            return "No workspaces found."

        headers = ["HOME", "WORKSPACE", "SESSIONS", "STATUS", "LAST_MODIFIED"]
        rows = []

        for ws in workspaces:
            workspace = ws.get("workspace") or ""
            if len(workspace) > 50 and self.width:
                workspace = "..." + workspace[-47:]

            modified = ws.get("modified") or ws.get("last_modified")
            if isinstance(modified, datetime):
                date_str = modified.strftime("%Y-%m-%d %H:%M")
            elif isinstance(modified, str):
                date_str = modified[:16] if len(modified) >= 16 else modified
            else:
                date_str = ""

            # Status should be pre-computed by the handler
            status = ws.get("status", "unknown")

            rows.append(
                [
                    ws.get("home", "local"),
                    workspace,
                    str(ws.get("session_count", "")),
                    status,
                    date_str,
                ]
            )

        return self._render_table(headers, rows)

    def _format_home_list(self, homes: List[Dict]) -> str:
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

    def _format_stats(self, stats: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        """Format statistics as table."""
        lines = []

        # Summary line
        total_sessions = stats.get("total_sessions", 0)
        total_messages = stats.get("total_messages", 0)
        lines.append(f"Sessions: {total_sessions}  Messages: {total_messages}")
        lines.append("")

        # By agent
        by_agent = stats.get("by_agent", {})
        if by_agent:
            lines.append("By Agent:")
            for agent, count in sorted(by_agent.items()):
                lines.append(f"  {agent}: {count}")
            lines.append("")

        # By home
        by_home = stats.get("by_home", {})
        if by_home:
            lines.append("By Home:")
            for home, count in sorted(by_home.items()):
                lines.append(f"  {home}: {count}")
            lines.append("")

        # By workspace (limited)
        by_workspace = stats.get("by_workspace", {})
        if by_workspace:
            lines.append("By Workspace:")
            sorted_ws = sorted(by_workspace.items(), key=lambda x: -x[1])
            for ws, count in sorted_ws[:10]:  # Top 10
                ws_display = ws
                if len(ws_display) > 50:
                    ws_display = "..." + ws_display[-47:]
                lines.append(f"  {ws_display}: {count}")
            if len(by_workspace) > 10:
                lines.append(f"  ... and {len(by_workspace) - 10} more")

        return "\n".join(lines)

    def _format_project_list(self, projects: List[Dict]) -> str:
        """Format project list as table."""
        if not projects:
            return "No projects configured."

        headers = ["PROJECT", "SOURCE", "WORKSPACE", "SESSIONS"]
        rows = []

        for p in projects:
            # Handle both legacy (source/workspace as lists) and new (workspace_count) formats
            sources = p.get("source", p.get("homes", []))
            workspaces = p.get("workspace", [])

            # For display, join multiple values or show count
            if isinstance(sources, list):
                source_str = ", ".join(sources) if len(sources) <= 3 else f"{len(sources)} sources"
            else:
                source_str = str(sources)

            if isinstance(workspaces, list):
                workspace_str = (
                    ", ".join(workspaces)
                    if len(workspaces) <= 2
                    else f"{len(workspaces)} workspaces"
                )
            else:
                workspace_str = str(p.get("workspace_count", workspaces))

            rows.append(
                [
                    p.get("project", p.get("name", "")),
                    source_str,
                    workspace_str,
                    str(p.get("session_count", "")),
                ]
            )

        return self._render_table(headers, rows)

    def _format_project_details(self, data: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        """Format project details."""
        lines = []
        project_name = data.get("project", "")
        lines.append(f"Project: {project_name}")
        lines.append(f"Total Sessions: {data.get('total_sessions', 0)}")
        lines.append("")

        workspaces_by_home = data.get("workspaces_by_home", {})
        for home, workspaces in workspaces_by_home.items():
            lines.append(f"  {home}:")
            for ws in workspaces:
                ws_path = ws.get("workspace", "")
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

    def format(self, data: Any, data_type: str, metadata: Dict[str, Any]) -> str:
        """Format data as TSV."""
        if data_type == "session_list":
            return self._format_session_list(data)
        elif data_type == "workspace_list":
            return self._format_workspace_list(data)
        elif data_type == "home_list":
            return self._format_home_list(data)
        elif data_type == "project_list":
            return self._format_project_list(data)
        else:
            # Fallback to JSON for complex types
            return json.dumps(data, default=str)

    def _format_session_list(self, sessions: List[Dict]) -> str:
        """Format session list as TSV."""
        if not sessions:
            return ""

        headers = ["AGENT", "HOME", "WORKSPACE", "FILE", "MESSAGES", "MODIFIED"]
        lines = ["\t".join(headers)]

        for s in sessions:
            modified = s.get("modified")
            if isinstance(modified, datetime):
                modified_str = modified.isoformat()
            else:
                modified_str = str(modified) if modified else ""

            row = [
                s.get("agent", ""),
                s.get("home", "local"),
                s.get("workspace_readable") or s.get("workspace", ""),
                s.get("filename", ""),
                str(s.get("message_count", "")),
                modified_str,
            ]
            lines.append("\t".join(row))

        return "\n".join(lines)

    def _format_workspace_list(self, workspaces: List[Dict]) -> str:
        """Format workspace list as TSV."""
        if not workspaces:
            return ""

        headers = ["HOME", "WORKSPACE", "SESSIONS", "STATUS", "LAST_MODIFIED"]
        lines = ["\t".join(headers)]

        for ws in workspaces:
            modified = ws.get("modified") or ws.get("last_modified")
            if isinstance(modified, datetime):
                modified_str = modified.isoformat()
            else:
                modified_str = str(modified) if modified else ""

            # Status should be pre-computed by the handler
            status = ws.get("status", "unknown")

            row = [
                ws.get("home", "local"),
                ws.get("workspace", ""),
                str(ws.get("session_count", "")),
                status,
                modified_str,
            ]
            lines.append("\t".join(row))

        return "\n".join(lines)

    def _format_home_list(self, homes: List[Dict]) -> str:
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

    def _format_project_list(self, projects: List[Dict]) -> str:
        """Format project list as TSV."""
        headers = ["PROJECT", "SOURCE", "WORKSPACE", "SESSIONS"]
        lines = ["\t".join(headers)]

        for p in projects:
            # Handle both legacy (source/workspace as lists) and new (workspace_count) formats
            sources = p.get("source", p.get("homes", []))
            workspaces = p.get("workspace", [])

            # For display, join multiple values or show count
            if isinstance(sources, list):
                source_str = ", ".join(sources) if len(sources) <= 3 else f"{len(sources)} sources"
            else:
                source_str = str(sources)

            if isinstance(workspaces, list):
                workspace_str = (
                    ", ".join(workspaces)
                    if len(workspaces) <= 2
                    else f"{len(workspaces)} workspaces"
                )
            else:
                workspace_str = str(p.get("workspace_count", workspaces))

            row = [
                p.get("project", p.get("name", "")),
                source_str,
                workspace_str,
                str(p.get("session_count", "")),
            ]
            lines.append("\t".join(row))

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
