import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


# Check if WSL is available and functional (for Windows-specific tests)
def _check_wsl_available():
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(["wsl", "--list"], capture_output=True, timeout=5, check=False)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


HAS_WSL = _check_wsl_available()


def run_cli(args, env=None, timeout=25):
    # Use agent-history (new name), fall back to claude-history for backward compat
    script_path = Path.cwd() / "agent-history"
    if not script_path.exists():
        script_path = Path.cwd() / "claude-history"
    cmd = [sys.executable, str(script_path), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
        timeout=timeout,
        check=False,
    )


def make_jsonl(path: Path, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_stats_models_tools_by_day(tmp_path: Path):
    projects = tmp_path / "projects"
    cfg = tmp_path / "cfg"
    projects.mkdir(parents=True, exist_ok=True)
    cfg.mkdir(parents=True, exist_ok=True)

    # Two days, include assistant with model and tool_use to populate stats
    # Use proper JSONL format with message wrapper
    rows = [
        {
            "type": "user",
            "timestamp": "2025-01-01T10:00:00Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "start"}]},
        },
        {
            "type": "assistant",
            "timestamp": "2025-01-01T10:01:00Z",
            "message": {
                "role": "assistant",
                "model": "claude-3-5-sonnet",
                "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "tool_use", "name": "bash", "id": "t1", "input": {"cmd": "echo hi"}},
                ],
            },
        },
        {
            "type": "user",
            "timestamp": "2025-01-02T09:00:00Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "next"}]},
        },
        {
            "type": "assistant",
            "timestamp": "2025-01-02T09:01:00Z",
            "message": {
                "role": "assistant",
                "model": "claude-3-5-haiku",
                "content": [{"type": "text", "text": "done"}],
            },
        },
    ]
    make_jsonl(projects / "-home-user-stats" / "s.jsonl", rows)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)
    # Set HOME to ensure test uses isolated config/database directory
    env["HOME"] = str(cfg)
    if sys.platform == "win32":
        env["USERPROFILE"] = str(cfg)

    # Sync
    r_sync = run_cli(["stats", "--sync", "--aw"], env=env)
    assert r_sync.returncode == 0, r_sync.stderr

    # Models (--models is legacy, maps to --by model)
    r_models = run_cli(["stats", "--aw", "--models"], env=env)
    assert r_models.returncode == 0, r_models.stderr
    # New flat format has "MODEL" column header
    assert "MODEL" in r_models.stdout

    # Tools (--tools is legacy, maps to --by tool)
    r_tools = run_cli(["stats", "--aw", "--tools"], env=env)
    assert r_tools.returncode == 0, r_tools.stderr
    # New flat format has "TOOL" column header
    assert "TOOL" in r_tools.stdout

    # By day (--by-day is legacy, maps to --by day)
    r_by_day = run_cli(["stats", "--aw", "--by-day"], env=env)
    assert r_by_day.returncode == 0, r_by_day.stderr
    assert "2025-01-01" in r_by_day.stdout or "2025-01-02" in r_by_day.stdout
    assert "DAY" in r_by_day.stdout  # Header column (uppercase in flat format)

    # Time tracking
    r_time = run_cli(["stats", "--aw", "--time"], env=env)
    assert r_time.returncode == 0, r_time.stderr
    # New flat format has NAME\tVALUE header and DATE breakdown
    assert "NAME\tVALUE" in r_time.stdout
    assert "total_work_seconds" in r_time.stdout
    assert "DATE" in r_time.stdout


@pytest.mark.skipif(not HAS_WSL, reason="Requires WSL on Windows")
def test_all_homes_sessions_windows(tmp_path: Path):
    # Local and WSL synthetic roots
    local = tmp_path / "local"
    wsl = tmp_path / "wsl"
    home_dir = tmp_path / "home"
    config_dir = home_dir / ".agent-history"
    config_dir.mkdir(parents=True, exist_ok=True)

    make_jsonl(
        local / "-home-user-loc" / "a.jsonl",
        [
            {
                "type": "user",
                "timestamp": "2025-01-03T00:00:00Z",
                "content": [{"type": "text", "text": "x"}],
            }
        ],
    )
    make_jsonl(
        wsl / "-home-test-distro-ws" / "b.jsonl",
        [
            {
                "type": "user",
                "timestamp": "2025-01-04T00:00:00Z",
                "content": [{"type": "text", "text": "y"}],
            }
        ],
    )

    # Add WSL to saved sources (required for --ah to include WSL)
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({"version": 1, "sources": ["wsl:TestWSL"]}))

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["CLAUDE_PROJECTS_DIR"] = str(local)
    env["CLAUDE_WSL_TEST_DISTRO"] = "TestWSL"
    env["CLAUDE_WSL_PROJECTS_DIR"] = str(wsl)

    r = run_cli(["lss", "--ah", "all"], env=env)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # Expect local and WSL paths present
    assert "/home/user/loc" in out
    assert (
        ("wsl.localhost" in out)
        or ("/home/test/distro-ws" in out)
        or ("/home/test/distro/ws" in out)
    )
