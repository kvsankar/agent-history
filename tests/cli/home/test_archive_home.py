"""Archive homes: saved home directories from machines that no longer run.

An archive keeps a machine's original layout, e.g. ``home/alex/.claude``.
cagelens reads it as a read-only home whose workspaces keep their original
paths, with no SSH access.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from tests.helpers.cli import run_cli_subprocess

pytestmark = [pytest.mark.home_scope]

ORBIT = "/home/alex/alex/projects/orbit"
NOTES = "/home/adam/notes"


def _claude_session(user_home: Path, workspace: str, session_id: str) -> None:
    encoded = workspace.replace("/", "-")
    path = user_home / ".claude" / "projects" / encoded / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True)
    entries = [
        {
            "type": "user",
            "uuid": f"{session_id}-u",
            "sessionId": session_id,
            "timestamp": "2026-02-01T10:00:00Z",
            "cwd": workspace,
            "message": {"role": "user", "content": "hello"},
        },
        {
            "type": "assistant",
            "uuid": f"{session_id}-a",
            "parentUuid": f"{session_id}-u",
            "sessionId": session_id,
            "timestamp": "2026-02-01T10:00:05Z",
            "cwd": workspace,
            "message": {
                "id": f"msg-{session_id}",
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "text", "text": "hi"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        },
    ]
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")


@pytest.fixture
def archive_root(tmp_path: Path) -> Path:
    """An archive of a retired VM with two users' saved home directories."""
    root = tmp_path / "archive" / "ubuntu-vm-uvm-20260928"
    _claude_session(root / "home" / "alex", ORBIT, "s-1")
    _claude_session(root / "home" / "adam", NOTES, "k-1")
    return root


def _run(isolated_home, *args):
    result = run_cli_subprocess(list(args), env=isolated_home["env"], cwd=isolated_home["path"])
    assert result.returncode == 0, result.stderr + result.stdout
    return result.stdout


def _config(isolated_home):
    return json.loads((isolated_home["history_dir"] / "config.json").read_text(encoding="utf-8"))


def test_add_registers_one_home_per_saved_user(isolated_home, archive_root):
    _run(isolated_home, "home", "add", "--archive", str(archive_root), "--name", "uvm")

    config = _config(isolated_home)
    assert "archive:uvm-alex" in config["homes"]
    assert "archive:uvm-adam" in config["homes"]
    assert config["archives"]["uvm-alex"] == str(archive_root / "home" / "alex")


def test_add_accepts_a_single_saved_home_directory(isolated_home, archive_root):
    user_home = archive_root / "home" / "alex"
    _run(isolated_home, "home", "add", "--archive", str(user_home), "--name", "uvm")

    config = _config(isolated_home)
    assert "archive:uvm" in config["homes"]
    assert config["archives"]["uvm"] == str(user_home)


def test_add_rejects_a_folder_without_agent_history(isolated_home, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()

    result = run_cli_subprocess(
        ["home", "add", "--archive", str(empty), "--name", "nothing"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode != 0
    assert "no agent session folders" in (result.stderr + result.stdout).lower()


def test_home_list_shows_archive_homes(isolated_home, archive_root):
    _run(isolated_home, "home", "add", "--archive", str(archive_root), "--name", "uvm")

    rows = json.loads(_run(isolated_home, "home", "list", "--format", "json"))

    archive = {row["home"]: row for row in rows if row["home"].startswith("archive:")}
    assert set(archive) == {"archive:uvm-alex", "archive:uvm-adam"}
    assert all(row["type"] == "archive" for row in archive.values())


def test_workspaces_keep_their_original_paths(isolated_home, archive_root):
    _run(isolated_home, "home", "add", "--archive", str(archive_root), "--name", "uvm")

    rows = json.loads(_run(isolated_home, "ws", "--home", "archive:uvm-alex", "--format", "json"))

    assert [(row["home"], row["workspace_display"]) for row in rows] == [
        ("archive:uvm-alex", ORBIT)
    ]
    assert rows[0]["status"] == "archived"


def test_all_homes_include_archive_homes(isolated_home, archive_root):
    _run(isolated_home, "home", "add", "--archive", str(archive_root), "--name", "uvm")

    rows = json.loads(_run(isolated_home, "ws", "--ah", "--format", "json"))

    homes = {(row["home"], row["workspace_display"]) for row in rows}
    assert ("archive:uvm-alex", ORBIT) in homes
    assert ("archive:uvm-adam", NOTES) in homes


def test_stats_sync_reads_archive_sessions(isolated_home, archive_root):
    _run(isolated_home, "home", "add", "--archive", str(archive_root), "--name", "uvm")

    _run(isolated_home, "stats", "--sync", "--ah", "--aw", "--quiet")

    db = isolated_home["history_dir"] / "metrics.db"
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT home, workspace, input_tokens FROM sessions WHERE home LIKE 'archive:%'"
        ).fetchall()
    assert sorted(rows) == [
        ("archive:uvm-adam", NOTES, 10),
        ("archive:uvm-alex", ORBIT, 10),
    ]


def test_remove_drops_the_archive_home(isolated_home, archive_root):
    _run(isolated_home, "home", "add", "--archive", str(archive_root), "--name", "uvm")

    _run(isolated_home, "home", "remove", "archive:uvm-adam")

    config = _config(isolated_home)
    assert "archive:uvm-adam" not in config["homes"]
    assert "uvm-adam" not in config["archives"]
    assert "archive:uvm-alex" in config["homes"]
