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


def _rewound_chat(tmp_path: Path, rewind_to: Any) -> Path:
    """The chat after the user rewinds to a message and asks again.

    Gemini CLI's ``rewindTo`` removes the named message and every later one,
    and its loader also removes every message when the ID is not found.
    """
    records = [
        META,
        *MESSAGES,
        {"$rewindTo": rewind_to},
        {"id": "u3", "type": "user", "content": "instead", "timestamp": T4},
    ]
    path = _chats(tmp_path) / "session-g-1.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def test_a_rewind_removes_the_message_it_names_and_every_later_one(tmp_path: Path) -> None:
    path = _rewound_chat(tmp_path, "u2")

    messages, _meta = gemini_read_json_messages(path)
    session_info, _messages, tool_uses = _stats(path)

    assert [m["content"] for m in messages] == ["hello", "Reading it.", "instead"]
    assert (session_info["message_count"], session_info["input_tokens"]) == (3, 10)
    assert [t["tool_use_id"] for t in tool_uses] == ["t1"]


def test_a_rewind_to_a_message_that_is_not_there_removes_every_message(tmp_path: Path) -> None:
    path = _rewound_chat(tmp_path, "not-there")

    messages, _meta = gemini_read_json_messages(path)
    session_info, _messages, _tool_uses = _stats(path)

    assert [m["content"] for m in messages] == ["instead"]
    assert (session_info["message_count"], session_info["input_tokens"]) == (1, 0)


def test_a_rewind_record_without_a_text_id_is_not_a_rewind(tmp_path: Path) -> None:
    messages, _meta = gemini_read_json_messages(_rewound_chat(tmp_path, 5))

    assert [m["content"] for m in messages] == ["hello", "Reading it.", "more", "Done.", "instead"]


def _resumed_legacy_chat(tmp_path: Path) -> Path:
    """A legacy JSON chat that Gemini CLI resumed; returns the JSONL copy.

    On resume Gemini CLI writes ``<name>.jsonl`` beside ``<name>.json``,
    holding the metadata and every message, keeps the JSON file, and
    appends later messages to the copy only.
    """
    legacy = _json_chat(tmp_path)
    records = [
        META,
        *MESSAGES,
        {"$set": {"sessionId": "g-1"}},
        {"id": "u3", "type": "user", "content": "back again", "timestamp": T4},
    ]
    copy = legacy.with_name(legacy.name + "l")
    copy.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return copy


def test_a_resumed_legacy_chat_is_listed_once_by_its_jsonl_copy(tmp_path: Path) -> None:
    from agent_history.backends.gemini import gemini_scan_sessions

    copy = _resumed_legacy_chat(tmp_path)

    sessions = gemini_scan_sessions(sessions_dir=tmp_path / "tmp")

    assert [(s["file"], s["message_count"]) for s in sessions] == [(copy, 5)]


def test_a_legacy_chat_without_a_jsonl_copy_is_listed(tmp_path: Path) -> None:
    from agent_history.backends.gemini import gemini_scan_sessions

    legacy = _json_chat(tmp_path)

    assert [s["file"] for s in gemini_scan_sessions(sessions_dir=tmp_path / "tmp")] == [legacy]


def test_syncing_a_resumed_chat_replaces_the_rows_of_its_legacy_file(tmp_path: Path) -> None:
    legacy = _json_chat(tmp_path)
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        assert sync_file_to_db(conn, legacy, agent="gemini")
        copy = _resumed_legacy_chat(tmp_path)
        assert sync_file_to_db(conn, copy, agent="gemini")
        rows = conn.execute("SELECT file_path, message_count FROM sessions").fetchall()
        message_files = {r[0] for r in conn.execute("SELECT file_path FROM messages")}
    finally:
        conn.close()

    assert [tuple(row) for row in rows] == [(str(copy), 5)]
    assert message_files == {str(copy)}
