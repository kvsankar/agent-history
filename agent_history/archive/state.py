"""Per-source collector state and the lock that keeps runs of one source apart.

The state file is a local cache of what the archive already holds for a source. The
manifests in the archive are the authority: a missing state file is rebuilt from them, and
each run applies the manifests the state does not include yet. The state lists the runs it
includes, so a run can tell when the archive lacks one of them.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

from agent_history.archive.errors import ArchiveError

# log_keys["<path>::<table>" + IDENTITY_SUFFIX] identifies the log table's rows (see databases).
IDENTITY_SUFFIX = "::identity"


class CollectLockedError(ArchiveError):
    """Another run for the same source and destination is in progress."""


@dataclass
class FileState:
    size: int
    mtime_ns: int
    sha256: str
    gone: bool = False
    signature: list[int] | None = None  # databases: size/mtime of the file and its WAL


@dataclass
class SourceState:
    files: dict[str, FileState] = field(default_factory=dict)
    log_keys: dict[str, Any] = field(default_factory=dict)  # "<path>::<table>" -> last key
    last_success: str | None = None
    last_run_id: str | None = None
    # Ids of the runs whose manifests this state includes. None for a state file written
    # before the list existed; such a state includes every run up to ``last_run_id``.
    runs: list[str] | None = field(default_factory=list)

    def apply_manifest(self, run: dict[str, Any], entries: list[dict[str, Any]]) -> None:
        """Update this state with one run's manifest."""
        for entry in entries:
            _apply_entry(self, entry)
        self.last_run_id = run.get("run_id")
        if self.runs is not None and self.last_run_id and self.last_run_id not in self.runs:
            self.runs.append(self.last_run_id)
        if run.get("started_at"):
            self.last_success = run["started_at"]

    def has_history(self) -> bool:
        """True when the state records any run to its destination."""
        return bool(self.last_run_id or self.runs or self.files or self.log_keys)

    def applied_runs(self, committed: list[str]) -> set[str]:
        """The ids among ``committed`` that this state already includes."""
        if self.runs is not None:
            return set(self.runs)
        last = self.last_run_id
        return {run_id for run_id in committed if last and run_id <= last}


def _apply_entry(state: SourceState, entry: dict[str, Any]) -> None:
    kind = entry.get("type")
    path = str(entry.get("path"))
    racy = bool(entry.get("racy"))  # not trusted: the next run checks the file again
    if kind == "rows":
        state.log_keys[f"{path}::{entry['table']}"] = entry["to_key"]
        if entry.get("identity"):  # lets the next run tell a recreated table
            state.log_keys[f"{path}::{entry['table']}{IDENTITY_SUFFIX}"] = entry["identity"]
        state.files[path] = FileState(0, 0, "", signature=None if racy else entry.get("signature"))
        return
    if kind != "file":
        return
    action = entry.get("action")
    if action == "gone":
        if path in state.files:
            state.files[path].gone = True
        return
    if action in ("added", "updated", "versioned", "touched", "returned"):
        state.files[path] = FileState(
            size=entry["size"],
            mtime_ns=-1 if racy else entry["mtime_ns"],
            sha256=entry["sha256"],
            signature=None if racy else entry.get("signature"),
        )


def destination_key(destination: str) -> str:
    return hashlib.sha256(destination.encode("utf-8")).hexdigest()[:16]


def state_path(state_dir: Path, destination: str, source: str) -> Path:
    return Path(state_dir) / destination_key(destination) / f"{source}.json"


def load_state(path: Path) -> SourceState | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None  # a damaged cache is rebuilt from the manifests
    files = {rel: FileState(**value) for rel, value in data.get("files", {}).items()}
    return SourceState(
        files=files,
        log_keys=dict(data.get("log_keys", {})),
        last_success=data.get("last_success"),
        last_run_id=data.get("last_run_id"),
        runs=list(data["runs"]) if isinstance(data.get("runs"), list) else None,
    )


def save_state(path: Path, state: SourceState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "files": {rel: asdict(value) for rel, value in sorted(state.files.items())},
        "log_keys": state.log_keys,
        "last_success": state.last_success,
        "last_run_id": state.last_run_id,
        "runs": state.runs,
    }
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


@contextmanager
def source_lock(state_dir: Path, destination: str, source: str) -> Iterator[None]:
    """Hold an exclusive, non-blocking lock for one source and destination."""
    lock_path = state_path(state_dir, destination, source).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        try:
            _lock(handle)
        except OSError as exc:
            raise CollectLockedError(f"Another archive run for {source} is in progress") from exc
        try:
            yield
        finally:
            _unlock(handle)
    finally:
        handle.close()


def _lock(handle) -> None:
    if platform.system() == "Windows":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle) -> None:
    if platform.system() == "Windows":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        except OSError:
            pass
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
