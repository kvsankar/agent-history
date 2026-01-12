from __future__ import annotations

from pathlib import Path

from tests.helpers.module_loader import load_agent_history


def test_token_stats_not_double_counted_for_agents(tmp_path: Path):
    """Token stats should not double-count messages across agent files sharing session_id."""
    ah = load_agent_history()
    db = tmp_path / "metrics.db"
    conn = ah.init_metrics_db(db_path=db)  # type: ignore[attr-defined]

    # Insert main and agent sessions with same session_id but different files
    conn.execute(
        """
        INSERT INTO sessions (file_path, session_id, workspace, home, source, agent, message_count)
        VALUES
        ('/tmp/main.jsonl', 'sess1', 'ws', 'local', 'local', 'claude', 2),
        ('/tmp/agent.jsonl', 'sess1', 'ws', 'local', 'local', 'claude', 1)
    """
    )
    conn.execute(
        """
        INSERT INTO messages (uuid, file_path, session_id, type, timestamp, input_tokens, output_tokens)
        VALUES
        ('m1', '/tmp/main.jsonl', 'sess1', 'assistant', '2025-01-01T00:00:00Z', 10, 5),
        ('m2', '/tmp/agent.jsonl', 'sess1', 'assistant', '2025-01-01T00:05:00Z', 3, 2)
    """
    )
    conn.commit()

    where_sql = "1=1"
    params: list[str] = []
    token_stats = ah._query_token_stats(conn, where_sql, params)  # type: ignore[attr-defined]
    assert token_stats["total_input"] == 13
    assert token_stats["total_output"] == 7

    conn.close()
