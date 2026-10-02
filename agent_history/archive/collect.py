"""The collector: copy new and changed source files into the archive.

A run walks the source, compresses changed files into a local staging folder, moves aside
archived copies that a rewrite would overwrite, transfers the staging folder, and then
writes the run's manifest. The manifest is written last, so an interrupted run leaves only
files that no manifest lists; the next run writes them again.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ALL_COMPLETED, FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_history.archive.codec import CompressResult, compress_file, hash_file
from agent_history.archive.config import ArchiveConfig, SourceConfig
from agent_history.archive.errors import ArchiveError
from agent_history.archive.layouts import SelectedFile, archive_file_path, iter_source_files
from agent_history.archive.manifest import (
    encode_manifest,
    manifest_path,
    new_run_id,
    read_manifests,
    run_stamp,
)
from agent_history.archive.state import (
    CollectLockedError,
    FileState,
    SourceState,
    load_state,
    save_state,
    source_lock,
    state_path,
)
from agent_history.archive.transport import Destination, open_destination

__all__ = ["CollectLockedError", "RunSummary", "collect_source", "source_lock"]

ARCHIVE_FORMAT = 1
# A file modified this recently may change again within the same timestamp tick without
# its size or time changing, so its state is not trusted and the next run checks it again.
RACY_WINDOW_NS = 2_000_000_000
# Staged files are transferred whenever this much has accumulated, and at the end.
BATCH_BYTES = 512 * 1024 * 1024
_IN_FLIGHT_PER_WORKER = 4
# Files this large are compressed with zstd's own threads as well, so one large session
# file does not take minutes on a single core.
LARGE_FILE_BYTES = 64 * 1024 * 1024
_FILE_ERRORS = (OSError, sqlite3.Error)


@dataclass
class RunSummary:
    run_id: str
    source: str
    written: int = 0
    versioned: int = 0
    gone: int = 0
    errors: int = 0
    skipped_reason: str | None = None
    dry_run: bool = False
    entries: list[dict[str, Any]] = field(default_factory=list)


def default_state_dir() -> Path:
    from agent_history.storage.config import get_config_dir

    return get_config_dir() / "archive-state"


def collect_source(
    config: ArchiveConfig,
    source_name: str,
    *,
    state_dir: Path | None = None,
    now: datetime | None = None,
    force: bool = False,
    dry_run: bool = False,
    destination: Destination | None = None,
) -> RunSummary:
    """Run the collector once for one source."""
    source = config.source(source_name)
    state_dir = Path(state_dir) if state_dir else default_state_dir()
    now = now or datetime.now(timezone.utc)
    destination = destination or open_destination(config.destination)
    with source_lock(state_dir, config.destination, source_name):
        run = _Run(config, source, destination, state_dir, now, dry_run)
        if not force and run.too_soon():
            return RunSummary(run.run_id, source_name, skipped_reason="min_interval")
        return run.execute()


def check_archive_format(destination: Destination, create: bool) -> None:
    data = destination.read_bytes("ARCHIVE.json")
    if data is None:
        if create:
            destination.write_bytes("ARCHIVE.json", json.dumps({"format": ARCHIVE_FORMAT}).encode())
        return
    found = json.loads(data.decode("utf-8")).get("format")
    if found != ARCHIVE_FORMAT:
        raise ArchiveError(f"Archive format {found} is not supported (expected {ARCHIVE_FORMAT})")


class _Run:
    def __init__(self, config, source: SourceConfig, destination, state_dir, now, dry_run):
        self.config = config
        self.source = source
        self.destination = destination
        self.now = now
        self.dry_run = dry_run
        self.run_id = new_run_id(now, source.name)
        self.state_file = state_path(state_dir, config.destination, source.name)
        self.state = load_state(self.state_file) or self._rebuild_state()
        self.summary = RunSummary(self.run_id, source.name, dry_run=dry_run)
        self.moves: list[tuple[str, str]] = []
        self.staged_bytes = 0
        # On disk next to the state, never the system temp folder (often a small tmpfs).
        self.work_root = self.state_file.parent / "work"

    def _rebuild_state(self) -> SourceState:
        state = SourceState()
        for run, entries in read_manifests(self.destination, self.source.name):
            state.apply_manifest(run, entries)
        return state

    def too_soon(self) -> bool:
        hours = self.config.min_interval_hours
        if not hours or not self.state.last_success:
            return False
        last = datetime.fromisoformat(self.state.last_success)
        return self.now - last < timedelta(hours=hours)

    def execute(self) -> RunSummary:
        check_archive_format(self.destination, create=not self.dry_run)
        if not self.dry_run:
            self._ping("/start")
            self.destination.write_bytes(
                f"sources/{self.source.name}/SOURCE.json", self._descriptor()
            )
        self.work_root.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="staging-", dir=self.work_root) as staging:
                self._scan(Path(staging))
                if not self.dry_run:
                    self._commit(Path(staging))
        except Exception:
            if not self.dry_run:
                self._ping("/fail")
            raise
        if not self.dry_run:
            self._ping("/fail" if self.summary.errors else "")
        return self.summary

    # -- scanning ---------------------------------------------------------------------

    def _scan(self, staging: Path) -> None:
        """Process files on a pool, recording each result as soon as it is ready.

        Up to ``_IN_FLIGHT_PER_WORKER`` files per worker are in flight, so one large file
        does not leave the other workers idle. Before a batch is transferred, every file
        in flight finishes, because the transfer empties the staging folder. Entries are
        sorted by path at the end, so manifests do not depend on timing.
        """
        seen = set()
        pending: set = set()
        window = self.config.workers * _IN_FLIGHT_PER_WORKER
        pool = ThreadPoolExecutor(max_workers=self.config.workers)
        try:
            for item in iter_source_files(self.source):
                seen.add(item.rel_path)
                pending.add(pool.submit(self._safe_process, item, staging))
                if len(pending) >= window:
                    pending = self._record_done(pending, FIRST_COMPLETED)
                if not self.dry_run and self.staged_bytes >= BATCH_BYTES:
                    pending = self._record_done(pending, ALL_COMPLETED)
                    self._flush(staging)
            self._record_done(pending, ALL_COMPLETED)
        except BaseException:
            for future in pending:
                future.cancel()  # queued work is dropped; running files finish
            raise
        finally:
            pool.shutdown(wait=True)
        for rel_path, previous in sorted(self.state.files.items()):
            if rel_path not in seen and not previous.gone:
                self._record({"type": "file", "path": rel_path, "action": "gone"})
        self.summary.entries.sort(key=lambda entry: (entry["path"], entry["type"]))

    def _record_done(self, pending: set, return_when: str) -> set:
        done, still_pending = wait(pending, return_when=return_when)
        for future in done:
            entry = future.result()
            if entry:
                self._record(entry)
        return still_pending

    def _safe_process(self, item: SelectedFile, staging: Path) -> dict[str, Any] | None:
        try:
            return self._process(item, staging)
        except _FILE_ERRORS as exc:
            return {"type": "error", "path": item.rel_path, "message": str(exc)}

    def _record(self, entry: dict[str, Any]) -> None:
        self.summary.entries.append(entry)
        if entry.get("type") == "error":
            self.summary.errors += 1
        self.staged_bytes += entry.get("compressed_size") or 0
        action = entry.get("action")
        if action in ("added", "updated", "versioned") or entry.get("rows"):
            self.summary.written += 1
        if action == "versioned":
            self.summary.versioned += 1
        if action == "gone":
            self.summary.gone += 1

    def _process(self, item: SelectedFile, staging: Path) -> dict[str, Any] | None:
        if item.database is not None:
            from agent_history.archive.databases import process_database

            return process_database(self, item, staging)
        stat = item.path.stat()
        previous = self.state.files.get(item.rel_path)
        if previous and (previous.size, previous.mtime_ns) == (stat.st_size, stat.st_mtime_ns):
            if previous.gone:
                return self._file_entry(
                    item, "returned", stat.st_size, stat.st_mtime_ns, previous.sha256
                )
            return None
        return self.stage_file(item, item.path, staging, stat.st_size, stat.st_mtime_ns, previous)

    def stage_file(
        self,
        item: SelectedFile,
        content: Path,
        staging: Path,
        size: int,
        mtime_ns: int,
        previous: FileState | None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Compress ``content`` as the new version of ``item`` and decide its action."""
        archived = archive_file_path(self.source.name, item.rel_path)
        staged = staging / archived
        prefix_length = previous.size if previous else None
        if self.dry_run and previous is None:
            result = CompressResult(size=size, sha256="", compressed_size=0)  # always "added"
        elif self.dry_run:
            result = hash_file(content, size, prefix_length)
        else:
            result = compress_file(
                content,
                staged,
                self.config.compression_level,
                size=size,
                prefix_length=prefix_length,
                threads=self.config.workers if size >= LARGE_FILE_BYTES else 0,
            )
            os.utime(staged, ns=(mtime_ns, mtime_ns))
        if previous and result.sha256 == previous.sha256:
            staged.unlink(missing_ok=True)
            return self._file_entry(item, "touched", size, mtime_ns, result.sha256, extra)
        action = "added"
        if previous:
            appended = result.size >= previous.size and result.prefix_sha256 == previous.sha256
            action = "updated" if appended and not (extra and extra.get("kind")) else "versioned"
        entry = self._file_entry(item, action, size, mtime_ns, result.sha256, extra)
        entry["compressed_size"] = result.compressed_size
        if action == "versioned" and previous is not None:
            version = f"versions/{item.rel_path}.{run_stamp(self.now)}-{self.run_id[-4:]}.zst"
            entry["previous_sha256"] = previous.sha256
            entry["previous_size"] = previous.size
            entry["version_path"] = version
            self.moves.append((archived, f"sources/{self.source.name}/{version}"))
        return entry

    def _file_entry(self, item, action, size, mtime_ns, sha256, extra=None) -> dict[str, Any]:
        entry = {
            "type": "file",
            "path": item.rel_path,
            "agent": item.agent,
            "action": action,
            "size": size,
            "mtime_ns": mtime_ns,
            "sha256": sha256,
        }
        entry.update(extra or {})
        if is_racy(mtime_ns):
            entry["racy"] = True
        return entry

    # -- committing -------------------------------------------------------------------

    def _flush(self, staging: Path) -> None:
        """Move aside rewritten files, transfer what is staged, then empty the staging folder."""
        self._apply_moves()
        self.moves = []
        if (staging / "sources").exists():
            self.destination.put_tree(staging)
            shutil.rmtree(staging / "sources")
        self.staged_bytes = 0

    def _commit(self, staging: Path) -> None:
        self._flush(staging)
        run = {
            "run_id": self.run_id,
            "source": self.source.name,
            "collector_host": _hostname(),
            "tool_version": _tool_version(),
            "format": ARCHIVE_FORMAT,
            "started_at": self.now.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "written": self.summary.written,
            "errors": self.summary.errors,
        }
        data = encode_manifest(run, self.summary.entries, self.config.compression_level)
        self.destination.write_bytes(manifest_path(self.source.name, self.run_id), data)
        self.state.apply_manifest(run, self.summary.entries)
        save_state(self.state_file, self.state)

    def _apply_moves(self) -> None:
        for src, dst in self.moves:
            if not self.destination.move(src, dst):
                sys.stderr.write(f"Warning: no archived copy to keep for {src}\n")

    def _descriptor(self) -> bytes:
        data = {
            "name": self.source.name,
            "kind": self.source.kind,
            "platform": self.source.platform,
            "note": self.source.note,
        }
        return (json.dumps(data, indent=2) + "\n").encode("utf-8")

    def _ping(self, suffix: str) -> None:
        url = self.config.health_url
        if not url:
            return
        try:
            urllib.request.urlopen(url.rstrip("/") + suffix, timeout=10).close()
        except OSError as exc:
            sys.stderr.write(f"Warning: health ping failed: {exc}\n")


def is_racy(mtime_ns: int) -> bool:
    return time.time_ns() - mtime_ns < RACY_WINDOW_NS


def _hostname() -> str:
    import socket

    return socket.gethostname()


def _tool_version() -> str:
    try:
        from importlib.metadata import version

        return version("cagelens")
    except Exception:
        return "unknown"
