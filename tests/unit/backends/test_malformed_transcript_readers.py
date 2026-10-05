"""The list, export and message readers skip transcript lines they cannot use.

A line can carry a byte that is not UTF-8, be valid JSON that is not an
object, or hold a string where an object is expected. One such line must
not stop a reader: it skips the line, or decodes the bad byte as U+FFFD,
and reads the rest of the file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
from agent_history.backends.gemini import gemini_get_first_timestamp, gemini_read_json_messages
from agent_history.backends.pi import pi_get_workspace_from_session, pi_read_jsonl_messages
from agent_history.core.lineage import extract_gemini_lineage, extract_pi_lineage
from agent_history.handlers.export import SessionExportHandler

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
