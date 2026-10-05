"""Collector runs whose source folders are missing, unreadable or overlapping."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_history.archive.collect import collect_source
from agent_history.archive.config import parse_config
from agent_history.archive.errors import ArchiveError
from agent_history.archive.manifest import read_manifests
from agent_history.archive.transport import open_destination

T0 = datetime(2026, 10, 2, 6, 15, tzinfo=timezone.utc)
SESSION = ".claude/projects/-home-alex-shop/a1.jsonl"


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {"tmp": tmp_path, "home": home, "dest": tmp_path / "archive", "state": tmp_path / "s"}


def _config(env, *extra_entries):
    entry = {"name": "src", "kind": "live", "platform": "linux", "home": str(env["home"])}
    return parse_config(
        {
            "archive": {"destination": str(env["dest"]), "compression_level": 3},
            "sources": [entry, *extra_entries],
        }
    )


def _write(root: Path, rel: str, data: bytes, mtime: int = 1_790_000_000) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))
    return path


def _collect(env, hours=0, config=None):
    config = config or _config(env)
    return collect_source(
        config, "src", state_dir=env["state"], now=T0 + timedelta(hours=hours), force=True
    )


def _run_entries(env, run_id):
    for run, entries in read_manifests(open_destination(str(env["dest"])), "src"):
        if run["run_id"] == run_id:
            return entries
    raise AssertionError(run_id)


def test_missing_home_fails_the_run_and_marks_nothing_gone(env):
    _write(env["home"], SESSION, b"a\n")
    first = _collect(env)
    env["home"].rename(env["tmp"] / "unmounted")

    with pytest.raises(ArchiveError):
        _collect(env, hours=1)

    runs = list(read_manifests(open_destination(str(env["dest"])), "src"))
    assert [run["run_id"] for run, _entries in runs] == [first.run_id]
    (env["tmp"] / "unmounted").rename(env["home"])
    later = _collect(env, hours=2)
    assert later.gone == 0


def test_unreadable_folder_is_an_error_and_its_files_are_not_gone(env, monkeypatch):
    from agent_history.archive import layouts

    _write(env["home"], SESSION, b"a\n")
    _write(env["home"], ".claude/history.jsonl", b"h\n")
    _collect(env)
    _write(env["home"], ".claude/projects/-home-alex-shop/b2.jsonl", b"b\n")
    _write(env["home"], ".claude/projects/-home-alex-web/c3.jsonl", b"c\n")
    locked = env["home"] / ".claude" / "projects" / "-home-alex-shop"
    real_scandir = layouts.os.scandir

    def scandir(path):
        if not isinstance(path, int) and Path(path) == locked:  # rmtree passes fds
            raise PermissionError(13, "Permission denied", str(path))
        return real_scandir(path)

    monkeypatch.setattr(layouts.os, "scandir", scandir)

    summary = _collect(env, hours=1)

    assert summary.gone == 0
    assert summary.errors == 1
    entries = {entry["path"]: entry for entry in _run_entries(env, summary.run_id)}
    assert entries[".claude/projects/-home-alex-shop"]["type"] == "error"
    assert entries[".claude/projects/-home-alex-web/c3.jsonl"]["action"] == "added"


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permissions that apply to the user running the tests",
)
def test_folder_without_permissions_does_not_abort_the_run(env):
    _write(env["home"], SESSION, b"a\n")
    _collect(env)
    locked = env["home"] / ".claude" / "projects" / "-home-alex-shop"
    locked.chmod(0)
    try:
        summary = _collect(env, hours=1)
    finally:
        locked.chmod(0o755)

    assert (summary.errors, summary.gone) == (1, 0)
