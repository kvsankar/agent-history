"""A file's metrics rows are stored together or not at all.

If one of a file's rows cannot be stored, the rows already written for that
file are rolled back, so a later commit cannot keep a session row without
its messages, and the next sync reads the file again.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import pytest

from agent_history.backends.registry import get_backend, register_backend, unregister_backend
from agent_history.storage import metrics
from agent_history.storage.metrics import init_metrics_db, sync_file_to_db

FAILING = "claude-unstorable"
UNSTORABLE = 2**70


def _session_file(tmp_path: Path) -> Path:
    path = tmp_path / "projects" / "-w" / "s-1.jsonl"
    path.parent.mkdir(parents=True)
    lines = [
        {
            "type": "user",
            "sessionId": "s-1",
            "timestamp": f"2026-01-01T00:00:0{i}Z",
            "message": {"role": "user", "content": "a"},
        }
        for i in range(3)
    ]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return path


@pytest.fixture
def failing_backend(monkeypatch: pytest.MonkeyPatch):
    """The Claude backend, but its second message holds a count SQLite cannot store.

    Cleaning a reader's output would make that count 0, so the count is put
    back after cleaning, as a stand-in for any value the store refuses.
    """
    claude = get_backend("claude")
    assert claude is not None

    def extract_stats(session_file: Path):
        session_info, messages, tool_uses = claude.extract_stats(session_file)
        messages[1]["input_tokens"] = UNSTORABLE
        return session_info, messages, tool_uses

    real_clean = metrics.clean_stats_payload

    def clean_but_keep_the_unstorable_count(payload):
        cleaned = real_clean(payload)
        for original, message in zip(payload[1], cleaned[1]):
            if original.get("input_tokens") == UNSTORABLE:
                message["input_tokens"] = UNSTORABLE
        return cleaned

    monkeypatch.setattr(metrics, "clean_stats_payload", clean_but_keep_the_unstorable_count)
    register_backend(dataclasses.replace(claude, id=FAILING, extract_stats=extract_stats))
    yield FAILING
    unregister_backend(FAILING)


def _counts(conn) -> tuple[int, int]:
    sessions = conn.execute("SELECT count(*) FROM sessions").fetchone()[0]
    messages = conn.execute("SELECT count(*) FROM messages").fetchone()[0]
    return sessions, messages


def test_a_file_whose_message_cannot_be_stored_leaves_no_rows(
    tmp_path: Path, failing_backend: str
) -> None:
    session_file = _session_file(tmp_path)
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        with pytest.raises(OverflowError):
            sync_file_to_db(conn, session_file, agent=failing_backend)
        conn.commit()  # as the orchestrator does after counting the error

        assert _counts(conn) == (0, 0)
        assert sync_file_to_db(conn, session_file, agent="claude")
        assert _counts(conn) == (1, 3)
    finally:
        conn.close()


def test_a_failed_resync_keeps_the_earlier_rows_and_reads_the_file_again(
    tmp_path: Path, failing_backend: str
) -> None:
    session_file = _session_file(tmp_path)
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        assert sync_file_to_db(conn, session_file, agent="claude")
        conn.commit()
        stat = session_file.stat()
        os.utime(session_file, (stat.st_atime, stat.st_mtime + 10))

        with pytest.raises(OverflowError):
            sync_file_to_db(conn, session_file, agent=failing_backend)
        conn.commit()

        assert _counts(conn) == (1, 3)
        assert sync_file_to_db(conn, session_file, agent="claude")
    finally:
        conn.close()


def test_files_synced_together_are_committed_by_the_caller(tmp_path: Path) -> None:
    """Each file is atomic without committing it, so a sync stays one transaction."""
    session_file = _session_file(tmp_path)
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        conn.commit()
        assert sync_file_to_db(conn, session_file, agent="claude")
        assert conn.in_transaction
        conn.rollback()
        assert _counts(conn) == (0, 0)
    finally:
        conn.close()
