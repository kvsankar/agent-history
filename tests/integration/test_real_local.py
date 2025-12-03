import os
import sys
import json
import subprocess
from pathlib import Path
import pytest

# Mark all tests in this module as integration
pytestmark = pytest.mark.integration


def run_cli(args, env=None, cwd=None, timeout=15):
    cmd = [sys.executable, str(Path.cwd() / "claude-history")] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
    )


def make_workspace(root: Path, encoded_name: str, files: int = 1):
    ws_dir = root / encoded_name
    ws_dir.mkdir(parents=True, exist_ok=True)
    # Create minimal .jsonl files (contents are irrelevant for lss listing)
    for i in range(files):
        (ws_dir / f"session-{i}.jsonl").write_text("{}\n", encoding="utf-8")
    return ws_dir


def test_lsw_local_lists_workspaces(tmp_path: Path):
    # Prepare a synthetic projects dir with two workspaces
    projects = tmp_path
    make_workspace(projects, "-home-user-alpha")
    make_workspace(projects, "-home-user-beta")

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)

    # List workspaces locally
    res = run_cli(["lsw", "--local"], env=env)
    assert res.returncode == 0, res.stderr
    out = res.stdout
    # Expect two workspaces listed
    assert "/home/user/alpha" in out
    assert "/home/user/beta" in out


def test_lss_local_lists_sessions_for_pattern(tmp_path: Path):
    projects = tmp_path
    make_workspace(projects, "-home-user-mysvc", files=2)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)

    # List sessions for pattern 'mysvc'
    res = run_cli(["lss", "--local", "mysvc"], env=env)
    assert res.returncode == 0, res.stderr
    out_lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    # First line is header
    assert out_lines[0].startswith("HOME\tWORKSPACE\tFILE\tMESSAGES\tDATE")
    # At least one file from workspace appears
    assert any("/home/user/mysvc" in ln for ln in out_lines[1:])


def test_lss_local_all_lists_any(tmp_path: Path):
    projects = tmp_path
    make_workspace(projects, "-home-user-foo", files=1)
    make_workspace(projects, "-home-user-bar", files=1)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)

    res = run_cli(["lss", "--local", "all"], env=env)
    assert res.returncode == 0, res.stderr
    out = res.stdout
    # Both workspaces appear in output
    assert "/home/user/foo" in out
    assert "/home/user/bar" in out
