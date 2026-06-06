"""Behavior tests for Gemini hash index management."""

import hashlib
import json
from pathlib import Path

from tests.helpers.cli import run_cli_subprocess


def _write_minimal_gemini_session(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "sessionId": "test-session",
                "projectHash": path.parent.parent.name,
                "startTime": "2025-01-01T00:00:00Z",
                "lastUpdated": "2025-01-01T00:00:01Z",
                "messages": [],
            }
        ),
        encoding="utf-8",
    )


def test_gemini_index_add_creates_mapping(isolated_home, tmp_path: Path):
    """gemini-index --add should create hash->path mappings."""
    project_dir = tmp_path / "gemini-project"
    project_dir.mkdir()

    project_hash = hashlib.sha256(str(project_dir.resolve()).encode()).hexdigest()

    chats_dir = isolated_home["gemini_dir"] / project_hash / "chats"
    chats_dir.mkdir(parents=True, exist_ok=True)
    session_file = chats_dir / "session-2025-01-01T00-00-test.json"
    _write_minimal_gemini_session(session_file)

    result = run_cli_subprocess(
        ["gemini-index", "--add", str(project_dir)],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"

    index_file = isolated_home["history_dir"] / "gemini_index.json"
    assert index_file.exists(), "Expected gemini_index.json to be created"

    data = json.loads(index_file.read_text(encoding="utf-8"))
    assert data.get("hashes", {}).get(project_hash) == str(project_dir.resolve())


def test_gemini_index_list_table_output(isolated_home):
    """gemini-index should render readable table output by default in table mode."""
    project_hash = "abcd1234" * 8
    project_path = "/home/user/gemini-project"
    index_file = isolated_home["history_dir"] / "gemini_index.json"
    index_file.write_text(
        json.dumps({"version": 1, "hashes": {project_hash: project_path}}),
        encoding="utf-8",
    )

    result = run_cli_subprocess(
        ["gemini-index", "--format", "table"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, result.stderr
    assert "HASH" in result.stdout
    assert "PATH" in result.stdout
    assert project_hash[:8] in result.stdout
    assert project_path in result.stdout
    assert "{'action':" not in result.stdout


def test_gemini_index_list_tsv_output(isolated_home):
    """gemini-index should render TSV when requested or piped."""
    project_hash = "dcba4321" * 8
    project_path = "/home/user/gemini-project"
    index_file = isolated_home["history_dir"] / "gemini_index.json"
    index_file.write_text(
        json.dumps({"version": 1, "hashes": {project_hash: project_path}}),
        encoding="utf-8",
    )

    result = run_cli_subprocess(
        ["gemini-index", "--format", "tsv"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "HASH\tPATH"
    assert f"{project_hash[:8]}\t{project_path}" in result.stdout
