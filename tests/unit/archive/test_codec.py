"""Tests for zstd compression helpers."""

from __future__ import annotations

import hashlib

import pytest
import zstandard

from agent_history.archive.codec import (
    compress_file,
    decompressed_sha256,
    open_maybe_compressed,
)


def test_compress_round_trip_records_hashes(tmp_path):
    src = tmp_path / "s.jsonl"
    data = b'{"a": 1}\n' * 1000
    src.write_bytes(data)
    dst = tmp_path / "s.jsonl.zst"

    result = compress_file(src, dst, level=3)

    assert result.size == len(data)
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    assert result.compressed_size == dst.stat().st_size
    assert zstandard.ZstdDecompressor().decompress(dst.read_bytes()) == data


def test_frame_header_records_original_size(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_bytes(b"x" * 5000)
    dst = tmp_path / "s.jsonl.zst"

    compress_file(src, dst, level=3)

    assert zstandard.frame_content_size(dst.read_bytes()) == 5000


def test_prefix_hash_covers_the_requested_length(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_bytes(b"old-part|new-part")

    result = compress_file(src, tmp_path / "o.zst", level=3, prefix_length=8)

    assert result.prefix_sha256 == hashlib.sha256(b"old-part").hexdigest()


def test_prefix_hash_is_none_when_file_is_shorter(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_bytes(b"short")

    result = compress_file(src, tmp_path / "o.zst", level=3, prefix_length=100)

    assert result.prefix_sha256 is None


def test_reads_only_the_size_seen_at_start(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_bytes(b"0123456789")

    result = compress_file(src, tmp_path / "o.zst", level=3, size=4)

    assert result.size == 4
    assert result.sha256 == hashlib.sha256(b"0123").hexdigest()


def test_shrinking_file_raises(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_bytes(b"0123")

    with pytest.raises(OSError, match="shrank"):
        compress_file(src, tmp_path / "o.zst", level=3, size=10)


def test_decompressed_sha256(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_bytes(b"hello")
    compress_file(src, tmp_path / "o.zst", level=3)

    assert decompressed_sha256(tmp_path / "o.zst") == (hashlib.sha256(b"hello").hexdigest(), 5)


@pytest.mark.parametrize("compressed", [False, True])
def test_open_maybe_compressed_reads_text(tmp_path, compressed):
    src = tmp_path / "s.jsonl"
    src.write_text("line one\nline two\n", encoding="utf-8")
    path = src
    if compressed:
        path = tmp_path / "s.jsonl.zst"
        compress_file(src, path, level=3)

    with open_maybe_compressed(path) as handle:
        assert handle.read() == "line one\nline two\n"
