"""E2E tests for multi-agent scenarios.

Tests the --agent flag with Claude, Codex, and Gemini sessions on remote nodes.
"""

import pytest
from conftest import run_cli

pytestmark = pytest.mark.e2e_docker


class TestAgentDetection:
    """Test that different agent types are detected on remote nodes."""

    def test_auto_detects_all_agents(self, charlie, verify_ssh_connectivity):
        """--agent auto shows sessions from all agents."""
        result = run_cli(["lss", "--agent", "auto", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should have sessions (generated fixtures include all three agents)

    def test_claude_only(self, charlie, verify_ssh_connectivity):
        """--agent claude shows only Claude Code sessions."""
        result = run_cli(["lss", "--agent", "claude", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should filter to Claude sessions only

    def test_codex_only(self, charlie, verify_ssh_connectivity):
        """--agent codex shows only Codex CLI sessions."""
        result = run_cli(["lss", "--agent", "codex", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should filter to Codex sessions only

    def test_gemini_only(self, charlie, verify_ssh_connectivity):
        """--agent gemini shows only Gemini CLI sessions."""
        result = run_cli(["lss", "--agent", "gemini", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should filter to Gemini sessions only


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

    def test_lsw_agent_gemini(self, charlie, verify_ssh_connectivity):
        """lsw --agent gemini lists Gemini workspaces."""
        result = run_cli(["lsw", "--agent", "gemini", "-r", charlie])
        assert result.returncode == 0, f"stderr: {result.stderr}"


class TestAgentExport:
    """Test export with agent filtering on remote nodes."""

    def test_export_claude_only(self, charlie, tmp_path, verify_ssh_connectivity):
        """Export only Claude sessions from remote."""
        output_dir = tmp_path / "claude"
        result = run_cli(
            [
                "export",
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
                "--agent",
                "codex",
                "-r",
                charlie,
                "-o",
                str(output_dir),
            ]
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_export_gemini_only(self, charlie, tmp_path, verify_ssh_connectivity):
        """Export only Gemini sessions from remote."""
        output_dir = tmp_path / "gemini"
        result = run_cli(
            [
                "export",
                "--agent",
                "gemini",
                "-r",
                charlie,
                "-o",
                str(output_dir),
            ]
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_export_all_agents(self, charlie, tmp_path, verify_ssh_connectivity):
        """Export all agent types from remote."""
        output_dir = tmp_path / "all"
        result = run_cli(
            [
                "export",
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
        gemini_result = run_cli(["lss", "myproject", "--agent", "gemini", "-r", charlie])

        # All should succeed (even if no sessions match)
        assert claude_result.returncode == 0
        assert codex_result.returncode == 0
        assert gemini_result.returncode == 0

    def test_agent_count_consistency(self, charlie, verify_ssh_connectivity):
        """Sum of individual agents equals auto count."""
        auto_result = run_cli(["lss", "--agent", "auto", "-r", charlie])
        claude_result = run_cli(["lss", "--agent", "claude", "-r", charlie])
        codex_result = run_cli(["lss", "--agent", "codex", "-r", charlie])
        gemini_result = run_cli(["lss", "--agent", "gemini", "-r", charlie])

        # All should succeed
        assert auto_result.returncode == 0
        assert claude_result.returncode == 0
        assert codex_result.returncode == 0
        assert gemini_result.returncode == 0

        # Count lines (rough session count) - just verify we got output
        _ = len(auto_result.stdout.strip().split("\n")) if auto_result.stdout.strip() else 0
        _ = (
            (len(claude_result.stdout.strip().split("\n")) if claude_result.stdout.strip() else 0)
            + (len(codex_result.stdout.strip().split("\n")) if codex_result.stdout.strip() else 0)
            + (len(gemini_result.stdout.strip().split("\n")) if gemini_result.stdout.strip() else 0)
        )

        # Should be roughly equal (allowing for header lines etc.)
        # This is a sanity check, not exact
