"""Tests for GitHub Copilot CLI and VS Code Copilot backends."""

from __future__ import annotations

import json
from pathlib import Path

from agent_history.backends.copilot import (
    copilot_cli_read_messages,
    copilot_cli_scan_sessions,
    copilot_extract_stats,
    copilot_message_to_unified,
    copilot_vscode_get_workspace_from_session,
    copilot_vscode_read_messages,
    copilot_vscode_scan_session_roots,
    copilot_vscode_scan_sessions,
)


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )


def test_copilot_cli_scans_workspace_yaml_and_reads_events(tmp_path: Path) -> None:
    session_dir = tmp_path / "session-state" / "cli-session-1"
    events_file = session_dir / "events.jsonl"
    (session_dir / "workspace.yaml").parent.mkdir(parents=True)
    (session_dir / "workspace.yaml").write_text(
        "cwd: /home/sankar/stellantis/ttt-python\nclient_name: github/cli\n",
        encoding="utf-8",
    )
    _write_jsonl(
        events_file,
        [
            {
                "id": "e1",
                "parentId": None,
                "timestamp": "2026-06-18T13:55:33.966Z",
                "type": "session.start",
                "data": {"sessionId": "cli-session-1"},
            },
            {
                "id": "e2",
                "parentId": "e1",
                "timestamp": "2026-06-18T13:55:34.000Z",
                "type": "user.message",
                "data": {"content": "Build tic tac toe"},
            },
            {
                "id": "e3",
                "parentId": "e2",
                "timestamp": "2026-06-18T13:55:35.000Z",
                "type": "assistant.message",
                "data": {
                    "content": "I will inspect files.",
                    "model": "gpt-5",
                    "outputTokens": 12,
                    "toolRequests": [
                        {"toolCallId": "tool-1", "name": "read_file", "arguments": {}}
                    ],
                },
            },
            {
                "id": "e4",
                "parentId": "e3",
                "timestamp": "2026-06-18T13:55:36.000Z",
                "type": "tool.execution_start",
                "data": {
                    "toolCallId": "tool-1",
                    "toolName": "read_file",
                    "arguments": {"filePath": "README.md"},
                },
            },
            {
                "id": "e5",
                "parentId": "e4",
                "timestamp": "2026-06-18T13:55:37.000Z",
                "type": "tool.execution_complete",
                "data": {
                    "toolCallId": "tool-1",
                    "toolName": "read_file",
                    "output": "README contents",
                    "success": True,
                },
            },
        ],
    )

    sessions = copilot_cli_scan_sessions(sessions_dir=tmp_path / "session-state")
    messages = copilot_cli_read_messages(events_file)

    assert len(sessions) == 1
    assert sessions[0]["agent"] == "copilot-cli"
    assert sessions[0]["workspace"] == "/home/sankar/stellantis/ttt-python"
    assert sessions[0]["message_count"] == 2
    assert [message["role"] for message in messages] == ["user", "assistant", "tool", "tool"]
    assert messages[1]["model"] == "gpt-5"
    assert messages[2]["is_tool_call"] is True
    assert messages[3]["is_tool_result"] is True


def test_copilot_vscode_scans_workspace_json_and_reads_transcript(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspaceStorage" / "hash123"
    transcript = workspace_dir / "GitHub.copilot-chat" / "transcripts" / "chat-1.jsonl"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "workspace.json").write_text(
        json.dumps({"folder": "file:///D:/stellantis/pre/ttt-python"}),
        encoding="utf-8",
    )
    _write_jsonl(
        transcript,
        [
            {
                "id": "v1",
                "parentId": None,
                "timestamp": "2026-06-18T14:00:00.000Z",
                "type": "session.start",
                "data": {"sessionId": "chat-1", "producer": "copilot-agent"},
            },
            {
                "id": "v2",
                "parentId": "v1",
                "timestamp": "2026-06-18T14:00:01.000Z",
                "type": "user.message",
                "data": {"content": "Create a CLI game"},
            },
            {
                "id": "v3",
                "parentId": "v2",
                "timestamp": "2026-06-18T14:00:02.000Z",
                "type": "assistant.message",
                "data": {"content": [{"text": "I will edit the project."}], "model": "gpt-5"},
            },
            {
                "id": "v4",
                "parentId": "v3",
                "timestamp": "2026-06-18T14:00:03.000Z",
                "type": "tool.execution_start",
                "data": {
                    "toolCallId": "tool-v1",
                    "toolName": "edit_file",
                    "arguments": {"filePath": "game.py"},
                },
            },
            {
                "id": "v5",
                "parentId": "v4",
                "timestamp": "2026-06-18T14:00:04.000Z",
                "type": "tool.execution_complete",
                "data": {
                    "toolCallId": "tool-v1",
                    "toolName": "edit_file",
                    "output": {"ok": True},
                },
            },
        ],
    )

    sessions = copilot_vscode_scan_sessions(sessions_dir=tmp_path / "workspaceStorage")
    messages = copilot_vscode_read_messages(transcript)

    assert (
        copilot_vscode_get_workspace_from_session(transcript) == "D:\\stellantis\\pre\\ttt-python"
    )
    assert len(sessions) == 1
    assert sessions[0]["agent"] == "copilot-vscode"
    assert sessions[0]["workspace"] == "D:\\stellantis\\pre\\ttt-python"
    assert sessions[0]["message_count"] == 2
    assert [message["role"] for message in messages] == ["user", "assistant", "tool", "tool"]
    assert messages[1]["content"] == "I will edit the project."
    assert messages[2]["tool_name"] == "edit_file"
    assert messages[3]["is_tool_result"] is True


def test_copilot_vscode_stats_uses_transcript_stem_as_session_id(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspaceStorage" / "hash123"
    transcript_a = workspace_dir / "GitHub.copilot-chat" / "transcripts" / "chat-a.jsonl"
    transcript_b = workspace_dir / "GitHub.copilot-chat" / "transcripts" / "chat-b.jsonl"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "workspace.json").write_text(
        json.dumps({"folder": "file:///home/sankar/project"}),
        encoding="utf-8",
    )
    for transcript, session_id in ((transcript_a, "chat-a"), (transcript_b, "chat-b")):
        _write_jsonl(
            transcript,
            [
                {
                    "id": f"{session_id}-1",
                    "timestamp": "2026-06-18T14:00:00.000Z",
                    "type": "session.start",
                    "data": {"sessionId": session_id},
                },
                {
                    "id": f"{session_id}-2",
                    "timestamp": "2026-06-18T14:00:01.000Z",
                    "type": "user.message",
                    "data": {"content": "Hello"},
                },
            ],
        )

    stats_a, messages_a, _tools_a = copilot_extract_stats(transcript_a, "copilot-vscode")
    stats_b, messages_b, _tools_b = copilot_extract_stats(transcript_b, "copilot-vscode")

    assert stats_a["session_id"] == "chat-a"
    assert stats_b["session_id"] == "chat-b"
    assert messages_a[0]["session_id"] == "chat-a"
    assert messages_b[0]["session_id"] == "chat-b"


def test_copilot_preserves_audit_events_and_reasoning_text(tmp_path: Path) -> None:
    events_file = tmp_path / "session-state" / "cli-session-2" / "events.jsonl"
    _write_jsonl(
        events_file,
        [
            {
                "id": "m1",
                "timestamp": "2026-06-18T14:00:00.000Z",
                "type": "assistant.message",
                "data": {
                    "content": "Answer",
                    "reasoningText": "I inspected the project shape.",
                    "reasoningOpaque": "opaque-ref",
                },
            },
            {
                "id": "m2",
                "timestamp": "2026-06-18T14:00:01.000Z",
                "type": "permission.requested",
                "data": {"toolName": "edit_file", "message": "Allow edit?"},
            },
        ],
    )

    messages = copilot_cli_read_messages(events_file)
    unified = copilot_message_to_unified(messages[0])

    assert messages[0]["thoughts"] == [
        {"subject": "reasoning", "description": "I inspected the project shape."}
    ]
    assert messages[0]["reasoning_opaque"] is True
    assert unified["thoughts"][0]["description"] == "I inspected the project shape."
    assert messages[1]["role"] == "system"
    assert messages[1]["raw_event_type"] == "permission.requested"
    assert "Allow edit?" in messages[1]["content"]


def test_copilot_tool_stats_uses_start_name_when_completion_omits_name(
    tmp_path: Path,
) -> None:
    events_file = tmp_path / "session-state" / "cli-session-3" / "events.jsonl"
    _write_jsonl(
        events_file,
        [
            {
                "id": "t1",
                "timestamp": "2026-06-18T14:00:00.000Z",
                "type": "tool.execution_start",
                "data": {"toolCallId": "tool-1", "toolName": "edit_file"},
            },
            {
                "id": "t2",
                "timestamp": "2026-06-18T14:00:01.000Z",
                "type": "tool.execution_complete",
                "data": {"toolCallId": "tool-1", "output": "ok"},
            },
        ],
    )

    _session_info, _messages, tool_uses = copilot_extract_stats(events_file, "copilot-cli")

    assert [tool["tool_name"] for tool in tool_uses] == ["edit_file", "edit_file"]


def test_copilot_shutdown_token_totals_are_used_for_stats(tmp_path: Path) -> None:
    events_file = tmp_path / "session-state" / "cli-session-4" / "events.jsonl"
    _write_jsonl(
        events_file,
        [
            {
                "id": "u1",
                "timestamp": "2026-06-18T14:00:00.000Z",
                "type": "user.message",
                "data": {"content": "Hello"},
            },
            {
                "id": "s1",
                "timestamp": "2026-06-18T14:00:02.000Z",
                "type": "session.shutdown",
                "data": {
                    "tokenDetails": {
                        "inputTokens": 14,
                        "outputTokens": 9,
                        "cacheReadTokens": 4,
                        "cacheCreationTokens": 2,
                    }
                },
            },
        ],
    )

    session_info, _messages, _tool_uses = copilot_extract_stats(events_file, "copilot-cli")

    assert session_info["input_tokens"] == 14
    assert session_info["output_tokens"] == 9
    assert session_info["cache_read_tokens"] == 4
    assert session_info["cache_creation_tokens"] == 2


def test_copilot_vscode_can_scan_multiple_workspace_storage_roots(tmp_path: Path) -> None:
    root_a = tmp_path / "Code" / "User" / "workspaceStorage"
    root_b = tmp_path / "Code - Insiders" / "User" / "workspaceStorage"
    for root, folder, stem in (
        (root_a, "file:///home/sankar/project-a", "chat-a"),
        (root_b, "file:///home/sankar/project-b", "chat-b"),
    ):
        workspace_dir = root / f"hash-{stem}"
        transcript = workspace_dir / "GitHub.copilot-chat" / "transcripts" / f"{stem}.jsonl"
        workspace_dir.mkdir(parents=True)
        (workspace_dir / "workspace.json").write_text(
            json.dumps({"folder": folder}),
            encoding="utf-8",
        )
        _write_jsonl(
            transcript,
            [
                {
                    "id": stem,
                    "timestamp": "2026-06-18T14:00:00.000Z",
                    "type": "user.message",
                    "data": {"content": stem},
                }
            ],
        )

    sessions = copilot_vscode_scan_session_roots([root_a, root_b])

    assert {session["workspace"] for session in sessions} == {
        "/home/sankar/project-a",
        "/home/sankar/project-b",
    }
