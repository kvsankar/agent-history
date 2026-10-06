"""Archiving agent SQLite databases.

*Snapshot* databases are copied with SQLite's backup API, which gives a consistent copy
that includes the write-ahead log. Credential columns are blanked in the copy, and the copy
is vacuumed so the blanked values do not survive in free pages.

*Log* databases keep a rolling window of rows. For those, each run exports only rows whose
key is above the last exported key, as JSON Lines. Credential columns are set to null, and
JSON Web Tokens inside text values are replaced with a placeholder.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_history.archive.codec import compress_file
from agent_history.archive.manifest import run_id_stamp
from agent_history.archive.state import IDENTITY_SUFFIX

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

# A JSON Web Token (JWT): base64url segments joined by dots, the header starting with
# "eyJ", the base64 of '{"'. A signed token has three segments of at least ten characters.
# A token whose signature is empty or short (an unsecured token, or one a log line cut
# off) matches only when its payload also starts with "eyJ": two dotted segments that
# both decode to JSON objects do not occur in ordinary text.
JWT_PATTERN = re.compile(
    r"eyJ[A-Za-z0-9_-]{10,}\."
    r"(?:[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|eyJ[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]*)?)"
)
JWT_PLACEHOLDER = "[redacted-jwt]"


def process_database(run: _Run, item: SelectedFile, staging: Path) -> dict[str, Any] | None:
    """Archive one database for a collector run; None when it has not changed."""
    rule = item.database
    assert rule is not None
    read_ns = time.time_ns()  # before reading: a slow copy must not hide a recent write
    signature = database_signature(item.path)
    previous = run.state.files.get(item.rel_path)
    if previous is not None and previous.signature == signature:
        return None
    with tempfile.TemporaryDirectory(prefix="db-", dir=run.work_root) as tmp:
        snapshot = Path(tmp) / "snapshot.db"
        backup_database(item.path, snapshot)
        if rule.mode == "log":
            return _export_new_rows(run, item, rule, snapshot, staging, signature, read_ns)
        blanked = blank_credentials(snapshot, rule)
        extra: dict[str, Any] = {
            "kind": "sqlite-snapshot",
            "blanked": blanked,
            "signature": signature,
        }
        if signature_is_racy(signature, read_ns):
            extra["racy"] = True
        return run.stage_file(
            item,
            snapshot,
            staging,
            snapshot.stat().st_size,
            item.path.stat().st_mtime_ns,
            previous,
            extra,
            read_ns=read_ns,
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


def signature_is_racy(signature: list[int], read_ns: int) -> bool:
    """True when the database or its WAL was modified just before ``read_ns``."""
    from agent_history.archive.collect import is_racy

    return is_racy(signature[1], read_ns) or (signature[3] >= 0 and is_racy(signature[3], read_ns))


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
    read_ns: int,
) -> dict[str, Any]:
    table, key = str(rule.log_table), str(rule.log_key)
    state_key = f"{item.rel_path}::{table}"
    last = run.state.log_keys.get(state_key)
    known = run.state.log_keys.get(state_key + IDENTITY_SUFFIX)
    with closing(sqlite3.connect(snapshot)) as conn:
        newest = conn.execute(f"SELECT MAX({_quote(key)}) FROM {_quote(table)}").fetchone()[0]
        reset = _was_recreated(conn, table, key, last, known, newest)
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
        if signature_is_racy(signature, read_ns):
            entry["racy"] = True
        jsonl = snapshot.with_suffix(".jsonl")
        count, blanked, redacted = _write_rows(conn, rule, start, jsonl)
        if blanked:
            entry["blanked"] = blanked
        if redacted:
            entry["redacted"] = {"jwt": redacted}
        if count == 0:
            entry["to_key"] = last if not reset else newest
        identity = _table_identity(conn, table, key, entry["to_key"])
        if identity is not None:
            entry["identity"] = identity
    if count == 0:
        return entry
    if run.dry_run:  # a dry run reports what it would export and compresses nothing
        entry["rows"] = count
        return entry
    export_path = f"{item.rel_path}.rows/{run_id_stamp(run.run_id)}-{run.run_id[-4:]}.jsonl"
    result = compress_file(
        jsonl,
        run.staged_path(staging, f"sources/{run.source.name}/files/{export_path}.zst"),
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


def _was_recreated(conn, table: str, key: str, last, identity, newest) -> bool:
    """Whether a log table was recreated (or emptied) since the last export.

    A recreated table can grow past the last exported key before the next run, so the
    newest key alone does not show it. ``identity`` (from :func:`_table_identity`)
    records the previous run's smallest key and hashes of the rows at that key and at
    ``last``. The agent deletes its oldest rows and adds rows with larger keys, so the
    smallest key never goes down unless the table starts again. If it has not gone
    down, the table counts as recreated only when both recorded rows are still there
    and both differ: one row can be updated in place, but every row is new in a
    recreated table.
    """
    if last is None or newest is None:
        return False
    if _sql_less(conn, newest, last):
        return True
    if not identity:  # state written before tables were identified
        return False
    first_key = identity.get("first_key")
    if _sql_less(conn, _min_key(conn, table, key), first_key):
        return True
    if first_key == last:  # one row: an update in place would look the same
        return False
    first = _row_identity(conn, table, key, first_key)
    latest = _row_identity(conn, table, key, last)
    return (
        first is not None
        and latest is not None
        and first != identity.get("first_sha256")
        and latest != identity.get("last_sha256")
    )


def _sql_less(conn, left, right) -> bool:
    """``left < right`` in SQLite's order, which ranks every number below every text.

    So a recorded key of another type than the table's keys never raises; a text key
    above number keys reads as a reset, and the run exports every row again.
    """
    return bool(conn.execute("SELECT ? < ?", (left, right)).fetchone()[0])


def _table_identity(conn, table: str, key: str, last) -> dict[str, Any] | None:
    """The smallest key, and hashes of the rows at it and at ``last``, for the next run."""
    first_key = _min_key(conn, table, key)
    if first_key is None or last is None:
        return None
    return {
        "first_key": first_key,
        "first_sha256": _row_identity(conn, table, key, first_key),
        "last_sha256": _row_identity(conn, table, key, last),
    }


def _min_key(conn, table: str, key: str):
    return conn.execute(f"SELECT MIN({_quote(key)}) FROM {_quote(table)}").fetchone()[0]


def _row_identity(conn, table: str, key: str, value) -> str | None:
    """SHA-256 of one row's values, leaving out credential columns; None if no such row."""
    cursor = conn.execute(f"SELECT * FROM {_quote(table)} WHERE {_quote(key)} = ?", (value,))
    row = cursor.fetchone()
    if row is None:
        return None
    names = [column[0] for column in cursor.description]
    record = {
        name: _json_value(cell)
        for name, cell in zip(names, row)
        if not _looks_like_credential(name)
    }
    text = json.dumps(record, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_rows(conn, rule: DatabaseRule, start, out: Path) -> tuple[int, list[str], int]:
    """Write rows with keys above ``start`` as JSON Lines, credential columns set to null.

    JWTs in text values are replaced with :data:`JWT_PLACEHOLDER`. BLOB values are
    written as base64 and left as they are. Returns the row count, the blanked
    "table.column" names and the number of JWTs replaced.
    """
    table, key = str(rule.log_table), str(rule.log_key)
    query = f"SELECT * FROM {_quote(table)}"
    params: tuple = ()
    if start is not None:
        query += f" WHERE {_quote(key)} > ?"
        params = (start,)
    cursor = conn.execute(query + f" ORDER BY {_quote(key)}", params)
    names = [column[0] for column in cursor.description]
    named = {entry.lower() for entry in rule.blank_columns}
    blank = {
        name for name in names if f"{table}.{name}".lower() in named or _looks_like_credential(name)
    }
    count = redacted = 0
    with out.open("w", encoding="utf-8") as handle:
        for row in cursor:
            record = {}
            for name, value in zip(names, row):
                record[name], replaced = _export_value(None if name in blank else value)
                redacted += replaced
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count, sorted(f"{table}.{name}" for name in blank), redacted


def _export_value(value: Any) -> tuple[Any, int]:
    """A value as written to a row export, and the number of JWTs replaced in it."""
    if isinstance(value, str):
        return replace_jwts(value)
    return _json_value(value), 0


def replace_jwts(text: str) -> tuple[str, int]:
    """``JWT_PATTERN.subn(JWT_PLACEHOLDER, text)``, in time linear in the text's length.

    Searching with the pattern itself tries every "eyJ" of a long base64url run, and each
    try reads to the end of the run: a 1 MB run took minutes. A match lies within one
    run of base64url characters and dots, so each run is searched on its own (_run_jwts).
    """
    if "eyJ" not in text:
        return text, 0
    count = 0

    def run(match: re.Match) -> str:
        nonlocal count
        replaced, found = _run_jwts(match.group())
        count += found
        return replaced

    return _BASE64URL_RUN.sub(run, text), count


_BASE64URL_RUN = re.compile(r"[A-Za-z0-9_.-]+")


def _run_jwts(run: str) -> tuple[str, int]:
    """Replace the JWTs in one run of base64url characters and dots, trying one start per
    dot-separated segment.

    A match's first segment runs from an "eyJ" to the next dot, and what must follow that
    dot does not depend on where in the segment the match starts. So when the segment's
    first "eyJ" with at least 10 characters after it starts no match, no later "eyJ" in
    the segment does, and the search moves on to the next segment. Each try reads at most
    three segments, so the run is read a bounded number of times. Matches end where a
    segment ends, as they do when the pattern searches the run.
    """
    parts: list[str] = []
    count = done = start = 0
    while (dot := run.find(".", start)) >= 0:
        header = run.find("eyJ", start, dot)
        match = JWT_PATTERN.match(run, header) if header >= 0 and dot - header >= 13 else None
        if match is None:
            start = dot + 1
            continue
        parts += [run[done:header], JWT_PLACEHOLDER]
        count += 1
        done = start = match.end()
    return "".join(parts) + run[done:], count


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):  # keep BLOBs distinguishable from TEXT
        return {"$base64": base64.b64encode(value).decode("ascii")}
    return value
