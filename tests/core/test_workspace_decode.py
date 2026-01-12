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
    env["USERPROFILE"] = str(tmp_path)

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
        # Use TSV format to get full, non-truncated paths
        result = run_cli_subprocess(
            ["ws", "list", "--aw", "--format", "tsv"],
            env=decode_test_home["env"],
        )
        assert result.returncode == 0

        # Should contain correct path
        assert "/home/alice/alice/projects/api/server" in result.stdout

        # Should NOT contain wrong path
        assert "/home/alice/alice-projects-api-server" not in result.stdout

    def test_deeply_nested_path_decodes_correctly(self, decode_test_home: Dict[str, Any]) -> None:
        """Deeply nested path should decode correctly."""
        # Use TSV format to get full, non-truncated paths
        result = run_cli_subprocess(
            ["ws", "list", "--aw", "--format", "tsv"],
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


class TestHierarchicalWorkspaces:
    """Test that parent and child workspaces are listed separately.

    Workspaces at different levels of a directory hierarchy must be
    treated as separate workspaces. Users can combine them into projects
    if they want unified access.
    """

    @pytest.fixture
    def hierarchical_home(self, tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
        """Create a test home with hierarchical workspaces (parent + children)."""
        # Create directory structure for a monorepo-style project
        monorepo = tmp_path / "home" / "user" / "projects" / "monorepo"
        monorepo.mkdir(parents=True)
        (monorepo / "packages" / "api").mkdir(parents=True)
        (monorepo / "packages" / "web").mkdir(parents=True)
        (monorepo / "packages" / "shared").mkdir(parents=True)

        # Create workspaces at different levels
        # Parent: /home/user/projects/monorepo
        create_workspace_fixture(tmp_path, "/home/user/projects/monorepo", num_sessions=2)

        # Children: /home/user/projects/monorepo/packages/*
        create_workspace_fixture(
            tmp_path, "/home/user/projects/monorepo/packages/api", num_sessions=3
        )
        create_workspace_fixture(
            tmp_path, "/home/user/projects/monorepo/packages/web", num_sessions=1
        )
        create_workspace_fixture(
            tmp_path, "/home/user/projects/monorepo/packages/shared", num_sessions=2
        )

        # Environment for test isolation
        env = os.environ.copy()
        env["AGENT_HISTORY_HOME"] = str(tmp_path)
        env["HOME"] = str(tmp_path)
        env["USERPROFILE"] = str(tmp_path)

        yield {
            "path": tmp_path,
            "env": env,
        }

    def test_parent_and_children_listed_separately(self, hierarchical_home: Dict[str, Any]) -> None:
        """Parent workspace and child workspaces should all appear in listing."""
        # Use TSV format to get full, non-truncated paths
        result = run_cli_subprocess(
            ["ws", "list", "--aw", "--format", "tsv"],
            env=hierarchical_home["env"],
        )
        assert result.returncode == 0
        output = result.stdout

        # All four workspaces should be listed separately
        assert "/home/user/projects/monorepo\t" in output  # Parent with tab after (TSV)
        assert "/home/user/projects/monorepo/packages/api" in output
        assert "/home/user/projects/monorepo/packages/web" in output
        assert "/home/user/projects/monorepo/packages/shared" in output

    def test_hierarchical_workspace_count(self, hierarchical_home: Dict[str, Any]) -> None:
        """Should have exactly 4 workspaces (1 parent + 3 children)."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=hierarchical_home["env"],
        )
        assert result.returncode == 0

        # Count non-empty lines (excluding header)
        lines = [line for line in result.stdout.strip().split("\n") if line]
        # First line is header, rest are workspaces
        assert lines[0].startswith("HOME"), "First line should be header"
        workspaces = lines[1:]  # Skip header
        assert len(workspaces) == 4, f"Expected 4 workspaces, got {len(workspaces)}: {workspaces}"

    def test_parent_not_merged_with_children(self, hierarchical_home: Dict[str, Any]) -> None:
        """Parent workspace sessions should not include child workspace sessions."""
        # Verify via ws list that workspaces are separate
        ws_result = run_cli_subprocess(
            ["ws", "list", "-n", "monorepo", "--aw"],
            env=hierarchical_home["env"],
        )
        assert ws_result.returncode == 0

        # Pattern "monorepo" should match all 4 workspaces (header + 4 data lines)
        lines = [line for line in ws_result.stdout.strip().split("\n") if line]
        workspaces = lines[1:]  # Skip header
        assert (
            len(workspaces) == 4
        ), f"Pattern 'monorepo' should match all 4 workspaces, got: {workspaces}"

    def test_child_workspace_pattern_excludes_parent(
        self, hierarchical_home: Dict[str, Any]
    ) -> None:
        """Pattern matching on child path should not include parent."""
        # Use TSV format to get full, non-truncated paths
        result = run_cli_subprocess(
            ["ws", "list", "-n", "packages/api", "--aw", "--format", "tsv"],
            env=hierarchical_home["env"],
        )
        assert result.returncode == 0
        output = result.stdout

        # Should find only the api workspace
        assert "/home/user/projects/monorepo/packages/api" in output

        # Should NOT include parent or siblings (header + 1 data line)
        lines = [line for line in output.strip().split("\n") if line]
        workspaces = lines[1:]  # Skip header
        assert len(workspaces) == 1, f"Expected 1 workspace, got: {workspaces}"
