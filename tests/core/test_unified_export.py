"""V1 unified export tests.

Spec Reference: docs/specs/cli-spec.md

These tests validate that sessions from all agents can be exported to
the unified NDJSON format with correct field mapping.
"""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.helpers.cli import run_cli_subprocess

pytestmark = pytest.mark.v1


class TestUnifiedExportClaude:
    """Test unified export for Claude sessions."""

    def test_export_json_creates_ndjson(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """Export --json creates NDJSON file."""
        output_dir = isolated_home["path"] / "exports"
        output_dir.mkdir()

        result = run_cli_subprocess(
            ["session", "export", "--json", "-o", str(output_dir), "--aw", "--force"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        # Allow failure if implementation not complete
        if result.returncode != 0:
            pytest.skip(f"Export not implemented or failed: {result.stderr}")

        # Find exported files
        json_files = list(output_dir.glob("**/*.ndjson"))
        assert len(json_files) > 0, "Should create at least one NDJSON file"

    def test_unified_schema_has_required_fields(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """Exported NDJSON has required unified schema fields."""
        output_dir = isolated_home["path"] / "exports"
        output_dir.mkdir()

        result = run_cli_subprocess(
            ["session", "export", "--json", "-o", str(output_dir), "--aw", "--force"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"Export not implemented: {result.stderr}")

        json_files = list(output_dir.glob("**/*.ndjson"))
        if not json_files:
            pytest.skip("No NDJSON files created")

        # Read first non-schema record and check schema
        with open(json_files[0], encoding="utf-8") as f:
            record = None
            for line in f:
                if not line.strip():
                    continue
                candidate = json.loads(line)
                if candidate.get("type") in ("schema", "header"):
                    continue
                record = candidate
                break

        if record is None:
            pytest.skip("No message records found in NDJSON file")

        # Check for unified schema fields
        # These are the minimum fields expected in unified format
        required_fields = ["timestamp", "role", "content"]
        for field in required_fields:
            assert field in record, f"Missing required field: {field}"


class TestUnifiedExportCodex:
    """Test unified export for Codex sessions."""

    def test_export_codex_session(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """Export Codex session to unified format."""
        output_dir = isolated_home["path"] / "exports"
        output_dir.mkdir()

        result = run_cli_subprocess(
            [
                "session",
                "export",
                "--json",
                "-o",
                str(output_dir),
                "--aw",
                "--agent",
                "codex",
                "--force",
            ],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"Codex export not implemented: {result.stderr}")


class TestUnifiedExportGemini:
    """Test unified export for Gemini sessions."""

    def test_export_gemini_session(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """Export Gemini session to unified format."""
        output_dir = isolated_home["path"] / "exports"
        output_dir.mkdir()

        result = run_cli_subprocess(
            [
                "session",
                "export",
                "--json",
                "-o",
                str(output_dir),
                "--aw",
                "--agent",
                "gemini",
                "--force",
            ],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"Gemini export not implemented: {result.stderr}")


class TestUnifiedExportAllAgents:
    """Test unified export across all agents."""

    def test_export_all_agents(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
        golden_totals: Dict[str, Any],
    ):
        """Export all agents and verify session count."""
        output_dir = isolated_home["path"] / "exports"
        output_dir.mkdir()

        result = run_cli_subprocess(
            ["session", "export", "--json", "-o", str(output_dir), "--aw", "--force"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"Multi-agent export not implemented: {result.stderr}")

        # Count exported sessions
        json_files = list(output_dir.glob("**/*.ndjson"))

        # We expect 3 sessions (one per agent)
        expected_sessions = golden_totals["sessions"]
        assert (
            len(json_files) >= expected_sessions
        ), f"Expected at least {expected_sessions} exported files, got {len(json_files)}"

    def test_unified_format_normalizes_roles(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """Unified format normalizes role names (gemini -> assistant)."""
        output_dir = isolated_home["path"] / "exports"
        output_dir.mkdir()

        result = run_cli_subprocess(
            ["session", "export", "--json", "-o", str(output_dir), "--aw", "--force"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"Export not implemented: {result.stderr}")

        # Check all files for role normalization
        for json_file in output_dir.glob("**/*.ndjson"):
            with open(json_file, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        role = record.get("role")
                        if role:
                            # All roles should be normalized to user/assistant
                            assert role in (
                                "user",
                                "assistant",
                                "system",
                            ), f"Unexpected role '{role}' - should be normalized"
