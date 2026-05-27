"""Pi coding-agent backend for agent-history."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any

from agent_history.export.markdown import (
    MARKDOWN_DEFAULT_LEVEL,
    parse_jsonl_to_markdown,
)
from agent_history.utils.platform import AGENT_PI

PI_WRAPPED_WORKSPACE_MARKER_LEN = len("----")


def _pretty_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _pi_agent_dir() -> Path:
    override = os.environ.get("PI_CODING_AGENT_DIR")
    if override:
        return Path(override)
    return Path.home() / ".pi" / "agent"


def _pi_session_dir_from_settings(settings_file: Path, base_dir: Path) -> Path | None:
    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    value = data.get("sessionDir")
    if not value:
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path if path.exists() else None


def pi_get_home_dir(include_project_settings: bool = False) -> Path:
    """Return Pi's session directory."""
    env_override = os.environ.get("PI_CODING_AGENT_SESSION_DIR") or os.environ.get(
        "PI_SESSIONS_DIR"
    )
    if env_override:
        return Path(env_override)

    agent_dir = _pi_agent_dir()
    if include_project_settings:
        project_settings = Path.cwd() / ".pi" / "settings.json"
        project_dir = _pi_session_dir_from_settings(project_settings, project_settings.parent)
        if project_dir:
            return project_dir

    global_dir = _pi_session_dir_from_settings(agent_dir / "settings.json", agent_dir)
    if global_dir:
        return global_dir

    return agent_dir / "sessions"


def _pi_format_timestamp(value: Any) -> str:
    """Return a readable timestamp from Pi entry/message timestamp values."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(float(value) / 1000).isoformat() + "Z"
        except (OSError, OverflowError, ValueError):
            return str(value)
    return str(value)


def _pi_extract_content(content: Any) -> str:
    """Extract visible text from Pi string or content-block arrays."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        block_type = content.get("type")
        if block_type == "text":
            return str(content.get("text", ""))
        if block_type == "image":
            return f"[Image: {content.get('mimeType', 'unknown')}]"
        if block_type == "thinking":
            return ""
        if "text" in content:
            return str(content.get("text") or "")
        if "content" in content:
            return _pi_extract_content(content.get("content"))
        return _pretty_json(content)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "toolCall":
                continue
            text = _pi_extract_content(block)
            if text:
                parts.append(text)
        return "\n".join(parts)
    return str(content)


def _pi_extract_thoughts(content: Any) -> list[dict[str, str]]:
    """Extract Pi thinking blocks for normalized message records."""
    if not isinstance(content, list):
        return []
    thoughts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "thinking":
            thinking = block.get("thinking")
            if thinking:
                thoughts.append({"subject": "thinking", "description": str(thinking)})
    return thoughts


def _pi_extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract Pi assistant tool calls from content blocks or metadata."""
    calls: list[dict[str, Any]] = []
    seen_ids = set()
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "toolCall":
                call_id = block.get("id")
                if call_id:
                    seen_ids.add(call_id)
                calls.append(
                    {
                        "id": call_id,
                        "name": block.get("name", "unknown"),
                        "arguments": block.get("arguments") or block.get("input") or {},
                    }
                )

    metadata_calls = (message.get("metadata") or {}).get("toolCalls")
    if isinstance(metadata_calls, list):
        for call in metadata_calls:
            if not isinstance(call, dict):
                continue
            call_id = call.get("id")
            if call_id and call_id in seen_ids:
                continue
            if call_id:
                seen_ids.add(call_id)
            calls.append(call)
    return calls


def _pi_message_role(raw_role: str) -> str:
    """Map Pi raw roles to normalized agent-history roles."""
    if raw_role in ("user", "assistant"):
        return raw_role
    if raw_role in ("toolResult", "bashExecution"):
        return "tool"
    return "system"


def _pi_entry_message(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Return the Pi AgentMessage object from a session entry."""
    if isinstance(entry.get("message"), dict):
        return entry["message"]
    if entry.get("type") == "message":
        return entry
    if entry.get("type") == "custom_message":
        return {
            "role": "custom",
            "content": entry.get("content", ""),
            "display": entry.get("display", False),
            "customType": entry.get("customType"),
            "details": entry.get("details"),
        }
    if entry.get("type") == "compaction":
        return {
            "role": "compactionSummary",
            "content": entry.get("summary", ""),
            "tokensBefore": entry.get("tokensBefore"),
        }
    if entry.get("type") == "branch_summary":
        return {
            "role": "branchSummary",
            "content": entry.get("summary", ""),
            "fromId": entry.get("fromId"),
        }
    if entry.get("type") in (
        "model_change",
        "thinking_level_change",
        "custom",
        "label",
        "session_info",
    ):
        entry_type = entry.get("type")
        content = _pretty_json({k: v for k, v in entry.items() if k != "type"})
        return {
            "role": entry_type,
            "content": content,
            "customType": entry_type,
        }
    return None


def _pi_normalize_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a Pi JSONL entry to the common normalized message shape."""
    message = _pi_entry_message(entry)
    if not message:
        return None

    raw_role = message.get("role", entry.get("role", "system"))
    role = _pi_message_role(raw_role)
    timestamp = _pi_format_timestamp(entry.get("timestamp") or message.get("timestamp"))
    content = _pi_extract_content(message.get("content"))
    tool_calls = _pi_extract_tool_calls(message)
    normalized: dict[str, Any] = {
        "role": role,
        "raw_role": raw_role,
        "content": content,
        "timestamp": timestamp,
        "raw_payload": message,
        "id": entry.get("id"),
        "parent_id": entry.get("parentId"),
    }
    if entry.get("children") is not None:
        normalized["children"] = entry.get("children")
    if message.get("model"):
        normalized["model"] = message.get("model")
    if message.get("usage"):
        normalized["tokens"] = message.get("usage")
    thoughts = _pi_extract_thoughts(message.get("content"))
    if thoughts:
        normalized["thoughts"] = thoughts
    if tool_calls:
        normalized["tool_calls"] = tool_calls
    if raw_role == "toolResult":
        normalized.update(
            {
                "is_tool_result": True,
                "tool_call_id": message.get("toolCallId"),
                "tool_name": message.get("toolName", "unknown"),
                "is_error": bool(message.get("isError")),
            }
        )
    elif raw_role == "bashExecution":
        output = message.get("output", content)
        exit_code = message.get("exitCode")
        normalized.update(
            {
                "is_tool_result": True,
                "tool_name": "bash",
                "content": str(output or ""),
                "command": message.get("command", ""),
                "exit_code": exit_code,
                "is_error": bool(message.get("cancelled"))
                or (exit_code is not None and exit_code != 0),
                "cancelled": bool(message.get("cancelled")),
                "truncated": bool(message.get("truncated")),
                "full_output_path": message.get("fullOutputPath"),
                "exclude_from_context": bool(message.get("excludeFromContext")),
            }
        )
    elif raw_role in (
        "custom",
        "compactionSummary",
        "branchSummary",
        "model_change",
        "thinking_level_change",
        "label",
        "session_info",
    ):
        normalized["is_internal_context"] = True
        normalized["internal_context_type"] = raw_role
        normalized["internal_context_name"] = message.get("customType") or raw_role
    return normalized


def _pi_active_branch_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return messages on Pi's latest active branch path."""
    by_id = {msg.get("id"): msg for msg in messages if msg.get("id")}
    if not by_id or not any(msg.get("parent_id") for msg in messages):
        return messages

    leaf = next((msg for msg in reversed(messages) if msg.get("id")), None)
    if not leaf:
        return messages

    active_ids = set()
    current = leaf
    while current and current.get("id") and current.get("id") not in active_ids:
        active_ids.add(current["id"])
        current = by_id.get(current.get("parent_id"))

    omitted = sum(1 for msg in messages if msg.get("id") and msg.get("id") not in active_ids)
    active = [msg for msg in messages if not msg.get("id") or msg.get("id") in active_ids]
    if omitted:
        for msg in active:
            msg["pi_omitted_branch_entries"] = omitted
    return active


def pi_read_jsonl_messages(
    jsonl_file: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Read messages from a Pi JSONL session file."""
    messages: list[dict[str, Any]] = []
    session_meta = None
    with open(jsonl_file, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry_type = entry.get("type")
            if entry_type in ("session", "tree"):
                session_meta = entry
                continue
            msg = _pi_normalize_entry(entry)
            if msg:
                messages.append(msg)
    return _pi_active_branch_messages(messages), session_meta


def _pi_decode_workspace_dir(name: str) -> str:
    """Decode Pi's --path-- workspace directory name when cwd metadata is absent."""
    trimmed = name
    if (
        trimmed.startswith("--")
        and trimmed.endswith("--")
        and len(trimmed) > PI_WRAPPED_WORKSPACE_MARKER_LEN
    ):
        trimmed = trimmed[2:-2]
    else:
        trimmed = trimmed.strip("-")
    if not trimmed:
        return "unknown"
    parts = [part for part in trimmed.split("-") if part]
    if parts and re.fullmatch(r"[A-Za-z]:", parts[0]):
        return str(PureWindowsPath(*parts))
    return "/" + "/".join(parts)


def pi_get_workspace_from_session(jsonl_file: Path) -> str:
    """Extract workspace path from Pi session header or encoded parent folder."""
    try:
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("type") in ("session", "tree"):
                    cwd = entry.get("cwd") or entry.get("workspace")
                    if cwd:
                        return str(cwd)
                    break
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return _pi_decode_workspace_dir(jsonl_file.parent.name)
    except (AttributeError, IndexError):
        return "unknown"


def pi_get_workspace_readable(workspace: str) -> str:
    """Convert a Pi workspace identifier to a readable path string."""
    if not workspace:
        return ""
    if workspace.startswith("--"):
        return _pi_decode_workspace_dir(workspace)
    return workspace


def pi_count_messages(jsonl_file: Path) -> int:
    """Count user/assistant messages in a Pi session."""
    try:
        messages, _ = pi_read_jsonl_messages(jsonl_file)
    except OSError:
        return 0
    return sum(1 for msg in messages if msg.get("role") in ("user", "assistant"))


def _message_label(msg: dict[str, Any]) -> str:
    if msg.get("is_tool_result"):
        return f"Tool Result: {msg.get('tool_name', 'unknown')}"
    if msg.get("is_internal_context"):
        return f"Context: {msg.get('internal_context_name', 'internal')}"
    role = msg.get("role", "unknown")
    return str(role).title()


def pi_parse_jsonl_to_markdown(jsonl_file: Path, minimal: bool = False) -> str:
    """Convert Pi JSONL to markdown format."""
    messages, session_meta = pi_read_jsonl_messages(jsonl_file)
    md_lines = ["# Pi Conversation", ""]

    if session_meta and not minimal:
        md_lines.extend(
            [
                "## Session Metadata",
                "",
                f"- **Session ID:** `{session_meta.get('id', 'unknown')}`",
                f"- **Working Directory:** `{session_meta.get('cwd', pi_get_workspace_from_session(jsonl_file))}`",
                f"- **Version:** `{session_meta.get('version', 'unknown')}`",
                "",
            ]
        )

    md_lines.extend(["---", ""])
    for i, msg in enumerate(messages, 1):
        md_lines.append(f"## {_message_label(msg)} (Message {i})")
        if not minimal:
            if msg.get("timestamp"):
                md_lines.append(f"*{msg['timestamp']}*")
            md_lines.append(f"*Raw Role: {msg.get('raw_role', msg.get('role', 'unknown'))}*")
        md_lines.append("")
        if msg.get("content"):
            md_lines.extend([str(msg["content"]), ""])
        for tool_call in msg.get("tool_calls", []):
            md_lines.extend(
                [
                    f"**[Tool: {tool_call.get('name', 'unknown')}]**",
                    f"Call ID: `{tool_call.get('id', '')}`",
                    "```json",
                    _pretty_json(tool_call.get("arguments") or {}),
                    "```",
                    "",
                ]
            )
        md_lines.extend(["---", ""])

    return "\n".join(md_lines)


def _matches_workspace_pattern(workspace: str, pattern: str) -> bool:
    if not pattern or pattern in ("", "*", "all"):
        return True
    workspace_lower = workspace.lower()
    readable_lower = pi_get_workspace_readable(workspace).lower()
    normalized_pattern = pattern.lower().strip("/")
    if normalized_pattern in workspace_lower or normalized_pattern in readable_lower:
        return True
    pattern_as_path = "/" + normalized_pattern.replace("-", "/")
    return pattern_as_path in readable_lower or pattern_as_path in workspace_lower


def _date_in_range(
    modified: datetime,
    since_date: datetime | None,
    until_date: datetime | None,
) -> bool:
    if since_date and modified < since_date:
        return False
    if until_date and modified > until_date:
        return False
    return True


def _pi_build_session_dict(
    jsonl_file: Path,
    workspace: str,
    modified: datetime,
    skip_message_count: bool,
) -> dict[str, Any]:
    return {
        "agent": AGENT_PI,
        "workspace": workspace,
        "workspace_readable": pi_get_workspace_readable(workspace),
        "file": jsonl_file,
        "filename": jsonl_file.name,
        "message_count": 0 if skip_message_count else pi_count_messages(jsonl_file),
        "message_count_skipped": skip_message_count,
        "modified": modified,
        "source": "local",
    }


def pi_scan_sessions(
    pattern: str = "",
    since_date: datetime | None = None,
    until_date: datetime | None = None,
    sessions_dir: Path | None = None,
    skip_message_count: bool = False,
) -> list[dict[str, Any]]:
    """Scan Pi session files under ~/.pi/agent/sessions/*/*.jsonl."""
    if sessions_dir is None:
        sessions_dir = pi_get_home_dir()
    if not sessions_dir.exists():
        return []

    sessions = []
    for jsonl_file in sessions_dir.glob("*/*.jsonl"):
        workspace = pi_get_workspace_from_session(jsonl_file)
        modified = datetime.fromtimestamp(jsonl_file.stat().st_mtime)
        if _matches_workspace_pattern(workspace, pattern) and _date_in_range(
            modified, since_date, until_date
        ):
            sessions.append(
                _pi_build_session_dict(
                    jsonl_file,
                    workspace,
                    modified,
                    skip_message_count,
                )
            )
    return sorted(sessions, key=lambda s: s["modified"], reverse=True)


def pi_message_to_unified(msg: dict[str, Any]) -> dict[str, Any]:
    """Convert a Pi message to the unified NDJSON message schema."""
    unified: dict[str, Any] = {
        "timestamp": msg.get("timestamp", ""),
        "role": msg.get("role", "assistant"),
        "content": msg.get("content", ""),
    }
    if msg.get("raw_role"):
        unified["raw_role"] = msg["raw_role"]
    if msg.get("model"):
        unified["model"] = msg["model"]
    if msg.get("tokens"):
        tokens = msg["tokens"]
        unified["tokens"] = {
            "input": tokens.get("input", 0),
            "output": tokens.get("output", 0),
            "cache_write": tokens.get("cacheWrite", 0),
            "cache_read": tokens.get("cacheRead", 0),
        }
    if msg.get("tool_calls"):
        unified["tool_calls"] = msg["tool_calls"]
    if msg.get("is_tool_result"):
        unified["role"] = "system"
        unified["tool_result"] = {
            "tool_call_id": msg.get("tool_call_id"),
            "tool_name": msg.get("tool_name", "unknown"),
            "is_error": msg.get("is_error", False),
        }
    return unified


def pi_render_markdown(
    session_file: Path,
    minimal: bool,
    messages: list[dict[str, Any]] | None,
    markdown_level: int,
) -> str:
    """Render Pi Markdown, using generic compact levels when requested."""
    if markdown_level < MARKDOWN_DEFAULT_LEVEL:
        return parse_jsonl_to_markdown(
            session_file,
            minimal,
            messages,
            agent_type=AGENT_PI,
            markdown_level=markdown_level,
        )
    return pi_parse_jsonl_to_markdown(session_file, minimal)
