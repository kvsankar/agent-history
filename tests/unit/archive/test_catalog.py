"""Tests for the archive catalog, run against SQLite and (when available) PostgreSQL."""

from __future__ import annotations

import glob
import itertools
import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_history.archive.catalog import catalog_status, open_store, sync_catalog
from agent_history.archive.collect import collect_source
from agent_history.archive.config import parse_config
from agent_history.archive.transport import open_destination
from tests.helpers.session_builders import ClaudeSessionBuilder, CodexSessionBuilder

T0 = datetime(2026, 10, 2, 6, 15, tzinfo=timezone.utc)
SECRET_PROMPT = "please refactor the billing module"
_STAMPS = itertools.count(1_700_000_000, 10)


def _settle(path: Path) -> None:
    stamp = next(_STAMPS)
    os.utime(path, (stamp, stamp))


# -- stores --------------------------------------------------------------------------


def _pg_bindir():
    candidates = sorted(glob.glob("/usr/lib/postgresql/*/bin"), reverse=True)
    if shutil.which("initdb"):
        candidates.insert(0, str(Path(shutil.which("initdb")).parent))
    for candidate in candidates:
        if (Path(candidate) / "initdb").exists():
            return Path(candidate)
    return None


@pytest.fixture(scope="session")
def pg_cluster():
    pytest.importorskip("psycopg")
    bindir = _pg_bindir()
    if bindir is None or os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
        pytest.skip("PostgreSQL server binaries are not available")
    base = Path(tempfile.mkdtemp(prefix="cgpg"))  # short path: socket names are limited
    data = base / "data"
    subprocess.run(
        [bindir / "initdb", "-D", data, "-A", "trust", "-U", "test"],
        check=True,
        capture_output=True,
    )
    options = f"-k {base} -c listen_addresses='' -p 54329"
    subprocess.run(
        [bindir / "pg_ctl", "-D", data, "-o", options, "-w", "-l", base / "log", "start"],
        check=True,
        capture_output=True,
    )
    yield f"host={base} port=54329 user=test"
    subprocess.run(
        [bindir / "pg_ctl", "-D", data, "-m", "immediate", "stop"], capture_output=True, check=False
    )
    shutil.rmtree(base, ignore_errors=True)


_DB_NAMES = itertools.count()


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path):
    if request.param == "sqlite":
        opened = open_store(f"sqlite:{tmp_path / 'catalog.db'}")
    else:
        import psycopg

        conninfo = request.getfixturevalue("pg_cluster")
        name = f"catalog_{os.getpid()}_{next(_DB_NAMES)}"
        with psycopg.connect(conninfo + " dbname=postgres", autocommit=True) as conn:
            conn.execute(f"CREATE DATABASE {name}")
        opened = open_store(f"postgres:{conninfo} dbname={name}")
    yield opened
    opened.close()


# -- archive fixture -----------------------------------------------------------------


@pytest.fixture
def archive(tmp_path):
    home = tmp_path / "home"
    claude = ClaudeSessionBuilder(workspace="-home-alex-shop", session_id="claude-s1")
    claude.add_user_message(SECRET_PROMPT)
    claude.add_assistant_message("Done.")
    claude_file = claude.write_to(home / ".claude" / "projects")
    _settle(claude_file)
    codex = CodexSessionBuilder(session_id="codex-s1", cwd="/home/alex/shop")
    codex.add_user_message("hello codex")
    codex.add_assistant_message("hi")
    _settle(codex.write_to(home / ".codex" / "sessions"))
    store_db = home / ".copilot" / "session-store.db"
    store_db.parent.mkdir(parents=True)
    conn = sqlite3.connect(store_db)
    conn.execute(
        "CREATE TABLE sessions (id TEXT, cwd TEXT, repository TEXT, branch TEXT, "
        "created_at TEXT, updated_at TEXT)"
    )
    conn.execute("CREATE TABLE turns (session_id TEXT, user_message TEXT)")
    conn.execute(
        "INSERT INTO sessions VALUES ('copilot-gone', '/home/alex/shop', NULL, 'main', "
        "'2026-06-18T03:41:00.960Z', '2026-06-18T03:41:11.645Z')"
    )
    conn.executemany("INSERT INTO turns VALUES ('copilot-gone', ?)", [("a",), ("b",)])
    conn.commit()
    conn.close()
    _settle(store_db)
    config = parse_config(
        {
            "archive": {"destination": str(tmp_path / "archive"), "compression_level": 3},
            "sources": [{"name": "laptop", "kind": "live", "platform": "linux", "home": str(home)}],
        }
    )
    state = tmp_path / "state"

    def collect(hours=0):
        return collect_source(config, "laptop", state_dir=state, now=T0 + timedelta(hours=hours))

    collect()
    return {
        "home": home,
        "claude_file": claude_file,
        "collect": collect,
        "destination": open_destination(str(tmp_path / "archive")),
        "path": tmp_path,
    }


def _rows(store, sql, params=()):
    return [tuple(row) for row in store.fetchall(sql, params)]


# -- tests ---------------------------------------------------------------------------


def test_sync_records_sources_runs_files_and_sessions(store, archive):
    summary = sync_catalog(store, archive["destination"])

    assert summary.runs == 1
    assert _rows(store, "SELECT name, kind, platform FROM sources") == [("laptop", "live", "linux")]
    assert _rows(store, "SELECT COUNT(*) FROM runs") == [(1,)]
    files = dict(_rows(store, "SELECT path, kind FROM files"))
    assert files[".claude/projects/-home-alex-shop/claude-s1.jsonl"] == "file"
    assert files[".copilot/session-store.db"] == "sqlite-snapshot"
    sessions = {
        row[0]: row[1:]
        for row in _rows(
            store,
            "SELECT session_id, agent, cwd, message_count, from_database FROM sessions",
        )
    }
    assert sessions["claude-s1"][0] == "claude"
    assert sessions["claude-s1"][2] >= 2
    assert sessions["codex-s1"][:2] == ("codex", "/home/alex/shop")
    assert sessions["copilot-gone"] == ("copilot-cli", "/home/alex/shop", 2, True)


def test_catalog_holds_no_message_text(store, archive, tmp_path):
    sync_catalog(store, archive["destination"])

    texts = [str(value) for row in store.fetchall("SELECT * FROM sessions") for value in row]
    texts += [str(value) for row in store.fetchall("SELECT * FROM files") for value in row]
    assert not any(SECRET_PROMPT in text for text in texts)


def test_sync_is_incremental(store, archive):
    sync_catalog(store, archive["destination"])
    with archive["claude_file"].open("a", encoding="utf-8") as handle:
        handle.write(
            '{"type":"user","sessionId":"claude-s1","timestamp":"2025-01-03T10:05:00Z",'
            '"uuid":"u9","message":{"role":"user","content":"more"}}\n'
        )
    _settle(archive["claude_file"])
    archive["collect"](hours=1)

    summary = sync_catalog(store, archive["destination"])

    assert summary.runs == 1
    assert _rows(store, "SELECT COUNT(*) FROM runs") == [(2,)]
    assert _rows(store, "SELECT COUNT(*) FROM sessions WHERE session_id = 'claude-s1'") == [(1,)]
    again = sync_catalog(store, archive["destination"])
    assert again.runs == 0


def test_sync_interrupted_while_reading_sessions_finishes_on_the_next_sync(
    store, archive, monkeypatch
):
    from agent_history.archive.catalog import sync

    real_extract = sync._extract_sessions
    calls = []

    def interrupted(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return real_extract(*args, **kwargs)

    monkeypatch.setattr(sync, "_extract_sessions", interrupted)
    with pytest.raises(KeyboardInterrupt):
        sync_catalog(store, archive["destination"])
    monkeypatch.setattr(sync, "_extract_sessions", real_extract)

    sync_catalog(store, archive["destination"])

    assert _rows(store, "SELECT COUNT(*) FROM runs") == [(1,)]
    assert sorted(row[0] for row in _rows(store, "SELECT session_id FROM sessions")) == [
        "claude-s1",
        "codex-s1",
        "copilot-gone",
    ]


def test_versions_and_gone_files_are_recorded(store, archive):
    archive["claude_file"].write_text('{"type":"summary"}\n', encoding="utf-8")
    _settle(archive["claude_file"])
    archive["collect"](hours=1)
    codex_files = list((archive["home"] / ".codex").rglob("*.jsonl"))
    for path in codex_files:
        path.unlink()
    archive["collect"](hours=2)

    sync_catalog(store, archive["destination"])

    assert _rows(
        store, "SELECT COUNT(*) FROM file_versions WHERE superseded_run_id IS NOT NULL"
    ) == [(1,)]
    gone = _rows(store, "SELECT path FROM files WHERE gone_run_id IS NOT NULL")
    assert [row[0] for row in gone] == [
        p.relative_to(archive["home"]).as_posix() for p in codex_files
    ]


def test_session_copies_view_groups_sources(store, archive):
    sync_catalog(store, archive["destination"])

    rows = _rows(
        store, "SELECT agent, session_id, sources FROM session_copies WHERE session_id = 'codex-s1'"
    )
    assert rows == [("codex", "codex-s1", 1)]


def test_rebuild_replays_every_manifest(store, archive):
    sync_catalog(store, archive["destination"])
    before = _rows(store, "SELECT COUNT(*) FROM files")

    summary = sync_catalog(store, archive["destination"], rebuild=True)

    assert summary.runs == 1
    assert _rows(store, "SELECT COUNT(*) FROM files") == before


def test_status_reports_counts_per_source(store, archive):
    sync_catalog(store, archive["destination"])

    (status,) = catalog_status(store)

    assert status["source"] == "laptop"
    assert status["runs"] == 1
    assert status["files"] >= 3
    assert status["sessions"] >= 3
    assert status["last_run_at"].startswith("2026-10-02")
