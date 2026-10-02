"""Zstandard (zstd) compression helpers for archived files.

Each archived file is one zstd frame whose header records the original size. Compression
reads the source once, hashing it on the way, so the recorded hash always describes the
exact bytes that were compressed.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import IO

CHUNK_SIZE = 1 << 20


def _zstd():
    try:
        import zstandard
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            "The session archive needs the zstandard package: pip install 'cagelens[archive]'"
        ) from exc
    return zstandard


@dataclass(frozen=True)
class CompressResult:
    size: int
    sha256: str
    compressed_size: int
    prefix_sha256: str | None = None


def compress_file(
    src: Path,
    dst: Path,
    level: int,
    size: int | None = None,
    prefix_length: int | None = None,
) -> CompressResult:
    """Compress the first ``size`` bytes of ``src`` (default: its current size) into ``dst``.

    ``prefix_length`` asks for the SHA-256 of the first that many bytes as well; it is None
    when the file is shorter. A file that shrinks while being read raises ``OSError``.
    """
    zstandard = _zstd()
    if size is None:
        size = src.stat().st_size
    whole = hashlib.sha256()
    prefix_digest = hashlib.sha256().hexdigest() if prefix_length == 0 else None
    remaining = size
    dst.parent.mkdir(parents=True, exist_ok=True)
    compressor = zstandard.ZstdCompressor(level=level, write_content_size=True)
    try:
        with src.open("rb") as reader, dst.open("wb") as raw_out:
            # Not a context manager: on error the frame must not be finished.
            writer = compressor.stream_writer(raw_out, size=size, closefd=False)
            while remaining:
                chunk = reader.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise OSError(f"{src} shrank while it was being archived")
                read_before = size - remaining
                if prefix_length and read_before < prefix_length <= read_before + len(chunk):
                    head = whole.copy()
                    head.update(chunk[: prefix_length - read_before])
                    prefix_digest = head.hexdigest()
                whole.update(chunk)
                writer.write(chunk)
                remaining -= len(chunk)
            writer.close()
    except BaseException:
        dst.unlink(missing_ok=True)
        raise
    return CompressResult(
        size=size,
        sha256=whole.hexdigest(),
        compressed_size=dst.stat().st_size,
        prefix_sha256=prefix_digest,
    )


def compress_bytes(data: bytes, level: int) -> bytes:
    return _zstd().ZstdCompressor(level=level, write_content_size=True).compress(data)


def decompress_bytes(data: bytes) -> bytes:
    reader = _zstd().ZstdDecompressor().stream_reader(io.BytesIO(data))
    return reader.read()


def decompressed_sha256(path: Path) -> tuple[str, int]:
    """SHA-256 and length of a compressed file's original content."""
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as raw, _zstd().ZstdDecompressor().stream_reader(raw) as reader:
        while True:
            chunk = reader.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def open_maybe_compressed(path: Path, encoding: str = "utf-8") -> IO[str]:
    """Open ``path`` as text, decompressing it when its name ends in ``.zst``."""
    path = Path(path)
    if path.name.endswith(".zst"):
        raw = path.open("rb")
        reader = _zstd().ZstdDecompressor().stream_reader(raw, closefd=True)
        return io.TextIOWrapper(reader, encoding=encoding)
    return path.open("r", encoding=encoding)
