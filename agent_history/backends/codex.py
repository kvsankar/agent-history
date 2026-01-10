"""Codex CLI backend for agent-history.

This module provides functions for:
- Session scanning from ~/.codex/sessions/YYYY/MM/DD/
- JSONL message parsing (Codex envelope format)
- Session index management for efficient workspace lookups
- Workspace path handling
- Metrics extraction for stats database

Codex CLI stores sessions as JSONL files with a {timestamp, type, payload}
envelope structure. Sessions are organized in date folders (YYYY/MM/DD/).

Environment Variables:
    CODEX_SESSIONS_DIR: Override sessions directory location (for testing)
    DEBUG: Enable debug output for index operations
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, TypedDict

from agent_history.storage.config import get_config_dir
from agent_history.utils.paths import normalize_workspace_name

__all__ = [
    # Constants
    "AGENT_CODEX",
    "CODEX_HOME_DIR",
    "CODEX_TEXT_TYPES",
    "CODEX_DATE_FOLDER_DEPTH",
    "CODEX_INDEX_VERSION",
    # Session scanning
    "codex_get_home_dir",
    "codex_scan_sessions",
    "codex_ensure_index_updated",
    # Message parsing
    "codex_read_jsonl_messages",
    "codex_extract_content",
    "codex_format_function_call",
    "codex_format_function_result",
    "codex_parse_jsonl_to_markdown",
    "codex_get_first_timestamp",
    "codex_count_messages",
    # Workspace handling
    "codex_get_workspace_from_session",
    "codex_get_workspace_readable",
    # Index management
    "codex_get_index_file",
    "codex_load_index",
    "codex_save_index",
    # Metrics extraction
    "codex_extract_metrics_from_jsonl",
    # Unified conversion
    "codex_message_to_unified",
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


# =============================================================================
# TypedDicts for Metrics (Type Safety)
# =============================================================================


class SessionMetrics(TypedDict):
    """Session metadata in metrics dict."""

    id: Optional[str]
    cwd: Optional[str]
    cli_version: Optional[str]
    model: Optional[str]
    startTime: Optional[str]
    lastUpdated: Optional[str]


class TokensSummary(TypedDict, total=False):
    """Token summary for Codex sessions."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    timestamp: Optional[str]


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

    Supports CODEX_SESSIONS_DIR environment variable override for testing
    and custom configurations.
    """
    env_override = os.environ.get("CODEX_SESSIONS_DIR")
    if env_override:
        return Path(env_override).expanduser()
    return CODEX_HOME_DIR


# =============================================================================
# JSONL Parsing
# =============================================================================


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
    session_meta = None

    with open(jsonl_file, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                entry_type = entry.get("type")
                timestamp = entry.get("timestamp", "")
                payload = entry.get("payload", {})

                if entry_type == "session_meta":
                    session_meta = payload
                elif entry_type == "response_item":
                    payload_type = payload.get("type")
                    if payload_type == "message":
                        messages.append(
                            {
                                "role": payload.get("role"),
                                "content": codex_extract_content(payload),
                                "timestamp": timestamp,
                            }
                        )
                    elif payload_type in ("function_call", "custom_tool_call"):
                        messages.append(
                            {
                                "role": "assistant",
                                "content": codex_format_function_call(payload),
                                "timestamp": timestamp,
                                "is_tool_call": True,
                            }
                        )
                    elif payload_type in ("function_call_output", "custom_tool_call_output"):
                        messages.append(
                            {
                                "role": "tool",
                                "content": codex_format_function_result(payload),
                                "timestamp": timestamp,
                                "is_tool_result": True,
                            }
                        )
            except json.JSONDecodeError:
                continue

    return messages, session_meta


def codex_get_first_timestamp(jsonl_file: Path) -> Optional[str]:
    """Get timestamp from Codex session's session_meta line.

    Args:
        jsonl_file: Path to the Codex rollout .jsonl file

    Returns:
        ISO 8601 timestamp string or None if not found
    """
    try:
        with open(jsonl_file, encoding="utf-8") as f:
            first_line = f.readline()
            entry = json.loads(first_line)
            if entry.get("type") == "session_meta":
                return entry.get("timestamp", "")
    except (OSError, json.JSONDecodeError):
        pass
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
        role = msg.get("role", "unknown")
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

    # Extract model and token usage (latest total_token_usage) from event stream.
    last_token_usage = None
    last_token_timestamp = None
    try:
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type")
                payload = entry.get("payload", {})

                if entry_type == "turn_context" and not metrics["session"]["model"]:
                    metrics["session"]["model"] = payload.get("model")
                    continue

                if entry_type == "event_msg" and payload.get("type") == "token_count":
                    info = payload.get("info") or {}
                    total_usage = info.get("total_token_usage")
                    if total_usage:
                        last_token_usage = total_usage
                        last_token_timestamp = entry.get("timestamp")
    except OSError:
        pass

    if last_token_usage:
        metrics["tokens_summary"] = {
            "input_tokens": last_token_usage.get("input_tokens", 0),
            "output_tokens": last_token_usage.get("output_tokens", 0)
            + last_token_usage.get("reasoning_output_tokens", 0),
            "cache_read_tokens": last_token_usage.get("cached_input_tokens", 0),
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
    try:
        with open(jsonl_file, encoding="utf-8") as f:
            first_line = f.readline()
            entry = json.loads(first_line)
            if entry.get("type") == "session_meta":
                cwd = entry.get("payload", {}).get("cwd", "")
                if cwd:
                    return cwd
    except (OSError, json.JSONDecodeError):
        pass
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
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "response_item":
                        payload = entry.get("payload", {})
                        if payload.get("type") == "message":
                            count += 1
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return count


# =============================================================================
# Session Index Management
# =============================================================================


def codex_get_index_file() -> Path:
    """Get path to Codex session index file (~/.agent-history/codex_index.json)."""
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
    for child in sorted(parent.iterdir()):
        if child.is_dir() and child.name.isdigit():
            yield child


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


def _codex_date_folders_since(sessions_dir: Path, since_date: Optional[str]) -> list:
    """Get list of date folders on or after since_date.

    Args:
        sessions_dir: Base sessions directory (~/.codex/sessions/)
        since_date: Date string "YYYY-MM-DD" to start from (inclusive)

    Returns:
        List of Path objects for YYYY/MM/DD folders to scan
    """
    if not sessions_dir.exists():
        return []

    since_dt = datetime.strptime(since_date, "%Y-%m-%d") if since_date else None
    return list(_iter_date_folders(sessions_dir, since_dt))


def _remove_stale_entries(sessions_map: dict) -> int:
    """Remove entries for files that no longer exist.

    Args:
        sessions_map: Dict mapping file paths to workspace names

    Returns:
        Number of stale entries removed
    """
    stale_keys = [k for k in sessions_map if not Path(k).exists()]
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
        for jsonl_file in day_dir.glob("rollout-*.jsonl"):
            file_key = str(jsonl_file)
            if file_key not in existing_sessions:
                workspace = codex_get_workspace_from_session(jsonl_file)
                existing_sessions[file_key] = workspace
    return existing_sessions


def codex_ensure_index_updated(sessions_dir: Optional[Path] = None) -> dict[str, str]:
    """Ensure Codex session index is up-to-date.

    Performs incremental indexing: only scans date folders since last update.

    Args:
        sessions_dir: Override sessions directory (for testing)

    Returns:
        Dict mapping session file paths (str) to encoded workspace names
    """
    sessions_dir = sessions_dir or codex_get_home_dir()

    if not sessions_dir.exists():
        return {}

    index = codex_load_index()
    sessions_map = index.get("sessions", {})

    # Clean up deleted files
    _remove_stale_entries(sessions_map)

    # Incremental scan from last scan date (or full scan if first run)
    folders = _codex_date_folders_since(sessions_dir, index.get("last_scan_date"))
    _scan_folders_for_sessions(folders, sessions_map)

    # Save updated index
    index["sessions"] = sessions_map
    index["last_scan_date"] = datetime.now().strftime("%Y-%m-%d")
    codex_save_index(index)

    return sessions_map


# =============================================================================
# Metrics DB Cache (for message counts)
# =============================================================================


def _get_metrics_db_path() -> Path:
    """Get the metrics database file path."""
    return get_config_dir() / "metrics.db"


def _get_cached_message_count(jsonl_file: Path, current_mtime: float) -> Optional[int]:
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
    dt: Optional[datetime],
    since_date: Optional[datetime],
    until_date: Optional[datetime],
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
    get_readable: Optional[Callable[[str], str]] = None,
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
    since_date: Optional[datetime],
    until_date: Optional[datetime],
    get_readable: Optional[Callable[[str], str]] = None,
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
    since_date: Optional[datetime],
    until_date: Optional[datetime],
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
    sessions_dir: Optional[Path] = None,
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
    # Walk through YYYY/MM/DD structure using glob
    for jsonl_file in sessions_dir.glob("*/*/*/rollout-*.jsonl"):
        file_key = str(jsonl_file)
        # Look up workspace from index (fallback to file read if not in index or empty)
        workspace = sessions_map.get(file_key)
        if not workspace:  # None or empty string
            workspace = codex_get_workspace_from_session(jsonl_file)
            # Update index with recomputed workspace if we had to fall back
            if workspace and file_key in sessions_map:
                sessions_map[file_key] = workspace

        modified = datetime.fromtimestamp(jsonl_file.stat().st_mtime)

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
    elif msg.get("is_tool_result"):
        unified["role"] = "system"

    return unified
