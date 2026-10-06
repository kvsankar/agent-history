"""Claude Code writes one model response as several lines; tokens count once."""

import json

from agent_history.storage import metrics


def _write_jsonl(path, entries):
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    return path


def _assistant(uuid, message_id, output, input_tokens=10, cache_read=2000, cache_write=300):
    return {
        "type": "assistant",
        "uuid": uuid,
        "sessionId": "s-1",
        "timestamp": "2026-09-10T10:00:00Z",
        "message": {
            "id": message_id,
            "role": "assistant",
            "model": "claude-test",
            "content": [],
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_write,
            },
        },
    }


def test_lines_repeating_one_response_count_its_tokens_once(tmp_path):
    """Each content block of a response is its own line with the same usage."""
    session_file = _write_jsonl(
        tmp_path / "s-1.jsonl",
        [
            _assistant("a-1", "msg-1", 40),
            _assistant("a-2", "msg-1", 40),
            _assistant("a-3", "msg-1", 40),
            _assistant("a-4", "msg-2", 7),
        ],
    )

    session_info, messages, _tools = metrics._parse_claude_jsonl(session_file)

    assert session_info["input_tokens"] == 20
    assert session_info["output_tokens"] == 47
    assert session_info["cache_read_tokens"] == 4000
    assert session_info["cache_creation_tokens"] == 600
    assert sum(m["output_tokens"] for m in messages) == session_info["output_tokens"]
    assert sum(m["cache_read_tokens"] for m in messages) == session_info["cache_read_tokens"]


def test_streamed_response_keeps_its_final_output_count(tmp_path):
    """Earlier lines of a streamed response carry a partial output count."""
    session_file = _write_jsonl(
        tmp_path / "s-1.jsonl",
        [_assistant("a-1", "msg-1", 1), _assistant("a-2", "msg-1", 853)],
    )

    session_info, messages, _tools = metrics._parse_claude_jsonl(session_file)

    assert session_info["output_tokens"] == 853
    assert session_info["input_tokens"] == 10
    assert sum(m["output_tokens"] for m in messages) == 853


def test_lines_without_a_response_id_each_count(tmp_path):
    first = _assistant("a-1", None, 5)
    second = _assistant("a-2", None, 6)

    session_info, _messages, _tools = metrics._parse_claude_jsonl(
        _write_jsonl(tmp_path / "s-1.jsonl", [first, second])
    )

    assert session_info["output_tokens"] == 11
