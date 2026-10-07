"""Codex CLI backend for cagelens.

This module provides functions for:
- Session scanning from ~/.codex/sessions/YYYY/MM/DD/
- JSONL message parsing (Codex envelope format)
- Session index management for efficient workspace lookups
- Workspace path handling
- Metrics extraction for stats database

Codex CLI stores sessions as JSONL files with a {timestamp, type, payload}
envelope structure. Sessions are organized in date folders (YYYY/MM/DD/).

Environment Variables:
    CODEX_HOME: Upstream Codex home directory; sessions live under sessions/
    CODEX_SESSIONS_DIR: Override sessions directory location (for testing/compat)
    DEBUG: Enable debug output for index operations
"""

from __future__ import annotations

import io
import json
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, TextIO, TypedDict

from agent_history.storage.config import get_config_dir
from agent_history.utils import progress
from agent_history.utils.codex_tokens import CodexTokenCounter, is_replayed
from agent_history.utils.jsonl import (
    TRANSCRIPT_ENCODING,
    TRANSCRIPT_ERRORS,
    dict_field,
    json_objects,
)
from agent_history.utils.paths import normalize_workspace_name
from agent_history.utils.session_identity import CodexSessionMeta

__all__ = [
    # Constants
    "AGENT_CODEX",
    "CODEX_DATE_FOLDER_DEPTH",
    "CODEX_HOME_DIR",
    "CODEX_INDEX_VERSION",
    "CODEX_TEXT_TYPES",
    "codex_count_messages",
    "codex_ensure_index_updated",
    "codex_extract_content",
    # Metrics extraction
    "codex_extract_metrics_from_jsonl",
    "codex_format_function_call",
    "codex_format_function_result",
    "codex_get_first_timestamp",
    # Session scanning
    "codex_get_home_dir",
    # Index management
    "codex_get_index_file",
    # Workspace handling
    "codex_get_workspace_from_session",
    "codex_get_workspace_readable",
    "codex_load_index",
    # Unified conversion
    "codex_message_to_unified",
    "codex_parse_jsonl_to_markdown",
    # Message parsing
    "codex_read_jsonl_messages",
    "codex_save_index",
    "codex_scan_sessions",
]


# =============================================================================
# Constants
# =============================================================================

AGENT_CODEX = "codex"

# Codex sessions directory (~/.codex/sessions/)
CODEX_HOME_DIR = Path.home() / ".codex" / "sessions"

# Text content types in Codex messages
CODEX_TEXT_TYPES = frozenset(["input_text", "output_text"])

# Depth of YYYY/MM/DD/file folder structure
CODEX_DATE_FOLDER_DEPTH = 4

# Index version - bump to rebuild index when format changes
CODEX_INDEX_VERSION = 3  # Raw cwd paths (not encoded)

# Regex for tool name extraction
_TOOL_NAME_PATTERN = re.compile(r"\*\*\[Tool:\s*([^\]]+)\]\*\*")
_SUBAGENT_NOTIFICATION_RE = re.compile(
    r"<subagent_notification>\s*(?P<body>.*?)\s*</subagent_notification>",
    re.DOTALL,
)


# =============================================================================
# TypedDicts for Metrics (Type Safety)
# =============================================================================


class SessionMetrics(TypedDict):
    """Session metadata in metrics dict."""

    id: str | None
    cwd: str | None
    cli_version: str | None
    model: str | None
    startTime: str | None
    lastUpdated: str | None


class TokensSummary(TypedDict, total=False):
    """Token summary for Codex sessions."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    timestamp: str | None


class MetricsDict(TypedDict, total=False):
    """Full metrics dictionary structure."""

    session: SessionMetrics
    messages: list[dict[str, Any]]
    tool_uses: list[dict[str, Any]]
    tokens_summary: TokensSummary


# =============================================================================
# Home Directory
# =============================================================================


def codex_get_home_dir() -> Path:
    """Get Codex sessions directory (~/.codex/sessions/).

    Supports upstream CODEX_HOME plus CODEX_SESSIONS_DIR for tests and
    cagelens compatibility. CODEX_SESSIONS_DIR wins because it points
    directly at the sessions root.
    """
    env_override = os.environ.get("CODEX_SESSIONS_DIR")
    if env_override:
        return Path(env_override).expanduser()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "sessions"
    return CODEX_HOME_DIR


# =============================================================================
# JSONL Parsing
# =============================================================================


class ZstandardMissingError(OSError):
    """A compressed rollout cannot be read because zstandard is not installed."""


@contextmanager
def _codex_open_text(
    jsonl_file: Path, encoding: str = "utf-8", errors: str = "strict"
) -> Iterator[TextIO]:
    """Open plain or zstd-compressed Codex rollout files as text."""
    if jsonl_file.name.endswith(".jsonl.zst"):
        try:
            import zstandard as zstd
        except ImportError as exc:
            raise ZstandardMissingError(
                "Reading .jsonl.zst Codex rollouts requires zstandard"
            ) from exc

        with open(jsonl_file, "rb") as raw:
            reader = zstd.ZstdDecompressor().stream_reader(raw)
            wrapper = io.TextIOWrapper(reader, encoding=encoding, errors=errors)
            try:
                yield wrapper
            finally:
                wrapper.detach()
                reader.close()
        return

    with open(jsonl_file, encoding=encoding, errors=errors) as f:
        yield f


@contextmanager
def _codex_open_entries(jsonl_file: Path) -> Iterator[Iterator[dict[str, Any]]]:
    """The JSON-object lines of a rollout; a bad byte decodes as U+FFFD."""
    with _codex_open_text(
        jsonl_file, encoding=TRANSCRIPT_ENCODING, errors=TRANSCRIPT_ERRORS
    ) as handle:
        yield json_objects(handle)


def codex_extract_content(payload: dict) -> str:
    """Extract text content from Codex message payload.

    Codex messages have content as either a string or an array of objects
    with type "input_text" (user) or "output_text" (assistant).

    Args:
        payload: The message payload dict containing content field

    Returns:
        Extracted text content as a string
    """
    content = payload.get("content", [])
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") in CODEX_TEXT_TYPES:
            parts.append(item.get("text", ""))
    return "\n".join(parts)


def codex_format_function_call(payload: dict) -> str:
    """Format a Codex function_call payload as markdown.

    Args:
        payload: The function_call payload dict

    Returns:
        Formatted markdown string for the tool call
    """
    name = payload.get("name", "unknown")
    args = payload.get("arguments", "{}")
    call_id = payload.get("call_id", "")
    return f"**[Tool: {name}]**\nCall ID: `{call_id}`\n```json\n{args}\n```"


def codex_format_function_result(payload: dict) -> str:
    """Format a Codex function_call_output payload as markdown.

    Args:
        payload: The function_call_output payload dict

    Returns:
        Formatted markdown string for the tool result
    """
    call_id = payload.get("call_id", "")
    output = payload.get("output", "")
    return f"**[Tool Result]**\nCall ID: `{call_id}`\n```\n{output}\n```"


def _codex_parse_subagent_notification(content: str) -> dict[str, Any] | None:
    match = _SUBAGENT_NOTIFICATION_RE.search(str(content or ""))
    if not match:
        return None
    try:
        data = json.loads(match.group("body"))
    except (json.JSONDecodeError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _codex_format_subagent_notification(data: dict[str, Any]) -> str:
    agent_path = str(data.get("agent_path") or data.get("agent_id") or "unknown")
    status = data.get("status") if isinstance(data.get("status"), dict) else {}
    state = next((key for key in ("completed", "failed", "cancelled") if key in status), "updated")
    details = status.get(state)
    if isinstance(details, (dict, list)):
        details = json.dumps(details, indent=2, ensure_ascii=False)
    lines = [
        f"**Sub-agent {state}**",
        f"Agent path: `{agent_path}`",
    ]
    if details:
        lines.extend(["", str(details)])
    return "\n".join(lines)


def _codex_subagent_notification_fields(content: str) -> dict[str, Any]:
    notification = _codex_parse_subagent_notification(content)
    if not notification:
        return {}
    status = notification.get("status") if isinstance(notification.get("status"), dict) else {}
    state = next((key for key in ("completed", "failed", "cancelled") if key in status), "updated")
    return {
        "role": "system",
        "content": _codex_format_subagent_notification(notification),
        "is_subagent_notification": True,
        "subagent_agent_path": notification.get("agent_path"),
        "subagent_status": state,
    }


def _codex_get_present(mapping: dict[str, Any], *keys: str) -> Any:
    """Return the first value for a key present in mapping, including None."""
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _codex_has_any(mapping: dict[str, Any], *keys: str) -> bool:
    """Return whether any key is present in mapping."""
    return any(key in mapping for key in keys)


def _codex_session_linkage(identity: CodexSessionMeta) -> dict[str, Any]:
    """Session-level linkage that every message of a rollout carries.

    ``CodexSessionMeta`` names the parent as the stats reader does: from
    the first session_meta's parent fields or spawn source, or else from a
    later session_meta that repeats the parent's.
    """
    payload = identity.payload or {}
    linkage = {
        "session_id": identity.session_id,
        "parent_session_id": identity.parent_session_id,
        "forked_from_id": payload.get("forked_from_id"),
        "thread_source": payload.get("thread_source"),
    }
    return {key: value for key, value in linkage.items() if value}


def _codex_record_linkage(
    entry: dict[str, Any],
    payload: dict[str, Any],
    current_turn_id: str | None,
) -> dict[str, Any]:
    """Extract optional Codex linkage metadata from a rollout record."""
    linkage: dict[str, Any] = {}

    if _codex_has_any(payload, "id"):
        linkage["id"] = payload.get("id")
    elif _codex_has_any(entry, "id"):
        linkage["id"] = entry.get("id")

    if _codex_has_any(payload, "parent_id", "parentId"):
        linkage["parent_id"] = _codex_get_present(payload, "parent_id", "parentId")
    elif _codex_has_any(entry, "parent_id", "parentId"):
        linkage["parent_id"] = _codex_get_present(entry, "parent_id", "parentId")

    turn_id = (
        _codex_get_present(payload, "turn_id", "turnId")
        if _codex_has_any(payload, "turn_id", "turnId")
        else current_turn_id
    )
    if turn_id:
        linkage["turn_id"] = turn_id

    return linkage


def codex_read_jsonl_messages(jsonl_file: Path) -> tuple:
    """Read messages from Codex rollout JSONL file.

    Parses the Codex JSONL format which uses a {timestamp, type, payload}
    envelope structure. Extracts session metadata and all messages including
    function calls and results.

    Args:
        jsonl_file: Path to the Codex rollout .jsonl file

    Returns:
        Tuple of (messages_list, session_meta_dict or None)
        Messages contain: role, content, timestamp, and optionally
        is_tool_call or is_tool_result flags
    """
    messages = []
    identity = CodexSessionMeta()
    current_turn_id = None

    try:
        with _codex_open_entries(jsonl_file) as entries:
            for entry in entries:
                entry_type = entry.get("type")
                payload = dict_field(entry, "payload")
                if entry_type == "session_meta":
                    # The first session_meta describes the rollout; a
                    # sub-agent later repeats its parent's
                    identity.add(payload)
                elif entry_type in ("turn_context", "event_msg"):
                    current_turn_id = _codex_turn_id(entry_type, payload) or current_turn_id
                elif entry_type == "response_item":
                    linkage = _codex_record_linkage(entry, payload, current_turn_id)
                    message = _codex_response_message(entry, payload, linkage, identity)
                    if message is not None:
                        messages.append(message)
    except OSError:
        return [], None

    # The parent can be named after the first messages, so the session's
    # linkage is added once the whole rollout is read
    session_linkage = _codex_session_linkage(identity)
    for message in messages:
        message.update(session_linkage)
    return messages, identity.payload


def _codex_turn_id(entry_type: str, payload: dict[str, Any]) -> Any:
    """Turn ID that a turn_context or a turn-start event opens, if any."""
    if entry_type == "turn_context":
        return payload.get("turn_id")
    if payload.get("type") in ("task_started", "turn_started"):
        return payload.get("turn_id")
    return None


def _codex_response_message(
    entry: dict[str, Any],
    payload: dict[str, Any],
    linkage: dict[str, Any],
    identity: CodexSessionMeta,
) -> dict[str, Any] | None:
    """Message for one response_item: a message, a tool call or a tool result."""
    payload_type = payload.get("type")
    timestamp = entry.get("timestamp", "")
    if payload_type == "message":
        content = codex_extract_content(payload)
        role = payload.get("role")
        parent_agent_fields = (
            {"is_parent_agent_message": True} if role == "user" and identity.is_subagent else {}
        )
        return {
            "role": role,
            "content": content,
            "timestamp": timestamp,
            **linkage,
            **parent_agent_fields,
            **_codex_subagent_notification_fields(content),
        }
    if payload_type in ("function_call", "custom_tool_call"):
        return {
            "role": "assistant",
            "content": codex_format_function_call(payload),
            "timestamp": timestamp,
            "is_tool_call": True,
            "tool_call_id": payload.get("call_id"),
            **linkage,
        }
    if payload_type in ("function_call_output", "custom_tool_call_output"):
        return {
            "role": "tool",
            "content": codex_format_function_result(payload),
            "timestamp": timestamp,
            "is_tool_result": True,
            "tool_call_id": payload.get("call_id"),
            **linkage,
        }
    return None


def _codex_first_entry(jsonl_file: Path) -> dict[str, Any] | None:
    """The first JSON-object line of a rollout, or None."""
    try:
        with _codex_open_entries(jsonl_file) as entries:
            return next(entries, None)
    except OSError:
        return None


def codex_get_first_timestamp(jsonl_file: Path) -> str | None:
    """Get timestamp from Codex session's session_meta line.

    Args:
        jsonl_file: Path to the Codex rollout .jsonl file

    Returns:
        ISO 8601 timestamp string or None if not found
    """
    entry = _codex_first_entry(jsonl_file)
    if entry is not None and entry.get("type") == "session_meta":
        return entry.get("timestamp", "")
    return None


def codex_parse_jsonl_to_markdown(jsonl_file: Path, minimal: bool = False) -> str:
    """Convert Codex rollout JSONL to markdown format.

    Args:
        jsonl_file: Path to the Codex rollout .jsonl file
        minimal: If True, omit metadata sections

    Returns:
        Markdown formatted string of the conversation
    """
    messages, session_meta = codex_read_jsonl_messages(jsonl_file)

    md_lines = ["# Codex Conversation", ""]

    if session_meta and not minimal:
        md_lines.extend(
            [
                "## Session Metadata",
                "",
                f"- **Session ID:** `{session_meta.get('id', 'unknown')}`",
                f"- **Working Directory:** `{session_meta.get('cwd', 'unknown')}`",
                f"- **CLI Version:** `{session_meta.get('cli_version', 'unknown')}`",
                f"- **Source:** `{session_meta.get('source', 'unknown')}`",
                "",
            ]
        )

    md_lines.extend(["---", ""])

    for i, msg in enumerate(messages, 1):
        role = str(msg.get("role") or "unknown")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")

        if role == "user":
            md_lines.append(f"## User (Message {i})")
        elif role == "assistant":
            if msg.get("is_tool_call"):
                md_lines.append(f"## Tool Call (Message {i})")
            else:
                md_lines.append(f"## Assistant (Message {i})")
        elif role == "tool":
            md_lines.append(f"## Tool Result (Message {i})")
        else:
            md_lines.append(f"## {role.title()} (Message {i})")

        if timestamp and not minimal:
            md_lines.append(f"*{timestamp}*")

        md_lines.extend(["", content, "", "---", ""])

    return "\n".join(md_lines)


def _extract_tool_name_from_content(content: str) -> str:
    """Extract tool name from formatted tool call content.

    Args:
        content: Formatted content string like "**[Tool: Bash]**..."

    Returns:
        Tool name or "unknown" if not found
    """
    match = _TOOL_NAME_PATTERN.search(content)
    return match.group(1).strip() if match else "unknown"


def codex_extract_metrics_from_jsonl(jsonl_file: Path) -> MetricsDict:
    """Extract metrics from Codex JSONL file for stats database.

    Mirror of extract_metrics_from_jsonl() for Codex format.

    Args:
        jsonl_file: Path to the Codex rollout .jsonl file

    Returns:
        Dict with session, messages, and tool_uses data
    """
    messages, session_meta = codex_read_jsonl_messages(jsonl_file)

    session: SessionMetrics = {
        "id": session_meta.get("id") if session_meta else None,
        "cwd": session_meta.get("cwd") if session_meta else None,
        "cli_version": session_meta.get("cli_version") if session_meta else None,
        "model": None,
        "startTime": None,
        "lastUpdated": None,
    }
    metrics: MetricsDict = {
        "session": session,
        "messages": [],
        "tool_uses": [],
    }

    # Extract model and per-response token usage from the event stream.
    token_counter = CodexTokenCounter()
    last_token_timestamp = None
    history_start = (session_meta or {}).get("subagent_history_start_ordinal")
    try:
        with _codex_open_entries(jsonl_file) as entries:
            for entry in entries:
                entry_type = entry.get("type")
                payload = dict_field(entry, "payload")

                if entry_type == "turn_context" and not metrics["session"]["model"]:
                    metrics["session"]["model"] = payload.get("model")
                    continue

                if entry_type == "event_msg" and payload.get("type") == "token_count":
                    replayed = is_replayed(entry, history_start)
                    if (
                        token_counter.add(dict_field(payload, "info"), replayed=replayed)
                        is not None
                    ):
                        last_token_timestamp = entry.get("timestamp")
    except OSError:
        pass

    if last_token_timestamp is not None:
        metrics["tokens_summary"] = {
            "input_tokens": token_counter.input_tokens,
            "output_tokens": token_counter.output_tokens,
            "cache_read_tokens": token_counter.cache_read_tokens,
            "timestamp": last_token_timestamp,
        }

    for msg in messages:
        if msg.get("is_tool_call"):
            # Extract tool name using regex
            content = msg.get("content", "")
            tool_name = _extract_tool_name_from_content(content)
            metrics["tool_uses"].append(
                {
                    "name": tool_name,
                    "timestamp": msg.get("timestamp"),
                }
            )
        elif not msg.get("is_tool_result"):
            metrics["messages"].append(
                {
                    "role": msg.get("role"),
                    "timestamp": msg.get("timestamp"),
                }
            )

    return metrics


# =============================================================================
# Session Scanning
# =============================================================================


def codex_get_workspace_from_session(jsonl_file: Path) -> str:
    """Extract workspace (cwd) from Codex session's session_meta.

    Args:
        jsonl_file: Path to the Codex rollout .jsonl file

    Returns:
        Workspace path from session_meta.cwd (e.g., '/home/user/project') or 'unknown'
    """
    entry = _codex_first_entry(jsonl_file)
    if entry is not None and entry.get("type") == "session_meta":
        cwd = dict_field(entry, "payload").get("cwd")
        if cwd and isinstance(cwd, str):
            return cwd
    return "unknown"


def codex_get_workspace_readable(workspace: str) -> str:
    """Convert a Codex workspace identifier to a readable path string."""
    if not workspace:
        return ""
    # Raw paths are already readable; fall back to decoding if an encoded workspace leaks in.
    if workspace.startswith("-") or workspace.startswith("home-") or workspace.startswith("mnt-"):
        return normalize_workspace_name(workspace, verify_local=False)
    return workspace


def codex_count_messages(jsonl_file: Path) -> int:
    """Count user/assistant messages in a Codex session.

    Args:
        jsonl_file: Path to the Codex rollout .jsonl file

    Returns:
        Number of user and assistant messages (excluding tool calls/results)
    """
    count = 0
    try:
        with _codex_open_entries(jsonl_file) as entries:
            for entry in entries:
                if (
                    entry.get("type") == "response_item"
                    and dict_field(entry, "payload").get("type") == "message"
                ):
                    count += 1
    except OSError:
        pass
    return count


# =============================================================================
# Session Index Management
# =============================================================================


def codex_get_index_file() -> Path:
    """Get path to Codex session index file (~/.cagelens/codex_index.json)."""
    return get_config_dir() / "codex_index.json"


def codex_load_index() -> dict[str, Any]:
    """Load Codex session index from file.

    Returns:
        Index dict with keys: version, last_scan_date, sessions
        sessions maps session file path (str) to encoded workspace name.
        Returns empty index if file doesn't exist or is invalid.
    """
    index_file = codex_get_index_file()
    default_index: dict[str, Any] = {
        "version": CODEX_INDEX_VERSION,
        "last_scan_date": None,
        "sessions": {},
    }

    if not index_file.exists():
        return default_index

    try:
        with open(index_file, encoding="utf-8") as f:
            data = json.load(f)

            # Version mismatch requires rebuild
            if data.get("version") != CODEX_INDEX_VERSION:
                if os.environ.get("DEBUG"):
                    sys.stderr.write(
                        f"Codex index version mismatch: "
                        f"expected {CODEX_INDEX_VERSION}, got {data.get('version')}\n"
                    )
                return default_index

            return data

    except OSError as e:
        if os.environ.get("DEBUG"):
            sys.stderr.write(f"Cannot read Codex index {index_file}: {e}\n")
    except json.JSONDecodeError as e:
        if os.environ.get("DEBUG"):
            sys.stderr.write(f"Invalid JSON in Codex index {index_file}: {e}\n")

    return default_index


def codex_save_index(index: dict) -> None:
    """Save Codex session index to file."""
    index_file = codex_get_index_file()
    try:
        index_file.parent.mkdir(parents=True, exist_ok=True)
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
    except OSError as e:
        if os.environ.get("DEBUG"):
            sys.stderr.write(f"Cannot write Codex index {index_file}: {e}\n")


def _codex_parse_date_folder(folder_path: Path) -> str:
    """Parse YYYY/MM/DD folder structure to date string.

    Args:
        folder_path: Path like .../2025/12/15/rollout-xxx.jsonl

    Returns:
        Date string like "2025-12-15" or empty string if invalid
    """
    try:
        parts = folder_path.parts
        # Find YYYY/MM/DD pattern in path (last 4 parts before filename)
        if len(parts) >= CODEX_DATE_FOLDER_DEPTH:
            year, month, day = parts[-4], parts[-3], parts[-2]
            if year.isdigit() and month.isdigit() and day.isdigit():
                return f"{year}-{month}-{day}"
    except (ValueError, IndexError):
        pass
    return ""


def _iter_numeric_subdirs(parent: Path):
    """Iterate sorted numeric subdirectories of a parent directory."""
    try:
        entries = list(parent.iterdir())
    except (OSError, PermissionError):
        return
    for child in sorted(entries):
        try:
            if child.is_dir() and child.name.isdigit():
                yield child
        except (OSError, PermissionError):
            continue


def _is_date_before_cutoff(year: int, month: int, day: int, cutoff) -> bool:
    """Check if date is before cutoff date.

    Args:
        year: Year component
        month: Month component
        day: Day component
        cutoff: Cutoff datetime or date (or None)

    Returns:
        True if the date is before cutoff
    """
    if not cutoff:
        return False
    from datetime import date as date_type

    folder_date = date_type(year, month, day)
    since = cutoff.date() if hasattr(cutoff, "date") else cutoff
    return folder_date < since


def _iter_day_folders(month_dir: Path, year: int, month: int, since_dt):
    """Generate day folders within a month, filtering by since_dt."""
    for day_dir in _iter_numeric_subdirs(month_dir):
        day = int(day_dir.name)
        if not _is_date_before_cutoff(year, month, day, since_dt):
            yield day_dir


def _iter_month_folders(year_dir: Path, year: int, since_dt):
    """Generate month folders within a year, filtering by since_dt."""
    for month_dir in _iter_numeric_subdirs(year_dir):
        month = int(month_dir.name)
        if since_dt and year == since_dt.year and month < since_dt.month:
            continue
        yield from _iter_day_folders(month_dir, year, month, since_dt)


def _iter_date_folders(sessions_dir: Path, since_dt):
    """Generate date folder paths, filtering by since_dt."""
    for year_dir in _iter_numeric_subdirs(sessions_dir):
        year = int(year_dir.name)
        if since_dt and year < since_dt.year:
            continue
        yield from _iter_month_folders(year_dir, year, since_dt)


def _codex_rollout_candidates(folder: Path) -> list[Path]:
    """Return plain and compressed Codex rollout files in a folder."""
    return list(folder.glob("rollout-*.jsonl")) + list(folder.glob("rollout-*.jsonl.zst"))


def _codex_date_folders_since(sessions_dir: Path, since_date: str | None) -> list:
    """Get list of date folders on or after since_date.

    Args:
        sessions_dir: Base sessions directory (~/.codex/sessions/)
        since_date: Date string "YYYY-MM-DD" to start from (inclusive)

    Returns:
        List of Path objects for YYYY/MM/DD folders to scan
    """
    try:
        if not sessions_dir.exists():
            return []
    except (OSError, PermissionError):
        return []

    since_dt = datetime.strptime(since_date, "%Y-%m-%d") if since_date else None
    return list(_iter_date_folders(sessions_dir, since_dt))


def _remove_stale_entries(sessions_map: dict, prefix: str = "") -> int:
    """Remove entries for files that no longer exist.

    Args:
        sessions_map: Dict mapping file paths to workspace names
        prefix: Only check entries whose path starts with this folder

    Returns:
        Number of stale entries removed
    """
    stale_keys = []
    for key in sessions_map:
        if prefix and not key.startswith(prefix.rstrip("/\\") + os.sep):
            continue
        try:
            if not Path(key).exists():
                stale_keys.append(key)
        except (OSError, PermissionError):
            stale_keys.append(key)
    for k in stale_keys:
        del sessions_map[k]
    return len(stale_keys)


def _scan_folders_for_sessions(
    folders: list[Path],
    existing_sessions: dict[str, str],
) -> dict[str, str]:
    """Scan folders and add new sessions to the map.

    Args:
        folders: List of date folders to scan
        existing_sessions: Current session->workspace mapping

    Returns:
        Updated session mapping (modifies in place and returns for chaining)
    """
    for day_dir in folders:
        try:
            candidates = _codex_rollout_candidates(day_dir)
        except (OSError, PermissionError):
            continue
        for jsonl_file in candidates:
            file_key = str(jsonl_file)
            if file_key not in existing_sessions:
                try:
                    workspace = codex_get_workspace_from_session(jsonl_file)
                except (OSError, PermissionError):
                    continue
                existing_sessions[file_key] = workspace
    return existing_sessions


# Index maps already brought up to date in this process, by (index file,
# sessions folder). Listing asks once per workspace; checking every indexed
# file again each time cost a network round trip per file on /mnt/c.
_REFRESHED_INDEXES: dict[tuple[str, str], dict[str, str]] = {}


def codex_ensure_index_updated(sessions_dir: Path | None = None) -> dict[str, str]:
    """Ensure Codex session index is up-to-date.

    Performs incremental indexing: only scans date folders since last update.

    Args:
        sessions_dir: Override sessions directory (for testing)

    Returns:
        Dict mapping session file paths (str) to encoded workspace names
    """
    sessions_dir = sessions_dir or codex_get_home_dir()

    try:
        if not sessions_dir.exists():
            return {}
    except (OSError, PermissionError):
        return {}

    dir_key = str(sessions_dir)
    memo_key = (str(codex_get_index_file()), dir_key)
    if memo_key in _REFRESHED_INDEXES:
        return _REFRESHED_INDEXES[memo_key]

    index = codex_load_index()
    sessions_map = index.get("sessions", {})

    # Each sessions folder (local, Windows, WSL, ...) keeps its own scan
    # date, so scanning one folder never makes another look up to date.
    scan_dates = index.setdefault("last_scan_dates", {})
    since = scan_dates.get(dir_key)
    if since is None and sessions_dir == codex_get_home_dir():
        since = index.get("last_scan_date")

    # Clean up deleted files in this folder only
    _remove_stale_entries(sessions_map, prefix=dir_key)

    # Incremental scan from last scan date (or full scan if first run)
    try:
        folders = _codex_date_folders_since(sessions_dir, since)
    except (OSError, PermissionError):
        return sessions_map
    _scan_folders_for_sessions(folders, sessions_map)

    # Save updated index
    index["sessions"] = sessions_map
    scan_dates[dir_key] = datetime.now().strftime("%Y-%m-%d")
    codex_save_index(index)
    _REFRESHED_INDEXES[memo_key] = sessions_map

    return sessions_map


# =============================================================================
# Metrics DB Cache (for message counts)
# =============================================================================


def _get_metrics_db_path() -> Path:
    """Get the metrics database file path."""
    return get_config_dir() / "metrics.db"


def _get_cached_message_count(jsonl_file: Path, current_mtime: float) -> int | None:
    """Return cached message count from metrics DB if mtime matches."""
    db_path = _get_metrics_db_path()
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=1.0)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT message_count, file_mtime FROM sessions WHERE file_path = ?",
            (str(jsonl_file),),
        ).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    file_mtime = row["file_mtime"]
    if file_mtime is None or file_mtime < current_mtime:
        return None
    return row["message_count"]


# =============================================================================
# Session Filtering
# =============================================================================


def _is_date_in_range(
    dt: datetime | None,
    since_date: datetime | None,
    until_date: datetime | None,
) -> bool:
    """Check if datetime is within date range (inclusive).

    Args:
        dt: datetime object to check
        since_date: Start date filter (datetime or None)
        until_date: End date filter (datetime or None)

    Returns:
        True if dt is within range, False otherwise.
    """
    if dt is None:
        return True
    check_date = dt.date() if hasattr(dt, "date") else dt
    if since_date:
        since = since_date.date() if hasattr(since_date, "date") else since_date
        if check_date < since:
            return False
    if until_date:
        until = until_date.date() if hasattr(until_date, "date") else until_date
        if check_date > until:
            return False
    return True


def _matches_workspace_pattern(
    workspace: str,
    pattern: str,
    get_readable: Callable[[str], str] | None = None,
) -> bool:
    """Check if workspace matches pattern (case-insensitive substring match).

    Args:
        workspace: Workspace identifier
        pattern: Pattern to match (empty matches all)
        get_readable: Optional function to get human-readable workspace name

    Returns:
        True if workspace matches pattern
    """
    # Empty pattern matches all
    if not pattern or pattern in ("", "*", "all"):
        return True

    # Scope resolution passes canonical keys (C:\\a becomes /mnt/c/a), while
    # Codex on native Windows records C:\\ paths; compare in key form too.
    from agent_history.utils.workspace_ref import build_workspace_ref

    pattern_key = build_workspace_ref(pattern).key.lower()
    if pattern_key and pattern_key in build_workspace_ref(workspace).key.lower():
        return True

    workspace_lower = workspace.lower()
    readable_lower = get_readable(workspace).lower() if get_readable else None

    # Normalize pattern for matching
    normalized_pattern = pattern.lower().strip("/")

    # Check exact match or substring match
    if normalized_pattern in workspace_lower:
        return True
    if readable_lower and normalized_pattern in readable_lower:
        return True

    # Check path-style pattern (e.g., "home/user" matches "-home-user-project")
    pattern_as_path = "/" + normalized_pattern.replace("-", "/")
    return pattern_as_path in (readable_lower or workspace_lower)


def _session_matches_filters(
    workspace: str,
    modified: datetime,
    pattern: str,
    since_date: datetime | None,
    until_date: datetime | None,
    get_readable: Callable[[str], str] | None = None,
) -> bool:
    """Check if session matches all filters.

    Args:
        workspace: Workspace identifier
        modified: Session modification datetime
        pattern: Workspace pattern to match
        since_date: Start date filter (inclusive)
        until_date: End date filter (inclusive)
        get_readable: Optional function to get human-readable workspace name

    Returns:
        True if session matches all filters
    """
    if not _matches_workspace_pattern(workspace, pattern, get_readable):
        return False
    return _is_date_in_range(modified, since_date, until_date)


def _codex_session_matches_filters(
    workspace: str,
    modified: datetime,
    pattern: str,
    since_date: datetime | None,
    until_date: datetime | None,
) -> bool:
    """Check if a Codex session matches the given filters.

    Uses shared _session_matches_filters for DRY implementation.
    """
    return _session_matches_filters(
        workspace,
        modified,
        pattern,
        since_date,
        until_date,
        get_readable=codex_get_workspace_readable,
    )


# =============================================================================
# Session Building
# =============================================================================


def _codex_build_session_dict(
    jsonl_file: Path,
    workspace: str,
    modified: datetime,
    skip_message_count: bool,
    use_cached_counts: bool = False,
) -> dict:
    """Build a session dictionary for a Codex session file."""
    message_count = 0
    if not skip_message_count:
        cached = None
        if use_cached_counts:
            cached = _get_cached_message_count(jsonl_file, modified.timestamp())
        message_count = cached if cached is not None else codex_count_messages(jsonl_file)
    return {
        "agent": AGENT_CODEX,
        "workspace": workspace,
        "workspace_readable": codex_get_workspace_readable(workspace),
        "file": jsonl_file,
        "filename": jsonl_file.name,
        "message_count": message_count,
        "message_count_skipped": skip_message_count,
        "modified": modified,
        "source": "local",
    }


def codex_scan_sessions(
    pattern: str = "",
    since_date=None,
    until_date=None,
    sessions_dir: Path | None = None,
    skip_message_count: bool = False,
    use_cached_counts: bool = False,
) -> list:
    """Scan ~/.codex/sessions/YYYY/MM/DD/ for rollout-*.jsonl files.

    Uses incremental indexing for efficient workspace lookups. The index maps
    session files to workspaces and is updated incrementally based on date folders.

    Args:
        pattern: Substring pattern to filter workspaces (empty matches all)
        since_date: Only include sessions modified on or after this date
        until_date: Only include sessions modified on or before this date
        sessions_dir: Override sessions directory (for testing)
        skip_message_count: If True, skip counting messages (set to 0)
        use_cached_counts: If True, use cached message counts from metrics DB

    Returns:
        List of session dicts sorted by modified time (newest first)
    """
    if sessions_dir is None:
        sessions_dir = codex_get_home_dir()

    if not sessions_dir.exists():
        return []

    # Get workspace mapping from incremental index
    sessions_map = codex_ensure_index_updated(sessions_dir)

    sessions = []
    if pattern and pattern not in ("", "*", "all"):
        candidates = [
            Path(file_key)
            for file_key, workspace in sessions_map.items()
            if workspace
            and _matches_workspace_pattern(workspace, pattern, codex_get_workspace_readable)
        ]
    else:
        # Walk through YYYY/MM/DD structure using glob
        try:
            candidates = list(sessions_dir.glob("*/*/*/rollout-*.jsonl")) + list(
                sessions_dir.glob("*/*/*/rollout-*.jsonl.zst")
            )
        except (OSError, PermissionError):
            return []

    for jsonl_file in candidates:
        file_key = str(jsonl_file)
        progress.add("codex_files_checked")
        # Look up workspace from index (fallback to file read if not in index or empty)
        workspace = sessions_map.get(file_key)
        if not workspace:  # None or empty string
            progress.add("codex_files_opened")
            try:
                workspace = codex_get_workspace_from_session(jsonl_file)
            except (OSError, PermissionError):
                continue
            # Update index with recomputed workspace if we had to fall back
            if workspace and file_key in sessions_map:
                sessions_map[file_key] = workspace

        try:
            modified = datetime.fromtimestamp(jsonl_file.stat().st_mtime)
        except (OSError, PermissionError):
            continue

        if _codex_session_matches_filters(workspace, modified, pattern, since_date, until_date):
            sessions.append(
                _codex_build_session_dict(
                    jsonl_file,
                    workspace,
                    modified,
                    skip_message_count,
                    use_cached_counts=use_cached_counts,
                )
            )

    return sorted(sessions, key=lambda s: s["modified"], reverse=True)


# =============================================================================
# Unified NDJSON Conversion
# =============================================================================


def _normalize_role(role: str) -> str:
    """Normalize role names to unified schema.

    Converts agent-specific role names to unified roles:
    - tool -> system (tool results are system-level)

    Args:
        role: Original role from agent format

    Returns:
        Normalized role: "user", "assistant", or "system"
    """
    if role == "tool":
        return "system"
    if role in ("user", "assistant", "system"):
        return role
    # System-level types (info, error, warning)
    if role in ("info", "error", "warning"):
        return "system"
    return role


def codex_message_to_unified(msg: dict) -> dict:
    """Convert Codex message to unified NDJSON schema.

    Args:
        msg: Codex message dict from codex_read_jsonl_messages

    Returns:
        Unified schema dict with timestamp, role, content, and optional fields
    """
    unified = {
        "timestamp": msg.get("timestamp", ""),
        "role": _normalize_role(msg.get("role", "user")),
        "content": msg.get("content", ""),
    }

    # Tool call handling - Codex stores these in content as formatted text
    if msg.get("is_tool_call"):
        # Parse the formatted tool call content for structured data
        unified["role"] = "assistant"
        if msg.get("tool_call_id"):
            unified["tool_call_id"] = msg["tool_call_id"]
    elif msg.get("is_tool_result"):
        unified["role"] = "system"
        if msg.get("tool_call_id"):
            unified["tool_result"] = {"tool_call_id": msg["tool_call_id"]}

    for field in (
        "id",
        "parent_id",
        "turn_id",
        "session_id",
        "parent_session_id",
        "forked_from_id",
        "thread_source",
    ):
        if field in msg:
            unified[field] = msg[field]

    return unified
