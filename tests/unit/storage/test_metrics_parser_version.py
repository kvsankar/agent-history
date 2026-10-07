"""Rows written by an older transcript parser are parsed again."""

import json

from agent_history.storage import metrics
from agent_history.storage.metrics import init_metrics_db, sync_file_to_db


def _session_file(tmp_path):
    session = tmp_path / "s-1.jsonl"
    entries = [
        {
            "type": "user",
            "uuid": "u-1",
            "sessionId": "s-1",
            "timestamp": "2026-05-01T04:29:02.000Z",
            "cwd": "/home/alex/project",
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


def _downgrade_to_version_7(db_path):
    """Make the database look as the previous release left it."""
    conn = init_metrics_db(db_path)
    try:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(sessions)")]
        if "parser_version" in columns:
            conn.execute("ALTER TABLE sessions DROP COLUMN parser_version")
        conn.execute("UPDATE schema_version SET version = 7")
        conn.commit()
    finally:
        conn.close()


def test_rows_from_a_version_7_database_are_parsed_again(tmp_path):
    """Version 7 rows hold the old parser's values and an up-to-date mtime."""
    session_file = _session_file(tmp_path)
    db_path = tmp_path / "metrics.db"
    conn = init_metrics_db(db_path)
    try:
        assert sync_file_to_db(conn, session_file, workspace="ws")
        conn.execute("UPDATE sessions SET session_id = 'old-parser-id', cwd = NULL")
        conn.commit()
    finally:
        conn.close()
    _downgrade_to_version_7(db_path)

    conn = init_metrics_db(db_path)
    try:
        assert sync_file_to_db(conn, session_file, workspace="ws")
        row = conn.execute("SELECT session_id, cwd FROM sessions").fetchone()
    finally:
        conn.close()

    assert (row["session_id"], row["cwd"]) == ("s-1", "/home/alex/project")


def test_rows_from_an_older_parser_version_are_parsed_again(tmp_path, monkeypatch):
    session_file = _session_file(tmp_path)
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        assert sync_file_to_db(conn, session_file, workspace="ws")
        assert not sync_file_to_db(conn, session_file, workspace="ws")

        monkeypatch.setattr(metrics, "METRICS_PARSER_VERSION", metrics.METRICS_PARSER_VERSION + 1)

        assert sync_file_to_db(conn, session_file, workspace="ws")
        assert not sync_file_to_db(conn, session_file, workspace="ws")
    finally:
        conn.close()
