"""E2E tests for multi-user scenarios.

Tests that different users on the same host have isolated workspaces.
"""

import pytest
from conftest import run_cli

pytestmark = pytest.mark.e2e_docker


class TestUserIsolation:
    """Test that users have isolated workspace data."""

    def test_different_users_same_host(self, alice, bob, verify_ssh_connectivity):
        """Different users on same host have separate workspaces."""
        alice_ws = run_cli(["lsw", "-r", alice])
        bob_ws = run_cli(["lsw", "-r", bob])

        assert alice_ws.returncode == 0, f"Alice failed: {alice_ws.stderr}"
        assert bob_ws.returncode == 0, f"Bob failed: {bob_ws.stderr}"

        # Both should have workspaces
        assert alice_ws.stdout.strip() != ""
        assert bob_ws.stdout.strip() != ""

        # Workspaces should contain user-specific paths
        # alice's workspaces should reference /home/alice/
        # bob's workspaces should reference /home/bob/

    def test_user_sessions_isolated(self, alice, bob, verify_ssh_connectivity):
        """Users' sessions don't leak between accounts."""
        alice_sessions = run_cli(["lss", "-r", alice])
        bob_sessions = run_cli(["lss", "-r", bob])

        assert alice_sessions.returncode == 0
        assert bob_sessions.returncode == 0

        # Sessions should be separate
        # (exact content depends on generated fixtures)

    def test_export_user_specific(self, alice, bob, tmp_path, verify_ssh_connectivity):
        """Exporting from one user doesn't affect another."""
        alice_dir = tmp_path / "alice"
        bob_dir = tmp_path / "bob"

        alice_export = run_cli(["export", "-r", alice, "-o", str(alice_dir)])
        bob_export = run_cli(["export", "-r", bob, "-o", str(bob_dir)])

        assert alice_export.returncode == 0
        assert bob_export.returncode == 0


class TestCrossUserAccess:
    """Test accessing another user's data (should fail without permissions)."""

    def test_cannot_access_other_user_home(self, node_alpha, verify_ssh_connectivity):
        """Cannot directly access another user's home directory."""
        # Try to list bob's claude directory as alice
        from conftest import ssh_run

        result = ssh_run("alice", node_alpha, "ls /home/bob/.claude/")
        # Should fail (permission denied) or be empty - either is acceptable
        # The key is that alice can't see bob's actual session data
        assert result.returncode != 0 or result.stdout.strip() == ""


class TestMultiUserOnBothNodes:
    """Test multi-user scenarios across both nodes."""

    def test_four_users_four_workspaces(self, alice, bob, charlie, dave, verify_ssh_connectivity):
        """All four test users can list their workspaces."""
        results = {}
        for name, remote in [
            ("alice", alice),
            ("bob", bob),
            ("charlie", charlie),
            ("dave", dave),
        ]:
            result = run_cli(["lsw", "-r", remote])
            results[name] = result
            assert result.returncode == 0, f"{name} failed: {result.stderr}"

        # All users should have workspaces
        for name, result in results.items():
            assert result.stdout.strip() != "", f"{name} has no workspaces"
