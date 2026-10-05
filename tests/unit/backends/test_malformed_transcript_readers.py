"""The list, export, message and stats readers skip transcript lines they cannot use.

A line can carry a byte that is not UTF-8, be valid JSON that is not an
object, nest too deeply to parse, or hold a string where an object is
expected. One such line must not stop a reader: it skips the line, or
decodes the bad byte as U+FFFD, and reads the rest of the file. A value of
the wrong type is ignored (a token count or timestamp) or stored as text
(an ID, model or tool name).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from agent_history.backends.claude import (
    _count_file_messages,
    get_first_timestamp,
    read_jsonl_messages,
)
from agent_history.backends.codex import (
    codex_count_messages,
    codex_extract_metrics_from_jsonl,
    codex_get_first_timestamp,
    codex_get_workspace_from_session,
    codex_parse_jsonl_to_markdown,
    codex_read_jsonl_messages,
)
from agent_history.backends.copilot import (
    copilot_cli_get_workspace_from_session,
    copilot_cli_read_messages,
    copilot_count_messages,
    copilot_extract_stats,
    copilot_render_markdown,
    copilot_vscode_get_workspace_from_session,
)
from agent_history.backends.gemini import gemini_get_first_timestamp, gemini_read_json_messages
from agent_history.backends.pi import pi_get_workspace_from_session, pi_read_jsonl_messages
from agent_history.backends.registry import get_backend
from agent_history.core.lineage import (
    extract_claude_lineage,
    extract_codex_lineage,
    extract_gemini_lineage,
    extract_pi_lineage,
)
from agent_history.handlers.export import SessionExportHandler
from agent_history.storage.metrics import init_metrics_db, sync_file_to_db
from agent_history.utils.platform import AGENT_COPILOT_CLI

REPLACED = "caf�"
START = "2026-05-01T04:29:00.000Z"
LATER = "2026-05-01T04:29:05.000Z"


def _line(value: Any) -> bytes:
    return json.dumps(value).encode("utf-8") + b"\n"


def _non_objects() -> bytes:
    return _line([1, 2]) + _line(None) + _line("text") + _line(3) + b"not json\n"


def _codex_item(payload: Any) -> bytes:
    return _line({"type": "response_item", "timestamp": LATER, "payload": payload})


def _codex_rollout(tmp_path: Path) -> Path:
    """A rollout whose first line and a later line carry a byte that is not UTF-8."""
    session_file = tmp_path / "rollout-2026-05-01T04-29-00-c-1.jsonl"
    session_file.write_bytes(
        b'{"type": "session_meta", "timestamp": "' + START.encode() + b'", '
        b'"payload": {"id": "c-1", "cwd": "/home/alex", "originator": "caf\xff"}}\n'
        + _non_objects()
        + _line({"type": "session_meta", "payload": None})
        + _line({"type": "turn_context", "payload": "model"})
        + _line({"type": "event_msg", "payload": "x"})
        + _line({"type": "event_msg", "payload": {"type": "token_count", "info": "x"}})
        + _codex_item(None)
        + _codex_item("message")
        + _codex_item({"type": "message", "role": "user", "content": 5})
        + b'{"type": "response_item", "payload": {"type": "message", "role": "user", '
        b'"content": "caf\xff"}}\n'
        + _codex_item(
            {
                "type": "message",
                "role": "assistant",
                "content": [3, None, {"type": "output_text", "text": "ok"}],
            }
        )
        + _codex_item({"type": "function_call", "name": "shell", "arguments": "{}", "call_id": "k"})
        + _line({"type": "turn_context", "payload": {"model": "model-1"}})
    )
    return session_file


def _codex_header_cases(tmp_path: Path) -> dict[str, Path]:
    """Rollouts whose session_meta is not cleanly the first line."""
    day = tmp_path / "sessions" / "2026" / "05" / "01"
    day.mkdir(parents=True)
    meta = {
        "type": "session_meta",
        "timestamp": START,
        "payload": {"id": "c-2", "cwd": "/home/alex"},
    }
    cases = {
        "byte order mark": b"\xef\xbb\xbf" + _line(meta),
        "non-object first line": _line([1]) + _line(meta),
        "bad byte in the first line": b'{"type": "session_meta", "timestamp": "'
        + START.encode()
        + b'", "payload": {"id": "c-2", "cwd": "/home/alex", "note": "\xff"}}\n',
    }
    paths = {}
    for index, (name, content) in enumerate(cases.items()):
        path = day / f"rollout-2026-05-01T04-29-0{index}-c-2.jsonl"
        path.write_bytes(content)
        paths[name] = path
    return paths


def test_codex_message_reader_skips_lines_it_cannot_use(tmp_path: Path) -> None:
    messages, session_meta = codex_read_jsonl_messages(_codex_rollout(tmp_path))

    assert session_meta is not None
    assert session_meta["id"] == "c-1"
    assert [(message["role"], message["content"]) for message in messages[:3]] == [
        ("user", ""),
        ("user", REPLACED),
        ("assistant", "ok"),
    ]
    assert messages[3]["is_tool_call"] is True
    assert len(messages) == 4


def test_codex_markdown_export_reads_past_a_bad_byte(tmp_path: Path) -> None:
    markdown = codex_parse_jsonl_to_markdown(_codex_rollout(tmp_path))

    assert REPLACED in markdown
    assert "`c-1`" in markdown


def test_codex_count_and_metrics_skip_lines_they_cannot_use(tmp_path: Path) -> None:
    rollout = _codex_rollout(tmp_path)

    assert codex_count_messages(rollout) == 3
    metrics = codex_extract_metrics_from_jsonl(rollout)
    assert metrics["session"]["id"] == "c-1"
    assert metrics["session"]["model"] == "model-1"
    assert len(metrics["messages"]) == 3
    assert [tool["name"] for tool in metrics["tool_uses"]] == ["shell"]


def test_codex_list_readers_find_the_header_past_unusable_lines(tmp_path: Path) -> None:
    for name, rollout in _codex_header_cases(tmp_path).items():
        assert codex_get_workspace_from_session(rollout) == "/home/alex", name
        assert codex_get_first_timestamp(rollout) == START, name


def test_codex_export_lineage_header_reads_past_unusable_lines(tmp_path: Path) -> None:
    handler = SessionExportHandler.__new__(SessionExportHandler)

    for name, rollout in _codex_header_cases(tmp_path).items():
        header = handler._read_codex_lineage_header(rollout)
        assert header is not None, name
        assert (header["kind"], header["session_id"]) == ("main", "c-2"), name


def _claude_session(tmp_path: Path) -> Path:
    def entry(entry_type: str, message: Any, uuid: str) -> dict[str, Any]:
        return {
            "type": entry_type,
            "sessionId": "s-1",
            "uuid": uuid,
            "timestamp": LATER,
            "message": message,
        }

    session_file = tmp_path / "project" / "s-1.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_bytes(
        _non_objects()
        + b'{"type": "user", "sessionId": "s-1", "timestamp": "'
        + START.encode()
        + b'", "message": {"role": "user", "content": "caf\xff"}}\n'
        + _line(entry("assistant", "plain text", "u-2"))
        + _line(entry("assistant", {"role": "assistant", "content": [3, None]}, "u-3"))
        + _line(
            entry(
                "assistant",
                {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
                "u-4",
            )
        )
    )
    return session_file


def test_claude_message_reader_skips_lines_it_cannot_use(tmp_path: Path) -> None:
    messages = read_jsonl_messages(_claude_session(tmp_path), quiet=True)

    assert [(message["role"], message["content"]) for message in messages] == [
        ("user", REPLACED),
        ("assistant", "[No content]"),
        ("assistant", "[No content]"),
        ("assistant", "ok"),
    ]


def test_claude_list_readers_skip_lines_they_cannot_use(tmp_path: Path) -> None:
    session_file = _claude_session(tmp_path)

    assert get_first_timestamp(session_file) == START
    assert _count_file_messages(session_file, skip_count=False) == 4


def _gemini_session(tmp_path: Path) -> Path:
    session_file = tmp_path / "chats" / "session-g-1.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_bytes(
        _non_objects()
        + _line({"sessionId": "g-1", "startTime": START})
        + _line({"$set": {"messages": [3, {"type": "user", "content": "first"}]}})
        + b'{"type": "user", "timestamp": "'
        + LATER.encode()
        + b'", "content": "caf\xff"}\n'
        + _line({"$rewindTo": "missing"})
    )
    return session_file


def test_gemini_jsonl_readers_skip_lines_they_cannot_use(tmp_path: Path) -> None:
    session_file = _gemini_session(tmp_path)

    messages, session_meta = gemini_read_json_messages(session_file)

    assert session_meta is not None
    assert session_meta["sessionId"] == "g-1"
    assert [message["content"] for message in messages] == ["first", REPLACED]
    assert gemini_get_first_timestamp(session_file) == START


def test_gemini_json_reader_decodes_a_bad_byte(tmp_path: Path) -> None:
    session_file = tmp_path / "session-g-2.json"
    session_file.write_bytes(
        b'{"sessionId": "g-2", "startTime": "'
        + START.encode()
        + b'", "messages": [3, {"type": "user", "content": "caf\xff"}]}'
    )
    not_an_object = tmp_path / "session-g-3.json"
    not_an_object.write_bytes(b"[1, 2]")

    messages, session_meta = gemini_read_json_messages(session_file)

    assert session_meta is not None
    assert session_meta["sessionId"] == "g-2"
    assert [message["content"] for message in messages] == [REPLACED]
    assert gemini_get_first_timestamp(session_file) == START
    assert gemini_read_json_messages(not_an_object) == ([], None)
    assert gemini_get_first_timestamp(not_an_object) is None


def _pi_session(tmp_path: Path) -> Path:
    session_file = tmp_path / "--home-alex-project--" / "p-1.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_bytes(
        _non_objects()
        + _line({"type": "session", "id": "p-1", "cwd": "/home/alex/project"})
        + b'{"type": "message", "id": "m-1", "timestamp": "'
        + START.encode()
        + b'", "message": {"role": "user", "content": "caf\xff"}}\n'
        + _line(
            {
                "type": "message",
                "id": "m-2",
                "parentId": "m-1",
                "message": {"role": "assistant", "content": "ok", "metadata": "x"},
            }
        )
    )
    return session_file


def test_pi_readers_skip_lines_they_cannot_use(tmp_path: Path) -> None:
    session_file = _pi_session(tmp_path)

    messages, session_meta = pi_read_jsonl_messages(session_file)

    assert session_meta is not None
    assert session_meta["id"] == "p-1"
    assert [(message["role"], message["content"]) for message in messages] == [
        ("user", REPLACED),
        ("assistant", "ok"),
    ]
    assert pi_get_workspace_from_session(session_file) == "/home/alex/project"


def test_gemini_lineage_skips_lines_it_cannot_use(tmp_path: Path) -> None:
    records = extract_gemini_lineage(_gemini_session(tmp_path))

    assert [(record["kind"], record["session_id"]) for record in records] == [("main", "g-1")]


def test_gemini_json_lineage_decodes_a_bad_byte(tmp_path: Path) -> None:
    session_file = tmp_path / "session-g-2.json"
    session_file.write_bytes(
        b'{"sessionId": "g-2", "messages": [3, {"type": "gemini", "content": "caf\xff", '
        b'"toolCalls": [5, {"id": "t-1", "displayName": "Code Agent"}]}]}'
    )

    records = extract_gemini_lineage(session_file)

    assert [(record["kind"], record["session_id"]) for record in records] == [
        ("main", "g-2"),
        ("subagent", "g-2:t-1"),
    ]


def test_pi_lineage_skips_lines_it_cannot_use(tmp_path: Path) -> None:
    records = extract_pi_lineage(_pi_session(tmp_path))

    assert [(record["kind"], record["session_id"]) for record in records] == [("main", "p-1")]


def _copilot_event(event_type: str, data: Any, event_id: str) -> bytes:
    return _line({"type": event_type, "id": event_id, "timestamp": LATER, "data": data})


def _copilot_cli_session(tmp_path: Path) -> Path:
    """A Copilot CLI session with bad bytes, non-object lines and odd nested values."""
    session_dir = tmp_path / "session-state" / "cli-1"
    session_dir.mkdir(parents=True)
    (session_dir / "workspace.yaml").write_bytes(b"cwd: /home/alex/project\nname: caf\xff\n")
    events_file = session_dir / "events.jsonl"
    events_file.write_bytes(
        _non_objects()
        + b'{"type": "user.message", "id": "e-1", "timestamp": "'
        + START.encode()
        + b'", "data": {"content": "caf\xff"}}\n'
        + _copilot_event("user.message", [1, 2], "e-2")
        + _copilot_event("assistant.message", "text", "e-3")
        + _copilot_event(
            "assistant.message",
            {"content": "ok", "model": "model-1", "outputTokens": 4, "toolRequests": [3, None]},
            "e-4",
        )
        + _copilot_event("tool.execution_start", {"toolCallId": "k", "toolName": "shell"}, "e-5")
        + _copilot_event("session.shutdown", [5], "e-6")
    )
    return events_file


def test_copilot_readers_read_past_a_bad_byte(tmp_path: Path) -> None:
    events_file = _copilot_cli_session(tmp_path)

    messages = copilot_cli_read_messages(events_file)
    session_info, db_messages, tool_uses = copilot_extract_stats(events_file, AGENT_COPILOT_CLI)

    visible = [m for m in messages if m["role"] in ("user", "assistant")]
    assert [(m["role"], m["content"]) for m in visible] == [
        ("user", REPLACED),
        ("user", ""),
        ("assistant", ""),
        ("assistant", "ok"),
    ]
    assert copilot_count_messages(events_file) == 4
    assert copilot_cli_get_workspace_from_session(events_file) == "/home/alex/project"
    assert (session_info["message_count"], session_info["output_tokens"]) == (4, 4)
    assert session_info["first_timestamp"] == START
    assert [m["model"] for m in db_messages] == [None, None, None, "model-1"]
    assert [t["tool_name"] for t in tool_uses] == ["shell"]
    assert "ok" in copilot_render_markdown(events_file, False, messages, 4, AGENT_COPILOT_CLI)


def test_copilot_vscode_workspace_reader_reads_past_a_bad_byte(tmp_path: Path) -> None:
    storage = tmp_path / "workspaceStorage" / "abc"
    transcript = storage / "GitHub.copilot-chat" / "transcripts" / "t-1.jsonl"
    transcript.parent.mkdir(parents=True)
    (storage / "workspace.json").write_bytes(
        b'{"folder": "file:///home/alex/project", "note": "caf\xff"}'
    )
    transcript.write_bytes(_copilot_event("user.message", {"content": "hi"}, "e-1"))

    assert copilot_vscode_get_workspace_from_session(transcript) == "/home/alex/project"
    assert copilot_count_messages(transcript) == 1


# A line nested more deeply than the JSON decoder's recursion limit
DEEP = b"[" * 100_000 + b"]" * 100_000 + b"\n"

CODEX_META = {"type": "session_meta", "timestamp": START, "payload": {"id": "c-1", "cwd": "/w"}}

# For each agent: where its session file lives and one usable user message
_AGENT_FILES: dict[str, tuple[str, bytes]] = {
    "claude": (
        "projects/-w/s-1.jsonl",
        _line(
            {
                "type": "user",
                "sessionId": "s-1",
                "timestamp": START,
                "message": {"role": "user", "content": "hi"},
            }
        ),
    ),
    "codex": (
        "sessions/2026/05/01/rollout-2026-05-01T04-29-00-c-1.jsonl",
        _line(CODEX_META) + _codex_item({"type": "message", "role": "user", "content": "hi"}),
    ),
    "gemini": (
        "tmp/h/chats/session-g-1.jsonl",
        _line({"sessionId": "g-1"})
        + _line({"id": "m-1", "type": "user", "content": "hi", "timestamp": START}),
    ),
    "pi": (
        "sessions/--w--/p-1.jsonl",
        _line({"type": "session", "id": "p-1"})
        + _line({"type": "message", "id": "m-1", "message": {"role": "user", "content": "hi"}}),
    ),
    "copilot-cli": (
        "session-state/c-1/events.jsonl",
        _copilot_event("user.message", {"content": "hi"}, "e-1"),
    ),
}

_LINEAGE_READERS = {
    "claude": extract_claude_lineage,
    "codex": extract_codex_lineage,
    "gemini": extract_gemini_lineage,
    "pi": extract_pi_lineage,
}


def _write_session(tmp_path: Path, agent: str, content: bytes) -> Path:
    path = tmp_path / _AGENT_FILES[agent][0]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _assert_bindable(payload: Any) -> None:
    """Every value a stats reader returns can be stored in SQLite as it is."""
    session_info, messages, tool_uses = payload
    conn = sqlite3.connect(":memory:")
    for row in (session_info, *messages, *tool_uses):
        names = ", ".join(f"c{i}" for i in range(len(row)))
        conn.execute(f"CREATE TABLE IF NOT EXISTS t{len(row)} ({names})")
        marks = ", ".join("?" * len(row))
        conn.execute(f"INSERT INTO t{len(row)} VALUES ({marks})", tuple(row.values()))
    conn.close()


def _synced_rows(tmp_path: Path, session_file: Path, agent: str) -> dict[str, list[tuple]]:
    conn = init_metrics_db(tmp_path / f"metrics-{agent}.db")
    try:
        assert sync_file_to_db(conn, session_file, force=True, agent=agent)
        return {
            "sessions": [
                tuple(row)
                for row in conn.execute(
                    "SELECT session_id, cwd, message_count, input_tokens, output_tokens,"
                    " first_timestamp, last_timestamp FROM sessions"
                )
            ],
            "messages": [
                tuple(row) for row in conn.execute("SELECT uuid, timestamp, model FROM messages")
            ],
            "tool_uses": [
                tuple(row)
                for row in conn.execute("SELECT tool_use_id, tool_name, is_error FROM tool_uses")
            ],
        }
    finally:
        conn.close()


@pytest.mark.parametrize("agent", sorted(_AGENT_FILES))
def test_every_reader_skips_a_deeply_nested_line(tmp_path: Path, agent: str) -> None:
    session_file = _write_session(tmp_path, agent, DEEP + _AGENT_FILES[agent][1])
    backend = get_backend(agent)
    assert backend is not None

    messages = backend.read_messages(session_file)
    assert [m["content"] for m in messages if m.get("role") == "user"] == ["hi"]
    assert backend.count_messages(session_file) == 1
    assert backend.render_markdown(session_file, False, messages, 4)
    stats = backend.extract_stats(session_file)
    assert stats[0]["message_count"] == 1
    assert _synced_rows(tmp_path, session_file, agent)["sessions"][0][2] == 1
    if agent in _LINEAGE_READERS:
        _LINEAGE_READERS[agent](session_file)


def test_gemini_json_reader_treats_a_deeply_nested_file_as_unreadable(tmp_path: Path) -> None:
    session_file = tmp_path / "tmp" / "h" / "chats" / "session-g-1.json"
    session_file.parent.mkdir(parents=True)
    session_file.write_bytes(b'{"sessionId": "g-1", "messages": ' + DEEP.strip() + b"}")
    backend = get_backend("gemini")
    assert backend is not None

    assert backend.read_messages(session_file) == []
    assert backend.extract_stats(session_file)[0]["message_count"] == 0
    assert extract_gemini_lineage(session_file) == []


T1 = "2026-05-01T04:29:01.000Z"

_GEMINI_JSON_CASES: dict[str, tuple[bytes, tuple]] = {
    # name: (file content, (session_id, message_count, input, output, first, last))
    "bad byte": (
        b'{"sessionId": "g\xff1", "messages": [{"type": "user", "timestamp": "'
        + T1.encode()
        + b'"}]}',
        ("g�1", 1, 0, 0, T1, T1),
    ),
    "top-level list": (b"[1, 2]", (None, 0, 0, 0, None, None)),
    "null messages": (b'{"sessionId": "g1", "messages": null}', ("g1", 0, 0, 0, None, None)),
    "message not an object": (
        b'{"sessionId": "g1", "messages": ["x", 5, {"type": "user"}]}',
        ("g1", 1, 0, 0, None, None),
    ),
    "tokens not an object": (
        b'{"sessionId": "g1", "messages": [{"type": "gemini", "tokens": "x"}]}',
        ("g1", 1, 0, 0, None, None),
    ),
    "token values as text": (
        b'{"sessionId": "g1", "messages": [{"type": "gemini",'
        b' "tokens": {"input": "5", "output": 2.0, "cached": "x"}}]}',
        ("g1", 1, 5, 2, None, None),
    ),
    "mixed timestamp types": (
        b'{"sessionId": "g1", "messages": [{"type": "user", "timestamp": 5},'
        b' {"type": "user", "timestamp": "' + T1.encode() + b'"},'
        b' {"type": "user", "timestamp": {"a": 1}}]}',
        ("g1", 3, 0, 0, T1, T1),
    ),
}


@pytest.mark.parametrize("name", sorted(_GEMINI_JSON_CASES))
def test_gemini_json_stats_reader_reads_malformed_chats(tmp_path: Path, name: str) -> None:
    content, expected = _GEMINI_JSON_CASES[name]
    session_file = tmp_path / "tmp" / "h" / "chats" / "session-g1.json"
    session_file.parent.mkdir(parents=True)
    session_file.write_bytes(content)
    backend = get_backend("gemini")
    assert backend is not None

    payload = backend.extract_stats(session_file)
    session_info = payload[0]
    _assert_bindable(payload)
    assert (
        session_info["session_id"],
        session_info["message_count"],
        session_info["input_tokens"],
        session_info["output_tokens"],
        session_info["first_timestamp"],
        session_info["last_timestamp"],
    ) == expected
    _synced_rows(tmp_path, session_file, "gemini")


def test_gemini_json_stats_reader_reads_malformed_tool_calls(tmp_path: Path) -> None:
    session_file = tmp_path / "tmp" / "h" / "chats" / "session-g1.json"
    session_file.parent.mkdir(parents=True)
    messages = [
        {"type": "gemini", "toolCalls": None},
        {
            "type": "gemini",
            "toolCalls": [
                5,
                {"id": "t-1", "name": "shell", "status": None},
                {"id": ["t-2"], "name": {"n": 1}, "status": "error"},
            ],
        },
    ]
    session_file.write_text(json.dumps({"sessionId": "g1", "messages": messages}))
    backend = get_backend("gemini")
    assert backend is not None

    payload = backend.extract_stats(session_file)
    _assert_bindable(payload)
    assert [(t["tool_use_id"], t["is_error"]) for t in payload[2]] == [
        ("t-1", 0),
        ('["t-2"]', 1),
    ]
    assert _synced_rows(tmp_path, session_file, "gemini")["tool_uses"] == [
        ("t-1", "shell", 0),
        ('["t-2"]', '{"n": 1}', 1),
    ]


def test_gemini_markdown_export_reads_fields_of_the_wrong_type(tmp_path: Path) -> None:
    session_file = tmp_path / "tmp" / "h" / "chats" / "session-g1.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_bytes(
        _line({"sessionId": "g1"})
        + _line({"id": "m-1", "type": "gemini", "content": "one", "tokens": "x", "toolCalls": None})
        + _line({"id": "m-2", "type": "gemini", "content": "two", "toolCalls": "x", "thoughts": 5})
        + _line(
            {
                "id": "m-3",
                "type": "gemini",
                "content": "three",
                "toolCalls": [
                    7,
                    {"name": "shell", "result": [{"functionResponse": "x"}]},
                    {"name": "read", "result": [{"functionResponse": {"response": {"output": 5}}}]},
                ],
            }
        )
    )
    backend = get_backend("gemini")
    assert backend is not None

    markdown = backend.render_markdown(session_file, False, None, 4)

    for text in ("one", "two", "three", "[Tool: shell]", "[Tool: read]"):
        assert text in markdown


def test_claude_stats_reader_ignores_values_of_the_wrong_type(tmp_path: Path) -> None:
    def entry(timestamp: Any, message: dict[str, Any], **fields: Any) -> dict[str, Any]:
        return {
            "type": message["role"],
            "sessionId": "s-1",
            "timestamp": timestamp,
            "message": message,
            **fields,
        }

    session_file = _write_session(
        tmp_path,
        "claude",
        _line(entry(T1, {"role": "user", "content": "a"}, cwd={"x": 1}))
        + _line(entry(5, {"role": "user", "content": "b"}))
        + _line(
            entry(
                {"a": 1},
                {
                    "role": "assistant",
                    "model": ["m"],
                    "usage": {
                        "input_tokens": "5",
                        "output_tokens": "x",
                        "cache_read_input_tokens": 3,
                    },
                    "content": [{"type": "tool_use", "name": ["n"], "id": {"a": 1}, "input": "s"}],
                },
            )
        ),
    )
    backend = get_backend("claude")
    assert backend is not None

    payload = backend.extract_stats(session_file)
    _assert_bindable(payload)
    session_info = payload[0]
    assert (session_info["first_timestamp"], session_info["last_timestamp"]) == (T1, T1)
    assert (session_info["input_tokens"], session_info["output_tokens"]) == (5, 0)
    assert session_info["cache_read_tokens"] == 3
    rows = _synced_rows(tmp_path, session_file, "claude")
    assert rows["sessions"] == [("s-1", '{"x": 1}', 3, 5, 0, T1, T1)]
    assert [model for _, _, model in rows["messages"]] == [None, None, '["m"]']
    assert rows["tool_uses"] == [('{"a": 1}', '["n"]', 0)]


def test_codex_stats_reader_ignores_values_of_the_wrong_type(tmp_path: Path) -> None:
    session_file = _write_session(
        tmp_path,
        "codex",
        _line({**CODEX_META, "payload": {"id": {"a": 1}, "cwd": {"b": 2}}})
        + _line({"type": "turn_context", "payload": {"model": {"m": 1}}})
        + _line(
            {
                "type": "response_item",
                "timestamp": 5,
                "payload": {"type": "message", "role": "user", "content": "a"},
            }
        )
        + _line(
            {
                "type": "response_item",
                "timestamp": T1,
                "payload": {"type": "message", "role": "assistant", "content": "b"},
            }
        )
        + _codex_item({"type": "function_call", "name": {"n": 1}, "arguments": 5, "call_id": [1]})
        + _codex_item({"type": "function_call_output", "output": {"a": 1}, "call_id": [1]}),
    )
    backend = get_backend("codex")
    assert backend is not None

    payload = backend.extract_stats(session_file)
    _assert_bindable(payload)
    assert (payload[0]["first_timestamp"], payload[0]["last_timestamp"]) == (T1, T1)
    rows = _synced_rows(tmp_path, session_file, "codex")
    assert rows["sessions"][0][:2] == ('{"a": 1}', '{"b": 2}')
    assert [model for _, _, model in rows["messages"]] == [None, '{"m": 1}']
    assert rows["tool_uses"] == [("[1]", '{"n": 1}', 0)]
    extract_codex_lineage(session_file)


def test_codex_lineage_reads_a_list_call_id(tmp_path: Path) -> None:
    session_file = _write_session(
        tmp_path,
        "codex",
        _line(CODEX_META)
        + _codex_item(
            {"type": "function_call", "name": "spawn_agent", "arguments": "{}", "call_id": [1]}
        )
        + _codex_item(
            {
                "type": "function_call_output",
                "call_id": [1],
                "output": json.dumps({"agent_id": "a-1"}),
            }
        ),
    )

    record, invocations = extract_codex_lineage(session_file)

    assert record is not None
    assert list(invocations) == ["a-1"]


def test_pi_readers_read_ids_that_are_not_text(tmp_path: Path) -> None:
    session_file = _write_session(
        tmp_path,
        "pi",
        _line({"type": "session", "id": {"a": 1}, "cwd": ["x"]})
        + _line(
            {
                "type": "message",
                "id": ["a"],
                "parentId": {"x": 1},
                "timestamp": 5,
                "message": {"role": "user", "content": "x"},
            }
        )
        + _line(
            {
                "type": "message",
                "id": "b",
                "parentId": ["a"],
                "timestamp": START,
                "message": {
                    "role": "assistant",
                    "usage": {"input": "5", "output": "x"},
                    "content": [{"type": "toolCall", "id": ["t"], "name": ["n"]}],
                },
            }
        )
        + _line(
            {
                "type": "message",
                "id": "c",
                "parentId": "b",
                "message": {"role": "assistant", "usage": "x", "content": "y"},
            }
        ),
    )
    backend = get_backend("pi")
    assert backend is not None

    messages = backend.read_messages(session_file)
    assert [m["role"] for m in messages] == ["user", "assistant", "assistant"]
    assert backend.count_messages(session_file) == 3
    assert backend.render_markdown(session_file, False, messages, 4)
    payload = backend.extract_stats(session_file)
    _assert_bindable(payload)
    assert (payload[0]["message_count"], payload[0]["input_tokens"]) == (3, 5)
    rows = _synced_rows(tmp_path, session_file, "pi")
    assert rows["sessions"][0][:2] == ('{"a": 1}', '["x"]')
    assert rows["tool_uses"] == [('["t"]', '["n"]', 0)]
    extract_pi_lineage(session_file)
