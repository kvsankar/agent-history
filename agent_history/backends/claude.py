"""Claude Code backend functions for agent-history.

This module handles Claude Code session discovery, message parsing, and
workspace management. It provides functions for:

- Session scanning: Finding and listing Claude Code sessions
- Message parsing: Reading and converting JSONL session files
- Workspace handling: Managing Claude's dash-encoded workspace directories

Claude Code stores sessions in ~/.claude/projects/ with workspace directories
using dash-encoded paths (e.g., '-home-user-project' for /home/user/project).
"""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Optional

from agent_history.utils.paths import (
    is_cached_workspace,
    normalize_workspace_name,
)

__all__ = [
    # Session scanning
    "get_workspace_sessions",
    "get_claude_projects_dir",
    # Message parsing
    "read_jsonl_messages",
    "extract_content",
    "get_first_timestamp",
    # Message conversion
    "claude_message_to_unified",
    "normalize_role",
    "extract_unified_content",
    # Workspace helpers
    "path_to_encoded_workspace",
    "validate_workspace_name",
    "is_safe_path",
    # Session helpers
    "is_date_in_range",
    # Internal helpers (exported for testing)
    "_get_session_from_file",
    "_count_file_messages",
    "_is_valid_workspace_dir",
    "_workspace_matches_pattern",
    "_detect_wsl_base_path",
    "_should_skip_workspace",
]


# ============================================================================
# Constants
# ============================================================================

# Maximum workspace name length (reasonable limit for encoded paths)
MAX_WORKSPACE_NAME_LENGTH = 1000

# Minimum length for Windows paths
MIN_WINDOWS_PATH_LEN = 2  # "C:"
MIN_WSL_MNT_PATH_LEN = 6  # "/mnt/c"

# Workspace name validation pattern (alphanumeric, dashes, underscores, dots, unicode)
import re

WORKSPACE_NAME_PATTERN = re.compile(r"^[-a-zA-Z0-9_.\u0080-\uFFFF]+$")


# ============================================================================
# Date Range Filtering
# ============================================================================


def is_date_in_range(
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


# ============================================================================
# Security and Validation
# ============================================================================


def validate_workspace_name(workspace_name: str) -> bool:
    """Validate workspace name to prevent command injection and path traversal.

    Workspace names from Claude Code are encoded paths like:
    - '-home-user-project' (Unix)
    - 'C--Users-name-project' (Windows)
    - 'remote_host_home-user-project' (cached remote)
    - 'wsl_Ubuntu_home-user-project' (cached WSL)

    Returns True if valid, False otherwise.
    """
    if not workspace_name:
        return False
    if len(workspace_name) > MAX_WORKSPACE_NAME_LENGTH:
        return False
    # Check for path traversal sequences
    if ".." in workspace_name:
        return False
    return WORKSPACE_NAME_PATTERN.match(workspace_name) is not None


def is_safe_path(base_dir: Path, target_path: Path) -> bool:
    """Check if target_path is safely within base_dir (no path traversal).

    This prevents directory traversal attacks where a malicious path
    could escape the intended base directory.

    Args:
        base_dir: The base directory that should contain the path
        target_path: The path to validate

    Returns:
        True if target_path is within base_dir, False otherwise.
    """
    try:
        # Resolve both paths to absolute paths (resolves symlinks and ..)
        base_resolved = base_dir.resolve()
        target_resolved = target_path.resolve()

        # Check if target is within base (or is base itself)
        return target_resolved == base_resolved or str(target_resolved).startswith(
            str(base_resolved) + os.sep
        )
    except (OSError, ValueError):
        return False


# ============================================================================
# Claude Projects Directory
# ============================================================================


def _get_claude_projects_path() -> Path:
    """Get Claude projects directory path without validation.

    Used for detection/existence checks where we don't want to exit on error.

    Returns:
        Path to Claude projects directory (may not exist)
    """
    env_override = os.environ.get("CLAUDE_PROJECTS_DIR")
    if env_override:
        return Path(env_override).expanduser()
    return Path.home() / ".claude" / "projects"


def get_claude_projects_dir() -> Path:
    """Get the Claude projects directory, with error handling.

    Creates the directory if it doesn't exist to avoid hard exits in clean environments.

    Returns:
        Path to ~/.claude/projects/
    """
    projects_dir = _get_claude_projects_path()
    projects_dir.mkdir(parents=True, exist_ok=True)

    return projects_dir


# ============================================================================
# Path Encoding
# ============================================================================


def _convert_windows_path_to_encoded(path: str) -> str:
    """Convert Windows absolute path (C:\\... or C:/...) to encoded format."""
    drive = path[0].upper()
    rest = path[2:].lstrip("/\\").replace("\\", "/").replace("/", "-")
    return f"{drive}--{rest}"


def path_to_encoded_workspace(path: str) -> str:
    """Convert an absolute path to Claude's encoded workspace directory name.

    Args:
        path: Absolute path (e.g., '/home/user/my-project' or 'C:\\Users\\alice\\projects')

    Returns:
        Encoded workspace name (e.g., '-home-user-my-project' or 'C--Users-alice-projects')
    """
    # Remove trailing slash/backslash if present
    path = path.rstrip("/").rstrip("\\")

    # Handle native Windows paths (C:\... or C:/...)
    # Check for drive letter followed by colon (e.g., C:, D:)
    if len(path) >= MIN_WINDOWS_PATH_LEN and path[1] == ":":
        return _convert_windows_path_to_encoded(path)

    # Handle WSL-mounted Windows paths like /mnt/c/Users/me/project
    if path.startswith("/mnt/") and len(path) > MIN_WSL_MNT_PATH_LEN:
        drive_letter = path[5]
        sep = path[MIN_WSL_MNT_PATH_LEN]
        if drive_letter.isalpha() and sep in ("/", "\\"):
            remainder = path[MIN_WSL_MNT_PATH_LEN + 1 :].replace("\\", "/").strip("/")
            normalized = remainder.replace("/", "-") if remainder else ""
            return f"{drive_letter.upper()}--{normalized}"

    # Replace / with - and add leading -
    if path.startswith("/"):
        return "-" + path[1:].replace("/", "-")
    else:
        return "-" + path.replace("/", "-")


# ============================================================================
# Message Parsing Helpers
# ============================================================================


def _iter_json_objects(line: str) -> Optional[list]:
    """Parse one or more JSON objects from a line.

    Returns a list of objects, or None if parsing fails.
    """
    decoder = json.JSONDecoder()
    idx = 0
    end = len(line)
    objects = []
    while idx < end:
        while idx < end and line[idx].isspace():
            idx += 1
        if idx >= end:
            break
        try:
            obj, next_idx = decoder.raw_decode(line, idx)
        except json.JSONDecodeError:
            return None
        objects.append(obj)
        idx = next_idx
    return objects


def _pretty_json(obj: Any) -> str:
    """Format an object as pretty-printed JSON.

    Args:
        obj: Any JSON-serializable object

    Returns:
        Pretty-printed JSON string with 2-space indentation
    """
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _format_tool_use_block(block: dict) -> list:
    """Format a tool_use block as markdown lines."""
    tool_name = block.get("name", "unknown")
    tool_id = block.get("id", "")
    tool_input = block.get("input", {})

    lines = [f"\n**[Tool Use: {tool_name}]**"]
    if tool_id:
        lines.append(f"Tool ID: `{tool_id}`")
    lines.extend(["\nInput:", "```json", _pretty_json(tool_input), "```\n"])
    return lines


def _extract_text_from_result_item(item) -> str:
    """Extract text from a single result item.

    Tool result content can be either dict items with 'text' key
    or primitive values that need string conversion.

    Args:
        item: A result item from tool_result content list

    Returns:
        Text content as string
    """
    if isinstance(item, dict):
        return item.get("text", "")
    return str(item)


def _format_tool_result_block(block: dict) -> list:
    """Format a tool_result block as markdown lines."""
    tool_use_id = block.get("tool_use_id", "")
    is_error = block.get("is_error", False)
    result_content = block.get("content", "")

    # Handle both string and list content in tool results
    if isinstance(result_content, list):
        result_text = "\n".join(_extract_text_from_result_item(item) for item in result_content)
    else:
        result_text = result_content

    status = "ERROR" if is_error else "Success"
    lines = [f"\n**[Tool Result: {status}]**"]
    if tool_use_id:
        lines.append(f"Tool Use ID: `{tool_use_id}`")
    lines.extend(["\n```", result_text, "```\n"])
    return lines


def extract_content(message_obj: dict) -> str:
    """Extract text content from message object, preserving all information.

    Claude API messages contain different content structures:
    - User messages: Simple string content
    - Assistant messages: Array of content blocks (text, tool_use, tool_result)

    Args:
        message_obj: Message dictionary from JSONL entry

    Returns:
        Markdown-formatted string of all message content.
    """
    if "content" not in message_obj:
        return "[No content]"

    content = message_obj["content"]

    # User messages have simple string content
    if isinstance(content, str):
        return content

    # Assistant messages have array of content blocks
    if not isinstance(content, list):
        return "[No content]"

    content_parts = []
    for block in content:
        block_type = block.get("type")
        if block_type == "text":
            content_parts.append(block.get("text", ""))
        elif block_type == "tool_use":
            content_parts.extend(_format_tool_use_block(block))
        elif block_type == "tool_result":
            content_parts.extend(_format_tool_result_block(block))

    return "\n".join(content_parts) if content_parts else "[No content]"


def _build_message_dict(
    entry: dict, message_obj: dict, role: str, content: str, timestamp: str
) -> dict:
    """Build a message dictionary from entry and message object.

    Args:
        entry: The JSONL entry dict with metadata
        message_obj: The message object from the entry
        role: Message role ("user" or "assistant")
        content: Extracted message content
        timestamp: ISO 8601 timestamp string

    Returns:
        Message dict with all preserved metadata
    """
    return {
        "role": role,
        "content": content,
        "timestamp": timestamp,
        "uuid": entry.get("uuid", ""),
        "parentUuid": entry.get("parentUuid"),
        "sessionId": entry.get("sessionId", ""),
        "agentId": entry.get("agentId"),
        "requestId": entry.get("requestId"),
        "cwd": entry.get("cwd", ""),
        "version": entry.get("version", ""),
        "gitBranch": entry.get("gitBranch"),
        "isSidechain": entry.get("isSidechain"),
        "isMeta": entry.get("isMeta"),
        "userType": entry.get("userType"),
        "model": message_obj.get("model"),
        "usage": message_obj.get("usage"),
        "stop_reason": message_obj.get("stop_reason"),
        "stop_sequence": message_obj.get("stop_sequence"),
    }


# ============================================================================
# Message Reading
# ============================================================================


def read_jsonl_messages(jsonl_file: Path, quiet: bool = False):
    """Read and parse all messages from a Claude Code JSONL session file.

    Parses each line of the JSONL file, extracting user and assistant
    messages along with their metadata. Invalid JSON lines are skipped
    with a warning.

    Args:
        jsonl_file: Path to the .jsonl session file
        quiet: If True, suppress warnings about malformed JSON

    Returns:
        List of message dicts containing:
        - role: "user" or "assistant"
        - content: Extracted and formatted message content
        - timestamp: ISO 8601 timestamp string
        - uuid, parentUuid, sessionId, agentId: Message identifiers
        - cwd, version, gitBranch: Context information
        - model, usage, stop_reason: Assistant message metadata
    """
    messages = []

    def handle_entry(entry: dict) -> None:
        entry_type = entry.get("type")
        if entry_type in ("user", "assistant"):
            message_obj = entry.get("message", {})
            role = message_obj.get("role", entry_type)
            timestamp = entry.get("timestamp", "")
            content = extract_content(message_obj)

            messages.append(_build_message_dict(entry, message_obj, role, content, timestamp))

    with open(jsonl_file, encoding="utf-8") as f:
        for line in f:
            try:
                handle_entry(json.loads(line))
            except json.JSONDecodeError as e:
                parsed = _iter_json_objects(line)
                if not parsed:
                    stripped = line.lstrip()
                    if stripped.startswith("{") or stripped.startswith("["):
                        if not quiet:
                            print(
                                f"Warning: Couldn't parse line in {jsonl_file.name}: {e}",
                                file=sys.stderr,
                            )
                    continue
                for entry in parsed:
                    if isinstance(entry, dict):
                        handle_entry(entry)

    return messages


def get_first_timestamp(jsonl_file: Path) -> Optional[str]:
    """Extract the first message timestamp from a .jsonl file.

    Scans the file line by line looking for the first user or assistant
    message with a timestamp. Returns None if file cannot be read or
    contains no valid messages.

    Args:
        jsonl_file: Path to JSONL file

    Returns:
        ISO 8601 timestamp string or None if not found or file cannot be read.
    """
    try:
        with open(jsonl_file, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                try:
                    entry = json.loads(line)
                    entry_type = entry.get("type")
                    if entry_type in ("user", "assistant"):
                        timestamp = entry.get("timestamp", "")
                        if timestamp:
                            return timestamp
                except json.JSONDecodeError as e:
                    # Skip malformed lines with debug info (NO-BARE-EXCEPT)
                    if os.environ.get("DEBUG"):
                        sys.stderr.write(
                            f"Warning: Malformed JSON at {jsonl_file}:{line_num}: {e}\n"
                        )
                    continue
    except OSError as e:
        # Log I/O errors in debug mode (NO-BARE-EXCEPT)
        if os.environ.get("DEBUG"):
            sys.stderr.write(f"Warning: Cannot read {jsonl_file}: {e}\n")
    return None


# ============================================================================
# Unified Message Conversion
# ============================================================================


def normalize_role(role: str) -> str:
    """Normalize role names to unified schema.

    Converts agent-specific role names to unified roles:
    - gemini -> assistant
    - tool -> system (tool results are system-level)

    Args:
        role: Original role from agent format

    Returns:
        Normalized role: "user", "assistant", or "system"
    """
    if role == "gemini":
        return "assistant"
    if role == "tool":
        return "system"
    if role in ("user", "assistant", "system"):
        return role
    # System-level types (info, error, warning)
    if role in ("info", "error", "warning"):
        return "system"
    return role


def extract_unified_content(msg: dict) -> str:
    """Extract content string from Claude message format.

    Args:
        msg: Message dict from read_jsonl_messages

    Returns:
        Content string
    """
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    # For array content (e.g., Claude tool_use blocks), join text parts
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") in ("input_text", "output_text"):
                    parts.append(item.get("text", ""))
        return "\n".join(parts) if parts else str(content)
    return str(content)


def claude_message_to_unified(msg: dict) -> dict:
    """Convert Claude message to unified NDJSON schema.

    Args:
        msg: Claude message dict from read_jsonl_messages

    Returns:
        Unified schema dict with timestamp, role, content, and optional fields
    """
    unified = {
        "timestamp": msg.get("timestamp", ""),
        "role": normalize_role(msg.get("role", "user")),
        "content": extract_unified_content(msg),
    }

    # Optional fields
    if msg.get("model"):
        unified["model"] = msg["model"]
    if msg.get("usage"):
        usage = msg["usage"]
        unified["tokens"] = {
            "input": usage.get("input_tokens", 0),
            "output": usage.get("output_tokens", 0),
        }
        if usage.get("cache_read_input_tokens"):
            unified["tokens"]["cached"] = usage["cache_read_input_tokens"]

    # Tool calls for Claude are embedded in content array
    message_obj = msg.get("message", {})
    content_array = message_obj.get("content", []) if isinstance(message_obj, dict) else []
    if isinstance(content_array, list):
        tool_calls = []
        for item in content_array:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "name": item.get("name"),
                        "id": item.get("id"),
                        "input": item.get("input"),
                    }
                )
        if tool_calls:
            unified["tool_calls"] = tool_calls

    return unified


# ============================================================================
# Session Scanning Helpers
# ============================================================================


def _detect_wsl_base_path(projects_dir: Path) -> Optional[Path]:
    """Detect WSL base path from projects directory, or None if not WSL.

    Handles both str and bytes forms for compatibility with tests that supply
    dummy path objects.
    """
    import os as _os

    p = _os.fspath(projects_dir)
    if isinstance(p, bytes):
        p = p.decode(errors="ignore")

    is_wsl_unc = any(
        p.startswith(prefix)
        for prefix in ("\\\\wsl.localhost\\", "//wsl.localhost/", "\\\\wsl$\\", "//wsl$/")
    )
    if not is_wsl_unc:
        return None

    # Use the UNC anchor (e.g., \\wsl.localhost\\Ubuntu) as the base path
    anchor = PureWindowsPath(p).anchor
    return Path(anchor.rstrip("\\/")) if anchor else None


def _should_skip_workspace(dir_name: str, include_cached: bool) -> bool:
    """Check if a workspace directory should be skipped."""
    if not include_cached:
        if is_cached_workspace(dir_name):
            return True
        if dir_name.startswith("-remote-") or dir_name.startswith("--wsl-"):
            return True
    return False


def _get_cached_message_count(jsonl_file: Path, current_mtime: float) -> Optional[int]:
    """Return cached message count from metrics DB if mtime matches."""
    from agent_history.storage.config import get_aliases_dir

    db_path = get_aliases_dir() / "metrics.db"
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


def _count_file_messages(
    jsonl_file: Path, skip_count: bool, use_cached_counts: bool = False
) -> int:
    """Count valid messages in a JSONL file.

    Only counts lines that are valid JSON with type 'user' or 'assistant'
    (or have 'role' field for older formats).
    """
    if skip_count:
        return 0
    try:
        current_mtime = jsonl_file.stat().st_mtime
    except OSError:
        current_mtime = None
    if use_cached_counts and current_mtime is not None:
        cached = _get_cached_message_count(jsonl_file, current_mtime)
        if cached is not None:
            return cached
    count = 0
    try:
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    # Count only user/assistant messages
                    msg_type = data.get("type") or data.get("role")
                    if msg_type in ("user", "assistant", "model"):
                        count += 1
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return count


def _get_session_from_file(
    jsonl_file: Path,
    workspace_dir: Path,
    readable_name: str,
    skip_message_count: bool,
    use_cached_counts: bool = False,
) -> dict:
    """Build session dict from a JSONL file."""
    stat = jsonl_file.stat()
    message_count = _count_file_messages(
        jsonl_file, skip_message_count, use_cached_counts=use_cached_counts
    )
    return {
        "agent": "claude",
        "workspace": workspace_dir.name,
        "workspace_readable": readable_name,
        "file": jsonl_file,
        "filename": jsonl_file.name,
        "size_kb": stat.st_size / 1024,
        "modified": datetime.fromtimestamp(stat.st_mtime),
        "message_count": message_count,
        "message_count_skipped": skip_message_count,
        "source": "local",
    }


def _is_session_in_date_range(
    session: dict[str, Any],
    since_date: Optional[datetime],
    until_date: Optional[datetime],
) -> bool:
    """Check if session modification date is within the specified range."""
    return is_date_in_range(session.get("modified"), since_date, until_date)


def _is_valid_workspace_dir(
    workspace_dir: Path,
    projects_dir: Path,
    include_cached: bool,
) -> bool:
    """Check if workspace directory is valid for scanning.

    Centralizes validation logic for workspace directories, making the main
    scanning loop cleaner and the validation independently testable.

    Args:
        workspace_dir: Workspace directory to validate
        projects_dir: Parent projects directory
        include_cached: Whether to include cached remote/WSL workspaces

    Returns:
        True if workspace is valid for scanning
    """
    if not workspace_dir.is_dir():
        return False

    dir_name = workspace_dir.name

    if not validate_workspace_name(dir_name):
        return False

    if not is_safe_path(projects_dir, workspace_dir):
        return False

    if _should_skip_workspace(dir_name, include_cached):
        return False

    return True


def _normalize_pattern(pattern: str) -> str:
    """Normalize pattern for cross-platform matching.

    Converts path separators to dashes for Claude-style encoded matching.
    """
    return pattern.replace("\\", "-").replace("/", "-")


def _get_pattern_tail(pattern: str) -> str:
    """Get last component of pattern for partial matching."""
    return pattern.replace("\\", "/").split("/")[-1]


def _workspace_matches_pattern(dir_name: str, workspace_pattern: str, match_all: bool) -> bool:
    """Check if workspace matches the pattern.

    Args:
        dir_name: Workspace directory name (encoded path)
        workspace_pattern: Pattern to match
        match_all: If True, match all workspaces

    Returns:
        True if workspace matches pattern
    """
    if match_all:
        return True
    dir_lower = dir_name.lower()
    pattern_lower = workspace_pattern.lower()

    # Direct match
    if pattern_lower in dir_lower:
        return True

    # Normalized match (handle path separators)
    normalized = _normalize_pattern(workspace_pattern).lower()
    if normalized in dir_lower:
        return True

    # Tail match (just the last component)
    tail = _get_pattern_tail(workspace_pattern).lower()
    return bool(tail and tail in dir_lower)


# ============================================================================
# Session Scanning
# ============================================================================


def get_workspace_sessions(
    workspace_pattern: str,
    quiet: bool = False,
    since_date=None,
    until_date=None,
    include_cached: bool = False,
    projects_dir: Optional[Path] = None,
    skip_message_count: bool = False,
    use_cached_counts: bool = False,
):
    """Find all Claude Code sessions in workspaces matching the pattern.

    Args:
        workspace_pattern: Substring to match workspace names. Use "", "*", or "all" to match all.
        quiet: Suppress progress output if True
        since_date: Filter to sessions modified on or after this date
        until_date: Filter to sessions modified on or before this date
        include_cached: If True, include remote_* and wsl_* cached workspaces
        projects_dir: Explicit projects directory path (default: auto-detect)
        skip_message_count: If True, skip counting messages (faster for slow filesystems)
        use_cached_counts: If True, use cached message counts from metrics DB

    Returns:
        List of session dicts with workspace, file, and metadata info
    """
    if projects_dir is None:
        projects_dir = get_claude_projects_dir()

    match_all = workspace_pattern.lower() in ("", "*", "all")
    wsl_base = _detect_wsl_base_path(projects_dir)
    sessions = []

    for workspace_dir in projects_dir.iterdir():
        # Use centralized validation (H10)
        if not _is_valid_workspace_dir(workspace_dir, projects_dir, include_cached):
            continue

        dir_name = workspace_dir.name
        if not _workspace_matches_pattern(dir_name, workspace_pattern, match_all):
            continue

        readable_name = normalize_workspace_name(dir_name, base_path=wsl_base)

        for jsonl_file in workspace_dir.glob("*.jsonl"):
            session = _get_session_from_file(
                jsonl_file,
                workspace_dir,
                readable_name,
                skip_message_count,
                use_cached_counts=use_cached_counts,
            )
            if _is_session_in_date_range(session, since_date, until_date):
                sessions.append(session)

    sessions.sort(key=lambda s: s["modified"])
    return sessions
