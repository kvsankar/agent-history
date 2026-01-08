from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

from tests.helpers.module_loader import load_agent_history


def test_project_show_table_auto(monkeypatch, capsys):
    """project show auto-detects current project and shows sessions per agent/home."""
    ah = load_agent_history()

    # Fake current workspace detection
    monkeypatch.setattr(ah, "check_current_workspace_exists", lambda: ("-home-user-proj", True))
    monkeypatch.setattr(ah, "get_alias_for_workspace", lambda pattern, source_key="local": "myproj")
    # Project definition
    monkeypatch.setattr(
        ah,
        "load_aliases",
        lambda: {"projects": {"myproj": {"local": ["-home-user-proj"]}}},
    )

    # Sessions across agents
    fake_sessions = [
        {"workspace": "-home-user-proj", "agent": "claude", "message_count": 10},
        {"workspace": "-home-user-proj", "agent": "codex", "message_count": 5},
        {"workspace": "-home-user-proj", "agent": "gemini", "message_count": 7},
    ]
    monkeypatch.setattr(
        ah,
        "_get_all_agent_sessions_for_source",
        lambda source, ws, since_date=None, until_date=None: [
            dict(s, modified=datetime(2025, 1, 1, 10, 0)) for s in fake_sessions
        ],
    )

    args = SimpleNamespace(name=None, format=None)
    ah.cmd_project_show(args)
    out = capsys.readouterr().out
    assert "Project: myproj" in out
    assert "Sessions: 3" in out
    assert "Sessions by agent" in out
    assert "claude" in out and "codex" in out and "gemini" in out


def test_project_show_json(monkeypatch, capsys):
    """project show with explicit name and json output."""
    ah = load_agent_history()
    monkeypatch.setattr(
        ah,
        "load_aliases",
        lambda: {
            "projects": {"sample": {"local": ["-home-user-proj"], "remote:vm": ["-home-user-proj"]}}
        },
    )
    monkeypatch.setattr(
        ah,
        "_get_all_agent_sessions_for_source",
        lambda source, ws, since_date=None, until_date=None: [
            {"agent": "claude", "message_count": 1, "modified": datetime(2025, 1, 1, 12, 0)},
            {"agent": "codex", "message_count": 2, "modified": datetime(2025, 1, 2, 12, 0)},
        ],
    )

    args = SimpleNamespace(name="sample", format="json")
    ah.cmd_project_show(args)
    out_str = capsys.readouterr().out
    out = json.loads(out_str[out_str.index("{") :])
    assert out["project"] == "sample"
    assert out["sessions"] == 4
    assert "per_agent" in out
    assert out["per_agent"]["claude"] == 2
    assert out["per_agent"]["codex"] == 2
