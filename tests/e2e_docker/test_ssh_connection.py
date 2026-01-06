"""SSH connection tests for agent-history remote functionality.

Tests basic SSH connectivity, authentication, and timeout handling.
"""

import pytest

from .conftest import run_cli, ssh_run


class TestSSHConnectivity:
    """Test SSH connectivity to remote nodes."""

    def test_ssh_to_alpha_alice(self, docker_env, ssh_to_alpha):
        """SSH to alice@node-alpha works."""
        result = ssh_to_alpha("alice", "whoami")
        assert result.returncode == 0, f"SSH failed: {result.stderr}"
        assert result.stdout.strip() == "alice"

    def test_ssh_to_alpha_bob(self, docker_env, ssh_to_alpha):
        """SSH to bob@node-alpha works."""
        result = ssh_to_alpha("bob", "whoami")
        assert result.returncode == 0, f"SSH failed: {result.stderr}"
        assert result.stdout.strip() == "bob"

    def test_ssh_to_beta_charlie(self, docker_env, ssh_to_beta):
        """SSH to charlie@node-beta works."""
        result = ssh_to_beta("charlie", "whoami")
        assert result.returncode == 0, f"SSH failed: {result.stderr}"
        assert result.stdout.strip() == "charlie"

    def test_ssh_to_beta_dave(self, docker_env, ssh_to_beta):
        """SSH to dave@node-beta works."""
        result = ssh_to_beta("dave", "whoami")
        assert result.returncode == 0, f"SSH failed: {result.stderr}"
        assert result.stdout.strip() == "dave"


class TestRemoteSessionData:
    """Test that remote nodes have expected session data."""

    def test_alice_has_claude_sessions(self, docker_env, ssh_to_alpha):
        """Alice's home has Claude session data."""
        result = ssh_to_alpha("alice", "ls ~/.claude/projects/")
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "-home-alice-myproject" in result.stdout

    def test_alice_has_codex_sessions(self, docker_env, ssh_to_alpha):
        """Alice's home has Codex session data."""
        result = ssh_to_alpha("alice", "ls ~/.codex/sessions/2025/01/15/")
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "session-codex-001.jsonl" in result.stdout

    def test_alice_has_gemini_sessions(self, docker_env, ssh_to_alpha):
        """Alice's home has Gemini session data."""
        result = ssh_to_alpha("alice", "find ~/.gemini -name '*.json' | head -1")
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert ".json" in result.stdout

    def test_charlie_has_claude_sessions(self, docker_env, ssh_to_beta):
        """Charlie's home has Claude session data."""
        result = ssh_to_beta("charlie", "ls ~/.claude/projects/")
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "-home-charlie-myproject" in result.stdout


class TestSSHErrors:
    """Test SSH error handling."""

    def test_invalid_host_fails(self, docker_env, cli_path):
        """CLI gracefully handles invalid SSH host."""
        result = run_cli(
            ["ws", "-r", "alice@nonexistent-host"],
            cli_path,
            timeout=15,  # Short timeout for expected failure
        )
        # Should fail but not crash
        assert result.returncode != 0
        # Should have error message about connection
        assert "error" in result.stderr.lower() or "could not" in result.stderr.lower()

    def test_invalid_user_fails(self, docker_env, cli_path):
        """CLI gracefully handles invalid SSH user."""
        node = docker_env["node_alpha"]
        result = run_cli(
            ["ws", "-r", f"nonexistent@{node}"],
            cli_path,
            timeout=15,
        )
        # Should fail
        assert result.returncode != 0


class TestRemoteFlag:
    """Test -r/--remote flag parsing."""

    def test_remote_flag_short(self, docker_env, cli_path):
        """CLI accepts -r flag."""
        node = docker_env["node_alpha"]
        result = run_cli(["ws", "-r", f"alice@{node}"], cli_path)
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_remote_flag_long(self, docker_env, cli_path):
        """CLI accepts --remote flag."""
        node = docker_env["node_alpha"]
        result = run_cli(["ws", "--remote", f"alice@{node}"], cli_path)
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_multiple_remotes(self, docker_env, cli_path):
        """CLI accepts multiple -r flags."""
        alpha = docker_env["node_alpha"]
        beta = docker_env["node_beta"]
        result = run_cli(
            ["ws", "-r", f"alice@{alpha}", "-r", f"charlie@{beta}"],
            cli_path,
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"
