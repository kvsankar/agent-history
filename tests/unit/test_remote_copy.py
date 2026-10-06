"""Tests for copying remote session files into the local cache."""

from __future__ import annotations

import os
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


@pytest.mark.skipif(SH is None, reason="needs a POSIX sh to stand in for the remote shell")
def test_sub_agents_with_the_same_file_name_are_cached_apart(monkeypatch, tmp_path: Path) -> None:
    workspace = "-home-alice-shop"
    projects = tmp_path / "remote" / ".claude" / "projects" / workspace
    first = projects / "session-a" / "subagents" / "agent-a1.jsonl"
    second = projects / "session-b" / "subagents" / "agent-a1.jsonl"
    for path, text, mtime in ((first, "first\n", 2_000), (second, "second\n", 1_000)):
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        os.utime(path, (mtime, mtime))
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(remote.subprocess, "run", _fake_ssh)
    client = remote.SSHRemoteClient()

    copies = []
    for path in (first, second):
        session = {
            "agent": "claude",
            "filename": path.name,
            "workspace": workspace,
            "remote_path": path.as_posix(),
            "mtime": path.stat().st_mtime,
        }
        copies.append(client.ensure_local_copy("alice@node-alpha", workspace, session))

    assert [copy.read_text(encoding="utf-8") for copy in copies] == ["first\n", "second\n"]
    assert copies[0].relative_to(copies[0].parents[2]).as_posix() == (
        "session-a/subagents/agent-a1.jsonl"
    )
    assert copies[1].relative_to(copies[1].parents[2]).as_posix() == (
        "session-b/subagents/agent-a1.jsonl"
    )


@pytest.mark.skipif(SH is None, reason="needs a POSIX sh to stand in for the remote shell")
def test_a_remote_path_outside_the_workspace_folder_is_cached_by_file_name(
    monkeypatch, tmp_path: Path
) -> None:
    remote_file = tmp_path / "remote" / "sessions" / "rollout-1.jsonl"
    remote_file.parent.mkdir(parents=True)
    remote_file.write_text("rollout\n", encoding="utf-8")
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(remote.subprocess, "run", _fake_ssh)

    session = {
        "agent": "codex",
        "filename": remote_file.name,
        "workspace": "/home/alice/shop",
        "remote_path": remote_file.as_posix(),
        "mtime": remote_file.stat().st_mtime,
    }
    dest = remote.SSHRemoteClient().ensure_local_copy("alice@node-alpha", "", session)

    assert dest is not None
    assert dest.name == "rollout-1.jsonl"
    assert dest.parent.name == "home-alice-shop"
