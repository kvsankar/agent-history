from __future__ import annotations

from agent_history.output.formatter import TableFormatter, TsvFormatter


def test_stats_workspace_display_map_used_in_table() -> None:
    formatter = TableFormatter(width=120)
    stats = {
        "sessions": 1,
        "messages": 2,
        "total_sessions": 1,
        "total_messages": 2,
        "by_workspace": {"abc123def456": {"sessions": 1}},
    }
    metadata = {
        "group_by": ["workspace"],
        "workspace_display_map": {"abc123def456": "/home/user/project"},
    }

    output = formatter.format(stats, "stats", metadata)
    assert "/home/user/project" in output
    assert "abc123def456" not in output


def test_stats_table_shows_workspace_glob_scope() -> None:
    formatter = TableFormatter(width=120)
    stats = {
        "sessions": 7,
        "messages": 1602,
        "total_sessions": 7,
        "total_messages": 1602,
        "by_agent": {"claude": {"sessions": 7}},
        "by_home": {"local": {"sessions": 7}},
        "by_workspace": {
            "bptrial-main": {"sessions": 5},
            "/home/sankar/sankar/projects/bptrial-main": {"sessions": 1},
            "bptrial-mobile": {"sessions": 1},
        },
    }
    metadata = {
        "homes": ["local"],
        "workspaces": [
            "bptrial-main",
            "/home/sankar/sankar/projects/bptrial-main",
            "bptrial-mobile",
        ],
        "scope_request": {"type": "workspace_glob", "values": ["*bptrial*"]},
    }

    output = formatter.format(stats, "stats", metadata)

    assert "Scope:" in output
    assert "Request: workspace glob *bptrial*" in output
    assert "Homes: 1 (local)" in output
    assert "Workspaces: 3 (bptrial-main" in output
    assert "Sessions: 7" in output


def test_stats_table_shows_project_scope() -> None:
    formatter = TableFormatter(width=120)
    stats = {
        "sessions": 2,
        "messages": 20,
        "total_sessions": 2,
        "total_messages": 20,
        "by_agent": {"claude": {"sessions": 2}},
        "by_home": {"local": {"sessions": 2}},
        "by_workspace": {"/tmp/project": {"sessions": 2}},
    }
    metadata = {
        "homes": ["local"],
        "workspaces": ["/tmp/project"],
        "scope_request": {"type": "project", "values": ["bptrial"]},
    }

    output = formatter.format(stats, "stats", metadata)

    assert "Request: project bptrial" in output
    assert "workspace glob" not in output


def test_stats_table_surfaces_dashboard_metrics_and_truncation_hint() -> None:
    formatter = TableFormatter(width=120)
    stats = {
        "sessions": 3,
        "messages": 12,
        "total_sessions": 3,
        "total_messages": 12,
        "main_sessions": 2,
        "agent_sessions": 1,
        "user_messages": 5,
        "assistant_messages": 7,
        "tokens": {
            "input": 1000,
            "output": 250,
            "cache_read": 100,
            "cache_creation": 50,
        },
        "by_agent": {"claude": {"sessions": 2}, "codex": {"sessions": 1}},
        "by_home": {"local": {"sessions": 3}},
        "by_workspace": {
            "/tmp/alpha": {"sessions": 2},
            "/tmp/beta": {"sessions": 1},
        },
        "by_tool": {"Read": {"uses": 4, "errors": 1}},
        "by_model": {"claude-sonnet": {"messages": 7, "tokens": 250}},
        "time_stats": {
            "total_duration_seconds": 3600,
            "average_duration_seconds": 1800,
            "sessions_with_time": 2,
            "by_day": {"2026-06-01": 3600},
        },
    }
    metadata = {
        "top_ws": 1,
        "human": True,
        "include_time": True,
        "sync_stats": {"errors": 1},
    }

    output = formatter.format(stats, "stats", metadata)

    assert "Session Types: main 2, agent 1" in output
    assert "Message Types: user 5, assistant 7" in output
    assert "Tokens: input 1K, output 250" in output
    assert "Tools: 4 uses, 1 errors" in output
    assert "Models: 1 (claude-sonnet)" in output
    assert "Time: total 1h" in output
    assert "Time by Day:" in output
    assert "2026-06-01: 1h" in output
    assert "... and 1 more (use --top-ws all or --format json)" in output
    assert "Metric Coverage:" in output
    assert "summarized: sessions, messages, tokens, tools, models, time" in output
    assert "--models for per-model messages/tokens" in output
    assert "--tools for per-tool uses/errors" in output
    assert "--time for time by day" in output
    assert "--by-day for session/message counts by day" in output
    assert "--sync --force to retry failed metric syncs" in output


def test_stats_tsv_includes_summary_tokens_and_breakdowns() -> None:
    formatter = TsvFormatter()
    stats = {
        "sessions": 1,
        "messages": 2,
        "total_sessions": 1,
        "total_messages": 2,
        "tokens": {"input": 10, "output": 5, "cache_read": 0, "cache_creation": 0},
        "by_workspace": {"hash": {"sessions": 1, "messages": 2}},
    }
    metadata = {"workspace_display_map": {"hash": "/tmp/project"}}

    output = formatter.format(stats, "stats", metadata)

    assert output.splitlines()[0] == "SECTION\tNAME\tSESSIONS\tMESSAGES\tVALUE\tEXTRA"
    assert "summary\ttotal\t1\t2\t\t" in output
    assert "token\tinput\t\t\t10\t" in output
    assert "workspace\t/tmp/project\t1\t2\t1\t" in output


def test_stats_guidance_handles_missing_sync_stats() -> None:
    formatter = TableFormatter(width=120)
    stats = {
        "sessions": 1,
        "messages": 2,
        "total_sessions": 1,
        "total_messages": 2,
        "by_agent": {"claude": {"sessions": 1}},
        "by_home": {"local": {"sessions": 1}},
        "by_workspace": {"/tmp/project": {"sessions": 1}},
    }

    output = formatter.format(stats, "stats", {"sync_stats": None})

    assert "Metric Coverage:" in output
    assert "--format json for the full metrics payload" in output


def test_stats_rollup_table_formats_dimensions_and_metric_columns() -> None:
    formatter = TableFormatter(width=120)
    rows = [
        {
            "project": "cagelens",
            "month": "2026-06",
            "time_hours": 1.5,
            "time_seconds": 5400,
        }
    ]
    metadata = {
        "dimensions": ["project", "month"],
        "metric": "time",
        "homes": ["local"],
        "workspaces": ["/tmp/project"],
        "scope_request": {"type": "current_workspace", "values": ["/tmp/project"]},
        "total_sessions": 1,
    }

    output = formatter.format(rows, "stats_rollup", metadata)

    assert "Scope:" in output
    assert "Request: current workspace /tmp/project" in output
    assert "PROJECT" in output
    assert "MONTH" in output
    assert "TIME_HOURS" in output
    assert "TIME_SECONDS" in output
    assert "cagelens" in output
    assert "2026-06" in output
    assert "1.50" in output
    assert "5400" in output


def test_stats_rollup_tsv_formats_token_columns() -> None:
    formatter = TsvFormatter()
    rows = [
        {
            "workspace": "/tmp/project",
            "model": "claude-test",
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 2,
        }
    ]
    metadata = {"dimensions": ["workspace", "model"], "metric": "tokens"}

    output = formatter.format(rows, "stats_rollup", metadata)

    assert output.splitlines() == [
        "WORKSPACE\tMODEL\tINPUT_TOKENS\tOUTPUT_TOKENS\tCACHE_READ\tCACHE_CREATE",
        "/tmp/project\tclaude-test\t10\t5\t3\t2",
    ]
