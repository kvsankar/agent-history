from __future__ import annotations

import json

from agent_history.adapters.inventory import InventoryProvider
from agent_history.cli import orchestrator as orchestrator_module
from agent_history.cli.orchestrator import CommandOrchestrator
from agent_history.scope.context import ResolutionContext
from agent_history.scope.resolver import ScopeResolver
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
                uuid, file_path, session_id, type, timestamp, model, output_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "msg-1",
                "/tmp/session.jsonl",
                "session-1",
                "assistant",
                "2026-06-01T00:01:00Z",
                "claude-test",
                5,
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
    assert stats["by_tool"]["Read"]["uses"] == 1
    assert "Using cached metrics" in captured.err


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
            "input_tokens": 0,
            "output_tokens": 5,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "time_seconds": None,
            "time_hours": None,
            "workspace": "/tmp/project",
            "model": "claude-test",
        }
    ]
    assert "Using cached metrics" in captured.err


def test_sync_stats_bypasses_cached_shortcut() -> None:
    orchestrator = CommandOrchestrator()
    request = orchestrator.parser.parse(["session", "stats", "--sync"])

    result = orchestrator._run_cached_stats_if_applicable(request, ResolutionContext())

    assert result is None
