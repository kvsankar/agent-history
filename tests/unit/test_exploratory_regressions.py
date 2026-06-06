"""Regression tests for exploratory cross-home/session issues."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_history.adapters.inventory import (
    InventoryProvider,
    _summarize_codex_sessions_dir,
)
from agent_history.adapters.remote import SSHRemoteClient
from agent_history.cli.orchestrator import CommandOrchestrator
from agent_history.cli.parser import CLIParser
from agent_history.scope.context import ResolutionContext
from agent_history.scope.resolver import ScopeResolver
from agent_history.storage.config import load_config
from tests.helpers.session_builders import ClaudeSessionBuilder
from tests.helpers.workspace_paths import encode_workspace_path


def _context(tmp_path: Path) -> ResolutionContext:
    return ResolutionContext(
        platform="linux",
        cwd=tmp_path,
        available_homes={"windows": ["alice"], "remote": ["vm01"], "wsl": []},
        claude_projects_dir=tmp_path / ".claude" / "projects",
        codex_sessions_dir=tmp_path / ".codex" / "sessions",
        gemini_sessions_dir=tmp_path / ".gemini" / "tmp",
        pi_sessions_dir=tmp_path / ".pi" / "agent" / "sessions",
    )


def test_home_add_windows_dispatches_without_scope_resolution(monkeypatch, tmp_path: Path) -> None:
    """Config-only home commands must not treat --windows as workspace scope."""
    context = _context(tmp_path)
    context.cwd_workspace = "/home/user/current-project"
    config_dir = tmp_path / ".agent-history"
    monkeypatch.setenv("AGENT_HISTORY_CONFIG_DIR", str(config_dir))

    orchestrator = CommandOrchestrator()
    orchestrator.context_builder.build = lambda: context

    def fail_resolve(*_args, **_kwargs):
        raise AssertionError("home add should not resolve workspaces")

    monkeypatch.setattr("agent_history.cli.orchestrator.ScopeResolver.resolve", fail_resolve)

    assert orchestrator.run(["home", "add", "--windows"]) == 0
    assert "windows" in load_config()["homes"]


def test_workspace_list_all_windows_uses_summaries_without_scope_resolution(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """`ws list --aw` should use source summaries instead of full scans."""
    context = _context(tmp_path)
    orchestrator = CommandOrchestrator()
    orchestrator.context_builder.build = lambda: context

    def fail_resolve(*_args, **_kwargs):
        raise AssertionError("all-workspace count listing should not resolve full scope")

    monkeypatch.setattr("agent_history.cli.orchestrator.ScopeResolver.resolve", fail_resolve)

    def fake_summaries(self, home: str, agent: str | None = None):
        assert home == "windows:alice"
        assert agent is None
        return [
            {
                "home": home,
                "workspace": "/mnt/c/work/project",
                "workspace_key": "path:/mnt/c/work/project",
                "workspace_display": "/mnt/c/work/project",
                "session_count": 2,
                "sessions": 2,
                "status": "unknown",
                "last_modified": "-",
                "agents": ["claude"],
            }
        ]

    monkeypatch.setattr(InventoryProvider, "list_workspace_summaries", fake_summaries)

    assert orchestrator.run(["ws", "list", "--windows", "--aw", "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["workspace"] == "/mnt/c/work/project"
    assert rows[0]["session_count"] == 2


def test_workspace_list_counts_flag_remains_compatible(monkeypatch, tmp_path: Path, capsys) -> None:
    """`ws list --counts` should keep working after counts became default."""
    context = _context(tmp_path)
    orchestrator = CommandOrchestrator()
    orchestrator.context_builder.build = lambda: context

    def fake_summaries(self, home: str, agent: str | None = None):
        return [
            {
                "home": home,
                "workspace": "/mnt/c/work/project",
                "workspace_key": "path:/mnt/c/work/project",
                "workspace_display": "/mnt/c/work/project",
                "session_count": 2,
                "sessions": 2,
                "status": "unknown",
                "last_modified": "2026-06-06T00:00:00",
                "agents": ["claude"],
            }
        ]

    monkeypatch.setattr(InventoryProvider, "list_workspace_summaries", fake_summaries)

    assert (
        orchestrator.run(["ws", "list", "--windows", "--aw", "--counts", "--format", "json"]) == 0
    )
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["session_count"] == 2
    assert rows[0]["last_modified"] == "2026-06-06T00:00:00"


def test_exact_path_scope_does_not_enumerate_workspaces(tmp_path: Path) -> None:
    """Full path positional scopes are exact targets and should not enumerate a home."""
    request = CLIParser().parse(
        ["session", "list", "--windows", "/mnt/c/sankar/projects/claude-history"]
    )
    assert request.scope_args.patterns == ["/mnt/c/sankar/projects/claude-history"]
    assert request.scope_args.name_patterns == []
    resolver = ScopeResolver(_context(tmp_path))

    def fail_enumerate(_home: str):
        raise AssertionError("exact path scope should not enumerate workspaces")

    resolver._workspace_stage._enumerate_workspaces_fn = fail_enumerate
    result = resolver.resolve(request.scope_args, load_sessions=False)

    assert result.success
    assert len(result.scope) == 1
    assert result.scope[0].home == "windows:alice"
    assert result.scope[0].workspace == "/mnt/c/sankar/projects/claude-history"


def test_reset_cache_target_is_positional_only() -> None:
    """Reset target selection should use one positional argument shape."""
    request = CLIParser().parse(["reset", "cache", "-y"])

    assert request.verb_args["reset_target"] == "cache"
    assert request.verb_args["reset_db"] is False
    assert request.verb_args["reset_config"] is False
    assert request.verb_args["reset_cache"] is True
    assert request.verb_args["yes"] is True


def test_reset_target_flags_are_not_supported() -> None:
    """Reset should not expose overlapping --db/--config/--settings flags."""
    with pytest.raises(SystemExit):
        CLIParser().parse(["reset", "--db"])


def test_gemini_index_does_not_build_resolution_context(monkeypatch, tmp_path: Path) -> None:
    """gemini-index should read the local index without resolving workspaces."""
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    orchestrator = CommandOrchestrator()

    def fail_build():
        raise AssertionError("gemini-index should not build resolution context")

    orchestrator.context_builder.build = fail_build

    assert orchestrator.run(["gemini-index", "--format", "json"]) == 0


def test_remote_session_listing_keeps_metadata_only_paths(monkeypatch, tmp_path: Path) -> None:
    """Remote list operations should not force a local cache fetch per session."""
    from agent_history.backends import ssh as ssh_backend

    remote_file = "/home/testuser/.claude/projects/-home-testuser-proj/session.jsonl"

    def fake_list_sessions(remote_host: str, workspace: str, agent: str = "claude"):
        assert remote_host == "testuser@vm01"
        assert workspace == "-home-testuser-proj"
        assert agent == "claude"
        return (
            [
                {
                    "file": remote_file,
                    "filename": "session.jsonl",
                    "workspace": workspace,
                    "message_count": 0,
                    "message_count_skipped": True,
                }
            ],
            None,
        )

    def fail_ensure(*_args, **_kwargs):
        raise AssertionError("list_sessions should not fetch local copies")

    monkeypatch.setattr(ssh_backend, "list_remote_sessions", fake_list_sessions)
    monkeypatch.setattr(SSHRemoteClient, "ensure_local_copy", fail_ensure)

    sessions = SSHRemoteClient().list_sessions(
        "testuser@vm01", "-home-testuser-proj", agent="claude"
    )

    assert len(sessions) == 1
    assert sessions[0]["file"] == Path(remote_file)
    assert sessions[0]["remote_path"] == remote_file
    assert sessions[0]["message_count_skipped"] is True


def test_remote_gemini_all_workspaces_preserves_hash_workspace_key(tmp_path: Path) -> None:
    """Remote Gemini --aw must pass the raw hash directory back to SSH listing."""
    project_hash = "0123456789abcdef0123456789abcdef"

    class FakeRemoteClient:
        def __init__(self):
            self.list_sessions_calls: list[tuple[str, str, str]] = []

        def list_workspaces(self, remote_host: str, agent: str = "claude"):
            assert remote_host == "vm01"
            assert agent == "gemini"
            return [project_hash]

        def list_sessions(self, remote_host: str, workspace: str, agent: str = "claude"):
            self.list_sessions_calls.append((remote_host, workspace, agent))
            return [
                {
                    "workspace": workspace,
                    "workspace_readable": workspace,
                    "file": tmp_path / "session-gemini.json",
                    "filename": "session-gemini.json",
                    "agent": agent,
                }
            ]

    remote_client = FakeRemoteClient()
    inventory = InventoryProvider(_context(tmp_path), remote_client=remote_client)

    workspaces = inventory.list_workspaces("remote:vm01", agent="gemini")
    sessions = inventory.list_sessions("remote:vm01", agent="gemini", workspace=workspaces[0])

    assert workspaces == [project_hash]
    assert remote_client.list_sessions_calls == [("vm01", project_hash, "gemini")]
    assert sessions[0]["workspace"] == project_hash
    assert sessions[0]["workspace_key"] == project_hash


def test_codex_workspace_summary_ignores_stale_and_out_of_root_index_entries(
    monkeypatch, tmp_path: Path
) -> None:
    """Codex summaries should count only existing rollout files under the sessions dir."""
    from agent_history.backends import codex as codex_backend

    sessions_dir = tmp_path / "sessions"
    good = sessions_dir / "2026" / "06" / "03" / "rollout-good.jsonl"
    good.parent.mkdir(parents=True)
    good.write_text('{"type":"session_meta","payload":{"cwd":"/repo/in-root"}}\n')
    non_rollout = sessions_dir / "2026" / "06" / "03" / "note.jsonl"
    non_rollout.write_text("{}\n")
    outside = tmp_path / "outside" / "rollout-outside.jsonl"
    outside.parent.mkdir()
    outside.write_text("{}\n")
    missing = sessions_dir / "2026" / "06" / "03" / "rollout-missing.jsonl"

    def fake_index(root: Path):
        assert root == sessions_dir
        return {
            str(good): "/repo/in-root",
            str(non_rollout): "/repo/non-rollout",
            str(outside): "/repo/outside",
            str(missing): "/repo/missing",
        }

    monkeypatch.setattr(codex_backend, "codex_ensure_index_updated", fake_index)

    rows = _summarize_codex_sessions_dir("local", sessions_dir)

    assert len(rows) == 1
    assert rows[0]["workspace"] == "/repo/in-root"
    assert rows[0]["session_count"] == 1


def test_windows_claude_exact_workspace_rewrites_readable_path(monkeypatch, tmp_path: Path) -> None:
    """Exact Windows/WSL path lookups should preserve the requested display path."""
    projects_dir = tmp_path / "windows-claude-projects"
    workspace = "/mnt/c/sankar/projects/claude-history"
    builder = ClaudeSessionBuilder(workspace=encode_workspace_path(workspace))
    builder.add_user_message("from windows")
    builder.write_to(projects_dir)
    monkeypatch.setenv("CLAUDE_WINDOWS_PROJECTS_DIR", str(projects_dir))

    inventory = InventoryProvider(_context(tmp_path))
    sessions = inventory.list_sessions("windows:alice", agent="claude", workspace=workspace)

    assert len(sessions) == 1
    assert sessions[0]["workspace_readable"] == workspace
