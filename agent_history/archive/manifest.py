"""Run manifests: the commit record of each collector run.

A manifest is a zstd-compressed JSON Lines file. Its first line describes the run; each
following line describes one path. A file in the archive counts as archived only when a
manifest lists it.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import TYPE_CHECKING, Any, Collection, Iterator

from agent_history.archive.codec import compress_bytes, decompress_bytes

if TYPE_CHECKING:
    from agent_history.archive.transport import Destination

MANIFEST_SUFFIX = ".jsonl.zst"


def new_run_id(now: datetime, source: str) -> str:
    return f"{run_stamp(now)}-{source}-{secrets.token_hex(2)}"


def run_stamp(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%SZ")


def manifests_dir(source: str) -> str:
    return f"sources/{source}/manifests"


def manifest_path(source: str, run_id: str) -> str:
    return f"{manifests_dir(source)}/{run_id}{MANIFEST_SUFFIX}"


def encode_manifest(run: dict[str, Any], entries: list[dict[str, Any]], level: int) -> bytes:
    lines = [json.dumps({"type": "run", **run}, sort_keys=True)]
    lines.extend(json.dumps(entry, sort_keys=True) for entry in entries)
    return compress_bytes(("\n".join(lines) + "\n").encode("utf-8"), level)


def decode_manifest(data: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = [json.loads(line) for line in decompress_bytes(data).decode("utf-8").splitlines()]
    if not records or records[0].get("type") != "run":
        raise ValueError("Manifest does not start with a run record")
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
    data = destination.read_bytes(manifest_path(source, run_id))
    return decode_manifest(data) if data is not None else None


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
