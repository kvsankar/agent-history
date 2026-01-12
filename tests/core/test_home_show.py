from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

from tests.helpers.module_loader import load_agent_history


def test_home_show_json(monkeypatch, capsys):
    """home show prints summary details per spec (JSON)."""
    ah = load_agent_history()

    # Stub homes and summary
    monkeypatch.setattr(
        ah,
        "_gather_homes",
        lambda args: [{"home": "local", "path": "/home/user/.claude/projects", "workspaces": 3}],
    )
    monkeypatch.setattr(
        ah,
        "_summarize_home",
        lambda home, agent="auto": {
            "type": "local",
            "host": "localhost",
            "status": "ok",
            "sessions": 5,
            "last_modified": datetime(2025, 1, 3, 18, 15),
            "top_workspaces": [("/home/user/proj", 4)],
        },
    )

    args = SimpleNamespace(name="local", format="json", agent=None)
    ah._cmd_home_show(args)  # type: ignore[attr-defined]
    out = json.loads(capsys.readouterr().out)
    assert out["home"] == "local"
    assert out["sessions"] == 5
    assert out["top_workspaces"][0]["workspace"] == "/home/user/proj"


def test_home_show_table(monkeypatch, capsys):
    """home show table output includes key fields."""
    ah = load_agent_history()
    monkeypatch.setattr(
        ah,
        "_gather_homes",
        lambda args: [{"home": "local", "path": "/home/user/.claude/projects", "workspaces": 3}],
    )
    monkeypatch.setattr(
        ah,
        "_summarize_home",
        lambda home, agent="auto": {
            "type": "local",
            "host": "localhost",
            "status": "ok",
            "sessions": 5,
            "last_modified": datetime(2025, 1, 3, 18, 15),
            "top_workspaces": [("/home/user/proj", 4)],
        },
    )

    args = SimpleNamespace(name="local", format=None, agent=None)
    ah._cmd_home_show(args)  # type: ignore[attr-defined]
    out = capsys.readouterr().out
    assert "Home: local" in out
    assert "Sessions: 5" in out
    assert "Top Workspaces:" in out
