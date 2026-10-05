"""The stats reader reads current Gemini JSONL chats as it reads JSON chats.

Gemini CLI writes current chats as append-only JSONL: a metadata line, one
line per message, and ``$set`` and ``$rewindTo`` records. A message that
changes (a tool call finishes, say) is written again in full under the same
ID, and the later line replaces the earlier one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_history.backends.gemini import gemini_read_json_messages
from agent_history.backends.registry import get_backend
from agent_history.storage.metrics import init_metrics_db, sync_file_to_db

START = "2026-05-01T04:29:00.000Z"
T1 = "2026-05-01T04:29:01.000Z"
T2 = "2026-05-01T04:29:02.000Z"
T3 = "2026-05-01T04:29:03.000Z"
T4 = "2026-05-01T04:29:04.000Z"

FIRST_REPLY: dict[str, Any] = {
    "id": "g1",
    "type": "gemini",
    "content": "Reading it.",
    "timestamp": T2,
    "model": "gemini-x",
    "tokens": {"input": 10, "output": 5, "cached": 2, "total": 17},
}
FINISHED_FIRST_REPLY: dict[str, Any] = {
    **FIRST_REPLY,
    "toolCalls": [{"id": "t1", "name": "read_file", "status": "success", "timestamp": T2}],
}
MESSAGES: list[dict[str, Any]] = [
    {"id": "u1", "type": "user", "content": "hello", "timestamp": T1},
    FINISHED_FIRST_REPLY,
    {"id": "u2", "type": "user", "content": "more", "timestamp": T3},
    {
        "id": "g2",
        "type": "gemini",
        "content": "Done.",
        "timestamp": T4,
        "model": "gemini-y",
        "tokens": {"input": 20, "output": 7, "total": 27},
        "toolCalls": [{"id": "t2", "name": "shell", "status": "error", "timestamp": T4}],
    },
]
META = {"sessionId": "g-1", "projectHash": "hash-1", "startTime": START, "lastUpdated": T4}


def _chats(tmp_path: Path) -> Path:
    chats = tmp_path / "tmp" / "hash-1" / "chats"
    chats.mkdir(parents=True, exist_ok=True)
    return chats


def _jsonl_chat(tmp_path: Path) -> Path:
    """The chat as Gemini CLI appends it, with the first reply written twice."""
    records = [
        {**META, "lastUpdated": START, "kind": "main"},
        MESSAGES[0],
        FIRST_REPLY,
        FINISHED_FIRST_REPLY,
        MESSAGES[2],
        MESSAGES[3],
        {"$set": {"lastUpdated": T4}},
    ]
    path = _chats(tmp_path) / "session-g-1.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def _json_chat(tmp_path: Path) -> Path:
    """The same chat in the legacy single-JSON form."""
    path = _chats(tmp_path) / "session-g-1.json"
    path.write_text(json.dumps({**META, "messages": MESSAGES}), encoding="utf-8")
    return path


def _stats(path: Path):
    backend = get_backend("gemini")
    assert backend is not None
    return backend.extract_stats(path)


def test_jsonl_chat_stats_hold_its_session_messages_and_tokens(tmp_path: Path) -> None:
    session_info, messages, tool_uses = _stats(_jsonl_chat(tmp_path))

    assert session_info["session_id"] == "g-1"
    assert session_info["cwd"] == "hash-1"
    assert (session_info["first_timestamp"], session_info["last_timestamp"]) == (T1, T4)
    assert (
        session_info["message_count"],
        session_info["user_messages"],
        session_info["assistant_messages"],
    ) == (4, 2, 2)
    assert (session_info["input_tokens"], session_info["output_tokens"]) == (30, 12)
    assert [m["model"] for m in messages] == [None, "gemini-x", None, "gemini-y"]
    assert [m["cache_read_tokens"] for m in messages] == [0, 2, 0, 0]
    assert [(t["tool_use_id"], t["tool_name"], t["is_error"]) for t in tool_uses] == [
        ("t1", "read_file", 0),
        ("t2", "shell", 1),
    ]


def test_jsonl_chat_stats_match_the_same_chat_as_json(tmp_path: Path) -> None:
    jsonl_stats = _stats(_jsonl_chat(tmp_path))
    json_stats = _stats(_json_chat(tmp_path))

    assert jsonl_stats == json_stats


def test_jsonl_message_reader_keeps_the_latest_copy_of_a_message(tmp_path: Path) -> None:
    messages, meta = gemini_read_json_messages(_jsonl_chat(tmp_path))

    assert meta is not None
    assert meta["sessionId"] == "g-1"
    assert [m["content"] for m in messages] == ["hello", "Reading it.", "more", "Done."]
    assert [len(m.get("tool_calls") or []) for m in messages] == [0, 1, 0, 1]


def test_jsonl_chat_gets_a_full_metrics_row(tmp_path: Path) -> None:
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        assert sync_file_to_db(conn, _jsonl_chat(tmp_path), agent="gemini")
        row = conn.execute(
            "SELECT session_id, message_count, input_tokens, output_tokens FROM sessions"
        ).fetchone()
        models = {r[0] for r in conn.execute("SELECT model FROM messages WHERE model IS NOT NULL")}
    finally:
        conn.close()

    assert tuple(row) == ("g-1", 4, 30, 12)
    assert models == {"gemini-x", "gemini-y"}
