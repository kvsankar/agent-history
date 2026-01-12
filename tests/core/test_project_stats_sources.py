from __future__ import annotations

from types import SimpleNamespace

from tests.helpers.module_loader import load_agent_history


def test_project_stats_adds_remotes(monkeypatch):
    """project stats should propagate project sources into remotes/flags for sync."""
    ah = load_agent_history()
    monkeypatch.setattr(
        ah,
        "load_aliases",
        lambda: {
            "projects": {
                "proj": {
                    "local": ["-home-user-proj"],
                    "remote:vm": ["-home-user-proj"],
                    "wsl:Ubuntu": ["-home-user-proj"],
                    "windows:user": ["C--Users-user-proj"],
                }
            }
        },
    )

    args = SimpleNamespace(
        name="proj",
        remotes=[],
        windows=False,
        wsl=False,
    )
    ah._apply_project_sources_to_args(args, "proj")  # type: ignore[attr-defined]
    assert "vm" in args.remotes
    assert "wsl://Ubuntu" in args.remotes
    assert "windows:user" in args.remotes
    assert args.windows is True
    assert args.wsl is True
