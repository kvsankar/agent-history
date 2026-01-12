"""Remote list/export should fetch sessions when no cache exists."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pytest

from agent_history.cli.orchestrator import CommandOrchestrator
from agent_history.scope.context import ResolutionContext
from tests.helpers.session_builders import ClaudeSessionBuilder
from tests.helpers.workspace_paths import encode_workspace_path


pytestmark = pytest.mark.scope


def _build_context(tmp_path: Path) -> ResolutionContext:
    local_root = tmp_path / "local"
    claude_dir = local_root / ".claude" / "projects"
    codex_dir = local_root / ".codex" / "sessions"
    gemini_dir = local_root / ".gemini" / "tmp"
    claude_dir.mkdir(parents=True, exist_ok=True)
    codex_dir.mkdir(parents=True, exist_ok=True)
    gemini_dir.mkdir(parents=True, exist_ok=True)
    return ResolutionContext(
        platform="linux",
        cwd=local_root,
        claude_projects_dir=claude_dir,
        codex_sessions_dir=codex_dir,
        gemini_sessions_dir=gemini_dir,
    )


def _setup_remote_fixture(tmp_path: Path) -> Tuple[str, str, Path]:
    remote_root = tmp_path / "remote-host"
    remote_projects = remote_root / ".claude" / "projects"
    remote_projects.mkdir(parents=True, exist_ok=True)

    remote_host = "user@remote-host"
    workspace_path = "/home/user/myproject"
    encoded_ws = encode_workspace_path(workspace_path)

    builder = ClaudeSessionBuilder(workspace=encoded_ws, session_id="remote-session-001")
    builder.add_user_message("Remote hello")
    builder.add_assistant_message("Remote response")
    session_file = builder.write_to(remote_projects)

    return remote_host, encoded_ws, session_file


def _patch_remote_list(
    monkeypatch, remote_host: str, encoded_ws: str, session_file: Path
) -> None:
    from agent_history.backends import ssh as ssh_backend

    def fake_list_remote_workspaces(remote: str, agent: str = "claude"):
        assert remote == remote_host
        assert agent == "claude"
        return [encoded_ws], None

    def fake_list_remote_sessions(remote: str, workspace: str, agent: str = "claude"):
        assert remote == remote_host
        assert agent == "claude"
        return (
            [
                {
                    "file": str(session_file),
                    "filename": session_file.name,
                    "workspace": workspace,
                    "home": f"remote:{remote_host}",
                    "agent": "claude",
                }
            ],
            None,
        )

    monkeypatch.setattr(ssh_backend, "list_remote_workspaces", fake_list_remote_workspaces)
    monkeypatch.setattr(ssh_backend, "list_remote_sessions", fake_list_remote_sessions)


def test_remote_session_list_fetches_sessions(monkeypatch, tmp_path: Path) -> None:
    remote_host, encoded_ws, session_file = _setup_remote_fixture(tmp_path)
    _patch_remote_list(monkeypatch, remote_host, encoded_ws, session_file)
    context = _build_context(tmp_path)

    orchestrator = CommandOrchestrator()
    result = orchestrator.run_with_context(
        ["session", "list", "-r", remote_host, "--aw"],
        context,
    )

    assert result.data, "Expected remote session list to fetch sessions from remote host"


def test_remote_session_export_fetches_sessions(monkeypatch, tmp_path: Path) -> None:
    remote_host, encoded_ws, session_file = _setup_remote_fixture(tmp_path)
    _patch_remote_list(monkeypatch, remote_host, encoded_ws, session_file)
    context = _build_context(tmp_path)
    output_dir = tmp_path / "remote-export"

    orchestrator = CommandOrchestrator()
    result = orchestrator.run_with_context(
        ["session", "export", "-r", remote_host, "--aw", "-o", str(output_dir)],
        context,
    )

    assert result.data.get("exported", 0) > 0, "Expected remote export to fetch sessions"
    assert list(output_dir.rglob("*.md")), "Expected remote export markdown files"
