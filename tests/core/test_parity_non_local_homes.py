"""Parity tests for non-local home support (WSL, web, remote cache).

These tests assert behavior required by the specs that is currently missing
from the modern implementation.
"""

import json
from pathlib import Path

from tests.helpers.cli import run_cli_subprocess
from tests.helpers.session_builders import ClaudeSessionBuilder


def test_wsl_home_sessions_are_listed(isolated_home, tmp_path: Path):
    """Sessions under a WSL home should be discoverable with --wsl."""
    wsl_projects_dir = tmp_path / "wsl_projects"

    builder = ClaudeSessionBuilder(workspace="-home-testuser-wsl-project")
    builder.add_user_message("hello from wsl")
    builder.write_to(wsl_projects_dir)

    env = dict(isolated_home["env"])
    env["CLAUDE_WSL_TEST_DISTRO"] = "TestDistro"
    env["CLAUDE_WSL_PROJECTS_DIR"] = str(wsl_projects_dir)

    result = run_cli_subprocess(
        ["session", "list", "--wsl", "--aw", "--format", "json"],
        env=env,
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip(), "Expected WSL sessions, got empty output"

    sessions = json.loads(result.stdout)
    assert sessions, "Expected at least one WSL session"


def test_web_home_appears_in_home_list(isolated_home):
    """home list --web should include a web home entry."""
    result = run_cli_subprocess(
        ["home", "list", "--web", "--format", "json"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip(), "Expected JSON output for homes"

    homes = json.loads(result.stdout)
    assert any(h.get("home") == "web" for h in homes), "Expected web home in list"


def test_remote_cache_is_used_for_sessions(tmp_path: Path):
    """Remote cache workspaces should be scanned for remote homes."""
    from agent_history.scope.cache import SessionCache
    from agent_history.scope.context import ResolutionContext

    projects_dir = tmp_path / ".claude" / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    builder = ClaudeSessionBuilder(
        workspace="remote_vm01_-home-testuser-remote-project",
        session_id="remote-session-001",
    )
    builder.add_user_message("hello from remote cache")
    builder.write_to(projects_dir)

    context = ResolutionContext(claude_projects_dir=projects_dir)
    cache = SessionCache(context)

    sessions = cache.get_sessions("remote:vm01", "/home/testuser/remote/project")
    assert sessions, "Expected remote cached sessions to be loaded"
