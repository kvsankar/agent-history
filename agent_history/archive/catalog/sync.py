"""Bring a catalog up to date with an archive by replaying manifests it has not ingested.

Session metadata is extracted once per changed session file, with the same backend parsers
the cagelens commands use; then each run's manifest is applied in one transaction. A session
file that cannot be read, or whose content does not match its manifest's SHA-256, is kept
in ``pending_sessions`` and read again by every later sync until it succeeds. When the
reader version recorded in ``schema_meta`` differs from the current one, every catalogued
session file is queued there too, so rows written by an older reader are replaced.

A source whose manifests cannot be read, or lack a field the catalog records, is
reported in the summary's errors and left unrecorded; the other sources are synced.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_history.archive.catalog.store import CatalogStore
from agent_history.archive.codec import CHUNK_SIZE, _zstd
from agent_history.archive.errors import ArchiveError
from agent_history.archive.layouts import SessionTarget, archive_file_path, session_target
from agent_history.archive.manifest import read_manifests
from agent_history.archive.transport import Destination
from agent_history.storage.metrics import METRICS_PARSER_VERSION

# The catalog's own part of how session files become rows (which archived paths hold
# sessions, how the workspace is derived). Raise it when that changes;
# METRICS_PARSER_VERSION covers the parsers.
_EXTRACTION_REVISION = 3
# Recorded in schema_meta. A catalog whose rows were written under another version has
# every session file read again on its next sync.
READER_VERSION = f"{METRICS_PARSER_VERSION}.{_EXTRACTION_REVISION}"
_READER_VERSION_KEY = "reader_version"

_WRITTEN = ("added", "updated", "versioned")
_PRESENT = (*_WRITTEN, "touched", "returned")


@dataclass
class SyncSummary:
    sources: int = 0
    runs: int = 0
    sessions: int = 0
    errors: list[str] = field(default_factory=list)


def list_sources(destination: Destination) -> list[str]:
    """The folders under sources/ that hold a SOURCE.json, without walking their files."""
    descriptors = {f"sources/{name}/SOURCE.json": name for name in destination.list_dirs("sources")}
    missing = set(destination.missing(list(descriptors)))
    return sorted(name for rel, name in descriptors.items() if rel not in missing)


def sync_catalog(
    store: CatalogStore,
    destination: Destination,
    sources: list[str] | None = None,
    rebuild: bool = False,
    work_dir: Path | None = None,
) -> SyncSummary:
    """Ingest new manifests of ``sources`` (default: every source in the archive).

    ``rebuild`` first deletes those sources' rows, or every row when no sources are named.
    Session files are decompressed into ``work_dir`` (default: under the cagelens config
    folder, not the system temp folder, which is often a small tmpfs).
    """
    available = list_sources(destination)
    unknown = sorted(set(sources or ()) - set(available))
    if unknown:
        raise ArchiveError(f"Not in the archive: {', '.join(unknown)}")
    if work_dir is None:
        from agent_history.storage.config import get_config_dir

        work_dir = get_config_dir() / "archive-work"
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    if rebuild:
        store.clear(sources or None)
    _queue_for_new_reader(store)
    summary = SyncSummary()
    for name in sources or available:
        try:
            _sync_source(store, destination, name, summary, Path(work_dir))
        except ArchiveError as exc:
            summary.errors.append(f"{name}: {exc}")
            continue
        except Exception as exc:  # a defect for one source must not stop the others
            summary.errors.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        summary.sources += 1
    return summary


def _queue_for_new_reader(store: CatalogStore) -> None:
    """Queue every catalogued session file to be read again if the reader has changed.

    A catalog written by another reader version (or by one that recorded none) holds
    rows that the current reader would write differently, and syncs read only new runs.
    So every session file in ``files`` goes to ``pending_sessions`` at its current
    SHA-256, unless it is pending already, and the new version is recorded in the same
    transaction: a sync that stops part way leaves the rest queued for the next sync.
    Session rows of paths that the current layouts no longer read sessions from are
    deleted in that transaction too, since no later read would replace them.
    """
    with store.transaction():
        found = store.fetchall(
            "SELECT value FROM schema_meta WHERE key = ?", (_READER_VERSION_KEY,)
        )
        if found and found[0][0] == READER_VERSION:
            return
        rows = store.fetchall(
            "SELECT f.source, f.path, f.sha256, s.platform FROM files f "
            "JOIN sources s ON s.name = f.source WHERE f.sha256 IS NOT NULL"
        )
        for source, path, sha256, platform in rows:
            if session_target(path, platform) is not None:
                store.execute(
                    "INSERT INTO pending_sessions (source, path, sha256) VALUES (?, ?, ?) "
                    "ON CONFLICT (source, path) DO NOTHING",
                    (source, path, sha256),
                )
        _delete_rows_of_non_session_paths(store)
        store.execute(
            "INSERT INTO schema_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (_READER_VERSION_KEY, READER_VERSION),
        )


def _delete_rows_of_non_session_paths(store: CatalogStore) -> None:
    rows = store.fetchall(
        "SELECT DISTINCT x.source, x.path, s.platform FROM sessions x "
        "JOIN sources s ON s.name = x.source"
    )
    for source, path, platform in rows:
        if session_target(path, platform) is None:
            store.execute("DELETE FROM sessions WHERE source = ? AND path = ?", (source, path))


def _sync_source(store, destination, name: str, summary: SyncSummary, work_dir: Path) -> None:
    descriptor = json.loads(destination.read_bytes(f"sources/{name}/SOURCE.json") or b"{}")
    done = {row[0] for row in store.fetchall("SELECT run_id FROM runs WHERE source = ?", (name,))}
    runs = list(read_manifests(destination, name, skip_run_ids=done))
    # Before anything is written: a bad manifest leaves every new run of the source
    # unrecorded, so the next sync reads them all again once it is fixed.
    for run, entries in runs:
        _check_manifest(run, entries)
    # Files that failed before, then this sync's runs: a newer run's hash replaces a
    # pending one.
    changed: dict[str, str] = dict(
        store.fetchall("SELECT path, sha256 FROM pending_sessions WHERE source = ?", (name,))
    )
    for _run, entries in runs:
        for entry in entries:
            if entry.get("type") == "file" and entry.get("action") in _WRITTEN:
                changed[entry["path"]] = entry["sha256"]
    # Sessions first, runs last: a sync stopped part way records no run, so the next
    # sync reads the same sessions again instead of skipping them.
    _sync_sessions(store, destination, name, descriptor, changed, summary, work_dir)
    for run, entries in runs:
        with store.transaction():
            _upsert_source(store, name, descriptor, run)
            _record_run(store, name, run, entries)
        summary.runs += 1


def _sync_sessions(
    store,
    destination,
    name: str,
    descriptor: dict,
    changed: dict[str, str],
    summary: SyncSummary,
    work_dir: Path,
) -> None:
    platform = descriptor.get("platform", "linux")
    for path, sha256 in sorted(changed.items()):
        target = session_target(path, platform)
        if target is None:
            continue
        try:
            rows = _extract_sessions(destination, name, path, target, sha256, work_dir)
        except Exception as exc:  # one bad file must not stop the sync
            summary.errors.append(f"{name}:{path}: {exc}")
            _mark_pending(store, name, path, sha256, exc)
            continue
        with store.transaction():
            store.execute("DELETE FROM sessions WHERE source = ? AND path = ?", (name, path))
            for row in rows:
                _insert_session(store, row)
            store.execute(
                "DELETE FROM pending_sessions WHERE source = ? AND path = ?", (name, path)
            )
        summary.sessions += len(rows)


def _mark_pending(store, source: str, path: str, sha256: str, exc: Exception) -> None:
    with store.transaction():
        store.execute(
            "INSERT INTO pending_sessions (source, path, sha256, error_type) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (source, path) DO UPDATE SET "
            "sha256 = excluded.sha256, error_type = excluded.error_type",
            (source, path, sha256, type(exc).__name__),
        )


def _upsert_source(store, name: str, descriptor: dict, run: dict) -> None:
    started = _timestamp(run.get("started_at"))
    store.execute(
        "INSERT INTO sources (name, kind, platform, note, first_run_at, last_run_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (name) DO UPDATE SET "
        "kind = excluded.kind, platform = excluded.platform, note = excluded.note, "
        "last_run_at = excluded.last_run_at",
        (
            name,
            descriptor.get("kind", "live"),
            descriptor.get("platform", "linux"),
            descriptor.get("note", ""),
            started,
            started,
        ),
    )


def _record_run(store, source: str, run: dict, entries: list[dict]) -> None:
    run_id = run["run_id"]
    store.execute(
        "INSERT INTO runs (run_id, source, collector_host, tool_version, started_at, "
        "finished_at, written, errors) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            source,
            run.get("collector_host"),
            run.get("tool_version"),
            _timestamp(run.get("started_at")),
            _timestamp(run.get("finished_at")),
            run.get("written"),
            run.get("errors"),
        ),
    )
    for entry in entries:
        if entry.get("type") == "rows":
            _record_rows(store, source, run_id, entry)
        elif entry.get("type") == "file":
            _record_file(store, source, run_id, entry)


def _check_manifest(run: dict, entries: list[dict]) -> None:
    """Raise ArchiveError naming the run, path and field of an entry the catalog cannot record."""
    run_id = run.get("run_id")
    for entry in entries:
        kind = entry.get("type")
        if kind not in ("file", "rows"):
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            raise ArchiveError(f"Run {run_id}'s manifest has a {kind} entry without a path")
        if kind == "file" and entry.get("action") == "versioned":
            version_path = entry.get("version_path")
            if not isinstance(version_path, str) or not version_path:
                raise ArchiveError(
                    f"Run {run_id} versions {path} but its manifest gives no version_path"
                )
        for name in _required_fields(kind, entry):
            if entry.get(name) is None:
                raise ArchiveError(f"Run {run_id}'s manifest gives no {name} for {path}")


def _required_fields(kind: str, entry: dict) -> tuple[str, ...]:
    """The fields, besides the path, that the catalog reads from a manifest entry."""
    if kind == "rows":
        return ("export_path", "table") if entry.get("rows") else ()
    if "action" not in entry:
        return ("action",)
    return ("size", "mtime_ns", "sha256") if entry["action"] in _PRESENT else ()


def _record_file(store, source: str, run_id: str, entry: dict) -> None:
    path, action = entry["path"], entry["action"]
    if action == "gone":
        store.execute(
            "UPDATE files SET gone_run_id = ? WHERE source = ? AND path = ?", (run_id, source, path)
        )
        return
    if action not in _PRESENT:
        return
    archive_path = archive_file_path(source, path)
    store.execute(
        "INSERT INTO files (source, path, agent, kind, size, mtime_ns, sha256, compressed_size, "
        "archive_path, first_run_id, last_written_run_id, gone_run_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL) ON CONFLICT (source, path) DO UPDATE SET "
        "agent = excluded.agent, kind = excluded.kind, size = excluded.size, "
        "mtime_ns = excluded.mtime_ns, sha256 = excluded.sha256, "
        "compressed_size = COALESCE(excluded.compressed_size, files.compressed_size), "
        "last_written_run_id = COALESCE(excluded.last_written_run_id, files.last_written_run_id), "
        "gone_run_id = NULL",
        (
            source,
            path,
            entry.get("agent"),
            entry.get("kind", "file"),
            entry["size"],
            entry["mtime_ns"],
            entry["sha256"],
            entry.get("compressed_size"),
            archive_path,
            run_id,
            run_id if action in _WRITTEN else None,
        ),
    )
    if action not in _WRITTEN:
        return
    kept = f"sources/{source}/{entry['version_path']}" if action == "versioned" else None
    store.execute(
        "UPDATE file_versions SET superseded_run_id = ?, archive_path = ? "
        "WHERE source = ? AND path = ? AND superseded_run_id IS NULL",
        (run_id, kept, source, path),
    )
    store.execute(
        "INSERT INTO file_versions (source, path, run_id, sha256, size, mtime_ns, archive_path, "
        "superseded_run_id) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        (source, path, run_id, entry["sha256"], entry["size"], entry["mtime_ns"], archive_path),
    )


def _record_rows(store, source: str, run_id: str, entry: dict) -> None:
    store.execute(
        "INSERT INTO files (source, path, agent, kind, first_run_id, last_written_run_id) "
        "VALUES (?, ?, ?, 'sqlite-log', ?, ?) ON CONFLICT (source, path) DO UPDATE SET "
        "last_written_run_id = excluded.last_written_run_id, gone_run_id = NULL",
        (source, entry["path"], entry.get("agent"), run_id, run_id),
    )
    if not entry.get("rows"):
        return
    store.execute(
        "INSERT INTO row_exports (source, archive_path, path, table_name, from_key, to_key, "
        "row_count, was_reset, run_id, sha256, size) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            source,
            f"sources/{source}/files/{entry['export_path']}.zst",
            entry["path"],
            entry["table"],
            _text(entry.get("from_key")),
            _text(entry.get("to_key")),
            entry["rows"],
            bool(entry.get("reset")),
            run_id,
            entry.get("sha256"),
            entry.get("size"),
        ),
    )


# -- session extraction ---------------------------------------------------------------


def _extract_sessions(
    destination: Destination,
    source: str,
    path: str,
    target: SessionTarget,
    sha256: str,
    work_dir: Path,
) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="session-", dir=work_dir) as tmp:
        local = Path(tmp) / path  # keep folder names: some parsers read them
        local.parent.mkdir(parents=True, exist_ok=True)
        _decompress_checked(destination, archive_file_path(source, path), local, sha256)
        base = {"source": source, "path": path, "agent": target.backend, "file_sha256": sha256}
        if target.database is not None:
            return [
                {**base, **row}
                for row in _database_sessions(local, str(target.database.sessions_sql))
            ]
        return [{**base, **_file_session(local, target.backend, target.workspace)}]


class ContentMismatchError(Exception):
    """An archived file's content differs from the SHA-256 its manifest records."""


def _decompress_checked(destination: Destination, archived: str, local: Path, sha256: str):
    """Decompress ``archived`` into ``local``, checking the content's SHA-256.

    A mismatch usually means a collect is rewriting the file and has not yet written the
    manifest that describes the new content.
    """
    digest = hashlib.sha256()
    with destination.open_binary(archived) as raw, local.open("wb") as out:
        with _zstd().ZstdDecompressor().stream_reader(raw) as reader:
            while chunk := reader.read(CHUNK_SIZE):
                digest.update(chunk)
                out.write(chunk)
    if digest.hexdigest() != sha256:
        raise ContentMismatchError(
            f"content does not match the manifest's SHA-256 {sha256[:12]}; "
            "a collect may be rewriting it"
        )


def _file_session(local: Path, backend_id: str, workspace: str | None) -> dict[str, Any]:
    """Session metadata of one session file.

    ``workspace`` is the workspace the archived path names, if any. Each backend's
    resolver may prefer what the file records (such as its working directory); without
    it, the Claude and Gemini resolvers fall back to the file's parent folder, which for
    a sub-agent is ``subagents`` and for a Gemini chat is ``chats``.
    """
    from agent_history.backends.registry import get_backend

    backend = get_backend(backend_id)
    if backend is None:
        raise ValueError(f"No cagelens backend {backend_id}")
    stats, messages, tool_uses = backend.extract_stats(local)
    stats = stats or {}
    try:
        workspace = backend.resolve_stats_workspace(local, stats, workspace)
    except Exception:
        pass
    models = sorted({str(m["model"]) for m in messages if m.get("model")})
    return {
        "session_id": stats.get("session_id") or local.name.split(".")[0],
        "from_database": False,
        "workspace": workspace,
        "cwd": stats.get("cwd"),
        "git_branch": stats.get("git_branch"),
        "models": json.dumps(models),
        "first_timestamp": _timestamp(stats.get("first_timestamp")),
        "last_timestamp": _timestamp(stats.get("last_timestamp")),
        "message_count": stats.get("message_count"),
        "user_messages": stats.get("user_messages"),
        "assistant_messages": stats.get("assistant_messages"),
        "tool_uses": len(tool_uses),
        "input_tokens": stats.get("input_tokens"),
        "output_tokens": stats.get("output_tokens"),
        "cache_read_tokens": stats.get("cache_read_tokens"),
        "cache_creation_tokens": stats.get("cache_creation_tokens"),
        "parent_session_id": stats.get("parent_session_id"),
        "is_subagent": bool(stats.get("is_agent")),
    }


def _database_sessions(local: Path, sql: str) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(local)) as conn:
        rows = conn.execute(sql).fetchall()
    return [
        {
            "session_id": str(session_id),
            "from_database": True,
            "cwd": cwd,
            "git_branch": branch,
            "first_timestamp": _timestamp(first),
            "last_timestamp": _timestamp(last),
            "message_count": count,
        }
        for session_id, cwd, branch, first, last, count in rows
        if session_id is not None
    ]


_SESSION_COLUMNS = (
    "source",
    "path",
    "session_id",
    "agent",
    "from_database",
    "workspace",
    "cwd",
    "git_branch",
    "models",
    "first_timestamp",
    "last_timestamp",
    "message_count",
    "user_messages",
    "assistant_messages",
    "tool_uses",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
    "parent_session_id",
    "is_subagent",
    "file_sha256",
)


def _insert_session(store: CatalogStore, row: dict[str, Any]) -> None:
    placeholders = ", ".join("?" for _ in _SESSION_COLUMNS)
    store.execute(
        f"INSERT INTO sessions ({', '.join(_SESSION_COLUMNS)}) VALUES ({placeholders}) "
        "ON CONFLICT (source, path, session_id) DO NOTHING",
        tuple(row.get(column) for column in _SESSION_COLUMNS),
    )


# -- value normalisation ----------------------------------------------------------------


def _timestamp(value: Any) -> str | None:
    """ISO 8601 UTC text for ISO strings and epoch seconds or milliseconds; else None."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            seconds = value / 1000 if value > 1e11 else value
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        sys.stderr.write(f"Warning: unreadable timestamp {value!r}\n")
        return None


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def catalog_status(store: CatalogStore, sources: list[str] | None = None) -> list[dict[str, Any]]:
    """Counts and the newest run per source, for ``sources`` (default: every source).

    A named source that the catalog does not hold is an error, as it is for sync.
    """
    rows = store.fetchall(
        "SELECT s.name, s.kind, "
        "(SELECT COUNT(*) FROM runs r WHERE r.source = s.name), "
        "(SELECT COUNT(*) FROM files f WHERE f.source = s.name), "
        "(SELECT COUNT(*) FROM files f WHERE f.source = s.name AND f.gone_run_id IS NOT NULL), "
        "(SELECT COUNT(*) FROM sessions x WHERE x.source = s.name), "
        "(SELECT MAX(started_at) FROM runs r WHERE r.source = s.name) "
        "FROM sources s ORDER BY s.name"
    )
    unknown = sorted(set(sources or ()) - {row[0] for row in rows})
    if unknown:
        raise ArchiveError(f"Not in the catalog: {', '.join(unknown)}")
    return [
        {
            "source": name,
            "kind": kind,
            "runs": runs,
            "files": files,
            "gone": gone,
            "sessions": sessions,
            "last_run_at": _timestamp(last if not isinstance(last, datetime) else last.isoformat()),
        }
        for name, kind, runs, files, gone, sessions, last in rows
        if not sources or name in sources
    ]
