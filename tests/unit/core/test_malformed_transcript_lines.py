"""Transcript lines of an unexpected shape are skipped, not fatal.

A line can be valid JSON but not an object, hold a string where an object
is expected, or carry a byte that is not UTF-8. The stats readers and the
lineage model skip what they cannot use and read the rest of the file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_history.core.lineage import extract_claude_lineage, extract_codex_lineage
from agent_history.storage import metrics


def _json_line(value: Any) -> bytes:
    return json.dumps(value).encode("utf-8") + b"\n"


def _claude_line(entry_type: str, message: Any) -> dict[str, Any]:
    return {
        "type": entry_type,
        "sessionId": "s-1",
        "uuid": f"{entry_type}-{len(json.dumps(message))}",
        "timestamp": "2026-05-01T04:29:02.000Z",
        "message": message,
    }


def _claude_file(tmp_path: Path) -> Path:
    usage = {"input_tokens": 3, "output_tokens": 4}
    session_file = tmp_path / "project" / "s-1.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_bytes(
        _json_line(_claude_line("user", {"role": "user", "content": "hello"}))
        + _json_line([1, 2])
        + _json_line(None)
        + _json_line("text")
        + _json_line(_claude_line("assistant", "plain text"))
        + _json_line(_claude_line("assistant", {"usage": "none", "content": "x"}))
        + b'{"type": "user", "sessionId": "s-1", "message": {"content": "caf\xff"}}\n'
        + _json_line(_claude_line("assistant", {"usage": usage, "content": []}))
    )
    return session_file


def _codex_file(tmp_path: Path) -> Path:
    def item(role: str) -> dict[str, Any]:
        return {
            "type": "response_item",
            "timestamp": "2026-05-01T04:29:03.000Z",
            "payload": {"type": "message", "role": role, "content": []},
        }

    session_file = tmp_path / "rollout-1.jsonl"
    session_file.write_bytes(
        _json_line({"type": "session_meta", "payload": {"id": "c-1", "cwd": "/home/alex"}})
        + _json_line([1])
        + _json_line(None)
        + _json_line({"type": "session_meta", "payload": None})
        + _json_line({"type": "turn_context", "payload": "model"})
        + _json_line({"type": "response_item", "payload": None})
        + _json_line({"type": "event_msg", "payload": "x"})
        + _json_line({"type": "event_msg", "payload": {"type": "token_count", "info": "x"}})
        + _json_line(
            {
                "type": "event_msg",
                "payload": {"type": "token_count", "info": {"total_token_usage": [1]}},
            }
        )
        + _json_line(item("user"))
        + b'{"type": "event_msg", "payload": {"type": "agent_message", "message": "\xff"}}\n'
        + _json_line(item("assistant"))
    )
    return session_file


def test_claude_reader_skips_lines_it_cannot_use(tmp_path: Path) -> None:
    session_info, messages, _tools = metrics._parse_claude_jsonl(_claude_file(tmp_path))

    assert session_info["session_id"] == "s-1"
    assert [message["type"] for message in messages] == [
        "user",
        "assistant",
        "assistant",
        "user",
        "assistant",
    ]
    assert (session_info["input_tokens"], session_info["output_tokens"]) == (3, 4)


def test_claude_lineage_skips_lines_it_cannot_use(tmp_path: Path) -> None:
    records, _notifications = extract_claude_lineage(_claude_file(tmp_path))

    assert [(record["kind"], record["session_id"]) for record in records] == [("main", "s-1")]


def test_codex_reader_skips_lines_it_cannot_use(tmp_path: Path) -> None:
    session_info, messages, _tools = metrics._parse_codex_jsonl(_codex_file(tmp_path))

    assert session_info["session_id"] == "c-1"
    assert session_info["cwd"] == "/home/alex"
    assert [message["type"] for message in messages] == ["user", "assistant"]


def test_codex_lineage_skips_lines_it_cannot_use(tmp_path: Path) -> None:
    record, _invocations = extract_codex_lineage(_codex_file(tmp_path))

    assert record is not None
    assert (record["kind"], record["session_id"]) == ("main", "c-1")
