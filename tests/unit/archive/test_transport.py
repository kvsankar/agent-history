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


def _replace_busy(monkeypatch, failures: int) -> list[str]:
    """Make os.replace fail ``failures`` times as Windows does while a reader holds the file."""
    from agent_history.archive import transport

    monkeypatch.setattr(transport, "_WINDOWS", True)
    monkeypatch.setattr(transport.time, "sleep", lambda seconds: None)
    real = os.replace
    calls: list[str] = []

    def busy(src, dst, *args, **kwargs):
        calls.append(str(dst))
        if len(calls) <= failures:
            raise PermissionError(13, "The process cannot access the file", str(dst))
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", busy)
    return calls


def test_placing_a_file_that_a_reader_holds_open_is_tried_again(tmp_path, monkeypatch):
    dest = LocalDestination(tmp_path)
    dest.write_bytes("sources/s/incoming/run/files/a.zst", b"new")
    dest.write_bytes("sources/s/files/a.zst", b"old")
    calls = _replace_busy(monkeypatch, failures=2)

    dest.place([], [("sources/s/incoming/run/files/a.zst", "sources/s/files/a.zst")])

    assert (tmp_path / "sources/s/files/a.zst").read_bytes() == b"new"
    assert len(calls) == 3


def test_a_file_held_open_for_too_long_fails_the_placement(tmp_path, monkeypatch):
    dest = LocalDestination(tmp_path)
    dest.write_bytes("sources/s/incoming/run/files/a.zst", b"new")
    _replace_busy(monkeypatch, failures=1000)

    with pytest.raises(PermissionError):
        dest.place([], [("sources/s/incoming/run/files/a.zst", "sources/s/files/a.zst")])


def test_a_permission_error_is_not_tried_again_outside_windows(tmp_path, monkeypatch):
    from agent_history.archive import transport

    calls = _replace_busy(monkeypatch, failures=1)
    monkeypatch.setattr(transport, "_WINDOWS", False)

    with pytest.raises(PermissionError):
        LocalDestination(tmp_path).write_bytes("sources/s/a.zst", b"x")
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("given", "extended"),
    [
        (r"C:\Users\alex\state", r"\\?\C:\Users\alex\state"),
        ("C:/Users/alex/state/", r"\\?\C:\Users\alex\state"),
        (r"C:\Users\alex\..\sam\.\state", r"\\?\C:\Users\sam\state"),
        (r"\\nas\share\archive", r"\\?\UNC\nas\share\archive"),
        (r"\\?\C:\Users\alex", r"\\?\C:\Users\alex"),
    ],
)
def test_windows_paths_take_the_extended_form(given, extended):
    from agent_history.archive.transport import extended_path

    assert extended_path(given) == extended


def test_long_path_changes_nothing_outside_windows(tmp_path, monkeypatch):
    from agent_history.archive import transport

    monkeypatch.setattr(transport, "_WINDOWS", False)

    assert transport.long_path(tmp_path) == tmp_path


def test_the_destination_and_the_work_folder_use_long_paths(tmp_path, monkeypatch):
    """Staging adds about 150 characters to a home-relative path; on Windows a long
    transcript path then passes 260 characters, which fails unless LongPathsEnabled is set."""
    from agent_history.archive import collect, transport
    from agent_history.archive.config import parse_config

    def marked(path):
        return path.with_name(path.name + "-long")

    monkeypatch.setattr(transport, "long_path", marked)
    monkeypatch.setattr(collect, "long_path", marked)
    session = tmp_path / "home" / ".claude" / "projects" / "p" / "a.jsonl"
    session.parent.mkdir(parents=True)
    session.write_bytes(b"x\n")
    config = parse_config(
        {
            "archive": {"destination": str(tmp_path / "archive"), "compression_level": 3},
            "sources": [
                {"name": "s", "kind": "live", "platform": "linux", "home": str(tmp_path / "home")}
            ],
        }
    )

    dest = LocalDestination(tmp_path / "archive")
    summary = collect.collect_source(config, "s", state_dir=tmp_path / "state")

    assert dest.root == tmp_path / "archive-long"
    assert dest.description == str(tmp_path / "archive")
    assert summary.written == 1
    assert (tmp_path / "archive-long" / "sources/s/files/.claude/projects/p/a.jsonl.zst").exists()
    assert list((tmp_path / "state").glob("*/work/s-long"))


@pytest.mark.skipif(os.name != "nt", reason="the 260-character limit is Windows'")
def test_a_file_whose_staged_path_passes_260_characters_is_archived(tmp_path):
    from agent_history.archive.collect import collect_source
    from agent_history.archive.config import parse_config
    from agent_history.archive.verify import verify_source

    rel = ".claude/projects/C--Users-alex-code-a-project-with-a-rather-long-name/" + (
        "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0/subagents/agent-a1b2c3d4e5f6a7b8c9.jsonl"
    )
    session = tmp_path / "home" / rel
    session.parent.mkdir(parents=True)
    session.write_bytes(b"x\n")
    config = parse_config(
        {
            "archive": {"destination": str(tmp_path / "archive"), "compression_level": 3},
            "sources": [
                {"name": "s", "kind": "live", "platform": "windows", "home": str(tmp_path / "home")}
            ],
        }
    )

    summary = collect_source(config, "s", state_dir=tmp_path / ("state-" + "x" * 60))

    assert (summary.written, summary.errors) == (1, 0)
    assert verify_source(LocalDestination(tmp_path / "archive"), "s").ok
