"""Tests for the local archive destination."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from agent_history.archive.transport import LocalDestination, fsync_file

LOCK = "sources/s/LOCK"

ENDS_IN_CTRL_Z = b"compressed bytes\x00\x1a"


def test_fsync_keeps_a_final_ctrl_z_byte(tmp_path, windows_text_mode):
    path = tmp_path / "copy.zst"
    path.write_bytes(ENDS_IN_CTRL_Z)

    fsync_file(path)

    assert path.read_bytes() == ENDS_IN_CTRL_Z


def test_written_and_transferred_files_keep_a_final_ctrl_z_byte(tmp_path, windows_text_mode):
    """Manifests and archived copies are zstd frames, which can end in any byte."""
    dest = LocalDestination(tmp_path / "archive")
    staging = tmp_path / "staging"
    staged = staging / "sources" / "s" / "incoming" / "run" / "files" / "a.jsonl.zst"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(ENDS_IN_CTRL_Z)

    dest.write_bytes("sources/s/manifests/run.jsonl.zst", ENDS_IN_CTRL_Z)
    dest.put_tree(staging)

    root = tmp_path / "archive" / "sources" / "s"
    assert (root / "manifests" / "run.jsonl.zst").read_bytes() == ENDS_IN_CTRL_Z
    assert (root / "incoming" / "run" / "files" / "a.jsonl.zst").read_bytes() == ENDS_IN_CTRL_Z


def test_sizes_reports_existing_files_only(tmp_path):
    dest = LocalDestination(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.zst").write_bytes(b"12345")
    (tmp_path / "a" / "empty.zst").write_bytes(b"")
    os.mkdir(tmp_path / "a" / "folder")

    sizes = dest.sizes(["a/one.zst", "a/empty.zst", "a/missing.zst", "a/folder"])

    assert sizes == {"a/one.zst": 5, "a/empty.zst": 0}


@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs fork to stop a process mid-call")
def test_a_run_killed_while_taking_the_lock_leaves_no_empty_owner_file(tmp_path):
    """A run killed between creating owner.json and writing it must not leave it empty.

    An empty owner file names no holder, so every later run would fail until --break-lock.
    """
    dest = LocalDestination(tmp_path)
    pid = os.fork()
    if pid == 0:  # the run that is killed: it dies right after a lock file is created
        real_open = os.open

        def open_then_die(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if Path(path).name.startswith("owner.json"):
                os._exit(9)
            return fd

        os.open = open_then_die
        try:
            dest.create_lock(LOCK, b'{"token": "killed"}')
        finally:
            os._exit(0)
    os.waitpid(pid, 0)

    assert not (tmp_path / LOCK / "owner.json").exists()
    assert dest.create_lock(LOCK, b'{"token": "next"}')
    assert (tmp_path / LOCK / "owner.json").read_bytes() == b'{"token": "next"}'


def test_the_lock_is_taken_once_and_leaves_only_the_owner_file(tmp_path):
    dest = LocalDestination(tmp_path)

    assert dest.create_lock(LOCK, b'{"token": "a"}')
    assert not dest.create_lock(LOCK, b'{"token": "b"}')

    assert os.listdir(tmp_path / LOCK) == ["owner.json"]
    assert (tmp_path / LOCK / "owner.json").read_bytes() == b'{"token": "a"}'


def test_without_hard_links_the_lock_falls_back_to_an_exclusive_create(tmp_path, monkeypatch):
    def no_links(src, dst, *args, **kwargs):
        raise OSError(errno.EPERM, "hard links are not supported here")

    monkeypatch.setattr(os, "link", no_links)
    dest = LocalDestination(tmp_path)

    assert dest.create_lock(LOCK, b'{"token": "a"}')
    assert not dest.create_lock(LOCK, b'{"token": "b"}')

    assert os.listdir(tmp_path / LOCK) == ["owner.json"]
    assert (tmp_path / LOCK / "owner.json").read_bytes() == b'{"token": "a"}'
