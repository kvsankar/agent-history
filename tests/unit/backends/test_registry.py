"""Tests for the internal coding-agent backend registry."""

from __future__ import annotations

from pathlib import Path

from agent_history.adapters.inventory import InventoryProvider
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
