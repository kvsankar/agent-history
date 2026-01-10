"""Gemini CLI backend for agent-history.

This module handles all Gemini CLI session operations:
- Session scanning (~/.gemini/tmp/<hash>/chats/)
- Hash-to-path index management for workspace resolution
- JSON message parsing and formatting
- Metrics extraction for statistics

Gemini CLI stores sessions differently from Claude:
- Sessions are in ~/.gemini/tmp/<project_hash>/chats/session-*.json
- Project hash is SHA-256 of the absolute project path
- Each session is a single JSON file (not JSONL)
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TypedDict

from ..storage.config import get_config_dir
from ..utils.platform import AGENT_GEMINI

__all__ = [
    # Constants
    "GEMINI_HOME_DIR",
    "GEMINI_HASH_INDEX_VERSION",
    "HASH_DISPLAY_LEN",
    # Home directory
    "gemini_get_home_dir",
    # JSON parsing
    "gemini_read_json_messages",
    "gemini_parse_json_to_markdown",
    "gemini_get_first_timestamp",
    # Tool/thought formatting
    "gemini_format_tool_call",
    "gemini_format_thoughts",
    # Metrics extraction
    "gemini_extract_metrics_from_json",
    # Hash index management
    "gemini_get_hash_index_file",
    "gemini_get_legacy_hash_index_file",
    "gemini_load_hash_index",
    "gemini_save_hash_index",
    "gemini_compute_project_hash",
    "gemini_update_hash_index_from_cwd",
    "gemini_get_path_for_hash",
    "gemini_get_workspace_readable",
    "gemini_add_paths_to_index",
    # Session scanning
    "gemini_get_workspace_from_session",
    "gemini_count_messages",
    "gemini_scan_sessions",
    # Unified export
    "_gemini_message_to_unified",
]


# =============================================================================
# Constants
# =============================================================================

# Gemini home directory (sessions stored in ~/.gemini/tmp/<hash>/chats/)
GEMINI_HOME_DIR = Path.home() / ".gemini" / "tmp"

# Hash index version for compatibility checking
GEMINI_HASH_INDEX_VERSION = 1

# Display constants
HASH_DISPLAY_LEN = 8  # Characters to show for truncated hash display
MAX_THOUGHT_LEN = 200  # Max length for thought descriptions before truncating
MAX_TOOL_OUTPUT_LEN = 2000  # Max length for tool output before truncating

# Gemini role display names
_GEMINI_ROLE_DISPLAY_NAMES = {
    "user": "User",
    "assistant": "Model",
    "info": "Info",
    "error": "Error",
    "warning": "Warning",
}


# =============================================================================
# TypedDicts for Type Safety
# =============================================================================


class SessionMetrics(TypedDict):
    """Session metadata in metrics dict."""

    id: Optional[str]
    cwd: Optional[str]
    cli_version: Optional[str]
    model: Optional[str]
    startTime: Optional[str]
    lastUpdated: Optional[str]


class TokensMetrics(TypedDict):
    """Token counts in metrics dict."""

    input: int
    output: int
    total: int


class MetricsDict(TypedDict, total=False):
    """Full metrics dictionary structure."""

    session: SessionMetrics
    messages: list[dict[str, Any]]
    tool_uses: list[dict[str, Any]]
    tokens: TokensMetrics


class HashIndexCounts(TypedDict):
    """Counts for hash index operations."""

    added: int
    existing: int
    no_sessions: int
    mappings: list[Any]


# =============================================================================
# Environment Override Support
# =============================================================================

import os


def gemini_get_home_dir() -> Path:
    """Get Gemini sessions directory (~/.gemini/tmp/).

    Supports GEMINI_SESSIONS_DIR environment variable override for testing
    and custom configurations.
    """
    env_override = os.environ.get("GEMINI_SESSIONS_DIR")
    if env_override:
        return Path(env_override).expanduser()
    return GEMINI_HOME_DIR


# =============================================================================
# Text Truncation Utilities
# =============================================================================


def _truncate_tool_output(output: str, max_len: int = MAX_TOOL_OUTPUT_LEN) -> str:
    """Truncate tool output to max length with indicator.

    Args:
        output: Tool output string
        max_len: Maximum length before truncation

    Returns:
        Original string if within limit, otherwise truncated with indicator
    """
    if len(output) <= max_len:
        return output
    return output[:max_len] + "\n... [truncated]"


def _truncate_thought(thought: str, max_len: int = MAX_THOUGHT_LEN) -> str:
    """Truncate thought description to max length.

    Args:
        thought: Thought description string
        max_len: Maximum length before truncation

    Returns:
        Original string if within limit, otherwise truncated with ellipsis
    """
    if len(thought) <= max_len:
        return thought
    return thought[:max_len] + "..."


def _truncate_hash(hash_string: str, max_len: int = HASH_DISPLAY_LEN) -> str:
    """Truncate hash to display length if needed.

    Args:
        hash_string: The hash string to truncate
        max_len: Maximum length (default: HASH_DISPLAY_LEN)

    Returns:
        Truncated hash if longer than max_len, otherwise original
    """
    if len(hash_string) > max_len:
        return hash_string[:max_len]
    return hash_string


# =============================================================================
# JSON Utilities
# =============================================================================


def pretty_json(obj: Any) -> str:
    """Format object as indented JSON.

    Args:
        obj: Object to serialize

    Returns:
        Pretty-printed JSON string
    """
    return json.dumps(obj, indent=2, ensure_ascii=False)


# =============================================================================
# Gemini JSON Parsing
# =============================================================================


def _extract_gemini_content_part(part) -> str:
    """Extract text from a single Gemini content part."""
    if isinstance(part, str):
        return part
    if not isinstance(part, dict):
        return ""

    if "text" in part:
        return part["text"]
    if "inlineData" in part:
        mime = part["inlineData"].get("mimeType", "unknown")
        return f"[Inline data: {mime}]"
    if "executableCode" in part:
        code = part["executableCode"]
        lang = code.get("language", "")
        return f"```{lang}\n{code.get('code', '')}\n```"
    if "codeExecutionResult" in part:
        result = part["codeExecutionResult"]
        return f"**Output:**\n```\n{result.get('output', '')}\n```"
    return ""


def _extract_gemini_content(content) -> str:
    """Extract text content from Gemini message content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_extract_gemini_content_part(p) for p in content]
        return "\n".join(p for p in parts if p)
    return ""


def _build_gemini_message(msg: dict, content: str) -> Optional[dict]:
    """Build a normalized message dict from Gemini message data."""
    msg_type = msg.get("type", "")
    timestamp = msg.get("timestamp", "")

    if msg_type == "user":
        return {"role": "user", "content": content, "timestamp": timestamp}
    if msg_type == "gemini":
        return {
            "role": "assistant",
            "content": content,
            "timestamp": timestamp,
            "thoughts": msg.get("thoughts", []),
            "tokens": msg.get("tokens"),
            "model": msg.get("model"),
            "tool_calls": msg.get("toolCalls", []),
        }
    if msg_type in ("info", "error", "warning"):
        return {"role": msg_type, "content": content, "timestamp": timestamp}
    return None


def gemini_read_json_messages(json_file: Path) -> tuple:
    """Read messages from Gemini CLI JSON session file.

    Gemini stores sessions as single JSON files (not JSONL) with structure:
    {sessionId, projectHash, startTime, lastUpdated, messages: [...]}

    Args:
        json_file: Path to the Gemini session .json file

    Returns:
        Tuple of (messages_list, session_meta_dict or None)
        Messages contain: role, content, timestamp, and optionally
        is_tool_call, thoughts, tokens, model fields
    """
    try:
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return [], None

    session_meta = {
        "sessionId": data.get("sessionId"),
        "projectHash": data.get("projectHash"),
        "startTime": data.get("startTime"),
        "lastUpdated": data.get("lastUpdated"),
        "summary": data.get("summary"),
    }

    messages = []
    for msg in data.get("messages", []):
        content = _extract_gemini_content(msg.get("content", ""))
        normalized = _build_gemini_message(msg, content)
        if normalized:
            messages.append(normalized)

    return messages, session_meta


# =============================================================================
# Tool and Thought Formatting
# =============================================================================


def gemini_format_tool_call(tool_call: dict) -> str:
    """Format a Gemini tool call as markdown.

    Args:
        tool_call: Tool call dict with id, name, args, result, status, etc.

    Returns:
        Formatted markdown string for the tool call
    """
    name = tool_call.get("displayName") or tool_call.get("name", "unknown")
    args = tool_call.get("args", {})
    status = tool_call.get("status", "")
    result = tool_call.get("result", [])

    lines = [f"**[Tool: {name}]** ({status})"]

    if args:
        try:
            args_str = pretty_json(args)
        except (TypeError, ValueError):
            args_str = str(args)
        lines.append(f"```json\n{args_str}\n```")

    # Extract result output if present
    if result:
        for r in result:
            if isinstance(r, dict):
                func_resp = r.get("functionResponse", {})
                output = func_resp.get("response", {}).get("output", "")
                if output:
                    # Use helper for consistent truncation (M4)
                    output = _truncate_tool_output(output)
                    lines.append(f"**Result:**\n```\n{output}\n```")

    return "\n".join(lines)


def gemini_format_thoughts(thoughts: list) -> str:
    """Format Gemini reasoning thoughts as markdown.

    Args:
        thoughts: List of thought dicts with subject, description, timestamp
                  (or strings for legacy/alternative formats)

    Returns:
        Formatted markdown string for the thoughts
    """
    if not thoughts:
        return ""

    lines = ["", "**Reasoning:**"]
    for thought in thoughts:
        # Handle both dict format and potential string format
        if isinstance(thought, str):
            if thought.strip():
                text = _truncate_thought(thought)
                lines.append(f"- {text}")
        elif isinstance(thought, dict):
            subject = thought.get("subject", "")
            description = thought.get("description", "")
            desc_text = _truncate_thought(description)
            if subject:
                lines.append(f"- **{subject}**: {desc_text}")
            elif description:
                lines.append(f"- {desc_text}")
        # Skip other types silently

    return "\n".join(lines)


def gemini_get_first_timestamp(json_file: Path) -> Optional[str]:
    """Get startTime from Gemini session.

    Args:
        json_file: Path to the Gemini session .json file

    Returns:
        ISO 8601 timestamp string or None if not found
    """
    try:
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("startTime", "")
    except (OSError, json.JSONDecodeError):
        pass
    return None


# =============================================================================
# Markdown Conversion
# =============================================================================


def _gemini_format_session_metadata(session_meta: dict) -> list:
    """Format Gemini session metadata as markdown lines."""
    project_hash = session_meta.get("projectHash") or "unknown"
    short_hash = _truncate_hash(project_hash)
    lines = [
        "## Session Metadata",
        "",
        f"- **Session ID:** `{session_meta.get('sessionId', 'unknown')}`",
        f"- **Project Hash:** `{short_hash}...`",
        f"- **Start Time:** `{session_meta.get('startTime', 'unknown')}`",
        f"- **Last Updated:** `{session_meta.get('lastUpdated', 'unknown')}`",
        "",
    ]
    if session_meta.get("summary"):
        lines.extend(["### Summary", "", session_meta["summary"], ""])
    return lines


def _gemini_get_role_header(role: str, msg_num: int) -> str:
    """Get the markdown header for a message role."""
    name = _GEMINI_ROLE_DISPLAY_NAMES.get(role, role.title())
    return f"## {name} (Message {msg_num})"


def _gemini_format_message(msg: dict, msg_num: int, minimal: bool) -> list:
    """Format a single Gemini message as markdown lines."""
    lines = [_gemini_get_role_header(msg.get("role", "unknown"), msg_num)]

    if not minimal:
        if msg.get("timestamp"):
            lines.append(f"*{msg['timestamp']}*")
        if msg.get("model"):
            lines.append(f"*Model: {msg['model']}*")

    lines.append("")

    if msg.get("thoughts") and not minimal:
        lines.extend([gemini_format_thoughts(msg["thoughts"]), ""])

    if msg.get("content"):
        lines.extend([msg["content"], ""])

    for tc in msg.get("tool_calls", []):
        lines.extend([gemini_format_tool_call(tc), ""])

    if msg.get("tokens") and not minimal:
        tokens = msg["tokens"]
        lines.extend(
            [
                f"*Tokens: {tokens.get('total', 0)} total "
                f"(in: {tokens.get('input', 0)}, out: {tokens.get('output', 0)}, "
                f"cached: {tokens.get('cached', 0)})*",
                "",
            ]
        )

    lines.extend(["---", ""])
    return lines


def gemini_parse_json_to_markdown(json_file: Path, minimal: bool = False) -> str:
    """Convert Gemini session JSON to markdown format.

    Args:
        json_file: Path to the Gemini session .json file
        minimal: If True, omit metadata sections

    Returns:
        Markdown formatted string of the conversation
    """
    messages, session_meta = gemini_read_json_messages(json_file)
    md_lines = ["# Gemini Conversation", ""]

    if session_meta and not minimal:
        md_lines.extend(_gemini_format_session_metadata(session_meta))

    md_lines.extend(["---", ""])

    for i, msg in enumerate(messages, 1):
        md_lines.extend(_gemini_format_message(msg, i, minimal))

    return "\n".join(md_lines)


# =============================================================================
# Metrics Extraction
# =============================================================================


def gemini_extract_metrics_from_json(json_file: Path) -> MetricsDict:
    """Extract metrics from Gemini JSON file for stats database.

    Args:
        json_file: Path to the Gemini session .json file

    Returns:
        Dict with session, messages, and tool_uses data
    """
    messages, session_meta = gemini_read_json_messages(json_file)

    metrics: MetricsDict = {
        "session": {
            "id": session_meta.get("sessionId") if session_meta else None,
            "cwd": session_meta.get("projectHash")
            if session_meta
            else None,  # Use hash as workspace
            "cli_version": None,  # Gemini doesn't store CLI version in session
            "model": None,
            "startTime": session_meta.get("startTime") if session_meta else None,
            "lastUpdated": session_meta.get("lastUpdated") if session_meta else None,
        },
        "messages": [],
        "tool_uses": [],
        "tokens": {
            "input": 0,
            "output": 0,
            "total": 0,
        },
    }

    for msg in messages:
        role = msg.get("role")
        timestamp = msg.get("timestamp")

        # Extract model from first assistant message
        if role == "assistant" and not metrics["session"]["model"]:
            metrics["session"]["model"] = msg.get("model")

        # Accumulate token usage
        tokens = msg.get("tokens")
        if tokens:
            metrics["tokens"]["input"] += tokens.get("input", 0)
            metrics["tokens"]["output"] += tokens.get("output", 0)
            metrics["tokens"]["total"] += tokens.get("total", 0)

        # Track tool calls
        for tc in msg.get("tool_calls", []):
            status = tc.get("status", "")
            metrics["tool_uses"].append(
                {
                    "name": tc.get("name", "unknown"),
                    "timestamp": tc.get("timestamp") or timestamp,
                    "is_error": status.lower() in ("error", "failed", "failure")
                    if status
                    else False,
                }
            )

        # Track messages (exclude system messages)
        if role in ("user", "assistant"):
            msg_data = {
                "role": role,
                "timestamp": timestamp,
                "model": msg.get("model"),
            }
            # Include per-message token usage for stats
            if tokens:
                msg_data["input_tokens"] = tokens.get("input", 0)
                msg_data["output_tokens"] = tokens.get("output", 0)
            metrics["messages"].append(msg_data)

    return metrics


# =============================================================================
# Hash Index Management
# =============================================================================


def gemini_get_hash_index_file() -> Path:
    """Get path to Gemini hash index file (~/.agent-history/gemini_index.json)."""
    return get_config_dir() / "gemini_index.json"


def gemini_get_legacy_hash_index_file() -> Path:
    """Legacy Gemini hash index location (~/.agent-history/gemini_hash_index.json)."""
    return get_config_dir() / "gemini_hash_index.json"


def gemini_load_hash_index() -> dict:
    """Load Gemini hash-to-path index from file.

    Returns:
        Index dict with keys: version, hashes
        hashes maps project hash (str) to absolute path (str)
    """
    index_file = gemini_get_hash_index_file()
    legacy_file = gemini_get_legacy_hash_index_file()

    # Prefer new location, fall back to legacy if present
    candidate_files = [index_file]
    if legacy_file != index_file:
        candidate_files.append(legacy_file)

    for candidate in candidate_files:
        if candidate.exists():
            try:
                with open(candidate, encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("version") == GEMINI_HASH_INDEX_VERSION:
                        return data
            except (OSError, json.JSONDecodeError):
                continue
    return {"version": GEMINI_HASH_INDEX_VERSION, "hashes": {}}


def gemini_save_hash_index(index: dict) -> None:
    """Save Gemini hash-to-path index to file."""
    index_file = gemini_get_hash_index_file()
    index_file.parent.mkdir(parents=True, exist_ok=True)
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def gemini_compute_project_hash(path: Path) -> str:
    """Compute SHA-256 hash of a path, matching Gemini CLI's approach.

    Gemini CLI uses SHA-256 of the absolute path string as the project identifier.

    Args:
        path: Path to hash (will be resolved to absolute)

    Returns:
        SHA-256 hex digest of the absolute path string
    """
    abs_path = str(path.resolve())
    return hashlib.sha256(abs_path.encode("utf-8")).hexdigest()


def gemini_update_hash_index_from_cwd() -> dict:
    """Update Gemini hash index based on current working directory.

    Called on each agent-history run to progressively build hash->path mapping.
    Checks if the current directory's hash exists in Gemini's session storage,
    and if so, records the mapping.

    Returns:
        Updated hash index dict
    """
    index = gemini_load_hash_index()
    cwd = Path.cwd()
    cwd_hash = gemini_compute_project_hash(cwd)

    # Check if this hash exists in Gemini's session storage
    gemini_dir = gemini_get_home_dir()
    hash_dir = gemini_dir / cwd_hash / "chats"

    if hash_dir.exists() and any(hash_dir.glob("session-*.json")):
        # Found Gemini sessions for this directory - record the mapping
        current_path = str(cwd.resolve())
        existing_path = index["hashes"].get(cwd_hash)

        if existing_path != current_path:
            index["hashes"][cwd_hash] = current_path
            gemini_save_hash_index(index)

    return index


def gemini_get_path_for_hash(project_hash: str) -> str | None:
    """Look up the real path for a Gemini project hash.

    Args:
        project_hash: SHA-256 hash of the project path

    Returns:
        Absolute path string if known, None otherwise
    """
    index = gemini_load_hash_index()
    return index["hashes"].get(project_hash)


def gemini_get_workspace_readable(workspace: str) -> str:
    """Get human-readable workspace name for a Gemini workspace identifier.

    Handles three cases:
    - Real path (starts with / or drive letter): return as-is
    - SHA-256 hash: looks up in hash index, falls back to truncated hash
    - Encoded path (like -home-user-project): normalizes to readable path

    Args:
        workspace: Real path, encoded workspace path, or SHA-256 hash

    Returns:
        Readable workspace name (path or [hash:xxxxxxxx])
    """
    # If it's already a real path, return it directly
    # Check for Unix paths (/) or Windows paths (drive letter like C:\)
    if workspace.startswith("/") or (len(workspace) > 1 and workspace[1] == ":"):
        return workspace

    # Try to look up as a hash in the index
    real_path = gemini_get_path_for_hash(workspace)
    if real_path:
        # Return the path directly - it's already readable
        return real_path

    # Fall back to truncated hash display
    if len(workspace) > HASH_DISPLAY_LEN:
        return f"[hash:{workspace[:HASH_DISPLAY_LEN]}]"
    return workspace


# =============================================================================
# Path-to-Index Addition
# =============================================================================


def _has_gemini_sessions(project_hash: str, gemini_dir: Path) -> bool:
    """Check if Gemini has sessions for this project hash.

    Args:
        project_hash: SHA-256 hash of project path
        gemini_dir: Gemini home directory

    Returns:
        True if sessions exist for this hash
    """
    hash_dir = gemini_dir / project_hash / "chats"
    return hash_dir.exists() and any(hash_dir.glob("session-*.json"))


def _build_path_mapping(
    project_str: str,
    project_hash: str,
    status: str,
    path_missing: bool,
) -> dict[str, Any]:
    """Build a path mapping result dict.

    Args:
        project_str: Resolved path string
        project_hash: SHA-256 hash of project path
        status: Status string ('added', 'existing', 'no_sessions')
        path_missing: Whether the path doesn't exist

    Returns:
        Mapping dict for the result
    """
    return {
        "path": project_str,
        "hash": project_hash[:HASH_DISPLAY_LEN],
        "status": status,
        "path_missing": path_missing,
    }


def _try_add_path_to_index(
    path: Path,
    index: dict[str, Any],
    gemini_dir: Path,
) -> tuple[str, dict[str, Any]]:
    """Try to add a single path to the index.

    Args:
        path: Path to add
        index: Current index dictionary
        gemini_dir: Gemini home directory

    Returns:
        Tuple of (status, mapping_dict)
    """
    resolved = path.resolve()
    project_hash = gemini_compute_project_hash(resolved)
    project_str = str(resolved)
    path_missing = not resolved.exists()

    # No sessions for this hash
    if not _has_gemini_sessions(project_hash, gemini_dir):
        return "no_sessions", _build_path_mapping(
            project_str, project_hash, "no_sessions", path_missing
        )

    # Already in index with same path
    existing = index["hashes"].get(project_hash)
    if existing == project_str:
        return "existing", _build_path_mapping(project_str, project_hash, "existing", path_missing)

    # Add to index
    index["hashes"][project_hash] = project_str
    return "added", _build_path_mapping(project_str, project_hash, "added", path_missing)


def gemini_add_paths_to_index(paths: list[Path]) -> HashIndexCounts:
    """Add explicit paths to the Gemini hash->path index.

    For each path, computes its SHA-256 hash and checks if Gemini has
    sessions for that hash. If sessions exist, adds the mapping to the index.

    Args:
        paths: List of Path objects to add to the index

    Returns:
        Dict with 'added', 'existing', 'no_sessions' counts and 'mappings' list
    """
    if not paths:
        return {"added": 0, "existing": 0, "no_sessions": 0, "mappings": []}

    index = gemini_load_hash_index()
    gemini_dir = gemini_get_home_dir()

    # Process each path
    results = [_try_add_path_to_index(p, index, gemini_dir) for p in paths]

    # Aggregate results
    counts: HashIndexCounts = {
        "added": sum(1 for status, _ in results if status == "added"),
        "existing": sum(1 for status, _ in results if status == "existing"),
        "no_sessions": sum(1 for status, _ in results if status == "no_sessions"),
        "mappings": [mapping for _, mapping in results],
    }

    # Save if we added anything
    if counts["added"] > 0:
        gemini_save_hash_index(index)

    return counts


# =============================================================================
# Session Scanning
# =============================================================================


def gemini_get_workspace_from_session(json_file: Path) -> str:
    """Extract workspace identifier from Gemini session.

    Uses the hash index to get the real path if known, otherwise returns
    the hash. This ensures consistent workspace naming across scan/export/stats.

    Args:
        json_file: Path to the Gemini session .json file

    Returns:
        Encoded path (if hash->path known) or project hash, or 'unknown'
    """
    # The file is in ~/.gemini/tmp/<project_hash>/chats/<session>.json
    # So we need to go up two levels to get the project hash
    try:
        chats_dir = json_file.parent  # chats/
        project_dir = chats_dir.parent  # <project_hash>/
        project_hash = project_dir.name

        # Try to get the real path from hash index
        real_path = gemini_get_path_for_hash(project_hash)
        if real_path:
            # Return real path directly - encoding would mangle hyphens in folder names
            return real_path
        return project_hash
    except (AttributeError, IndexError):
        pass
    return "unknown"


def gemini_count_messages(json_file: Path) -> int:
    """Count user/assistant messages in a Gemini session.

    Args:
        json_file: Path to the Gemini session .json file

    Returns:
        Number of user and gemini messages
    """
    count = 0
    try:
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
            for msg in data.get("messages", []):
                if msg.get("type") in ("user", "gemini"):
                    count += 1
    except (OSError, json.JSONDecodeError):
        pass
    return count


def _gemini_build_session_dict(
    json_file: Path,
    workspace: str,
    modified: datetime,
    skip_message_count: bool,
    use_cached_counts: bool = False,
    get_cached_count_fn=None,
) -> dict:
    """Build a session dictionary for a Gemini session file.

    Args:
        json_file: Path to session file
        workspace: Workspace identifier (hash or path)
        modified: Last modified datetime
        skip_message_count: If True, skip counting messages
        use_cached_counts: If True, try to use cached message counts
        get_cached_count_fn: Optional function to get cached counts
    """
    # Use hash index to get readable workspace name if known
    workspace_readable = gemini_get_workspace_readable(workspace)
    message_count = 0
    if not skip_message_count:
        cached = None
        if use_cached_counts and get_cached_count_fn:
            cached = get_cached_count_fn(json_file, modified.timestamp())
        message_count = cached if cached is not None else gemini_count_messages(json_file)
    return {
        "agent": AGENT_GEMINI,
        "workspace": workspace,
        "workspace_readable": workspace_readable,
        "file": json_file,
        "filename": json_file.name,
        "message_count": message_count,
        "message_count_skipped": skip_message_count,
        "modified": modified,
        "source": "local",
    }


def _matches_workspace_pattern(
    workspace: str,
    pattern: str,
    get_readable=None,
) -> bool:
    """Check if workspace matches the given pattern.

    Args:
        workspace: Workspace identifier
        pattern: Pattern to match (substring match)
        get_readable: Optional function to get readable workspace name

    Returns:
        True if workspace matches pattern
    """
    if not pattern:
        return True

    # Get readable form for matching
    readable = get_readable(workspace) if get_readable else None

    workspace_lower = workspace.lower()
    readable_lower = readable.lower() if readable else None
    pattern_lower = pattern.lower()

    # Direct substring match
    if pattern_lower in workspace_lower:
        return True
    if readable_lower and pattern_lower in readable_lower:
        return True

    # Handle pattern with dashes as potential path separators
    # e.g., "my-project" should match "/home/user/my-project"
    normalized_pattern = pattern_lower.replace("-", "/").strip("/")
    if normalized_pattern in workspace_lower.replace("-", "/"):
        return True
    if readable_lower and normalized_pattern in readable_lower:
        return True

    # Also try the reverse: convert pattern to path format for matching
    pattern_as_path = "/" + normalized_pattern.replace("-", "/")
    return pattern_as_path in (readable_lower or workspace_lower)


def _is_date_in_range(
    modified: datetime,
    since_date: Optional[datetime],
    until_date: Optional[datetime],
) -> bool:
    """Check if date is within the given range.

    Args:
        modified: Date to check
        since_date: Start of range (inclusive)
        until_date: End of range (inclusive)

    Returns:
        True if date is within range
    """
    if since_date and modified < since_date:
        return False
    if until_date and modified > until_date:
        return False
    return True


def _gemini_session_matches_filters(
    workspace: str,
    modified: datetime,
    pattern: str,
    since_date: Optional[datetime],
    until_date: Optional[datetime],
) -> bool:
    """Check if a Gemini session matches the given filters.

    Uses shared _session_matches_filters with gemini_get_workspace_readable
    for hash-to-path lookups.
    """
    if not _matches_workspace_pattern(workspace, pattern, gemini_get_workspace_readable):
        return False
    return _is_date_in_range(modified, since_date, until_date)


def gemini_scan_sessions(
    pattern: str = "",
    since_date=None,
    until_date=None,
    sessions_dir: Optional[Path] = None,
    skip_message_count: bool = False,
    use_cached_counts: bool = False,
    get_cached_count_fn=None,
) -> list:
    """Scan ~/.gemini/tmp/*/chats/ for session-*.json files.

    Args:
        pattern: Substring pattern to filter workspaces (empty matches all)
        since_date: Only include sessions modified on or after this date
        until_date: Only include sessions modified on or before this date
        sessions_dir: Override sessions directory (for testing)
        skip_message_count: If True, skip counting messages (set to 0)
        use_cached_counts: If True, try to use cached message counts
        get_cached_count_fn: Optional function to get cached counts

    Returns:
        List of session dicts sorted by modified time (newest first)
    """
    if sessions_dir is None:
        sessions_dir = gemini_get_home_dir()

    if not sessions_dir.exists():
        return []

    sessions = []
    # Gemini stores sessions in ~/.gemini/tmp/<project_hash>/chats/session-*.json
    for json_file in sessions_dir.glob("*/chats/session-*.json"):
        workspace = gemini_get_workspace_from_session(json_file)
        modified = datetime.fromtimestamp(json_file.stat().st_mtime)

        if _gemini_session_matches_filters(workspace, modified, pattern, since_date, until_date):
            sessions.append(
                _gemini_build_session_dict(
                    json_file,
                    workspace,
                    modified,
                    skip_message_count,
                    use_cached_counts=use_cached_counts,
                    get_cached_count_fn=get_cached_count_fn,
                )
            )

    return sorted(sessions, key=lambda s: s["modified"], reverse=True)


# =============================================================================
# Unified NDJSON Export Support
# =============================================================================


def _normalize_role(role: str) -> str:
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


def _gemini_message_to_unified(msg: dict) -> dict:
    """Convert Gemini message to unified NDJSON schema.

    Args:
        msg: Gemini message dict from gemini_read_json_messages

    Returns:
        Unified schema dict with timestamp, role, content, and optional fields
    """
    role = msg.get("role", "user")
    unified = {
        "timestamp": msg.get("timestamp", ""),
        "role": _normalize_role(role),
        "content": msg.get("content", ""),
    }

    # Optional fields
    if msg.get("model"):
        unified["model"] = msg["model"]
    if msg.get("tokens"):
        tokens = msg["tokens"]
        unified["tokens"] = {
            "input": tokens.get("input", 0),
            "output": tokens.get("output", 0),
        }
        if tokens.get("cached"):
            unified["tokens"]["cached"] = tokens["cached"]

    # Tool calls
    tool_calls = msg.get("tool_calls", [])
    if tool_calls:
        unified["tool_calls"] = [
            {
                "name": tc.get("name"),
                "id": tc.get("id"),
                "args": tc.get("args"),
                "status": tc.get("status"),
            }
            for tc in tool_calls
        ]

    return unified
