"""The Codex stats reader handles zstd-compressed rollouts and bad bytes."""

import json

import zstandard

from agent_history.storage import metrics


def _lines():
    entries = [
        {
            "type": "session_meta",
            "timestamp": "2026-09-29T12:00:00Z",
            "payload": {"id": "c-1", "cwd": "/home/alex/project", "cli_version": "1.0"},
        },
        {
            "type": "response_item",
            "timestamp": "2026-09-29T12:00:01Z",
            "payload": {"type": "message", "role": "user", "content": []},
        },
        {
            "type": "response_item",
            "timestamp": "2026-09-29T12:00:02Z",
            "payload": {"type": "message", "role": "assistant", "content": []},
        },
    ]
    return [json.dumps(entry).encode("utf-8") + b"\n" for entry in entries]


def test_compressed_rollout_is_read_like_a_plain_one(tmp_path):
    rollout = tmp_path / "rollout-2026-09-29T12-00-00-c-1.jsonl.zst"
    rollout.write_bytes(zstandard.ZstdCompressor().compress(b"".join(_lines())))

    session_info, messages, _tools = metrics._parse_codex_jsonl(rollout)

    assert session_info["session_id"] == "c-1"
    assert session_info["cwd"] == "/home/alex/project"
    assert [m["type"] for m in messages] == ["user", "assistant"]


def test_invalid_utf8_line_does_not_stop_the_rest_of_the_rollout(tmp_path):
    first, *rest = _lines()
    rollout = tmp_path / "rollout-2026-09-29T12-00-00-c-1.jsonl"
    rollout.write_bytes(
        b"\xef\xbb\xbf" + first + b'{"type": "event_msg", "x": "\xff"}\n' + b"".join(rest)
    )

    session_info, messages, _tools = metrics._parse_codex_jsonl(rollout)

    assert session_info["session_id"] == "c-1"
    assert [m["type"] for m in messages] == ["user", "assistant"]
