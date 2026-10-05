"""Which session a Codex rollout belongs to, and its parent.

A spawned sub-agent or forked rollout starts with its own session_meta and
later repeats the parent's session_meta.
"""

import json

from agent_history.storage import metrics

CHILD = "child-thread"
PARENT = "parent-thread"


def _write_jsonl(path, entries):
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    return path


def _meta(session_id, cwd, branch, **extra):
    payload = {"id": session_id, "cwd": cwd, "cli_version": "1.0", "git": {"branch": branch}}
    payload.update(extra)
    return {"type": "session_meta", "timestamp": "2026-09-29T12:00:00Z", "payload": payload}


def _message(role, timestamp):
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {"type": "message", "role": role, "content": []},
    }


def _function_call(timestamp):
    return {
        "type": "response_item",
        "timestamp": timestamp,
        "payload": {"type": "function_call", "name": "shell", "call_id": "call-1"},
    }


def _rollout(tmp_path, first_meta, later_meta=None):
    entries = [first_meta, _message("user", "2026-09-29T12:00:01Z")]
    if later_meta is not None:
        entries.append(later_meta)
    entries += [
        _message("assistant", "2026-09-29T12:00:02Z"),
        _function_call("2026-09-29T12:00:03Z"),
    ]
    return _write_jsonl(tmp_path / "rollout.jsonl", entries)


def _spawn_source(parent):
    return {
        "subagent": {
            "thread_spawn": {
                "parent_thread_id": parent,
                "depth": 1,
                "agent_nickname": "helper",
                "agent_role": "worker",
            }
        }
    }


def test_spawned_subagent_keeps_its_own_meta_and_names_its_parent(tmp_path):
    rollout = _rollout(
        tmp_path,
        _meta(CHILD, "/home/alex/child", "feature", source=_spawn_source(PARENT)),
        _meta(PARENT, "/home/alex/parent", "main", source="cli"),
    )

    session_info, messages, tool_uses = metrics._parse_codex_jsonl(rollout)

    assert session_info["session_id"] == CHILD
    assert session_info["cwd"] == "/home/alex/child"
    assert session_info["git_branch"] == "feature"
    assert session_info["is_agent"] is True
    assert session_info["parent_session_id"] == PARENT
    assert {m["session_id"] for m in messages} == {CHILD}
    assert {t["session_id"] for t in tool_uses} == {CHILD}


def test_reviewer_subagent_is_an_agent_with_its_parent_thread(tmp_path):
    rollout = _rollout(
        tmp_path,
        _meta(
            CHILD,
            "/home/alex/project",
            "main",
            source={"subagent": {"other": "guardian"}},
            parent_thread_id=PARENT,
        ),
    )

    session_info, _messages, _tools = metrics._parse_codex_jsonl(rollout)

    assert session_info["is_agent"] is True
    assert session_info["parent_session_id"] == PARENT


def test_forked_rollout_is_a_main_session_with_the_fork_source_as_parent(tmp_path):
    rollout = _rollout(
        tmp_path,
        _meta(CHILD, "/home/alex/project", "main", source="cli", forked_from_id=PARENT),
        _meta(PARENT, "/home/alex/project", "main", source="cli"),
    )

    session_info, _messages, _tools = metrics._parse_codex_jsonl(rollout)

    assert session_info["session_id"] == CHILD
    assert session_info["is_agent"] is False
    assert session_info["parent_session_id"] == PARENT


def test_later_session_meta_without_parent_fields_names_the_parent(tmp_path):
    rollout = _rollout(
        tmp_path,
        _meta(CHILD, "/home/alex/project", "main", source="cli"),
        _meta(PARENT, "/home/alex/other", "dev", source="cli"),
    )

    session_info, _messages, _tools = metrics._parse_codex_jsonl(rollout)

    assert session_info["session_id"] == CHILD
    assert session_info["cwd"] == "/home/alex/project"
    assert session_info["parent_session_id"] == PARENT


def test_plain_rollout_has_no_parent(tmp_path):
    rollout = _rollout(tmp_path, _meta(CHILD, "/home/alex/project", "main", source="cli"))

    session_info, _messages, _tools = metrics._parse_codex_jsonl(rollout)

    assert session_info["session_id"] == CHILD
    assert session_info["is_agent"] is False
    assert session_info["parent_session_id"] is None
