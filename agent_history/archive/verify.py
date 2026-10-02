"""Verification: decompress archived files and compare them with their manifests."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from agent_history.archive.codec import CHUNK_SIZE, _zstd
from agent_history.archive.layouts import archive_file_path
from agent_history.archive.manifest import read_manifests
from agent_history.archive.transport import Destination

_WRITTEN = ("added", "updated", "versioned")


@dataclass
class VerifyReport:
    checked: int = 0
    mismatched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unlisted: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.mismatched or self.missing or self.unlisted)


def expected_contents(destination: Destination, source: str) -> dict[str, tuple[str, int, str]]:
    """Map source-relative archive paths to (sha256, size, label) from the manifests."""
    expected: dict[str, tuple[str, int, str]] = {}
    for _run, entries in read_manifests(destination, source):
        for entry in entries:
            _expect_entry(expected, source, entry)
    return expected


def _expect_entry(expected, source: str, entry) -> None:
    if entry.get("type") == "rows" and entry.get("export_path"):
        rel = f"files/{entry['export_path']}.zst"
        expected[rel] = (entry["sha256"], entry["size"], entry["export_path"])
        return
    if entry.get("type") != "file" or entry.get("action") not in _WRITTEN:
        return
    current = archive_file_path(source, entry["path"])[len(f"sources/{source}/") :]
    if entry["action"] == "versioned" and entry.get("version_path"):
        expected[entry["version_path"]] = (
            entry["previous_sha256"],
            entry["previous_size"],
            entry["version_path"],
        )
    expected[current] = (entry["sha256"], entry["size"], entry["path"])


def verify_source(
    destination: Destination,
    source: str,
    sample: int | None = None,
    rng: random.Random | None = None,
) -> VerifyReport:
    """Check archived files of one source; ``sample`` limits how many are decompressed."""
    expected = expected_contents(destination, source)
    report = VerifyReport()
    present = set()
    for folder in ("files", "versions"):
        for name in destination.list_files(f"sources/{source}/{folder}"):
            present.add(f"{folder}/{name}")
    for rel in sorted(present - set(expected)):
        report.unlisted.append(_label(rel))
    selected = sorted(expected)
    if sample is not None and sample < len(selected):
        selected = sorted((rng or random.Random()).sample(selected, sample))
    for rel in selected:
        sha256, size, label = expected[rel]
        if rel not in present:
            report.missing.append(label)
            continue
        report.checked += 1
        if _content_digest(destination, f"sources/{source}/{rel}") != (sha256, size):
            report.mismatched.append(label)
    return report


def _label(rel: str) -> str:
    if rel.startswith("files/") and rel.endswith(".zst"):
        return rel[len("files/") : -len(".zst")]
    return rel


def _content_digest(destination: Destination, rel: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    try:
        with destination.open_binary(rel) as raw:
            with _zstd().ZstdDecompressor().stream_reader(raw) as reader:
                while True:
                    chunk = reader.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    digest.update(chunk)
                    total += len(chunk)
    except Exception:
        return ("", -1)
    return digest.hexdigest(), total
