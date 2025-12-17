"""E2E tests for stats synchronization from remote nodes.

Tests the stats --sync command with real SSH connections.
"""

import pytest

from .helpers import run_cli

pytestmark = pytest.mark.e2e_docker


class TestStatsSyncRemote:
    """Test syncing statistics from remote nodes."""

    def test_stats_sync_from_remote(self, charlie, verify_ssh_connectivity):
        """stats --sync -r syncs data from remote node."""
        result = run_cli(["stats", "--sync", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should show sync progress or completion

    def test_stats_after_sync(self, charlie, isolated_home, verify_ssh_connectivity):
        """stats shows data after syncing from remote."""
        # First sync
        sync_result = run_cli(["stats", "--sync", "-r", charlie], env=isolated_home["env"])
        assert sync_result.returncode == 0, f"sync stderr: {sync_result.stderr}"

        # Then view stats
        stats_result = run_cli(["stats"], env=isolated_home["env"])
        assert stats_result.returncode == 0, f"stats stderr: {stats_result.stderr}"

    def test_stats_sync_with_agent_filter(self, charlie, verify_ssh_connectivity):
        """stats --sync with agent filter syncs only that agent's data."""
        result = run_cli(["stats", "--sync", "--agent", "claude", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"


class TestStatsDisplayRemote:
    """Test stats display options with remote data."""

    def test_stats_tools_remote(self, charlie, isolated_home, verify_ssh_connectivity):
        """stats --tools shows tool usage from remote."""
        # Sync first
        run_cli(["stats", "--sync", "-r", charlie], env=isolated_home["env"])

        # Then view tool stats
        result = run_cli(["stats", "--tools"], env=isolated_home["env"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_stats_models_remote(self, charlie, isolated_home, verify_ssh_connectivity):
        """stats --models shows model usage from remote."""
        # Sync first
        run_cli(["stats", "--sync", "-r", charlie], env=isolated_home["env"])

        # Then view model stats
        result = run_cli(["stats", "--models"], env=isolated_home["env"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_stats_by_workspace_remote(self, charlie, isolated_home, verify_ssh_connectivity):
        """stats --by-workspace shows per-workspace stats from remote."""
        # Sync first
        run_cli(["stats", "--sync", "-r", charlie], env=isolated_home["env"])

        # Then view workspace stats
        result = run_cli(["stats", "--by-workspace"], env=isolated_home["env"])
        assert result.returncode == 0, f"stderr: {result.stderr}"


class TestStatsSyncMultipleRemotes:
    """Test syncing from multiple remote nodes."""

    def test_sync_from_both_nodes(self, alice, charlie, isolated_home, verify_ssh_connectivity):
        """Can sync stats from multiple remote nodes."""
        # Sync from alice
        alice_result = run_cli(["stats", "--sync", "-r", alice], env=isolated_home["env"])
        assert alice_result.returncode == 0, f"alice stderr: {alice_result.stderr}"

        # Sync from charlie
        charlie_result = run_cli(["stats", "--sync", "-r", charlie], env=isolated_home["env"])
        assert charlie_result.returncode == 0, f"charlie stderr: {charlie_result.stderr}"

        # View combined stats
        stats_result = run_cli(["stats"], env=isolated_home["env"])
        assert stats_result.returncode == 0, f"stats stderr: {stats_result.stderr}"
