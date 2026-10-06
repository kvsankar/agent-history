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
import re
import secrets
import socket
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from agent_history.archive.errors import ArchiveError
from agent_history.archive.transport import (
    LOCK_FOLDER,
    LOCK_OWNER,
    Destination,
    fsync_dir,
    fsync_file,
)

# log_keys["<path>::<table>" + IDENTITY_SUFFIX] identifies the log table's rows (see databases).
IDENTITY_SUFFIX = "::identity"


class CollectLockedError(ArchiveError):
    """Another run for the same source and destination is in progress."""


BREAK_LOCK_OPTION = "--break-lock"


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
    last_success: str | None = None  # start of the last run that recorded no errors
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
        if run.get("started_at") and not run.get("errors"):
            self.last_success = run["started_at"]  # a run with errors is retried sooner

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
    if action == "displaced":  # its copy is now a version, so if it returns it is new
        state.files.pop(path, None)
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
    """The state in ``path``; None when it is missing or cannot be used.

    A state file that cannot be read, is not JSON, or has another shape (for example a
    field from a newer version, or a value of another type) is a damaged cache: the
    caller rebuilds the state from the manifests, and a warning names the file.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        _warn_unusable_state(path, exc)
        return None
    try:
        return _decode_state(data)
    except (TypeError, KeyError, AttributeError, ValueError) as exc:
        _warn_unusable_state(path, exc)
        return None


def _decode_state(data: Any) -> SourceState:
    """The state a decoded state file holds; TypeError or ValueError when it cannot."""
    _expect(data, dict, "the state")
    files = _expect(data.get("files", {}), dict, "files")
    log_keys = _expect(data.get("log_keys", {}), dict, "log_keys")
    last_success = _optional(data.get("last_success"), str, "last_success")
    if last_success is not None and datetime.fromisoformat(last_success).tzinfo is None:
        raise ValueError(f"last_success has no time zone: {last_success}")
    runs = _optional(data.get("runs"), list, "runs")
    for run_id in runs or ():
        _expect(run_id, str, "a run id")
    return SourceState(
        files={_expect(rel, str, "a path"): _decode_file(value) for rel, value in files.items()},
        log_keys=dict(log_keys),
        last_success=last_success,
        last_run_id=_optional(data.get("last_run_id"), str, "last_run_id"),
        runs=None if runs is None else list(runs),
    )


def _decode_file(value: Any) -> FileState:
    file = FileState(**_expect(value, dict, "a file's state"))
    for name, kind in (("size", int), ("mtime_ns", int), ("sha256", str), ("gone", bool)):
        _expect(getattr(file, name), kind, name)
    for number in _optional(file.signature, list, "signature") or ():
        _expect(number, int, "signature")
    return file


def _expect(value: Any, kind: type, what: str) -> Any:
    # bool is an int in Python, but never a size or a time.
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise TypeError(f"{what} is {type(value).__name__}, not {kind.__name__}")
    return value


def _optional(value: Any, kind: type, what: str) -> Any:
    return None if value is None else _expect(value, kind, what)


def _warn_unusable_state(path: Path, exc: Exception) -> None:
    sys.stderr.write(
        f"Warning: the state file {path} cannot be used ({type(exc).__name__}: {exc}); "
        f"rebuilding it from the archive's manifests\n"
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
    fsync_file(tmp)
    os.replace(tmp, path)
    fsync_dir(path.parent)


def lock_path(state_dir: Path, destination: str, source: str) -> Path:
    return state_path(state_dir, destination, source).with_suffix(".lock")


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


# -- the lock in the archive ----------------------------------------------------------
#
# The local lock keeps apart runs that share a state folder and spell the destination the
# same way. Runs with another state folder, another spelling of the destination, or on
# another machine with the same source name share only the archive, so a run also holds
# sources/<source>/LOCK/owner.json there while it changes the source's folder. The owner
# file is the lock: it is created exclusively with its content (Destination.create_lock),
# and a LOCK folder without one is no lock.

# Seconds to wait before reading again an owner file that is empty or does not parse: the
# run that created it may be writing it at this moment.
LOCK_SETTLE_SECONDS = 2.0
_LOCK_ATTEMPTS = 3
# A lock of another holder that started longer ago than this, or at a time its owner file
# does not tell, fails the run instead of skipping it: its run was most likely stopped,
# and only --break-lock removes it, so skipping would skip every run from then on.
STALE_LOCK_HOURS = 24


class LockOwnerUnknownError(ArchiveError):
    """A source's lock in the archive exists, but its owner file names no holder."""


class StaleLockError(ArchiveError):
    """A source's lock in the archive names another holder whose run looks stopped."""


def destination_lock_path(source: str) -> str:
    return f"sources/{source}/{LOCK_FOLDER}"


@contextmanager
def destination_lock(
    destination: Destination,
    source: str,
    local_lock: Path,
    collector: str,
    break_lock: bool = False,
    now: datetime | None = None,
) -> Iterator[None]:
    """Hold the source's lock in the archive.

    ``collector`` is the state folder's id (collector_id), and ``local_lock`` the local
    lock this process holds. Raises CollectLockedError when another run holds the lock,
    StaleLockError when that run started more than STALE_LOCK_HOURS before ``now`` or at
    an unknown time, and LockOwnerUnknownError when the owner file stays empty or
    damaged, so no holder can be named. A lock that a killed run of this collector left
    is taken over: one whose owner records this state folder's id, this local lock and
    this host. The id is random, so another machine with the same host name and state
    path (a second WSL distribution on one PC) is another holder. ``break_lock`` first
    removes any lock.
    """
    ours = _lock_owner(local_lock, collector)
    if break_lock:
        _break_lock(destination, source)
    _take_lock(destination, source, ours, now or datetime.now(timezone.utc))
    try:
        yield
    finally:
        _release_lock(destination, source, ours)


def _take_lock(destination: Destination, source: str, ours: dict[str, Any], now: datetime) -> None:
    rel = destination_lock_path(source)
    for _ in range(_LOCK_ATTEMPTS):
        if destination.create_lock(rel, json.dumps(ours).encode("utf-8")):
            return
        held = _settled_owner(destination, source)
        if held is None:
            continue  # released meanwhile
        if not _same_collector(held, ours):
            raise _foreign_lock_error(destination, source, held, now)
        sys.stderr.write(
            f"Removing the lock of {source} left by an interrupted run on this machine "
            f"(started {held.get('started_at', 'at an unknown time')})\n"
        )
        destination.remove_lock(rel)
    raise CollectLockedError(
        _locked_message(destination, source, read_lock_owner(destination, source))
    )


def _settled_owner(destination: Destination, source: str) -> dict[str, Any] | None:
    """The holder a lock records; None when the lock has gone.

    An owner file that is empty or does not parse is read again after a pause, in case
    its run is writing it. If it still names no holder, LockOwnerUnknownError.
    """
    for attempt in range(2):
        if attempt:
            time.sleep(LOCK_SETTLE_SECONDS)
        data = destination.read_bytes(f"{destination_lock_path(source)}/{LOCK_OWNER}")
        if data is None:
            return None
        owner = _parse_owner(data)
        if owner:
            return owner
    raise LockOwnerUnknownError(
        f"The lock of {source} in {destination.description} names no holder: its "
        f"{LOCK_FOLDER}/{LOCK_OWNER} is empty or damaged, for example because a run was "
        f"stopped while it took the lock. If no archive run of {source} is going on any "
        f"machine, run collect again with {BREAK_LOCK_OPTION}."
    )


def read_lock_owner(destination: Destination, source: str) -> dict[str, Any]:
    """What a source's lock records about its holder; empty when unknown."""
    data = destination.read_bytes(f"{destination_lock_path(source)}/{LOCK_OWNER}")
    return _parse_owner(data) if data is not None else {}


def _parse_owner(data: bytes) -> dict[str, Any]:
    try:
        owner = json.loads(data.decode("utf-8"))
    except ValueError:
        return {}
    return owner if isinstance(owner, dict) else {}


def _lock_owner(local_lock: Path, collector: str) -> dict[str, Any]:
    local_lock = Path(local_lock)
    return {
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "collector_id": collector,  # the state folder
        "local_lock": f"{local_lock.parent.name}/{local_lock.name}",  # within it
        "token": secrets.token_hex(8),  # this run
    }


_COLLECTOR_KEYS = ("collector_id", "local_lock", "host")


def _same_collector(held: dict[str, Any], ours: dict[str, Any]) -> bool:
    """True when ``held`` was written by a run of this state folder, local lock and host.

    An owner file of an earlier version records no collector_id, so it is another
    holder: its identity, a hash of the host name and the local lock path, is the same
    for two machines with the same host name and state path.
    """
    return all(held.get(key) == ours[key] for key in _COLLECTOR_KEYS)


COLLECTOR_ID_FILE = "collector-id"
_COLLECTOR_ID = re.compile(r"[0-9a-f]{32}")


def collector_id(state_dir: Path) -> str:
    """The state folder's random id, made on first use and kept in ``collector-id``.

    A lock in the archive whose owner records this id was taken by a run of this state
    folder. The file is made with a hard link from a complete temporary file, so of two
    runs that make it at once both read the same id; a file that does not hold an id is
    replaced.
    """
    state_dir = Path(state_dir)
    path = state_dir / COLLECTOR_ID_FILE
    found = _read_collector_id(path)
    if found:
        return found
    state_dir.mkdir(parents=True, exist_ok=True)
    made = secrets.token_hex(16)
    tmp = state_dir / f"{COLLECTOR_ID_FILE}.{made}.tmp"
    tmp.write_text(made + "\n", encoding="ascii")
    fsync_file(tmp)
    try:
        _place_collector_id(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    fsync_dir(state_dir)
    return _read_collector_id(path) or made


def _place_collector_id(tmp: Path, path: Path) -> None:
    if path.exists():  # damaged
        os.replace(tmp, path)
        return
    try:
        os.link(tmp, path)
    except FileExistsError:
        pass  # another run made it just now
    except OSError:
        os.replace(tmp, path)  # no hard links here


def _read_collector_id(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None
    return text if _COLLECTOR_ID.fullmatch(text) else None


def _describe_owner(owner: dict[str, Any]) -> str:
    if not owner:
        return "holder unknown"
    return (
        f"host {owner.get('host', 'unknown')}, process {owner.get('pid', 'unknown')}, "
        f"since {owner.get('started_at', 'an unknown time')}"
    )


def _locked_message(destination: Destination, source: str, held: dict[str, Any]) -> str:
    return (
        f"Another archive run for {source} holds its lock in {destination.description} "
        f"({_describe_owner(held)}). If no such run is still going, for example because it "
        f"was killed on another machine, run collect again with {BREAK_LOCK_OPTION}."
    )


def _foreign_lock_error(
    destination: Destination, source: str, held: dict[str, Any], now: datetime
) -> ArchiveError:
    """CollectLockedError for a lock taken recently, StaleLockError otherwise."""
    started = _started_at(held)
    if started is not None and now - started <= timedelta(hours=STALE_LOCK_HOURS):
        return CollectLockedError(_locked_message(destination, source, held))
    when = (
        f"more than {STALE_LOCK_HOURS} hours ago" if started is not None else "at an unknown time"
    )
    return StaleLockError(
        f"The lock of {source} in {destination.description} names another run "
        f"({_describe_owner(held)}), which started {when}, so it was probably stopped "
        f"without releasing the lock. If no archive run of {source} is going on any "
        f"machine, run collect again with {BREAK_LOCK_OPTION}."
    )


def _started_at(owner: dict[str, Any]) -> datetime | None:
    """When the owner's run started; None when the owner file does not tell."""
    value = owner.get("started_at")
    if not isinstance(value, str):
        return None
    try:
        started = datetime.fromisoformat(value)
    except ValueError:
        return None
    return started if started.tzinfo is not None else None


def _break_lock(destination: Destination, source: str) -> None:
    rel = destination_lock_path(source)
    if destination.exists(rel):
        held = read_lock_owner(destination, source)
        sys.stderr.write(f"Removing the lock of {source} ({_describe_owner(held)})\n")
        destination.remove_lock(rel)


def _release_lock(destination: Destination, source: str, ours: dict[str, Any]) -> None:
    """Remove the lock if this run still holds it; a failure here only warns."""
    try:
        if read_lock_owner(destination, source).get("token") != ours["token"]:
            sys.stderr.write(
                f"Warning: the lock of {source} was taken over by another run; left in place\n"
            )
            return
        destination.remove_lock(destination_lock_path(source))
    except (ArchiveError, OSError) as exc:
        sys.stderr.write(
            f"Warning: could not remove the lock of {source}: {exc}. The next run on this "
            f"machine removes it.\n"
        )


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
