"""Catalog stores: SQLite (standard library) and PostgreSQL (psycopg 3, optional).

SQL is written once with ``?`` placeholders; the PostgreSQL store rewrites them to
``%s``. Opened for writing, both stores create their own tables and views and record
the schema version. Opened read-only, a store changes nothing: it only checks that this
cagelens can read the catalog.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from agent_history.archive.catalog.schema import (
    DATA_TABLES,
    SCHEMA_VERSION,
    UPGRADABLE_VERSIONS,
    statements,
)
from agent_history.archive.errors import ArchiveError

_SYNC_COMMAND = "cagelens archive catalog sync"
# SQLite's extended result code for a read-only connection that meets a journal left by
# an interrupted write: rolling it back would write, so it cannot read the database.
_SQLITE_READONLY_ROLLBACK = 776


class CatalogStore:
    dialect: str
    # Returns a row when the table named by its one parameter exists.
    table_exists_sql: str

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        raise NotImplementedError

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[tuple]:
        raise NotImplementedError

    @contextmanager
    def transaction(self) -> Iterator[None]:
        raise NotImplementedError
        yield  # pragma: no cover

    def close(self) -> None:
        raise NotImplementedError

    def ensure_schema(self) -> None:
        """Create missing tables, upgrade an older version, and replace every view."""
        with self.transaction():
            for sql in statements(self.dialect):
                self.execute(sql)
            found = self.fetchall("SELECT value FROM schema_meta WHERE key = 'version'")
            if not found:
                self.execute(
                    "INSERT INTO schema_meta (key, value) VALUES ('version', ?)", (SCHEMA_VERSION,)
                )
            elif found[0][0] in UPGRADABLE_VERSIONS:
                self.execute(
                    "UPDATE schema_meta SET value = ? WHERE key = 'version'", (SCHEMA_VERSION,)
                )
            elif found[0][0] != SCHEMA_VERSION:
                raise _unsupported(found[0][0])

    def check_schema(self) -> None:
        """Check, changing nothing, that the catalog exists at this cagelens's version."""
        found = []
        if self.fetchall(self.table_exists_sql, ("schema_meta",)):
            found = self.fetchall("SELECT value FROM schema_meta WHERE key = 'version'")
        if not found:
            raise ArchiveError(f"The store holds no catalog yet: run {_SYNC_COMMAND} first")
        version = found[0][0]
        if version in UPGRADABLE_VERSIONS:
            raise ArchiveError(
                f"Catalog schema {version} is older than this cagelens reads "
                f"({SCHEMA_VERSION}): run {_SYNC_COMMAND} to upgrade it"
            )
        if version != SCHEMA_VERSION:
            raise _unsupported(version)

    def clear(self, sources: Sequence[str] | None = None) -> None:
        """Delete every row, or only the rows of ``sources``."""
        with self.transaction():
            for table in DATA_TABLES:
                if sources is None:
                    self.execute(f"DELETE FROM {table}")
                    continue
                column = "name" if table == "sources" else "source"
                for name in sources:
                    self.execute(f"DELETE FROM {table} WHERE {column} = ?", (name,))


def _unsupported(version: str) -> ArchiveError:
    return ArchiveError(f"Catalog schema {version} is not supported (expected {SCHEMA_VERSION})")


class SqliteStore(CatalogStore):
    dialect = "sqlite"
    table_exists_sql = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?"

    def __init__(self, path: Path, read_only: bool = False):
        self.path = Path(path)
        if read_only:
            if not self.path.is_file():
                raise ArchiveError(f"No catalog at {self.path}: run {_SYNC_COMMAND} first")
            # The URI's read-only mode never writes, not even a journal, so it also
            # reads a file or folder that this user cannot write.
            uri = f"{self.path.absolute().as_uri()}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True, isolation_level=None)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), isolation_level=None)

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        self.conn.execute(sql, tuple(params))

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[tuple]:
        return self.conn.execute(sql, tuple(params)).fetchall()

    def check_schema(self) -> None:
        try:
            super().check_schema()
        except sqlite3.Error as exc:  # such as a file that is not a SQLite database
            if self._interrupted_write(exc):
                raise ArchiveError(
                    f"The catalog at {self.path} has a journal left by an interrupted sync, "
                    f"which reading it without writing cannot undo: run {_SYNC_COMMAND} "
                    "to recover it"
                ) from exc
            raise ArchiveError(f"Cannot read the catalog at {self.path}: {exc}") from exc

    def _interrupted_write(self, exc: sqlite3.Error) -> bool:
        """Whether ``exc`` comes from a rollback journal that an interrupted write left."""
        code = getattr(exc, "sqlite_errorcode", None)  # Python 3.11 and later
        if code is not None:
            return code == _SQLITE_READONLY_ROLLBACK
        journal = self.path.with_name(self.path.name + "-journal")
        return journal.is_file() and journal.stat().st_size > 0

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def close(self) -> None:
        self.conn.close()


class PostgresStore(CatalogStore):
    dialect = "postgres"
    table_exists_sql = "SELECT 1 WHERE to_regclass(CAST(? AS TEXT)) IS NOT NULL"

    def __init__(self, conninfo: str, read_only: bool = False):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise ArchiveError(
                "A PostgreSQL catalog needs psycopg: pip install 'cagelens[postgres]'"
            ) from exc
        self.conn = psycopg.connect(conninfo, autocommit=True)
        if read_only:
            # Every transaction of this session, including each autocommit statement,
            # is read-only.
            self.conn.execute("SET default_transaction_read_only = on")

    @staticmethod
    def _sql(sql: str) -> str:
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        self.conn.execute(self._sql(sql), tuple(params))  # type: ignore[arg-type]

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[tuple]:
        return self.conn.execute(self._sql(sql), tuple(params)).fetchall()  # type: ignore[arg-type]

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.conn.transaction():
            yield

    def close(self) -> None:
        self.conn.close()


def open_store(spec: str, read_only: bool = False) -> CatalogStore:
    """Open ``sqlite:<path>`` or ``postgres:<libpq connection string>``.

    For writing (catalog sync and rebuild), opening creates missing tables, upgrades an
    older schema version and replaces the views. ``read_only`` (catalog status) changes
    nothing: it refuses a missing catalog or one at another schema version.
    """
    if spec.startswith("sqlite:"):
        store: CatalogStore = SqliteStore(Path(spec[len("sqlite:") :]).expanduser(), read_only)
    elif spec.startswith("postgres:"):
        store = PostgresStore(spec[len("postgres:") :], read_only)
    else:
        raise ArchiveError(
            f"Unknown catalog store: {spec} (use sqlite:<path> or postgres:<conninfo>)"
        )
    try:
        if read_only:
            store.check_schema()
        else:
            store.ensure_schema()
    except BaseException:
        store.close()
        raise
    return store
