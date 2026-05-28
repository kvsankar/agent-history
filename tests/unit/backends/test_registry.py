"""Tests for the internal coding-agent backend registry."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent_history.adapters.inventory import InventoryProvider
from agent_history.backends import ssh as ssh_backend
from agent_history.backends.registry import (
    AgentBackend,
    get_agent_choices,
    get_backend,
    register_backend,
    unregister_backend,
)
from agent_history.cli.parser import CLIParser
from agent_history.scope.context import ResolutionContext


def test_builtin_agent_choices_come_from_registry() -> None:
    """Built-in agent choices should be registry-backed."""
    choices = get_agent_choices()

    assert choices[0] == "auto"
    assert "claude" in choices
    assert "codex" in choices
    assert "gemini" in choices
    assert get_backend("claude") is not None


def test_registered_backend_is_visible_to_parser_and_inventory(tmp_path: Path) -> None:
    """A backend can be added without editing parser or inventory dispatch code."""
    session_file = tmp_path / "fake-session.jsonl"
    session_file.write_text('{"role":"user","content":"hello"}\n', encoding="utf-8")

    backend = AgentBackend(
        id="fake",
        label="Fake Agent",
        get_session_dir=lambda resolver, context: tmp_path,
        scan_sessions=lambda sessions_dir: [
            {
                "agent": "fake",
                "workspace": "/tmp/fake-workspace",
                "workspace_readable": "/tmp/fake-workspace",
                "file": session_file,
                "filename": session_file.name,
                "message_count": 0,
                "message_count_skipped": True,
            }
        ],
        list_workspaces=lambda sessions_dir, home: ["/tmp/fake-workspace"],
        read_messages=lambda path: [{"role": "user", "content": "hello"}],
        count_messages=lambda path: 1,
        render_markdown=lambda path, minimal, messages, level: "# Fake\n",
        message_to_unified=lambda msg: {
            "timestamp": msg.get("timestamp", ""),
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
        },
        extract_stats=lambda path: (
            {
                "session_id": "fake-session",
                "message_count": 1,
                "user_messages": 1,
                "assistant_messages": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_tokens": 0,
                "cache_read_tokens": 0,
                "first_timestamp": "2026-01-01T00:00:00Z",
                "last_timestamp": "2026-01-01T00:00:00Z",
            },
            [
                {
                    "session_id": "fake-session",
                    "type": "user",
                    "timestamp": "2026-01-01T00:00:00Z",
                }
            ],
            [],
        ),
        resolve_stats_workspace=lambda path, session_info, workspace: workspace
        or "/tmp/fake-workspace",
    )

    register_backend(backend)
    try:
        assert "fake" in get_agent_choices()

        request = CLIParser().parse(["session", "list", "--agent", "fake"])
        assert request.scope_args.agent == "fake"

        inventory = InventoryProvider(ResolutionContext())
        sessions = inventory.list_sessions("local", agent="fake")

        assert len(sessions) == 1
        assert sessions[0]["agent"] == "fake"
        assert sessions[0]["workspace_display"] == "/tmp/fake-workspace"
    finally:
        unregister_backend("fake")


def test_registered_backend_can_drive_remote_listing(monkeypatch, tmp_path: Path) -> None:
    """Remote SSH listing should consume backend commands, not central agent branches."""
    session_file = tmp_path / "fake-remote.jsonl"
    session_file.write_text('{"role":"user","content":"remote"}\n', encoding="utf-8")

    backend = AgentBackend(
        id="fake-remote",
        label="Fake Remote Agent",
        get_session_dir=lambda resolver, context: tmp_path,
        scan_sessions=lambda sessions_dir: [],
        list_workspaces=lambda sessions_dir, home: [],
        read_messages=lambda path: [{"role": "user", "content": "remote"}],
        count_messages=lambda path: 1,
        render_markdown=lambda path, minimal, messages, level: "# Fake Remote\n",
        message_to_unified=lambda msg: {
            "timestamp": msg.get("timestamp", ""),
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
        },
        extract_stats=lambda path: (
            {"session_id": "fake-remote", "message_count": 1},
            [{"session_id": "fake-remote", "type": "user", "timestamp": ""}],
            [],
        ),
        resolve_stats_workspace=lambda path, session_info, workspace: workspace or "fake-ws",
        remote_list_workspaces_command=lambda: "fake-list-workspaces",
        remote_parse_workspaces=lambda output: [f"parsed:{output.strip()}"],
        remote_list_sessions_command=lambda workspace: f"fake-list-sessions {workspace}",
        remote_workspace_readable=lambda workspace: f"readable:{workspace}",
        remote_file_path=lambda workspace, filename, session: f"/remote/{workspace}/{filename}",
    )

    commands: list[str] = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd[-1])
        if cmd[-1] == "fake-list-workspaces":
            return SimpleNamespace(returncode=0, stdout="fake-ws\n", stderr="")
        if cmd[-1] == "fake-list-sessions parsed:fake-ws":
            return SimpleNamespace(
                returncode=0,
                stdout="/remote/fake-ws/fake-remote.jsonl|12|1700000000|1|parsed:fake-ws\n",
                stderr="",
            )
        return SimpleNamespace(returncode=1, stdout="", stderr="unexpected command")

    monkeypatch.setattr(ssh_backend, "check_ssh_connection", lambda remote: (True, ""))
    monkeypatch.setattr(ssh_backend.subprocess, "run", fake_run)

    register_backend(backend)
    try:
        workspaces, workspace_error = ssh_backend.list_remote_workspaces(
            "user@example", agent="fake-remote"
        )
        sessions, session_error = ssh_backend.list_remote_sessions(
            "user@example", workspaces[0], agent="fake-remote"
        )
    finally:
        unregister_backend("fake-remote")

    assert workspace_error is None
    assert session_error is None
    assert workspaces == ["parsed:fake-ws"]
    assert sessions[0]["agent"] == "fake-remote"
    assert sessions[0]["remote_path"] == "/remote/fake-ws/fake-remote.jsonl"
    assert commands == ["fake-list-workspaces", "fake-list-sessions parsed:fake-ws"]
