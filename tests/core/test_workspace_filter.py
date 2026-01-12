from __future__ import annotations

from tests.helpers.module_loader import load_agent_history


def test_workspace_matcher_filters_similar_names():
    """Only sessions from the target workspace should be kept (no substring bleed)."""
    ah = load_agent_history()
    matcher = ah._build_workspace_matcher("-home-user-projects-auth")  # type: ignore[attr-defined]

    sessions = [
        {
            "workspace": "-home-user-projects-auth",
            "workspace_readable": "/home/user/projects/auth",
            "agent": "claude",
            "file": "main.jsonl",
        },
        {
            "workspace": "-home-user-projects-auth-infra",
            "workspace_readable": "/home/user/projects/auth-infra",
            "agent": "claude",
            "file": "infra.jsonl",
        },
        {
            "workspace": "/home/user/projects/auth",
            "workspace_readable": "/home/user/projects/auth",
            "agent": "codex",
            "file": "codex.jsonl",
        },
    ]

    kept = [s for s in sessions if matcher(s)]

    # Exact workspace and codex path should stay; infra variant should be filtered out
    assert len(kept) == 2
    assert all("infra" not in (s.get("workspace_readable") or "") for s in kept)


def test_workspace_matcher_handles_verified_decode(tmp_path, monkeypatch):
    """Matcher should include sessions when verified decode differs from naive decode (hyphens)."""
    ah = load_agent_history()
    # Create a realistic path with hyphen in last segment
    ws_dir = tmp_path / "home" / "user" / "projects" / "claude-history"
    ws_dir.mkdir(parents=True)
    monkeypatch.setenv("AGENT_HISTORY_HOME", str(tmp_path))
    matcher = ah._build_workspace_matcher("-home-user-projects-claude-history")  # type: ignore[attr-defined]

    sessions = [
        {
            "workspace": "hash123",
            "workspace_readable": str(ws_dir),
            "agent": "gemini",
            "file": "sess.json",
        }
    ]

    kept = [s for s in sessions if matcher(s)]
    assert len(kept) == 1
