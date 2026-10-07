"""Windows sessions listed and parsed by cagelens running on Windows.

From WSL every file access to /mnt/c is a round trip to Windows. The Windows
side lists the sessions and parses changed files natively, writing one JSON
lines file; WSL reads that file and stores the rows under the Windows home.
"""

import json
import sys

import pytest

from agent_history.scope.types import ConcreteRecord
from agent_history.storage import metrics, windows_native


def _claude_file(root, name, workspace):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "type": "user",
            "uuid": f"{name}-u",
            "sessionId": name,
            "timestamp": "2026-03-01T10:00:00Z",
            "cwd": workspace,
            "message": {"role": "user", "content": "hi"},
        },
        {
            "type": "assistant",
            "uuid": f"{name}-a",
            "sessionId": name,
            "timestamp": "2026-03-01T10:00:05Z",
            "cwd": workspace,
            "message": {
                "id": f"msg-{name}",
                "role": "assistant",
                "model": "claude-test",
                "content": [],
                "usage": {"input_tokens": 11, "output_tokens": 3},
            },
        },
    ]
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("windows", "wsl"),
    [
        (
            r"C:\Users\alex\.claude\projects\x\s.jsonl",
            "/mnt/c/Users/alex/.claude/projects/x/s.jsonl",
        ),
        ("D:/acme/batch-1", "/mnt/d/acme/batch-1"),
        ("C:\\", "/mnt/c"),
    ],
)
def test_paths_translate_both_ways(windows, wsl):
    assert windows_native.to_wsl_path(windows) == wsl
    assert windows_native.to_wsl_path(windows_native.to_windows_path(wsl)) == wsl


def test_non_drive_values_are_left_alone():
    assert windows_native.to_wsl_path("[hash:1eeab72d]") == "[hash:1eeab72d]"
    assert windows_native.to_wsl_path("C--alex-projects-x") == "C--alex-projects-x"


def test_export_parses_only_changed_files(tmp_path):
    changed = _claude_file(tmp_path / "p", "new.jsonl", "/work/a")
    unchanged = _claude_file(tmp_path / "p", "old.jsonl", "/work/a")
    scope = [
        ConcreteRecord(
            home="local",
            workspace="/work/a",
            sessions=[
                {"file": str(changed), "agent": "claude"},
                {"file": str(unchanged), "agent": "claude"},
            ],
        )
    ]
    known = {str(unchanged): unchanged.stat().st_mtime}
    out = tmp_path / "export.jsonl"

    windows_native.export_scope(scope, known, out, jobs=1)

    lines = {
        row["file"]: row for row in map(json.loads, out.read_text(encoding="utf-8").splitlines())
    }
    assert set(lines) == {str(changed), str(unchanged)}
    assert lines[str(changed)]["record"]["session_info"]["input_tokens"] == 11
    assert lines[str(unchanged)]["record"] is None
    assert lines[str(changed)]["workspace"] == "/work/a"


def _export_line(path, workspace, record):
    return json.dumps(
        {"file": path, "agent": "claude", "workspace": workspace, "mtime": 100.0, "record": record}
    )


def test_import_builds_windows_scope_and_stores_without_reading_files(tmp_path):
    record = {
        "file_path": r"C:\Users\alex\.claude\projects\p\s.jsonl",
        "mtime": 100.0,
        "agent": "claude",
        "workspace": r"C:\alex\projects\ledger",
        "session_info": {"session_id": "s", "message_count": 2, "input_tokens": 11},
        "messages": [{"uuid": "m", "type": "assistant", "timestamp": "2026-03-01T10:00:05Z"}],
        "tool_uses": [],
        "work_seconds": 5,
        "num_periods": 1,
    }
    export = tmp_path / "export.jsonl"
    export.write_text(
        _export_line(record["file_path"], r"C:\alex\projects\ledger", record)
        + "\n"
        + _export_line(
            r"C:\Users\alex\.claude\projects\p\old.jsonl", r"C:\alex\projects\ledger", None
        )
        + "\n",
        encoding="utf-8",
    )

    scope, prepared = windows_native.read_export(export, "windows:alex")

    assert [(r.home, r.workspace) for r in scope] == [
        ("windows:alex", "/mnt/c/alex/projects/ledger")
    ]
    files = sorted(s["file"] for s in scope[0].sessions)
    assert files == [
        "/mnt/c/Users/alex/.claude/projects/p/old.jsonl",
        "/mnt/c/Users/alex/.claude/projects/p/s.jsonl",
    ]

    conn = metrics.init_metrics_db(tmp_path / "m.db")
    try:
        stats = metrics.sync_scope_to_db(conn, scope, prepared=prepared)
        rows = conn.execute(
            "SELECT file_path, home, workspace, input_tokens FROM sessions"
        ).fetchall()
    finally:
        conn.close()
    assert stats == {"synced": 1, "skipped": 1, "errors": 0}
    assert [tuple(row) for row in rows] == [
        (
            "/mnt/c/Users/alex/.claude/projects/p/s.jsonl",
            "windows:alex",
            "/mnt/c/alex/projects/ledger",
            11,
        )
    ]


def test_known_mtimes_come_from_current_rows_as_windows_paths(tmp_path):
    conn = metrics.init_metrics_db(tmp_path / "m.db")
    try:
        metrics._store_file_stats(
            conn,
            {
                "file_path": "/mnt/c/Users/alex/.claude/projects/p/s.jsonl",
                "mtime": 123.0,
                "agent": "claude",
                "workspace": "/mnt/c/x",
                "session_info": {},
                "messages": [],
                "tool_uses": [],
                "work_seconds": 0,
                "num_periods": 1,
            },
            "windows:alex",
        )
        known = windows_native.known_mtimes(conn, "windows:alex")
    finally:
        conn.close()

    assert known == {r"C:\Users\alex\.claude\projects\p\s.jsonl": 123.0}


def test_run_export_invokes_the_windows_command_and_reads_its_output(tmp_path):
    """The command receives Windows paths for its input and output files."""
    script = tmp_path / "fake_windows.py"
    script.write_text(
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "known = args[args.index('--known') + 1]\n"
        "out = args[args.index('--out') + 1]\n"
        "assert json.load(open(known)) == {}\n"
        "open(out, 'w').write(json.dumps({'file': 'C:\\\\a\\\\s.jsonl', 'agent': 'claude', "
        "'workspace': 'C:\\\\a', 'mtime': 1.0, 'record': None}) + '\\n')\n",
        encoding="utf-8",
    )
    lines = windows_native.run_export(
        [sys.executable, str(script)],
        known={},
        work_dir=tmp_path / "exchange",
        to_windows=str,
    )

    assert [line["file"] for line in lines] == ["C:\\a\\s.jsonl"]


def test_interop_socket_is_found_when_the_environment_lacks_it(tmp_path):
    """Processes started over SSH have no WSL_INTEROP, so Windows programs fail."""
    run_dir = tmp_path / "run" / "WSL"
    run_dir.mkdir(parents=True)
    old = run_dir / "1_interop"
    new = run_dir / "809948_interop"
    old.touch()
    new.touch()
    import os

    os.utime(old, (1, 1))

    env = windows_native.interop_env({}, run_dir)
    assert env["WSL_INTEROP"] == str(new)
    assert windows_native.interop_env({"WSL_INTEROP": "/x"}, run_dir)["WSL_INTEROP"] == "/x"
    assert "WSL_INTEROP" not in windows_native.interop_env({}, tmp_path / "missing")


def test_extended_length_prefix_is_dropped():
    """Windows reports some folders as \\\\?\\C:\\..., which must match plain C:\\..."""
    assert windows_native.to_wsl_path("\\\\?\\C:\\alex\\projects\\sample-project") == (
        "/mnt/c/alex/projects/sample-project"
    )
