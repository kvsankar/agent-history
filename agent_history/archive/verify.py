"""Verification: decompress archived files and compare them with their manifests."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Callable

from agent_history.archive.codec import CHUNK_SIZE, _zstd
from agent_history.archive.errors import ArchiveError
from agent_history.archive.layouts import archive_file_path
from agent_history.archive.manifest import ManifestError, decode_manifest, read_manifests
from agent_history.archive.transport import Destination, fold_case, ignores_case

_WRITTEN = ("added", "updated", "versioned")


@dataclass
class VerifyReport:
    checked: int = 0
    mismatched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unlisted: list[str] = field(default_factory=list)
    # "<label>: <message>" for files that could not be read from the destination, for
    # example because the connection dropped; such a file is neither checked nor mismatched
    errors: list[str] = field(default_factory=list)
    # Ids of interrupted runs that wrote their manifest but did not commit it. Their files
    # may be partly in place; each such file may hold its committed or its new content.
    # The next collect finishes these runs.
    pending: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.mismatched or self.missing or self.unlisted or self.errors or self.pending)


def _same(rel: str) -> str:
    return rel


def expected_contents(
    destination: Destination, source: str, key: Callable[[str], str] = _same
) -> dict[str, tuple[str, int, str]]:
    """Map source-relative archive paths to (sha256, size, label) from the manifests.

    ``key`` turns each path into the form the destination compares: ``fold_case`` for a
    destination that ignores letter case.
    """
    expected: dict[str, tuple[str, int, str]] = {}
    for _run, entries in read_manifests(destination, source):
        for entry in entries:
            _expect_entry(expected, source, entry, key)
    return expected


def _expect_entry(expected, source: str, entry, key: Callable[[str], str] = _same) -> None:
    if entry.get("type") == "rows" and entry.get("export_path"):
        rel = f"files/{entry['export_path']}.zst"
        expected[key(rel)] = (entry["sha256"], entry["size"], entry["export_path"])
        return
    action = entry.get("action")
    if entry.get("type") != "file" or action not in (*_WRITTEN, "displaced"):
        return
    current = key(archive_file_path(source, entry["path"])[len(f"sources/{source}/") :])
    if action in ("versioned", "displaced") and entry.get("version_path"):
        expected[key(entry["version_path"])] = (
            entry["previous_sha256"],
            entry["previous_size"],
            entry["version_path"],
        )
    if action != "displaced":
        expected[current] = (entry["sha256"], entry["size"], entry["path"])
    elif entry.get("version_path") and expected.get(current, ("", 0, ""))[2] == entry["path"]:
        del expected[current]  # the copy moved to its version path


def verify_source(
    destination: Destination,
    source: str,
    sample: int | None = None,
    rng: random.Random | None = None,
) -> VerifyReport:
    """Check archived files of one source; ``sample`` limits how many are decompressed.

    On a destination that ignores letter case, paths are compared case-folded: there a
    copy can sit in a folder whose name an earlier run gave in another case.
    """
    key = fold_case if ignores_case(destination) else _same
    expected = expected_contents(destination, source, key)
    report = VerifyReport()
    report.pending, placing = _pending_contents(destination, source, key)
    present: dict[str, str] = {}  # compared form -> path as listed
    for folder in ("files", "versions"):
        for name in destination.list_files(f"sources/{source}/{folder}"):
            present[key(f"{folder}/{name}")] = f"{folder}/{name}"
    for rel in sorted(present[found] for found in set(present) - set(expected) - set(placing)):
        report.unlisted.append(_label(rel))
    selected = sorted(set(expected) | set(placing))
    if sample is not None and sample < len(selected):
        selected = sorted((rng or random.Random()).sample(selected, sample))
    for rel in selected:
        _check_file(
            destination, source, present.get(rel), expected.get(rel), placing.get(rel), report
        )
    return report


def _check_file(destination, source, listed, committed, placing, report) -> None:
    """Check one file against its committed content, or a pending run's new content.

    ``listed`` is the file's path as the destination lists it; None when it is missing.
    """
    label = (committed or placing)[2]
    if listed is None:
        if placing is None:  # a pending run may not have placed it, or moved it to versions
            report.missing.append(label)
        return
    try:
        digest = _content_digest(destination, f"sources/{source}/{listed}")
    except (ArchiveError, OSError) as exc:
        report.errors.append(f"{label}: {exc}")
        return
    report.checked += 1
    wanted = [(sha256, size) for sha256, size, _ in filter(None, (committed, placing))]
    if digest not in wanted:
        report.mismatched.append(label)


def _pending_contents(
    destination: Destination, source: str, key: Callable[[str], str] = _same
) -> tuple[list[str], dict[str, tuple[str, int, str]]]:
    """The interrupted runs in the incoming folder, and what their manifests place where."""
    from agent_history.archive.collect import PENDING_MANIFEST, incoming_dir, pending_run_ids

    run_ids = pending_run_ids(destination, source)
    placing: dict[str, tuple[str, int, str]] = {}
    for run_id in run_ids:
        data = destination.read_bytes(f"{incoming_dir(source, run_id)}/{PENDING_MANIFEST}")
        if data is None:
            continue
        try:
            _run, entries = decode_manifest(data)
        except ManifestError:
            continue  # cut short while written, so it placed nothing (see recover_incoming)
        for entry in entries:
            _expect_entry(placing, source, entry, key)
    return run_ids, placing


def _label(rel: str) -> str:
    if rel.startswith("files/") and rel.endswith(".zst"):
        return rel[len("files/") : -len(".zst")]
    return rel


def _content_digest(destination: Destination, rel: str) -> tuple[str, int]:
    """SHA-256 and size of an archived file's content; ("", -1) when it does not decompress.

    A failure to read the file from the destination raises ArchiveError or OSError.
    """
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
    except (ArchiveError, OSError):
        raise
    except Exception:  # not valid zstd: the content does not match
        return ("", -1)
    return digest.hexdigest(), total
