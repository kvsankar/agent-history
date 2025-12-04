import importlib.machinery
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_CLI_SCRIPT = Path(__file__).resolve().parents[2] / "claude-history"
_CLI_LOADER = importlib.machinery.SourceFileLoader("claude_history_cli_module", str(_CLI_SCRIPT))
_CLI_SPEC = importlib.util.spec_from_loader(_CLI_LOADER.name, _CLI_LOADER)
_claude_cli = importlib.util.module_from_spec(_CLI_SPEC)
_CLI_LOADER.exec_module(_claude_cli)


def run_cli(args, env=None, timeout=20):
    cmd = [sys.executable, str(Path.cwd() / "claude-history"), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
        timeout=timeout,
        check=False,
    )


def make_workspace(root: Path, encoded_name: str, files: int = 1):
    ws = root / encoded_name
    ws.mkdir(parents=True, exist_ok=True)
    for i in range(files):
        (ws / f"session-{i}.jsonl").write_text("{}\n", encoding="utf-8")
    return ws


def test_e2e_local_lsh_lsw_lss(tmp_path: Path):
    projects = tmp_path
    make_workspace(projects, "-home-user-e2e-one", files=2)
    make_workspace(projects, "-home-user-e2e-two", files=1)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)

    # lsh local
    r1 = run_cli(["lsh", "--local"], env=env)
    assert r1.returncode == 0, r1.stderr
    assert "Local" in r1.stdout

    # lsw local
    r2 = run_cli(["lsw", "--local"], env=env)
    assert r2.returncode == 0, r2.stderr
    out = r2.stdout
    assert "/home/user/e2e-one" in out
    assert "/home/user/e2e-two" in out

    # lss local pattern
    r3 = run_cli(["lss", "--local", "e2e-one"], env=env)
    assert r3.returncode == 0, r3.stderr
    assert "/home/user/e2e-one" in r3.stdout


def test_e2e_windows_from_windows(tmp_path: Path):
    if sys.platform != "win32":
        return
    projects = tmp_path
    win_ws1 = projects / "real" / "alpha"
    win_ws2 = projects / "real" / "beta"
    win_ws1.mkdir(parents=True, exist_ok=True)
    win_ws2.mkdir(parents=True, exist_ok=True)

    ws1_encoded = _claude_cli._convert_windows_path_to_encoded(str(win_ws1))
    ws2_encoded = _claude_cli._convert_windows_path_to_encoded(str(win_ws2))

    make_workspace(projects, ws1_encoded, files=1)
    make_workspace(projects, ws2_encoded, files=1)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)  # local still needs a valid root
    env["CLAUDE_WINDOWS_PROJECTS_DIR"] = str(projects)

    r = run_cli(["lsw", "--windows"], env=env)
    assert r.returncode == 0, r.stderr
    lines = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    assert str(win_ws1) in lines and str(win_ws2) in lines
    for path_str in lines:
        assert Path(path_str).exists(), f"Listed path is not accessible: {path_str}"


def test_e2e_wsl_from_windows(tmp_path: Path):
    if sys.platform != "win32":
        return
    projects = tmp_path
    make_workspace(projects, "-home-test-distro-svc", files=1)
    # Empty workspace should still be listed
    empty_ws = projects / "-home-test-distro-blogging-platform"
    empty_ws.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)
    env["CLAUDE_WSL_TEST_DISTRO"] = "TestWSL"
    env["CLAUDE_WSL_PROJECTS_DIR"] = str(projects)

    r1 = run_cli(["lsw", "--wsl"], env=env)
    assert r1.returncode == 0, r1.stderr
    assert (
        "\\\\wsl.localhost\\TestWSL\\home\\test\\distro\\svc" in r1.stdout
        or "\\\\wsl$\\TestWSL\\home\\test\\distro\\svc" in r1.stdout
        or "/home/test/distro/svc" in r1.stdout
        or "/home/test/distro-svc" in r1.stdout
    )
    assert "blogging-platform" in r1.stdout

    r2 = run_cli(["lss", "--wsl"], env=env)
    assert r2.returncode == 0, r2.stderr
    assert "HOME\tWORKSPACE\tFILE\t" in r2.stdout


def test_e2e_wsl_unc_path_without_flag(tmp_path: Path):
    if sys.platform != "win32":
        return
    projects = tmp_path
    make_workspace(projects, "-home-test-distro-noflag", files=1)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)
    env["CLAUDE_WSL_TEST_DISTRO"] = "TestWSL"
    env["CLAUDE_WSL_PROJECTS_DIR"] = str(projects)

    unc = str(projects / "-home-test-distro-noflag")
    r = run_cli(["lss", unc], env=env)
    assert r.returncode == 0, r.stderr
    assert "HOME\tWORKSPACE\tFILE\t" in r.stdout


def test_e2e_export_local(tmp_path: Path):
    projects = tmp_path / "projects"
    outdir = tmp_path / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    projects.mkdir(parents=True, exist_ok=True)
    make_workspace(projects, "-home-user-export", files=1)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)

    r = run_cli(["export", "--local", "--out", str(outdir), "user-export"], env=env, timeout=40)
    assert r.returncode == 0, r.stderr
    # Expect at least one markdown file written
    md_files = list(outdir.rglob("*.md"))
    assert md_files, f"No files in {outdir} after export:\n{r.stdout}\n{r.stderr}"


def test_e2e_export_variants(tmp_path: Path):
    projects = tmp_path / "projects"
    outdir = tmp_path / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    projects.mkdir(parents=True, exist_ok=True)

    # Create workspace with two sessions for variety
    def make_ws(name):
        ws = projects / name
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "s1.jsonl").write_text(
            '{"type":"user","timestamp":"2025-01-01T00:00:00Z","content":[{"type":"text","text":"one"}]}\n'
        )
        (ws / "s2.jsonl").write_text(
            '{"type":"user","timestamp":"2025-01-02T00:00:00Z","content":[{"type":"text","text":"two"}]}\n'
        )
        return ws

    make_ws("-home-user-flags")

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)

    # Minimal export
    r1 = run_cli(
        ["export", "--local", "--minimal", "--out", str(outdir), "user-flags"], env=env, timeout=40
    )
    assert r1.returncode == 0, r1.stderr

    # Flat export
    r2 = run_cli(
        ["export", "--local", "--flat", "--out", str(outdir), "user-flags"], env=env, timeout=40
    )
    assert r2.returncode == 0, r2.stderr

    # Split export
    r3 = run_cli(
        ["export", "--local", "--split", "1", "--out", str(outdir), "user-flags"],
        env=env,
        timeout=60,
    )
    assert r3.returncode == 0, r3.stderr

    md_files = list(outdir.rglob("*.md"))
    assert md_files, f"No markdown files found in {outdir} after variant exports"


def test_e2e_export_absolute_path_target(tmp_path: Path):
    projects = tmp_path / "projects"
    outdir = tmp_path / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    projects.mkdir(parents=True, exist_ok=True)

    target_path = "/abs/export-case" if os.name != "nt" else r"C:\Users\export\case"
    encoded_workspace = _claude_cli._coerce_target_to_workspace_pattern(target_path)
    make_workspace(projects, encoded_workspace, files=1)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)

    r = run_cli(["export", "--local", "--out", str(outdir), target_path], env=env, timeout=40)
    assert r.returncode == 0, r.stderr
    md_files = list(outdir.rglob("*.md"))
    assert md_files, f"No markdown files created for absolute path target:\n{r.stdout}\n{r.stderr}"


def test_e2e_lss_absolute_path_target(tmp_path: Path):
    projects = tmp_path / "projects"
    projects.mkdir(parents=True, exist_ok=True)

    target_path = "/home/test/abs/export-case" if os.name != "nt" else r"C:\abs\export\case"
    encoded_workspace = _claude_cli._coerce_target_to_workspace_pattern(target_path)
    make_workspace(projects, encoded_workspace, files=1)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)

    r = run_cli(["lss", "--local", target_path], env=env)
    assert r.returncode == 0, r.stderr
    assert "session-0.jsonl" in r.stdout


def test_e2e_all_homes_windows(tmp_path: Path):
    if sys.platform != "win32":
        return
    local = tmp_path / "local"
    wsl = tmp_path / "wsl"
    local.mkdir(parents=True, exist_ok=True)
    wsl.mkdir(parents=True, exist_ok=True)

    # Create a local and a WSL workspace with one session each
    (local / "-home-user-loc").mkdir()
    (local / "-home-user-loc" / "a.jsonl").write_text("{}\n")
    (wsl / "-home-test-distro-ws").mkdir()
    (wsl / "-home-test-distro-ws" / "b.jsonl").write_text("{}\n")

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(local)
    env["CLAUDE_WSL_TEST_DISTRO"] = "TestWSL"
    env["CLAUDE_WSL_PROJECTS_DIR"] = str(wsl)

    # Workspaces across all homes
    r = run_cli(["lsw", "--ah"], env=env)
    assert r.returncode == 0, r.stderr
    # Should include both local and WSL-style paths somewhere
    assert "/home/user/loc" in r.stdout
    assert (
        ("wsl.localhost" in r.stdout)
        or ("/home/test/distro-ws" in r.stdout)
        or ("/home/test/distro/ws" in r.stdout)
    )


def test_e2e_stats_top_ws_limit(tmp_path: Path):
    """stats --top-ws should limit workspaces per home."""
    home_dir = tmp_path / "home"
    config_dir = home_dir / ".claude-history"
    projects = tmp_path / "projects"
    config_dir.mkdir(parents=True, exist_ok=True)
    projects.mkdir(parents=True, exist_ok=True)

    db_path = config_dir / "metrics.db"
    conn = _claude_cli.init_metrics_db(db_path)

    def make_sessions(encoded_workspace: str, source: str, count: int):
        ws_dir = projects / encoded_workspace
        ws_dir.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            f = ws_dir / f"s{i}.jsonl"
            f.write_text(
                '{"type":"user","content":[{"type":"text","text":"hi"}]}\n', encoding="utf-8"
            )
            _claude_cli.sync_file_to_db(conn, f, source=source, force=True)

    make_sessions("-home-user-proj-local-main", "local", 3)
    make_sessions("-home-user-proj-local-secondary", "local", 1)
    make_sessions("-home-user-proj-wsl-main", "wsl:Ubuntu", 2)
    make_sessions("-home-user-proj-wsl-secondary", "wsl:Ubuntu", 1)
    conn.close()

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)

    result = run_cli(["stats", "--aw", "--top-ws", "1"], env=env)
    assert result.returncode == 0, result.stderr

    output = result.stdout
    assert "Home: local" in output
    assert "Home: wsl:Ubuntu" in output
    assert "Workspace: local-main" in output
    assert "Workspace: wsl-main" in output
    assert "local-secondary" not in output
    assert "wsl-secondary" not in output
