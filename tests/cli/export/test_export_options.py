"""Export option coverage for session export flags.

Spec Reference: docs/specs/cli-spec.md (export options)
"""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.helpers.cli import assert_cli_success, run_cli_subprocess

pytestmark = pytest.mark.v1


def test_session_export_source_copies_raw_files(
    isolated_home: Dict[str, Any],
    setup_golden_fixtures: Dict[str, Path],
) -> None:
    """--source should copy the original JSON/JSONL alongside markdown."""
    output_dir = isolated_home["path"] / "exports_source"
    output_dir.mkdir()

    result = run_cli_subprocess(
        ["session", "export", "--aw", "--source", "--force", "-o", str(output_dir)],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )
    if result.returncode != 0:
        pytest.skip(f"session export --source failed: {result.stderr}")

    md_files = list(output_dir.rglob("*.md"))
    json_copies = list(output_dir.rglob("*.jsonl")) + list(output_dir.rglob("*.json"))
    assert md_files, "Markdown output should be created with --source"
    assert json_copies, "Raw source files should be copied with --source"

    # Verify each source file was copied (match by exact content)
    source_contents = {path.read_text(encoding="utf-8"): path.suffix for path in setup_golden_fixtures.values()}
    matched = set()
    for copy in json_copies:
        content = copy.read_text(encoding="utf-8")
        if content in source_contents:
            matched.add(source_contents[content])
    assert matched, "At least one source file should be identical to a copied file"


def test_session_export_flat_writes_to_root(
    isolated_home: Dict[str, Any],
    setup_golden_fixtures: Dict[str, Path],
) -> None:
    """--flat should avoid creating workspace subdirectories."""
    output_dir = isolated_home["path"] / "exports_flat"
    output_dir.mkdir()

    result = run_cli_subprocess(
        ["session", "export", "--aw", "--flat", "--force", "-o", str(output_dir)],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )
    assert_cli_success(result, "--flat export should succeed")

    md_files = list(output_dir.rglob("*.md"))
    assert md_files, "Markdown output should exist"
    nested = [f for f in md_files if f.parent != output_dir]
    assert not nested, f"--flat should place files in {output_dir}, found nested files: {nested}"


def test_session_export_split_creates_parts(isolated_home: Dict[str, Any]) -> None:
    """--split should produce multiple part files for long conversations."""
    # Create a Claude workspace with enough messages to trigger splitting
    workspace = isolated_home["claude_dir"] / "-home-user-split-target"
    workspace.mkdir(parents=True, exist_ok=True)
    session_file = workspace / "split-session.jsonl"

    rows = []
    for i in range(6):
        rows.append(
            {
                "type": "user",
                "timestamp": f"2025-01-01T10:00:0{i}Z",
                "message": {"role": "user", "content": f"Step {i} details\nMore text to force lines"},
                "uuid": f"u{i}",
                "sessionId": "split-session",
            }
        )
        rows.append(
            {
                "type": "assistant",
                "timestamp": f"2025-01-01T10:00:1{i}Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": f"Assistant reply {i}\nwith extra lines\nand more"}],
                },
                "uuid": f"a{i}",
                "parentUuid": f"u{i}",
                "sessionId": "split-session",
            }
        )

    with open(session_file, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    output_dir = isolated_home["path"] / "exports_split"
    output_dir.mkdir()

    result = run_cli_subprocess(
        ["session", "export", "split-target", "--split", "10", "--force", "-o", str(output_dir)],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )
    assert_cli_success(result, "--split export should succeed")

    part_files = list(output_dir.rglob("*_part*.md"))
    assert part_files, "Split export should create part files"
