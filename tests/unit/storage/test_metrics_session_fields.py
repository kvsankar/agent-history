"""Session fields that appear after the first line of a transcript."""

import json

from agent_history.storage import metrics


def _write_jsonl(path, entries):
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    return path


def test_claude_session_fields_come_from_the_first_line_that_has_them(tmp_path):
    """A queue-operation first line has no cwd, branch or version; later lines do."""
    session_file = _write_jsonl(
        tmp_path / "session.jsonl",
        [
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "timestamp": "2026-05-01T04:29:01.796Z",
                "sessionId": "s-1",
            },
            {
                "type": "user",
                "uuid": "u-1",
                "sessionId": "s-1",
                "timestamp": "2026-05-01T04:29:02.000Z",
                "cwd": "/home/user/project",
                "gitBranch": "main",
                "version": "2.1.0",
                "message": {"role": "user", "content": "hello"},
            },
        ],
    )

    session_info, _messages, _tools = metrics._parse_claude_jsonl(session_file)

    assert session_info["session_id"] == "s-1"
    assert session_info["cwd"] == "/home/user/project"
    assert session_info["git_branch"] == "main"
    assert session_info["claude_version"] == "2.1.0"


def test_codex_assistant_messages_carry_the_turn_model(tmp_path):
    """Codex names the model in turn_context lines, which can change between turns."""

    def message(role, timestamp):
        return {
            "type": "response_item",
            "timestamp": timestamp,
            "payload": {"type": "message", "role": role, "content": []},
        }

    session_file = _write_jsonl(
        tmp_path / "rollout.jsonl",
        [
            {
                "type": "session_meta",
                "timestamp": "2026-09-29T12:00:00Z",
                "payload": {"id": "c-1", "cwd": "/home/user/project", "cli_version": "1.0"},
            },
            {
                "type": "turn_context",
                "timestamp": "2026-09-29T12:00:01Z",
                "payload": {"cwd": "/home/user/project", "model": "model-a"},
            },
            message("user", "2026-09-29T12:00:02Z"),
            message("assistant", "2026-09-29T12:00:03Z"),
            {
                "type": "turn_context",
                "timestamp": "2026-09-29T12:01:00Z",
                "payload": {"cwd": "/home/user/project", "model": "model-b"},
            },
            message("user", "2026-09-29T12:01:01Z"),
            message("assistant", "2026-09-29T12:01:02Z"),
        ],
    )

    _session_info, messages, _tools = metrics._parse_codex_jsonl(session_file)

    assert [(m["type"], m["model"]) for m in messages] == [
        ("user", None),
        ("assistant", "model-a"),
        ("user", None),
        ("assistant", "model-b"),
    ]
