"""Archiving agent SQLite databases.

*Snapshot* databases are copied with SQLite's backup API, which gives a consistent copy
that includes the write-ahead log. Credential columns are blanked in the copy, and the copy
is vacuumed so the blanked values do not survive in free pages.

*Log* databases keep a rolling window of rows. For those, each run exports only rows whose
key is above the last exported key, as JSON Lines.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_history.archive.codec import compress_file
from agent_history.archive.manifest import run_stamp

if TYPE_CHECKING:
    from agent_history.archive.collect import _Run
    from agent_history.archive.layouts import DatabaseRule, SelectedFile

# A column is blanked when its lower-cased name contains any of these.
CREDENTIAL_COLUMN_MARKERS = (
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "apikey",
    "secret",
    "password",
)


def process_database(run: _Run, item: SelectedFile, staging: Path) -> dict[str, Any] | None:
    """Archive one database for a collector run; None when it has not changed."""
    rule = item.database
    assert rule is not None
    signature = database_signature(item.path)
    previous = run.state.files.get(item.rel_path)
    if previous is not None and previous.signature == signature:
        return None
    with tempfile.TemporaryDirectory(prefix="cagelens-db-") as tmp:
        snapshot = Path(tmp) / "snapshot.db"
        backup_database(item.path, snapshot)
        if rule.mode == "log":
            return _export_new_rows(run, item, rule, snapshot, staging, signature)
        blanked = blank_credentials(snapshot, rule)
        extra: dict[str, Any] = {
            "kind": "sqlite-snapshot",
            "blanked": blanked,
            "signature": signature,
        }
        if signature_is_racy(signature):
            extra["racy"] = True
        return run.stage_file(
            item,
            snapshot,
            staging,
            snapshot.stat().st_size,
            item.path.stat().st_mtime_ns,
            previous,
            extra,
        )


def database_signature(path: Path) -> list[int]:
    """Size and modification time of a database file and of its WAL, if any.

    An empty WAL counts as none: opening a WAL database, even read-only, can create one.
    """
    stat = path.stat()
    wal = path.with_name(path.name + "-wal")
    wal_stat = wal.stat() if wal.exists() else None
    if wal_stat is not None and wal_stat.st_size == 0:
        wal_stat = None
    return [
        stat.st_size,
        stat.st_mtime_ns,
        wal_stat.st_size if wal_stat else -1,
        wal_stat.st_mtime_ns if wal_stat else -1,
    ]


def signature_is_racy(signature: list[int]) -> bool:
    from agent_history.archive.collect import is_racy

    return is_racy(signature[1]) or (signature[3] >= 0 and is_racy(signature[3]))


def backup_database(src: Path, dst: Path) -> None:
    """Copy a live database consistently, without writing to the source folder."""
    source = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)
    with closing(source), closing(sqlite3.connect(dst)) as target:
        source.backup(target)
    with closing(sqlite3.connect(dst)) as target:
        target.execute("PRAGMA journal_mode=DELETE")


def blank_credentials(path: Path, rule: DatabaseRule) -> list[str]:
    """Set credential columns to NULL, then VACUUM; return the "table.column" names."""
    named = {entry.lower() for entry in rule.blank_columns}
    blanked = []
    with closing(sqlite3.connect(path)) as conn:
        for table in _plain_tables(conn):
            for column in _columns(conn, table):
                qualified = f"{table}.{column}"
                if qualified.lower() in named or _looks_like_credential(column):
                    conn.execute(
                        f"UPDATE {_quote(table)} SET {_quote(column)} = NULL "
                        f"WHERE {_quote(column)} IS NOT NULL"
                    )
                    blanked.append(qualified)
        conn.commit()
        conn.execute("VACUUM")
    return sorted(blanked)


def _looks_like_credential(column: str) -> bool:
    lowered = column.lower()
    return any(marker in lowered for marker in CREDENTIAL_COLUMN_MARKERS)


def _plain_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [name for name, sql in rows if not (sql or "").upper().startswith("CREATE VIRTUAL")]


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({_quote(table)})")]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _export_new_rows(
    run: _Run,
    item: SelectedFile,
    rule: DatabaseRule,
    snapshot: Path,
    staging: Path,
    signature: list[int],
) -> dict[str, Any]:
    table, key = str(rule.log_table), str(rule.log_key)
    state_key = f"{item.rel_path}::{table}"
    last = run.state.log_keys.get(state_key)
    with closing(sqlite3.connect(snapshot)) as conn:
        newest = conn.execute(f"SELECT MAX({_quote(key)}) FROM {_quote(table)}").fetchone()[0]
        reset = last is not None and newest is not None and newest < last
        start = None if reset else last
        entry: dict[str, Any] = {
            "type": "rows",
            "path": item.rel_path,
            "agent": item.agent,
            "table": table,
            "key": key,
            "from_key": start,
            "to_key": last if newest is None else newest,
            "reset": reset,
            "signature": signature,
            "rows": 0,
        }
        if signature_is_racy(signature):
            entry["racy"] = True
        jsonl = snapshot.with_suffix(".jsonl")
        count = _write_rows(conn, table, key, start, jsonl)
    if count == 0:
        entry["to_key"] = last if not reset else newest
        return entry
    export_path = f"{item.rel_path}.rows/{run_stamp(run.now)}-{run.run_id[-4:]}.jsonl"
    result = compress_file(
        jsonl,
        staging / f"sources/{run.source.name}/files/{export_path}.zst",
        run.config.compression_level,
    )
    entry.update(
        rows=count,
        export_path=export_path,
        sha256=result.sha256,
        size=result.size,
        compressed_size=result.compressed_size,
    )
    return entry


def _write_rows(conn, table: str, key: str, start, out: Path) -> int:
    query = f"SELECT * FROM {_quote(table)}"
    params: tuple = ()
    if start is not None:
        query += f" WHERE {_quote(key)} > ?"
        params = (start,)
    cursor = conn.execute(query + f" ORDER BY {_quote(key)}", params)
    names = [column[0] for column in cursor.description]
    count = 0
    with out.open("w", encoding="utf-8") as handle:
        for row in cursor:
            record = {name: _json_value(value) for name, value in zip(names, row)}
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):  # keep BLOBs distinguishable from TEXT
        return {"$base64": base64.b64encode(value).decode("ascii")}
    return value
