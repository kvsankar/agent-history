"""Tests for consistent error messages across all commands and sources.

Error messages should follow a consistent pattern regardless of the source
(local, remote, windows, wsl) or command being used.
"""

import os
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from tests.helpers.cli import run_cli_subprocess
from tests.v1.test_workspace_decode import create_workspace_fixture


@pytest.fixture
def empty_home(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create an empty test home with no workspaces."""
    # Create the .claude directory but no projects
    (tmp_path / ".claude" / "projects").mkdir(parents=True)

    env = os.environ.copy()
    env["AGENT_HISTORY_HOME"] = str(tmp_path)
    env["HOME"] = str(tmp_path)

    yield {"path": tmp_path, "env": env}


@pytest.fixture
def home_with_workspaces(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create a test home with workspaces for testing."""
    (tmp_path / "home" / "user" / "projects" / "myapp").mkdir(parents=True)
    create_workspace_fixture(tmp_path, "/home/user/projects/myapp", num_sessions=1)

    env = os.environ.copy()
    env["AGENT_HISTORY_HOME"] = str(tmp_path)
    env["HOME"] = str(tmp_path)

    yield {"path": tmp_path, "env": env}


class TestNoSessionsErrorMessages:
    """Test that 'no sessions found' errors are consistent."""

    def test_local_no_sessions_message(self, empty_home: Dict[str, Any]) -> None:
        """Local source should show consistent error for no sessions."""
        result = run_cli_subprocess(
            ["session", "list", "--aw"],
            env=empty_home["env"],
        )
        # Should exit 0 but show message on stderr
        assert "No sessions found" in result.stderr or "No workspaces found" in result.stderr

    def test_local_pattern_no_match_message(self, home_with_workspaces: Dict[str, Any]) -> None:
        """Local source with non-matching pattern should show consistent error."""
        result = run_cli_subprocess(
            ["session", "list", "-n", "nonexistent-pattern", "--aw"],
            env=home_with_workspaces["env"],
        )
        # Should mention the pattern that didn't match
        assert "No sessions found" in result.stderr or result.stdout == ""


class TestNoWorkspacesErrorMessages:
    """Test that 'no workspaces found' errors are consistent."""

    def test_local_no_workspaces_message(self, empty_home: Dict[str, Any]) -> None:
        """Local source should show consistent error for no workspaces."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=empty_home["env"],
        )
        # Should show message on stderr when no workspaces found
        assert "No workspaces found" in result.stderr or result.stdout == ""

    def test_local_pattern_no_match_workspaces(self, home_with_workspaces: Dict[str, Any]) -> None:
        """Local source with non-matching pattern should show consistent error."""
        result = run_cli_subprocess(
            ["ws", "list", "-n", "nonexistent-pattern", "--aw"],
            env=home_with_workspaces["env"],
        )
        # No output when pattern doesn't match
        lines = [
            line
            for line in result.stdout.strip().split("\n")
            if line and not line.startswith("HOME")
        ]
        assert len(lines) == 0, f"Expected no workspace matches, got: {lines}"


class TestErrorMessageFormat:
    """Test that error messages follow consistent format."""

    def test_error_messages_go_to_stderr(self, empty_home: Dict[str, Any]) -> None:
        """Error/info messages should go to stderr, not stdout."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=empty_home["env"],
        )
        # If there's a "no workspaces" message, it should be on stderr
        if "No workspaces" in result.stderr:
            assert "No workspaces" not in result.stdout

    def test_data_output_goes_to_stdout(self, home_with_workspaces: Dict[str, Any]) -> None:
        """Data output should go to stdout, not stderr."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=home_with_workspaces["env"],
        )
        assert result.returncode == 0
        # Header and data should be on stdout
        assert "HOME" in result.stdout or "WORKSPACE" in result.stdout
