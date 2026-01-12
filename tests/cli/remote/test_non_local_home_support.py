"""Non-local home support for session list/export."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.cli import assert_cli_success, run_cli_subprocess
from tests.helpers.gap_helpers import ensure_config_env, load_json_output
from tests.helpers.session_builders import ClaudeSessionBuilder
from tests.helpers.workspace_paths import encode_workspace_path


pytestmark = pytest.mark.scope


class TestNonLocalHomes:
    """Non-local homes should resolve and return sessions."""

    def test_wsl_home_session_listing(self, tmp_path: Path) -> None:
        wsl_projects = tmp_path / "wsl-home" / ".claude" / "projects"
        wsl_projects.mkdir(parents=True, exist_ok=True)

        encoded = encode_workspace_path("/home/testuser/wsl-project")
        builder = ClaudeSessionBuilder(workspace=encoded, session_id="wsl-session-001")
        builder.add_user_message("WSL hello")
        builder.add_assistant_message("WSL response")
        builder.write_to(wsl_projects)

        env = {
            "HOME": str(tmp_path),
            "CLAUDE_WSL_TEST_DISTRO": "UbuntuTest",
            "CLAUDE_WSL_PROJECTS_DIR": str(wsl_projects),
        }
        env = ensure_config_env(env, tmp_path / ".agent-history")

        result = run_cli_subprocess(
            ["session", "list", "--home", "wsl:UbuntuTest", "--aw", "--format", "json"],
            env=env,
        )

        assert_cli_success(result, "WSL home session listing should succeed")
        sessions = load_json_output(result)
        assert sessions, "Expected WSL sessions to be listed"
        assert all(s.get("home") == "wsl:UbuntuTest" for s in sessions)

    def test_wsl_home_session_export(self, tmp_path: Path) -> None:
        wsl_projects = tmp_path / "wsl-home-export" / ".claude" / "projects"
        wsl_projects.mkdir(parents=True, exist_ok=True)

        encoded = encode_workspace_path("/home/testuser/wsl-export")
        builder = ClaudeSessionBuilder(workspace=encoded, session_id="wsl-session-export-001")
        builder.add_user_message("WSL export hello")
        builder.add_assistant_message("WSL export response")
        builder.write_to(wsl_projects)

        env = {
            "HOME": str(tmp_path),
            "CLAUDE_WSL_TEST_DISTRO": "UbuntuTest",
            "CLAUDE_WSL_PROJECTS_DIR": str(wsl_projects),
        }
        env = ensure_config_env(env, tmp_path / ".agent-history")
        output_dir = tmp_path / "wsl-export-output"

        result = run_cli_subprocess(
            ["session", "export", "--home", "wsl:UbuntuTest", "--aw", "-o", str(output_dir)],
            env=env,
        )

        assert_cli_success(result, "WSL home session export should succeed")
        assert list(output_dir.rglob("*.md")), "Expected WSL export markdown files"

    def test_windows_home_session_listing(self, tmp_path: Path) -> None:
        windows_projects = tmp_path / "windows-home" / ".claude" / "projects"
        windows_projects.mkdir(parents=True, exist_ok=True)

        encoded = encode_workspace_path("/mnt/c/Users/testuser/windows-project")
        builder = ClaudeSessionBuilder(workspace=encoded, session_id="win-session-001")
        builder.add_user_message("Windows hello")
        builder.add_assistant_message("Windows response")
        builder.write_to(windows_projects)

        env = {
            "HOME": str(tmp_path),
            "CLAUDE_WINDOWS_PROJECTS_DIR": str(windows_projects),
        }
        env = ensure_config_env(env, tmp_path / ".agent-history")

        result = run_cli_subprocess(
            ["session", "list", "--home", "windows", "--aw", "--format", "json"],
            env=env,
        )

        assert_cli_success(result, "Windows home session listing should succeed")
        assert "No sessions found" not in result.stderr, "Windows home returned no sessions"
        sessions = load_json_output(result)
        assert sessions, "Expected Windows sessions to be listed"
        assert all(s.get("home") == "windows" for s in sessions)

    def test_windows_home_session_export(self, tmp_path: Path) -> None:
        windows_projects = tmp_path / "windows-home-export" / ".claude" / "projects"
        windows_projects.mkdir(parents=True, exist_ok=True)

        encoded = encode_workspace_path("/mnt/c/Users/testuser/windows-export")
        builder = ClaudeSessionBuilder(workspace=encoded, session_id="win-session-export-001")
        builder.add_user_message("Windows export hello")
        builder.add_assistant_message("Windows export response")
        builder.write_to(windows_projects)

        env = {
            "HOME": str(tmp_path),
            "CLAUDE_WINDOWS_PROJECTS_DIR": str(windows_projects),
        }
        env = ensure_config_env(env, tmp_path / ".agent-history")
        output_dir = tmp_path / "windows-export-output"

        result = run_cli_subprocess(
            ["session", "export", "--home", "windows", "--aw", "-o", str(output_dir)],
            env=env,
        )

        assert_cli_success(result, "Windows home session export should succeed")
        assert list(output_dir.rglob("*.md")), "Expected Windows export markdown files"
