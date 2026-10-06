"""Codex token usage is summed per response, not from running totals."""

import json

from agent_history.backends.codex import codex_extract_metrics_from_jsonl
from agent_history.storage import metrics


def _write_jsonl(path, entries):
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    return path


def _meta():
    return {
        "type": "session_meta",
        "timestamp": "2026-09-29T12:00:00Z",
        "payload": {"id": "c-1", "cwd": "/home/user/project", "cli_version": "1.0"},
    }


def _message(role, timestamp):
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {"type": "message", "role": role, "content": []},
    }


def _usage(input_tokens, cached, output):
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "output_tokens": output,
        "reasoning_output_tokens": 0,
        "total_tokens": input_tokens + output,
    }


def _token_count(timestamp, total, last):
    return {
        "type": "event_msg",
        "timestamp": timestamp,
        "payload": {
            "type": "token_count",
            "info": {"total_token_usage": total, "last_token_usage": last},
        },
    }


def _subagent_session(tmp_path):
    """A spawned sub-agent's first running total includes its parent's usage.

    The sub-agent itself used 100 + 200 input tokens. Its running totals start
    at the parent's 1,000,000. The second response's event is repeated, as
    Codex does when only rate limits change.
    """
    return _write_jsonl(
        tmp_path / "rollout.jsonl",
        [
            _meta(),
            _message("user", "2026-09-29T12:00:01Z"),
            _message("assistant", "2026-09-29T12:00:02Z"),
            _token_count(
                "2026-09-29T12:00:03Z", _usage(1_000_100, 500_040, 10_010), _usage(100, 40, 10)
            ),
            _message("assistant", "2026-09-29T12:00:04Z"),
            _token_count(
                "2026-09-29T12:00:05Z", _usage(1_000_300, 500_190, 10_030), _usage(200, 150, 20)
            ),
            _token_count(
                "2026-09-29T12:00:06Z", _usage(1_000_300, 500_190, 10_030), _usage(200, 150, 20)
            ),
        ],
    )


def test_session_tokens_exclude_inherited_totals_and_repeated_events(tmp_path):
    session_info, _messages, _tools = metrics._parse_codex_jsonl(_subagent_session(tmp_path))

    assert session_info["input_tokens"] == 300
    assert session_info["cache_read_tokens"] == 190
    assert session_info["output_tokens"] == 30


def test_message_tokens_are_per_response_and_sum_to_the_session(tmp_path):
    session_info, messages, _tools = metrics._parse_codex_jsonl(_subagent_session(tmp_path))

    assistant = [m for m in messages if m["type"] == "assistant"]
    assert [m["input_tokens"] for m in assistant] == [100, 200]
    assert [m["output_tokens"] for m in assistant] == [10, 20]
    assert sum(m["cache_read_tokens"] for m in messages) == session_info["cache_read_tokens"]


def test_events_without_last_usage_fall_back_to_the_change_in_totals(tmp_path):
    """Older Codex versions only record running totals."""
    session_file = _write_jsonl(
        tmp_path / "rollout.jsonl",
        [
            _meta(),
            _message("assistant", "2026-09-29T12:00:02Z"),
            _token_count("2026-09-29T12:00:03Z", _usage(100, 40, 10), None),
            _message("assistant", "2026-09-29T12:00:04Z"),
            _token_count("2026-09-29T12:00:05Z", _usage(300, 190, 30), None),
        ],
    )

    session_info, messages, _tools = metrics._parse_codex_jsonl(session_file)

    assert session_info["input_tokens"] == 300
    assert [m["input_tokens"] for m in messages] == [100, 200]


def test_backend_token_summary_uses_the_same_per_response_sums(tmp_path):
    summary = codex_extract_metrics_from_jsonl(_subagent_session(tmp_path))["tokens_summary"]

    assert summary["input_tokens"] == 300
    assert summary["cache_read_tokens"] == 190
    assert summary["output_tokens"] == 30


def test_reasoning_tokens_are_already_inside_output(tmp_path):
    """Codex's output count includes reasoning; total = input + output."""
    usage = {
        "input_tokens": 19082,
        "cached_input_tokens": 4864,
        "output_tokens": 140,
        "reasoning_output_tokens": 122,
        "total_tokens": 19222,
    }
    session_file = _write_jsonl(
        tmp_path / "rollout.jsonl",
        [
            _meta(),
            _message("assistant", "2026-09-29T12:00:02Z"),
            _token_count("2026-09-29T12:00:03Z", usage, usage),
        ],
    )

    session_info, messages, _tools = metrics._parse_codex_jsonl(session_file)

    assert session_info["output_tokens"] == 140
    assert messages[0]["output_tokens"] == 140
    summary = codex_extract_metrics_from_jsonl(session_file)["tokens_summary"]
    assert summary["output_tokens"] == 140
