"""Tests for copying remote session files into the local cache."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agent_history.adapters import remote

SH = shutil.which("sh")
_REAL_RUN = subprocess.run


def _fake_ssh(cmd, capture_output=True, check=False, **kwargs):
    """Run an ssh command line the way ssh does: join the remote args, run them with sh."""
    assert cmd[0] == "ssh"
    remote_command = " ".join(cmd[2:])
    return _REAL_RUN(
        [SH, "-c", remote_command],
        capture_output=capture_output,
        check=check,
        stdin=subprocess.DEVNULL,
    )


@pytest.mark.skipif(SH is None, reason="needs a POSIX sh to stand in for the remote shell")
def test_ensure_local_copy_fetches_remote_file_content(monkeypatch, tmp_path: Path) -> None:
    remote_file = tmp_path / "remote" / "rollout-2025-01-15T10-00-00-session-codex-001.jsonl"
    remote_file.parent.mkdir()
    remote_file.write_text('{"type":"session_meta"}\n', encoding="utf-8")
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(remote.subprocess, "run", _fake_ssh)

    session = {
        "agent": "codex",
        "filename": remote_file.name,
        "workspace": "/home/alice/myproject",
        "remote_path": remote_file.as_posix(),
        "mtime": remote_file.stat().st_mtime,
    }
    dest = remote.SSHRemoteClient().ensure_local_copy("alice@node-alpha", "", session)

    assert dest is not None
    assert dest.read_text(encoding="utf-8") == '{"type":"session_meta"}\n'
