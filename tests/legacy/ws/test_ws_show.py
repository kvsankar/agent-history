from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from tests.helpers.module_loader import load_agent_history


def _fake_sessions():
    return [
        {
            "workspace": "/home/user/proj",
            "workspace_readable": "/home/user/proj",
            "filename": "sess-new.jsonl",
            "message_count": 4,
            "modified": datetime(2025, 1, 3, 18, 15),
        },
        {
            "workspace": "/home/user/proj",
            "workspace_readable": "/home/user/proj",
            "filename": "sess-old.jsonl",
            "message_count": 2,
            "modified": datetime(2025, 1, 2, 10, 30),
        },
    ]


def test_ws_show_output(monkeypatch, capsys):
    """ws show displays workspace summary in human-readable format."""
    ah = load_agent_history()
    monkeypatch.setattr(ah, "collect_sessions_with_dedup", lambda *a, **k: _fake_sessions())

    args = SimpleNamespace(
        agent=None,
        since_date=None,
        until_date=None,
    )

    ah._dispatch_ws_show(args, ["/home/user/proj"], [])
    out = capsys.readouterr().out

    # Check for expected human-readable output
    assert "Workspace:" in out
    assert "Sessions: 2" in out
    assert "Messages: 6" in out
    assert "Recent Sessions:" in out
