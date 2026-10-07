"""Tests must never read the real user's home.

On Windows, Python resolves the home folder from USERPROFILE, not HOME, so a
fixture that only sets HOME leaves the CLI reading the real agent folders.
"""

import os
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


@pytest.mark.skipif(sys.platform != "win32", reason="USERPROFILE is Windows-only")
def test_tests_do_not_see_the_real_windows_home() -> None:
    """The test run replaces the real profile folder with an empty one."""
    real_home = Path(os.environ["HOMEDRIVE"] + os.environ["HOMEPATH"])

    assert Path.home() != real_home
    assert Path(os.environ["USERPROFILE"]) != real_home
