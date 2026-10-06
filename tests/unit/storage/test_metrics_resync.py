"""Rows written by an older cagelens are re-derived on the next sync."""

import json

from agent_history.storage import metrics


def _session_file(tmp_path):
    path = tmp_path / "-home-user-projects-swdev-with-ai" / "s-1.jsonl"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "type": "user",
                "uuid": "u-1",
                "sessionId": "s-1",
                "timestamp": "2026-04-21T10:00:00Z",
                "cwd": "/home/user/projects/swdev-with-ai",
                "message": {"role": "user", "content": "hello"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _sync(conn, path):
    synced = metrics.sync_file_to_db(conn, path, agent="claude")
    conn.commit()
    return synced


def _workspace(conn, path):
    return conn.execute(
        "SELECT workspace FROM sessions WHERE file_path = ?", (str(path),)
    ).fetchone()["workspace"]


def test_unchanged_file_from_an_older_format_is_synced_again(tmp_path):
    """An older cagelens stored a short workspace name such as 'with-ai'."""
    path = _session_file(tmp_path)
    conn = metrics.init_metrics_db(tmp_path / "metrics.db")
    try:
        assert _sync(conn, path)
        current = _workspace(conn, path)
        conn.execute(
            "UPDATE sessions SET workspace = 'with-ai', stats_format = 0 WHERE file_path = ?",
            (str(path),),
        )
        conn.commit()

        assert _sync(conn, path)
        assert _workspace(conn, path) == current
    finally:
        conn.close()


def test_unchanged_file_in_the_current_format_is_skipped(tmp_path):
    path = _session_file(tmp_path)
    conn = metrics.init_metrics_db(tmp_path / "metrics.db")
    try:
        assert _sync(conn, path)
        assert not _sync(conn, path)
    finally:
        conn.close()


def test_database_from_an_older_cagelens_gains_the_format_column(tmp_path):
    """Older databases lack the column; every row then counts as outdated."""
    path = _session_file(tmp_path)
    db = tmp_path / "metrics.db"
    conn = metrics.init_metrics_db(db)
    try:
        assert _sync(conn, path)
        conn.execute("ALTER TABLE sessions DROP COLUMN stats_format")
        conn.commit()
    finally:
        conn.close()

    conn = metrics.init_metrics_db(db)
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
        assert "stats_format" in columns
        assert conn.execute("SELECT stats_format FROM sessions").fetchone()[0] == 0
    finally:
        conn.close()
