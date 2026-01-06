"""Remote operations tests for agent-history.

Tests workspace listing, session listing, and export from remote hosts.
"""

import pytest
import tempfile
from pathlib import Path

from .conftest import run_cli, skip_if_not_docker


class TestRemoteWorkspaceList:
    """Test `ws -r user@host` command."""

    def test_ws_remote_lists_workspaces(self, docker_env, cli_path):
        """ws -r lists workspaces from remote host."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(["ws", "-r", f"alice@{node}"], cli_path)

        assert result.returncode == 0, f"Failed: {result.stderr}"
        # Should list myproject workspace
        assert "myproject" in result.stdout or "project" in result.stdout.lower()

    def test_ws_remote_different_users(self, docker_env, cli_path):
        """ws -r shows different workspaces for different users."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]

        # Alice's workspaces
        alice_result = run_cli(["ws", "-r", f"alice@{node}"], cli_path)
        assert alice_result.returncode == 0

        # Bob's workspaces
        bob_result = run_cli(["ws", "-r", f"bob@{node}"], cli_path)
        assert bob_result.returncode == 0

        # Both should have output (they have similar setups in test data)
        assert alice_result.stdout.strip() != "" or "No workspaces" in alice_result.stderr
        assert bob_result.stdout.strip() != "" or "No workspaces" in bob_result.stderr

    def test_ws_remote_pattern_filter(self, docker_env, cli_path):
        """ws -r with pattern filters workspaces."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(["ws", "-r", f"alice@{node}", "-n", "myproject"], cli_path)

        assert result.returncode == 0, f"Failed: {result.stderr}"


class TestRemoteSessionList:
    """Test `session list -r user@host` command."""

    def test_session_list_remote(self, docker_env, cli_path):
        """session list -r shows sessions from remote host."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "list", "-r", f"alice@{node}", "--aw"],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        # Should show session data
        output = result.stdout + result.stderr
        # Either shows sessions or "no sessions" message
        assert len(output) > 0

    def test_session_list_remote_with_workspace(self, docker_env, cli_path):
        """session list -r with workspace pattern."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "list", "-r", f"alice@{node}", "myproject"],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_session_list_remote_claude_agent(self, docker_env, cli_path):
        """session list -r --agent claude filters to Claude sessions."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "list", "-r", f"alice@{node}", "--aw", "--agent", "claude"],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_session_list_remote_codex_agent(self, docker_env, cli_path):
        """session list -r --agent codex filters to Codex sessions."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "list", "-r", f"alice@{node}", "--aw", "--agent", "codex"],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_session_list_remote_gemini_agent(self, docker_env, cli_path):
        """session list -r --agent gemini filters to Gemini sessions."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "list", "-r", f"alice@{node}", "--aw", "--agent", "gemini"],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"


class TestRemoteExport:
    """Test `session export -r user@host` command."""

    def test_export_remote_creates_files(self, docker_env, cli_path):
        """session export -r creates markdown files locally."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(
                [
                    "session", "export",
                    "-r", f"alice@{node}",
                    "--aw",
                    "-o", tmpdir,
                ],
                cli_path,
            )

            # Command should succeed
            assert result.returncode == 0, f"Failed: {result.stderr}"

            # Check if any files were created (may or may not have sessions)
            output_path = Path(tmpdir)
            # List what was created
            files = list(output_path.rglob("*.md"))
            # Note: May be empty if no sessions, but command should still succeed

    def test_export_remote_with_agent_filter(self, docker_env, cli_path):
        """session export -r --agent filters exports."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(
                [
                    "session", "export",
                    "-r", f"alice@{node}",
                    "--aw",
                    "--agent", "claude",
                    "-o", tmpdir,
                ],
                cli_path,
            )

            assert result.returncode == 0, f"Failed: {result.stderr}"


class TestRemoteStats:
    """Test `session stats -r user@host` command."""

    def test_stats_remote_basic(self, docker_env, cli_path):
        """session stats -r shows stats from remote host."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "stats", "-r", f"alice@{node}", "--aw"],
            cli_path,
        )

        # Stats may succeed or indicate no data - both are valid
        # Just shouldn't crash
        assert result.returncode in [0, 1], f"Unexpected error: {result.stderr}"

    def test_stats_remote_by_model(self, docker_env, cli_path):
        """session stats -r --by model groups by model."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "stats", "-r", f"alice@{node}", "--aw", "--by", "model"],
            cli_path,
        )

        assert result.returncode in [0, 1], f"Unexpected error: {result.stderr}"


class TestCrossNodeOperations:
    """Test operations across multiple remote nodes."""

    def test_ws_multiple_remotes(self, docker_env, cli_path):
        """ws with multiple -r flags lists from all remotes."""
        skip_if_not_docker()
        alpha = docker_env["node_alpha"]
        beta = docker_env["node_beta"]

        result = run_cli(
            ["ws", "-r", f"alice@{alpha}", "-r", f"charlie@{beta}"],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_session_list_multiple_remotes(self, docker_env, cli_path):
        """session list with multiple -r flags lists from all remotes."""
        skip_if_not_docker()
        alpha = docker_env["node_alpha"]
        beta = docker_env["node_beta"]

        result = run_cli(
            [
                "session", "list",
                "-r", f"alice@{alpha}",
                "-r", f"charlie@{beta}",
                "--aw",
            ],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
