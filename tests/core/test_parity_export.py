"""Parity tests for export behavior across agents and NDJSON schema."""

import json
from pathlib import Path

from tests.helpers.cli import run_cli_subprocess


def _find_single_output_file(output_dir: Path, suffix: str) -> Path:
    matches = [
        path for path in output_dir.glob(f"**/*{suffix}") if path.name != "index.md"
    ]
    assert matches, f"Expected export output with suffix {suffix}"
    return matches[0]


def test_codex_markdown_export_uses_codex_header(
    isolated_home, setup_golden_fixtures
):
    output_dir = isolated_home["path"] / "exports"
    output_dir.mkdir()

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "--agent",
            "codex",
            "--aw",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"

    output_file = _find_single_output_file(output_dir, ".md")
    contents = output_file.read_text(encoding="utf-8")
    assert contents.startswith("# Codex Conversation"), "Expected Codex export header"


def test_gemini_markdown_export_uses_gemini_header(
    isolated_home, setup_golden_fixtures
):
    output_dir = isolated_home["path"] / "exports"
    output_dir.mkdir()

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "--agent",
            "gemini",
            "--aw",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"

    output_file = _find_single_output_file(output_dir, ".md")
    contents = output_file.read_text(encoding="utf-8")
    assert contents.startswith("# Gemini Conversation"), "Expected Gemini export header"


def test_ndjson_export_writes_header_and_session_record(
    isolated_home, setup_golden_fixtures
):
    output_dir = isolated_home["path"] / "exports"
    output_dir.mkdir()

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "--json",
            "--aw",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"

    output_file = _find_single_output_file(output_dir, ".ndjson")
    lines = [line for line in output_file.read_text(encoding="utf-8").splitlines() if line]
    assert lines, "Expected NDJSON output"

    first = json.loads(lines[0])
    assert first.get("type") == "header", "Expected header as first NDJSON line"

    session_lines = [json.loads(line) for line in lines if json.loads(line).get("type") == "session"]
    assert session_lines, "Expected at least one session record"
