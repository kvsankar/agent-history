"""Regression tests for refreshed upstream agent session formats."""

from __future__ import annotations

import json
from pathlib import Path


def test_claude_unified_export_preserves_structured_tool_calls(tmp_path: Path) -> None:
    from agent_history.backends.claude import claude_message_to_unified, read_jsonl_messages

    session_file = tmp_path / "claude.jsonl"
    session_file.write_text(
        json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-06-04T00:00:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "I will inspect it."},
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "Read",
                            "input": {"file_path": "README.md"},
                        },
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    messages = read_jsonl_messages(session_file)
    unified = claude_message_to_unified(messages[0])

    assert unified["tool_calls"] == [
        {"name": "Read", "id": "toolu_1", "input": {"file_path": "README.md"}}
    ]


def test_codex_home_env_points_to_sessions_dir(monkeypatch, tmp_path: Path) -> None:
    from agent_history.backends.codex import codex_get_home_dir

    monkeypatch.delenv("CODEX_SESSIONS_DIR", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex-custom"))

    assert codex_get_home_dir() == tmp_path / ".codex-custom" / "sessions"


def test_codex_reads_plain_rollout_after_compressed_support(tmp_path: Path) -> None:
    from agent_history.backends.codex import codex_read_jsonl_messages

    rollout = tmp_path / "rollout-current.jsonl"
    rollout.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-04T00:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": "codex-current", "cwd": "/repo"},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-04T00:00:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "Hi"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    messages, meta = codex_read_jsonl_messages(rollout)

    assert meta["id"] == "codex-current"
    assert messages == [{"role": "user", "content": "Hi", "timestamp": "2026-06-04T00:00:01Z"}]


def test_codex_scan_discovers_compressed_rollout_names(monkeypatch, tmp_path: Path) -> None:
    from agent_history.backends import codex as codex_backend

    monkeypatch.setenv("AGENT_HISTORY_CONFIG_DIR", str(tmp_path / ".agent-history"))
    sessions_dir = tmp_path / "sessions"
    rollout = sessions_dir / "2026" / "06" / "04" / "rollout-current.jsonl.zst"
    rollout.parent.mkdir(parents=True)
    rollout.write_bytes(b"not a real zstd stream")

    monkeypatch.setattr(
        codex_backend,
        "codex_get_workspace_from_session",
        lambda path: "/home/user/current-codex",
    )

    sessions = codex_backend.codex_scan_sessions(
        sessions_dir=sessions_dir,
        skip_message_count=True,
    )

    assert len(sessions) == 1
    assert sessions[0]["file"] == rollout
    assert sessions[0]["workspace"] == "/home/user/current-codex"


def test_gemini_reads_current_jsonl_append_session(tmp_path: Path) -> None:
    from agent_history.backends.gemini import gemini_count_messages, gemini_read_json_messages

    session_file = tmp_path / "session-current.jsonl"
    records = [
        {
            "sessionId": "gemini-jsonl-1",
            "projectHash": "proj-short-id",
            "startTime": "2026-06-04T00:00:00Z",
            "lastUpdated": "2026-06-04T00:00:01Z",
            "kind": "conversation",
        },
        {
            "id": "u1",
            "timestamp": "2026-06-04T00:00:01Z",
            "type": "user",
            "content": [{"text": "Hello"}],
        },
        {
            "id": "g1",
            "timestamp": "2026-06-04T00:00:02Z",
            "type": "gemini",
            "model": "gemini-2.5-pro",
            "content": [
                {"text": "I can help."},
                {"functionCall": {"name": "read_file", "args": {"path": "README.md"}}},
            ],
            "tokens": {"input": 11, "output": 7, "cached": 3, "total": 21},
        },
        {"$rewindTo": "u1"},
        {
            "id": "g2",
            "timestamp": "2026-06-04T00:00:03Z",
            "type": "gemini",
            "content": "After rewind.",
        },
        {"$set": {"summary": "short summary", "lastUpdated": "2026-06-04T00:00:04Z"}},
    ]
    session_file.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    messages, meta = gemini_read_json_messages(session_file)

    assert meta["sessionId"] == "gemini-jsonl-1"
    assert meta["summary"] == "short summary"
    assert [message["content"] for message in messages] == ["Hello", "After rewind."]
    assert gemini_count_messages(session_file) == 2


def test_gemini_scan_discovers_jsonl_sessions(tmp_path: Path) -> None:
    from agent_history.backends.gemini import gemini_scan_sessions

    session_file = tmp_path / "project-id" / "chats" / "session-current.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_text(
        json.dumps({"sessionId": "gemini-jsonl-2", "projectHash": "project-id"}) + "\n",
        encoding="utf-8",
    )

    sessions = gemini_scan_sessions(sessions_dir=tmp_path, skip_message_count=True)

    assert len(sessions) == 1
    assert sessions[0]["file"] == session_file
    assert sessions[0]["workspace"] == "project-id"
