from __future__ import annotations

from agent_history.handlers.base import CommandResult
from agent_history.output.formatter import OutputFormatter, TableFormatter, TsvFormatter
from agent_history.scope.context import OutputArgs


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
    assert "Workspaces: 3\n" in output
    assert "    - bptrial-main\n" in output
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
            "total_sessions": 3,
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
    assert "Models: 1 (top by messages: claude-sonnet)" in output
    assert "Time: observed total 1h 0s, avg timed session 30m 0s, coverage 2/3 sessions" in output
    assert "Time by Day:" in output
    assert "2026-06-01: 1h 0s" in output
    assert "... and 1 more (use --top-ws all or --format json)" in output
    assert "Metric Coverage:" in output
    assert "summarized: sessions, messages, tokens, tools, models, time" in output
    assert "--models for per-model messages/tokens" in output
    assert "--tools for per-tool uses/errors" in output


def test_stats_table_makes_partial_time_coverage_explicit() -> None:
    formatter = TableFormatter(width=120)
    stats = {
        "sessions": 68,
        "total_sessions": 68,
        "messages": 219,
        "time_stats": {
            "total_duration_seconds": 7397,
            "average_duration_seconds": 7397,
            "sessions_with_time": 1,
            "total_sessions": 68,
            "by_day": {},
        },
    }

    output = formatter.format(stats, "stats", {"top_ws": 10})

    assert (
        "Time: observed total 2h 3m 17s, avg timed session 2h 3m 17s, coverage 1/68 sessions"
        in output
    )
    assert "--time for time by day" in output
    assert "--by-day for session/message counts by day" in output


def test_stats_table_human_duration_includes_seconds_component() -> None:
    formatter = TableFormatter(width=120)
    stats = {
        "sessions": 1,
        "total_sessions": 1,
        "messages": 1,
        "time_stats": {
            "total_duration_seconds": 93784,
            "average_duration_seconds": 93784,
            "sessions_with_time": 1,
            "total_sessions": 1,
            "by_day": {"2026-06-01": 93784},
        },
    }

    output = formatter.format(stats, "stats", {"human": True, "include_time": True})

    assert "observed total 26h 3m 4s" in output
    assert "2026-06-01: 26h 3m 4s" in output


def test_project_table_outputs_include_workspace_totals() -> None:
    formatter = TableFormatter(width=120)

    details = formatter.format(
        {
            "project": "bptrial",
            "total_workspaces": 19,
            "total_sessions": 509,
            "workspaces_by_home": {},
        },
        "project_details",
        {},
    )
    update = formatter.format(
        {
            "project": "bptrial",
            "dry_run": False,
            "added": 3,
            "existing": 0,
            "project_workspaces": 19,
            "resolved_workspaces": [],
        },
        "project_update",
        {},
    )

    assert "Total Workspaces: 19" in details
    assert "Project Workspaces: 19 workspace(s)" in update


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
            "time_hms": "1h 30m 0s",
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
    assert "TIME_HMS" in output
    assert "TIME_HOURS" in output
    assert "TIME_SECONDS" in output
    assert "cagelens" in output
    assert "2026-06" in output
    assert "1h 30m 0s" in output
    assert "1.50" in output
    assert "5400" in output


def test_stats_rollup_table_empty_rows_shows_message() -> None:
    formatter = TableFormatter(width=120)

    output = formatter.format([], "stats_rollup", {"dimensions": ["month"], "metric": "time"})

    assert output == "No cached stats matched this scope. Run with --sync to refresh."


def test_output_formatter_does_not_suppress_empty_stats_rollup(capsys) -> None:
    result = CommandResult(
        success=True,
        data=[],
        data_type="stats_rollup",
        metadata={"dimensions": ["month"], "metric": "time"},
        warnings=["Using cached metrics. Run with `--sync` to refresh from source files."],
    )

    OutputFormatter().format(result, OutputArgs(format="table"))

    captured = capsys.readouterr()
    assert "No cached stats matched this scope" in captured.out
    assert "Using cached metrics" in captured.err


def test_stats_rollup_scope_workspaces_use_multiline_summary() -> None:
    formatter = TableFormatter(width=120)
    rows = [{"month": "2026-06", "time_hms": "1h 30m 0s", "time_hours": 1.5, "time_seconds": 5400}]
    metadata = {
        "dimensions": ["month"],
        "metric": "time",
        "homes": ["local", "windows:kvsan"],
        "workspaces": [
            "/home/sankar/sankar/projects/auth",
            "/home/sankar/sankar/projects/auth-infra-test-tagging",
            "/home/sankar/sankar/projects/auth/docs",
            "/home/sankar/sankar/projects/auth/docs/consolidation",
            "/home/sankar/sankar/projects/auth/infra",
        ],
        "scope_request": {"type": "project", "values": ["bptrial"]},
        "total_sessions": 571,
    }

    output = formatter.format(rows, "stats_rollup", metadata)

    assert "Workspaces: 5\n" in output
    assert "    - /home/sankar/sankar/projects/auth\n" in output
    assert "    - ... 1 more\n" in output
    assert "Workspaces: 5 (/home" not in output


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


def test_stats_rollup_table_human_formats_token_columns() -> None:
    formatter = TableFormatter(width=120)
    rows = [
        {
            "workspace": "/tmp/project",
            "month": "2026-06",
            "input_tokens": 146_441,
            "output_tokens": 891_487,
            "cache_read_tokens": 600_132_653,
            "cache_creation_tokens": 24_403_179,
        }
    ]
    metadata = {"dimensions": ["workspace", "month"], "metric": "tokens", "human": True}

    output = formatter.format(rows, "stats_rollup", metadata)

    assert "146.4K" in output
    assert "891.5K" in output
    assert "600.1M" in output
    assert "24.4M" in output
    assert "600132653" not in output


def test_stats_rollup_table_can_append_total_row_and_separator() -> None:
    formatter = TableFormatter(width=120)
    rows = [
        {
            "month": "2026-01",
            "time_hms": "1h 0m 0s",
            "time_hours": 1.0,
            "time_seconds": 3600,
            "input_tokens": 1_000,
            "output_tokens": 2_000,
            "cache_read_tokens": 3_000,
            "cache_creation_tokens": 4_000,
            "sessions": 1,
            "messages": 2,
        },
        {
            "month": "2026-02",
            "time_hms": "0h 30m 0s",
            "time_hours": 0.5,
            "time_seconds": 1800,
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_read_tokens": 30,
            "cache_creation_tokens": 40,
            "sessions": 3,
            "messages": 4,
        },
    ]
    metadata = {
        "dimensions": ["month"],
        "metric": "all",
        "total": True,
        "separator": True,
        "human": True,
        "scope_request": {"type": "all_workspaces", "values": []},
    }

    output = formatter.format(rows, "stats_rollup", metadata)

    assert "\n--\n" in output
    assert "TOTAL" in output
    assert "1h 30m 0s" in output
    assert "4K" in output
    assert "SESSIONS" in output
    assert "MESSAGES" in output


def test_stats_rollup_table_right_aligns_numeric_columns() -> None:
    formatter = TableFormatter(width=120)
    rows = [
        {"month": "2026-01", "input_tokens": 1, "output_tokens": 20},
        {"month": "2026-02", "input_tokens": 1000, "output_tokens": 2},
    ]
    metadata = {"dimensions": ["month"], "metric": "tokens"}

    output = formatter.format(rows, "stats_rollup", metadata)
    lines = output.splitlines()
    header = next(line for line in lines if line.startswith("MONTH"))
    first_row = next(line for line in lines if line.startswith("2026-01"))
    input_col = header.index("INPUT_TOKENS")
    output_col = header.index("OUTPUT_TOKENS")

    assert first_row[input_col - 1] == " "
    assert first_row[output_col - 1] == " "
    assert first_row[input_col : input_col + len("INPUT_TOKENS")].strip() == "1"
    assert first_row[output_col : output_col + len("OUTPUT_TOKENS")].strip() == "20"


def test_stats_rollup_tsv_human_formats_token_columns() -> None:
    formatter = TsvFormatter()
    rows = [
        {
            "workspace": "/tmp/project",
            "model": "claude-test",
            "input_tokens": 10_000,
            "output_tokens": 5_000_000,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 2,
        }
    ]
    metadata = {"dimensions": ["workspace", "model"], "metric": "tokens", "human": True}

    output = formatter.format(rows, "stats_rollup", metadata)

    assert output.splitlines() == [
        "WORKSPACE\tMODEL\tINPUT_TOKENS\tOUTPUT_TOKENS\tCACHE_READ\tCACHE_CREATE",
        "/tmp/project\tclaude-test\t10K\t5M\t3\t2",
    ]


def test_stats_rollup_tsv_can_append_total_row() -> None:
    formatter = TsvFormatter()
    rows = [
        {"month": "2026-01", "input_tokens": 10, "output_tokens": 20},
        {"month": "2026-02", "input_tokens": 30, "output_tokens": 40},
    ]
    metadata = {"dimensions": ["month"], "metric": "tokens", "total": True}

    output = formatter.format(rows, "stats_rollup", metadata)

    assert output.splitlines() == [
        "MONTH\tINPUT_TOKENS\tOUTPUT_TOKENS\tCACHE_READ\tCACHE_CREATE",
        "2026-01\t10\t20\t0\t0",
        "2026-02\t30\t40\t0\t0",
        "TOTAL\t40\t60\t0\t0",
    ]
