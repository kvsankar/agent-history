"""Validate default jobs parallelism selection."""

from types import SimpleNamespace

from tests.helpers.module_loader import load_agent_history


def test_default_jobs_uses_cpu_capped(monkeypatch):
    """Default jobs should use min(cpu_count, 2)."""
    ah = load_agent_history()

    monkeypatch.setattr(ah.os, "cpu_count", lambda: 8)
    assert ah._default_jobs() == 2

    monkeypatch.setattr(ah.os, "cpu_count", lambda: 1)
    assert ah._default_jobs() == 1


def test_jobs_resolution_falls_back_to_default(monkeypatch):
    """Stats sync uses default when jobs flag is not provided."""
    ah = load_agent_history()

    recorded = {}

    def fake_sync_remote(*_args, **_kwargs):
        recorded["used"] = True
        return {"synced": 0, "skipped": 0, "errors": 0}

    monkeypatch.setattr(ah, "_sync_remote_to_db", fake_sync_remote)
    monkeypatch.setattr(ah, "_sync_remote_to_db_with_new_conn", fake_sync_remote)
    monkeypatch.setattr(
        ah, "_sync_source_to_db", lambda *a, **k: {"synced": 0, "skipped": 0, "errors": 0}
    )
    monkeypatch.setattr(
        ah, "_sync_codex_to_db", lambda *a, **k: {"synced": 0, "skipped": 0, "errors": 0}
    )
    monkeypatch.setattr(
        ah, "_sync_gemini_to_db", lambda *a, **k: {"synced": 0, "skipped": 0, "errors": 0}
    )
    monkeypatch.setattr(ah, "_sync_wsl_windows_to_db", lambda *a, **k: None)
    monkeypatch.setattr(ah, "get_saved_homes", lambda: [])
    dummy_conn = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(ah, "init_metrics_db", lambda: dummy_conn)
    monkeypatch.setattr(ah, "get_claude_projects_dir", lambda: None)

    monkeypatch.setattr(ah.os, "cpu_count", lambda: 4)

    args = SimpleNamespace(
        force=False,
        all_homes=False,
        remotes=["example.com", "example.org"],
        patterns=None,
        workspace=[],
        jobs=None,
        no_remote=False,
        no_wsl=True,
        no_windows=True,
        show_progress=False,
    )

    ah.cmd_stats_sync(args)
    # Should have attempted remote sync and used default jobs>1 path
    assert recorded.get("used")
