"""Estimated API cost in DB-backed stats and rollups."""

import json

import pytest

from agent_history import pricing
from agent_history.pricing import PriceTable
from agent_history.storage import metrics

PRICES = PriceTable(
    {
        "claude-test": [{"from": "2026-01-01", "input": 1e-06, "output": 10e-06}],
        "gpt-test": [
            {"from": "2026-01-01", "input": 2e-06, "output": 20e-06, "cache_read": 0.2e-06}
        ],
    }
)

CLAUDE_COST = 1000 * 1e-06 + 100 * 10e-06
# Codex input includes the 400 cached tokens.
CODEX_COST = 600 * 2e-06 + 400 * 0.2e-06 + 50 * 20e-06
UNPRICED_TOKENS = 70


@pytest.fixture(autouse=True)
def _test_prices(monkeypatch):
    monkeypatch.setattr(pricing, "load_price_table", lambda: PRICES)


def _write_jsonl(path, entries):
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    return path


def _claude_entry(uuid, entry_type, model=None, usage=None):
    message = {"role": entry_type, "content": []}
    if model:
        message["model"] = model
        message["id"] = f"msg-{uuid}"
    if usage:
        message["usage"] = usage
    return {
        "type": entry_type,
        "uuid": uuid,
        "sessionId": "s-1",
        "timestamp": "2026-09-10T10:00:00Z",
        "cwd": "/home/user/project",
        "message": message,
    }


def _codex_session(path):
    usage = {
        "input_tokens": 1000,
        "cached_input_tokens": 400,
        "output_tokens": 50,
        "reasoning_output_tokens": 0,
        "total_tokens": 1050,
    }
    return _write_jsonl(
        path,
        [
            {
                "type": "session_meta",
                "timestamp": "2026-09-10T11:00:00Z",
                "payload": {"id": "c-1", "cwd": "/home/user/project", "cli_version": "1.0"},
            },
            {
                "type": "turn_context",
                "timestamp": "2026-09-10T11:00:01Z",
                "payload": {"model": "gpt-test"},
            },
            {
                "type": "response_item",
                "timestamp": "2026-09-10T11:00:02Z",
                "payload": {"type": "message", "role": "user", "content": []},
            },
            {
                "type": "response_item",
                "timestamp": "2026-09-10T11:00:03Z",
                "payload": {"type": "message", "role": "assistant", "content": []},
            },
            {
                "type": "event_msg",
                "timestamp": "2026-09-10T11:00:04Z",
                "payload": {
                    "type": "token_count",
                    "info": {"total_token_usage": usage, "last_token_usage": usage},
                },
            },
        ],
    )


@pytest.fixture
def db_path(tmp_path):
    claude_file = _write_jsonl(
        tmp_path / "s-1.jsonl",
        [
            _claude_entry("u-1", "user"),
            _claude_entry(
                "a-1", "assistant", "claude-test", {"input_tokens": 1000, "output_tokens": 100}
            ),
            _claude_entry(
                "a-2", "assistant", "claude-unknown", {"input_tokens": 50, "output_tokens": 20}
            ),
        ],
    )
    codex_file = _codex_session(tmp_path / "rollout.jsonl")

    path = tmp_path / "metrics.db"
    conn = metrics.init_metrics_db(path)
    try:
        metrics.sync_file_to_db(conn, claude_file, workspace="project-a", agent="claude")
        metrics.sync_file_to_db(conn, codex_file, workspace="project-b", agent="codex")
        conn.commit()
    finally:
        conn.close()
    return path


def test_scoped_stats_report_estimated_cost_and_unpriced_messages(db_path):
    stats = metrics.get_scoped_stats_from_db(db_path=db_path)

    assert stats["cost"]["usd"] == pytest.approx(CLAUDE_COST + CODEX_COST)
    assert stats["cost"]["unpriced_messages"] == 1
    assert stats["cost"]["unpriced_tokens"] == UNPRICED_TOKENS
    assert stats["cost"]["unpriced_models"] == ["claude-unknown"]


def test_model_breakdown_carries_cost(db_path):
    by_model = metrics.get_scoped_stats_from_db(db_path=db_path)["by_model"]

    assert by_model["claude-test"]["cost_usd"] == pytest.approx(CLAUDE_COST)
    assert by_model["gpt-test"]["cost_usd"] == pytest.approx(CODEX_COST)
    assert by_model["claude-unknown"]["cost_usd"] is None


def test_session_rollup_carries_cost(db_path):
    rows = metrics.get_stats_rollup_from_db(db_path=db_path, by=["agent"], metric="cost")

    cost = {row["agent"]: row["cost_usd"] for row in rows}
    assert cost == pytest.approx({"claude": CLAUDE_COST, "codex": CODEX_COST})
    assert [row["agent"] for row in rows] == ["codex", "claude"]


def test_model_rollup_carries_cost(db_path):
    rows = metrics.get_stats_rollup_from_db(db_path=db_path, by=["model"], metric="cost")

    cost = {row["model"]: row["cost_usd"] for row in rows}
    assert cost["claude-test"] == pytest.approx(CLAUDE_COST)
    assert cost["gpt-test"] == pytest.approx(CODEX_COST)
    assert rows[0]["model"] == "gpt-test"


def test_rollup_rows_count_unpriced_tokens(db_path):
    rows = metrics.get_stats_rollup_from_db(db_path=db_path, by=["agent"], metric="all")

    unpriced = {row["agent"]: row["unpriced_tokens"] for row in rows}
    assert unpriced == {"claude": UNPRICED_TOKENS, "codex": 0}


def test_rollup_can_sort_by_cost(db_path):
    rows = metrics.get_stats_rollup_from_db(
        db_path=db_path, by=["agent"], metric="all", sort_by=["cost"], sort_direction="asc"
    )

    assert [row["agent"] for row in rows] == ["claude", "codex"]


def test_file_scoped_stats_carry_cost(db_path):
    """The stats overlay reads totals for the sessions resolved in scope."""
    conn = metrics.init_metrics_db(db_path)
    try:
        claude_path = conn.execute(
            "SELECT file_path FROM sessions WHERE agent = 'claude'"
        ).fetchone()["file_path"]
    finally:
        conn.close()

    stats = metrics.get_session_stats_from_db(db_path=db_path, file_paths=[claude_path])

    assert stats["cost"]["usd"] == pytest.approx(CLAUDE_COST)
    assert stats["cost"]["unpriced_models"] == ["claude-unknown"]
    assert stats["by_model"]["claude-test"]["cost_usd"] == pytest.approx(CLAUDE_COST)
    assert "gpt-test" not in stats["by_model"]
