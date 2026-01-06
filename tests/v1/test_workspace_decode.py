"""Tests for workspace path encoding/decoding.

These tests verify that workspace directory names are correctly decoded
back to readable paths, especially for:
- Deep path hierarchies
- Folders with dashes in their names
- Paths that don't exist on the filesystem

The bug being tested: workspace names like `-home-alice-alice-projects-api`
were incorrectly decoding to `/home/alice/alice-projects-api` instead of
`/home/alice/alice/projects/api` when the target path didn't exist.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from tests.helpers.cli import run_cli_subprocess


def create_workspace_fixture(base_path: Path, workspace_path: str, num_sessions: int = 1) -> str:
    """Create a Claude workspace with sessions at the given path.

    Args:
        base_path: The temp directory acting as home
        workspace_path: The workspace path (e.g., "/home/user/projects/my-app")
        num_sessions: Number of sessions to create

    Returns:
        The encoded workspace directory name
    """
    # Encode the workspace path (replace / with -)
    encoded = workspace_path.replace("/", "-")
    if not encoded.startswith("-"):
        encoded = "-" + encoded

    # Create the Claude projects directory structure
    claude_dir = base_path / ".claude" / "projects" / encoded
    claude_dir.mkdir(parents=True, exist_ok=True)

    # Create minimal session files
    for i in range(num_sessions):
        session_file = claude_dir / f"session-{i:03d}.jsonl"
        session_data = [
            {
                "type": "user",
                "message": {"role": "user", "content": "test"},
                "timestamp": "2025-01-01T10:00:00Z",
                "sessionId": f"sess-{i}",
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
                "timestamp": "2025-01-01T10:00:01Z",
                "sessionId": f"sess-{i}",
            },
        ]
        with open(session_file, "w") as f:
            for entry in session_data:
                f.write(json.dumps(entry) + "\n")

    return encoded


@pytest.fixture
def decode_test_home(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create a test home with various workspace path patterns."""
    # Create the actual directory structure that should be resolved
    # This simulates a real filesystem where some paths exist

    # Simple path: /home/user/projects/simple
    (tmp_path / "home" / "user" / "projects" / "simple").mkdir(parents=True)

    # Path with dash in folder: /home/user/projects/my-app
    (tmp_path / "home" / "user" / "projects" / "my-app").mkdir(parents=True)

    # Deep path: /home/user/projects/org/repo/src
    (tmp_path / "home" / "user" / "projects" / "org" / "repo" / "src").mkdir(parents=True)

    # Deep hierarchy with repeated segment (the bug case)
    # e.g., /home/alice/alice/projects/api
    (tmp_path / "home" / "alice" / "alice" / "projects").mkdir(parents=True)
    (tmp_path / "home" / "alice" / "alice" / "projects" / "api").mkdir()
    (tmp_path / "home" / "alice" / "alice" / "projects" / "api" / "server").mkdir()
    (tmp_path / "home" / "alice" / "alice" / "projects" / "api" / "client").mkdir()
    (tmp_path / "home" / "alice" / "alice" / "projects" / "api" / "client" / "tests" / "e2e").mkdir(
        parents=True
    )

    # Create workspaces (Claude session directories)
    workspaces = {}

    # Simple workspace
    workspaces["simple"] = create_workspace_fixture(tmp_path, "/home/user/projects/simple")

    # Workspace with dash in name
    workspaces["my-app"] = create_workspace_fixture(tmp_path, "/home/user/projects/my-app")

    # Deep workspace
    workspaces["deep"] = create_workspace_fixture(tmp_path, "/home/user/projects/org/repo/src")

    # Deep hierarchy workspaces (the bug case)
    workspaces["api"] = create_workspace_fixture(tmp_path, "/home/alice/alice/projects/api")
    workspaces["api-server"] = create_workspace_fixture(
        tmp_path, "/home/alice/alice/projects/api/server"
    )
    workspaces["api-client-e2e"] = create_workspace_fixture(
        tmp_path, "/home/alice/alice/projects/api/client/tests/e2e"
    )

    # Non-existent path (directory doesn't exist but workspace does)
    workspaces["nonexistent"] = create_workspace_fixture(
        tmp_path, "/home/alice/alice/projects/notes-app"
    )

    # Environment for test isolation
    env = os.environ.copy()
    env["AGENT_HISTORY_HOME"] = str(tmp_path)
    env["HOME"] = str(tmp_path)

    yield {
        "path": tmp_path,
        "env": env,
        "workspaces": workspaces,
    }


class TestWorkspaceDecodeSimple:
    """Test simple workspace path decoding."""

    def test_simple_path_decodes_correctly(self, decode_test_home: Dict[str, Any]) -> None:
        """Simple path without dashes should decode correctly."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=decode_test_home["env"],
        )
        assert result.returncode == 0
        # Should contain /home/user/projects/simple
        assert "/home/user/projects/simple" in result.stdout

    def test_deep_path_decodes_correctly(self, decode_test_home: Dict[str, Any]) -> None:
        """Deep path hierarchy should decode correctly."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=decode_test_home["env"],
        )
        assert result.returncode == 0
        # Should contain /home/user/projects/org/repo/src
        assert "/home/user/projects/org/repo/src" in result.stdout


class TestWorkspaceDecodeWithDashes:
    """Test workspace decoding when folder names contain dashes."""

    def test_dash_in_folder_name_decodes_correctly(self, decode_test_home: Dict[str, Any]) -> None:
        """Folder with dash in name should decode correctly when path exists."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=decode_test_home["env"],
        )
        assert result.returncode == 0
        # Should contain /home/user/projects/my-app (with dash preserved)
        assert "/home/user/projects/my-app" in result.stdout
        # Should NOT have /home/user/projects/my/app (incorrectly split)
        assert "/home/user/projects/my/app" not in result.stdout


class TestWorkspaceDecodeDeepHierarchy:
    """Test the specific deep hierarchy pattern that was failing.

    Bug: -home-alice-alice-projects-api was decoding to
    /home/alice/alice-projects-api instead of /home/alice/alice/projects/api
    """

    def test_deep_hierarchy_decodes_correctly(self, decode_test_home: Dict[str, Any]) -> None:
        """Deep hierarchy workspace should decode to correct path."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=decode_test_home["env"],
        )
        assert result.returncode == 0

        # Should contain correct path
        assert "/home/alice/alice/projects/api" in result.stdout

        # Should NOT contain wrong path (the bug)
        assert "/home/alice/alice-projects-api" not in result.stdout

    def test_nested_path_decodes_correctly(self, decode_test_home: Dict[str, Any]) -> None:
        """Nested path in deep hierarchy should decode correctly."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=decode_test_home["env"],
        )
        assert result.returncode == 0

        # Should contain correct path
        assert "/home/alice/alice/projects/api/server" in result.stdout

        # Should NOT contain wrong path
        assert "/home/alice/alice-projects-api-server" not in result.stdout

    def test_deeply_nested_path_decodes_correctly(self, decode_test_home: Dict[str, Any]) -> None:
        """Deeply nested path should decode correctly."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=decode_test_home["env"],
        )
        assert result.returncode == 0

        # Should contain correct deep path
        assert "/home/alice/alice/projects/api/client/tests/e2e" in result.stdout


class TestWorkspaceDecodeNonExistent:
    """Test decoding when the target directory doesn't exist on filesystem.

    This is critical: even when a path doesn't exist, we should decode it
    correctly based on what DOES exist, not merge everything arbitrarily.
    """

    def test_nonexistent_leaf_still_decodes_parent_correctly(
        self, decode_test_home: Dict[str, Any]
    ) -> None:
        """When leaf doesn't exist, parent path should still decode correctly.

        /home/alice/alice/projects exists, but notes-app doesn't.
        Should decode to: /home/alice/alice/projects/notes-app
        NOT: /home/alice/alice-projects-notes-app
        """
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=decode_test_home["env"],
        )
        assert result.returncode == 0

        # The nonexistent workspace should still show correct parent structure
        # It might have [missing] marker, but path should be correct
        output = result.stdout

        # Should contain the correctly decoded path (possibly with [missing])
        assert (
            "/home/alice/alice/projects/notes-app" in output
            or "/home/alice/alice/projects/notes-app [missing]" in output
        )

        # Should NOT contain the buggy merged path
        assert "/home/alice/alice-projects-notes-app" not in output
