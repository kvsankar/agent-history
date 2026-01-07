"""Tests for Cross-Home Access Guard feature.

When accessing non-local homes (--windows, --wsl, -r user@host, --ah) from within
a local workspace, the command requires either:
1. An explicit workspace pattern (-n <pattern>)
2. A project that ties the local workspace to remote workspaces
3. The --aw flag (explicitly requesting all workspaces)

Rationale: The same path on different machines (e.g., /home/user/myproject on
local vs remote) may be completely unrelated codebases. Implicit path matching
across homes would show misleading results.

The guard applies to all session verbs: list, export, and stats.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from tests.helpers.cli import run_cli_subprocess
from tests.v1.test_workspace_decode import create_workspace_fixture

# Session verbs that the cross-home guard applies to
SESSION_VERBS = ["list", "export", "stats"]


@pytest.fixture
def cross_home_test_setup(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create a test home with workspaces for cross-home guard testing.

    Creates:
    - A local workspace at /home/user/myproject
    - A simulated local workspace directory (for cwd testing)
    """
    # Create the actual directory structure
    local_project = tmp_path / "home" / "user" / "myproject"
    local_project.mkdir(parents=True)

    # Create local workspace with sessions
    create_workspace_fixture(tmp_path, "/home/user/myproject", num_sessions=2)

    # Create another workspace without a project
    another_project = tmp_path / "home" / "user" / "another"
    another_project.mkdir(parents=True)
    create_workspace_fixture(tmp_path, "/home/user/another", num_sessions=1)

    # Environment for test isolation
    env = os.environ.copy()
    env["AGENT_HISTORY_HOME"] = str(tmp_path)
    env["HOME"] = str(tmp_path)

    yield {
        "path": tmp_path,
        "env": env,
        "local_project": local_project,
    }


@pytest.fixture
def cross_home_with_project(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create a test home with a project that ties workspaces together.

    Creates:
    - A local workspace at /home/user/myproject
    - A project configuration that ties local and remote workspaces
    """
    # Create the actual directory structure
    local_project = tmp_path / "home" / "user" / "myproject"
    local_project.mkdir(parents=True)

    # Create local workspace with sessions
    create_workspace_fixture(tmp_path, "/home/user/myproject", num_sessions=2)

    # Create project configuration in the agent-history config store
    config_dir = tmp_path / ".agent-history"
    config_dir.mkdir(parents=True, exist_ok=True)
    encoded_ws = "/home/user/myproject".replace("/", "-")
    if not encoded_ws.startswith("-"):
        encoded_ws = "-" + encoded_ws
    projects_config = {
        "version": 2,
        "projects": {
            "myproj": {
                "local": [encoded_ws],
                "windows": [encoded_ws],
                "remote:vm01": [encoded_ws],
            }
        },
    }
    project_file = config_dir / "config.json"
    with open(project_file, "w") as f:
        json.dump(projects_config, f)

    # Environment for test isolation
    env = os.environ.copy()
    env["AGENT_HISTORY_HOME"] = str(tmp_path)
    env["HOME"] = str(tmp_path)
    env["AGENT_HISTORY_CONFIG_DIR"] = str(config_dir)

    yield {
        "path": tmp_path,
        "env": env,
        "local_project": local_project,
        "project_file": project_file,
    }


def assert_cross_home_guard_error(result: Any) -> None:
    """Assert that the result is a cross-home guard error."""
    assert result.returncode != 0, f"Expected error, got success with: {result.stdout}"
    error_output = result.stderr.lower()
    assert (
        "pattern" in error_output or "project" in error_output or "requires" in error_output
    ), f"Expected error about pattern/project, got: {result.stderr}"


class TestCrossHomeGuardWindowsFlag:
    """Test Cross-Home Access Guard with --windows flag for all session verbs."""

    # --- session list ---

    def test_windows_list_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session list --windows without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "list", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_windows_list_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session list --windows -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "list", "--windows", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- session export ---

    def test_windows_export_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session export --windows without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "export", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_windows_export_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session export --windows -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "export", "--windows", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- session stats ---

    def test_windows_stats_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session stats --windows without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "stats", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_windows_stats_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session stats --windows -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "stats", "--windows", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- ws list ---

    def test_ws_list_windows_without_pattern_errors(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """ws list --windows without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["ws", "list", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode != 0, f"Expected error, got success with: {result.stdout}"

    def test_ws_list_windows_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """ws list --windows with -n pattern should succeed."""
        result = run_cli_subprocess(
            ["ws", "list", "--windows", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"


class TestCrossHomeGuardWslFlag:
    """Test Cross-Home Access Guard with --wsl flag for all session verbs."""

    # --- session list ---

    def test_wsl_list_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session list --wsl without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "list", "--wsl"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_wsl_list_with_pattern_succeeds(self, cross_home_test_setup: Dict[str, Any]) -> None:
        """session list --wsl -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "list", "--wsl", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- session export ---

    def test_wsl_export_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session export --wsl without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "export", "--wsl"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_wsl_export_with_pattern_succeeds(self, cross_home_test_setup: Dict[str, Any]) -> None:
        """session export --wsl -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "export", "--wsl", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- session stats ---

    def test_wsl_stats_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session stats --wsl without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "stats", "--wsl"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_wsl_stats_with_pattern_succeeds(self, cross_home_test_setup: Dict[str, Any]) -> None:
        """session stats --wsl -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "stats", "--wsl", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"


class TestCrossHomeGuardRemoteFlag:
    """Test Cross-Home Access Guard with -r (remote) flag for all session verbs."""

    # --- session list ---

    def test_remote_list_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session list -r vm01 without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "list", "-r", "vm01"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_remote_list_with_pattern_succeeds(self, cross_home_test_setup: Dict[str, Any]) -> None:
        """session list -r vm01 -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "list", "-r", "vm01", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- session export ---

    def test_remote_export_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session export -r vm01 without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "export", "-r", "vm01"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_remote_export_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session export -r vm01 -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "export", "-r", "vm01", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- session stats ---

    def test_remote_stats_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session stats -r vm01 without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "stats", "-r", "vm01"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_remote_stats_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session stats -r vm01 -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "stats", "-r", "vm01", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- ws list ---

    def test_ws_list_remote_without_pattern_errors(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """ws list -r vm01 without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["ws", "list", "-r", "vm01"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode != 0, f"Expected error, got success with: {result.stdout}"

    def test_ws_list_remote_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """ws list -r vm01 with -n pattern should succeed."""
        result = run_cli_subprocess(
            ["ws", "list", "-r", "vm01", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"


class TestCrossHomeGuardAllHomesFlag:
    """Test Cross-Home Access Guard with --ah (all homes) flag for all session verbs."""

    # --- session list ---

    def test_all_homes_list_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session list --ah without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "list", "--ah"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_all_homes_list_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session list --ah -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "list", "--ah", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    def test_all_homes_list_with_all_workspaces_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session list --ah --aw should succeed (explicitly requesting all workspaces)."""
        result = run_cli_subprocess(
            ["session", "list", "--ah", "--aw"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- session export ---

    def test_all_homes_export_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session export --ah without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "export", "--ah"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_all_homes_export_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session export --ah -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "export", "--ah", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    def test_all_homes_export_with_all_workspaces_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session export --ah --aw should succeed (explicitly requesting all workspaces)."""
        result = run_cli_subprocess(
            ["session", "export", "--ah", "--aw"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- session stats ---

    def test_all_homes_stats_without_pattern_errors_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session stats --ah without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["session", "stats", "--ah"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert_cross_home_guard_error(result)

    def test_all_homes_stats_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session stats --ah -n myproject should succeed."""
        result = run_cli_subprocess(
            ["session", "stats", "--ah", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    def test_all_homes_stats_with_all_workspaces_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session stats --ah --aw should succeed (explicitly requesting all workspaces)."""
        result = run_cli_subprocess(
            ["session", "stats", "--ah", "--aw"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- ws list ---

    def test_ws_list_all_homes_without_pattern_errors(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """ws list --ah without pattern should error when in a local workspace."""
        result = run_cli_subprocess(
            ["ws", "list", "--ah"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode != 0, f"Expected error, got success with: {result.stdout}"

    def test_ws_list_all_homes_with_all_workspaces_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """ws list --ah with --aw should succeed."""
        result = run_cli_subprocess(
            ["ws", "list", "--ah", "--aw"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"


class TestCrossHomeGuardWithProject:
    """Test that projects allow cross-home access without explicit pattern for all verbs."""

    # --- session list ---

    def test_windows_list_with_project_succeeds(
        self, cross_home_with_project: Dict[str, Any]
    ) -> None:
        """session list --windows should succeed when project ties homes together."""
        result = run_cli_subprocess(
            ["session", "list", "--windows"],
            env=cross_home_with_project["env"],
            cwd=cross_home_with_project["local_project"],
        )
        assert result.returncode == 0, f"Expected success with project, got error: {result.stderr}"

    def test_remote_list_with_project_succeeds(
        self, cross_home_with_project: Dict[str, Any]
    ) -> None:
        """session list -r vm01 should succeed when project ties homes together."""
        result = run_cli_subprocess(
            ["session", "list", "-r", "vm01"],
            env=cross_home_with_project["env"],
            cwd=cross_home_with_project["local_project"],
        )
        assert result.returncode == 0, f"Expected success with project, got error: {result.stderr}"

    def test_all_homes_list_with_project_succeeds(
        self, cross_home_with_project: Dict[str, Any]
    ) -> None:
        """session list --ah should succeed when project ties homes together."""
        result = run_cli_subprocess(
            ["session", "list", "--ah"],
            env=cross_home_with_project["env"],
            cwd=cross_home_with_project["local_project"],
        )
        assert result.returncode == 0, f"Expected success with project, got error: {result.stderr}"

    # --- session export ---

    def test_windows_export_with_project_succeeds(
        self, cross_home_with_project: Dict[str, Any]
    ) -> None:
        """session export --windows should succeed when project ties homes together."""
        result = run_cli_subprocess(
            ["session", "export", "--windows"],
            env=cross_home_with_project["env"],
            cwd=cross_home_with_project["local_project"],
        )
        assert result.returncode == 0, f"Expected success with project, got error: {result.stderr}"

    def test_remote_export_with_project_succeeds(
        self, cross_home_with_project: Dict[str, Any]
    ) -> None:
        """session export -r vm01 should succeed when project ties homes together."""
        result = run_cli_subprocess(
            ["session", "export", "-r", "vm01"],
            env=cross_home_with_project["env"],
            cwd=cross_home_with_project["local_project"],
        )
        assert result.returncode == 0, f"Expected success with project, got error: {result.stderr}"

    def test_all_homes_export_with_project_succeeds(
        self, cross_home_with_project: Dict[str, Any]
    ) -> None:
        """session export --ah should succeed when project ties homes together."""
        result = run_cli_subprocess(
            ["session", "export", "--ah"],
            env=cross_home_with_project["env"],
            cwd=cross_home_with_project["local_project"],
        )
        assert result.returncode == 0, f"Expected success with project, got error: {result.stderr}"

    # --- session stats ---

    def test_windows_stats_with_project_succeeds(
        self, cross_home_with_project: Dict[str, Any]
    ) -> None:
        """session stats --windows should succeed when project ties homes together."""
        result = run_cli_subprocess(
            ["session", "stats", "--windows"],
            env=cross_home_with_project["env"],
            cwd=cross_home_with_project["local_project"],
        )
        assert result.returncode == 0, f"Expected success with project, got error: {result.stderr}"

    def test_remote_stats_with_project_succeeds(
        self, cross_home_with_project: Dict[str, Any]
    ) -> None:
        """session stats -r vm01 should succeed when project ties homes together."""
        result = run_cli_subprocess(
            ["session", "stats", "-r", "vm01"],
            env=cross_home_with_project["env"],
            cwd=cross_home_with_project["local_project"],
        )
        assert result.returncode == 0, f"Expected success with project, got error: {result.stderr}"

    def test_all_homes_stats_with_project_succeeds(
        self, cross_home_with_project: Dict[str, Any]
    ) -> None:
        """session stats --ah should succeed when project ties homes together."""
        result = run_cli_subprocess(
            ["session", "stats", "--ah"],
            env=cross_home_with_project["env"],
            cwd=cross_home_with_project["local_project"],
        )
        assert result.returncode == 0, f"Expected success with project, got error: {result.stderr}"


class TestCrossHomeGuardSkipConditions:
    """Test conditions when the cross-home guard is skipped for all verbs."""

    # --- Guard skipped when not in workspace ---

    def test_guard_skipped_list_when_not_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """Guard should be skipped for session list when not in a local workspace."""
        result = run_cli_subprocess(
            ["session", "list", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["path"],  # Root of test home, not a workspace
        )
        if result.returncode != 0:
            error_output = result.stderr.lower()
            assert not (
                "pattern" in error_output and "project" in error_output
            ), f"Guard should not trigger outside workspace: {result.stderr}"

    def test_guard_skipped_export_when_not_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """Guard should be skipped for session export when not in a local workspace."""
        result = run_cli_subprocess(
            ["session", "export", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["path"],
        )
        if result.returncode != 0:
            error_output = result.stderr.lower()
            assert not (
                "pattern" in error_output and "project" in error_output
            ), f"Guard should not trigger outside workspace: {result.stderr}"

    def test_guard_skipped_stats_when_not_in_workspace(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """Guard should be skipped for session stats when not in a local workspace."""
        result = run_cli_subprocess(
            ["session", "stats", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["path"],
        )
        if result.returncode != 0:
            error_output = result.stderr.lower()
            assert not (
                "pattern" in error_output and "project" in error_output
            ), f"Guard should not trigger outside workspace: {result.stderr}"

    # --- Guard skipped with --aw flag ---

    def test_guard_skipped_list_with_all_workspaces_flag(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """Guard should be skipped for session list when using --aw."""
        result = run_cli_subprocess(
            ["session", "list", "--windows", "--aw"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected --aw to bypass guard: {result.stderr}"

    def test_guard_skipped_export_with_all_workspaces_flag(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """Guard should be skipped for session export when using --aw."""
        result = run_cli_subprocess(
            ["session", "export", "--windows", "--aw"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected --aw to bypass guard: {result.stderr}"

    def test_guard_skipped_stats_with_all_workspaces_flag(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """Guard should be skipped for session stats when using --aw."""
        result = run_cli_subprocess(
            ["session", "stats", "--windows", "--aw"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected --aw to bypass guard: {result.stderr}"

    def test_ws_list_with_all_workspaces_bypasses_guard(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """ws list with --aw should bypass the cross-home guard."""
        result = run_cli_subprocess(
            ["ws", "list", "--windows", "--aw"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected --aw to bypass guard: {result.stderr}"


class TestCrossHomeGuardErrorMessages:
    """Test that cross-home guard produces helpful error messages for all verbs."""

    def test_error_message_list_mentions_pattern_option(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session list error message should mention -n pattern as a solution."""
        result = run_cli_subprocess(
            ["session", "list", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode != 0
        assert "-n" in result.stderr or "pattern" in result.stderr.lower()

    def test_error_message_export_mentions_pattern_option(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session export error message should mention -n pattern as a solution."""
        result = run_cli_subprocess(
            ["session", "export", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode != 0
        assert "-n" in result.stderr or "pattern" in result.stderr.lower()

    def test_error_message_stats_mentions_pattern_option(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session stats error message should mention -n pattern as a solution."""
        result = run_cli_subprocess(
            ["session", "stats", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode != 0
        assert "-n" in result.stderr or "pattern" in result.stderr.lower()

    def test_error_message_mentions_all_workspaces_option(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """Error message should mention --aw as a solution."""
        result = run_cli_subprocess(
            ["session", "list", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode != 0
        assert "--aw" in result.stderr or "all workspaces" in result.stderr.lower()

    def test_error_message_mentions_project_option(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """Error message should mention project as a solution."""
        result = run_cli_subprocess(
            ["session", "list", "--windows"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode != 0
        assert "project" in result.stderr.lower()


class TestCrossHomeGuardMultipleFlags:
    """Test cross-home guard with multiple remote/non-local flags for all verbs."""

    # --- session list ---

    def test_multiple_remote_flags_list_without_pattern_errors(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session list with multiple remote flags without pattern should error."""
        result = run_cli_subprocess(
            ["session", "list", "--windows", "--wsl"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode != 0, f"Expected error, got success with: {result.stdout}"

    def test_multiple_remote_flags_list_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session list with multiple remote flags and pattern should succeed."""
        result = run_cli_subprocess(
            ["session", "list", "--windows", "--wsl", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- session export ---

    def test_multiple_remote_flags_export_without_pattern_errors(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session export with multiple remote flags without pattern should error."""
        result = run_cli_subprocess(
            ["session", "export", "--windows", "--wsl"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode != 0, f"Expected error, got success with: {result.stdout}"

    def test_multiple_remote_flags_export_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session export with multiple remote flags and pattern should succeed."""
        result = run_cli_subprocess(
            ["session", "export", "--windows", "--wsl", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"

    # --- session stats ---

    def test_multiple_remote_flags_stats_without_pattern_errors(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session stats with multiple remote flags without pattern should error."""
        result = run_cli_subprocess(
            ["session", "stats", "--windows", "--wsl"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode != 0, f"Expected error, got success with: {result.stdout}"

    def test_multiple_remote_flags_stats_with_pattern_succeeds(
        self, cross_home_test_setup: Dict[str, Any]
    ) -> None:
        """session stats with multiple remote flags and pattern should succeed."""
        result = run_cli_subprocess(
            ["session", "stats", "--windows", "--wsl", "-n", "myproject"],
            env=cross_home_test_setup["env"],
            cwd=cross_home_test_setup["local_project"],
        )
        assert result.returncode == 0, f"Expected success, got error: {result.stderr}"
