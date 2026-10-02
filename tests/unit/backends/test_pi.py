"""Tests for the Pi backend."""

from __future__ import annotations

import json
from pathlib import Path

from agent_history.adapters.inventory import InventoryProvider
from agent_history.backends.pi import (
    pi_count_messages,
    pi_get_home_dir,
    pi_get_workspace_from_session,
    pi_parse_jsonl_to_markdown,
    pi_read_jsonl_messages,
    pi_scan_sessions,
)
from agent_history.backends.registry import get_agent_choices, get_backend
from agent_history.scope.context import ResolutionContext


def _write_pi_session(session_file: Path) -> None:
    session_file.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {"type": "session", "id": "pi-session", "cwd": "/home/sankar/pi-project"},
        {
            "type": "message",
            "id": "u1",
            "timestamp": 1700000000000,
            "message": {"role": "user", "content": "Hello Pi"},
        },
        {
            "type": "message",
            "id": "a1",
            "parentId": "u1",
            "timestamp": 1700000001000,
            "message": {
                "role": "assistant",
                "model": "pi-model",
                "content": [
                    {"type": "text", "text": "Hello from Pi"},
                    {
                        "type": "toolCall",
                        "id": "tool-1",
                        "name": "read_file",
                        "arguments": {"path": "README.md"},
                    },
                ],
                "usage": {
                    "input": 10,
                    "output": 5,
                    "cacheWrite": 2,
                    "cacheRead": 3,
                },
            },
        },
        {
            "type": "message",
            "id": "t1",
            "parentId": "a1",
            "timestamp": 1700000002000,
            "message": {
                "role": "toolResult",
                "toolCallId": "tool-1",
                "toolName": "read_file",
                "content": "file contents",
            },
        },
    ]
    session_file.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n",
        encoding="utf-8",
    )


def test_pi_backend_is_registered() -> None:
    assert "pi" in get_agent_choices()
    assert get_backend("pi") is not None


def test_pi_read_jsonl_normalizes_roles_tool_calls_and_workspace(tmp_path: Path) -> None:
    session_file = (
        tmp_path / ".pi" / "agent" / "sessions" / "--home-sankar-pi-project--" / "session.jsonl"
    )
    _write_pi_session(session_file)

    messages, meta = pi_read_jsonl_messages(session_file)

    assert meta["id"] == "pi-session"
    assert pi_get_workspace_from_session(session_file) == "/home/sankar/pi-project"
    assert [msg["role"] for msg in messages] == ["user", "assistant", "tool"]
    assert messages[1]["tool_calls"][0]["name"] == "read_file"
    assert messages[2]["is_tool_result"] is True
    assert pi_count_messages(session_file) == 2


def test_pi_scan_sessions_uses_workspace_filters(tmp_path: Path) -> None:
    sessions_dir = tmp_path / ".pi" / "agent" / "sessions"
    session_file = sessions_dir / "--home-sankar-pi-project--" / "session.jsonl"
    _write_pi_session(session_file)

    sessions = pi_scan_sessions(pattern="pi-project", sessions_dir=sessions_dir)

    assert len(sessions) == 1
    assert sessions[0]["agent"] == "pi"
    assert sessions[0]["workspace_readable"] == "/home/sankar/pi-project"


def test_inventory_discovers_pi_sessions_from_registry(tmp_path: Path) -> None:
    sessions_dir = tmp_path / ".pi" / "agent" / "sessions"
    session_file = sessions_dir / "--home-sankar-pi-project--" / "session.jsonl"
    _write_pi_session(session_file)

    inventory = InventoryProvider(ResolutionContext(pi_sessions_dir=sessions_dir))
    sessions = inventory.list_sessions("local", agent="pi")

    assert len(sessions) == 1
    assert sessions[0]["agent"] == "pi"
    assert sessions[0]["workspace_display"] == "/home/sankar/pi-project"


def test_pi_markdown_export_includes_metadata_and_tool_calls(tmp_path: Path) -> None:
    session_file = (
        tmp_path / ".pi" / "agent" / "sessions" / "--home-sankar-pi-project--" / "session.jsonl"
    )
    _write_pi_session(session_file)

    markdown = pi_parse_jsonl_to_markdown(session_file)

    assert "# Pi Conversation" in markdown
    assert "Hello from Pi" in markdown
    assert "**[Tool: read_file]**" in markdown


def test_pi_stats_sync_uses_backend_capabilities(tmp_path: Path) -> None:
    from agent_history.storage.metrics import init_metrics_db, sync_sessions_to_db

    sessions_dir = tmp_path / ".pi" / "agent" / "sessions"
    session_file = sessions_dir / "--home-sankar-pi-project--" / "session.jsonl"
    _write_pi_session(session_file)

    conn = init_metrics_db(db_path=tmp_path / "metrics.db")
    try:
        stats = sync_sessions_to_db(conn, sessions_dir, agent="pi", force=True)
        row = conn.execute(
            """
            SELECT workspace, agent, message_count, input_tokens, output_tokens,
                   cache_creation_tokens, cache_read_tokens
            FROM sessions
            WHERE file_path = ?
            """,
            (str(session_file),),
        ).fetchone()
        tool_count = conn.execute(
            "SELECT COUNT(*) FROM tool_uses WHERE file_path = ?",
            (str(session_file),),
        ).fetchone()[0]
    finally:
        conn.close()

    assert stats == {"synced": 1, "skipped": 0, "errors": 0}
    assert row is not None
    assert row["workspace"] == "/home/sankar/pi-project"
    assert row["agent"] == "pi"
    assert row["message_count"] == 2
    assert row["input_tokens"] == 10
    assert row["output_tokens"] == 5
    assert row["cache_creation_tokens"] == 2
    assert row["cache_read_tokens"] == 3
    assert tool_count == 2


def test_pi_home_dir_uses_project_settings_session_dir(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    settings_dir = project_dir / ".pi"
    custom_sessions = settings_dir / "sessions"
    custom_sessions.mkdir(parents=True)
    (settings_dir / "settings.json").write_text(
        json.dumps({"sessionDir": "sessions"}),
        encoding="utf-8",
    )

    monkeypatch.chdir(project_dir)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "agent"))

    assert pi_get_home_dir(include_project_settings=True) == custom_sessions
