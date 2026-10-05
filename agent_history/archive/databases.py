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
import shutil
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
    with tempfile.TemporaryDirectory(prefix="db-", dir=run.work_root) as tmp:
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
    """Copy a live database consistently, without writing to the source folder.

    Some filesystems (WSL's /mnt/c) cannot open a WAL database read-only. Then the file and
    its WAL are copied to local disk first, and the copy is checked before it is used.
    """
    try:
        with closing(_open_read_only(src)) as source, closing(sqlite3.connect(dst)) as target:
            source.backup(target)
    except sqlite3.OperationalError:
        dst.unlink(missing_ok=True)
        _backup_from_copy(src, dst)
    with closing(sqlite3.connect(dst)) as target:
        target.execute("PRAGMA journal_mode=DELETE")


def _open_read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
    except sqlite3.Error:
        conn.close()
        raise
    return conn


def _backup_from_copy(src: Path, dst: Path, attempts: int = 3) -> None:
    copy = dst.with_name("source-copy.db")
    wal = src.with_name(src.name + "-wal")
    for _ in range(attempts):
        before = database_signature(src)
        shutil.copyfile(src, copy)
        copy_wal = copy.with_name(copy.name + "-wal")
        copy_wal.unlink(missing_ok=True)
        if wal.exists():
            shutil.copyfile(wal, copy_wal)
        if database_signature(src) != before:
            continue  # written while copying; try again
        with closing(sqlite3.connect(copy)) as conn:
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                continue
            with closing(sqlite3.connect(dst)) as target:
                conn.backup(target)
        return
    raise sqlite3.OperationalError(f"{src} kept changing or failed its check while being copied")


def blank_credentials(path: Path, rule: DatabaseRule) -> list[str]:
    """Blank credential columns, then VACUUM; return the "table.column" names.

    A column that allows NULL is set to NULL. A NOT NULL column gets an empty value of
    its type. A column in a UNIQUE index or primary key, or one whose CHECK constraint
    refuses the empty value, gets a random value per row instead, so no row is replaced
    or refused. Each column is committed on its own, so a refused update cannot undo
    another column's blanking.
    """
    named = {entry.lower() for entry in rule.blank_columns}
    blanked = []
    with closing(sqlite3.connect(path)) as conn:
        for table in _plain_tables(conn):
            unique = _unique_columns(conn, table)
            for column, declared, not_null in _column_info(conn, table):
                qualified = f"{table}.{column}"
                if qualified.lower() in named or _looks_like_credential(column):
                    _blank_column(conn, table, column, declared, not_null, column in unique)
                    blanked.append(qualified)
        conn.execute("VACUUM")
    return sorted(blanked)


def _blank_column(conn, table: str, column: str, declared: str, not_null: bool, unique: bool):
    update = f"UPDATE {_quote(table)} SET {_quote(column)} = "
    where = f" WHERE {_quote(column)} IS NOT NULL"
    empty, random = _blank_values(declared)
    if not not_null:
        conn.execute(update + "NULL" + where)
    elif unique:
        conn.execute(update + random + where)
    else:
        try:
            conn.execute(update + empty + where)
        except sqlite3.IntegrityError:  # a CHECK constraint refuses the empty value
            conn.rollback()
            conn.execute(update + random + where)
    conn.commit()


def _blank_values(declared: str) -> tuple[str, str]:
    """SQL for an empty value and a random per-row value of a column's declared type.

    The type follows SQLite's affinity rules, so the values also suit STRICT tables.
    """
    upper = declared.upper()
    if "INT" in upper:
        return "0", "random()"
    if "CHAR" in upper or "CLOB" in upper or "TEXT" in upper:
        return "''", "lower(hex(randomblob(16)))"
    if "BLOB" in upper:
        return "zeroblob(0)", "randomblob(16)"
    if "REAL" in upper or "FLOA" in upper or "DOUB" in upper:
        return "0.0", "random() * 1.0"
    if not upper or upper == "ANY":
        return "''", "lower(hex(randomblob(16)))"
    return "0", "random()"  # NUMERIC affinity


def _looks_like_credential(column: str) -> bool:
    lowered = column.lower()
    return any(marker in lowered for marker in CREDENTIAL_COLUMN_MARKERS)


def _plain_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [name for name, sql in rows if not (sql or "").upper().startswith("CREATE VIRTUAL")]


def _column_info(conn: sqlite3.Connection, table: str) -> list[tuple[str, str, bool]]:
    """(name, declared type, NOT NULL) for each column of a table."""
    rows = conn.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    return [(row[1], row[2] or "", bool(row[3])) for row in rows]


def _unique_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Columns of a table that are part of its primary key or of any UNIQUE index."""
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({_quote(table)})") if row[5]}
    for index in conn.execute(f"PRAGMA index_list({_quote(table)})").fetchall():
        if index[2]:
            info = conn.execute(f"PRAGMA index_info({_quote(index[1])})").fetchall()
            columns.update(row[2] for row in info if row[2] is not None)
    return columns


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
