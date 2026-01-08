from __future__ import annotations

from pathlib import Path

from tests.helpers.module_loader import load_agent_history


def test_status_ok_for_encoded_path(monkeypatch, tmp_path: Path):
    """Encoded workspace should resolve to ok when the path exists."""
    ah = load_agent_history()
    workdir = tmp_path / "home" / "user" / "proj"
    workdir.mkdir(parents=True)
    monkeypatch.setenv("AGENT_HISTORY_HOME", str(tmp_path))

    status = ah._check_workspace_status("-home-user-proj", "local")  # type: ignore[attr-defined]
    assert status == "ok"


def test_status_missing_for_nonexistent(monkeypatch, tmp_path: Path):
    """Missing workspace should report missing."""
    ah = load_agent_history()
    monkeypatch.setenv("AGENT_HISTORY_HOME", str(tmp_path))

    status = ah._check_workspace_status("-home-user-missing", "local")  # type: ignore[attr-defined]
    assert status == "missing"


def test_status_unknown_for_hash():
    """Hash-style workspace should return unknown."""
    ah = load_agent_history()
    status = ah._check_workspace_status("abcdef1234567890abcdef", "local")  # type: ignore[attr-defined]
    assert status == "unknown"
