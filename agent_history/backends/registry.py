"""Internal registry for coding-agent backends.

The registry is intentionally internal for now: built-in backends register a
small capability surface, and CLI/handlers consume those capabilities instead
of branching on agent ids throughout the package.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

from agent_history.utils.paths import normalize_workspace_name
from agent_history.utils.platform import AGENT_CLAUDE, AGENT_CODEX, AGENT_GEMINI, AGENT_PI

DEFAULT_AGENT = "auto"
DEFAULT_BACKEND_ID = AGENT_CLAUDE

MessageList = List[Dict[str, Any]]
SessionList = List[Dict[str, Any]]
StatsPayload = tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]


@dataclass(frozen=True)
class AgentBackend:
    """Capability descriptor for one coding-agent session source."""

    id: str
    label: str
    get_session_dir: Callable[[Any, Any], Path | None]
    scan_sessions: Callable[[Path], SessionList]
    list_workspaces: Callable[[Path, str], list[str]]
    read_messages: Callable[[Path], MessageList]
    count_messages: Callable[[Path], int]
    render_markdown: Callable[[Path, bool, MessageList | None, int], str]
    message_to_unified: Callable[[dict[str, Any]], dict[str, Any]]
    extract_stats: Callable[[Path], StatsPayload]
    resolve_stats_workspace: Callable[[Path, dict[str, Any], str | None], str]
    file_markers: tuple[str, ...] = ()
    file_suffixes: tuple[str, ...] = ()
    supports_conversation_graph: bool = False


_BACKENDS: dict[str, AgentBackend] = {}


def register_backend(backend: AgentBackend) -> None:
    """Register or replace a backend capability descriptor."""
    _BACKENDS[backend.id] = backend


def unregister_backend(agent_id: str) -> None:
    """Remove a backend from the registry."""
    _BACKENDS.pop(agent_id, None)


def get_backend(agent_id: str | None) -> AgentBackend | None:
    """Return a backend by id, treating ``auto``/None as the default backend."""
    if agent_id in (None, DEFAULT_AGENT):
        agent_id = DEFAULT_BACKEND_ID
    return _BACKENDS.get(str(agent_id))


def require_backend(agent_id: str | None) -> AgentBackend:
    """Return a backend or raise a clear error for unsupported agents."""
    backend = get_backend(agent_id)
    if backend is None:
        raise KeyError(f"Unsupported agent backend: {agent_id}")
    return backend


def iter_backends(agent_id: str | None = None) -> Iterable[AgentBackend]:
    """Iterate selected backends, or all registered backends for auto/None."""
    if agent_id in (None, DEFAULT_AGENT):
        return tuple(_BACKENDS.values())
    backend = get_backend(agent_id)
    return (backend,) if backend else ()


def get_agent_choices(include_auto: bool = True) -> tuple[str, ...]:
    """Return CLI agent choices from registered backends."""
    choices = tuple(_BACKENDS.keys())
    if include_auto:
        return (DEFAULT_AGENT, *choices)
    return choices


def get_default_backend_id() -> str:
    """Return the fallback backend id for legacy/default behavior."""
    return DEFAULT_BACKEND_ID


def infer_backend_from_file(session_file: Path) -> AgentBackend:
    """Infer a backend from a local session file path."""
    parts = set(session_file.parts)
    suffix = session_file.suffix.lower()
    for backend in _BACKENDS.values():
        if backend.file_markers and any(marker in parts for marker in backend.file_markers):
            return backend
    for backend in _BACKENDS.values():
        if suffix and suffix in backend.file_suffixes:
            return backend
    return require_backend(DEFAULT_BACKEND_ID)


def _workspace_names_from_sessions(sessions: SessionList) -> list[str]:
    return sorted(
        {
            (
                s.get("workspace_key") or s.get("workspace_readable") or s.get("workspace", "")
            ).strip()
            for s in sessions
            if s
        }
        - {""}
    )


def _claude_session_dir(resolver: Any, context: Any) -> Path | None:
    return resolver.get_claude_dir(context)


def _claude_scan_sessions(projects_dir: Path) -> SessionList:
    from agent_history.backends.claude import get_workspace_sessions

    return get_workspace_sessions(
        workspace_pattern="*",
        projects_dir=projects_dir,
        skip_message_count=True,
    )


def _claude_list_workspaces(projects_dir: Path, home: str) -> list[str]:
    verify_local = home == "local"
    if os.environ.get("AGENT_HISTORY_TEST_MODE") and os.environ.get("CLAUDE_WINDOWS_PROJECTS_DIR"):
        verify_local = False

    workspaces: list[str] = []
    for entry in projects_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            workspaces.append(normalize_workspace_name(entry.name, verify_local=verify_local))
    return workspaces


def _claude_read_messages(session_file: Path) -> MessageList:
    from agent_history.backends.claude import read_jsonl_messages

    return read_jsonl_messages(session_file)


def _claude_count_messages(session_file: Path) -> int:
    from agent_history.backends.claude import _count_file_messages

    return _count_file_messages(session_file, skip_count=False, use_cached_counts=True)


def _claude_render_markdown(
    session_file: Path,
    minimal: bool,
    messages: MessageList | None,
    markdown_level: int,
) -> str:
    from agent_history.export.markdown import parse_jsonl_to_markdown

    return parse_jsonl_to_markdown(
        session_file,
        minimal,
        messages,
        agent_type=AGENT_CLAUDE,
        markdown_level=markdown_level,
    )


def _claude_message_to_unified(message: dict[str, Any]) -> dict[str, Any]:
    from agent_history.backends.claude import claude_message_to_unified

    return claude_message_to_unified(message)


def _claude_extract_stats(session_file: Path) -> StatsPayload:
    from agent_history.storage.metrics import _parse_claude_jsonl

    return _parse_claude_jsonl(session_file)


def _claude_resolve_stats_workspace(
    session_file: Path, session_info: dict[str, Any], workspace: str | None
) -> str:
    del session_info
    return workspace or session_file.parent.name


def _codex_session_dir(resolver: Any, context: Any) -> Path | None:
    return resolver.get_codex_dir(context)


def _codex_scan_sessions(sessions_dir: Path) -> SessionList:
    from agent_history.backends.codex import codex_scan_sessions

    return codex_scan_sessions(pattern="", sessions_dir=sessions_dir, skip_message_count=True)


def _codex_list_workspaces(sessions_dir: Path, home: str) -> list[str]:
    del home
    return _workspace_names_from_sessions(_codex_scan_sessions(sessions_dir))


def _codex_read_messages(session_file: Path) -> MessageList:
    from agent_history.backends.codex import codex_read_jsonl_messages

    messages, _ = codex_read_jsonl_messages(session_file)
    return messages


def _codex_count_messages(session_file: Path) -> int:
    from agent_history.backends.codex import codex_count_messages

    return codex_count_messages(session_file)


def _codex_render_markdown(
    session_file: Path,
    minimal: bool,
    messages: MessageList | None,
    markdown_level: int,
) -> str:
    from agent_history.export.markdown import MARKDOWN_DEFAULT_LEVEL, parse_jsonl_to_markdown

    if markdown_level < MARKDOWN_DEFAULT_LEVEL:
        return parse_jsonl_to_markdown(
            session_file,
            minimal,
            messages,
            agent_type=AGENT_CODEX,
            markdown_level=markdown_level,
        )

    from agent_history.backends.codex import codex_parse_jsonl_to_markdown

    return codex_parse_jsonl_to_markdown(session_file, minimal)


def _codex_message_to_unified(message: dict[str, Any]) -> dict[str, Any]:
    from agent_history.backends.codex import codex_message_to_unified

    return codex_message_to_unified(message)


def _codex_extract_stats(session_file: Path) -> StatsPayload:
    from agent_history.storage.metrics import _parse_codex_jsonl

    return _parse_codex_jsonl(session_file)


def _codex_resolve_stats_workspace(
    session_file: Path, session_info: dict[str, Any], workspace: str | None
) -> str:
    del session_file
    return session_info.get("cwd") or workspace or "unknown"


def _gemini_session_dir(resolver: Any, context: Any) -> Path | None:
    return resolver.get_gemini_dir(context)


def _gemini_scan_sessions(sessions_dir: Path) -> SessionList:
    from agent_history.backends.gemini import gemini_scan_sessions

    return gemini_scan_sessions(pattern="", sessions_dir=sessions_dir, skip_message_count=True)


def _gemini_list_workspaces(sessions_dir: Path, home: str) -> list[str]:
    del home
    return _workspace_names_from_sessions(_gemini_scan_sessions(sessions_dir))


def _gemini_read_messages(session_file: Path) -> MessageList:
    from agent_history.backends.gemini import gemini_read_json_messages

    messages, _ = gemini_read_json_messages(session_file)
    return messages


def _gemini_count_messages(session_file: Path) -> int:
    from agent_history.backends.gemini import gemini_count_messages

    return gemini_count_messages(session_file)


def _gemini_render_markdown(
    session_file: Path,
    minimal: bool,
    messages: MessageList | None,
    markdown_level: int,
) -> str:
    from agent_history.export.markdown import MARKDOWN_DEFAULT_LEVEL, parse_jsonl_to_markdown

    if markdown_level < MARKDOWN_DEFAULT_LEVEL:
        return parse_jsonl_to_markdown(
            session_file,
            minimal,
            messages,
            agent_type=AGENT_GEMINI,
            markdown_level=markdown_level,
        )

    from agent_history.backends.gemini import gemini_parse_json_to_markdown

    return gemini_parse_json_to_markdown(session_file, minimal)


def _gemini_message_to_unified(message: dict[str, Any]) -> dict[str, Any]:
    from agent_history.backends.gemini import _gemini_message_to_unified

    return _gemini_message_to_unified(message)


def _gemini_extract_stats(session_file: Path) -> StatsPayload:
    from agent_history.storage.metrics import _parse_gemini_json

    return _parse_gemini_json(session_file)


def _gemini_resolve_stats_workspace(
    session_file: Path, session_info: dict[str, Any], workspace: str | None
) -> str:
    from agent_history.backends.gemini import (
        gemini_get_hash_index_file,
        gemini_get_legacy_hash_index_file,
        gemini_get_path_for_hash,
    )

    del session_info
    hash_dir = session_file.parent.parent
    project_hash = hash_dir.name if hash_dir.name else None
    if project_hash:
        resolved = gemini_get_path_for_hash(project_hash)
        if resolved:
            return resolved
        for index_file in (gemini_get_hash_index_file(), gemini_get_legacy_hash_index_file()):
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            resolved = data.get("hashes", {}).get(project_hash)
            if resolved:
                return resolved
    return workspace or session_file.parent.name


def _pi_session_dir(resolver: Any, context: Any) -> Path | None:
    return resolver.get_pi_dir(context)


def _pi_scan_sessions(sessions_dir: Path) -> SessionList:
    from agent_history.backends.pi import pi_scan_sessions

    return pi_scan_sessions(pattern="", sessions_dir=sessions_dir, skip_message_count=True)


def _pi_list_workspaces(sessions_dir: Path, home: str) -> list[str]:
    del home
    return _workspace_names_from_sessions(_pi_scan_sessions(sessions_dir))


def _pi_read_messages(session_file: Path) -> MessageList:
    from agent_history.backends.pi import pi_read_jsonl_messages

    messages, _ = pi_read_jsonl_messages(session_file)
    return messages


def _pi_count_messages(session_file: Path) -> int:
    from agent_history.backends.pi import pi_count_messages

    return pi_count_messages(session_file)


def _pi_render_markdown(
    session_file: Path,
    minimal: bool,
    messages: MessageList | None,
    markdown_level: int,
) -> str:
    from agent_history.backends.pi import pi_render_markdown

    return pi_render_markdown(session_file, minimal, messages, markdown_level)


def _pi_message_to_unified(message: dict[str, Any]) -> dict[str, Any]:
    from agent_history.backends.pi import pi_message_to_unified

    return pi_message_to_unified(message)


def _empty_session_info() -> dict[str, Any]:
    return {
        "session_id": None,
        "message_count": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "first_timestamp": None,
        "last_timestamp": None,
        "cwd": None,
        "git_branch": None,
        "claude_version": None,
        "is_agent": False,
        "parent_session_id": None,
    }


def _pi_extract_stats(session_file: Path) -> StatsPayload:
    from agent_history.backends.pi import pi_read_jsonl_messages

    messages, session_meta = pi_read_jsonl_messages(session_file)
    session_info = _empty_session_info()
    session_info["session_id"] = (session_meta or {}).get("id")
    session_info["cwd"] = (session_meta or {}).get("cwd") or (session_meta or {}).get("workspace")

    db_messages: list[dict[str, Any]] = []
    tool_uses: list[dict[str, Any]] = []
    timestamps: list[str] = []

    for msg in messages:
        role = msg.get("role")
        timestamp = msg.get("timestamp", "")
        if timestamp:
            timestamps.append(timestamp)

        for tool_call in msg.get("tool_calls", []):
            tool_uses.append(
                {
                    "tool_use_id": tool_call.get("id"),
                    "message_uuid": msg.get("id"),
                    "session_id": session_info["session_id"],
                    "tool_name": tool_call.get("name", "unknown"),
                    "is_error": 0,
                    "timestamp": timestamp,
                }
            )

        if msg.get("is_tool_result"):
            tool_uses.append(
                {
                    "tool_use_id": msg.get("tool_call_id"),
                    "message_uuid": msg.get("id"),
                    "session_id": session_info["session_id"],
                    "tool_name": msg.get("tool_name", "unknown"),
                    "is_error": 1 if msg.get("is_error") else 0,
                    "timestamp": timestamp,
                }
            )
            continue

        if role not in ("user", "assistant"):
            continue

        tokens = msg.get("tokens") or {}
        input_tokens = tokens.get("input", 0) or 0
        output_tokens = tokens.get("output", 0) or 0
        cache_creation = tokens.get("cacheWrite", 0) or 0
        cache_read = tokens.get("cacheRead", 0) or 0

        session_info["message_count"] += 1
        if role == "user":
            session_info["user_messages"] += 1
        else:
            session_info["assistant_messages"] += 1
        session_info["input_tokens"] += input_tokens
        session_info["output_tokens"] += output_tokens
        session_info["cache_creation_tokens"] += cache_creation
        session_info["cache_read_tokens"] += cache_read

        db_messages.append(
            {
                "uuid": msg.get("id"),
                "session_id": session_info["session_id"],
                "parent_uuid": msg.get("parent_id"),
                "type": role,
                "timestamp": timestamp,
                "model": msg.get("model"),
                "stop_reason": None,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_tokens": cache_creation,
                "cache_read_tokens": cache_read,
            }
        )

    if timestamps:
        session_info["first_timestamp"] = min(timestamps)
        session_info["last_timestamp"] = max(timestamps)

    return session_info, db_messages, tool_uses


def _pi_resolve_stats_workspace(
    session_file: Path, session_info: dict[str, Any], workspace: str | None
) -> str:
    from agent_history.backends.pi import pi_get_workspace_from_session

    return session_info.get("cwd") or workspace or pi_get_workspace_from_session(session_file)


register_backend(
    AgentBackend(
        id=AGENT_CLAUDE,
        label="Claude Code",
        get_session_dir=_claude_session_dir,
        scan_sessions=_claude_scan_sessions,
        list_workspaces=_claude_list_workspaces,
        read_messages=_claude_read_messages,
        count_messages=_claude_count_messages,
        render_markdown=_claude_render_markdown,
        message_to_unified=_claude_message_to_unified,
        extract_stats=_claude_extract_stats,
        resolve_stats_workspace=_claude_resolve_stats_workspace,
        file_markers=(".claude",),
        file_suffixes=(".jsonl",),
        supports_conversation_graph=True,
    )
)
register_backend(
    AgentBackend(
        id=AGENT_CODEX,
        label="Codex CLI",
        get_session_dir=_codex_session_dir,
        scan_sessions=_codex_scan_sessions,
        list_workspaces=_codex_list_workspaces,
        read_messages=_codex_read_messages,
        count_messages=_codex_count_messages,
        render_markdown=_codex_render_markdown,
        message_to_unified=_codex_message_to_unified,
        extract_stats=_codex_extract_stats,
        resolve_stats_workspace=_codex_resolve_stats_workspace,
        file_markers=(".codex",),
        file_suffixes=(".jsonl",),
    )
)
register_backend(
    AgentBackend(
        id=AGENT_GEMINI,
        label="Gemini CLI",
        get_session_dir=_gemini_session_dir,
        scan_sessions=_gemini_scan_sessions,
        list_workspaces=_gemini_list_workspaces,
        read_messages=_gemini_read_messages,
        count_messages=_gemini_count_messages,
        render_markdown=_gemini_render_markdown,
        message_to_unified=_gemini_message_to_unified,
        extract_stats=_gemini_extract_stats,
        resolve_stats_workspace=_gemini_resolve_stats_workspace,
        file_markers=(".gemini",),
        file_suffixes=(".json",),
    )
)
register_backend(
    AgentBackend(
        id=AGENT_PI,
        label="Pi",
        get_session_dir=_pi_session_dir,
        scan_sessions=_pi_scan_sessions,
        list_workspaces=_pi_list_workspaces,
        read_messages=_pi_read_messages,
        count_messages=_pi_count_messages,
        render_markdown=_pi_render_markdown,
        message_to_unified=_pi_message_to_unified,
        extract_stats=_pi_extract_stats,
        resolve_stats_workspace=_pi_resolve_stats_workspace,
        file_markers=(".pi",),
        file_suffixes=(".jsonl",),
    )
)
