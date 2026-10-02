from __future__ import annotations

import json

from agent_history.adapters.inventory import InventoryProvider
from agent_history.cli import orchestrator as orchestrator_module
from agent_history.cli.orchestrator import CommandOrchestrator
from agent_history.handlers.stats import SessionStatsHandler
from agent_history.scope.context import OutputArgs, ResolutionContext
from agent_history.scope.resolver import ScopeResolver
from agent_history.scope.types import ConcreteRecord
from agent_history.storage.metrics import init_metrics_db


def _seed_metrics_db() -> None:
    conn = init_metrics_db()
    try:
        conn.execute(
            """
            INSERT INTO sessions (
                file_path, session_id, workspace, home, source, agent, file_mtime,
                is_agent, message_count, user_messages, assistant_messages,
                input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
                first_timestamp, last_timestamp, start_time, work_period_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/session.jsonl",
                "session-1",
                "/tmp/project",
                "local",
                "local",
                "claude",
                123.0,
                0,
                2,
                1,
                1,
                10,
                5,
                2,
                3,
                "2026-06-01T00:00:00Z",
                "2026-06-01T00:05:00Z",
                "2026-06-01T00:00:00Z",
                300,
            ),
        )
        conn.execute(
            """
            INSERT INTO messages (
                uuid, file_path, session_id, type, timestamp, model,
                input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "msg-1",
                "/tmp/session.jsonl",
                "session-1",
                "assistant",
                "2026-06-01T00:01:00Z",
                "claude-test",
                10,
                5,
                2,
                3,
            ),
        )
        conn.execute(
            """
            INSERT INTO tool_uses (
                tool_use_id, file_path, session_id, tool_name, is_error, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "tool-1",
                "/tmp/session.jsonl",
                "session-1",
                "Read",
                0,
                "2026-06-01T00:02:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_untimestamped_zero_time_session() -> None:
    conn = init_metrics_db()
    try:
        conn.execute(
            """
            INSERT INTO sessions (
                file_path, session_id, workspace, home, source, agent, file_mtime,
                is_agent, message_count, user_messages, assistant_messages,
                input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
                first_timestamp, last_timestamp, start_time, work_period_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/session-no-time.jsonl",
                "session-no-time",
                "/tmp/project",
                "local",
                "local",
                "claude",
                124.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                None,
                None,
                None,
                0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_second_workspace_session() -> None:
    conn = init_metrics_db()
    try:
        conn.execute(
            """
            INSERT INTO sessions (
                file_path, session_id, workspace, home, source, agent, file_mtime,
                is_agent, message_count, user_messages, assistant_messages,
                input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
                first_timestamp, last_timestamp, start_time, work_period_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/session-two.jsonl",
                "session-2",
                "/tmp/second-project",
                "local",
                "local",
                "claude",
                125.0,
                0,
                1,
                1,
                0,
                1,
                0,
                0,
                0,
                "2026-06-02T00:00:00Z",
                "2026-06-02T00:00:00Z",
                "2026-06-02T00:00:00Z",
                0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_cached_session(
    *,
    file_path: str,
    session_id: str,
    workspace: str,
    agent: str = "claude",
    start: str = "2026-06-01T00:00:00Z",
    end: str = "2026-06-01T00:05:00Z",
    work_seconds: int = 300,
    messages: int = 1,
    input_tokens: int = 1,
    output_tokens: int = 0,
) -> None:
    conn = init_metrics_db()
    try:
        conn.execute(
            """
            INSERT INTO sessions (
                file_path, session_id, workspace, home, source, agent, file_mtime,
                is_agent, message_count, user_messages, assistant_messages,
                input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
                first_timestamp, last_timestamp, start_time, end_time, work_period_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_path,
                session_id,
                workspace,
                "local",
                "local",
                agent,
                200.0,
                0,
                messages,
                1 if messages else 0,
                max(messages - 1, 0),
                input_tokens,
                output_tokens,
                0,
                0,
                start,
                end,
                start,
                end,
                work_seconds,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_default_stats_uses_cached_db_without_scope_resolution(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()

    def fail_resolve(*args, **kwargs):
        raise AssertionError("default cached stats should not resolve raw scope")

    def fail_list_sessions(*args, **kwargs):
        raise AssertionError("default cached stats should not scan raw sessions")

    def fail_sync(*args, **kwargs):
        raise AssertionError("default cached stats should not sync")

    monkeypatch.setattr(ScopeResolver, "resolve", fail_resolve)
    monkeypatch.setattr(InventoryProvider, "list_sessions", fail_list_sessions)
    monkeypatch.setattr(orchestrator_module, "sync_scope_to_db", fail_sync)

    exit_code = CommandOrchestrator().run(["session", "stats", "--format", "json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    stats = json.loads(captured.out)
    assert stats["total_sessions"] == 1
    assert stats["tokens"]["input"] == 10
    assert "by_tool" not in stats
    assert "Using cached metrics" in captured.err


def test_cached_stats_json_grouping_flags_control_optional_breakdowns(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()

    exit_code = CommandOrchestrator().run(["stats", "--format", "json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    plain_stats = json.loads(captured.out)
    assert "by_tool" not in plain_stats
    assert "by_model" not in plain_stats
    assert "by_day" not in plain_stats

    exit_code = CommandOrchestrator().run(["stats", "--by", "tool,model,day", "--format", "json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    grouped_stats = json.loads(captured.out)
    assert grouped_stats != plain_stats
    assert grouped_stats["by_tool"]["Read"]["uses"] == 1
    assert grouped_stats["by_model"]["claude-test"]["messages"] == 1
    assert grouped_stats["by_day"]["2026-06-01"]["sessions"] == 1


def test_cached_stats_top_ws_limits_workspace_rows_json(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()
    _seed_second_workspace_session()

    exit_code = CommandOrchestrator().run(["stats", "--top-ws", "1", "--format", "json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    stats = json.loads(captured.out)
    assert stats["total_sessions"] == 2
    assert len(stats["workspace_rows"]) == 1
    assert len(stats["by_workspace"]) == 2


def test_top_level_stats_uses_cached_db_without_scope_resolution(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()

    def fail_resolve(*args, **kwargs):
        raise AssertionError("top-level cached stats should not resolve raw scope")

    def fail_list_sessions(*args, **kwargs):
        raise AssertionError("top-level cached stats should not scan raw sessions")

    def fail_sync(*args, **kwargs):
        raise AssertionError("top-level cached stats should not sync")

    monkeypatch.setattr(ScopeResolver, "resolve", fail_resolve)
    monkeypatch.setattr(InventoryProvider, "list_sessions", fail_list_sessions)
    monkeypatch.setattr(orchestrator_module, "sync_scope_to_db", fail_sync)

    exit_code = CommandOrchestrator().run(["stats", "--format", "json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    stats = json.loads(captured.out)
    assert stats["total_sessions"] == 1
    assert stats["tokens"]["output"] == 5
    assert "Using cached metrics" in captured.err


def test_top_level_stats_rollup_uses_cached_db(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()

    def fail_resolve(*args, **kwargs):
        raise AssertionError("cached stats rollup should not resolve raw scope")

    def fail_list_sessions(*args, **kwargs):
        raise AssertionError("cached stats rollup should not scan raw sessions")

    def fail_sync(*args, **kwargs):
        raise AssertionError("cached stats rollup should not sync")

    monkeypatch.setattr(ScopeResolver, "resolve", fail_resolve)
    monkeypatch.setattr(InventoryProvider, "list_sessions", fail_list_sessions)
    monkeypatch.setattr(orchestrator_module, "sync_scope_to_db", fail_sync)

    exit_code = CommandOrchestrator().run(
        [
            "stats",
            "rollup",
            "--metric",
            "tokens",
            "--by",
            "workspace,model",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    rows = json.loads(captured.out)
    assert rows == [
        {
            "sessions": 1,
            "messages": 1,
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 2,
            "time_seconds": None,
            "time_hms": None,
            "time_hours": None,
            "workspace": "/tmp/project",
            "model": "claude-test",
        }
    ]
    assert "Using cached metrics" in captured.err


def test_time_model_rollup_fails_with_explicit_message(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()

    exit_code = CommandOrchestrator().run(
        [
            "stats",
            "rollup",
            "--metric",
            "time",
            "--by",
            "month,model",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "--metric time cannot be grouped by model" in captured.err
    assert "time is tracked per session" in captured.err


def test_time_month_rollup_omits_untimestamped_zero_time_bucket(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()
    _seed_untimestamped_zero_time_session()

    exit_code = CommandOrchestrator().run(
        [
            "stats",
            "rollup",
            "--metric",
            "time",
            "--by",
            "month",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    rows = json.loads(captured.out)
    assert rows == [
        {
            "sessions": 1,
            "messages": 2,
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 2,
            "time_seconds": 300,
            "time_hms": "0h 5m 0s",
            "time_hours": 300 / 3600,
            "month": "2026-06",
        }
    ]


def test_time_rollup_accepts_workspace_month_aliases(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()

    exit_code = CommandOrchestrator().run(
        [
            "stats",
            "rollup",
            "--metric",
            "time",
            "--by",
            "ws,month",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    rows = json.loads(captured.out)
    assert rows[0]["workspace"] == "/tmp/project"
    assert rows[0]["month"] == "2026-06"
    assert rows[0]["time_hms"] == "0h 5m 0s"


def test_time_rollup_total_uses_scope_wall_clock_not_group_sum(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _insert_cached_session(
        file_path="/tmp/claude-overlap.jsonl",
        session_id="claude-overlap",
        workspace="/tmp/project",
        agent="claude",
        start="2026-06-01T00:00:00Z",
        end="2026-06-01T01:00:00Z",
        work_seconds=3600,
    )
    _insert_cached_session(
        file_path="/tmp/codex-overlap.jsonl",
        session_id="codex-overlap",
        workspace="/tmp/project",
        agent="codex",
        start="2026-06-01T00:30:00Z",
        end="2026-06-01T01:30:00Z",
        work_seconds=3600,
    )

    exit_code = CommandOrchestrator().run(
        ["stats", "rollup", "--metric", "time", "--by", "agent", "--format", "tsv", "--raw"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    rows = [line.split("\t") for line in captured.out.splitlines()]
    total = next(row for row in rows if row[0] == "TOTAL")
    assert total[3] == "5400"


def test_project_rollup_uses_configured_project_membership(tmp_path, monkeypatch, capsys) -> None:
    config_dir = tmp_path / ".cagelens"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 2,
                "homes": [],
                "sources": [],
                "projects": {
                    "sample": {
                        "local": [
                            "/tmp/project",
                            "/tmp/second-project",
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(config_dir))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()
    _seed_second_workspace_session()

    exit_code = CommandOrchestrator().run(
        [
            "stats",
            "rollup",
            "--metric",
            "all",
            "--by",
            "project",
            "--project",
            "sample",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    rows = json.loads(captured.out)
    assert rows == [
        {
            "sessions": 2,
            "messages": 3,
            "input_tokens": 11,
            "output_tokens": 5,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 2,
            "time_seconds": 300,
            "time_hms": "0h 5m 0s",
            "time_hours": 300 / 3600,
            "project": "sample",
        }
    ]


def test_cached_stats_tag_filter_selects_matching_projects(tmp_path, monkeypatch, capsys) -> None:
    config_dir = tmp_path / ".cagelens"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 2,
                "homes": [],
                "sources": [],
                "projects": {
                    "sample": {"local": ["/tmp/project"]},
                    "personal": {"local": ["/tmp/second-project"]},
                },
                "project_tags": {
                    "sample": ["work"],
                    "personal": ["personal"],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(config_dir))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()
    _seed_second_workspace_session()

    exit_code = CommandOrchestrator().run(["stats", "--tag", "work", "--format", "json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    stats = json.loads(captured.out)
    assert stats["total_sessions"] == 1
    assert stats["by_workspace"] == {
        "/tmp/project": {
            "sessions": 1,
            "messages": 2,
        }
    }


def test_cached_stats_rollup_by_tag_duplicates_multi_tag_projects_and_untagged(
    tmp_path, monkeypatch, capsys
) -> None:
    config_dir = tmp_path / ".cagelens"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 2,
                "homes": [],
                "sources": [],
                "projects": {
                    "sample": {"local": ["/tmp/project"]},
                    "untagged-project": {"local": ["/tmp/second-project"]},
                },
                "project_tags": {
                    "sample": ["work", "client"],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(config_dir))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()
    _seed_second_workspace_session()

    exit_code = CommandOrchestrator().run(
        [
            "stats",
            "rollup",
            "--metric",
            "all",
            "--by",
            "tag",
            "--format",
            "json",
            "--raw",
            "--no-total",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    rows = sorted(json.loads(captured.out), key=lambda row: row["tag"])
    assert rows == [
        {
            "sessions": 1,
            "messages": 2,
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 2,
            "time_seconds": 300,
            "time_hms": "0h 5m 0s",
            "time_hours": 300 / 3600,
            "tag": "client",
        },
        {
            "sessions": 1,
            "messages": 1,
            "input_tokens": 1,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "time_seconds": 0,
            "time_hms": "0h 0m 0s",
            "time_hours": 0,
            "tag": "untagged",
        },
        {
            "sessions": 1,
            "messages": 2,
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 2,
            "time_seconds": 300,
            "time_hms": "0h 5m 0s",
            "time_hours": 300 / 3600,
            "tag": "work",
        },
    ]


def test_cached_token_rollup_by_tag_model_preserves_null_time(
    tmp_path, monkeypatch, capsys
) -> None:
    config_dir = tmp_path / ".cagelens"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 2,
                "homes": [],
                "sources": [],
                "projects": {"sample": {"local": ["/tmp/project"]}},
                "project_tags": {"sample": ["work"]},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(config_dir))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()

    exit_code = CommandOrchestrator().run(
        [
            "stats",
            "rollup",
            "--metric",
            "tokens",
            "--by",
            "tag,model",
            "--format",
            "json",
            "--no-total",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    rows = json.loads(captured.out)
    assert rows == [
        {
            "sessions": 1,
            "messages": 1,
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 2,
            "time_seconds": None,
            "time_hms": None,
            "time_hours": None,
            "tag": "work",
            "model": "claude-test",
        }
    ]


def test_synced_project_rollup_uses_passed_project_membership(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()
    _seed_second_workspace_session()
    scope = [
        ConcreteRecord(home="local", workspace="/tmp/project", sessions=[{}]),
        ConcreteRecord(home="local", workspace="/tmp/second-project", sessions=[{}]),
    ]

    result = SessionStatsHandler().execute(
        scope,
        {
            "stats_mode": "rollup",
            "metric": "all",
            "by": ["project"],
            "project_map": {
                "/tmp/project": "sample",
                "/tmp/second-project": "sample",
            },
        },
        OutputArgs(format="json"),
    )

    assert result.success
    assert result.data == [
        {
            "sessions": 2,
            "messages": 3,
            "input_tokens": 11,
            "output_tokens": 5,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 2,
            "time_seconds": 300,
            "time_hms": "0h 5m 0s",
            "time_hours": 300 / 3600,
            "project": "sample",
        }
    ]


def test_token_month_rollup_omits_untimestamped_zero_token_bucket(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()
    _seed_untimestamped_zero_time_session()

    exit_code = CommandOrchestrator().run(
        [
            "stats",
            "rollup",
            "--metric",
            "tokens",
            "--by",
            "workspace,month",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    rows = json.loads(captured.out)
    assert rows == [
        {
            "sessions": 1,
            "messages": 2,
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_tokens": 3,
            "cache_creation_tokens": 2,
            "time_seconds": 300,
            "time_hms": "0h 5m 0s",
            "time_hours": 300 / 3600,
            "workspace": "/tmp/project",
            "month": "2026-06",
        }
    ]


def test_token_rollup_without_model_uses_session_token_totals(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    conn = init_metrics_db()
    try:
        conn.execute(
            """
            INSERT INTO sessions (
                file_path, session_id, workspace, home, source, agent, file_mtime,
                is_agent, message_count, user_messages, assistant_messages,
                input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
                first_timestamp, last_timestamp, start_time, work_period_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/codex.jsonl",
                "codex-1",
                "/tmp/project",
                "local",
                "local",
                "codex",
                123.0,
                0,
                1,
                0,
                1,
                10,
                2,
                0,
                8,
                "2026-06-01T00:00:00Z",
                "2026-06-01T00:01:00Z",
                "2026-06-01T00:00:00Z",
                60,
            ),
        )
        conn.execute(
            """
            INSERT INTO messages (
                uuid, file_path, session_id, type, timestamp, model,
                input_tokens, output_tokens, cache_read_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "codex-msg-1",
                "/tmp/codex.jsonl",
                "codex-1",
                "assistant",
                "2026-06-01T00:01:00Z",
                "gpt-5.1-codex-max",
                1234,
                56,
                1000,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    exit_code = CommandOrchestrator().run(
        [
            "stats",
            "rollup",
            "--metric",
            "tokens",
            "--by",
            "agent,month",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    rows = json.loads(captured.out)
    assert rows[0]["agent"] == "codex"
    assert rows[0]["input_tokens"] == 10
    assert rows[0]["output_tokens"] == 2
    assert rows[0]["cache_read_tokens"] == 8


def test_token_model_rollup_omits_zero_token_model_bucket(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / ".cagelens"))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()
    conn = init_metrics_db()
    try:
        conn.execute(
            """
            INSERT INTO messages (
                uuid, file_path, session_id, type, timestamp, model,
                input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "synthetic-zero",
                "/tmp/session.jsonl",
                "session-1",
                "assistant",
                "2026-06-01T00:02:00Z",
                "<synthetic>",
                0,
                0,
                0,
                0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    exit_code = CommandOrchestrator().run(
        [
            "stats",
            "rollup",
            "--metric",
            "tokens",
            "--by",
            "month,model",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    rows = json.loads(captured.out)
    assert {row["model"] for row in rows} == {"claude-test"}


def test_project_stats_scope_keeps_configured_workspace_count(
    tmp_path, monkeypatch, capsys
) -> None:
    config_dir = tmp_path / ".cagelens"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 2,
                "homes": [],
                "sources": [],
                "projects": {
                    "sample": {
                        "local": [
                            "/tmp/project",
                            "/tmp/project-without-cached-metrics",
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(config_dir))
    monkeypatch.chdir(tmp_path)
    _seed_metrics_db()

    exit_code = CommandOrchestrator().run(["stats", "--project", "sample", "--format", "table"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Request: project sample" in captured.out
    assert "Workspaces: 2 (" in captured.out
    assert "/tmp/project-without-cached-metrics" in captured.out
    assert "Sessions: 1" in captured.out


def test_sync_stats_bypasses_cached_shortcut() -> None:
    orchestrator = CommandOrchestrator()
    request = orchestrator.parser.parse(["session", "stats", "--sync"])

    result = orchestrator._run_cached_stats_if_applicable(request, ResolutionContext())

    assert result is None
