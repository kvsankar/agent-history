import os
import sys
import subprocess
from pathlib import Path


def run_cli(args, env=None, timeout=20):
    cmd = [sys.executable, str(Path.cwd() / "claude-history")] + args
    return subprocess.run(cmd, capture_output=True, text=True, env=env or os.environ.copy(), timeout=timeout)


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
    make_workspace(projects, "C--e2e-win-alpha", files=1)
    make_workspace(projects, "C--e2e-win-beta", files=1)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)  # local still needs a valid root
    env["CLAUDE_WINDOWS_PROJECTS_DIR"] = str(projects)

    r = run_cli(["lsw", "--windows"], env=env)
    assert r.returncode == 0, r.stderr
    # Should print native Windows paths
    assert "C:\\e2e-win-alpha" in r.stdout or "C:\\e2e-win-beta" in r.stdout


def test_e2e_wsl_from_windows(tmp_path: Path):
    if sys.platform != "win32":
        return
    projects = tmp_path
    make_workspace(projects, "-home-test-distro-svc", files=1)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)
    env["CLAUDE_WSL_TEST_DISTRO"] = "TestWSL"
    env["CLAUDE_WSL_PROJECTS_DIR"] = str(projects)

    r1 = run_cli(["lsw", "--wsl"], env=env)
    assert r1.returncode == 0, r1.stderr
    # On Windows we print UNC paths for WSL
    assert "wsl.localhost" in r1.stdout or "wsl$" in r1.stdout or "/home/test/distro/svc" in r1.stdout

    r2 = run_cli(["lss", "--wsl"], env=env)
    assert r2.returncode == 0, r2.stderr
    assert "HOME\tWORKSPACE\tFILE\t" in r2.stdout


def test_e2e_export_local(tmp_path: Path):
    projects = tmp_path / "projects"
    outdir = tmp_path / "out"
    outdir.mkdir(parents=True, exist_ok=True)
    projects.mkdir(parents=True, exist_ok=True)
    make_workspace(projects, "-home-user-export", files=1)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(projects)

    r = run_cli(["export", "export", "--local", "--out", str(outdir), "user-export"], env=env, timeout=40)
    assert r.returncode == 0, r.stderr
    # Expect at least one markdown file written
    md_files = list(outdir.glob("*.md"))
    assert md_files, f"No files in {outdir} after export:\n{r.stdout}\n{r.stderr}"

