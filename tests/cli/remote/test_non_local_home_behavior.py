"""Behavior tests for non-local home support (WSL, web, remote cache).

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


def test_remote_sessions_use_remote_client(tmp_path: Path):
    """Remote homes should rely on remote client listings, not local cache dirs."""
    from agent_history.adapters.inventory import InventoryProvider
    from agent_history.scope.cache import SessionCache
    from agent_history.scope.context import ResolutionContext

    class FakeRemoteClient:
        def list_workspaces(self, remote_host: str, agent: str = "claude"):
            return ["-home-testuser-remote-project"]

        def list_sessions(self, remote_host: str, workspace: str, agent: str = "claude"):
            return [
                {
                    "workspace": workspace,
                    "workspace_readable": "/home/testuser/remote/project",
                    "file": tmp_path / "remote-session.jsonl",
                    "filename": "remote-session.jsonl",
                    "agent": "claude",
                }
            ]

    context = ResolutionContext()
    inventory = InventoryProvider(context, remote_client=FakeRemoteClient())
    cache = SessionCache(context, inventory_provider=inventory)

    sessions = cache.get_sessions("remote:vm01", "/home/testuser/remote/project")
    assert sessions, "Expected remote sessions from remote client"
