import os
import sys
import json
import subprocess
from pathlib import Path


def run_cli(args, env=None, timeout=25):
    cmd = [sys.executable, str(Path.cwd() / "claude-history")] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
        timeout=timeout,
    )


def make_workspace(root: Path, encoded_name: str, jsonl_rows: list):
    ws = root / encoded_name
    ws.mkdir(parents=True, exist_ok=True)
    f = ws / "session-0.jsonl"
    with f.open("w", encoding="utf-8") as fh:
        for row in jsonl_rows:
            fh.write(json.dumps(row) + "\n")
    return ws


def test_e2e_stats_sync_and_show_local(tmp_path: Path):
    projects = tmp_path / "projects"
    cfg = tmp_path / "cfg"
    projects.mkdir(parents=True, exist_ok=True)
    cfg.mkdir(parents=True, exist_ok=True)

    # Minimal valid user message for metrics sync
    rows = [
        {
            "type": "user",
            "timestamp": "2025-01-01T00:00:00Z",
            "content": [{"type": "text", "text": "hi"}],
        }
    ]
    ws = make_workspace(projects, "-home-user-stat", rows)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)
    # Redirect config/metrics DB to temp
    if sys.platform == "win32":
        env["USERPROFILE"] = str(cfg)
    else:
        env["HOME"] = str(cfg)

    r1 = run_cli(["stats", "--sync", "--aw"], env=env)
    assert r1.returncode == 0, r1.stderr

    r2 = run_cli(["stats", "--aw", "--by-workspace"], env=env)
    assert r2.returncode == 0, r2.stderr
    # Should at least include some header text or not be empty
    assert r2.stdout.strip() != ""


def test_e2e_alias_create_add_show_export(tmp_path: Path):
    projects = tmp_path / "projects"
    cfg = tmp_path / "cfg"
    projects.mkdir(parents=True, exist_ok=True)
    cfg.mkdir(parents=True, exist_ok=True)

    # Create a workspace with one message
    rows = [
        {
            "type": "user",
            "timestamp": "2025-01-02T00:00:00Z",
            "content": [{"type": "text", "text": "alias"}],
        }
    ]
    ws = make_workspace(projects, "-home-user-alias", rows)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)
    if sys.platform == "win32":
        env["USERPROFILE"] = str(cfg)
    else:
        env["HOME"] = str(cfg)

    # Create alias and add the encoded workspace dir
    alias = "mye2e"
    r1 = run_cli(["alias", "create", alias], env=env)
    assert r1.returncode == 0, r1.stderr

    r2 = run_cli(["alias", "add", alias, "--", "-home-user-alias"], env=env)
    assert r2.returncode == 0, r2.stderr

    # Export alias config and verify structure contains our workspace
    r3 = run_cli(["alias", "export"], env=env)
    assert r3.returncode == 0, r3.stderr
    data = json.loads(r3.stdout)
    assert alias in data.get("aliases", {})
    assert "local" in data["aliases"][alias]
    assert "-home-user-alias" in data["aliases"][alias]["local"]

    # Show should succeed (content may vary by platform setup)
    r4 = run_cli(["alias", "show", alias], env=env)
    assert r4.returncode == 0, r4.stderr

    # List sessions via alias using @alias in lss
    r5 = run_cli(["lss", f"@{alias}"], env=env)
    assert r5.returncode == 0, r5.stderr
    assert "HOME\tWORKSPACE\tFILE\t" in r5.stdout
