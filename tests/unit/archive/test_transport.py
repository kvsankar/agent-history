"""Tests for the local archive destination."""

from __future__ import annotations

import os

from agent_history.archive.transport import LocalDestination, fsync_file

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
