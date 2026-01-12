"""Session export handler for the resolution pipeline.

This module provides the SessionExportHandler class that handles 'session export'
commands using the new resolution pipeline architecture. It exports sessions
to markdown files, supporting options like minimal output, split files, and
flat directory structure.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent_history.backends.claude import read_jsonl_messages
from agent_history.core.workspaces import build_workspace_metadata
from agent_history.export import (
    MIN_MESSAGES_FOR_SPLIT,
    build_output_filename_ndjson,
    copy_source_file,
    generate_index_manifest,
    generate_markdown_parts,
    parse_jsonl_to_markdown,
    write_ndjson_export,
)
from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope
from agent_history.types import MessageDict, SessionDict
from agent_history.utils.paths import decode_workspace_path
from agent_history.utils.platform import AGENT_CLAUDE, AGENT_CODEX, AGENT_GEMINI
from agent_history.utils.workspace_ref import WorkspaceContext

_INVALID_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1F]')

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
        jobs = verb_args.get("jobs")
        session_ids = verb_args.get("session_ids") or []
        quiet = output_args.quiet

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Track export statistics
        exported: List[SessionDict] = []
        skipped: List[SessionDict] = []
        failed: List[Tuple[SessionDict, str]] = []

        # Track sources for index manifest generation
        sources_info: Dict[str, int] = {}  # home -> session count

        # Collect all tasks to process
        tasks = []
        for record in scope:
            context = WorkspaceContext.from_record(record)
            for session in record.sessions:
                tasks.append(
                    (session, context.home, context.workspace, context.workspace_display)
                )

        # Filter by explicit session IDs/filenames if provided
        missing_ids: List[str] = []
        if session_ids:
            tasks, missing_ids = self._filter_tasks_by_session_ids(tasks, session_ids)

        # Use ThreadPoolExecutor when jobs > 1
        if jobs is not None and jobs > 1:
            with ThreadPoolExecutor(max_workers=jobs) as executor:
                futures = []
                for session, home, workspace, workspace_display in tasks:
                    future = executor.submit(
                        self._export_session_safe,
                        session=session,
                        home=home,
                        workspace=workspace,
                        workspace_display=workspace_display,
                        output_dir=output_dir,
                        minimal=minimal,
                        split_lines=split_lines,
                        flat=flat,
                        force=force,
                        include_source=include_source,
                        export_json=export_json,
                        quiet=quiet,
                    )
                    futures.append((future, session, home))

                # Collect results
                for future, session, home in futures:
                    result, error = future.result()
                    if error:
                        failed.append((session, error))
                        if not quiet:
                            filename = session.get("filename", session.get("file", "unknown"))
                            sys.stderr.write(f"Error exporting {filename}: {error}\n")

                    elif result == EXPORT_EXPORTED:
                        exported.append(session)
                        sources_info[home] = sources_info.get(home, 0) + 1
                    elif result == EXPORT_SKIPPED:
                        skipped.append(session)
                        sources_info[home] = sources_info.get(home, 0) + 1
        else:
            # Sequential: Process each record in scope
            for session, home, workspace, workspace_display in tasks:
                try:
                    result = self._export_session(
                        session=session,
                        home=home,
                        workspace=workspace,
                        workspace_display=workspace_display,
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
                        sources_info[home] = sources_info.get(home, 0) + 1
                    elif result == EXPORT_SKIPPED:
                        skipped.append(session)
                        # Also track skipped for index (they still exist in output)
                        sources_info[home] = sources_info.get(home, 0) + 1
                except Exception as e:
                    failed.append((session, str(e)))
                    if not quiet:
                        filename = session.get("filename", session.get("file", "unknown"))
                        sys.stderr.write(f"Error exporting {filename}: {e}\n")

        # Add missing session IDs as failures
        for missing_id in missing_ids:
            failed.append(({"filename": missing_id}, "Session not found"))
            if not quiet:
                sys.stderr.write(f"Error exporting {missing_id}: session not found\n")

        # Collect unique homes and workspaces from export tasks
        contexts = [
            WorkspaceContext(
                home=home,
                workspace=workspace,
                workspace_key=workspace,
                workspace_display=workspace_display,
            )
            for _, home, workspace, workspace_display in tasks
        ]
        metadata = build_workspace_metadata(contexts)
        unique_homes = set(metadata["homes"])
        unique_workspaces = set(metadata["workspaces"])

        # Generate index manifest if multi-home or multi-workspace export
        if len(unique_homes) > 1 or len(unique_workspaces) > 1:
            generate_index_manifest(output_dir, sources_info, quiet)

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
                "homes": sorted(unique_homes),
                "workspaces": sorted(unique_workspaces),
                "workspace_display_map": metadata["workspace_display_map"],
            },
            errors=[f"{s.get('filename', s.get('file', 'unknown'))}: {e}" for s, e in failed],
        )

    def _filter_tasks_by_session_ids(
        self,
        tasks: List[Tuple[SessionDict, str, str, str]],
        session_ids: List[str],
    ) -> Tuple[List[Tuple[SessionDict, str, str, str]], List[str]]:
        """Filter export tasks to specific session IDs or filenames."""
        targets = [str(value).strip() for value in session_ids if str(value).strip()]
        if not targets:
            return tasks, []

        matched: set[str] = set()
        filtered: List[Tuple[SessionDict, str, str, str]] = []
        seen_keys: set[str] = set()

        for session, home, workspace, workspace_display in tasks:
            for target in targets:
                if self._session_matches_target(session, target):
                    key = (
                        str(session.get("file"))
                        or session.get("filename")
                        or session.get("session_id")
                        or session.get("id")
                    )
                    if key not in seen_keys:
                        seen_keys.add(key)
                        filtered.append((session, home, workspace, workspace_display))
                    matched.add(target)
                    break

        missing = [target for target in targets if target not in matched]
        return filtered, missing

    def _session_matches_target(self, session: SessionDict, target: str) -> bool:
        """Check whether a session matches an explicit identifier."""
        target = str(target)
        if not target:
            return False

        for key in ("session_id", "id", "filename"):
            value = session.get(key)
            if value is not None and str(value) == target:
                return True

        file_value = session.get("file")
        if file_value:
            path = Path(str(file_value))
            if target in (str(path), path.name, path.stem):
                return True

        filename = session.get("filename")
        if filename:
            if target == Path(str(filename)).stem:
                return True

        return False

    def _export_session_safe(
        self,
        session: SessionDict,
        home: str,
        workspace: str,
        workspace_display: str,
        output_dir: Path,
        minimal: bool,
        split_lines: Optional[int],
        flat: bool,
        force: bool,
        include_source: bool,
        export_json: bool,
        quiet: bool,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Export a single session, catching exceptions for thread safety.

        Returns:
            Tuple of (result, error). If error is None, result contains
            EXPORT_EXPORTED, EXPORT_SKIPPED, or EXPORT_FAILED.
        """
        try:
            result = self._export_session(
                session=session,
                home=home,
                workspace=workspace,
                workspace_display=workspace_display,
                output_dir=output_dir,
                minimal=minimal,
                split_lines=split_lines,
                flat=flat,
                force=force,
                include_source=include_source,
                export_json=export_json,
                quiet=quiet,
            )
            return (result, None)
        except Exception as e:
            return (None, str(e))

    def _export_session(
        self,
        session: SessionDict,
        home: str,
        workspace: str,
        workspace_display: str,
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

        # Ensure remote sessions are fetched locally before reading
        if not jsonl_file.exists() and home.startswith("remote:"):
            from agent_history.adapters.remote import SSHRemoteClient

            remote_host = home[7:]
            client = SSHRemoteClient()
            local_copy = client.ensure_local_copy(remote_host, workspace, session)
            if local_copy:
                jsonl_file = local_copy

        # Ensure web sessions are cached locally before reading
        if not jsonl_file.exists() and home == "web":
            from agent_history.backends.web import WebSessionsError, ensure_web_session_cache
            from agent_history.backends.web import resolve_web_credentials

            session_id = session.get("session_id") or session.get("id") or session.get("filename")
            if not session_id:
                raise ValueError("Web session missing identifier")
            try:
                token, org_uuid = resolve_web_credentials()
                jsonl_file = ensure_web_session_cache(
                    str(session_id), token, org_uuid, force=force
                )
            except WebSessionsError as exc:
                raise ValueError(str(exc)) from exc

        if not jsonl_file.exists():
            raise ValueError(f"Session file does not exist: {jsonl_file}")

        # Determine agent type
        agent_type = session.get("agent", AGENT_CLAUDE)

        # Read messages
        messages = self._read_session_messages(jsonl_file, agent_type)
        if messages is None:
            raise ValueError(f"Could not read messages from {jsonl_file}")

        # Generate source tag from home
        source_tag = self._get_source_tag(home)

        # Build output path
        ws_output_path = self._get_workspace_output_path(output_dir, workspace_display, flat)

        # Handle NDJSON export
        if export_json:
            output_name = build_output_filename_ndjson(jsonl_file, source_tag, messages)
            output_file = ws_output_path / output_name

            # Check if export is up-to-date
            if not force and self._is_export_up_to_date(output_file, jsonl_file):
                return EXPORT_SKIPPED

            # Write NDJSON export
            write_ndjson_export(
                output_file=output_file,
                agent_type=agent_type,
                messages=messages,
                session=session,
                quiet=quiet,
            )
            if include_source:
                source_copy = output_file.with_suffix(jsonl_file.suffix)
                source_copy.write_bytes(jsonl_file.read_bytes())
                if not quiet:
                    print(source_copy)
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
    ) -> Optional[List[MessageDict]]:
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

        def _sanitize_segment(segment: str) -> str:
            cleaned = _INVALID_PATH_CHARS_RE.sub("_", segment)
            cleaned = cleaned.rstrip(" .")
            if not cleaned:
                cleaned = "_"
            upper = cleaned.upper()
            if upper in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                "COM1",
                "COM2",
                "COM3",
                "COM4",
                "COM5",
                "COM6",
                "COM7",
                "COM8",
                "COM9",
                "LPT1",
                "LPT2",
                "LPT3",
                "LPT4",
                "LPT5",
                "LPT6",
                "LPT7",
                "LPT8",
                "LPT9",
            }:
                cleaned = f"_{cleaned}"
            return cleaned

        decoded = decode_workspace_path(workspace, verify_local=False)
        normalized = decoded.replace("\\", "/")
        if "/" in normalized:
            parts_raw = [part for part in normalized.split("/") if part]
            if parts_raw and parts_raw[0].endswith(":"):
                parts_raw[0] = parts_raw[0].rstrip(":")
            parts = [_sanitize_segment(part) for part in parts_raw]
            ws_path = output_dir.joinpath(*parts)
        else:
            ws_path = output_dir / _sanitize_segment(normalized)
        ws_path.mkdir(parents=True, exist_ok=True)
        return ws_path

    def _build_output_filename(
        self, jsonl_file: Path, source_tag: str, messages: List[MessageDict]
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
        messages: List[MessageDict],
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
            parts = generate_markdown_parts(messages, jsonl_file, minimal, split_lines)
            if parts:
                self._write_split_parts(parts, output_name, ws_output_path, quiet)
                # Copy source file if requested
                if include_source:
                    copy_source_file(jsonl_file, ws_output_path, quiet)
                return

        # Write single file
        if agent_type == AGENT_CODEX:
            from agent_history.backends.codex import codex_parse_jsonl_to_markdown

            markdown = codex_parse_jsonl_to_markdown(jsonl_file, minimal)
        elif agent_type == AGENT_GEMINI:
            from agent_history.backends.gemini import gemini_parse_json_to_markdown

            markdown = gemini_parse_json_to_markdown(jsonl_file, minimal)
        else:
            markdown = parse_jsonl_to_markdown(
                jsonl_file, minimal, messages, agent_type=agent_type
            )
        output_file.write_text(markdown, encoding="utf-8")
        if not quiet:
            print(output_file)

        # Copy source file if requested
        if include_source:
            copy_source_file(jsonl_file, ws_output_path, quiet)

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
