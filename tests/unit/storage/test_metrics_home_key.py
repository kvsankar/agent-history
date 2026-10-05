"""A stats sync records the home of the scope that syncs the file."""

import json

from agent_history.storage.metrics import init_metrics_db, sync_file_to_db


def _session_file(tmp_path):
    session = tmp_path / "session.jsonl"
    entries = [
        {
            "type": "user",
            "uuid": "u-1",
            "sessionId": "s-1",
            "timestamp": "2026-05-01T04:29:02.000Z",
            "cwd": "/mnt/c/projects/app",
            "message": {"role": "user", "content": "hello"},
        },
        {
            "type": "assistant",
            "uuid": "a-1",
            "sessionId": "s-1",
            "timestamp": "2026-05-01T04:29:05.000Z",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
        },
    ]
    session.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return session


def test_unchanged_file_synced_from_another_home_takes_that_home(tmp_path):
    """The same Windows file reached as "windows" and as "windows:alice" must not split.

    Before, a sync skipped any file whose modification time had not changed,
    so the home recorded on its first sync stayed forever. Main sessions and
    their sub-agent files then sat under different home names, and a rollup
    for one home missed the others.
    """
    session_file = _session_file(tmp_path)
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        assert sync_file_to_db(conn, session_file, source_key="windows:alice", workspace="ws")
        assert sync_file_to_db(conn, session_file, source_key="windows", workspace="ws")
        homes = [row["home"] for row in conn.execute("SELECT home FROM sessions")]
    finally:
        conn.close()

    assert homes == ["windows"]


def test_unchanged_file_from_the_same_home_is_still_skipped(tmp_path):
    session_file = _session_file(tmp_path)
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        assert sync_file_to_db(conn, session_file, source_key="windows", workspace="ws")
        assert not sync_file_to_db(conn, session_file, source_key="windows", workspace="ws")
    finally:
        conn.close()
