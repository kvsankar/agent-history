"""Work-period gap threshold behavior."""

from agent_history.storage import metrics


def test_work_period_gap_threshold_is_30_minutes():
    """Gap threshold should be 30 minutes per spec/legacy behavior."""
    assert metrics.WORK_PERIOD_GAP_THRESHOLD == 30 * 60


def test_time_stats_merge_overlapping_sessions_by_day(tmp_path):
    """Daily work time should be wall-clock union, not summed overlapping sessions."""
    db_path = tmp_path / "metrics.db"
    conn = metrics.init_metrics_db(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO sessions (
                file_path, session_id, workspace, home, source, agent,
                start_time, end_time, first_timestamp, last_timestamp,
                message_count, work_period_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "/tmp/one.jsonl",
                    "one",
                    "/tmp/ws",
                    "local",
                    "local",
                    "claude",
                    "2026-06-10T10:00:00Z",
                    "2026-06-10T11:00:00Z",
                    "2026-06-10T10:00:00Z",
                    "2026-06-10T11:00:00Z",
                    2,
                    3600,
                ),
                (
                    "/tmp/two.jsonl",
                    "two",
                    "/tmp/ws",
                    "local",
                    "local",
                    "codex",
                    "2026-06-10T10:30:00Z",
                    "2026-06-10T11:30:00Z",
                    "2026-06-10T10:30:00Z",
                    "2026-06-10T11:30:00Z",
                    2,
                    3600,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    stats = metrics.get_scoped_stats_from_db(db_path=db_path)

    assert stats["time_stats"]["by_day"]["2026-06-10"] == 5400
    assert stats["time_stats"]["total_duration_seconds"] == 5400

    rollup = metrics.get_stats_rollup_from_db(
        db_path=db_path,
        by=["day"],
        metric="time",
        sort_direction="asc",
    )
    assert rollup[0]["day"] == "2026-06-10"
    assert rollup[0]["time_seconds"] == 5400
