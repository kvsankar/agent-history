"""Run manifests: the commit record of each collector run.

A manifest is a zstd-compressed JSON Lines file. Its first line describes the run; each
following line describes one path. A file in the archive counts as archived only when a
manifest lists it.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Collection, Iterable, Iterator

from agent_history.archive.codec import compress_bytes, decompress_bytes
from agent_history.archive.errors import ArchiveError

if TYPE_CHECKING:
    from agent_history.archive.transport import Destination

MANIFEST_SUFFIX = ".jsonl.zst"


class ManifestError(ArchiveError):
    """A manifest that cannot be decoded."""


_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
_STAMP_LENGTH = len("20261002T061500Z")


def new_run_id(now: datetime, source: str, after: Iterable[str] = ()) -> str:
    """A run id that sorts after every id in ``after``, the source's committed runs.

    Readers apply manifests in run id order, so a run in the same second as the newest
    one, or after the clock stepped back, takes the second after the newest stamp.
    """
    return f"{next_run_stamp(now, after)}-{source}-{secrets.token_hex(2)}"


def next_run_stamp(now: datetime, after: Iterable[str] = ()) -> str:
    stamp = run_stamp(now)
    stamps = [found for found in map(_stamp_of, after) if found is not None]
    newest = max(stamps, default=None)
    if newest is not None and stamp <= newest:
        later = datetime.strptime(newest, _STAMP_FORMAT) + timedelta(seconds=1)
        stamp = later.strftime(_STAMP_FORMAT)
    return stamp


def _stamp_of(run_id: str) -> str | None:
    stamp = run_id[:_STAMP_LENGTH]
    try:
        datetime.strptime(stamp, _STAMP_FORMAT)
    except ValueError:
        return None  # not a collector's run id; it does not affect the order
    return stamp


def run_stamp(now: datetime) -> str:
    return now.strftime(_STAMP_FORMAT)


def run_id_stamp(run_id: str) -> str:
    """The UTC time at the start of a run id, as written in version and export names."""
    return run_id[:_STAMP_LENGTH]


def manifests_dir(source: str) -> str:
    return f"sources/{source}/manifests"


def manifest_path(source: str, run_id: str) -> str:
    return f"{manifests_dir(source)}/{run_id}{MANIFEST_SUFFIX}"


def encode_manifest(run: dict[str, Any], entries: list[dict[str, Any]], level: int) -> bytes:
    lines = [json.dumps({"type": "run", **run}, sort_keys=True)]
    lines.extend(json.dumps(entry, sort_keys=True) for entry in entries)
    return compress_bytes(("\n".join(lines) + "\n").encode("utf-8"), level)


def decode_manifest(
    data: bytes, name: str = "The manifest"
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The run record and the entries of a manifest; ManifestError names ``name``."""
    try:
        text = decompress_bytes(data).decode("utf-8")
        records = [json.loads(line) for line in text.splitlines()]
    except Exception as exc:  # zstd, UTF-8 and JSON errors alike: the file is damaged
        raise ManifestError(f"{name} cannot be decoded: {exc}") from exc
    if not records or not all(isinstance(record, dict) for record in records):
        raise ManifestError(f"{name} does not hold one JSON object per line")
    if records[0].get("type") != "run":
        raise ManifestError(f"{name} does not start with a run record")
    return records[0], records[1:]


def committed_run_ids(destination: Destination, source: str) -> list[str]:
    """Ids of the runs of a source that have a manifest in the archive, oldest first."""
    return sorted(
        name[: -len(MANIFEST_SUFFIX)]
        for name in destination.list_files(manifests_dir(source))
        if name.endswith(MANIFEST_SUFFIX) and "/" not in name
    )


def read_manifest(
    destination: Destination, source: str, run_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    path = manifest_path(source, run_id)
    data = destination.read_bytes(path)
    if data is None:
        return None
    return decode_manifest(data, f"The manifest {path} in {destination.description}")


def read_manifests(
    destination: Destination, source: str, skip_run_ids: Collection[str] = ()
) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Yield (run, entries) for every manifest of a source, oldest first."""
    for run_id in committed_run_ids(destination, source):
        if run_id in skip_run_ids:
            continue
        manifest = read_manifest(destination, source, run_id)
        if manifest is not None:
            yield manifest
