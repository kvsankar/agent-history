"""Export output requirements for agent formats and NDJSON schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.helpers.cli import assert_cli_success, run_cli_subprocess
from tests.helpers.gap_helpers import assert_exported_to_dir, ensure_config_env


pytestmark = pytest.mark.scope


class TestExportMetadataRequirements:
    """Exports should include agent metadata and unified schema headers."""

    def test_codex_export_includes_session_metadata(
        self, agent_filter_sessions: Dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "codex-export"
        env = ensure_config_env(agent_filter_sessions["env"], tmp_path / ".agent-history")
        result = run_cli_subprocess(
            ["session", "export", "--agent", "codex", "--aw", "-o", str(output_dir)],
            env=env,
        )

        assert_cli_success(result, "Codex export should succeed")
        assert "No sessions found" not in result.stderr, "Codex export returned no sessions"
        assert_exported_to_dir(result, output_dir)
        md_files = sorted(output_dir.rglob("*.md"))
        assert md_files, "Expected markdown exports for Codex sessions"
        content = md_files[0].read_text(encoding="utf-8")
        assert "## Session Metadata" in content, "Expected Codex session metadata section"

    def test_gemini_export_includes_session_metadata(
        self, agent_filter_sessions: Dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "gemini-export"
        env = ensure_config_env(agent_filter_sessions["env"], tmp_path / ".agent-history")
        result = run_cli_subprocess(
            ["session", "export", "--agent", "gemini", "--aw", "-o", str(output_dir)],
            env=env,
        )

        assert_cli_success(result, "Gemini export should succeed")
        assert "No sessions found" not in result.stderr, "Gemini export returned no sessions"
        assert_exported_to_dir(result, output_dir)
        md_files = sorted(output_dir.rglob("*.md"))
        assert md_files, "Expected markdown exports for Gemini sessions"
        content = md_files[0].read_text(encoding="utf-8")
        assert "## Session Metadata" in content, "Expected Gemini session metadata section"

    def test_ndjson_header_schema_version(
        self, agent_filter_sessions: Dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "ndjson-export"
        env = ensure_config_env(agent_filter_sessions["env"], tmp_path / ".agent-history")
        result = run_cli_subprocess(
            ["session", "export", "--agent", "claude", "--aw", "--json", "-o", str(output_dir)],
            env=env,
        )

        assert_cli_success(result, "NDJSON export should succeed")
        assert "No sessions found" not in result.stderr, "NDJSON export returned no sessions"
        assert_exported_to_dir(result, output_dir)
        ndjson_files = sorted(output_dir.rglob("*.ndjson"))
        assert ndjson_files, "Expected NDJSON export files"
        header = json.loads(ndjson_files[0].read_text(encoding="utf-8").splitlines()[0])
        assert "schema_version" in header, "Expected unified schema_version in NDJSON header"

    def test_ndjson_source_copy(
        self, agent_filter_sessions: Dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "ndjson-source"
        env = ensure_config_env(agent_filter_sessions["env"], tmp_path / ".agent-history")
        result = run_cli_subprocess(
            [
                "session",
                "export",
                "--agent",
                "claude",
                "--aw",
                "--json",
                "--source",
                "-o",
                str(output_dir),
            ],
            env=env,
        )

        assert_cli_success(result, "NDJSON export with --source should succeed")
        assert "No sessions found" not in result.stderr, "NDJSON export returned no sessions"
        assert_exported_to_dir(result, output_dir)
        ndjson_files = sorted(output_dir.rglob("*.ndjson"))
        assert ndjson_files, "Expected NDJSON export files"
        source_copy = ndjson_files[0].with_suffix(".jsonl")
        assert source_copy.exists(), "Expected raw source copy alongside NDJSON export"
