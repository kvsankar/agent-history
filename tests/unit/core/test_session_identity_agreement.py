"""The stats readers, the lineage model and the export agree on session IDs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from agent_history.backends.codex import codex_read_jsonl_messages
from agent_history.core.lineage import (
    build_timeline_lineage,
    extract_claude_lineage,
    extract_codex_lineage,
)
from agent_history.handlers.export import SessionExportHandler
from agent_history.storage import metrics
from agent_history.utils.platform import AGENT_CLAUDE

PARENT = "11111111-1111-4111-8111-111111111111"
EARLIER = "22222222-2222-4222-8222-222222222222"


def _write_jsonl(path: Path, entries: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    return path


def _claude_line(session_id, uuid, agent_id=None, entry_type="user", **extra):
    entry: dict[str, Any] = {
        "type": entry_type,
        "uuid": uuid,
        "timestamp": "2026-05-01T04:29:02.000Z",
        "message": {"role": entry_type, "content": "hello"},
        **extra,
    }
    if session_id:
        entry["sessionId"] = session_id
    if agent_id:
        entry["agentId"] = agent_id
        entry["isSidechain"] = True
    return entry


def _session(path: Path, agent: str) -> dict[str, Any]:
    return {
        "agent": agent,
        "file": path,
        "filename": path.name,
        "workspace": "workspace",
        "workspace_readable": "/home/alex/project",
        "modified": datetime(2026, 6, 9, 10, 0, 0),
    }


# Each case: (relative path, session IDs of the lines in order, agentId)
CLAUDE_CASES = {
    "main": (f"{PARENT}.jsonl", [PARENT, PARENT], None),
    "continued main": (f"{PARENT}.jsonl", [EARLIER, EARLIER, PARENT], None),
    "main with another name": ("copy.jsonl", [EARLIER, PARENT], None),
    "main without sessionId lines": (f"{PARENT}.jsonl", [None, None], None),
    "sub-agent in its folder": (f"{PARENT}/subagents/agent-a1.jsonl", [PARENT], "a1"),
    "sub-agent of a continued parent": (
        f"{PARENT}/subagents/agent-a2.jsonl",
        [EARLIER, PARENT],
        "a2",
    ),
    "sub-agent resumed after its parent was continued": (
        f"{EARLIER}/subagents/agent-a3.jsonl",
        [EARLIER, PARENT],
        "a3",
    ),
    "sub-agent named by a later session": (
        f"{EARLIER}/subagents/agent-a4.jsonl",
        [PARENT],
        "a4",
    ),
    "legacy sub-agent": ("agent-a5.jsonl", [EARLIER, PARENT, PARENT], "a5"),
    "legacy sub-agent without agentId": ("agent-b7.jsonl", [PARENT], None),
    "workflow sub-agent": (f"{PARENT}/subagents/workflows/wf_1/agent-a6.jsonl", [PARENT], "a6"),
}


@pytest.mark.parametrize("case", sorted(CLAUDE_CASES))
def test_claude_lineage_matches_the_stats_reader(tmp_path: Path, case: str) -> None:
    relative, session_ids, agent_id = CLAUDE_CASES[case]
    session_file = _write_jsonl(
        tmp_path / "project" / relative,
        [
            _claude_line(session_id, f"m-{index}", agent_id)
            for index, session_id in enumerate(session_ids)
        ],
    )

    session_info, _messages, _tools = metrics._parse_claude_jsonl(session_file)
    records, _notifications = extract_claude_lineage(session_file)

    assert len(records) == 1
    record = records[0]
    assert record["session_id"] == session_info["session_id"]
    assert record.get("parent_session_id") == session_info["parent_session_id"]
    assert (record["kind"] == "subagent") == session_info["is_agent"]


def test_claude_sidechain_lines_alone_do_not_make_a_sub_agent(tmp_path: Path) -> None:
    """A main-level file without an agent name or agentId is a main session."""
    session_file = _write_jsonl(
        tmp_path / "project" / f"{PARENT}.jsonl",
        [_claude_line(PARENT, "m-0", isSidechain=True)],
    )

    session_info, _messages, _tools = metrics._parse_claude_jsonl(session_file)
    records, _notifications = extract_claude_lineage(session_file)

    assert session_info["is_agent"] is False
    assert [(record["kind"], record["session_id"]) for record in records] == [("main", PARENT)]


def test_claude_notification_in_a_continued_parent_joins_its_sub_agent(tmp_path: Path) -> None:
    """The parent's notification and the child's parent use the same session ID."""
    workspace = tmp_path / "-home-alex-project"
    parent = _write_jsonl(
        workspace / f"{PARENT}.jsonl",
        [
            _claude_line(EARLIER, "m-0"),
            _claude_line(PARENT, "m-1"),
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "sessionId": PARENT,
                "uuid": "notif-1",
                "timestamp": "2026-05-01T04:30:00.000Z",
                "content": (
                    "<task-notification><task-id>a1</task-id>"
                    "<tool-use-id>toolu-1</tool-use-id><status>completed</status>"
                    "<result>done</result></task-notification>"
                ),
            },
        ],
    )
    _write_jsonl(
        workspace / PARENT / "subagents" / "agent-a1.jsonl",
        [_claude_line(PARENT, "c-0", "a1")],
    )

    lineage = build_timeline_lineage([_session(parent, AGENT_CLAUDE)], include_related=True)
    child = next(record for record in lineage if record.get("agent_id") == "a1")

    assert child["session_id"] == f"{PARENT}:a1"
    assert child["parent_session_id"] == PARENT
    assert child["join_status"] == "joined"
    assert child["invocation_tool_call_id"] == "toolu-1"


CHILD_THREAD = "child-thread"
PARENT_THREAD = "parent-thread"


def _codex_meta(session_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "timestamp": "2026-06-09T10:00:00.000Z",
        "type": "session_meta",
        "payload": {"id": session_id, "cwd": "/home/alex/project", **extra},
    }


def _codex_message(role: str, text: str) -> dict[str, Any]:
    return {
        "timestamp": "2026-06-09T10:00:01.000Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": role,
            "content": [{"type": "input_text", "text": text}],
        },
    }


_SPAWN = {"subagent": {"thread_spawn": {"parent_thread_id": PARENT_THREAD, "depth": 1}}}
_GUARDIAN = {"subagent": {"other": "guardian"}}

# Each case: the session_meta payloads of the rollout, in order
CODEX_CASES = {
    "main": [_codex_meta(PARENT_THREAD, source="cli")],
    "spawned sub-agent": [_codex_meta(CHILD_THREAD, source=_SPAWN, thread_source="subagent")],
    "spawned sub-agent without thread_source": [_codex_meta(CHILD_THREAD, source=_SPAWN)],
    "sub-agent that repeats its parent's session_meta": [
        _codex_meta(CHILD_THREAD, source=_SPAWN, thread_source="subagent"),
        _codex_meta(PARENT_THREAD, source="cli"),
    ],
    "review thread": [
        _codex_meta(
            CHILD_THREAD,
            source=_GUARDIAN,
            thread_source="guardian_review",
            parent_thread_id=PARENT_THREAD,
        )
    ],
    "forked rollout": [
        _codex_meta(CHILD_THREAD, source="cli", forked_from_id=PARENT_THREAD),
        _codex_meta(PARENT_THREAD, source="cli"),
    ],
}


def _codex_rollout(tmp_path: Path, metas: list[dict[str, Any]]) -> Path:
    session_file = tmp_path / "sessions" / "2026" / "06" / "09" / "rollout-1.jsonl"
    entries = [metas[0], _codex_message("user", "Inspect this."), *metas[1:]]
    entries.append(_codex_message("assistant", "Done."))
    return _write_jsonl(session_file, entries)


@pytest.mark.parametrize("case", sorted(CODEX_CASES))
def test_codex_lineage_and_export_match_the_stats_reader(tmp_path: Path, case: str) -> None:
    session_file = _codex_rollout(tmp_path, CODEX_CASES[case])

    session_info, _messages, _tools = metrics._parse_codex_jsonl(session_file)
    record, _invocations = extract_codex_lineage(session_file)
    header = SessionExportHandler()._read_codex_lineage_header(session_file)

    assert record is not None
    assert header is not None
    assert record["session_id"] == header["session_id"] == session_info["session_id"]
    assert record.get("parent_session_id") == session_info["parent_session_id"]
    assert header["parent_session_id"] == session_info["parent_session_id"]
    assert (record["kind"] == "subagent") == session_info["is_agent"]
    assert (header["kind"] == "subagent") == session_info["is_agent"]


def test_codex_sub_agent_that_repeats_its_parent_meta_keeps_its_own_identity(
    tmp_path: Path,
) -> None:
    session_file = _codex_rollout(
        tmp_path, CODEX_CASES["sub-agent that repeats its parent's session_meta"]
    )

    record, _invocations = extract_codex_lineage(session_file)
    messages, session_meta = codex_read_jsonl_messages(session_file)

    assert record is not None
    assert (record["session_id"], record["kind"]) == (CHILD_THREAD, "subagent")
    assert record["parent_session_id"] == PARENT_THREAD
    assert session_meta is not None
    assert session_meta["id"] == CHILD_THREAD
    assert [message["session_id"] for message in messages] == [CHILD_THREAD, CHILD_THREAD]


def test_codex_review_thread_prompts_come_from_the_parent_agent(tmp_path: Path) -> None:
    session_file = _codex_rollout(tmp_path, CODEX_CASES["review thread"])

    messages, _session_meta = codex_read_jsonl_messages(session_file)

    assert messages[0]["role"] == "user"
    assert messages[0]["is_parent_agent_message"] is True
