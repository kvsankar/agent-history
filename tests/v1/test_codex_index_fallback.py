"""Codex index fallback tests (ported from legacy)."""

import json
from pathlib import Path
from typing import Dict

import pytest

from tests.helpers.cli import run_cli_subprocess
from tests.helpers.session_builders import CodexSessionBuilder

pytestmark = pytest.mark.v1


def _write_codex_session(tmp_codex_dir: Path, cwd: str) -> Path:
    """Create a minimal Codex session with the given cwd."""
    builder = CodexSessionBuilder(cwd=cwd, session_id="fallback-test")
    builder.add_user_message("hi").add_assistant_message("hello").add_token_count(100, 15, cached=40)
    return builder.write_to(tmp_codex_dir, date_str="2025-01-15")


def _write_index(history_dir: Path, mapping: Dict[str, str]) -> Path:
    """Write codex_session_index.json with provided mapping."""
    history_dir.mkdir(parents=True, exist_ok=True)
    index_file = history_dir / "codex_session_index.json"
    index_file.write_text(
        json.dumps({"version": 1, "last_scan_date": "2025-01-01", "sessions": mapping}),
        encoding="utf-8",
    )
    return index_file


def test_empty_index_entry_triggers_fallback(isolated_home: Dict[str, Path]) -> None:
    """Empty workspace in index should cause file read fallback."""
    session_file = _write_codex_session(isolated_home["codex_dir"], "/home/user/fallback-project")
    _write_index(isolated_home["history_dir"], {str(session_file): ""})

    result = run_cli_subprocess(
        ["--agent", "codex", "session", "list", "--local", "--aw"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, result.stderr
    assert "fallback" in result.stdout.lower() or "project" in result.stdout.lower()


def test_lsw_with_empty_index_entry(isolated_home: Dict[str, Path]) -> None:
    """Workspace listing should still work when index lacks workspace."""
    session_file = _write_codex_session(isolated_home["codex_dir"], "/home/user/my-project")
    _write_index(isolated_home["history_dir"], {str(session_file): ""})

    result = run_cli_subprocess(
        ["--agent", "codex", "ws", "--local"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "Expected workspace output"


def test_pattern_filter_with_fallback_workspace(isolated_home: Dict[str, Path]) -> None:
    """Pattern filters should work after fallback resolution."""
    session_file = _write_codex_session(isolated_home["codex_dir"], "/home/user/react-app")
    _write_index(isolated_home["history_dir"], {str(session_file): ""})

    result = run_cli_subprocess(
        ["--agent", "codex", "session", "list", "react", "--local", "--format", "json"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "Expected sessions when pattern matches"

    result2 = run_cli_subprocess(
        ["--agent", "codex", "session", "list", "nonexistent", "--local", "--format", "json"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )
    assert result2.returncode in (0, 1)
