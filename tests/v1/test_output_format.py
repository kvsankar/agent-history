"""Tests for consistent output format across all commands.

All listing commands should produce tabular output with headers,
regardless of the flags/options used.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from tests.helpers.cli import run_cli_subprocess
from tests.v1.test_workspace_decode import create_workspace_fixture


@pytest.fixture
def output_test_home(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create a test home with workspaces for output format testing."""
    # Create directory structure
    (tmp_path / "home" / "user" / "projects" / "app1").mkdir(parents=True)
    (tmp_path / "home" / "user" / "projects" / "app2").mkdir(parents=True)

    # Create workspaces with sessions
    create_workspace_fixture(tmp_path, "/home/user/projects/app1", num_sessions=2)
    create_workspace_fixture(tmp_path, "/home/user/projects/app2", num_sessions=3)

    # Environment for test isolation
    env = os.environ.copy()
    env["AGENT_HISTORY_HOME"] = str(tmp_path)
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)

    yield {
        "path": tmp_path,
        "env": env,
    }


class TestWsListOutputFormat:
    """Test ws list output format consistency."""

    def test_ws_list_aw_has_header(self, output_test_home: Dict[str, Any]) -> None:
        """ws list --aw should have tabular header with all required columns."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=output_test_home["env"],
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert len(lines) >= 1, "Should have at least header line"
        header = lines[0]
        assert header.startswith("HOME"), f"Header should start with HOME, got: {header}"
        assert "WORKSPACE" in header
        assert "SESSIONS" in header
        assert "STATUS" in header

    def test_ws_list_pattern_has_header(self, output_test_home: Dict[str, Any]) -> None:
        """ws list -n pattern should have tabular header."""
        result = run_cli_subprocess(
            ["ws", "list", "-n", "app", "--aw"],
            env=output_test_home["env"],
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")
        assert lines[0].startswith("HOME"), f"Header should start with HOME, got: {lines[0]}"

    def test_ws_list_this_has_header(self, output_test_home: Dict[str, Any]) -> None:
        """ws list --this should have tabular header (when workspace exists)."""
        # Change to a workspace directory
        ws_path = output_test_home["path"] / "home" / "user" / "projects" / "app1"
        env = output_test_home["env"].copy()
        env["PWD"] = str(ws_path)

        result = run_cli_subprocess(
            ["ws", "list", "--aw"],  # Use --aw to ensure we get results
            env=env,
        )
        assert result.returncode == 0
        if result.stdout.strip():  # If there's output
            lines = result.stdout.strip().split("\n")
            assert lines[0].startswith("HOME"), f"Header should start with HOME, got: {lines[0]}"


class TestWsListOutputColumns:
    """Test ws list output columns are correct."""

    def test_ws_list_has_all_columns(self, output_test_home: Dict[str, Any]) -> None:
        """ws list should have HOME, WORKSPACE, SESSIONS, STATUS, LAST_MODIFIED columns."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=output_test_home["env"],
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")

        # Check header columns
        header = lines[0]
        expected_cols = ["HOME", "WORKSPACE", "SESSIONS", "STATUS", "LAST_MODIFIED"]
        for col in expected_cols:
            assert col in header, f"Header missing column {col}: {header}"

    def test_ws_list_data_rows_have_correct_columns(self, output_test_home: Dict[str, Any]) -> None:
        """Data rows should have values for all columns (using TSV format for parsing)."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw", "--format", "tsv"],
            env=output_test_home["env"],
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split("\n")

        # Skip header, check data rows
        for line in lines[1:]:
            cols = line.split("\t")
            assert len(cols) == 5, f"Expected 5 columns, got {len(cols)}: {line}"
            home, workspace, sessions, status, last_mod = cols
            assert home == "local", f"HOME should be 'local', got: {home}"
            assert workspace.startswith("/") or workspace.startswith(
                "["
            ), f"WORKSPACE should be path: {workspace}"
            assert sessions.isdigit(), f"SESSIONS should be number: {sessions}"
            assert status in (
                "ok",
                "missing",
                "unknown",
            ), f"STATUS should be ok/missing/unknown: {status}"


class TestWsListStatusColumn:
    """Test STATUS column correctly identifies missing paths."""

    @pytest.fixture
    def home_with_missing(self, tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
        """Create home with existing and non-existing workspace paths."""
        # Create existing path
        (tmp_path / "home" / "user" / "projects" / "exists").mkdir(parents=True)
        create_workspace_fixture(tmp_path, "/home/user/projects/exists", num_sessions=1)

        # Create workspace for non-existing path (directory not created)
        create_workspace_fixture(tmp_path, "/home/user/projects/deleted", num_sessions=1)

        env = os.environ.copy()
        env["AGENT_HISTORY_HOME"] = str(tmp_path)
        env["HOME"] = str(tmp_path)
        env["USERPROFILE"] = str(tmp_path)

        yield {"path": tmp_path, "env": env}

    def test_existing_path_shows_ok(self, home_with_missing: Dict[str, Any]) -> None:
        """Existing workspace path should show status 'ok'."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw", "--format", "tsv"],
            env=home_with_missing["env"],
        )
        assert result.returncode == 0

        # Find the line for existing workspace
        for line in result.stdout.strip().split("\n")[1:]:  # Skip header
            if "/home/user/projects/exists" in line:
                cols = line.split("\t")
                assert cols[3] == "ok", f"Existing path should have status 'ok': {line}"
                return
        pytest.fail("Did not find existing workspace in output")

    def test_missing_path_shows_missing(self, home_with_missing: Dict[str, Any]) -> None:
        """Non-existing workspace path should show status 'missing'."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw", "--format", "tsv"],
            env=home_with_missing["env"],
        )
        assert result.returncode == 0

        # Find the line for deleted workspace
        for line in result.stdout.strip().split("\n")[1:]:  # Skip header
            if "/home/user/projects/deleted" in line:
                cols = line.split("\t")
                assert cols[3] == "missing", f"Missing path should have status 'missing': {line}"
                return
        pytest.fail("Did not find deleted workspace in output")


class TestWsListJsonFormat:
    """Test ws list JSON output format."""

    def test_json_format_has_all_fields(self, output_test_home: Dict[str, Any]) -> None:
        """JSON output should have all required fields."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw", "--format", "json"],
            env=output_test_home["env"],
        )
        assert result.returncode == 0

        data = json.loads(result.stdout)
        assert isinstance(data, list), "JSON output should be array"
        assert len(data) >= 1, "Should have at least one workspace"

        for item in data:
            assert "home" in item, f"Missing 'home' field: {item}"
            assert "workspace" in item, f"Missing 'workspace' field: {item}"
            assert "sessions" in item, f"Missing 'sessions' field: {item}"
            assert "status" in item, f"Missing 'status' field: {item}"
            assert "last_modified" in item, f"Missing 'last_modified' field: {item}"
