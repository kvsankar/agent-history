"""Tests for scripts/run_tests.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_runner():
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_tests.py"
    spec = importlib.util.spec_from_file_location("run_tests", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run_main(monkeypatch, runner, tmp_root: Path, platform: str) -> list[str]:
    calls = []
    monkeypatch.setattr(runner, "_is_windows", lambda: platform == "win32")
    monkeypatch.setattr(runner.subprocess, "call", lambda cmd, cwd: calls.append(cmd) or 0)
    monkeypatch.setattr(sys, "argv", ["run_tests.py", "--tmp-root", str(tmp_root)])
    assert runner.main() == 0
    return calls[0]


def test_creates_missing_tmp_root_on_posix(monkeypatch, tmp_path):
    runner = _load_runner()
    tmp_root = tmp_path / "fresh-checkout" / ".tmp"

    cmd = _run_main(monkeypatch, runner, tmp_root, "linux")

    assert tmp_root.is_dir()
    basetemp = Path(cmd[cmd.index("--basetemp") + 1])
    assert basetemp.parent == tmp_root


def test_creates_missing_tmp_root_on_windows(monkeypatch, tmp_path):
    runner = _load_runner()
    tmp_root = tmp_path / "fresh-checkout" / ".tmp"
    for name in ("TEMP", "TMP", "TMPDIR"):
        monkeypatch.delenv(name, raising=False)

    _run_main(monkeypatch, runner, tmp_root, "win32")

    assert tmp_root.is_dir()
