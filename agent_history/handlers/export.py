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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent_history.backends.registry import (
    get_backend,
    get_default_backend_id,
    infer_backend_from_file,
)
from agent_history.cli.constants import (
    DEFAULT_OUTPUT_DIR,
    EXPORT_FORMAT_HTML,
    EXPORT_FORMAT_MARKDOWN,
    MARKDOWN_DEFAULT_LEVEL,
)
from agent_history.core.workspaces import build_workspace_metadata
from agent_history.export import (
    MIN_MESSAGES_FOR_SPLIT,
    build_output_filename_ndjson,
    copy_source_file,
    generate_index_manifest,
    generate_markdown_parts,
    render_html_export,
    render_html_timeline_export,
    write_ndjson_export,
)
from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope
from agent_history.types import MessageDict, SessionDict
from agent_history.utils.paths import decode_workspace_path
from agent_history.utils.workspace_ref import WorkspaceContext

_INVALID_PATH_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
_ExportTask = Tuple[SessionDict, str, str, str]

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
                - output_dir: Path for output (default: ./.cagelens/exports)
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
        output_dir_value = verb_args.get("output_dir", DEFAULT_OUTPUT_DIR)
        output_to_stdout = str(output_dir_value) == "-"
        output_dir = (
            Path(output_dir_value) if isinstance(output_dir_value, str) else output_dir_value
        )
        export_format = verb_args.get("export_format", EXPORT_FORMAT_MARKDOWN)
        markdown_level = verb_args.get("markdown_level", MARKDOWN_DEFAULT_LEVEL)
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
        targets = verb_args.get("targets") or []
        quiet = output_args.quiet

        if export_format == EXPORT_FORMAT_HTML and export_json:
            return CommandResult(
                success=False,
                data=None,
                data_type="export_result",
                errors=["Use either --json or --format html, not both"],
            )

        if output_to_stdout:
            return self._export_single_session_to_stdout(
                targets=targets,
                minimal=minimal,
                markdown_level=markdown_level,
                export_format=export_format,
                export_json=export_json,
                split_lines=split_lines,
                include_source=include_source,
            )

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Track export statistics
        exported: List[SessionDict] = []
        skipped: List[SessionDict] = []
        failed: List[Tuple[SessionDict, str]] = []

        # Track sources for index manifest generation
        sources_info: Dict[str, int] = {}  # home -> session count

        tasks = self._build_export_tasks(scope)

        # Filter by explicit session IDs/filenames if provided
        missing_ids: List[str] = []
        if session_ids:
            tasks, missing_ids = self._filter_tasks_by_session_ids(tasks, session_ids)

        self._process_export_tasks(
            tasks=tasks,
            output_dir=output_dir,
            minimal=minimal,
            split_lines=split_lines,
            flat=flat,
            force=force,
            include_source=include_source,
            export_json=export_json,
            export_format=export_format,
            markdown_level=markdown_level,
            quiet=quiet,
            jobs=jobs,
            exported=exported,
            skipped=skipped,
            failed=failed,
            sources_info=sources_info,
        )

        # Add missing session IDs as failures
        for missing_id in missing_ids:
            failed.append(({"filename": missing_id}, "Session not found"))
            if not quiet:
                sys.stderr.write(f"Error exporting {missing_id}: session not found\n")

        if export_format == EXPORT_FORMAT_HTML:
            self._write_html_timeline_index(
                tasks=tasks,
                output_dir=output_dir,
                flat=flat,
                quiet=quiet,
            )

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

    def _build_export_tasks(self, scope: ConcreteScope) -> List[_ExportTask]:
        tasks: List[_ExportTask] = []
        for record in scope:
            context = WorkspaceContext.from_record(record)
            for session in record.sessions:
                tasks.append((session, context.home, context.workspace, context.workspace_display))
        return tasks

    def _process_export_tasks(
        self,
        tasks: List[_ExportTask],
        output_dir: Path,
        minimal: bool,
        split_lines: Optional[int],
        flat: bool,
        force: bool,
        include_source: bool,
        export_json: bool,
        export_format: str,
        markdown_level: int,
        quiet: bool,
        jobs: Optional[int],
        exported: List[SessionDict],
        skipped: List[SessionDict],
        failed: List[Tuple[SessionDict, str]],
        sources_info: Dict[str, int],
    ) -> None:
        if jobs is not None and jobs > 1:
            self._process_export_tasks_parallel(
                tasks,
                output_dir,
                minimal,
                split_lines,
                flat,
                force,
                include_source,
                export_json,
                export_format,
                markdown_level,
                quiet,
                jobs,
                exported,
                skipped,
                failed,
                sources_info,
            )
            return

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
                    export_format=export_format,
                    markdown_level=markdown_level,
                    quiet=quiet,
                )
                self._record_export_result(result, session, home, exported, skipped, sources_info)
            except Exception as e:
                self._record_export_error(session, str(e), failed, quiet)

    def _process_export_tasks_parallel(
        self,
        tasks: List[_ExportTask],
        output_dir: Path,
        minimal: bool,
        split_lines: Optional[int],
        flat: bool,
        force: bool,
        include_source: bool,
        export_json: bool,
        export_format: str,
        markdown_level: int,
        quiet: bool,
        jobs: int,
        exported: List[SessionDict],
        skipped: List[SessionDict],
        failed: List[Tuple[SessionDict, str]],
        sources_info: Dict[str, int],
    ) -> None:
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            futures = [
                (
                    executor.submit(
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
                        export_format=export_format,
                        markdown_level=markdown_level,
                        quiet=quiet,
                    ),
                    session,
                    home,
                )
                for session, home, workspace, workspace_display in tasks
            ]

            for future, session, home in futures:
                result, error = future.result()
                if error:
                    self._record_export_error(session, error, failed, quiet)
                elif result:
                    self._record_export_result(
                        result, session, home, exported, skipped, sources_info
                    )

    def _record_export_result(
        self,
        result: str,
        session: SessionDict,
        home: str,
        exported: List[SessionDict],
        skipped: List[SessionDict],
        sources_info: Dict[str, int],
    ) -> None:
        if result == EXPORT_EXPORTED:
            exported.append(session)
            sources_info[home] = sources_info.get(home, 0) + 1
        elif result == EXPORT_SKIPPED:
            skipped.append(session)
            sources_info[home] = sources_info.get(home, 0) + 1

    def _record_export_error(
        self,
        session: SessionDict,
        error: str,
        failed: List[Tuple[SessionDict, str]],
        quiet: bool,
    ) -> None:
        failed.append((session, error))
        if not quiet:
            filename = session.get("filename", session.get("file", "unknown"))
            sys.stderr.write(f"Error exporting {filename}: {error}\n")

    def _filter_tasks_by_session_ids(
        self,
        tasks: List[_ExportTask],
        session_ids: List[str],
    ) -> Tuple[List[_ExportTask], List[str]]:
        """Filter export tasks to specific session IDs or filenames."""
        targets = [str(value).strip() for value in session_ids if str(value).strip()]
        if not targets:
            return tasks, []

        matched: set[str] = set()
        filtered: List[_ExportTask] = []
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

    def _export_single_session_to_stdout(
        self,
        targets: List[str],
        minimal: bool,
        markdown_level: int,
        export_format: str,
        export_json: bool,
        split_lines: Optional[int],
        include_source: bool,
    ) -> CommandResult:
        """Render one explicit session file to stdout."""
        if export_json:
            return CommandResult(
                success=False,
                data=None,
                data_type="export_result",
                errors=["Stdout export does not support --json"],
            )
        if split_lines:
            return CommandResult(
                success=False,
                data=None,
                data_type="export_result",
                errors=["Stdout export does not support --split"],
            )
        if include_source:
            return CommandResult(
                success=False,
                data=None,
                data_type="export_result",
                errors=["Stdout export does not support --source"],
            )
        if len(targets) != 1:
            return CommandResult(
                success=False,
                data=None,
                data_type="export_result",
                errors=[
                    "Stdout export requires exactly one session file target",
                    "Pass the full path to the session file when using -o -",
                ],
            )

        session_file = Path(targets[0]).expanduser()
        if not session_file.is_file():
            return CommandResult(
                success=False,
                data=None,
                data_type="export_result",
                errors=[f"Session file does not exist: {session_file}"],
            )

        agent_type = self._detect_agent_from_file(session_file)
        messages = self._read_session_messages(session_file, agent_type)
        if messages is None:
            return CommandResult(
                success=False,
                data=None,
                data_type="export_result",
                errors=[f"Could not read messages from {session_file}"],
            )

        if export_format == EXPORT_FORMAT_HTML:
            rendered = self._render_html(
                jsonl_file=session_file,
                agent_type=agent_type,
                messages=messages,
                minimal=minimal,
            )
        else:
            rendered = self._render_markdown(
                jsonl_file=session_file,
                agent_type=agent_type,
                messages=messages,
                minimal=minimal,
                markdown_level=markdown_level,
            )
        sys.stdout.write(rendered)
        return CommandResult(success=True, data=None, data_type="export_result")

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
        export_format: str,
        markdown_level: int,
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
                export_format=export_format,
                markdown_level=markdown_level,
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
        export_format: str,
        markdown_level: int,
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
        jsonl_file = self._resolve_export_session_file(session, home, workspace, force)

        # Determine agent type
        agent_type = session.get("agent", get_default_backend_id())

        # Read messages
        messages = self._read_session_messages(jsonl_file, agent_type)
        if messages is None:
            raise ValueError(f"Could not read messages from {jsonl_file}")

        # Generate source tag from home
        source_tag = self._get_source_tag(home)

        # Build output path
        ws_output_path = self._get_workspace_output_path(output_dir, workspace_display, flat)

        if export_json:
            return self._write_ndjson_session_export(
                jsonl_file=jsonl_file,
                source_tag=source_tag,
                messages=messages,
                session=session,
                agent_type=agent_type,
                ws_output_path=ws_output_path,
                force=force,
                include_source=include_source,
                quiet=quiet,
            )

        # Handle markdown or HTML export
        output_name = self._build_output_filename(
            jsonl_file,
            source_tag,
            messages,
            extension=".html" if export_format == EXPORT_FORMAT_HTML else ".md",
        )
        output_file = ws_output_path / output_name

        # Check if export is up-to-date
        if not force and self._is_export_up_to_date(output_file, jsonl_file):
            return EXPORT_SKIPPED

        if export_format == EXPORT_FORMAT_HTML:
            if split_lines:
                raise ValueError("HTML export does not support --split")
            self._write_html_export(
                jsonl_file=jsonl_file,
                output_file=output_file,
                output_name=output_name,
                agent_type=agent_type,
                messages=messages,
                minimal=minimal,
                include_source=include_source,
                quiet=quiet,
                ws_output_path=ws_output_path,
            )
            return EXPORT_EXPORTED

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
            markdown_level=markdown_level,
        )

        return EXPORT_EXPORTED

    def _resolve_export_session_file(
        self,
        session: SessionDict,
        home: str,
        workspace: str,
        force: bool,
    ) -> Path:
        jsonl_file = session.get("file")
        if jsonl_file is None:
            raise ValueError("Session has no 'file' field")
        if isinstance(jsonl_file, str):
            jsonl_file = Path(jsonl_file)

        if not jsonl_file.exists() and home.startswith("remote:"):
            jsonl_file = self._resolve_remote_session_file(session, home, workspace) or jsonl_file

        if not jsonl_file.exists() and home == "web":
            jsonl_file = self._resolve_web_session_file(session, force)

        if not jsonl_file.exists():
            raise ValueError(f"Session file does not exist: {jsonl_file}")
        return jsonl_file

    def _resolve_remote_session_file(
        self, session: SessionDict, home: str, workspace: str
    ) -> Optional[Path]:
        from agent_history.adapters.remote import SSHRemoteClient

        remote_host = home[7:]
        client = SSHRemoteClient()
        return client.ensure_local_copy(remote_host, workspace, session)

    def _resolve_web_session_file(self, session: SessionDict, force: bool) -> Path:
        from agent_history.backends.web import (
            WebSessionsError,
            ensure_web_session_cache,
            resolve_web_credentials,
        )

        session_id = session.get("session_id") or session.get("id") or session.get("filename")
        if not session_id:
            raise ValueError("Web session missing identifier")
        try:
            token, org_uuid = resolve_web_credentials()
            return ensure_web_session_cache(str(session_id), token, org_uuid, force=force)
        except WebSessionsError as exc:
            raise ValueError(str(exc)) from exc

    def _write_ndjson_session_export(
        self,
        jsonl_file: Path,
        source_tag: str,
        messages: List[MessageDict],
        session: SessionDict,
        agent_type: str,
        ws_output_path: Path,
        force: bool,
        include_source: bool,
        quiet: bool,
    ) -> str:
        output_name = build_output_filename_ndjson(jsonl_file, source_tag, messages)
        output_file = ws_output_path / output_name

        if not force and self._is_export_up_to_date(output_file, jsonl_file):
            return EXPORT_SKIPPED

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
            backend = get_backend(agent_type)
            if backend is None:
                raise ValueError(f"Unsupported agent backend: {agent_type}")
            return backend.read_messages(jsonl_file)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            sys.stderr.write(f"Error reading {jsonl_file.name}: {e}\n")
            return None

    def _detect_agent_from_file(self, session_file: Path) -> str:
        """Infer agent type from a local session file path."""
        return infer_backend_from_file(session_file).id

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
        self,
        jsonl_file: Path,
        source_tag: str,
        messages: List[MessageDict],
        extension: str = ".md",
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
            return f"{source_tag}{ts_prefix}_{jsonl_file.stem}{extension}"
        return f"{source_tag}{jsonl_file.stem}{extension}"

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
        markdown_level: int = MARKDOWN_DEFAULT_LEVEL,
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
            parts = generate_markdown_parts(
                messages,
                jsonl_file,
                minimal,
                split_lines,
                markdown_level=markdown_level,
            )
            if parts:
                self._write_split_parts(parts, output_name, ws_output_path, quiet)
                # Copy source file if requested
                if include_source:
                    copy_source_file(jsonl_file, ws_output_path, quiet)
                return

        # Write single file
        markdown = self._render_markdown(
            jsonl_file=jsonl_file,
            agent_type=agent_type,
            messages=messages,
            minimal=minimal,
            markdown_level=markdown_level,
        )
        output_file.write_text(markdown, encoding="utf-8")
        if not quiet:
            print(output_file)

        # Copy source file if requested
        if include_source:
            copy_source_file(jsonl_file, ws_output_path, quiet)

    def _render_markdown(
        self,
        jsonl_file: Path,
        agent_type: str,
        messages: List[MessageDict],
        minimal: bool,
        markdown_level: int,
    ) -> str:
        """Render Markdown for a parsed session."""
        backend = get_backend(agent_type)
        if backend is None:
            raise ValueError(f"Unsupported agent backend: {agent_type}")
        return backend.render_markdown(jsonl_file, minimal, messages, markdown_level)

    def _write_html_timeline_index(
        self,
        tasks: List[_ExportTask],
        output_dir: Path,
        flat: bool,
        quiet: bool,
    ) -> None:
        """Write the HTML timeline entry point for the resolved export scope."""
        entries: List[Dict[str, Any]] = []
        for session, home, workspace, workspace_display in tasks:
            try:
                jsonl_file = self._resolve_export_session_file(
                    session=session,
                    home=home,
                    workspace=workspace,
                    force=False,
                )
                agent_type = str(session.get("agent", get_default_backend_id()))
                messages = self._read_session_messages(jsonl_file, agent_type)
                if messages is None:
                    continue

                source_tag = self._get_source_tag(home)
                ws_output_path = self._get_workspace_output_path(
                    output_dir, workspace_display, flat
                )
                output_name = self._build_output_filename(
                    jsonl_file,
                    source_tag,
                    messages,
                    extension=".html",
                )
                detail_file = ws_output_path / output_name
                if not detail_file.exists():
                    continue

                entries.append(
                    self._build_html_timeline_entry(
                        session=session,
                        jsonl_file=jsonl_file,
                        detail_file=detail_file,
                        output_dir=output_dir,
                        agent_type=agent_type,
                        messages=messages,
                        home=home,
                        workspace=workspace,
                        workspace_display=workspace_display,
                    )
                )
            except (OSError, ValueError):
                continue

        html = render_html_timeline_export(entries)
        index_file = output_dir / "index.html"
        index_file.write_text(html, encoding="utf-8")
        if not quiet:
            print(index_file)

    def _build_html_timeline_entry(
        self,
        session: SessionDict,
        jsonl_file: Path,
        detail_file: Path,
        output_dir: Path,
        agent_type: str,
        messages: List[MessageDict],
        home: str,
        workspace: str,
        workspace_display: str,
    ) -> Dict[str, Any]:
        start_dt, end_dt, timestamp_quality = self._timeline_time_range(jsonl_file, messages)
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = max(start_ms, int(end_dt.timestamp() * 1000))
        duration_seconds = max(0, int((end_ms - start_ms) / 1000))
        session_id = self._timeline_session_id(session, jsonl_file, messages)
        is_subagent = self._timeline_is_subagent(session, jsonl_file, messages)
        parent_session_id = self._timeline_first_value(
            messages,
            "parent_session_id",
            "parentSessionId",
        )
        if not parent_session_id and is_subagent:
            parent_session_id = self._timeline_first_value(messages, "sessionId", "session_id")
        parent_message_id = None
        if parent_session_id or is_subagent:
            parent_message_id = self._timeline_first_value(
                messages,
                "parent_id",
                "parentUuid",
                "parentId",
            )
        lineage_quality = "explicit" if parent_session_id or parent_message_id else "none"

        try:
            html_file = detail_file.relative_to(output_dir).as_posix()
        except ValueError:
            html_file = detail_file.name

        return {
            "id": session_id,
            "title": self._timeline_title(jsonl_file, messages),
            "agent": agent_type,
            "is_subagent": is_subagent,
            "parent_session_id": parent_session_id,
            "parent_message_id": parent_message_id,
            "lineage_quality": lineage_quality,
            "workspace": workspace,
            "workspace_display": workspace_display,
            "home": home,
            "source_file": str(jsonl_file),
            "html_file": html_file,
            "start": self._timeline_iso(start_dt),
            "end": self._timeline_iso(end_dt),
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_seconds": duration_seconds,
            "duration_label": self._timeline_duration_label(duration_seconds),
            "message_count": len(messages),
            "turn_count": self._timeline_turn_count(messages),
            "tool_call_count": sum(1 for message in messages if message.get("is_tool_call")),
            "timestamp_quality": timestamp_quality,
        }

    def _timeline_time_range(
        self, jsonl_file: Path, messages: List[MessageDict]
    ) -> Tuple[datetime, datetime, str]:
        timestamps = [
            parsed
            for message in messages
            if (parsed := self._timeline_parse_timestamp(message.get("timestamp")))
        ]
        if timestamps:
            return min(timestamps), max(timestamps), "message"

        fallback = datetime.fromtimestamp(jsonl_file.stat().st_mtime, timezone.utc)
        return fallback, fallback, "file_mtime"

    def _timeline_parse_timestamp(self, value: Any) -> Optional[datetime]:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value), timezone.utc)
            except (OSError, OverflowError, ValueError):
                return None
        text = str(value)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _timeline_session_id(
        self, session: SessionDict, jsonl_file: Path, messages: List[MessageDict]
    ) -> str:
        for value in (
            session.get("session_id"),
            session.get("id"),
            self._timeline_first_value(messages, "session_id", "sessionId"),
        ):
            if value:
                return str(value)
        return jsonl_file.stem

    def _timeline_title(self, jsonl_file: Path, messages: List[MessageDict]) -> str:
        for message in messages:
            if str(message.get("role") or "").lower() == "user" and message.get("content"):
                content = " ".join(str(message["content"]).split())
                if len(content) > 90:
                    content = content[:87].rstrip() + "..."
                return content
        return jsonl_file.stem

    def _timeline_is_subagent(
        self, session: SessionDict, jsonl_file: Path, messages: List[MessageDict]
    ) -> bool:
        if session.get("is_subagent"):
            return True
        if jsonl_file.name.startswith("agent-"):
            return True
        if any(message.get("isSidechain") for message in messages):
            return True
        if self._timeline_first_value(messages, "parent_session_id", "parentSessionId"):
            return True
        return False

    def _timeline_first_value(self, messages: List[MessageDict], *keys: str) -> Any:
        for message in messages:
            for key in keys:
                value = message.get(key)
                if value not in (None, ""):
                    return value
        return None

    def _timeline_turn_count(self, messages: List[MessageDict]) -> int:
        return sum(
            1
            for message in messages
            if str(message.get("role") or "").lower() == "user"
            and not message.get("is_tool_result")
        )

    def _timeline_iso(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _timeline_duration_label(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        if hours < 48:
            return f"{hours}h {minutes % 60}m"
        days = hours // 24
        return f"{days}d {hours % 24}h"

    def _write_html_export(
        self,
        jsonl_file: Path,
        output_file: Path,
        output_name: str,
        agent_type: str,
        messages: List[MessageDict],
        minimal: bool,
        include_source: bool,
        quiet: bool,
        ws_output_path: Path,
    ) -> None:
        """Write exported session to a single HTML file."""
        html = self._render_html(
            jsonl_file=jsonl_file,
            agent_type=agent_type,
            messages=messages,
            minimal=minimal,
            display_file=output_name,
        )
        output_file.write_text(html, encoding="utf-8")
        if not quiet:
            print(output_file)

        if include_source:
            copy_source_file(jsonl_file, ws_output_path, quiet)

    def _render_html(
        self,
        jsonl_file: Path,
        agent_type: str,
        messages: List[MessageDict],
        minimal: bool,
        display_file: Optional[str] = None,
    ) -> str:
        """Render HTML for a parsed session."""
        return render_html_export(
            jsonl_file=jsonl_file,
            agent_type=agent_type,
            messages=messages,
            minimal=minimal,
            display_file=display_file,
        )

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
