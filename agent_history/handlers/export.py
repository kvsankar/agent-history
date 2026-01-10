"""Session export handler for the resolution pipeline.

This module provides the SessionExportHandler class that handles 'session export'
commands using the new resolution pipeline architecture. It exports sessions
to markdown files, supporting options like minimal output, split files, and
flat directory structure.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent_history.backends.claude import read_jsonl_messages
from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope
from agent_history.utils.paths import normalize_workspace_name
from agent_history.utils.platform import AGENT_CLAUDE, AGENT_CODEX, AGENT_GEMINI

# =============================================================================
# Constants
# =============================================================================

# Conversation splitting constants
SPLIT_MIN_FACTOR = 0.8  # Minimum lines before considering split (80% of target)
SPLIT_MAX_FACTOR = 1.3  # Maximum lines before forcing split (130% of target)
HEADER_LINES_ESTIMATE = 30  # Approximate header size in lines
METADATA_LINES_ESTIMATE = 20  # Approximate metadata section size in lines
MIN_MESSAGES_FOR_SPLIT = 2  # Minimum messages to consider splitting
MIN_SPLIT_POINTS = 2  # Minimum split points (start + end)

# Split point scoring weights
SCORE_USER_MESSAGE_NEXT = 100  # Next message is User (best - starting new topic)
SCORE_TOOL_RESULT = 50  # Current message is tool result (action complete)
SCORE_TIME_GAP_LARGE = 30  # Time gap > 5 minutes
SCORE_TIME_GAP_MEDIUM = 10  # Time gap > 1 minute
SCORE_DISTANCE_PENALTY = 0.05  # Penalty per line away from target

# Time gap thresholds (in seconds)
TIME_GAP_LARGE = 300  # 5 minutes
TIME_GAP_MEDIUM = 60  # 1 minute

# Markdown markers for tool content
TOOL_RESULT_MARKER = "**[Tool Result:"


# =============================================================================
# Export Result Type
# =============================================================================

EXPORT_EXPORTED = "exported"
EXPORT_SKIPPED = "skipped"
EXPORT_FAILED = "failed"


# =============================================================================
# Session Export Handler
# =============================================================================


class SessionExportHandler(VerbHandler):
    """Handle 'session export' command.

    This handler exports sessions from a resolved ConcreteScope to markdown
    files. It supports various output options including minimal mode (no metadata),
    file splitting for long conversations, and flat vs organized directory
    structures.

    The handler iterates through all records in the scope, exporting each
    session to a markdown file. Sessions can be organized by workspace
    (default) or placed in a flat directory structure.
    """

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """Export sessions to markdown.

        Args:
            scope: Resolved scope with sessions to export.
            verb_args: Export options:
                - output_dir: Path for output (default: ./ai-chats)
                - minimal: bool - omit metadata in output
                - split: int - split at N lines (None to disable)
                - flat: bool - no workspace subdirs (default: False)
                - force: bool - overwrite existing files (default: False)
            output_args: Output formatting options.

        Returns:
            CommandResult with export statistics:
                - data['exported']: count of exported sessions
                - data['skipped']: count of skipped (up-to-date) sessions
                - data['failed']: count of failed sessions
        """
        output_dir = verb_args.get("output_dir", Path.cwd() / "ai-chats")
        if isinstance(output_dir, str):
            output_dir = Path(output_dir)

        minimal = verb_args.get("minimal", False)
        split_lines = verb_args.get("split")
        flat = verb_args.get("flat", False)
        force = verb_args.get("force", False)
        include_source = verb_args.get("include_source", False)
        export_json = verb_args.get("export_json", False)
        quiet = output_args.quiet

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Track export statistics
        exported: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        failed: List[Tuple[Dict[str, Any], str]] = []

        # Track sources for index manifest generation
        sources_info: Dict[str, int] = {}  # home -> session count

        # Process each record in scope
        for record in scope:
            for session in record.sessions:
                try:
                    result = self._export_session(
                        session=session,
                        home=record.home,
                        workspace=record.workspace,
                        output_dir=output_dir,
                        minimal=minimal,
                        split_lines=split_lines,
                        flat=flat,
                        force=force,
                        include_source=include_source,
                        export_json=export_json,
                        quiet=quiet,
                    )
                    if result == EXPORT_EXPORTED:
                        exported.append(session)
                        # Track by home for index manifest
                        sources_info[record.home] = sources_info.get(record.home, 0) + 1
                    elif result == EXPORT_SKIPPED:
                        skipped.append(session)
                        # Also track skipped for index (they still exist in output)
                        sources_info[record.home] = sources_info.get(record.home, 0) + 1
                except Exception as e:
                    failed.append((session, str(e)))
                    if not quiet:
                        filename = session.get("filename", session.get("file", "unknown"))
                        sys.stderr.write(f"Error exporting {filename}: {e}\n")

        # Collect unique homes and workspaces
        unique_homes = set(r.home for r in scope)
        unique_workspaces = set(r.workspace for r in scope)

        # Generate index manifest if multi-home or multi-workspace export
        if len(unique_homes) > 1 or len(unique_workspaces) > 1:
            self._generate_index_manifest(output_dir, sources_info, quiet)

        return CommandResult(
            success=len(failed) == 0,
            data={
                "exported": len(exported),
                "skipped": len(skipped),
                "failed": len(failed),
                "output_dir": str(output_dir),
            },
            data_type="export_result",
            metadata={
                "homes": list(unique_homes),
                "workspaces": list(unique_workspaces),
            },
            errors=[f"{s.get('filename', s.get('file', 'unknown'))}: {e}" for s, e in failed],
        )

    def _export_session(
        self,
        session: Dict[str, Any],
        home: str,
        workspace: str,
        output_dir: Path,
        minimal: bool,
        split_lines: Optional[int],
        flat: bool,
        force: bool,
        include_source: bool,
        export_json: bool,
        quiet: bool,
    ) -> str:
        """Export a single session to markdown.

        Args:
            session: Session dict with 'file', 'filename', etc.
            home: Home identifier (e.g., "local", "wsl:Ubuntu").
            workspace: Workspace path.
            output_dir: Base output directory.
            minimal: If True, omit metadata.
            split_lines: Line threshold for splitting (None to disable).
            flat: If True, use flat directory structure.
            force: If True, overwrite existing files.
            include_source: If True, copy raw source file alongside markdown.
            export_json: If True, export as JSON instead of markdown.
            quiet: If True, suppress per-file output.

        Returns:
            Export result: EXPORT_EXPORTED, EXPORT_SKIPPED, or EXPORT_FAILED.
        """
        # Get session file path
        jsonl_file = session.get("file")
        if jsonl_file is None:
            raise ValueError("Session has no 'file' field")
        if isinstance(jsonl_file, str):
            jsonl_file = Path(jsonl_file)

        # Determine agent type
        agent_type = session.get("agent", AGENT_CLAUDE)

        # Read messages
        messages = self._read_session_messages(jsonl_file, agent_type)
        if messages is None:
            raise ValueError(f"Could not read messages from {jsonl_file}")

        # Generate source tag from home
        source_tag = self._get_source_tag(home)

        # Build output path
        ws_output_path = self._get_workspace_output_path(output_dir, workspace, flat)

        # Handle NDJSON export
        if export_json:
            output_name = self._build_output_filename_ndjson(jsonl_file, source_tag, messages)
            output_file = ws_output_path / output_name

            # Check if export is up-to-date
            if not force and self._is_export_up_to_date(output_file, jsonl_file):
                return EXPORT_SKIPPED

            # Write NDJSON export
            self._write_ndjson_export(
                output_file=output_file,
                agent_type=agent_type,
                messages=messages,
                session=session,
                quiet=quiet,
            )
            return EXPORT_EXPORTED

        # Handle markdown export
        output_name = self._build_output_filename(jsonl_file, source_tag, messages)
        output_file = ws_output_path / output_name

        # Check if export is up-to-date
        if not force and self._is_export_up_to_date(output_file, jsonl_file):
            return EXPORT_SKIPPED

        # Export the session
        self._write_export(
            jsonl_file=jsonl_file,
            output_file=output_file,
            output_name=output_name,
            agent_type=agent_type,
            messages=messages,
            minimal=minimal,
            split_lines=split_lines,
            include_source=include_source,
            quiet=quiet,
            ws_output_path=ws_output_path,
        )

        return EXPORT_EXPORTED

    def _read_session_messages(
        self, jsonl_file: Path, agent_type: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Read messages from a session file based on agent type.

        Args:
            jsonl_file: Path to session file.
            agent_type: Agent type (claude, codex, gemini).

        Returns:
            List of messages, or None if reading failed.
        """
        try:
            if agent_type == AGENT_GEMINI:
                # Gemini uses JSON files
                from agent_history.backends.gemini import gemini_read_json_messages

                messages, _ = gemini_read_json_messages(jsonl_file)
            elif agent_type == AGENT_CODEX:
                # Codex uses JSONL files
                from agent_history.backends.codex import codex_read_jsonl_messages

                messages, _ = codex_read_jsonl_messages(jsonl_file)
            else:
                # Claude uses JSONL files
                messages = read_jsonl_messages(jsonl_file)
            return messages
        except (OSError, json.JSONDecodeError) as e:
            sys.stderr.write(f"Error reading {jsonl_file.name}: {e}\n")
            return None

    def _get_source_tag(self, home: str) -> str:
        """Generate source tag from home identifier.

        Args:
            home: Home identifier (e.g., "local", "wsl:Ubuntu", "remote:vm01").

        Returns:
            Source tag for filename prefix (e.g., "", "wsl_Ubuntu_", "remote_vm01_").
        """
        if home == "local":
            return ""
        # Convert "wsl:Ubuntu" to "wsl_Ubuntu_"
        return home.replace(":", "_") + "_"

    def _get_workspace_output_path(self, output_dir: Path, workspace: str, flat: bool) -> Path:
        """Get output path for workspace, creating directory if needed.

        Args:
            output_dir: Base output directory.
            workspace: Workspace path or encoded name.
            flat: If True, use flat structure (no subdirs).

        Returns:
            Directory path for workspace output.
        """
        if flat:
            return output_dir

        # Normalize workspace name for directory
        ws_name = normalize_workspace_name(workspace, verify_local=False)
        ws_name = ws_name.replace("/", "-").replace("\\", "-")
        if ws_name.startswith("-"):
            ws_name = ws_name[1:]

        ws_path = output_dir / ws_name
        ws_path.mkdir(parents=True, exist_ok=True)
        return ws_path

    def _build_output_filename(
        self, jsonl_file: Path, source_tag: str, messages: List[Dict[str, Any]]
    ) -> str:
        """Build output filename with optional timestamp prefix.

        Args:
            jsonl_file: Source session file.
            source_tag: Source prefix (e.g., "wsl_Ubuntu_").
            messages: List of messages (for timestamp extraction).

        Returns:
            Output filename (e.g., "20240115120000_session-123.md").
        """
        ts_prefix = None
        if messages and messages[0].get("timestamp"):
            try:
                timestamp = messages[0]["timestamp"]
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                ts_prefix = dt.strftime("%Y%m%d%H%M%S")
            except (ValueError, AttributeError):
                pass

        if ts_prefix:
            return f"{source_tag}{ts_prefix}_{jsonl_file.stem}.md"
        return f"{source_tag}{jsonl_file.stem}.md"

    def _build_output_filename_ndjson(
        self, jsonl_file: Path, source_tag: str, messages: List[Dict[str, Any]]
    ) -> str:
        """Build NDJSON output filename with optional timestamp prefix.

        Args:
            jsonl_file: Source session file.
            source_tag: Source prefix (e.g., "wsl_Ubuntu_").
            messages: List of messages (for timestamp extraction).

        Returns:
            Output filename (e.g., "20240115120000_session-123.ndjson").
        """
        ts_prefix = None
        if messages and messages[0].get("timestamp"):
            try:
                timestamp = messages[0]["timestamp"]
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                ts_prefix = dt.strftime("%Y%m%d%H%M%S")
            except (ValueError, AttributeError):
                pass

        if ts_prefix:
            return f"{source_tag}{ts_prefix}_{jsonl_file.stem}.ndjson"
        return f"{source_tag}{jsonl_file.stem}.ndjson"

    def _write_ndjson_export(
        self,
        output_file: Path,
        agent_type: str,
        messages: List[Dict[str, Any]],
        session: Dict[str, Any],
        quiet: bool,
    ) -> None:
        """Write session to NDJSON file in unified format.

        The unified format normalizes messages from different agents to a
        common schema with fields: timestamp, role, content.
        Roles are normalized to: user, assistant, system.

        Args:
            output_file: Output file path.
            agent_type: Agent type (claude, codex, gemini).
            messages: Pre-read messages.
            session: Session metadata.
            quiet: If True, suppress per-file output.
        """
        lines = []
        for msg in messages:
            unified = self._normalize_message_to_unified(msg, agent_type)
            lines.append(json.dumps(unified, ensure_ascii=False))

        output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if not quiet:
            print(output_file)

    def _normalize_message_to_unified(self, msg: Dict[str, Any], agent_type: str) -> Dict[str, Any]:
        """Normalize a message to unified schema.

        The unified schema has:
        - timestamp: ISO format timestamp
        - role: "user", "assistant", or "system"
        - content: Message content as string

        Args:
            msg: Original message dictionary.
            agent_type: Agent type for role normalization.

        Returns:
            Normalized message dictionary.
        """
        # Normalize role: different agents may use different role names
        role = msg.get("role", "assistant")
        # Normalize "model" role (used by Gemini) to "assistant"
        if role == "model":
            role = "assistant"
        # Ensure role is one of the expected values
        if role not in ("user", "assistant", "system"):
            role = "assistant"

        # Extract content - handle both string and list content formats
        content = msg.get("content", "")
        if isinstance(content, list):
            # Claude sometimes has content as a list of blocks
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)
            content = "\n".join(text_parts)

        unified = {
            "timestamp": msg.get("timestamp", ""),
            "role": role,
            "content": content,
        }

        return unified

    def _is_export_up_to_date(self, output_file: Path, jsonl_file: Path) -> bool:
        """Check if export output is already up-to-date.

        Args:
            output_file: Destination file path.
            jsonl_file: Source session file path.

        Returns:
            True if output is up-to-date and can be skipped.
        """
        if not output_file.exists():
            return False
        return output_file.stat().st_mtime >= jsonl_file.stat().st_mtime

    def _write_export(
        self,
        jsonl_file: Path,
        output_file: Path,
        output_name: str,
        agent_type: str,
        messages: List[Dict[str, Any]],
        minimal: bool,
        split_lines: Optional[int],
        include_source: bool,
        quiet: bool,
        ws_output_path: Path,
    ) -> None:
        """Write exported session to file(s).

        Args:
            jsonl_file: Source session file.
            output_file: Main output file path.
            output_name: Output filename.
            agent_type: Agent type.
            messages: Pre-read messages.
            minimal: If True, omit metadata.
            split_lines: Line threshold for splitting.
            include_source: If True, copy raw source file alongside markdown.
            quiet: If True, suppress per-file output.
            ws_output_path: Workspace output directory.
        """
        # Try to write split parts if enabled
        if split_lines and messages and len(messages) > MIN_MESSAGES_FOR_SPLIT:
            parts = self._generate_markdown_parts(messages, jsonl_file, minimal, split_lines)
            if parts:
                self._write_split_parts(parts, output_name, ws_output_path, quiet)
                # Copy source file if requested
                if include_source:
                    self._copy_source_file(jsonl_file, ws_output_path, quiet)
                return

        # Write single file
        markdown = self._parse_jsonl_to_markdown(jsonl_file, minimal, messages)
        output_file.write_text(markdown, encoding="utf-8")
        if not quiet:
            print(output_file)

        # Copy source file if requested
        if include_source:
            self._copy_source_file(jsonl_file, ws_output_path, quiet)

    def _write_split_parts(
        self,
        parts: List[Tuple[int, int, str, int, int]],
        output_name: str,
        ws_output_path: Path,
        quiet: bool,
    ) -> None:
        """Write split parts to files.

        Args:
            parts: List of (part_num, total_parts, markdown, start_msg, end_msg).
            output_name: Base output filename.
            ws_output_path: Output directory.
            quiet: If True, suppress per-file output.
        """
        base_name = output_name[:-3]  # Remove .md extension
        for part_num, _, part_md, _, _ in parts:
            part_file = ws_output_path / f"{base_name}_part{part_num}.md"
            part_file.write_text(part_md, encoding="utf-8")
            if not quiet:
                print(part_file)

    def _copy_source_file(
        self,
        source_file: Path,
        output_dir: Path,
        quiet: bool,
    ) -> None:
        """Copy raw source file to output directory.

        Args:
            source_file: Source session file (JSONL or JSON).
            output_dir: Destination directory.
            quiet: If True, suppress output.
        """
        import shutil

        dest_file = output_dir / source_file.name
        shutil.copy2(source_file, dest_file)
        if not quiet:
            print(dest_file)

    # =========================================================================
    # Markdown Generation
    # =========================================================================

    def _parse_jsonl_to_markdown(
        self,
        jsonl_file: Path,
        minimal: bool = False,
        messages: Optional[List[Dict[str, Any]]] = None,
        display_file: Optional[str] = None,
        show_graph: bool = True,
    ) -> str:
        """Convert a Claude Code JSONL session file to readable Markdown.

        Args:
            jsonl_file: Path to the JSONL file.
            minimal: If True, omit metadata.
            messages: Pre-parsed messages (optional).
            display_file: File name to display in header.
            show_graph: If True, include conversation graph analysis.

        Returns:
            Markdown formatted string.
        """
        if messages is None:
            messages = read_jsonl_messages(jsonl_file)

        # Build header
        md_lines = self._generate_markdown_file_header(jsonl_file, messages, display_file)

        md_lines.extend(["", "---", ""])

        # Build message index for parent references
        uuid_to_index = {msg["uuid"]: i for i, msg in enumerate(messages, 1) if msg.get("uuid")}

        # Generate message sections
        for i, msg in enumerate(messages, 1):
            md_lines.extend(self._generate_message_section(msg, i, minimal, uuid_to_index))

        return "\n".join(md_lines)

    def _generate_markdown_file_header(
        self,
        jsonl_file: Path,
        messages: List[Dict[str, Any]],
        display_file: Optional[str] = None,
    ) -> List[str]:
        """Generate markdown header for a session file.

        Args:
            jsonl_file: Source file path.
            messages: List of messages.
            display_file: Override display filename.

        Returns:
            List of markdown header lines.
        """
        display_name = display_file or jsonl_file.name
        lines = [f"# Claude Code Session: {display_name}", ""]

        if messages:
            first_ts = messages[0].get("timestamp", "")
            last_ts = messages[-1].get("timestamp", "") if len(messages) > 1 else ""
            if first_ts:
                lines.append(f"**Started:** {first_ts}")
            if last_ts:
                lines.append(f"**Ended:** {last_ts}")
            lines.append(f"**Messages:** {len(messages)}")

        return lines

    def _generate_message_section(
        self,
        msg: Dict[str, Any],
        index: int,
        minimal: bool,
        uuid_to_index: Dict[str, int],
    ) -> List[str]:
        """Generate markdown section for a single message.

        Args:
            msg: Message dictionary.
            index: Message index (1-based).
            minimal: If True, omit metadata.
            uuid_to_index: Mapping of UUID to message index.

        Returns:
            List of markdown lines for the message.
        """
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")

        # Role emoji and header
        role_display = "User" if role == "user" else "Assistant"
        lines = [f"## Message {index}: {role_display}", ""]

        if timestamp:
            lines.append(f"*{timestamp}*")
            lines.append("")

        # Add content
        lines.append(content)
        lines.append("")

        # Add metadata if not minimal
        if not minimal:
            metadata_lines = self._generate_metadata_section(msg, uuid_to_index)
            if metadata_lines:
                lines.extend(metadata_lines)

        lines.append("---")
        lines.append("")

        return lines

    def _generate_metadata_section(
        self, msg: Dict[str, Any], uuid_to_index: Dict[str, int]
    ) -> List[str]:
        """Generate metadata section for a message.

        Args:
            msg: Message dictionary.
            uuid_to_index: Mapping of UUID to message index.

        Returns:
            List of metadata lines.
        """
        lines = []

        # Common metadata fields
        if msg.get("model"):
            lines.append(f"**Model:** {msg['model']}")

        if msg.get("usage"):
            usage = msg["usage"]
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            lines.append(f"**Tokens:** {input_tokens} in / {output_tokens} out")

        if msg.get("cwd"):
            lines.append(f"**CWD:** {msg['cwd']}")

        if msg.get("gitBranch"):
            lines.append(f"**Branch:** {msg['gitBranch']}")

        # Parent reference
        parent_uuid = msg.get("parentUuid")
        if parent_uuid and parent_uuid in uuid_to_index:
            lines.append(f"**Reply to:** Message {uuid_to_index[parent_uuid]}")

        if lines:
            lines.insert(0, "")
            lines.insert(1, "<details>")
            lines.insert(2, "<summary>Metadata</summary>")
            lines.insert(3, "")
            lines.append("")
            lines.append("</details>")

        return lines

    # =========================================================================
    # Conversation Splitting
    # =========================================================================

    def _generate_markdown_parts(
        self,
        messages: List[Dict[str, Any]],
        jsonl_file: Path,
        minimal: bool,
        split_lines: int,
        display_file: Optional[str] = None,
    ) -> Optional[List[Tuple[int, int, str, int, int]]]:
        """Generate multiple markdown parts from messages, split at smart break points.

        Args:
            messages: List of messages.
            jsonl_file: Source file path.
            minimal: If True, omit metadata.
            split_lines: Target lines per part.
            display_file: Override display filename.

        Returns:
            List of (part_num, total_parts, markdown, start_msg, end_msg) tuples,
            or None if splitting not needed.
        """
        if not split_lines or len(messages) == 0:
            return None

        # Find all split points
        split_points = [0]  # Start with message 0
        remaining_messages = messages

        while True:
            split_idx = self._find_best_split_point(remaining_messages, split_lines, minimal)

            if split_idx is None or split_idx >= len(remaining_messages):
                break

            global_idx = split_points[-1] + split_idx
            split_points.append(global_idx)
            remaining_messages = messages[global_idx:]

        # Add end point
        split_points.append(len(messages))

        # If only one part, no splitting needed
        if len(split_points) <= MIN_SPLIT_POINTS:
            return None

        total_parts = len(split_points) - 1
        parts = []

        for part_num in range(total_parts):
            start_idx = split_points[part_num]
            end_idx = split_points[part_num + 1]
            part_messages = messages[start_idx:end_idx]

            # Generate markdown for this part
            part_md = self._generate_part_markdown(
                part_messages,
                jsonl_file,
                minimal,
                part_num + 1,
                total_parts,
                start_idx,
                end_idx,
                display_file,
            )

            parts.append((part_num + 1, total_parts, part_md, start_idx, end_idx))

        return parts

    def _find_best_split_point(
        self, messages: List[Dict[str, Any]], target_lines: int, minimal: bool
    ) -> Optional[int]:
        """Find the optimal message index to split a conversation.

        Args:
            messages: List of messages.
            target_lines: Target number of lines per part.
            minimal: If True, less metadata overhead.

        Returns:
            Message index to split at, or None if no split needed.
        """
        min_lines = int(target_lines * SPLIT_MIN_FACTOR)
        max_lines = int(target_lines * SPLIT_MAX_FACTOR)

        current_lines = HEADER_LINES_ESTIMATE
        best_split = None
        best_score = -1

        for i, msg in enumerate(messages):
            current_lines += self._estimate_message_lines(msg.get("content", ""), not minimal)

            if current_lines > max_lines:
                return i if i > 0 else 1

            if current_lines >= min_lines:
                score = self._calculate_split_score(messages, i, msg, current_lines, target_lines)
                if score > best_score:
                    best_score = score
                    best_split = i + 1

        return best_split

    def _estimate_message_lines(self, msg_content: str, has_metadata: bool) -> int:
        """Estimate number of lines a message will take in markdown.

        Args:
            msg_content: Message content string.
            has_metadata: If True, include metadata overhead.

        Returns:
            Estimated line count.
        """
        lines = 0
        lines += 1  # Message header (## Message N)
        lines += 1  # Empty line
        lines += 1  # Timestamp
        lines += 1  # Empty line
        lines += len(msg_content.split("\n"))  # Content
        lines += 1  # Empty line
        if has_metadata:
            lines += METADATA_LINES_ESTIMATE
            lines += 1  # Empty line
        lines += 1  # Separator (---)
        lines += 1  # Empty line
        return lines

    def _calculate_split_score(
        self,
        messages: List[Dict[str, Any]],
        index: int,
        msg: Dict[str, Any],
        current_lines: int,
        target_lines: int,
    ) -> float:
        """Calculate a score for splitting at this position.

        Higher scores indicate better split points.

        Args:
            messages: List of messages.
            index: Current message index.
            msg: Current message.
            current_lines: Current line count.
            target_lines: Target line count.

        Returns:
            Split score (higher is better).
        """
        score = 0.0

        # Best: next message is from User (starting new topic)
        if index + 1 < len(messages) and messages[index + 1].get("role") == "user":
            score += SCORE_USER_MESSAGE_NEXT

        # Good: current message is a tool result (action complete)
        if msg.get("content") and TOOL_RESULT_MARKER in msg.get("content", ""):
            score += SCORE_TOOL_RESULT

        # Bonus for time gaps
        if index + 1 < len(messages):
            time_gap = self._get_time_gap(msg, messages[index + 1])
            if time_gap >= TIME_GAP_LARGE:
                score += SCORE_TIME_GAP_LARGE
            elif time_gap >= TIME_GAP_MEDIUM:
                score += SCORE_TIME_GAP_MEDIUM

        # Penalty for distance from target
        distance = abs(current_lines - target_lines)
        score -= distance * SCORE_DISTANCE_PENALTY

        return score

    def _get_time_gap(self, msg1: Dict[str, Any], msg2: Dict[str, Any]) -> float:
        """Calculate time gap between two messages in seconds.

        Args:
            msg1: First message.
            msg2: Second message.

        Returns:
            Time gap in seconds, or 0 if timestamps unavailable.
        """
        try:
            ts1 = msg1.get("timestamp", "")
            ts2 = msg2.get("timestamp", "")
            if not ts1 or not ts2:
                return 0

            dt1 = datetime.fromisoformat(ts1.replace("Z", "+00:00"))
            dt2 = datetime.fromisoformat(ts2.replace("Z", "+00:00"))
            return abs((dt2 - dt1).total_seconds())
        except (ValueError, TypeError):
            return 0

    def _generate_part_markdown(
        self,
        messages: List[Dict[str, Any]],
        jsonl_file: Path,
        minimal: bool,
        part_num: int,
        total_parts: int,
        start_idx: int,
        end_idx: int,
        display_file: Optional[str] = None,
    ) -> str:
        """Generate markdown for a single part of a split conversation.

        Args:
            messages: Messages for this part.
            jsonl_file: Source file path.
            minimal: If True, omit metadata.
            part_num: Part number (1-based).
            total_parts: Total number of parts.
            start_idx: Starting message index (0-based).
            end_idx: Ending message index (0-based, exclusive).
            display_file: Override display filename.

        Returns:
            Markdown string for this part.
        """
        display_name = display_file or jsonl_file.name

        lines = [
            f"# Claude Code Session: {display_name} (Part {part_num}/{total_parts})",
            "",
            f"**Messages:** {start_idx + 1} - {end_idx} of total",
            "",
        ]

        lines.extend(["", "---", ""])

        # Build UUID index for this part
        uuid_to_index = {
            msg["uuid"]: start_idx + i for i, msg in enumerate(messages, 1) if msg.get("uuid")
        }

        for i, msg in enumerate(messages):
            global_idx = start_idx + i + 1
            lines.extend(self._generate_message_section(msg, global_idx, minimal, uuid_to_index))

        return "\n".join(lines)

    # =========================================================================
    # Index Manifest Generation
    # =========================================================================

    def _generate_index_manifest(
        self,
        output_dir: Path,
        sources_info: Dict[str, int],
        quiet: bool,
    ) -> None:
        """Generate index.md manifest file summarizing all exported sessions.

        This method scans the output directory for workspace subdirectories
        and generates an index.md file with:
        - Generation timestamp
        - Total workspaces and sessions counts
        - Sources section listing sessions per home
        - Workspaces section with headings for each workspace

        Args:
            output_dir: Base output directory containing workspace subdirs.
            sources_info: Mapping of home identifier to session count.
            quiet: If True, suppress output.
        """
        workspaces = self._scan_workspace_directories(output_dir)

        lines = [
            "# Claude Conversation Export Index",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Total Workspaces:** {len(workspaces)}",
            f"**Total Sessions:** {sum(ws['total'] for ws in workspaces.values())}",
            "",
            "## Sources",
            "",
        ]

        # Add sources section - format home names nicely
        for home, count in sorted(sources_info.items()):
            source_label = self._format_source_label(home)
            lines.append(f"- **{source_label}**: {count} sessions")

        lines.extend(["", "## Workspaces", ""])

        for workspace_name in sorted(workspaces.keys()):
            ws_info = workspaces[workspace_name]
            lines.append(f"### {workspace_name} ({ws_info['total']} sessions)")
            lines.append("")
            lines.extend(self._format_workspace_sources(ws_info["sources"]))
            lines.append("")

        index_path = output_dir / "index.md"
        index_path.write_text("\n".join(lines), encoding="utf-8")
        if not quiet:
            print(f"\n[Index] Generated: {index_path}")

    def _scan_workspace_directories(self, output_dir: Path) -> Dict[str, Dict[str, Any]]:
        """Scan workspace directories and group sessions by source.

        Args:
            output_dir: Base output directory containing workspace subdirs.

        Returns:
            Dictionary mapping workspace name to info dict with 'total' and 'sources'.
        """
        workspaces: Dict[str, Dict[str, Any]] = {}
        for item in output_dir.iterdir():
            if not item.is_dir():
                continue

            sessions = list(item.glob("*.md"))
            sources = {"local": 0, "wsl": 0, "windows": 0, "remote": 0}
            for session_file in sessions:
                sources[self._classify_session_source(session_file.name)] += 1

            workspaces[item.name] = {"total": len(sessions), "sources": sources}
        return workspaces

    def _classify_session_source(self, filename: str) -> str:
        """Classify session source based on filename prefix.

        Args:
            filename: Session filename (e.g., "wsl_Ubuntu_session.md").

        Returns:
            Source category: "local", "wsl", "windows", or "remote".
        """
        if filename.startswith("wsl_"):
            return "wsl"
        if filename.startswith("windows_"):
            return "windows"
        if filename.startswith("remote_"):
            return "remote"
        return "local"

    def _format_source_label(self, home: str) -> str:
        """Format home identifier as a human-readable label.

        Args:
            home: Home identifier (e.g., "local", "wsl:Ubuntu").

        Returns:
            Human-readable label (e.g., "Local", "WSL (Ubuntu)").
        """
        if home == "local":
            return "Local"
        if home.startswith("wsl:"):
            distro = home[4:]
            return f"WSL ({distro})"
        if home.startswith("windows:"):
            user = home[8:]
            return f"Windows ({user})"
        if home.startswith("remote:"):
            host = home[7:]
            return f"Remote ({host})"
        return home

    def _format_workspace_sources(self, sources: Dict[str, int]) -> List[str]:
        """Format workspace sources as markdown lines.

        Args:
            sources: Mapping of source category to session count.

        Returns:
            List of markdown lines describing non-zero sources.
        """
        lines = []
        for source, label in [
            ("local", "Local"),
            ("wsl", "WSL"),
            ("windows", "Windows"),
            ("remote", "Remote"),
        ]:
            if sources.get(source, 0) > 0:
                lines.append(f"- **{label}:** {sources[source]} sessions")
        return lines
