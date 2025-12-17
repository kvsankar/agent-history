"""E2E tests for multi-agent scenarios.

Tests the --agent flag with Claude, Codex, and Gemini sessions on remote nodes.
"""

import pytest

from .helpers import run_cli

pytestmark = pytest.mark.e2e_docker


class TestAgentDetection:
    """Test that different agent types are detected on remote nodes."""

    def test_auto_detects_all_agents(self, charlie, verify_ssh_connectivity):
        """--agent auto shows sessions from all agents."""
        # Use '*' to match all workspaces (no current workspace on remote)
        result = run_cli(["lss", "*", "--agent", "auto", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should have sessions (generated fixtures include all three agents)
        assert result.stdout.strip(), "Expected sessions from all agents"

    def test_claude_only(self, charlie, verify_ssh_connectivity):
        """--agent claude shows only Claude Code sessions."""
        result = run_cli(["lss", "*", "--agent", "claude", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should filter to Claude sessions only
        assert result.stdout.strip(), "Expected Claude sessions but got none"

    def test_codex_only(self, charlie, verify_ssh_connectivity):
        """--agent codex shows only Codex CLI sessions."""
        result = run_cli(["lss", "*", "--agent", "codex", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should find Codex sessions (synthetic data has them)
        assert result.stdout.strip(), "Expected Codex sessions but got none"

    def test_gemini_only(self, charlie, verify_ssh_connectivity):
        """--agent gemini shows only Gemini CLI sessions."""
        result = run_cli(["lss", "*", "--agent", "gemini", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should find Gemini sessions (synthetic data has them)
        assert result.stdout.strip(), "Expected Gemini sessions but got none"


class TestAgentWorkspaces:
    """Test workspace listing with agent filtering."""

    def test_lsw_agent_claude(self, charlie, verify_ssh_connectivity):
        """lsw --agent claude lists Claude workspaces."""
        result = run_cli(["lsw", "--agent", "claude", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_lsw_agent_codex(self, charlie, verify_ssh_connectivity):
        """lsw --agent codex lists Codex workspaces."""
        result = run_cli(["lsw", "--agent", "codex", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should find Codex workspaces (synthetic data has them)
        assert "myproject" in result.stdout, f"Expected 'myproject' workspace, got: {result.stdout}"

    def test_lsw_agent_gemini(self, charlie, verify_ssh_connectivity):
        """lsw --agent gemini lists Gemini workspaces."""
        result = run_cli(["lsw", "--agent", "gemini", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should find Gemini workspaces (hash-based)
        assert result.stdout.strip(), "Expected Gemini workspaces but got none"


class TestAgentExport:
    """Test export with agent filtering on remote nodes."""

    def test_export_claude_only(self, charlie, tmp_path, verify_ssh_connectivity):
        """Export only Claude sessions from remote."""
        output_dir = tmp_path / "claude"
        result = run_cli(
            [
                "export",
                "--aw",
                "--agent",
                "claude",
                "-r",
                charlie,
                "-o",
                str(output_dir),
            ]
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_export_codex_only(self, charlie, tmp_path, verify_ssh_connectivity):
        """Export only Codex sessions from remote."""
        output_dir = tmp_path / "codex"
        result = run_cli(
            [
                "export",
                "--aw",
                "--agent",
                "codex",
                "-r",
                charlie,
                "-o",
                str(output_dir),
            ]
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Verify files were exported
        assert output_dir.exists(), "Output directory should be created"

    def test_export_gemini_only(self, charlie, tmp_path, verify_ssh_connectivity):
        """Export only Gemini sessions from remote."""
        output_dir = tmp_path / "gemini"
        result = run_cli(
            [
                "export",
                "--aw",
                "--agent",
                "gemini",
                "-r",
                charlie,
                "-o",
                str(output_dir),
            ]
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Verify output directory exists
        assert output_dir.exists(), "Output directory should be created"

    def test_export_all_agents(self, charlie, tmp_path, verify_ssh_connectivity):
        """Export all agent types from remote."""
        output_dir = tmp_path / "all"
        result = run_cli(
            [
                "export",
                "--aw",
                "--agent",
                "auto",
                "-r",
                charlie,
                "-o",
                str(output_dir),
            ]
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"


class TestMixedAgentScenarios:
    """Test scenarios with mixed agent types."""

    def test_same_workspace_multiple_agents(self, charlie, verify_ssh_connectivity):
        """Workspace can have sessions from multiple agents."""
        # myproject should have Claude, Codex, and Gemini sessions
        # (created by generate-sessions.sh)

        claude_result = run_cli(["lss", "myproject", "--agent", "claude", "-r", charlie])
        codex_result = run_cli(["lss", "myproject", "--agent", "codex", "-r", charlie])
        # Gemini uses hash-based workspaces, so use '*' to match all
        gemini_result = run_cli(["lss", "*", "--agent", "gemini", "-r", charlie])

        # All should succeed and return sessions
        assert claude_result.returncode == 0, f"Claude failed: {claude_result.stderr}"
        assert codex_result.returncode == 0, f"Codex failed: {codex_result.stderr}"
        assert gemini_result.returncode == 0, f"Gemini failed: {gemini_result.stderr}"

        assert claude_result.stdout.strip(), "Expected Claude sessions for myproject"
        assert codex_result.stdout.strip(), "Expected Codex sessions for myproject"
        assert gemini_result.stdout.strip(), "Expected Gemini sessions"

    def test_agent_count_consistency(self, charlie, verify_ssh_connectivity):
        """All agents can be queried successfully."""
        # Use '*' to match all workspaces
        auto_result = run_cli(["lss", "*", "--agent", "auto", "-r", charlie])
        claude_result = run_cli(["lss", "*", "--agent", "claude", "-r", charlie])
        codex_result = run_cli(["lss", "*", "--agent", "codex", "-r", charlie])
        gemini_result = run_cli(["lss", "*", "--agent", "gemini", "-r", charlie])

        # All should succeed
        assert auto_result.returncode == 0, f"Auto failed: {auto_result.stderr}"
        assert claude_result.returncode == 0, f"Claude failed: {claude_result.stderr}"
        assert codex_result.returncode == 0, f"Codex failed: {codex_result.stderr}"
        assert gemini_result.returncode == 0, f"Gemini failed: {gemini_result.stderr}"

        # Verify we got output from each
        assert auto_result.stdout.strip(), "Auto should return sessions"
        assert claude_result.stdout.strip(), "Claude should return sessions"
        assert codex_result.stdout.strip(), "Codex should return sessions"
        assert gemini_result.stdout.strip(), "Gemini should return sessions"
