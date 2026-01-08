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


def test_ws_show_json_output(monkeypatch, capsys):
    """ws show emits spec-style summary in JSON format."""
    ah = load_agent_history()
    monkeypatch.setattr(ah, "collect_sessions_with_dedup", lambda *a, **k: _fake_sessions())

    args = SimpleNamespace(
        agent=None,
        format="json",
        since_date=None,
        until_date=None,
    )

    ah._dispatch_ws_show(args, ["/home/user/proj"], [])
    out = capsys.readouterr().out
    assert '"workspace": "proj"' in out or '"workspace": "/home/user/proj"' in out
    assert '"sessions": 2' in out
    assert '"messages": 6' in out
    assert '"recent"' in out


def test_ws_show_tsv_output(monkeypatch, capsys):
    """ws show emits tab-separated key/value rows for TSV."""
    ah = load_agent_history()
    monkeypatch.setattr(ah, "collect_sessions_with_dedup", lambda *a, **k: _fake_sessions())

    args = SimpleNamespace(
        agent=None,
        format="tsv",
        since_date=None,
        until_date=None,
    )

    ah._dispatch_ws_show(args, ["/home/user/proj"], [])
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0].startswith("Workspace\t")
    assert any(line.startswith("Sessions\t2") for line in out)
    assert any(line.startswith("Messages\t6") for line in out)
