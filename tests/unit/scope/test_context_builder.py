"""Tests for building resolution context from environment state."""

from __future__ import annotations

from pathlib import Path

from agent_history.scope.context import ContextBuilder


def test_test_mode_pi_override_skips_host_platform_scan(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Pi-only isolated fixtures should not probe real WSL/Windows homes."""
    pi_dir = tmp_path / ".pi" / "agent" / "sessions"
    pi_dir.mkdir(parents=True)

    monkeypatch.setenv("AGENT_HISTORY_TEST_MODE", "1")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PI_SESSIONS_DIR", str(pi_dir))
    monkeypatch.delenv("AGENT_HISTORY_HOME", raising=False)
    monkeypatch.delenv("AGENT_HISTORY_HOME_WSL", raising=False)
    monkeypatch.delenv("AGENT_HISTORY_HOME_WINDOWS", raising=False)
    monkeypatch.delenv("AGENT_HISTORY_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECTS_DIR", raising=False)
    monkeypatch.delenv("CODEX_SESSIONS_DIR", raising=False)
    monkeypatch.delenv("GEMINI_SESSIONS_DIR", raising=False)

    def fail_platform_probe(*_args, **_kwargs):
        raise AssertionError("host platform scan should be skipped")

    monkeypatch.setattr(
        "agent_history.utils.platform.get_wsl_distributions",
        fail_platform_probe,
    )
    monkeypatch.setattr(
        "agent_history.utils.platform.get_windows_users_with_claude",
        fail_platform_probe,
    )
    monkeypatch.setattr(
        "agent_history.utils.platform.is_running_in_wsl",
        lambda: True,
    )
    monkeypatch.setattr("agent_history.storage.config.load_config", lambda: {})

    ctx = ContextBuilder().build()

    assert ctx.pi_sessions_dir == pi_dir
    assert ctx.available_homes == {"wsl": [], "windows": [], "remote": []}
