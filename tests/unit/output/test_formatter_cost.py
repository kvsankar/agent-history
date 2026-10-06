"""Estimated API cost in stats output."""

from __future__ import annotations

from agent_history.output.formatter import TableFormatter, TsvFormatter


def _stats(cost):
    return {
        "sessions": 2,
        "messages": 4,
        "total_sessions": 2,
        "total_messages": 4,
        "tokens": {"input": 10, "output": 5, "cache_read": 0, "cache_creation": 0},
        "cost": cost,
        "by_model": {
            "claude-test": {"messages": 2, "tokens": 5, "cost_usd": 1234.5},
            "claude-unknown": {"messages": 1, "tokens": 3, "cost_usd": None},
        },
    }


PRICED = {"usd": 1234.5, "unpriced_messages": 0, "unpriced_tokens": 0, "unpriced_models": []}
PARTLY_PRICED = {
    "usd": 1234.5,
    "unpriced_messages": 1,
    "unpriced_tokens": 70,
    "unpriced_models": ["claude-unknown"],
}


def test_table_dashboard_shows_estimated_cost():
    output = TableFormatter(width=120).format(_stats(PRICED), "stats", {})

    assert "Estimated API cost: $1,234.50 (at API list prices)" in output


def test_table_dashboard_names_models_it_could_not_price():
    output = TableFormatter(width=120).format(_stats(PARTLY_PRICED), "stats", {})

    assert "Estimated API cost: $1,234.50 (at API list prices)" in output
    assert "Not priced: 70 tokens in 1 messages (claude-unknown)" in output


def test_table_model_breakdown_shows_cost():
    output = TableFormatter(width=120).format(_stats(PRICED), "stats", {"group_by": ["model"]})

    assert "claude-test: 2 messages, 5 tokens, $1,234.50" in output
    assert "claude-unknown: 1 messages, 3 tokens, not priced" in output


def test_tsv_reports_cost_record():
    output = TsvFormatter().format(_stats(PARTLY_PRICED), "stats", {})

    assert "cost\tusd\t\t\t1234.50\t" in output
    assert "cost\tunpriced_tokens\t\t\t70\tclaude-unknown" in output


def test_stats_without_cost_data_show_no_cost_line():
    stats = _stats(PRICED)
    del stats["cost"]

    output = TableFormatter(width=120).format(stats, "stats", {})

    assert "Estimated API cost" not in output


def test_cost_rollup_tsv_columns_and_total():
    rows = [
        {"month": "2026-01", "cost_usd": 10.5, "unpriced_tokens": 0, "share": 10.5 / 12.75},
        {"month": "2026-02", "cost_usd": 2.25, "unpriced_tokens": 70, "share": 2.25 / 12.75},
    ]
    metadata = {
        "dimensions": ["month"],
        "metric": "cost",
        "total": True,
        "scope_totals": {"cost_usd": 12.75, "unpriced_tokens": 70},
    }

    output = TsvFormatter().format(rows, "stats_rollup", metadata)

    assert output.splitlines() == [
        "MONTH\tCOST_USD\tUNPRICED_TOKENS\tSHARE",
        "2026-01\t10.50\t0\t82.4%",
        "2026-02\t2.25\t70\t17.6%",
        "TOTAL\t12.75\t70\t100.0%",
    ]


def test_all_metric_rollup_includes_cost_column():
    rows = [
        {
            "agent": "codex",
            "time_seconds": 60,
            "input_tokens": 1,
            "output_tokens": 2,
            "cost_usd": 3.0,
            "sessions": 1,
            "messages": 2,
        }
    ]
    metadata = {"dimensions": ["agent"], "metric": "all"}

    lines = TsvFormatter().format(rows, "stats_rollup", metadata).splitlines()

    assert lines[0].split("\t")[-3:] == ["COST_USD", "SESSIONS", "MESSAGES"]
    assert lines[1].split("\t")[-3:] == ["3.00", "1", "2"]
