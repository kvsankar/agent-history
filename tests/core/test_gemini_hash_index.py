"""Gemini hash index and workspace resolution tests (ported from legacy)."""

import json
from pathlib import Path
from typing import Dict

import pytest

from tests.helpers.cli import run_cli_subprocess
from tests.helpers.session_builders import GeminiSessionBuilder

pytestmark = pytest.mark.v1


def _write_gemini_session(gemini_dir: Path, project_hash: str, session_id: str = "session-001") -> Path:
    """Create a minimal Gemini session under the hash directory."""
    builder = GeminiSessionBuilder(session_id=session_id, project_hash=project_hash)
    builder.add_user_message("hi").add_gemini_message("hello", input_tokens=10, output_tokens=5)
    return builder.write_to(gemini_dir)


def _write_hash_index(history_dir: Path, mapping: Dict[str, str]) -> Path:
    """Write gemini_hash_index.json with provided mapping."""
    history_dir.mkdir(parents=True, exist_ok=True)
    index_file = history_dir / "gemini_hash_index.json"
    index_file.write_text(json.dumps({"version": 1, "hashes": mapping}), encoding="utf-8")
    return index_file


def test_workspace_uses_encoded_path_when_index_present(isolated_home):
    """Readable workspace should replace hash when index is populated."""
    project_hash = "abc123def456789"
    project_path = "/home/testuser/myproject"
    _write_hash_index(isolated_home["history_dir"], {project_hash: project_path})
    _write_gemini_session(isolated_home["gemini_dir"], project_hash, "session-encoded")

    result = run_cli_subprocess(
        ["--agent", "gemini", "ws", "list", "--local"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "Expected workspace output"
    assert "[hash:" not in result.stdout


def test_pattern_filter_matches_path_with_index(isolated_home):
    """Pattern filtering should match readable path from hash index."""
    project_hash = "xyz789abc123"
    project_path = "/home/user/django-app"
    _write_hash_index(isolated_home["history_dir"], {project_hash: project_path})
    _write_gemini_session(isolated_home["gemini_dir"], project_hash, "session-filter")

    result = run_cli_subprocess(
        ["--agent", "gemini", "session", "list", "django", "--format", "json"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "Expected output for matching pattern"


def test_export_uses_encoded_path_in_output(isolated_home, tmp_path: Path):
    """Export should use encoded path directory names when index is present."""
    project_hash = "exporthash123"
    project_path = "/home/user/export-test-project"
    _write_hash_index(isolated_home["history_dir"], {project_hash: project_path})
    _write_gemini_session(isolated_home["gemini_dir"], project_hash, "session-export")

    output_dir = tmp_path / "exports"
    output_dir.mkdir()

    result = run_cli_subprocess(
        ["--agent", "gemini", "session", "export", "--aw", "-o", str(output_dir)],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, result.stderr
    md_files = list(output_dir.rglob("*.md"))
    assert md_files, "Expected exported markdown"
    # Directory names should favor encoded path over raw hash
    dir_names = {p.parent.name for p in md_files}
    assert project_hash not in dir_names
