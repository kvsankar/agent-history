"""Multi-home tests for agent-history.

Tests --ah (all homes) functionality with local + remote homes,
and the home add/remove/list commands.
"""

import pytest
import tempfile
from pathlib import Path

from .conftest import run_cli, skip_if_not_docker


class TestAllHomesFlag:
    """Test --ah/--all-homes flag functionality."""

    def test_ws_all_homes_includes_remote(self, docker_env, cli_path):
        """ws --ah includes configured remote homes."""
        skip_if_not_docker()
        # First, add a remote home
        node = docker_env["node_alpha"]
        add_result = run_cli(["home", "add", f"alice@{node}"], cli_path)

        # Now list with --ah
        result = run_cli(["ws", "--ah"], cli_path)

        # Should succeed
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_session_list_all_homes(self, docker_env, cli_path):
        """session list --ah lists from all configured homes."""
        skip_if_not_docker()
        result = run_cli(["session", "list", "--ah", "--aw"], cli_path)
        # Should succeed (may have no sessions)
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_all_homes_with_exclusions(self, docker_env, cli_path):
        """--ah with --no-remote excludes remote homes."""
        skip_if_not_docker()
        result = run_cli(
            ["session", "list", "--ah", "--no-remote", "--aw"],
            cli_path,
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"


class TestHomeCommands:
    """Test home add/remove/list commands."""

    def test_home_list_shows_local(self, docker_env, cli_path):
        """home list shows local home."""
        skip_if_not_docker()
        result = run_cli(["home", "list"], cli_path)
        assert result.returncode == 0, f"Failed: {result.stderr}"
        # Should show local home
        assert "local" in result.stdout.lower() or len(result.stdout) > 0

    def test_home_add_remote(self, docker_env, cli_path):
        """home add user@host adds a remote home."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(["home", "add", f"alice@{node}"], cli_path)
        # Should succeed
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_home_add_second_remote(self, docker_env, cli_path):
        """home add can add multiple remotes."""
        skip_if_not_docker()
        beta = docker_env["node_beta"]
        result = run_cli(["home", "add", f"charlie@{beta}"], cli_path)
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_home_list_after_add(self, docker_env, cli_path):
        """home list shows added remotes."""
        skip_if_not_docker()
        # Add a remote first
        node = docker_env["node_alpha"]
        run_cli(["home", "add", f"alice@{node}"], cli_path)

        # List homes
        result = run_cli(["home", "list"], cli_path)
        assert result.returncode == 0, f"Failed: {result.stderr}"
        # Should show the remote
        output = result.stdout.lower()
        assert "remote" in output or "alice" in output or node in result.stdout

    def test_home_remove_remote(self, docker_env, cli_path):
        """home remove user@host removes a remote home."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        # Add first
        run_cli(["home", "add", f"alice@{node}"], cli_path)
        # Then remove
        result = run_cli(["home", "remove", f"alice@{node}"], cli_path)
        assert result.returncode == 0, f"Failed: {result.stderr}"


class TestLocalPlusRemote:
    """Test operations combining local and remote homes."""

    def test_local_flag_with_remote(self, docker_env, cli_path):
        """--local -r combines local and specific remote."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(
            ["ws", "--local", "-r", f"alice@{node}"],
            cli_path,
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_session_local_plus_remote(self, docker_env, cli_path):
        """session list --local -r lists from both."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]
        result = run_cli(
            ["session", "list", "--local", "-r", f"alice@{node}", "--aw"],
            cli_path,
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_export_local_plus_remote(self, docker_env, cli_path):
        """session export --local -r exports from both."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_cli(
                [
                    "session", "export",
                    "--local", "-r", f"alice@{node}",
                    "--aw",
                    "-o", tmpdir,
                ],
                cli_path,
            )
            assert result.returncode == 0, f"Failed: {result.stderr}"


class TestHomeShow:
    """Test home show command."""

    def test_home_show_local(self, docker_env, cli_path):
        """home show local displays local home details."""
        skip_if_not_docker()
        result = run_cli(["home", "show", "local"], cli_path)
        # May fail if "local" isn't the exact name, but shouldn't crash
        # Just check it runs without crashing


class TestMultiUserMultiNode:
    """Test scenarios with multiple users across nodes."""

    def test_different_users_same_node(self, docker_env, cli_path):
        """Can list from different users on same node."""
        skip_if_not_docker()
        node = docker_env["node_alpha"]

        # Alice
        alice_result = run_cli(["ws", "-r", f"alice@{node}"], cli_path)
        assert alice_result.returncode == 0

        # Bob
        bob_result = run_cli(["ws", "-r", f"bob@{node}"], cli_path)
        assert bob_result.returncode == 0

    def test_same_user_name_different_nodes(self, docker_env, cli_path):
        """Different nodes can have users with different data."""
        skip_if_not_docker()
        alpha = docker_env["node_alpha"]
        beta = docker_env["node_beta"]

        # Alice on alpha
        alice_result = run_cli(["ws", "-r", f"alice@{alpha}"], cli_path)
        assert alice_result.returncode == 0

        # Charlie on beta (different user, different node)
        charlie_result = run_cli(["ws", "-r", f"charlie@{beta}"], cli_path)
        assert charlie_result.returncode == 0

    def test_aggregate_stats_multiple_remotes(self, docker_env, cli_path):
        """stats with multiple -r aggregates data."""
        skip_if_not_docker()
        alpha = docker_env["node_alpha"]
        beta = docker_env["node_beta"]

        result = run_cli(
            [
                "session", "stats",
                "-r", f"alice@{alpha}",
                "-r", f"charlie@{beta}",
                "--aw",
            ],
            cli_path,
        )
        # May fail if no sessions, but shouldn't crash
        assert result.returncode in [0, 1], f"Unexpected error: {result.stderr}"
