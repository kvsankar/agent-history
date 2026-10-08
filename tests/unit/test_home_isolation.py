"""Tests must never read the real user's home or probe the host for other homes.

On Windows, Python resolves the home folder from USERPROFILE, not HOME, so a
fixture that only sets HOME leaves the CLI reading the real agent folders.
Discovery of WSL distributions (from Windows) and Windows users (from WSL)
reaches real homes outside any fixture.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers.cli import run_cli_subprocess
from tests.helpers.session_builders import CodexSessionBuilder


def test_cli_subprocess_follows_fixture_home(tmp_path: Path) -> None:
    """A fixture that sets HOME gets that home in the CLI on every platform."""
    CodexSessionBuilder(cwd="/home/testuser/isolation-probe").write_to(
        tmp_path / ".codex" / "sessions"
    )
    claude_dir = tmp_path / ".claude" / "projects"
    claude_dir.mkdir(parents=True)

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["CLAUDE_PROJECTS_DIR"] = str(claude_dir)

    result = run_cli_subprocess(["ws", "list", "--agent", "codex"], env=env)

    assert result.returncode == 0, result.stderr
    assert "isolation-probe" in result.stdout


def _real_home() -> Path:
    """The account's home folder, looked up without the environment."""
    if sys.platform == "win32":
        return Path(os.environ["HOMEDRIVE"] + os.environ["HOMEPATH"])
    import pwd

    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def test_tests_do_not_see_the_real_home() -> None:
    """The test run replaces the real home folder with an empty one."""
    real_home = _real_home()

    assert Path.home() != real_home
    assert Path(os.environ["HOME"]) != real_home
    if sys.platform == "win32":
        assert Path(os.environ["USERPROFILE"]) != real_home


def test_wsl_discovery_does_not_probe_the_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Listing WSL distributions must not run wsl.exe during tests."""
    from agent_history.utils import platform as platform_mod

    calls = []

    def record_run(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 1, b"", b"")

    monkeypatch.setattr(platform_mod.subprocess, "run", record_run)

    assert platform_mod._get_wsl_distro_names() == []
    assert calls == []


def test_windows_user_discovery_does_not_probe_the_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Listing Windows users from WSL must not scan the mounted drives during tests."""
    from agent_history.utils import platform as platform_mod

    scanned = []

    class FakeMount:
        name = "c"

        def __init__(self, *args):
            pass

        def exists(self):
            return True

        def iterdir(self):
            return iter([self])

    monkeypatch.setattr(platform_mod, "Path", FakeMount)
    monkeypatch.setattr(platform_mod, "_is_valid_windows_drive", lambda drive: True)
    monkeypatch.setattr(
        platform_mod, "_scan_users_in_drive", lambda drive, results: scanned.append(drive)
    )

    assert platform_mod.get_windows_users_with_claude() == []
    assert scanned == []
