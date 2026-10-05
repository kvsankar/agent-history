"""The collector: copy new and changed source files into the archive.

A run walks the source, compresses changed files into a local staging folder, and
transfers the staging folder to the run's incoming folder in the archive. At the end it
writes its manifest there, moves the archived copies that rewrites replace to versions/,
moves the new copies into place, and commits the manifest. An interrupted run either
changed no committed path or is finished by the next run (see "committing a run" below).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ALL_COMPLETED, FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_history.archive.codec import CompressResult, compress_file, hash_file
from agent_history.archive.config import ArchiveConfig, SourceConfig
from agent_history.archive.errors import ArchiveError
from agent_history.archive.layouts import (
    SelectedFile,
    archive_file_path,
    is_within,
    iter_source_files,
)
from agent_history.archive.manifest import (
    ManifestError,
    committed_run_ids,
    decode_manifest,
    encode_manifest,
    manifest_path,
    new_run_id,
    read_manifest,
    run_id_stamp,
)
from agent_history.archive.state import (
    CollectLockedError,
    FileState,
    SourceState,
    destination_lock,
    load_state,
    save_state,
    source_lock,
    state_path,
)
from agent_history.archive.transport import Destination, Keep, Put, open_destination

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
# Only one large file at a time uses those threads, which bounds the memory they take.
_LARGE_FILE_SLOT = threading.Lock()
_FILE_ERRORS = (OSError, sqlite3.Error)
_WRITTEN = ("added", "updated", "versioned")


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
    destination: Destination | str | None = None,
    break_lock: bool = False,
) -> RunSummary:
    """Run the collector once for one source.

    ``destination`` overrides the configured one, as a path or URL or as an open
    destination. The state and the local lock are kept per destination: per path or URL
    as written, or per description for an open destination. ``break_lock`` removes the
    source's lock in the archive before the run takes it.
    """
    source = config.source(source_name)
    state_dir = Path(state_dir) if state_dir else default_state_dir()
    now = now or datetime.now(timezone.utc)
    if destination is None or isinstance(destination, str):
        key = destination or config.destination
        destination = open_destination(key)
    else:
        key = destination.description
    with source_lock(state_dir, key, source_name):
        run = _Run(config, source, destination, state_dir, now, dry_run, key)
        return run.execute(force=force, break_lock=break_lock)


def check_archive_format(destination: Destination, create: bool) -> bool:
    """Check ARCHIVE.json; create it when missing and ``create``. False when it is missing."""
    data = destination.read_bytes("ARCHIVE.json")
    if data is None:
        if create:
            destination.write_bytes("ARCHIVE.json", json.dumps({"format": ARCHIVE_FORMAT}).encode())
        return False
    try:
        found = json.loads(data.decode("utf-8"))
    except ValueError as exc:  # not UTF-8 or not JSON
        raise ArchiveError(
            f"ARCHIVE.json in {destination.description} cannot be read: {exc}"
        ) from exc
    if not isinstance(found, dict):
        raise ArchiveError(f"ARCHIVE.json in {destination.description} is not a JSON object")
    found = found.get("format")
    if found != ARCHIVE_FORMAT:
        raise ArchiveError(f"Archive format {found} is not supported (expected {ARCHIVE_FORMAT})")
    return True


# -- committing a run -------------------------------------------------------------------
#
# A run sends its files to sources/<source>/incoming/<run id>/, laid out like the source's
# folder, so no committed path changes while files are in transit. To finish, it writes its
# manifest there, moves the archived copies of rewritten files to versions/, moves the new
# copies into place, and only then moves the manifest to manifests/, which commits the run.
# Each step can be repeated, so a run that stopped after writing that manifest is finished
# by the next run, and an incoming folder without one holds nothing committed.

PENDING_MANIFEST = "manifest.jsonl.zst"


def incoming_root(source: str) -> str:
    return f"sources/{source}/incoming"


def incoming_dir(source: str, run_id: str) -> str:
    return f"{incoming_root(source)}/{run_id}"


def placements(
    source: str, run_id: str, entries: list[dict[str, Any]]
) -> tuple[list[Keep], list[Put]]:
    """The moves that put a run's files in place, from its manifest entries."""
    prefix = f"sources/{source}/"
    incoming = incoming_dir(source, run_id)
    keeps: list[Keep] = []
    puts: list[Put] = []
    for entry in entries:
        if entry.get("type") == "rows" and entry.get("export_path"):
            current = f"{prefix}files/{entry['export_path']}.zst"
        elif entry.get("type") == "file" and entry.get("action") in _WRITTEN:
            current = archive_file_path(source, entry["path"])
        else:
            continue
        staged = f"{incoming}/{current[len(prefix) :]}"
        if entry.get("action") == "versioned" and entry.get("version_path"):
            keeps.append((current, f"{prefix}{entry['version_path']}", staged))
        puts.append((staged, current))
    return keeps, puts


def finish_run(
    destination: Destination,
    source: str,
    run_id: str,
    entries: list[dict[str, Any]],
    discard: str,
) -> None:
    """Place a run's files, commit its manifest, then remove the discard folder.

    Safe to repeat after an interruption.
    """
    destination.place(*placements(source, run_id, entries))
    pending = f"{incoming_dir(source, run_id)}/{PENDING_MANIFEST}"
    if not destination.move(pending, manifest_path(source, run_id)):
        raise ArchiveError(f"The manifest of run {run_id} disappeared before it was committed")
    destination.discard_tree(discard)


def pending_run_ids(destination: Destination, source: str) -> list[str]:
    """Interrupted runs that wrote their manifest to the incoming folder, oldest first."""
    names = destination.list_files(incoming_root(source))
    return sorted(
        name.split("/")[0]
        for name in names
        if name.count("/") == 1 and name.endswith(f"/{PENDING_MANIFEST}")
    )


def recover_incoming(destination: Destination, source: str) -> bool:
    """Finish runs that stopped after writing their manifest; drop other incoming files.

    Returns True when a run was finished. Called with the source's lock held, so no other
    run of the source is writing to the incoming folder. A manifest that does not decode
    was cut short while it was written, and placing starts only after that write, so
    such a run placed nothing and is dropped with the rest.
    """
    finished = False
    for run_id in pending_run_ids(destination, source):
        data = destination.read_bytes(f"{incoming_dir(source, run_id)}/{PENDING_MANIFEST}")
        if data is None:
            continue
        try:
            _run, entries = decode_manifest(
                data, f"The manifest of interrupted run {run_id} in {destination.description}"
            )
        except ManifestError as exc:
            sys.stderr.write(
                f"Warning: discarding interrupted run {run_id}, which placed no files: {exc}\n"
            )
            continue
        sys.stderr.write(f"Finishing interrupted run {run_id}\n")
        finish_run(destination, source, run_id, entries, incoming_dir(source, run_id))
        finished = True
    destination.discard_tree(incoming_root(source))
    return finished


class _Run:
    def __init__(self, config, source: SourceConfig, destination, state_dir, now, dry_run, key):
        self.config = config
        self.source = source
        self.destination = destination
        self.now = now
        self.dry_run = dry_run
        self.run_id = ""  # named once the archive's runs are known (_set_run_id)
        self.state_file = state_path(state_dir, key, source.name)
        loaded = load_state(self.state_file)
        self.state = loaded or SourceState()
        self.rebuild_state = loaded is None
        self.summary = RunSummary(self.run_id, source.name, dry_run=dry_run)
        self.incoming = ""
        # (manifest entry, archived copy, version path) for each rewrite
        self.moves: list[tuple[dict[str, Any], str, str]] = []
        self.staged_bytes = 0
        # On disk next to the state, never the system temp folder (often a small tmpfs).
        # One folder per source, because the lock that keeps runs apart is per source.
        self.work_root = self.state_file.parent / "work" / source.name

    # -- the state against the archive ------------------------------------------------

    def _check_destination(self) -> bool:
        """Refuse a destination that does not hold what the state says.

        A network mount that is not mounted looks like an empty folder, and a restored
        archive can be older than the state. Writing into either would record files as
        archived that the real archive does not hold, so the run stops instead. Writes
        nothing. Returns whether ARCHIVE.json exists.
        """
        committed = committed_run_ids(self.destination, self.source.name)
        has_format = check_archive_format(self.destination, create=False)
        if not has_format and (committed or self._destination_has_history()):
            raise ArchiveError(
                f"The archive at {self.destination.description} has no ARCHIVE.json, but "
                f"earlier runs wrote to it. Check that the destination is mounted. If the "
                f"archive was emptied on purpose, delete the state folder "
                f"{self.state_file.parent} to start again."
            )
        lost = sorted(set(self.state.applied_runs(committed)) - set(committed))
        if self.state.runs is None and self.state.last_run_id not in (None, *committed):
            lost = [str(self.state.last_run_id)]
        if lost:
            raise ArchiveError(
                f"The archive at {self.destination.description} lacks {len(lost)} run "
                f"manifest(s) that the local state records, such as {lost[-1]}. The "
                f"destination may not be mounted, or may be an older copy. If the archive "
                f"was restored on purpose, delete the state file {self.state_file}; it is "
                f"then rebuilt from the archive's manifests."
            )
        return has_format

    def _catch_up(self, has_format: bool) -> None:
        """With the locks held: finish interrupted runs and apply the manifests the
        state lacks, then name this run after the newest committed one."""
        if not self.dry_run:
            if not has_format:
                check_archive_format(self.destination, create=True)
            recover_incoming(self.destination, self.source.name)
        committed = committed_run_ids(self.destination, self.source.name)
        self._reconcile(committed)
        self._set_run_id(new_run_id(self.now, self.source.name, after=committed))

    def _set_run_id(self, run_id: str) -> None:
        """Name the run so that it sorts after the source's committed runs."""
        self.run_id = run_id
        self.summary.run_id = run_id
        self.incoming = incoming_dir(self.source.name, run_id)

    def _destination_has_history(self) -> bool:
        """True when this or another source's state records runs to this destination."""
        if self.state.has_history():
            return True
        for path in self.state_file.parent.glob("*.json"):
            other = load_state(path)
            if other is not None and other.has_history():
                return True
        return False

    def _reconcile(self, committed: list[str]) -> None:
        """Apply manifests that the state does not include yet, oldest first.

        They come from a run that stopped after writing its manifest but before saving
        the state, or, when the state file is missing, from every earlier run.
        """
        applied = self.state.applied_runs(committed)
        if self.state.runs is None:
            self.state.runs = sorted(applied)
        for run_id in committed:
            if run_id in applied:
                continue
            manifest = read_manifest(self.destination, self.source.name, run_id)
            if manifest is not None:
                self.state.apply_manifest(*manifest)

    def _clear_work(self) -> None:
        """Remove staging and database copies left by a run that was killed.

        The source's lock is held, so no other run is using this source's work folder.
        """
        self.work_root.mkdir(parents=True, exist_ok=True)
        for folder in self.work_root.iterdir():
            if folder.is_dir() and folder.name.startswith(("staging-", "db-")):
                shutil.rmtree(folder, ignore_errors=True)

    def too_soon(self) -> bool:
        hours = self.config.min_interval_hours
        if not hours or not self.state.last_success:
            return False
        last = datetime.fromisoformat(self.state.last_success)
        return self.now - last < timedelta(hours=hours)

    def _has_pending_run(self) -> bool:
        """True when an interrupted run waits in the incoming folder to be finished.

        Such a run is finished even before min_interval_hours have passed, so the archive
        does not hold placed but uncommitted files until then. A dry run would not finish
        it, so it does not look. When the destination cannot be read, the run is not due
        anyway: it is skipped with a warning, and the next due run reports the failure.
        """
        if self.dry_run:
            return False
        try:
            return bool(pending_run_ids(self.destination, self.source.name))
        except (ArchiveError, OSError) as exc:
            sys.stderr.write(
                f"Warning: could not look for interrupted runs of {self.source.name}: {exc}\n"
            )
            return False

    def execute(self, force: bool = False, break_lock: bool = False) -> RunSummary:
        """Check the destination and take its lock, then run.

        A failure before the run starts sends the failure request too, except that a
        lock another run holds is not a failure: the run is skipped.
        """
        with ExitStack() as stack:
            try:
                if self.rebuild_state:  # before the interval check, which needs the state
                    self._reconcile(committed_run_ids(self.destination, self.source.name))
                if not force and self.too_soon() and not self._has_pending_run():
                    return RunSummary("", self.source.name, skipped_reason="min_interval")
                has_format = self._check_destination()
                if not self.dry_run:  # a dry run writes nothing, so it needs no lock
                    local_lock = self.state_file.with_suffix(".lock")
                    stack.enter_context(
                        destination_lock(self.destination, self.source.name, local_lock, break_lock)
                    )
            except CollectLockedError:
                raise
            except Exception:
                if not self.dry_run:
                    self._ping("/fail")
                raise
            return self._execute_locked(has_format)

    def _execute_locked(self, has_format: bool) -> RunSummary:
        if not self.dry_run:
            self._ping("/start")
        try:
            self._catch_up(has_format)
            if not self.dry_run:
                self.destination.write_bytes(
                    f"sources/{self.source.name}/SOURCE.json", self._descriptor()
                )
            self._clear_work()
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
        unreadable: list[str] = []
        pending: set = set()
        window = self.config.workers * _IN_FLIGHT_PER_WORKER
        pool = ThreadPoolExecutor(max_workers=self.config.workers)
        try:
            for item in iter_source_files(self.source):
                seen.add(item.rel_path)
                if item.error is not None:
                    unreadable.append(item.rel_path)
                    self._record({"type": "error", "path": item.rel_path, "message": item.error})
                    continue
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
            if rel_path not in seen and not previous.gone and not is_within(rel_path, unreadable):
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
        read_ns = time.time_ns()  # before reading: a slow read must not hide a recent write
        stat = item.path.stat()
        previous = self.state.files.get(item.rel_path)
        if previous and (previous.size, previous.mtime_ns) == (stat.st_size, stat.st_mtime_ns):
            if previous.gone:
                entry = self._file_entry(
                    item, "returned", stat.st_size, stat.st_mtime_ns, previous.sha256
                )
                return _mark_racy(entry, stat.st_mtime_ns, read_ns)
            return None
        return self.stage_file(
            item, item.path, staging, stat.st_size, stat.st_mtime_ns, previous, read_ns=read_ns
        )

    def stage_file(
        self,
        item: SelectedFile,
        content: Path,
        staging: Path,
        size: int,
        mtime_ns: int,
        previous: FileState | None,
        extra: dict[str, Any] | None = None,
        *,
        read_ns: int,
    ) -> dict[str, Any] | None:
        """Compress ``content`` as the new version of ``item`` and decide its action.

        ``read_ns`` is the time just before the file was read, for the racy check.
        """
        archived = archive_file_path(self.source.name, item.rel_path)
        staged = self.staged_path(staging, archived)
        prefix_length = previous.size if previous else None
        if self.dry_run and previous is None:
            result = CompressResult(size=size, sha256="", compressed_size=0)  # always "added"
        elif self.dry_run:
            result = hash_file(content, size, prefix_length)
        else:
            result = self._compress(content, staged, size, prefix_length)
            os.utime(staged, ns=(mtime_ns, mtime_ns))
        if previous and result.sha256 == previous.sha256:
            staged.unlink(missing_ok=True)
            entry = self._file_entry(item, "touched", size, mtime_ns, result.sha256, extra)
            return _mark_racy(entry, mtime_ns, read_ns)
        action = "added"
        if previous:
            appended = result.size >= previous.size and result.prefix_sha256 == previous.sha256
            action = "updated" if appended and not (extra and extra.get("kind")) else "versioned"
        entry = _mark_racy(
            self._file_entry(item, action, size, mtime_ns, result.sha256, extra), mtime_ns, read_ns
        )
        entry["compressed_size"] = result.compressed_size
        if action == "versioned" and previous is not None:
            stamp = run_id_stamp(self.run_id)
            version = f"versions/{item.rel_path}.{stamp}-{self.run_id[-4:]}.zst"
            entry["previous_sha256"] = previous.sha256
            entry["previous_size"] = previous.size
            entry["version_path"] = version
            self.moves.append((entry, archived, f"sources/{self.source.name}/{version}"))
        return entry

    def staged_path(self, staging: Path, archived: str) -> Path:
        """Where a file for archive path ``archived`` is staged: under the incoming folder."""
        prefix = f"sources/{self.source.name}/"
        if not archived.startswith(prefix):
            raise ArchiveError(f"{archived} is outside source {self.source.name}")
        return staging / self.incoming / archived[len(prefix) :]

    def _compress(self, content: Path, staged: Path, size: int, prefix_length: int | None):
        level = self.config.compression_level
        if size < LARGE_FILE_BYTES or self.config.workers < 2:
            return compress_file(content, staged, level, size=size, prefix_length=prefix_length)
        with _LARGE_FILE_SLOT:
            return compress_file(
                content,
                staged,
                level,
                size=size,
                prefix_length=prefix_length,
                threads=self.config.workers,
            )

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
        return entry

    # -- committing -------------------------------------------------------------------

    def _flush(self, staging: Path) -> None:
        """Transfer what is staged to the run's incoming folder, then empty the staging folder.

        Nothing at a committed path changes here: files move into place only after the
        run's manifest is written (see ``_commit``).
        """
        if (staging / "sources").exists():
            self.destination.put_tree(staging)
            shutil.rmtree(staging / "sources")
        self.staged_bytes = 0

    def _commit(self, staging: Path) -> None:
        """Finish the run: write its manifest to the incoming folder, place files, commit.

        The manifest in the incoming folder records every move before any is made, so a run
        that stops part way is finished by the next one (``recover_incoming``). A run that
        stops before that manifest is written changed no committed path.
        """
        self._flush(staging)
        self._check_transfer()
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
        self.destination.write_bytes(f"{self.incoming}/{PENDING_MANIFEST}", data)
        # The incoming folder holds only this run's files: earlier ones were cleared at the start.
        finish_run(
            self.destination,
            self.source.name,
            self.run_id,
            self.summary.entries,
            incoming_root(self.source.name),
        )
        self.state.apply_manifest(run, self.summary.entries)
        save_state(self.state_file, self.state)

    def _check_transfer(self) -> None:
        """Before committing: every new copy arrived, and every copy to keep exists.

        A rewritten file whose archived copy is missing (removed outside the collector)
        cannot be kept, so its entry records no version and the run records an error.
        """
        _keeps, puts = placements(self.source.name, self.run_id, self.summary.entries)
        sources = [current for _entry, current, _version in self.moves]
        missing = set(self.destination.missing([incoming for incoming, _ in puts] + sources))
        lost = sorted(incoming for incoming, _ in puts if incoming in missing)
        if lost:
            raise ArchiveError(f"{len(lost)} transferred files are missing, such as {lost[0]}")
        for entry, current, _version in self.moves:
            if current in missing:
                self._drop_version(entry, current)
        self.summary.entries.sort(key=lambda entry: (entry["path"], entry["type"]))

    def _drop_version(self, entry: dict[str, Any], current: str) -> None:
        for key in ("version_path", "previous_sha256", "previous_size"):
            entry.pop(key, None)
        entry["action"] = "added"
        self.summary.versioned -= 1
        self._record(
            {
                "type": "error",
                "path": entry["path"],
                "message": f"the previous archived copy {current} was missing, so it "
                "could not be kept as a version",
            }
        )

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


def is_racy(mtime_ns: int, read_ns: int) -> bool:
    """True when a file was modified within the racy window before it was read."""
    return read_ns - mtime_ns < RACY_WINDOW_NS


def _mark_racy(entry: dict[str, Any], mtime_ns: int, read_ns: int) -> dict[str, Any]:
    if is_racy(mtime_ns, read_ns):
        entry["racy"] = True
    return entry


def _hostname() -> str:
    import socket

    return socket.gethostname()


def _tool_version() -> str:
    try:
        from importlib.metadata import version

        return version("cagelens")
    except Exception:
        return "unknown"
