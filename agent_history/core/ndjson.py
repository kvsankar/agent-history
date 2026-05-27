"""NDJSON core utilities with unified message records."""

from __future__ import annotations

from typing import Any

from agent_history.backends.registry import require_backend
from agent_history.core.conversation import analyze_conversation_graph

SCHEMA_VERSION = "2.0"


def build_ndjson_records(
    agent_type: str, messages: list[dict[str, Any]], session: dict[str, Any]
) -> list[dict[str, Any]]:
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
    backend = require_backend(agent_type)

    for msg in messages:
        unified = backend.message_to_unified(msg)
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
    if backend.supports_conversation_graph and messages:
        graph = analyze_conversation_graph(messages)
        if not graph.is_linear:
            session_record["forks"] = {
                "fork_points": graph.fork_points,
                "branches": graph.branches,
            }
    records.append(session_record)

    return records
