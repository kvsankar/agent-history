"""Catalog stores: SQLite (standard library) and PostgreSQL (psycopg 3, optional).

SQL is written once with ``?`` placeholders; the PostgreSQL store rewrites them to
``%s``. Both stores create their own tables and record the schema version.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from agent_history.archive.catalog.schema import DATA_TABLES, SCHEMA_VERSION, statements
from agent_history.archive.errors import ArchiveError


class CatalogStore:
    dialect: str

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
        with self.transaction():
            for sql in statements(self.dialect):
                self.execute(sql)
            found = self.fetchall("SELECT value FROM schema_meta WHERE key = 'version'")
            if not found:
                self.execute(
                    "INSERT INTO schema_meta (key, value) VALUES ('version', ?)", (SCHEMA_VERSION,)
                )
            elif found[0][0] != SCHEMA_VERSION:
                raise ArchiveError(
                    f"Catalog schema {found[0][0]} is not supported (expected {SCHEMA_VERSION})"
                )

    def clear(self) -> None:
        with self.transaction():
            for table in DATA_TABLES:
                self.execute(f"DELETE FROM {table}")


class SqliteStore(CatalogStore):
    dialect = "sqlite"

    def __init__(self, path: Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None)

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        self.conn.execute(sql, tuple(params))

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[tuple]:
        return self.conn.execute(sql, tuple(params)).fetchall()

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

    def __init__(self, conninfo: str):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise ArchiveError(
                "A PostgreSQL catalog needs psycopg: pip install 'cagelens[postgres]'"
            ) from exc
        self.conn = psycopg.connect(conninfo, autocommit=True)

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


def open_store(spec: str) -> CatalogStore:
    """Open ``sqlite:<path>`` or ``postgres:<libpq connection string>``, creating tables."""
    if spec.startswith("sqlite:"):
        store: CatalogStore = SqliteStore(Path(spec[len("sqlite:") :]).expanduser())
    elif spec.startswith("postgres:"):
        store = PostgresStore(spec[len("postgres:") :])
    else:
        raise ArchiveError(
            f"Unknown catalog store: {spec} (use sqlite:<path> or postgres:<conninfo>)"
        )
    store.ensure_schema()
    return store
