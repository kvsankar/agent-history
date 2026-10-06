"""Stats sync of a Windows home through cagelens running on Windows.

The "Windows" side here is this machine's Python running the same code, so
the test covers the command, the exchange files and the import, not the
WSL-to-Windows boundary itself.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from tests.helpers.cli import run_cli_subprocess

# The Windows export is how WSL reads a Windows home; native Windows reads it directly.
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="WSL/Linux-side feature")

REPO = Path(__file__).resolve().parents[3]


def _claude_session(projects_dir: Path) -> None:
    path = projects_dir / "-work-books" / "s-1.jsonl"
    path.parent.mkdir(parents=True)
    entries = [
        {
            "type": "user",
            "uuid": "u",
            "sessionId": "s-1",
            "timestamp": "2026-03-01T10:00:00Z",
            "cwd": "/work/books",
            "message": {"role": "user", "content": "hi"},
        },
        {
            "type": "assistant",
            "uuid": "a",
            "sessionId": "s-1",
            "timestamp": "2026-03-01T10:00:05Z",
            "cwd": "/work/books",
            "message": {
                "id": "m",
                "role": "assistant",
                "model": "claude-test",
                "content": [],
                "usage": {"input_tokens": 9, "output_tokens": 1},
            },
        },
    ]
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def _configure(isolated_home, python: str) -> None:
    config = {
        "version": 2,
        "homes": [],
        "projects": {},
        "windows_native": {
            "python": python,
            "code": str(REPO),
            "exchange_dir": str(isolated_home["path"] / "exchange"),
        },
    }
    (isolated_home["history_dir"] / "config.json").write_text(json.dumps(config), encoding="utf-8")


def _rows(isolated_home):
    with sqlite3.connect(isolated_home["history_dir"] / "metrics.db") as conn:
        return conn.execute("SELECT home, workspace, input_tokens FROM sessions").fetchall()


def test_windows_home_rows_come_from_the_windows_export(isolated_home):
    _claude_session(isolated_home["claude_dir"])
    _configure(isolated_home, sys.executable)

    result = run_cli_subprocess(
        ["stats", "--sync", "--home", "windows:alex", "--aw", "--quiet"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    rows = _rows(isolated_home)
    assert [(home, tokens) for home, _ws, tokens in rows] == [("windows:alex", 9)]

    again = run_cli_subprocess(
        ["stats", "--sync", "--home", "windows:alex", "--aw", "--quiet"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
        timeout=120,
    )
    assert again.returncode == 0, again.stderr
    export = isolated_home["path"] / "exchange" / "export.jsonl"
    lines = [json.loads(line) for line in export.read_text(encoding="utf-8").splitlines()]
    assert [line["record"] for line in lines] == [None], "unchanged file must not be re-parsed"
    assert len(_rows(isolated_home)) == 1


def test_unreachable_windows_falls_back_with_a_warning(isolated_home):
    _configure(isolated_home, str(isolated_home["path"] / "missing-python.exe"))

    result = run_cli_subprocess(
        ["stats", "--sync", "--home", "windows:alex", "--aw", "--quiet"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "could not run cagelens on Windows" in result.stderr
