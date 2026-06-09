"""Tests for normalized cross-agent lineage extraction."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_history.backends.claude import get_workspace_sessions
from agent_history.core.lineage import build_timeline_lineage
from agent_history.utils.platform import AGENT_CLAUDE, AGENT_CODEX, AGENT_GEMINI, AGENT_PI


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _session(path: Path, agent: str) -> dict[str, Any]:
    return {
        "agent": agent,
        "file": path,
        "filename": path.name,
        "workspace": "workspace",
        "workspace_readable": "/tmp/workspace",
        "modified": datetime(2026, 6, 9, 10, 0, 0),
    }


def test_codex_lineage_joins_parent_spawn_to_child_completion(tmp_path: Path) -> None:
    parent = tmp_path / "rollout-parent.jsonl"
    child = tmp_path / "rollout-child.jsonl"
    _write_jsonl(
        parent,
        [
            {
                "timestamp": "2026-06-09T10:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "parent-thread", "cwd": "/tmp/workspace"},
            },
            {
                "timestamp": "2026-06-09T10:00:01.000Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "call_id": "call-spawn",
                    "arguments": '{"agent_type": "explorer"}',
                },
            },
            {
                "timestamp": "2026-06-09T10:00:02.000Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-spawn",
                    "output": '{"agent_id": "child-thread", "nickname": "Confucius"}',
                },
            },
        ],
    )
    _write_jsonl(
        child,
        [
            {
                "timestamp": "2026-06-09T10:00:03.000Z",
                "type": "session_meta",
                "payload": {
                    "id": "child-thread",
                    "timestamp": "2026-06-09T10:00:03.000Z",
                    "cwd": "/tmp/workspace",
                    "thread_source": "subagent",
                    "agent_nickname": "Confucius",
                    "agent_role": "explorer",
                    "source": {
                        "subagent": {
                            "thread_spawn": {
                                "parent_thread_id": "parent-thread",
                                "depth": 1,
                            }
                        }
                    },
                },
            },
            {
                "timestamp": "2026-06-09T10:00:20.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "turn-child",
                    "last_agent_message": "child done",
                    "duration_ms": 17000,
                },
            },
        ],
    )

    lineage = build_timeline_lineage([_session(parent, AGENT_CODEX), _session(child, AGENT_CODEX)])
    child_record = next(record for record in lineage if record["session_id"] == "child-thread")

    assert child_record["kind"] == "subagent"
    assert child_record["parent_session_id"] == "parent-thread"
    assert child_record["agent_name"] == "Confucius"
    assert child_record["invocation_tool_call_id"] == "call-spawn"
    assert child_record["status"] == "completed"
    assert child_record["duration_ms"] == 17000
    assert child_record["last_agent_message"] == "child done"


def test_codex_lineage_tolerates_non_dict_source_metadata(tmp_path: Path) -> None:
    session_file = tmp_path / "rollout-main.jsonl"
    _write_jsonl(
        session_file,
        [
            {
                "timestamp": "2026-06-09T10:00:00.000Z",
                "type": "session_meta",
                "payload": {
                    "id": "main-thread",
                    "cwd": "/tmp/workspace",
                    "source": "codex-tui",
                },
            }
        ],
    )

    lineage = build_timeline_lineage([_session(session_file, AGENT_CODEX)])

    assert lineage[0]["session_id"] == "main-thread"
    assert lineage[0]["kind"] == "main"


def test_claude_lineage_discovers_nested_subagent_and_notification(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "-tmp-workspace"
    parent = workspace / "parent-session.jsonl"
    child = workspace / "parent-session" / "subagents" / "agent-task123.jsonl"
    _write_jsonl(
        parent,
        [
            {
                "type": "user",
                "sessionId": "parent-session",
                "uuid": "u1",
                "timestamp": "2026-06-09T10:00:00.000Z",
                "message": {"role": "user", "content": "Start"},
            },
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "sessionId": "parent-session",
                "timestamp": "2026-06-09T10:00:10.000Z",
                "content": (
                    "<task-notification>"
                    "<task-id>task123</task-id>"
                    "<tool-use-id>toolu-task</tool-use-id>"
                    "<status>completed</status>"
                    "<summary>Agent completed</summary>"
                    "<result>nested done</result>"
                    "<usage><duration_ms>12345</duration_ms></usage>"
                    "</task-notification>"
                ),
            },
        ],
    )
    _write_jsonl(
        child,
        [
            {
                "type": "user",
                "sessionId": "parent-session",
                "agentId": "task123",
                "isSidechain": True,
                "uuid": "cu1",
                "timestamp": "2026-06-09T10:00:02.000Z",
                "message": {"role": "user", "content": "Child task"},
            },
            {
                "type": "assistant",
                "sessionId": "parent-session",
                "agentId": "task123",
                "isSidechain": True,
                "uuid": "ca1",
                "timestamp": "2026-06-09T10:00:09.000Z",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "Done"}]},
            },
        ],
    )

    lineage = build_timeline_lineage([_session(parent, AGENT_CLAUDE)])
    child_record = next(record for record in lineage if record.get("agent_id") == "task123")

    assert child_record["kind"] == "subagent"
    assert child_record["session_id"] == "parent-session:task123"
    assert child_record["parent_session_id"] == "parent-session"
    assert child_record["invocation_tool_call_id"] == "toolu-task"
    assert child_record["status"] == "completed"
    assert child_record["duration_ms"] == 12345
    assert child_record["last_agent_message"] == "nested done"


def test_claude_scanner_includes_nested_subagent_files(tmp_path: Path) -> None:
    workspace = tmp_path / "-tmp-workspace"
    parent = workspace / "parent-session.jsonl"
    child = workspace / "parent-session" / "subagents" / "agent-task123.jsonl"
    _write_jsonl(
        parent,
        [
            {
                "type": "user",
                "sessionId": "parent-session",
                "uuid": "u1",
                "timestamp": "2026-06-09T10:00:00.000Z",
                "message": {"role": "user", "content": "Start"},
            }
        ],
    )
    _write_jsonl(
        child,
        [
            {
                "type": "user",
                "sessionId": "parent-session",
                "agentId": "task123",
                "isSidechain": True,
                "uuid": "cu1",
                "timestamp": "2026-06-09T10:00:02.000Z",
                "message": {"role": "user", "content": "Child task"},
            }
        ],
    )

    sessions = get_workspace_sessions(
        "*",
        projects_dir=tmp_path,
        skip_message_count=True,
    )

    assert {Path(session["file"]).name for session in sessions} == {
        "parent-session.jsonl",
        "agent-task123.jsonl",
    }


def test_gemini_lineage_represents_subagent_tool_call(tmp_path: Path) -> None:
    gemini_file = tmp_path / "session.json"
    gemini_file.write_text(
        json.dumps(
            {
                "sessionId": "gemini-parent",
                "startTime": "2026-06-09T10:00:00.000Z",
                "lastUpdated": "2026-06-09T10:00:30.000Z",
                "messages": [
                    {
                        "id": "m1",
                        "timestamp": "2026-06-09T10:00:05.000Z",
                        "type": "gemini",
                        "toolCalls": [
                            {
                                "id": "codebase_investigator-1",
                                "name": "codebase_investigator",
                                "displayName": "Codebase Investigator Agent",
                                "status": "success",
                                "timestamp": "2026-06-09T10:00:25.000Z",
                                "resultDisplay": "Subagent codebase_investigator Finished",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    lineage = build_timeline_lineage([_session(gemini_file, AGENT_GEMINI)])
    child_record = next(record for record in lineage if record["kind"] == "subagent")

    assert child_record["session_id"] == "gemini-parent:codebase_investigator-1"
    assert child_record["parent_session_id"] == "gemini-parent"
    assert child_record["agent_name"] == "Codebase Investigator Agent"
    assert child_record["status"] == "success"
    assert child_record["last_agent_message"] == "Subagent codebase_investigator Finished"


def test_gemini_jsonl_lineage_represents_subagent_tool_call(tmp_path: Path) -> None:
    gemini_file = tmp_path / "session.jsonl"
    _write_jsonl(
        gemini_file,
        [
            {
                "sessionId": "gemini-jsonl-parent",
                "startTime": "2026-06-09T10:00:00.000Z",
            },
            {
                "id": "m1",
                "timestamp": "2026-06-09T10:00:05.000Z",
                "type": "gemini",
                "toolCalls": [
                    {
                        "id": "codebase_investigator-1",
                        "name": "codebase_investigator",
                        "displayName": "Codebase Investigator Agent",
                        "status": "success",
                        "timestamp": "2026-06-09T10:00:25.000Z",
                        "resultDisplay": "Subagent codebase_investigator Finished",
                    }
                ],
            },
        ],
    )

    lineage = build_timeline_lineage([_session(gemini_file, AGENT_GEMINI)])
    child_record = next(record for record in lineage if record["kind"] == "subagent")

    assert child_record["session_id"] == "gemini-jsonl-parent:codebase_investigator-1"
    assert child_record["parent_session_id"] == "gemini-jsonl-parent"


def test_pi_lineage_marks_parent_child_messages_as_branch_not_subagent(tmp_path: Path) -> None:
    pi_file = tmp_path / "pi-session.jsonl"
    _write_jsonl(
        pi_file,
        [
            {"type": "session", "id": "pi-session", "timestamp": "2026-06-09T10:00:00.000Z"},
            {
                "type": "message",
                "id": "u1",
                "timestamp": "2026-06-09T10:00:01.000Z",
                "message": {"role": "user", "content": "Hello"},
            },
            {
                "type": "message",
                "id": "a1",
                "parentId": "u1",
                "timestamp": "2026-06-09T10:00:02.000Z",
                "message": {"role": "assistant", "content": "Hi"},
            },
        ],
    )

    lineage = build_timeline_lineage([_session(pi_file, AGENT_PI)])

    assert {record["kind"] for record in lineage} == {"main", "branch"}
    assert not any(record["kind"] == "subagent" for record in lineage)
