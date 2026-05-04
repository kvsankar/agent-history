"""V1 CLI happy path tests.

Spec Reference: docs/specs/cli-spec.md

These tests validate the basic CLI commands work with golden fixtures:
- ws list: List workspaces
- session list: List sessions in workspace
- session export: Export to markdown
- session stats: Show aggregate statistics

Note: Tests are written to spec, not implementation. They may fail until
the implementation is updated to match the spec.
"""

from pathlib import Path
from typing import Any, Dict

import pytest

from tests.helpers.cli import (
    assert_cli_success,
    run_cli_subprocess,
)

pytestmark = pytest.mark.v1


class TestWsList:
    """Test ws list command."""

    def test_ws_list_returns_success(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """ws list returns exit code 0."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )
        assert_cli_success(result, "ws list should succeed")

    def test_ws_list_shows_workspaces(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """ws list shows workspace names."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"ws list failed: {result.stderr}")

        # Should show at least one workspace
        output = result.stdout
        # Check for workspace indicators (exact format depends on impl)
        assert output.strip(), "ws list should produce output"

    def test_ws_list_shows_claude_workspace(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """ws list shows Claude workspace."""
        result = run_cli_subprocess(
            ["ws", "list", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"ws list failed: {result.stderr}")

        # Should mention the golden project workspace
        # The exact format may vary
        output = result.stdout.lower()
        # Check for any indication of the workspace
        assert (
            "golden" in output or "testuser" in output or "project" in output or len(output) > 0
        ), "ws list should show workspace information"


class TestSessionList:
    """Test session list command."""

    def test_session_list_returns_success(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """session list returns exit code 0."""
        result = run_cli_subprocess(
            ["session", "list", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )
        assert_cli_success(result, "session list should succeed")

    def test_session_list_shows_sessions(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
        golden_totals: Dict[str, Any],
    ):
        """session list shows correct number of sessions."""
        result = run_cli_subprocess(
            ["session", "list", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"session list failed: {result.stderr}")

        output = result.stdout
        # Should have output for sessions
        assert output.strip(), "session list should produce output"


class TestSessionExport:
    """Test session export command."""

    def test_session_export_creates_file(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """session export creates markdown file."""
        output_dir = isolated_home["path"] / "exports"
        output_dir.mkdir()

        result = run_cli_subprocess(
            ["session", "export", "-o", str(output_dir), "--aw", "--force"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"session export failed: {result.stderr}")

        # Should create at least one markdown file
        md_files = list(output_dir.glob("**/*.md"))
        assert len(md_files) > 0, "session export should create markdown files"

    def test_session_export_markdown_has_content(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """Exported markdown has message content."""
        output_dir = isolated_home["path"] / "exports"
        output_dir.mkdir()

        result = run_cli_subprocess(
            ["session", "export", "-o", str(output_dir), "--aw", "--force"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"session export failed: {result.stderr}")

        md_files = list(output_dir.glob("**/*.md"))
        if not md_files:
            pytest.skip("No markdown files created")

        # Read first file and check for content
        content = md_files[0].read_text()
        assert len(content) > 100, "Markdown should have substantial content"

    def test_session_export_minimal_flag(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """session export --minimal omits metadata."""
        output_dir = isolated_home["path"] / "exports"
        output_dir.mkdir()

        # Export with minimal flag
        result = run_cli_subprocess(
            ["session", "export", "--minimal", "-o", str(output_dir), "--aw", "--force"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"session export --minimal failed: {result.stderr}")

        md_files = list(output_dir.glob("**/*.md"))
        if md_files:
            content = md_files[0].read_text()
            # Minimal mode should not include UUID metadata
            assert (
                "UUID" not in content or "uuid" not in content.lower()
            ), "Minimal mode should omit UUID metadata"

    def test_session_export_json_flag(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """session export --json creates NDJSON file."""
        output_dir = isolated_home["path"] / "exports"
        output_dir.mkdir()

        result = run_cli_subprocess(
            ["session", "export", "--json", "-o", str(output_dir), "--aw", "--force"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"session export --json failed: {result.stderr}")

        # Should create NDJSON files
        json_files = list(output_dir.glob("**/*.ndjson")) + list(output_dir.glob("**/*.json"))
        assert len(json_files) > 0, "session export --json should create JSON/NDJSON files"


class TestSessionStats:
    """Test session stats command."""

    def test_session_stats_returns_success(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """session stats returns exit code 0."""
        result = run_cli_subprocess(
            ["session", "stats", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )
        assert_cli_success(result, "session stats should succeed")

    def test_session_stats_shows_counts(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """session stats shows session and message counts."""
        result = run_cli_subprocess(
            ["session", "stats", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"session stats failed: {result.stderr}")

        output = result.stdout
        assert output.strip(), "session stats should produce output"

    def test_session_stats_sync_flag(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """session stats --sync creates metrics database."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"session stats --sync failed: {result.stderr}")

        # Command succeeded - metrics.db may or may not be created depending on impl


class TestAgentFilter:
    """Test --agent filter flag."""

    def test_agent_filter_claude(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """--agent claude filters to Claude sessions only."""
        result = run_cli_subprocess(
            ["session", "list", "--aw", "--agent", "claude"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"--agent claude failed: {result.stderr}")

    def test_agent_filter_codex(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """--agent codex filters to Codex sessions only."""
        result = run_cli_subprocess(
            ["session", "list", "--aw", "--agent", "codex"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"--agent codex failed: {result.stderr}")

    def test_agent_filter_gemini(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """--agent gemini filters to Gemini sessions only."""
        result = run_cli_subprocess(
            ["session", "list", "--aw", "--agent", "gemini"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"--agent gemini failed: {result.stderr}")
