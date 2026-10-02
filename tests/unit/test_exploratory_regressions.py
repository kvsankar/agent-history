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
from agent_history.backends.claude import read_jsonl_messages
from agent_history.backends.gemini import gemini_get_workspace_readable
from agent_history.cli.orchestrator import CommandOrchestrator
from agent_history.cli.parser import CLIParser
from agent_history.handlers.base import CommandResult
from agent_history.handlers.stubs import SessionShowHandler
from agent_history.output.formatter import OutputFormatter, TsvFormatter
from agent_history.scope.context import OutputArgs, ResolutionContext
from agent_history.scope.resolver import ScopeResolver
from agent_history.scope.types import ConcreteRecord, WorkspaceSpecCurrent
from agent_history.storage.config import load_config, save_config
from agent_history.storage.metrics import init_metrics_db, sync_file_to_db
from tests.helpers.session_builders import ClaudeSessionBuilder
from tests.helpers.workspace_paths import create_workspace_fixture, encode_workspace_path


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


def test_home_show_local_dispatches_without_workspace_scope(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """home show <name> should show configured homes, not resolve workspace scope."""
    context = _context(tmp_path)
    context.cwd_workspace = "/home/user/current-project"
    orchestrator = CommandOrchestrator()
    orchestrator.context_builder.build = lambda: context

    def fail_resolve(*_args, **_kwargs):
        raise AssertionError("home show should not resolve workspaces")

    monkeypatch.setattr("agent_history.cli.orchestrator.ScopeResolver.resolve", fail_resolve)

    assert orchestrator.run(["home", "show", "local", "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["home"] == "local"


def test_home_remove_unknown_prints_each_error_once(capsys) -> None:
    """Empty error results should not write the same errors twice."""
    result = CommandResult(
        success=False,
        data=None,
        data_type="message",
        errors=["Home 'missing' not found.", "Configured homes: local"],
    )

    OutputFormatter().format(result, OutputArgs(format="table"))

    err_lines = capsys.readouterr().err.splitlines()
    assert err_lines == [
        "Error: Home 'missing' not found.",
        "Error: Configured homes: local",
    ]


def test_home_add_bare_wsl_is_not_reported_as_remote(monkeypatch, tmp_path: Path, capsys) -> None:
    """A saved bare WSL category home must not become remote:wsl in home list."""
    context = _context(tmp_path)
    monkeypatch.setenv("AGENT_HISTORY_CONFIG_DIR", str(tmp_path / ".agent-history"))
    save_config({"version": 1, "homes": ["wsl"], "sources": ["wsl"], "projects": {}})
    orchestrator = CommandOrchestrator()
    orchestrator.context_builder.build = lambda: context

    assert orchestrator.run(["home", "list", "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    homes = {row["home"]: row for row in rows}
    assert "remote:wsl" not in homes
    assert homes["wsl"]["type"] == "wsl"


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


def test_at_project_shorthand_maps_to_project_scope() -> None:
    """@name should be equivalent to --project name, not a workspace literal."""
    request = CLIParser().parse(["session", "list", "@tp"])

    assert request.scope_args.projects == ["tp"]
    assert request.scope_args.patterns == []


def test_at_project_shorthand_works_for_session_export() -> None:
    request = CLIParser().parse(["session", "export", "@tp", "-o", "/tmp/out"])

    assert request.scope_args.projects == ["tp"]
    assert request.scope_args.patterns == []
    assert request.verb_args["targets"] == []


def test_session_list_without_explicit_scope_uses_current_workspace_intent(
    tmp_path: Path,
) -> None:
    """Outside a workspace, session list should not silently expand to all workspaces."""
    request = CLIParser().parse(["session", "list"])
    template = ScopeResolver(_context(tmp_path))._build_template(request.scope_args)

    assert isinstance(template[0].workspace, WorkspaceSpecCurrent)


def test_session_export_without_explicit_scope_uses_current_workspace_intent(
    tmp_path: Path,
) -> None:
    """Bare session export must not become an accidental all-workspaces export."""
    request = CLIParser().parse(["session", "export", "-o", "/tmp/out"])
    template = ScopeResolver(_context(tmp_path))._build_template(request.scope_args)

    assert isinstance(template[0].workspace, WorkspaceSpecCurrent)


def test_all_workspaces_and_this_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match=r"--aw.*--this"):
        CLIParser().parse(["session", "list", "--aw", "--this"])


def test_inverted_date_range_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"--since.*after --until"):
        CLIParser().parse(
            ["session", "list", "--aw", "--since", "2026-06-01", "--until", "2026-01-01"]
        )


def test_jobs_must_be_positive() -> None:
    with pytest.raises(SystemExit):
        CLIParser().parse(["session", "export", "/tmp/ws", "-o", "/tmp/out", "--jobs", "0"])


def test_output_width_must_not_be_negative() -> None:
    with pytest.raises(SystemExit):
        CLIParser().parse(["session", "list", "--aw", "-w", "-5"])


def test_project_show_accepts_output_format() -> None:
    request = CLIParser().parse(["project", "show", "tp", "--format", "table"])

    assert request.output_args.format == "table"


def test_broken_pipe_is_quiet_success(monkeypatch, tmp_path: Path, capsys) -> None:
    """Closed downstream pipes should behave like normal CLI termination."""
    context = _context(tmp_path)
    orchestrator = CommandOrchestrator()
    orchestrator.context_builder.build = lambda: context

    def raise_broken_pipe(*_args, **_kwargs):
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr(orchestrator.formatter, "format", raise_broken_pipe)

    assert orchestrator.run(["home", "list"]) == 0
    assert "Broken pipe" not in capsys.readouterr().err


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


def test_reset_all_removes_codex_workspace_index(monkeypatch, tmp_path: Path) -> None:
    """Reset all should clear every cagelens-managed index file."""
    config_dir = tmp_path / ".cagelens"
    config_dir.mkdir()
    codex_index = config_dir / "codex_index.json"
    codex_index.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(config_dir))

    assert CommandOrchestrator().run(["reset", "all", "-y"]) == 0

    assert not codex_index.exists()


def test_claude_workspace_with_space_is_listed_by_session_scope(tmp_path: Path) -> None:
    """Claude session scanning should not drop encoded workspaces containing spaces."""
    workspace = "/tmp/sp ace/proj"
    create_workspace_fixture(tmp_path, workspace, num_sessions=1)
    context = _context(tmp_path)
    request = CLIParser().parse(["session", "list", "--aw", "--agent", "claude"])

    result = ScopeResolver(context).resolve(request.scope_args)
    sessions = [session for record in result.scope for session in record.sessions]

    assert result.success
    assert len(sessions) == 1
    assert sessions[0]["workspace_display"] == workspace


def test_tsv_formatter_escapes_control_characters_in_cells() -> None:
    """Tabs/newlines inside data cells must not create extra TSV columns or rows."""
    output = TsvFormatter().format(
        [
            {
                "home": "local",
                "workspace": "/tmp/ta\tb/ws\nnext",
                "session_count": 1,
                "status": "missing",
                "last_modified": "2026-06-15T00:00:00",
            }
        ],
        "workspace_list",
        {},
    )

    lines = output.splitlines()
    assert len(lines) == 2
    cells = lines[1].split("\t")
    assert len(cells) == 5
    assert cells[1] == r"/tmp/ta\tb/ws\nnext"


def test_multi_remote_preflight_keeps_reachable_hosts(monkeypatch, tmp_path: Path, capsys) -> None:
    """One failed explicit remote should not discard successful remotes."""
    context = _context(tmp_path)
    context.available_homes["remote"] = []
    orchestrator = CommandOrchestrator()
    orchestrator.context_builder.build = lambda: context

    def fake_check(remote_host: str):
        return (remote_host == "goodhost", "" if remote_host == "goodhost" else "not found")

    def fake_summaries(self, home: str, agent: str | None = None):
        assert home == "remote:goodhost"
        assert agent == "claude"
        return [
            {
                "home": home,
                "workspace": "/home/test/project",
                "workspace_key": "/home/test/project",
                "workspace_display": "/home/test/project",
                "session_count": 1,
                "sessions": 1,
                "status": "ok",
                "last_modified": "2026-06-15T00:00:00",
                "agents": ["claude"],
            }
        ]

    monkeypatch.setattr("agent_history.backends.ssh.check_ssh_connection", fake_check)
    monkeypatch.setattr(InventoryProvider, "list_workspace_summaries", fake_summaries)

    exit_code = orchestrator.run(
        [
            "ws",
            "list",
            "--aw",
            "-r",
            "goodhost",
            "-r",
            "badhost.invalid",
            "--agent",
            "claude",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    rows = json.loads(captured.out)
    assert exit_code == 0
    assert len(rows) == 1
    assert rows[0]["home"] == "remote:goodhost"
    assert rows[0]["session_count"] == 1
    assert "badhost.invalid" in captured.err


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


def test_gemini_readable_does_not_label_plain_workspace_slug_as_hash() -> None:
    """Resolved Gemini names that are not hashes must remain readable names."""
    assert gemini_get_workspace_readable("swdev-with-ai") == "swdev-with-ai"


def test_session_show_matches_bare_filename_stem() -> None:
    """session show <id> should match a session whose filename is <id>.jsonl."""
    session_id = "019e8bf0-6c1a-75d1-9381-d2a787a1fd94"
    scope = [
        ConcreteRecord(
            home="local",
            workspace="/tmp/project",
            workspace_key="/tmp/project",
            workspace_display="/tmp/project",
            sessions=[
                {
                    "filename": f"{session_id}.jsonl",
                    "file": f"/tmp/project/{session_id}.jsonl",
                    "workspace": "/tmp/project",
                }
            ],
        )
    ]

    result = SessionShowHandler().execute(
        scope,
        {"session_id": session_id},
        OutputArgs(format="json"),
    )

    assert result.success
    assert result.data["filename"] == f"{session_id}.jsonl"


def test_claude_jsonl_utf8_bom_does_not_drop_first_message(tmp_path: Path) -> None:
    """A UTF-8 BOM at the start of a JSONL file should not hide the first record."""
    session_file = tmp_path / "bom.jsonl"
    lines = [
        {
            "type": "user",
            "sessionId": "bom-session",
            "uuid": "user-1",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {"role": "user", "content": "hello"},
        },
        {
            "type": "assistant",
            "sessionId": "bom-session",
            "uuid": "assistant-1",
            "timestamp": "2026-06-01T00:01:00Z",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
        },
    ]
    session_file.write_text(
        "\ufeff" + "\n".join(json.dumps(line) for line in lines) + "\n",
        encoding="utf-8",
    )

    messages = read_jsonl_messages(session_file)

    assert [message["role"] for message in messages] == ["user", "assistant"]


def test_metrics_sync_utf8_bom_counts_first_claude_message(monkeypatch, tmp_path: Path) -> None:
    """Metrics sync should parse BOM-prefixed Claude JSONL instead of silently losing it."""
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    session_file = tmp_path / "bom-metrics.jsonl"
    first = {
        "type": "user",
        "sessionId": "bom-metrics",
        "uuid": "user-1",
        "timestamp": "2026-06-01T00:00:00Z",
        "cwd": "/tmp/project",
        "message": {"role": "user", "content": "hello"},
    }
    second = {
        "type": "assistant",
        "sessionId": "bom-metrics",
        "uuid": "assistant-1",
        "timestamp": "2026-06-01T00:01:00Z",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    }
    session_file.write_text(
        "\ufeff" + json.dumps(first) + "\n" + json.dumps(second) + "\n",
        encoding="utf-8",
    )
    conn = init_metrics_db()
    try:
        assert sync_file_to_db(conn, session_file, workspace="/tmp/project", force=True)
        row = conn.execute(
            "SELECT message_count, user_messages, assistant_messages FROM sessions"
        ).fetchone()
    finally:
        conn.close()

    assert dict(row) == {"message_count": 2, "user_messages": 1, "assistant_messages": 1}


def test_stats_rejects_unknown_summary_grouping(monkeypatch, tmp_path: Path, capsys) -> None:
    """stats --by should reject unsupported dimensions like rollup already does."""
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)

    exit_code = CommandOrchestrator().run(["stats", "--by", "bogusdim"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Unsupported stats dimension" in captured.err


def test_home_add_accepts_bare_ssh_alias(monkeypatch, tmp_path: Path) -> None:
    """home add should accept the same bare SSH alias shape accepted by -r."""
    monkeypatch.setenv("AGENT_HISTORY_CONFIG_DIR", str(tmp_path / ".agent-history"))

    assert CommandOrchestrator().run(["home", "add", "ubuntuvm01"]) == 0

    assert "ubuntuvm01" in load_config()["homes"]


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
