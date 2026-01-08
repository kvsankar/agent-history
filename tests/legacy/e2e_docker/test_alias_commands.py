"""E2E tests for alias commands using Docker infrastructure."""

from .helpers import get_env, run_cli


class TestAliasLifecycle:
    """Test alias create/list/show/delete lifecycle."""

    def test_alias_create_and_list(self):
        """Test creating an alias and listing it."""
        # Create alias
        result = run_cli(["project", "add", "test-project", "--allow-empty"])
        assert result.returncode == 0

        # List aliases
        result = run_cli(["project", "list"])
        assert result.returncode == 0
        assert "test-project" in result.stdout

        # Delete alias
        result = run_cli(["project", "remove", "test-project"])
        assert result.returncode == 0

    def test_alias_show_empty(self):
        """Test showing an empty alias."""
        # Create empty alias
        run_cli(["project", "add", "empty-alias", "--allow-empty"])

        # Show it
        result = run_cli(["project", "show", "empty-alias"])
        assert result.returncode == 0
        # Should indicate it's empty or show no workspaces

        # Cleanup
        run_cli(["project", "remove", "empty-alias"])

    def test_alias_list_with_counts(self):
        """Test alias list with --counts flag."""
        # Create alias
        run_cli(["project", "add", "counted-alias", "--allow-empty"])

        # List with counts
        result = run_cli(["project", "list", "--counts"])
        assert result.returncode == 0
        assert "counted-alias" in result.stdout

        # Cleanup
        run_cli(["project", "remove", "counted-alias"])


class TestAliasWithRemote:
    """Test alias commands with remote workspaces."""

    def test_alias_add_from_remote(self):
        """Test adding workspaces from remote to alias."""
        env = get_env()
        node = env["node_alpha"]
        user = env["alpha_users"][0]

        # Create alias
        result = run_cli(["project", "add", "remote-test", "--allow-empty"])
        assert result.returncode == 0

        # Add workspace from remote - use '*' to match any workspace
        result = run_cli(
            [
                "project",
                "add",
                "remote-test",
                "-r",
                f"{user}@{node}",
                "*",  # pattern to match any workspace
            ]
        )
        # Should not crash - may succeed or have no matches
        assert "Traceback" not in result.stderr

        # Show alias
        result = run_cli(["project", "show", "remote-test"])
        assert result.returncode == 0

        # Cleanup
        run_cli(["project", "remove", "remote-test"])


class TestAliasLss:
    """Test lss command with aliases."""

    def test_lss_with_alias_syntax(self):
        """Test lss @alias syntax."""
        # Create alias first
        run_cli(["project", "add", "lss-test", "--allow-empty"])

        # Use @alias syntax
        result = run_cli(["lss", "@lss-test"])
        # Should work even if alias is empty
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stderr

        # Cleanup
        run_cli(["project", "remove", "lss-test"])

    def test_lss_with_alias_flag(self):
        """Test lss --alias flag."""
        run_cli(["project", "add", "flag-test", "--allow-empty"])

        result = run_cli(["lss", "--alias", "flag-test"])
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stderr

        run_cli(["project", "remove", "flag-test"])


class TestAliasExport:
    """Test export command with aliases."""

    def test_export_with_alias(self, tmp_path):
        """Test export @alias syntax."""
        run_cli(["project", "add", "export-test", "--allow-empty"])

        result = run_cli(["export", "@export-test", "-o", "/tmp/alias-export"])
        # Should work even if empty
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stderr

        run_cli(["project", "remove", "export-test"])


class TestSourceManagement:
    """Test home (list homes) source management."""

    def test_lsh_list(self):
        """Test listing homes."""
        result = run_cli(["home"])
        assert result.returncode == 0
        assert "Traceback" not in result.stderr

    def test_lsh_add_remove_remote(self):
        """Test adding and removing a remote source."""
        env = get_env()
        node = env["node_alpha"]
        user = env["alpha_users"][0]
        remote = f"{user}@{node}"

        # Add remote
        result = run_cli(["home", "add", remote])
        assert result.returncode == 0
        assert "Traceback" not in result.stderr

        # Verify it's listed
        result = run_cli(["home"])
        assert result.returncode == 0

        # Remove remote
        result = run_cli(["home", "remove", remote])
        assert result.returncode == 0

    def test_lsh_clear(self):
        """Test clearing all sources."""
        result = run_cli(["home", "clear"])
        assert result.returncode == 0
