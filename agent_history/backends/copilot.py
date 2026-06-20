"""GitHub Copilot local-history backends for cagelens."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import unquote, urlparse

from agent_history.export.markdown import MARKDOWN_DEFAULT_LEVEL, parse_jsonl_to_markdown
from agent_history.utils.platform import AGENT_COPILOT_CLI, AGENT_COPILOT_VSCODE


def copilot_cli_get_home_dir() -> Path:
    """Return Copilot CLI's session-state directory."""
    override = os.environ.get("COPILOT_CLI_SESSIONS_DIR") or os.environ.get("COPILOT_SESSIONS_DIR")
    if override:
        return Path(override).expanduser()
    copilot_home = os.environ.get("COPILOT_HOME")
    if copilot_home:
        return Path(copilot_home).expanduser() / "session-state"
    return Path.home() / ".copilot" / "session-state"


def _default_vscode_workspace_storage_roots() -> list[Path]:
    home = Path.home()
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        return [
            appdata / "Code" / "User" / "workspaceStorage",
            appdata / "Code - Insiders" / "User" / "workspaceStorage",
        ]
    if sys_platform := os.environ.get("CAGELENS_PLATFORM_OVERRIDE"):
        platform_name = sys_platform
    else:
        import sys

        platform_name = sys.platform
    if platform_name == "darwin":
        return [
            home / "Library" / "Application Support" / "Code" / "User" / "workspaceStorage",
            home
            / "Library"
            / "Application Support"
            / "Code - Insiders"
            / "User"
            / "workspaceStorage",
        ]
    return [
        home / ".config" / "Code" / "User" / "workspaceStorage",
        home / ".config" / "Code - Insiders" / "User" / "workspaceStorage",
        home / ".vscode-server" / "data" / "User" / "workspaceStorage",
    ]


def copilot_vscode_workspace_storage_roots() -> list[Path]:
    """Return all local VS Code workspaceStorage roots to scan."""
    override = os.environ.get("COPILOT_VSCODE_WORKSPACE_STORAGE_DIR")
    if override:
        return [Path(override).expanduser()]
    return _default_vscode_workspace_storage_roots()


def copilot_vscode_get_home_dir() -> Path:
    """Return the first VS Code workspaceStorage directory to scan."""
    roots = copilot_vscode_workspace_storage_roots()
    for root in roots:
        if root.exists():
            return root
    return roots[0]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8-sig") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    events.append(value)
    except OSError:
        return []
    return events


def _extract_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            text = _extract_text(item)
            if text:
                parts.append(text)
        return "\n".join(parts)
    if isinstance(content, dict):
        for key in ("text", "value", "content", "message"):
            if key in content:
                text = _extract_text(content.get(key))
                if text:
                    return text
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _pretty_json(value: Any) -> str:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return value
        return json.dumps(decoded, indent=2, ensure_ascii=False)
    return json.dumps(value or {}, indent=2, ensure_ascii=False)


def _tool_call_id(data: dict[str, Any], event: dict[str, Any]) -> str | None:
    return (
        data.get("toolCallId")
        or data.get("tool_call_id")
        or data.get("callId")
        or data.get("call_id")
        or event.get("id")
    )


def _tool_name(data: dict[str, Any]) -> str:
    return str(data.get("toolName") or data.get("name") or data.get("tool") or "unknown")


def _tool_args(data: dict[str, Any]) -> Any:
    return data.get("arguments") or data.get("parameters") or data.get("input") or {}


def _tool_output(data: dict[str, Any]) -> str:
    output = data.get("output")
    if output is None:
        output = data.get("result")
    if output is None:
        output = data.get("error")
    if isinstance(output, str):
        return output
    return json.dumps(output or {}, indent=2, ensure_ascii=False)


_AUDIT_EVENT_TYPES = {
    "hook.end",
    "hook.start",
    "permission.completed",
    "permission.requested",
    "session.info",
    "session.model_change",
    "session.resume",
    "session.shutdown",
    "system.message",
    "system.notification",
}


def _event_timestamp(event: dict[str, Any]) -> str:
    value = event.get("timestamp")
    return str(value or "")


def _base_event(event: dict[str, Any], event_type: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "timestamp": _event_timestamp(event),
        "uuid": event.get("id"),
        "parentUuid": event.get("parentId"),
        "raw_event_type": event_type,
        "raw_payload": event,
    }
    agent_id = event.get("agentId")
    if agent_id:
        base["agent_id"] = agent_id
    return base


def _normalize_user_message(base: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    return {
        **base,
        "role": "user",
        "content": _extract_text(data.get("content")),
    }


def _normalize_assistant_message(base: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        **base,
        "role": "assistant",
        "content": _extract_text(data.get("content")),
    }
    if data.get("model"):
        normalized["model"] = data.get("model")
    if data.get("modelId"):
        normalized["model"] = data.get("modelId")
    output_tokens = data.get("outputTokens")
    if isinstance(output_tokens, int):
        normalized["usage"] = {"input_tokens": 0, "output_tokens": output_tokens}
    if isinstance(data.get("toolRequests"), list):
        normalized["tool_calls"] = data["toolRequests"]
    reasoning = data.get("reasoningText") or data.get("reasoning")
    if reasoning:
        normalized["thoughts"] = [{"subject": "reasoning", "description": str(reasoning)}]
    if data.get("reasoningOpaque"):
        normalized["reasoning_opaque"] = True
    return normalized


def _normalize_audit_event(
    base: dict[str, Any], data: dict[str, Any], event_type: str
) -> dict[str, Any]:
    content = data.get("content") or data.get("message")
    if not content:
        content = f"**{event_type}**\n\n```json\n{_pretty_json(data)}\n```"
    return {
        **base,
        "role": "system",
        "content": _extract_text(content),
    }


def _normalize_tool_start(
    base: dict[str, Any], data: dict[str, Any], event: dict[str, Any]
) -> dict[str, Any]:
    name = _tool_name(data)
    call_id = _tool_call_id(data, event) or ""
    return {
        **base,
        "role": "tool",
        "content": (
            f"**[Tool: {name}]**\nCall ID: `{call_id}`\n"
            f"```json\n{_pretty_json(_tool_args(data))}\n```"
        ),
        "is_tool_call": True,
        "tool_call_id": call_id,
        "tool_name": name,
        "tool_input": _tool_args(data),
    }


def _normalize_tool_complete(
    base: dict[str, Any], data: dict[str, Any], event: dict[str, Any]
) -> dict[str, Any]:
    name = _tool_name(data)
    return {
        **base,
        "role": "tool",
        "content": _tool_output(data),
        "is_tool_result": True,
        "tool_call_id": _tool_call_id(data, event),
        "tool_name": name,
        "is_error": bool(data.get("isError") or data.get("error")),
    }


def _normalize_subagent_event(
    base: dict[str, Any], data: dict[str, Any], event_type: str
) -> dict[str, Any]:
    title = event_type.replace(".", " ").title()
    return {
        **base,
        "role": "system",
        "content": f"{title}\n\n```json\n{_pretty_json(data)}\n```",
        "semantic_origin": "subagent_event",
        "subagent_status": "completed" if event_type.endswith("completed") else "started",
    }


def _normalize_event(event: dict[str, Any], agent: str) -> dict[str, Any] | None:
    del agent
    event_type = str(event.get("type") or "")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    base = _base_event(event, event_type)

    if event_type == "user.message":
        return _normalize_user_message(base, data)
    if event_type == "assistant.message":
        return _normalize_assistant_message(base, data)
    if event_type in _AUDIT_EVENT_TYPES:
        return _normalize_audit_event(base, data, event_type)
    if event_type == "tool.execution_start":
        return _normalize_tool_start(base, data, event)
    if event_type == "tool.execution_complete":
        return _normalize_tool_complete(base, data, event)
    if event_type in {"subagent.started", "subagent.completed"}:
        return _normalize_subagent_event(base, data, event_type)
    return None


def _read_messages(path: Path, agent: str) -> list[dict[str, Any]]:
    return [
        message
        for event in _read_jsonl(path)
        if (message := _normalize_event(event, agent)) is not None
    ]


def _tool_name_by_call_id(path: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for event in _read_jsonl(path):
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if event.get("type") == "assistant.message" and isinstance(data.get("toolRequests"), list):
            for request in data["toolRequests"]:
                if not isinstance(request, dict):
                    continue
                call_id = request.get("toolCallId") or request.get("id")
                name = request.get("name") or request.get("toolName")
                if call_id and name:
                    names[str(call_id)] = str(name)
        if event.get("type") == "tool.execution_start":
            call_id = _tool_call_id(data, event)
            if call_id:
                names[str(call_id)] = _tool_name(data)
    return names


def copilot_cli_read_messages(session_file: Path) -> list[dict[str, Any]]:
    return _read_messages(session_file, AGENT_COPILOT_CLI)


def copilot_vscode_read_messages(session_file: Path) -> list[dict[str, Any]]:
    return _read_messages(session_file, AGENT_COPILOT_VSCODE)


def _count_visible_messages(session_file: Path) -> int:
    count = 0
    for event in _read_jsonl(session_file):
        if event.get("type") in {"user.message", "assistant.message"}:
            count += 1
    return count


def copilot_count_messages(session_file: Path) -> int:
    return _count_visible_messages(session_file)


def _parse_simple_yaml_value(path: Path, key: str) -> str | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith(f"{key}:"):
                continue
            value = line.split(":", 1)[1].strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            return value or None
    except OSError:
        return None
    return None


def _cwd_from_session_start(events_file: Path) -> str | None:
    for event in _read_jsonl(events_file):
        if event.get("type") != "session.start":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        context = data.get("context") if isinstance(data.get("context"), dict) else {}
        cwd = context.get("cwd") or data.get("cwd")
        return str(cwd) if cwd else None
    return None


def copilot_cli_get_workspace_from_session(events_file: Path) -> str:
    workspace_yaml = events_file.parent / "workspace.yaml"
    return (
        _parse_simple_yaml_value(workspace_yaml, "cwd")
        or _cwd_from_session_start(events_file)
        or events_file.parent.name
    )


def _decode_file_uri(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "file":
        return value
    path = unquote(parsed.path)
    if parsed.netloc:
        return f"//{parsed.netloc}{path}"
    if len(path) >= 3 and path[0] == "/" and path[2] == ":":
        return str(PureWindowsPath(path[1:]))
    return path


def _workspace_json_for_transcript(transcript_file: Path) -> Path | None:
    for parent in transcript_file.parents:
        if parent.name == "GitHub.copilot-chat":
            return parent.parent / "workspace.json"
    return None


def copilot_vscode_get_workspace_from_session(transcript_file: Path) -> str:
    workspace_json = _workspace_json_for_transcript(transcript_file)
    if workspace_json:
        try:
            data = json.loads(workspace_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        folder = data.get("folder") if isinstance(data, dict) else None
        if isinstance(folder, str) and folder:
            return _decode_file_uri(folder)
    return _cwd_from_session_start(transcript_file) or transcript_file.parent.parent.parent.name


def _session_id_for_file(session_file: Path, agent: str) -> str:
    if agent == AGENT_COPILOT_VSCODE:
        return session_file.stem
    return session_file.parent.name


def _matches_workspace_pattern(workspace: str, pattern: str) -> bool:
    if not pattern or pattern in ("", "*", "all"):
        return True
    return pattern.lower().strip("/") in workspace.lower()


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


def _build_session_dict(
    *,
    agent: str,
    session_file: Path,
    workspace: str,
    modified: datetime,
    skip_message_count: bool,
) -> dict[str, Any]:
    return {
        "agent": agent,
        "workspace": workspace,
        "workspace_readable": workspace,
        "file": session_file,
        "filename": session_file.name,
        "message_count": 0 if skip_message_count else copilot_count_messages(session_file),
        "message_count_skipped": skip_message_count,
        "modified": modified,
        "source": "local",
    }


def copilot_cli_scan_sessions(
    pattern: str = "",
    since_date: datetime | None = None,
    until_date: datetime | None = None,
    sessions_dir: Path | None = None,
    skip_message_count: bool = False,
) -> list[dict[str, Any]]:
    sessions_dir = sessions_dir or copilot_cli_get_home_dir()
    if not sessions_dir.exists():
        return []
    sessions: list[dict[str, Any]] = []
    for events_file in sessions_dir.glob("*/events.jsonl"):
        workspace = copilot_cli_get_workspace_from_session(events_file)
        modified = datetime.fromtimestamp(events_file.stat().st_mtime)
        if _matches_workspace_pattern(workspace, pattern) and _date_in_range(
            modified, since_date, until_date
        ):
            sessions.append(
                _build_session_dict(
                    agent=AGENT_COPILOT_CLI,
                    session_file=events_file,
                    workspace=workspace,
                    modified=modified,
                    skip_message_count=skip_message_count,
                )
            )
    return sorted(sessions, key=lambda item: item["modified"], reverse=True)


def copilot_vscode_scan_sessions(
    pattern: str = "",
    since_date: datetime | None = None,
    until_date: datetime | None = None,
    sessions_dir: Path | None = None,
    skip_message_count: bool = False,
) -> list[dict[str, Any]]:
    sessions_dir = sessions_dir or copilot_vscode_get_home_dir()
    if not sessions_dir.exists():
        return []
    sessions: list[dict[str, Any]] = []
    for transcript_file in sessions_dir.glob("*/GitHub.copilot-chat/transcripts/*.jsonl"):
        workspace = copilot_vscode_get_workspace_from_session(transcript_file)
        modified = datetime.fromtimestamp(transcript_file.stat().st_mtime)
        if _matches_workspace_pattern(workspace, pattern) and _date_in_range(
            modified, since_date, until_date
        ):
            sessions.append(
                _build_session_dict(
                    agent=AGENT_COPILOT_VSCODE,
                    session_file=transcript_file,
                    workspace=workspace,
                    modified=modified,
                    skip_message_count=skip_message_count,
                )
            )
    return sorted(sessions, key=lambda item: item["modified"], reverse=True)


def copilot_vscode_scan_session_roots(
    roots: list[Path],
    pattern: str = "",
    since_date: datetime | None = None,
    until_date: datetime | None = None,
    skip_message_count: bool = False,
) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for root in roots:
        sessions.extend(
            copilot_vscode_scan_sessions(
                pattern=pattern,
                sessions_dir=root,
                since_date=since_date,
                until_date=until_date,
                skip_message_count=skip_message_count,
            )
        )
    deduped = {str(session["file"]): session for session in sessions}
    return sorted(deduped.values(), key=lambda item: item["modified"], reverse=True)


def copilot_render_markdown(
    session_file: Path,
    minimal: bool,
    messages: list[dict[str, Any]] | None,
    markdown_level: int,
    agent: str,
) -> str:
    return parse_jsonl_to_markdown(
        session_file,
        minimal,
        messages,
        agent_type=agent,
        markdown_level=markdown_level or MARKDOWN_DEFAULT_LEVEL,
    )


def copilot_message_to_unified(message: dict[str, Any]) -> dict[str, Any]:
    unified: dict[str, Any] = {
        "timestamp": message.get("timestamp", ""),
        "role": message.get("role", "assistant"),
        "content": message.get("content", ""),
    }
    if message.get("raw_event_type"):
        unified["raw_event_type"] = message["raw_event_type"]
    if message.get("model"):
        unified["model"] = message["model"]
    if message.get("usage"):
        tokens = message["usage"]
        unified["tokens"] = {
            "input": tokens.get("input_tokens", 0),
            "output": tokens.get("output_tokens", 0),
        }
    if message.get("tool_calls"):
        unified["tool_calls"] = message["tool_calls"]
    if message.get("thoughts"):
        unified["thoughts"] = message["thoughts"]
    if message.get("is_tool_call"):
        unified["tool_call"] = {
            "tool_call_id": message.get("tool_call_id"),
            "tool_name": message.get("tool_name", "unknown"),
            "input": message.get("tool_input"),
        }
    if message.get("is_tool_result"):
        unified["role"] = "system"
        unified["tool_result"] = {
            "tool_call_id": message.get("tool_call_id"),
            "tool_name": message.get("tool_name", "unknown"),
            "is_error": message.get("is_error", False),
        }
    return unified


def _flatten_int_values(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, nested in item.items():
                normalized = str(key).lower()
                if isinstance(nested, bool):
                    continue
                if isinstance(nested, int):
                    if "cache" in normalized and "read" in normalized:
                        totals["cache_read"] += nested
                    elif "cache" in normalized and (
                        "write" in normalized or "creation" in normalized or "create" in normalized
                    ):
                        totals["cache_write"] += nested
                    elif "input" in normalized or "prompt" in normalized:
                        totals["input"] += nested
                    elif "output" in normalized or "completion" in normalized:
                        totals["output"] += nested
                elif isinstance(nested, (dict, list)):
                    stack.append(nested)
        elif isinstance(item, list):
            stack.extend(item)
    return totals


def _shutdown_token_totals(session_file: Path) -> dict[str, int]:
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    for event in _read_jsonl(session_file):
        if event.get("type") != "session.shutdown":
            continue
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        flattened = _flatten_int_values(data)
        for key, value in flattened.items():
            totals[key] += value
    return totals


def copilot_extract_stats(session_file: Path, agent: str) -> tuple[dict[str, Any], list, list]:
    messages = _read_messages(session_file, agent)
    session_id = _session_id_for_file(session_file, agent)
    tool_names = _tool_name_by_call_id(session_file)
    user_messages = [msg for msg in messages if msg.get("role") == "user"]
    assistant_messages = [msg for msg in messages if msg.get("role") == "assistant"]
    timestamps = [msg["timestamp"] for msg in messages if msg.get("timestamp")]
    output_tokens = 0
    db_messages: list[dict[str, Any]] = []
    tool_uses: list[dict[str, Any]] = []

    for msg in messages:
        if msg.get("is_tool_call") or msg.get("is_tool_result"):
            tool_uses.append(
                {
                    "tool_use_id": msg.get("tool_call_id"),
                    "message_uuid": msg.get("uuid"),
                    "session_id": session_id,
                    "tool_name": tool_names.get(
                        str(msg.get("tool_call_id") or ""), msg.get("tool_name", "unknown")
                    ),
                    "is_error": 1 if msg.get("is_error") else 0,
                    "timestamp": msg.get("timestamp", ""),
                }
            )
            continue
        if msg.get("role") not in {"user", "assistant"}:
            continue
        usage = msg.get("usage") or {}
        input_count = usage.get("input_tokens", 0) or 0
        output_count = usage.get("output_tokens", 0) or 0
        output_tokens += output_count
        db_messages.append(
            {
                "uuid": msg.get("uuid"),
                "session_id": session_id,
                "parent_uuid": msg.get("parentUuid"),
                "type": msg.get("role"),
                "timestamp": msg.get("timestamp", ""),
                "model": msg.get("model"),
                "stop_reason": None,
                "input_tokens": input_count,
                "output_tokens": output_count,
                "cache_creation_tokens": 0,
                "cache_read_tokens": 0,
            }
        )

    workspace_getter = (
        copilot_cli_get_workspace_from_session
        if agent == AGENT_COPILOT_CLI
        else copilot_vscode_get_workspace_from_session
    )
    shutdown_totals = _shutdown_token_totals(session_file)
    input_tokens = shutdown_totals["input"]
    if shutdown_totals["output"]:
        output_tokens = max(output_tokens, shutdown_totals["output"])
    session_info = {
        "session_id": session_id,
        "message_count": len(user_messages) + len(assistant_messages),
        "user_messages": len(user_messages),
        "assistant_messages": len(assistant_messages),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_tokens": shutdown_totals["cache_write"],
        "cache_read_tokens": shutdown_totals["cache_read"],
        "first_timestamp": min(timestamps) if timestamps else None,
        "last_timestamp": max(timestamps) if timestamps else None,
        "cwd": workspace_getter(session_file),
        "git_branch": None,
        "claude_version": None,
        "is_agent": False,
        "parent_session_id": None,
    }
    return session_info, db_messages, tool_uses
