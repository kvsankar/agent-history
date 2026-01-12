from __future__ import annotations

from types import SimpleNamespace

from tests.helpers.module_loader import load_agent_history


def test_expand_patterns_for_sync_expands_projects(monkeypatch):
    """@project patterns expand to concrete workspaces for stats sync."""
    ah = load_agent_history()
    monkeypatch.setattr(
        ah,
        "load_aliases",
        lambda: {
            "projects": {"proj1": {"local": ["-home-user-proj1"], "remote:vm": ["/srv/proj1"]}}
        },
    )

    expanded = ah._expand_patterns_for_sync(["@proj1"])  # type: ignore[attr-defined]
    assert "-home-user-proj1" in expanded
    assert "/srv/proj1" in expanded
    assert "@proj1" not in expanded


def test_combine_workspace_inputs_preserves_project_patterns():
    """Project patterns shouldn't be prefixed with '=' so they expand correctly."""
    ah = load_agent_history()
    combined = ah._combine_workspace_inputs(["@proj"], None, all_flag=False)  # type: ignore[attr-defined]
    assert combined == ["@proj"]


def test_cmd_stats_sync_uses_project_patterns(monkeypatch):
    """project patterns expand during stats sync."""
    ah = load_agent_history()

    # Stub aliases
    monkeypatch.setattr(
        ah,
        "load_aliases",
        lambda: {"projects": {"proj": {"local": ["-home-user-proj"], "remote:vm": ["/srv/proj"]}}},
    )

    recorded = {}

    class DummyConn:
        def close(self): ...

        def execute(self, *a, **k):
            class Row:
                def fetchone(self):
                    return (0, 0, 0)

            return Row()

    monkeypatch.setattr(ah, "init_metrics_db", lambda *a, **k: DummyConn())

    def record_patterns(
        conn, projects_dir, source_key, display_name, pats, force, show_progress=False
    ):
        recorded["patterns"] = pats
        return {"synced": 0, "skipped": 0, "errors": 0}

    monkeypatch.setattr(ah, "_sync_source_to_db", record_patterns)

    def record_codex(conn, pats, force, **kw):
        recorded.setdefault("patterns_codex", pats)
        return {"synced": 0, "skipped": 0, "errors": 0}

    def record_gemini(conn, pats, force, **kw):
        recorded.setdefault("patterns_gemini", pats)
        return {"synced": 0, "skipped": 0, "errors": 0}

    monkeypatch.setattr(ah, "_sync_codex_to_db", record_codex)
    monkeypatch.setattr(ah, "_sync_gemini_to_db", record_gemini)

    args = SimpleNamespace(
        force=False,
        all_homes=False,
        remotes=[],
        patterns=None,
        workspace=["@proj"],
        jobs=1,
        no_remote=False,
        no_wsl=True,
        no_windows=True,
        show_progress=False,
    )
    ah.cmd_stats_sync(args)
    expanded = set(recorded.get("patterns", []))
    # Should include both encoded and decoded project workspaces
    assert {"-home-user-proj", "/srv/proj"}.issubset(expanded)
