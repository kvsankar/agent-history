"""Focused Codex parser tests for rollout linkage metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_history.backends.codex import codex_message_to_unified, codex_read_jsonl_messages


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def test_codex_parser_preserves_session_turn_and_message_linkage(tmp_path: Path) -> None:
    session_file = tmp_path / "rollout-linkage.jsonl"
    records = [
        {
            "timestamp": "2026-06-09T10:00:00.000Z",
            "type": "session_meta",
            "payload": {
                "id": "thread-child",
                "parent_thread_id": "thread-parent",
                "forked_from_id": "thread-fork",
                "thread_source": "subagent",
                "cwd": "/tmp/project",
                "originator": "codex_cli_rs",
                "cli_version": "0.135.0",
            },
        },
        {
            "timestamp": "2026-06-09T10:00:01.000Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-1",
                "model_context_window": 258400,
            },
        },
        {
            "timestamp": "2026-06-09T10:00:02.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "id": "msg-user-1",
                "parent_id": None,
                "role": "user",
                "content": [{"type": "input_text", "text": "Inspect the repo"}],
            },
        },
        {
            "timestamp": "2026-06-09T10:00:03.000Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-1",
                "cwd": "/tmp/project",
                "approval_policy": "never",
                "model": "gpt-5.5",
            },
        },
        {
            "timestamp": "2026-06-09T10:00:04.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "id": "msg-assistant-1",
                "parent_id": "msg-user-1",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "I'll inspect it."}],
            },
        },
        {
            "timestamp": "2026-06-09T10:00:05.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "id": "item-call-1",
                "parent_id": "msg-assistant-1",
                "name": "shell",
                "arguments": '{"command": "ls"}',
                "call_id": "call-1",
            },
        },
        {
            "timestamp": "2026-06-09T10:00:06.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "id": "item-output-1",
                "parent_id": "item-call-1",
                "call_id": "call-1",
                "output": "README.md",
            },
        },
    ]
    _write_jsonl(session_file, records)

    messages, meta = codex_read_jsonl_messages(session_file)

    assert meta is not None
    assert meta["id"] == "thread-child"
    assert [message["id"] for message in messages] == [
        "msg-user-1",
        "msg-assistant-1",
        "item-call-1",
        "item-output-1",
    ]
    assert [message["parent_id"] for message in messages] == [
        None,
        "msg-user-1",
        "msg-assistant-1",
        "item-call-1",
    ]
    assert {message["session_id"] for message in messages} == {"thread-child"}
    assert {message["parent_session_id"] for message in messages} == {"thread-parent"}
    assert {message["forked_from_id"] for message in messages} == {"thread-fork"}
    assert {message["thread_source"] for message in messages} == {"subagent"}
    assert {message["turn_id"] for message in messages} == {"turn-1"}
    assert messages[2]["tool_call_id"] == "call-1"
    assert messages[3]["tool_call_id"] == "call-1"


def test_codex_parser_marks_subagent_notification_as_system_event(tmp_path: Path) -> None:
    session_file = tmp_path / "rollout-notification.jsonl"
    _write_jsonl(
        session_file,
        [
            {
                "timestamp": "2026-06-09T10:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "thread-parent", "cwd": "/tmp/project"},
            },
            {
                "timestamp": "2026-06-09T10:00:01.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "<subagent_notification>\n"
                                '{"agent_path":"agent-1","status":{"completed":"Reviewed it."}}\n'
                                "</subagent_notification>"
                            ),
                        }
                    ],
                },
            },
        ],
    )

    messages, _meta = codex_read_jsonl_messages(session_file)

    assert messages[0]["role"] == "system"
    assert messages[0]["is_subagent_notification"] is True
    assert messages[0]["subagent_agent_path"] == "agent-1"
    assert messages[0]["subagent_status"] == "completed"
    assert "<subagent_notification>" not in messages[0]["content"]
    assert "**Sub-agent completed**" in messages[0]["content"]
    assert "Reviewed it." in messages[0]["content"]


def test_codex_parser_marks_subagent_user_messages_as_parent_agent(tmp_path: Path) -> None:
    session_file = tmp_path / "rollout-child.jsonl"
    _write_jsonl(
        session_file,
        [
            {
                "timestamp": "2026-06-09T10:00:00.000Z",
                "type": "session_meta",
                "payload": {
                    "id": "thread-child",
                    "parent_thread_id": "thread-parent",
                    "thread_source": "subagent",
                    "cwd": "/tmp/project",
                },
            },
            {
                "timestamp": "2026-06-09T10:00:01.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Inspect this area."}],
                },
            },
        ],
    )

    messages, _meta = codex_read_jsonl_messages(session_file)

    assert messages[0]["role"] == "user"
    assert messages[0]["is_parent_agent_message"] is True
    assert messages[0]["thread_source"] == "subagent"


def test_codex_unified_messages_preserve_linkage_fields() -> None:
    msg = {
        "timestamp": "2026-06-09T10:00:04.000Z",
        "role": "assistant",
        "content": "Done",
        "id": "msg-assistant-1",
        "parent_id": "msg-user-1",
        "turn_id": "turn-1",
        "session_id": "thread-child",
        "parent_session_id": "thread-parent",
        "forked_from_id": "thread-fork",
        "thread_source": "subagent",
    }

    unified = codex_message_to_unified(msg)

    assert unified == {
        "timestamp": "2026-06-09T10:00:04.000Z",
        "role": "assistant",
        "content": "Done",
        "id": "msg-assistant-1",
        "parent_id": "msg-user-1",
        "turn_id": "turn-1",
        "session_id": "thread-child",
        "parent_session_id": "thread-parent",
        "forked_from_id": "thread-fork",
        "thread_source": "subagent",
    }


def test_codex_unified_tool_records_preserve_call_ids() -> None:
    tool_call = codex_message_to_unified(
        {
            "timestamp": "2026-06-09T10:00:05.000Z",
            "role": "assistant",
            "content": "**[Tool: shell]**",
            "is_tool_call": True,
            "tool_call_id": "call-1",
            "id": "item-call-1",
            "turn_id": "turn-1",
            "session_id": "thread-child",
        }
    )
    tool_result = codex_message_to_unified(
        {
            "timestamp": "2026-06-09T10:00:06.000Z",
            "role": "tool",
            "content": "**[Tool Result]**",
            "is_tool_result": True,
            "tool_call_id": "call-1",
            "id": "item-output-1",
            "parent_id": "item-call-1",
            "turn_id": "turn-1",
            "session_id": "thread-child",
        }
    )

    assert tool_call["role"] == "assistant"
    assert tool_call["tool_call_id"] == "call-1"
    assert tool_call["id"] == "item-call-1"
    assert tool_call["turn_id"] == "turn-1"
    assert tool_result["role"] == "system"
    assert tool_result["tool_result"] == {"tool_call_id": "call-1"}
    assert tool_result["id"] == "item-output-1"
    assert tool_result["parent_id"] == "item-call-1"
