"""Transcript values that SQLite cannot hold as they are still give a stats row.

A count can be text such as "1e300" or a number beyond 64 bits, and text can
hold a lone UTF-16 surrogate, which a JSON escape can write but UTF-8 cannot encode.
Counts outside 0 to 2**53 are stored as 0, and lone surrogates as U+FFFD.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agent_history.storage import metrics
from agent_history.storage.metrics import (
    get_session_stats_from_db,
    init_metrics_db,
    sync_file_to_db,
)

LONE = "\ud800"


def _transcript(folder: Path, session_id: str, usage: dict, **fields) -> Path:
    path = folder / "-home-alex-shop" / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "type": "assistant",
        "sessionId": session_id,
        "uuid": f"{session_id}-a1",
        "timestamp": "2026-01-01T00:00:01Z",
        "cwd": "/home/alex/shop",
        "message": {"role": "assistant", "model": "model-x", "content": [], "usage": usage},
        **fields,
    }
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    return path


def test_counts_a_store_cannot_hold_are_stored_as_0(tmp_path: Path) -> None:
    path = _transcript(
        tmp_path,
        "s1",
        {"input_tokens": "1e300", "output_tokens": 2**64, "cache_read_input_tokens": 2**53},
    )
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        assert sync_file_to_db(conn, path, agent="claude")
        row = conn.execute(
            "SELECT input_tokens, output_tokens, cache_read_tokens FROM sessions"
        ).fetchone()
    finally:
        conn.close()

    assert tuple(row) == (0, 0, 2**53)


def test_text_with_lone_surrogates_is_stored_with_replacement_characters(tmp_path: Path) -> None:
    path = _transcript(
        tmp_path,
        "s1",
        {"input_tokens": 3},
        cwd=f"/home/alex/sh{LONE}op",
        gitBranch=f"ma{LONE}in",
        message={"role": "assistant", "model": f"model{LONE}", "content": [], "usage": {}},
    )
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        assert sync_file_to_db(conn, path, agent="claude")
        row = conn.execute("SELECT cwd, git_branch FROM sessions").fetchone()
        models = [r[0] for r in conn.execute("SELECT model FROM messages")]
    finally:
        conn.close()

    assert tuple(row) == ("/home/alex/sh\ufffdop", "ma\ufffdin")
    assert models == ["model\ufffd"]


def test_sessions_with_counts_beyond_2_to_the_53_still_sum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each count fits in 64 bits, but their sum would not."""
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / "config"))
    db_path = tmp_path / "metrics.db"
    conn = init_metrics_db(db_path)
    try:
        for session_id in ("s1", "s2"):
            path = _transcript(tmp_path, session_id, {"input_tokens": "5e18", "output_tokens": 7})
            assert sync_file_to_db(conn, path, agent="claude")
        conn.commit()
    finally:
        conn.close()

    summary = get_session_stats_from_db(db_path=db_path)

    assert (summary["sessions"], summary["input_tokens"], summary["output_tokens"]) == (2, 0, 14)


def test_stats_say_when_the_metrics_database_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from agent_history.handlers.stats import SessionStatsHandler

    def overflow(**kwargs):
        raise sqlite3.OperationalError("integer overflow")

    monkeypatch.setattr(metrics, "get_session_stats_from_db", overflow)

    assert SessionStatsHandler()._db_overlay_stats([]) is None
    assert "integer overflow" in capsys.readouterr().err


def test_a_timestamp_with_a_lone_surrogate_is_stored(tmp_path: Path) -> None:
    path = _transcript(tmp_path, "s1", {"input_tokens": 3}, timestamp=f"2026-01-01T00:00:01{LONE}")
    conn = init_metrics_db(tmp_path / "metrics.db")
    try:
        assert sync_file_to_db(conn, path, agent="claude")
        stamps = [r[0] for r in conn.execute("SELECT timestamp FROM messages")]
    finally:
        conn.close()

    assert stamps == ["2026-01-01T00:00:01\ufffd"]
