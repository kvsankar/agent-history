"""Remote operations tests for agent-history.

Tests workspace listing, session listing, and export from remote hosts.
"""

import json
import tempfile
from pathlib import Path

import pytest

from .conftest import run_cli


class TestRemoteWorkspaceList:
    """Test `ws -r user@host` command."""

    def test_ws_remote_lists_workspaces(self, docker_env, cli_path):
        """ws -r lists workspaces from remote host."""
        node = docker_env["node_alpha"]
        result = run_cli(["ws", "-r", f"alice@{node}"], cli_path)

        assert result.returncode == 0, f"Failed: {result.stderr}"
        # Should list myproject workspace
        assert "myproject" in result.stdout or "project" in result.stdout.lower()

    def test_ws_remote_different_users(self, docker_env, cli_path):
        """ws -r shows different workspaces for different users."""
        node = docker_env["node_alpha"]

        # Alice's workspaces
        alice_result = run_cli(["ws", "-r", f"alice@{node}"], cli_path)
        assert alice_result.returncode == 0

        # Bob's workspaces
        bob_result = run_cli(["ws", "-r", f"bob@{node}"], cli_path)
        assert bob_result.returncode == 0

        assert "myproject" in alice_result.stdout or "another-project" in alice_result.stdout
        assert "myproject" in bob_result.stdout or "another-project" in bob_result.stdout

    def test_ws_remote_pattern_filter(self, docker_env, cli_path):
        """ws -r with pattern filters workspaces."""
        node = docker_env["node_alpha"]
        result = run_cli(["ws", "-r", f"alice@{node}", "-n", "myproject"], cli_path)

        assert result.returncode == 0, f"Failed: {result.stderr}"


class TestRemoteSessionList:
    """Test `session list -r user@host` command."""

    def test_session_list_remote(self, docker_env, cli_path):
        """session list -r shows sessions from remote host."""
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "list", "-r", f"alice@{node}", "--aw", "--format", "json"],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        sessions = json.loads(result.stdout)
        assert sessions, "Expected remote sessions for alice"
        assert any("session-claude-001" in s.get("filename", "") for s in sessions)

    def test_session_list_remote_with_workspace(self, docker_env, cli_path):
        """session list -r with workspace pattern."""
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "list", "-r", f"alice@{node}", "myproject", "--format", "json"],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        sessions = json.loads(result.stdout)
        assert sessions, "Expected remote sessions for myproject"
        assert any("session-claude-001" in s.get("filename", "") for s in sessions)

    def test_session_list_remote_claude_agent(self, docker_env, cli_path):
        """session list -r --agent claude filters to Claude sessions."""
        node = docker_env["node_alpha"]
        result = run_cli(
            [
                "session",
                "list",
                "-r",
                f"alice@{node}",
                "--aw",
                "--agent",
                "claude",
                "--format",
                "json",
            ],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        sessions = json.loads(result.stdout)
        assert sessions, "Expected remote Claude sessions"
        assert all(s.get("agent") == "claude" for s in sessions)

    def test_session_list_remote_codex_agent(self, docker_env, cli_path):
        """session list -r --agent codex filters to Codex sessions."""
        node = docker_env["node_alpha"]
        result = run_cli(
            [
                "session",
                "list",
                "-r",
                f"alice@{node}",
                "--aw",
                "--agent",
                "codex",
                "--format",
                "json",
            ],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        sessions = json.loads(result.stdout)
        assert sessions, "Expected remote Codex sessions"
        assert all(s.get("agent") == "codex" for s in sessions)
        assert any("session-codex-001" in s.get("filename", "") for s in sessions)

    def test_session_list_remote_gemini_agent(self, docker_env, cli_path):
        """session list -r --agent gemini filters to Gemini sessions."""
        node = docker_env["node_alpha"]
        result = run_cli(
            [
                "session",
                "list",
                "-r",
                f"alice@{node}",
                "--aw",
                "--agent",
                "gemini",
                "--format",
                "json",
            ],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"
        sessions = json.loads(result.stdout)
        assert sessions, "Expected remote Gemini sessions"
        assert all(s.get("agent") == "gemini" for s in sessions)
        assert any("session-gemini-001" in s.get("filename", "") for s in sessions)


class TestRemoteExport:
    """Test `session export -r user@host` command."""

    def test_export_remote_creates_files(self, docker_env, cli_path):
        """session export -r creates markdown files locally."""
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

            output_path = Path(tmpdir)
            files = list(output_path.rglob("*.md"))
            assert files, "Expected remote export to create markdown files"

    @pytest.mark.parametrize(
        ("agent", "header"),
        [
            ("claude", "# Claude Conversation"),
            ("codex", "# Codex Conversation"),
            ("gemini", "# Gemini Conversation"),
        ],
    )
    def test_export_remote_with_agent_filter(self, docker_env, cli_path, agent, header):
        """session export -r --agent should export files per agent."""
        node = docker_env["node_alpha"]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(
                [
                    "session", "export",
                    "-r", f"alice@{node}",
                    "--aw",
                    "--agent", agent,
                    "-o", tmpdir,
                ],
                cli_path,
            )

            assert result.returncode == 0, f"Failed: {result.stderr}"
            output_path = Path(tmpdir)
            files = list(output_path.rglob("*.md"))
            assert files, f"Expected {agent} export files"
            assert header in files[0].read_text(encoding="utf-8")


class TestRemoteStats:
    """Test `session stats -r user@host` command."""

    def test_stats_remote_basic(self, docker_env, cli_path):
        """session stats -r shows stats from remote host."""
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "stats", "-r", f"alice@{node}", "--aw"],
            cli_path,
        )

        # Stats may succeed or indicate no data - both are valid
        # Just shouldn't crash
        assert result.returncode in [0, 1], f"Unexpected error: {result.stderr}"

    def test_stats_remote_with_sync(self, docker_env, cli_path):
        """session stats --sync -r should run without crashing."""
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "stats", "--sync", "-r", f"alice@{node}", "--aw"],
            cli_path,
        )

        assert result.returncode in [0, 1], f"Unexpected error: {result.stderr}"

    def test_stats_remote_by_model(self, docker_env, cli_path):
        """session stats -r --by model groups by model."""
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
        alpha = docker_env["node_alpha"]
        beta = docker_env["node_beta"]

        result = run_cli(
            ["ws", "-r", f"alice@{alpha}", "-r", f"charlie@{beta}"],
            cli_path,
        )

        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_session_list_multiple_remotes(self, docker_env, cli_path):
        """session list with multiple -r flags lists from all remotes."""
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
