"""NDJSON core utilities with unified message records."""

from __future__ import annotations

from typing import Any, Dict, List

from agent_history.backends.claude import claude_message_to_unified
from agent_history.core.conversation import analyze_conversation_graph
from agent_history.backends.codex import codex_message_to_unified
from agent_history.backends.gemini import _gemini_message_to_unified
from agent_history.utils.platform import AGENT_CLAUDE, AGENT_CODEX, AGENT_GEMINI


SCHEMA_VERSION = "2.0"


def build_ndjson_records(
    agent_type: str, messages: List[Dict[str, Any]], session: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Build NDJSON records with a unified message schema.

    Args:
        agent_type: Agent type (claude, codex, gemini).
        messages: Parsed message list for the session.
        session: Session metadata dict.

    Returns:
        List of NDJSON-ready records (header + messages + session summary).
    """
    header = {
        "type": "header",
        "schema_version": SCHEMA_VERSION,
        "agent": agent_type,
        "session_file": session.get("filename", session.get("file", "")),
    }

    session_id = session.get("session_id") or session.get("id")
    if session_id:
        header["session_id"] = session_id

    workspace = session.get("workspace_readable") or session.get("workspace")
    if workspace:
        header["workspace"] = workspace

    records = [header]

    for msg in messages:
        unified = _normalize_message(agent_type, msg)
        unified["type"] = "message"
        if session_id:
            unified["session_id"] = session_id
        records.append(unified)

    session_record = {
        "type": "session",
        "agent": agent_type,
        "session_id": session_id or "",
        "message_count": len(messages),
        "workspace": workspace or "",
    }
    if agent_type == AGENT_CLAUDE and messages:
        graph = analyze_conversation_graph(messages)
        if not graph.is_linear:
            session_record["forks"] = {
                "fork_points": graph.fork_points,
                "branches": graph.branches,
            }
    records.append(session_record)

    return records


def _normalize_message(agent_type: str, msg: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a message to unified schema based on agent type."""
    if agent_type == AGENT_CODEX:
        return codex_message_to_unified(msg)
    if agent_type == AGENT_GEMINI:
        return _gemini_message_to_unified(msg)
    return claude_message_to_unified(msg)
