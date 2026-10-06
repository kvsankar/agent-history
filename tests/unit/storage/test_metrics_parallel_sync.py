"""Syncing with several worker processes stores the same rows as syncing serially."""

import json

import pytest

from agent_history.scope.types import ConcreteRecord
from agent_history.storage import metrics

SESSIONS = 12


def _claude_file(root, n):
    workspace = f"/home/user/projects/p{n % 3}"
    path = root / workspace.replace("/", "-") / f"s-{n}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "type": "user",
            "uuid": f"u-{n}",
            "sessionId": f"s-{n}",
            "timestamp": f"2026-03-0{1 + n % 9}T10:00:00Z",
            "cwd": workspace,
            "message": {"role": "user", "content": "hi"},
        },
        {
            "type": "assistant",
            "uuid": f"a-{n}",
            "sessionId": f"s-{n}",
            "timestamp": f"2026-03-0{1 + n % 9}T10:00:09Z",
            "cwd": workspace,
            "message": {
                "id": f"msg-{n}",
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "tool_use", "id": f"t-{n}", "name": "Read", "input": {}}],
                "usage": {"input_tokens": 10 + n, "output_tokens": n},
            },
        },
    ]
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return path, workspace


def _scope(root):
    records = {}
    for n in range(SESSIONS):
        path, workspace = _claude_file(root, n)
        records.setdefault(workspace, []).append({"file": str(path), "agent": "claude"})
    return [
        ConcreteRecord(home="local", workspace=workspace, sessions=sessions)
        for workspace, sessions in records.items()
    ]


def _rows(conn):
    return {
        "sessions": conn.execute(
            "SELECT file_path, workspace, home, agent, message_count, input_tokens, "
            "output_tokens, start_time, end_time, work_period_seconds, stats_format "
            "FROM sessions ORDER BY file_path"
        ).fetchall(),
        "messages": conn.execute(
            "SELECT file_path, uuid, type, model, input_tokens, output_tokens "
            "FROM messages ORDER BY file_path, uuid"
        ).fetchall(),
        "tools": conn.execute(
            "SELECT file_path, tool_name FROM tool_uses ORDER BY file_path"
        ).fetchall(),
    }


def _sync(tmp_path, scope, name, jobs):
    conn = metrics.init_metrics_db(tmp_path / f"{name}.db")
    stats = metrics.sync_scope_to_db(conn, scope, jobs=jobs)
    conn.commit()
    return conn, stats


@pytest.fixture
def scope(tmp_path):
    return _scope(tmp_path / "projects")


def test_parallel_sync_matches_serial_sync(tmp_path, scope):
    serial, serial_stats = _sync(tmp_path, scope, "serial", jobs=1)
    parallel, parallel_stats = _sync(tmp_path, scope, "parallel", jobs=4)
    try:
        assert serial_stats == parallel_stats == {"synced": SESSIONS, "skipped": 0, "errors": 0}
        assert _rows(parallel) == _rows(serial)
    finally:
        serial.close()
        parallel.close()


def test_parallel_sync_skips_unchanged_files(tmp_path, scope):
    conn, _stats = _sync(tmp_path, scope, "db", jobs=4)
    try:
        again = metrics.sync_scope_to_db(conn, scope, jobs=4)
        assert again == {"synced": 0, "skipped": SESSIONS, "errors": 0}
    finally:
        conn.close()


def test_unreadable_file_counts_as_an_error(tmp_path, scope):
    broken = tmp_path / "broken.jsonl"
    broken.write_bytes(b"\xff\xfe not utf-8\n")
    scope[0].sessions.append({"file": str(broken), "agent": "claude"})

    conn, stats = _sync(tmp_path, scope, "db", jobs=4)
    try:
        assert stats == {"synced": SESSIONS, "skipped": 0, "errors": 1}
    finally:
        conn.close()


def test_default_jobs_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("CAGELENS_SYNC_JOBS", "3")
    assert metrics.default_sync_jobs() == 3
    monkeypatch.setenv("CAGELENS_SYNC_JOBS", "not-a-number")
    assert metrics.default_sync_jobs() >= 1
