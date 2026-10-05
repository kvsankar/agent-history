"""Catalog tables, written once for SQLite and PostgreSQL.

``{TS}``, ``{JSON}``, ``{BIG}`` and ``{BOOL}`` are replaced per store: PostgreSQL gets
``timestamptz``, ``jsonb``, ``bigint`` and ``boolean``; SQLite gets ``TEXT`` and ``INTEGER``.
``{BYTES}`` names each store's byte-order collation (``"C"`` and ``BINARY``), so text sorts
the same way on both whatever the database's locale.
The catalog holds metadata only, never message text.

Views hold no data, so changing one needs no new schema version: every open replaces them
(SQLite drops and creates each view; PostgreSQL uses ``CREATE OR REPLACE VIEW``, which
accepts a changed query as long as the view's columns stay the same).
"""

from __future__ import annotations

SCHEMA_VERSION = "2"

# Older versions that opening upgrades in place. Each later version only added tables
# (created by the CREATE ... IF NOT EXISTS statements below), so upgrading only records
# the new version. Version 2 added ``pending_sessions``.
UPGRADABLE_VERSIONS = ("1",)

TYPES = {
    "sqlite": {
        "TS": "TEXT",
        "JSON": "TEXT",
        "BIG": "INTEGER",
        "BOOL": "INTEGER",
        "BYTES": "BINARY",
    },
    "postgres": {
        "TS": "TIMESTAMPTZ",
        "JSON": "JSONB",
        "BIG": "BIGINT",
        "BOOL": "BOOLEAN",
        "BYTES": '"C"',
    },
}

TABLES = (
    """CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sources (
        name TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        platform TEXT NOT NULL,
        note TEXT,
        first_run_at {TS},
        last_run_at {TS}
    )""",
    """CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        collector_host TEXT,
        tool_version TEXT,
        started_at {TS},
        finished_at {TS},
        written INTEGER,
        errors INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS files (
        source TEXT NOT NULL,
        path TEXT NOT NULL,
        agent TEXT,
        kind TEXT NOT NULL,
        size {BIG},
        mtime_ns {BIG},
        sha256 TEXT,
        compressed_size {BIG},
        archive_path TEXT,
        first_run_id TEXT,
        last_written_run_id TEXT,
        gone_run_id TEXT,
        PRIMARY KEY (source, path)
    )""",
    """CREATE TABLE IF NOT EXISTS file_versions (
        source TEXT NOT NULL,
        path TEXT NOT NULL,
        run_id TEXT NOT NULL,
        sha256 TEXT,
        size {BIG},
        mtime_ns {BIG},
        archive_path TEXT,
        superseded_run_id TEXT,
        PRIMARY KEY (source, path, run_id)
    )""",
    """CREATE TABLE IF NOT EXISTS row_exports (
        source TEXT NOT NULL,
        archive_path TEXT NOT NULL,
        path TEXT NOT NULL,
        table_name TEXT NOT NULL,
        from_key TEXT,
        to_key TEXT,
        row_count INTEGER,
        was_reset {BOOL},
        run_id TEXT NOT NULL,
        sha256 TEXT,
        size {BIG},
        PRIMARY KEY (source, archive_path)
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        source TEXT NOT NULL,
        path TEXT NOT NULL,
        session_id TEXT NOT NULL,
        agent TEXT NOT NULL,
        from_database {BOOL} NOT NULL,
        workspace TEXT,
        cwd TEXT,
        git_branch TEXT,
        models {JSON},
        first_timestamp {TS},
        last_timestamp {TS},
        message_count INTEGER,
        user_messages INTEGER,
        assistant_messages INTEGER,
        tool_uses INTEGER,
        input_tokens {BIG},
        output_tokens {BIG},
        cache_read_tokens {BIG},
        cache_creation_tokens {BIG},
        parent_session_id TEXT,
        is_subagent {BOOL},
        file_sha256 TEXT,
        PRIMARY KEY (source, path, session_id)
    )""",
    # Session files whose last read failed, with the SHA-256 the manifest gave them;
    # every sync retries them. ``error_type`` is the exception's class name only, so
    # no file content can reach the catalog.
    """CREATE TABLE IF NOT EXISTS pending_sessions (
        source TEXT NOT NULL,
        path TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        error_type TEXT,
        PRIMARY KEY (source, path)
    )""",
    """CREATE INDEX IF NOT EXISTS sessions_by_id ON sessions (agent, session_id)""",
    """CREATE INDEX IF NOT EXISTS runs_by_source ON runs (source)""",
    """CREATE VIEW IF NOT EXISTS session_copies AS
        SELECT agent, session_id,
               COUNT(DISTINCT source) AS sources,
               COUNT(*) AS copies,
               MAX(message_count) AS max_messages,
               MAX(last_timestamp) AS last_timestamp
        FROM sessions
        GROUP BY agent, session_id""",
    # Session files before database rows (a database may count turns, a file counts
    # messages), then the most messages, then the latest message. "x IS NULL" puts
    # NULLs last on both stores: they sort last in SQLite but first in PostgreSQL.
    # The last tie-break compares bytes, as PostgreSQL would otherwise use its locale.
    """CREATE VIEW IF NOT EXISTS session_longest_copy AS
        SELECT * FROM (
            SELECT s.*, ROW_NUMBER() OVER (
                PARTITION BY agent, session_id
                ORDER BY from_database,
                         message_count IS NULL, message_count DESC,
                         last_timestamp IS NULL, last_timestamp DESC,
                         source COLLATE {BYTES}, path COLLATE {BYTES}
            ) AS copy_rank
            FROM sessions s
        ) ranked
        WHERE copy_rank = 1""",
)

# Deleted in this order when the catalog is rebuilt.
DATA_TABLES = (
    "pending_sessions",
    "sessions",
    "row_exports",
    "file_versions",
    "files",
    "runs",
    "sources",
)


_CREATE_VIEW = "CREATE VIEW IF NOT EXISTS "


def statements(dialect: str) -> list[str]:
    types = TYPES[dialect]
    result = []
    for template in TABLES:
        sql = template
        for name, value in types.items():
            sql = sql.replace("{" + name + "}", value)
        if sql.startswith(_CREATE_VIEW):
            view = sql[len(_CREATE_VIEW) :].split()[0]
            if dialect == "postgres":
                sql = "CREATE OR REPLACE VIEW " + sql[len(_CREATE_VIEW) :]
            else:
                result.append(f"DROP VIEW IF EXISTS {view}")
                sql = "CREATE VIEW " + sql[len(_CREATE_VIEW) :]
        result.append(sql)
    return result
