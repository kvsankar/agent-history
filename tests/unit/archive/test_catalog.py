"""Tests for the archive catalog, run against SQLite and (when available) PostgreSQL."""

from __future__ import annotations

import glob
import itertools
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_history.archive.catalog import catalog_status, open_store, sync_catalog
from agent_history.archive.catalog.schema import SCHEMA_VERSION
from agent_history.archive.catalog.sync import READER_VERSION
from agent_history.archive.codec import compress_bytes, decompress_bytes
from agent_history.archive.collect import collect_source
from agent_history.archive.config import parse_config
from agent_history.archive.errors import ArchiveError
from agent_history.archive.layouts import archive_file_path
from agent_history.archive.transport import open_destination
from agent_history.cli.orchestrator import main
from tests.helpers.session_builders import (
    ClaudeSessionBuilder,
    CodexSessionBuilder,
    GeminiSessionBuilder,
)

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


def _new_store_spec(request, tmp_path, create_options=""):
    if request.param == "sqlite":
        return f"sqlite:{tmp_path / 'catalog.db'}"
    import psycopg

    conninfo = request.getfixturevalue("pg_cluster")
    name = f"catalog_{os.getpid()}_{next(_DB_NAMES)}"
    with psycopg.connect(conninfo + " dbname=postgres", autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {name} {create_options}")
    return f"postgres:{conninfo} dbname={name}"


@pytest.fixture(params=["sqlite", "postgres"])
def store_spec(request, tmp_path):
    """The ``--store`` value of an empty catalog database."""
    return _new_store_spec(request, tmp_path)


@pytest.fixture(params=["sqlite", "postgres"])
def linguistic_store(request, tmp_path):
    """An empty catalog whose PostgreSQL database sorts text by language rules ("a" < "B")."""
    opened = open_store(
        _new_store_spec(
            request, tmp_path, "TEMPLATE template0 LOCALE_PROVIDER icu ICU_LOCALE 'und'"
        )
    )
    yield opened
    opened.close()


@pytest.fixture
def store(store_spec):
    opened = open_store(store_spec)
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


def _session_ids(store):
    return sorted(row[0] for row in _rows(store, "SELECT session_id FROM sessions"))


def _codex_file(archive):
    """The Codex session file's path in the source and its compressed copy in the archive."""
    (local,) = (archive["home"] / ".codex").rglob("*.jsonl")
    rel = local.relative_to(archive["home"]).as_posix()
    return local, rel, archive["path"] / "archive" / archive_file_path("laptop", rel)


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


def _add_claude_sub_agent(archive, rel_folder, name="agent-a1.jsonl", agent_id="a1"):
    """Add a Claude sub-agent transcript under the claude-s1 session folder."""
    path = archive["home"] / ".claude/projects/-home-alex-shop/claude-s1" / rel_folder / name
    path.parent.mkdir(parents=True)
    line = {
        "type": "user",
        "sessionId": "claude-s1",
        "agentId": agent_id,
        "timestamp": "2025-01-03T10:06:00Z",
        "uuid": f"{agent_id}-u1",
        "message": {"role": "user", "content": "look at the tests"},
    }
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    _settle(path)
    return path


def test_a_claude_sub_agent_has_its_projects_folder_as_workspace(store, archive):
    _add_claude_sub_agent(archive, "subagents")
    archive["collect"](hours=1)

    sync_catalog(store, archive["destination"])

    assert _rows(
        store,
        "SELECT session_id, workspace, parent_session_id FROM sessions "
        "WHERE agent = 'claude' ORDER BY session_id",
    ) == [
        ("claude-s1", "-home-alex-shop", None),
        ("claude-s1:a1", "-home-alex-shop", "claude-s1"),
    ]


@pytest.mark.parametrize("rel_folder", ["subagents", "subagents/workflows/wf_1"])
def test_a_claude_compaction_transcript_is_archived_but_not_catalogued_as_a_session(
    store, archive, rel_folder
):
    path = _add_claude_sub_agent(
        archive, rel_folder, name="agent-acompact-1.jsonl", agent_id="acompact-1"
    )
    rel = path.relative_to(archive["home"]).as_posix()
    archive["collect"](hours=1)

    summary = sync_catalog(store, archive["destination"])

    assert summary.errors == []
    assert _rows(store, "SELECT kind FROM files WHERE path = ?", (rel,)) == [("file",)]
    assert _rows(store, "SELECT COUNT(*) FROM sessions WHERE path = ?", (rel,)) == [(0,)]
    assert _session_ids(store) == ["claude-s1", "codex-s1", "copilot-gone"]


def test_a_claude_workflow_sub_agent_is_catalogued(store, archive):
    workflow = "subagents/workflows/wf_1"
    _add_claude_sub_agent(archive, workflow, name="agent-w1.jsonl", agent_id="w1")
    journal = archive["home"] / ".claude/projects/-home-alex-shop/claude-s1" / workflow
    (journal / "journal.jsonl").write_text('{"type":"step"}\n', encoding="utf-8")
    _settle(journal / "journal.jsonl")
    archive["collect"](hours=1)

    summary = sync_catalog(store, archive["destination"])

    assert summary.errors == []
    assert _rows(
        store,
        "SELECT session_id, workspace, parent_session_id, is_subagent FROM sessions "
        "WHERE path LIKE ?",
        ("%/workflows/%",),
    ) == [("claude-s1:w1", "-home-alex-shop", "claude-s1", True)]


def test_a_gemini_chat_of_an_unknown_project_has_its_project_folder_as_workspace(
    store, archive, monkeypatch, tmp_path
):
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / "config"))
    gemini = GeminiSessionBuilder(session_id="gemini-s1", project_hash="b" * 64)
    gemini.add_user_message("hello gemini")
    gemini.add_gemini_message("hi")
    _settle(gemini.write_to(archive["home"] / ".gemini" / "tmp"))
    archive["collect"](hours=1)

    sync_catalog(store, archive["destination"])

    assert _rows(store, "SELECT workspace FROM sessions WHERE agent = 'gemini'") == [("b" * 64,)]


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


def test_a_session_file_that_could_not_be_read_is_read_on_the_next_sync(store, archive):
    # A running collect moves the archived copy aside before the new copy arrives.
    _, rel, archived = _codex_file(archive)
    aside = archived.with_name(archived.name + ".aside")
    archived.rename(aside)

    first = sync_catalog(store, archive["destination"])

    assert [error for error in first.errors if rel in error]
    assert "codex-s1" not in _session_ids(store)
    aside.rename(archived)

    second = sync_catalog(store, archive["destination"])

    assert second.errors == []
    assert second.runs == 0
    assert _session_ids(store) == ["claude-s1", "codex-s1", "copilot-gone"]
    assert sync_catalog(store, archive["destination"]).sessions == 0


def test_a_session_file_that_still_cannot_be_read_is_reported_on_every_sync(store, archive):
    _, rel, archived = _codex_file(archive)
    archived.rename(archived.with_name(archived.name + ".aside"))
    sync_catalog(store, archive["destination"])

    again = sync_catalog(store, archive["destination"])

    assert again.runs == 0
    assert [error for error in again.errors if rel in error]


def test_sync_does_not_read_a_session_file_that_differs_from_its_manifest(store, archive):
    # A running collect has rewritten the archived copy and not yet written its manifest.
    _, rel, archived = _codex_file(archive)
    original = archived.read_bytes()
    archived.write_bytes(compress_bytes(decompress_bytes(original) + b"\n", 3))

    first = sync_catalog(store, archive["destination"])

    assert [error for error in first.errors if rel in error and "SHA-256" in error]
    assert "codex-s1" not in _session_ids(store)
    archived.write_bytes(original)

    second = sync_catalog(store, archive["destination"])

    assert second.errors == []
    assert _rows(store, "SELECT file_sha256 FROM sessions WHERE session_id = 'codex-s1'") == (
        _rows(store, "SELECT sha256 FROM files WHERE path = ?", (rel,))
    )


def test_a_session_file_that_failed_is_read_at_its_newest_hash_after_another_run(store, archive):
    local, rel, archived = _codex_file(archive)
    aside = archived.with_name(archived.name + ".aside")
    archived.rename(aside)
    assert sync_catalog(store, archive["destination"]).errors
    aside.rename(archived)
    with local.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    _settle(local)
    archive["collect"](hours=1)

    summary = sync_catalog(store, archive["destination"])

    assert summary.errors == []
    assert summary.runs == 1
    assert _rows(store, "SELECT file_sha256 FROM sessions WHERE session_id = 'codex-s1'") == (
        _rows(store, "SELECT sha256 FROM files WHERE path = ?", (rel,))
    )


def _add_claude_transcript(archive, name, **fields):
    """Add a one-line Claude transcript to the -home-alex-shop project folder."""
    path = archive["home"] / ".claude/projects/-home-alex-shop" / name
    line = {
        "type": "user",
        "sessionId": "odd-1",
        "uuid": "odd-u1",
        "timestamp": "2025-01-03T10:06:00Z",
        "message": {"role": "user", "content": "hello"},
        **fields,
    }
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    _settle(path)
    return path


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"sessionId": {"x": 1}}, ('{"x": 1}', None, None)),
        (
            {"cwd": "/home/alex/a\u0000b", "gitBranch": "ma\u0000in"},
            ("odd-1", "/home/alex/ab", "main"),
        ),
    ],
    ids=["object-session-id", "nul-in-text"],
)
def test_a_transcript_with_values_a_store_cannot_take_is_catalogued_as_text(
    store, archive, fields, expected
):
    _add_claude_transcript(archive, "odd-1.jsonl", **fields)
    archive["collect"](hours=1)

    summary = sync_catalog(store, archive["destination"])

    assert summary.errors == []
    assert summary.runs == 2
    assert _rows(
        store,
        "SELECT session_id, cwd, git_branch FROM sessions WHERE path LIKE ?",
        ("%/odd-1.jsonl",),
    ) == [expected]
    assert "claude-s1" in _session_ids(store)


def test_a_database_session_with_values_a_store_cannot_take_is_catalogued_as_text(store, archive):
    state = archive["home"] / ".codex" / "state_5.sqlite"
    with closing(sqlite3.connect(state)) as conn:
        conn.execute("CREATE TABLE threads (id, cwd, created_at, updated_at)")
        conn.execute(
            "INSERT INTO threads VALUES (?, ?, 1767225600, 1767225660)",
            (b"thread-1", "/home/alex/a\x00b"),
        )
        conn.commit()
    _settle(state)
    archive["collect"](hours=1)

    summary = sync_catalog(store, archive["destination"])

    assert summary.errors == []
    assert _rows(
        store, "SELECT session_id, cwd FROM sessions WHERE path = ?", (".codex/state_5.sqlite",)
    ) == [("thread-1", "/home/alex/ab")]


def test_a_session_file_the_store_refuses_is_retried_without_blocking_its_source(
    store, archive, monkeypatch
):
    from agent_history.archive.catalog import sync

    _, rel, _ = _codex_file(archive)
    real_insert = sync._insert_session

    def refuse_codex(target_store, row):
        if row["path"] == rel:
            raise ValueError("the store refused a value")
        real_insert(target_store, row)

    monkeypatch.setattr(sync, "_insert_session", refuse_codex)
    first = sync_catalog(store, archive["destination"])

    assert first.runs == 1
    assert [error for error in first.errors if rel in error]
    assert _session_ids(store) == ["claude-s1", "copilot-gone"]
    assert _rows(store, "SELECT path, error_type FROM pending_sessions") == [(rel, "ValueError")]
    monkeypatch.setattr(sync, "_insert_session", real_insert)

    second = sync_catalog(store, archive["destination"])

    assert second.errors == []
    assert _session_ids(store) == ["claude-s1", "codex-s1", "copilot-gone"]
    assert _rows(store, "SELECT COUNT(*) FROM pending_sessions") == [(0,)]


def test_a_version_1_catalog_is_upgraded_when_it_is_opened(store_spec):
    old = open_store(store_spec)
    with old.transaction():
        old.execute("DROP TABLE pending_sessions")
        old.execute("UPDATE schema_meta SET value = '1' WHERE key = 'version'")
    old.close()

    upgraded = open_store(store_spec)

    try:
        assert _rows(upgraded, "SELECT value FROM schema_meta") == [(SCHEMA_VERSION,)]
        assert _rows(upgraded, "SELECT COUNT(*) FROM pending_sessions") == [(0,)]
    finally:
        upgraded.close()


def _reader_version(store):
    return _rows(store, "SELECT value FROM schema_meta WHERE key = 'reader_version'")


def _make_rows_stale(store, reader_version="old"):
    """Make the session rows look written by an older reader."""
    with store.transaction():
        store.execute("UPDATE sessions SET workspace = 'stale', message_count = -1")
        store.execute("DELETE FROM schema_meta WHERE key = 'reader_version'")
        if reader_version is not None:
            store.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('reader_version', ?)",
                (reader_version,),
            )


def _stale_rows(store):
    return _rows(
        store, "SELECT COUNT(*) FROM sessions WHERE workspace = 'stale' OR message_count = -1"
    )


def test_sync_records_the_reader_version(store, archive):
    sync_catalog(store, archive["destination"])

    assert _reader_version(store) == [(READER_VERSION,)]


def test_a_new_reader_reads_every_session_file_again(store, archive):
    sync_catalog(store, archive["destination"])
    _make_rows_stale(store)

    summary = sync_catalog(store, archive["destination"])

    assert summary.runs == 0
    assert summary.sessions == 3
    assert _stale_rows(store) == [(0,)]
    assert _reader_version(store) == [(READER_VERSION,)]
    assert _rows(store, "SELECT COUNT(*) FROM pending_sessions") == [(0,)]
    assert sync_catalog(store, archive["destination"]).sessions == 0


def test_a_new_reader_also_reads_files_that_are_gone_from_the_source(store, archive):
    codex_local, _, _ = _codex_file(archive)
    codex_local.unlink()
    archive["collect"](hours=1)
    sync_catalog(store, archive["destination"])
    _make_rows_stale(store)

    sync_catalog(store, archive["destination"])

    assert _stale_rows(store) == [(0,)]
    assert "codex-s1" in _session_ids(store)


def test_a_catalog_upgraded_from_version_1_reads_every_session_file_again(store_spec, archive):
    old = open_store(store_spec)
    sync_catalog(old, archive["destination"])
    _make_rows_stale(old, reader_version=None)
    with old.transaction():
        old.execute("DROP TABLE pending_sessions")
        old.execute("UPDATE schema_meta SET value = '1' WHERE key = 'version'")
    old.close()

    upgraded = open_store(store_spec)
    try:
        sync_catalog(upgraded, archive["destination"])

        assert _stale_rows(upgraded) == [(0,)]
        assert _reader_version(upgraded) == [(READER_VERSION,)]
    finally:
        upgraded.close()


def test_reading_again_for_a_new_reader_finishes_after_an_interrupted_sync(
    store, archive, monkeypatch
):
    from agent_history.archive.catalog import sync

    sync_catalog(store, archive["destination"])
    _make_rows_stale(store)
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

    assert _stale_rows(store) == [(0,)]
    assert _rows(store, "SELECT COUNT(*) FROM pending_sessions") == [(0,)]


def test_a_new_reader_keeps_a_pending_files_newer_hash(store, archive):
    sync_catalog(store, archive["destination"])
    _, rel, _ = _codex_file(archive)
    with store.transaction():
        store.execute(
            "INSERT INTO pending_sessions (source, path, sha256, error_type) "
            "VALUES ('laptop', ?, 'newer', 'OSError')",
            (rel,),
        )
    _make_rows_stale(store)

    summary = sync_catalog(store, archive["destination"])

    assert [error for error in summary.errors if rel in error and "SHA-256" in error]
    assert _rows(store, "SELECT sha256 FROM pending_sessions") == [("newer",)]


def test_a_new_reader_deletes_sessions_of_paths_that_are_no_longer_session_files(store, archive):
    # An older layout read sessions from a path that the current layout does not.
    journal = ".claude/projects/-home-alex-shop/claude-s1/subagents/workflows/wf_1/journal.jsonl"
    sync_catalog(store, archive["destination"])
    with store.transaction():
        store.execute(
            "INSERT INTO sessions (source, path, session_id, agent, from_database) "
            "VALUES ('laptop', ?, 'journal', 'claude', ?)",
            (journal, False),
        )
    _make_rows_stale(store)

    sync_catalog(store, archive["destination"])

    assert _session_ids(store) == ["claude-s1", "codex-s1", "copilot-gone"]


def test_a_catalog_that_holds_compaction_sessions_loses_them_on_its_next_sync(store, archive):
    # Catalogs written before compaction transcripts were left out hold their rows.
    from agent_history.storage.metrics import METRICS_PARSER_VERSION

    path = _add_claude_sub_agent(
        archive, "subagents", name="agent-acompact-1.jsonl", agent_id="acompact-1"
    )
    rel = path.relative_to(archive["home"]).as_posix()
    archive["collect"](hours=1)
    sync_catalog(store, archive["destination"])
    with store.transaction():
        store.execute(
            "INSERT INTO sessions (source, path, session_id, agent, from_database) "
            "VALUES ('laptop', ?, 'claude-s1:acompact-1', 'claude', ?) "
            "ON CONFLICT (source, path, session_id) DO NOTHING",
            (rel, False),
        )
        store.execute(
            "UPDATE schema_meta SET value = ? WHERE key = 'reader_version'",
            (f"{METRICS_PARSER_VERSION}.3",),
        )

    summary = sync_catalog(store, archive["destination"])

    assert summary.errors == []
    assert _session_ids(store) == ["claude-s1", "codex-s1", "copilot-gone"]
    assert _rows(store, "SELECT COUNT(*) FROM pending_sessions") == [(0,)]


_JOURNAL = ".claude/projects/-home-alex-shop/claude-s1/subagents/workflows/wf_1/journal.jsonl"


def _add_rows_of_a_former_session_file(store):
    """Pending and session rows that an older layout wrote for a path it read sessions from."""
    with store.transaction():
        store.execute(
            "INSERT INTO pending_sessions (source, path, sha256, error_type) "
            "VALUES ('laptop', ?, 'abc', 'OSError')",
            (_JOURNAL,),
        )
        store.execute(
            "INSERT INTO sessions (source, path, session_id, agent, from_database) "
            "VALUES ('laptop', ?, 'journal', 'claude', ?)",
            (_JOURNAL, False),
        )


@pytest.mark.parametrize("new_reader", [True, False], ids=["new-reader", "same-reader"])
def test_a_pending_path_that_is_no_longer_a_session_file_is_forgotten(store, archive, new_reader):
    sync_catalog(store, archive["destination"])
    _add_rows_of_a_former_session_file(store)
    if new_reader:
        _make_rows_stale(store)

    summary = sync_catalog(store, archive["destination"])

    assert summary.errors == []
    assert _rows(store, "SELECT COUNT(*) FROM pending_sessions") == [(0,)]
    assert _session_ids(store) == ["claude-s1", "codex-s1", "copilot-gone"]


def test_a_catalog_with_an_unknown_schema_version_is_refused(store_spec):
    newer = open_store(store_spec)
    with newer.transaction():
        newer.execute("UPDATE schema_meta SET value = '99' WHERE key = 'version'")
    newer.close()

    with pytest.raises(ArchiveError, match="schema 99"):
        open_store(store_spec)


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


def _add_copy(store, path, from_database, message_count, last_timestamp=None):
    store.execute(
        "INSERT INTO sessions (source, path, session_id, agent, from_database, message_count, "
        "last_timestamp) VALUES ('laptop', ?, 'shared', 'copilot-cli', ?, ?, ?)",
        (path, from_database, message_count, last_timestamp),
    )


def _copies(store):
    return _rows(
        store,
        "SELECT copies, max_file_messages, max_database_count FROM session_copies "
        "WHERE session_id = 'shared'",
    )


def test_session_copies_keeps_file_message_counts_apart_from_database_counts(store):
    # A database may count turns and a session file counts messages.
    with store.transaction():
        _add_copy(store, "a.db", True, 50)
        _add_copy(store, "a.jsonl", False, 40)

    assert _copies(store) == [(2, 40, 50)]


def test_opening_a_catalog_replaces_a_session_copies_view_with_other_columns(store_spec):
    old = open_store(store_spec)
    with old.transaction():
        old.execute("DROP VIEW session_copies")
        old.execute(
            "CREATE VIEW session_copies AS SELECT agent, session_id, "
            "COUNT(DISTINCT source) AS sources, COUNT(*) AS copies, "
            "MAX(message_count) AS max_messages, MAX(last_timestamp) AS last_timestamp "
            "FROM sessions GROUP BY agent, session_id"
        )
        _add_copy(old, "a.db", True, 50)
    old.close()

    reopened = open_store(store_spec)

    try:
        assert _copies(reopened) == [(1, None, 50)]
    finally:
        reopened.close()


def _longest_copy(store):
    return _rows(store, "SELECT path FROM session_longest_copy WHERE session_id = 'shared'")


def test_the_longest_copy_is_not_one_without_a_message_count(store):
    with store.transaction():
        _add_copy(store, "a.db", True, None)
        _add_copy(store, "a.jsonl", False, 40)

    assert _longest_copy(store) == [("a.jsonl",)]


def test_the_longest_copy_is_a_session_file_rather_than_a_database_row(store):
    # A database counts turns and a session file counts messages, so they do not compare.
    with store.transaction():
        _add_copy(store, "a.db", True, 50)
        _add_copy(store, "a.jsonl", False, 40)

    assert _longest_copy(store) == [("a.jsonl",)]


def test_the_longest_copy_breaks_a_tie_by_the_latest_known_message(store):
    with store.transaction():
        _add_copy(store, "a.jsonl", False, 40, None)
        _add_copy(store, "b.jsonl", False, 40, "2026-10-02T06:15:00+00:00")

    assert _longest_copy(store) == [("b.jsonl",)]


def test_the_longest_copy_breaks_a_full_tie_by_byte_order_on_every_store(linguistic_store):
    # Byte order puts "B" before "a"; a language collation puts "a" first.
    with linguistic_store.transaction():
        _add_copy(linguistic_store, "a.jsonl", False, 40, "2026-10-02T06:15:00+00:00")
        _add_copy(linguistic_store, "B.jsonl", False, 40, "2026-10-02T06:15:00+00:00")

    assert _longest_copy(linguistic_store) == [("B.jsonl",)]


def test_opening_a_catalog_replaces_views_from_an_older_version(store_spec):
    old = open_store(store_spec)
    with old.transaction():
        old.execute("DROP VIEW session_longest_copy")
        old.execute(
            "CREATE VIEW session_longest_copy AS SELECT * FROM (SELECT s.*, ROW_NUMBER() "
            "OVER (PARTITION BY agent, session_id ORDER BY message_count DESC, "
            "last_timestamp DESC, source, path) AS copy_rank FROM sessions s) ranked "
            "WHERE copy_rank = 1"
        )
        _add_copy(old, "a.db", True, 50)
        _add_copy(old, "a.jsonl", False, 40)
    old.close()

    reopened = open_store(store_spec)

    try:
        assert _longest_copy(reopened) == [("a.jsonl",)]
    finally:
        reopened.close()


def _collect_second_source(archive, name="desktop"):
    home = archive["path"] / name
    claude = ClaudeSessionBuilder(workspace="-home-alex-site", session_id=f"{name}-s1")
    claude.add_user_message("hello")
    claude.add_assistant_message("hi")
    _settle(claude.write_to(home / ".claude" / "projects"))
    config = parse_config(
        {
            "archive": {"destination": str(archive["path"] / "archive"), "compression_level": 3},
            "sources": [{"name": name, "kind": "live", "platform": "linux", "home": str(home)}],
        }
    )
    collect_source(config, name, state_dir=archive["path"] / f"state-{name}", now=T0)


_COUNTS_BY_SOURCE = (
    "SELECT source, COUNT(*) FROM {} GROUP BY source ORDER BY source",
    ("sessions", "files", "file_versions", "runs"),
)


def _counts(store):
    sql, tables = _COUNTS_BY_SOURCE
    counts = {table: _rows(store, sql.format(table)) for table in tables}
    counts["sources"] = _rows(store, "SELECT name FROM sources ORDER BY name")
    return counts


def test_rebuilding_one_source_keeps_the_other_sources(store, archive):
    _collect_second_source(archive)
    sync_catalog(store, archive["destination"])
    before = _counts(store)
    assert [row[0] for row in before["sources"]] == ["desktop", "laptop"]

    summary = sync_catalog(store, archive["destination"], sources=["laptop"], rebuild=True)

    assert summary.runs == 1
    assert _counts(store) == before


def test_sync_with_a_source_that_is_not_in_the_archive_is_an_error(store, archive):
    with pytest.raises(ArchiveError, match="nope"):
        sync_catalog(store, archive["destination"], sources=["nope"])


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


# -- catalog status reads without changing the catalog -------------------------------


def _raw(spec, sql):
    """Column names and rows, read with a plain connection that never changes the schema."""
    if spec.startswith("sqlite:"):
        with closing(sqlite3.connect(spec[len("sqlite:") :])) as conn:
            cursor = conn.execute(sql)
            return [column[0] for column in cursor.description], cursor.fetchall()
    import psycopg

    with psycopg.connect(spec[len("postgres:") :]) as conn:
        cursor = conn.execute(sql)
        return [column.name for column in cursor.description or ()], cursor.fetchall()


def _has_table(spec, name):
    if spec.startswith("sqlite:"):
        if not Path(spec[len("sqlite:") :]).exists():
            return False
        sql = f"SELECT name FROM sqlite_master WHERE name = '{name}'"
    else:
        sql = f"SELECT relname FROM pg_class WHERE relname = '{name}'"
    return bool(_raw(spec, sql)[1])


def _status(spec, *extra):
    return main(["archive", "catalog", "status", "--store", spec, "--json", *extra])


def test_status_reads_a_catalog_without_replacing_its_views(store_spec, archive, capsys):
    catalog = open_store(store_spec)
    sync_catalog(catalog, archive["destination"])
    with catalog.transaction():
        catalog.execute("DROP VIEW session_copies")
        catalog.execute(
            "CREATE VIEW session_copies AS SELECT agent, session_id, "
            "MAX(message_count) AS max_messages FROM sessions GROUP BY agent, session_id"
        )
    catalog.close()
    capsys.readouterr()

    assert _status(store_spec) == 0

    assert [row["source"] for row in json.loads(capsys.readouterr().out)] == ["laptop"]
    columns, _ = _raw(store_spec, "SELECT * FROM session_copies")
    assert columns == ["agent", "session_id", "max_messages"]


def test_status_of_an_older_catalog_asks_for_a_sync_and_does_not_upgrade_it(store_spec, capsys):
    old = open_store(store_spec)
    with old.transaction():
        old.execute("DROP TABLE pending_sessions")
        old.execute("UPDATE schema_meta SET value = '1' WHERE key = 'version'")
    old.close()

    assert _status(store_spec) == 1

    assert "archive catalog sync" in capsys.readouterr().err
    assert _raw(store_spec, "SELECT value FROM schema_meta WHERE key = 'version'")[1] == [("1",)]
    assert not _has_table(store_spec, "pending_sessions")


def test_status_of_a_newer_catalog_is_refused_without_changing_it(store_spec, capsys):
    newer = open_store(store_spec)
    with newer.transaction():
        newer.execute("UPDATE schema_meta SET value = '99' WHERE key = 'version'")
        newer.execute("DROP VIEW session_copies")
    newer.close()

    assert _status(store_spec) == 1

    assert "schema 99" in capsys.readouterr().err
    assert _raw(store_spec, "SELECT value FROM schema_meta WHERE key = 'version'")[1] == [("99",)]
    assert not _has_table(store_spec, "session_copies")


def test_status_of_a_database_without_a_catalog_is_an_error_and_creates_nothing(store_spec, capsys):
    assert _status(store_spec) == 1

    assert "archive catalog sync" in capsys.readouterr().err
    assert not _has_table(store_spec, "schema_meta")


def test_status_reads_a_sqlite_catalog_it_cannot_write(tmp_path, archive, capsys):
    folder = tmp_path / "shared"
    spec = f"sqlite:{folder / 'catalog.db'}"
    catalog = open_store(spec)
    sync_catalog(catalog, archive["destination"])
    catalog.close()
    (folder / "catalog.db").chmod(0o444)
    folder.chmod(0o555)
    try:
        if os.access(folder / "catalog.db", os.W_OK):
            pytest.skip("this user can write read-only files")
        capsys.readouterr()

        assert _status(spec) == 0

        assert [row["source"] for row in json.loads(capsys.readouterr().out)] == ["laptop"]
    finally:
        folder.chmod(0o755)


# A sync killed part way through a transaction: its rollback journal stays behind.
_INTERRUPTED_WRITE = """
import os, sqlite3, sys
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute("PRAGMA cache_size = 10")
conn.execute("BEGIN")
for number in range(300):
    conn.execute(
        "INSERT INTO sources (name, kind, platform, note) VALUES (?, 'live', 'linux', ?)",
        (f"s{number}", "n" * 1000),
    )
os._exit(0)
"""


def test_status_after_an_interrupted_sync_asks_for_a_sync_and_changes_nothing(
    tmp_path, archive, capsys
):
    db = tmp_path / "catalog.db"
    spec = f"sqlite:{db}"
    catalog = open_store(spec)
    sync_catalog(catalog, archive["destination"])
    catalog.close()
    subprocess.run([sys.executable, "-c", _INTERRUPTED_WRITE, str(db)], check=True)
    journal = db.with_name(db.name + "-journal")
    assert journal.stat().st_size > 0
    before = [db.read_bytes(), journal.read_bytes()]
    capsys.readouterr()

    assert _status(spec) != 0

    error = capsys.readouterr().err
    assert "interrupted sync" in error
    assert "cagelens archive catalog sync" in error
    assert [db.read_bytes(), journal.read_bytes()] == before
    catalog = open_store(spec)
    sync_catalog(catalog, archive["destination"])
    catalog.close()
    assert _status(spec) == 0
    assert [row["source"] for row in json.loads(capsys.readouterr().out)] == ["laptop"]


def test_status_of_a_source_that_is_not_in_the_catalog_is_an_error(store_spec, archive, capsys):
    catalog = open_store(store_spec)
    sync_catalog(catalog, archive["destination"])
    catalog.close()
    capsys.readouterr()

    assert _status(store_spec, "--source", "laptop", "--source", "nope") == 1

    captured = capsys.readouterr()
    assert "nope" in captured.err
    assert captured.out == ""


def test_a_catalog_opened_read_only_refuses_writes(store_spec):
    open_store(store_spec).close()
    reader = open_store(store_spec, read_only=True)
    try:
        with pytest.raises(Exception, match=r"read-?only"):
            with reader.transaction():
                reader.execute("DELETE FROM sources")
    finally:
        reader.close()


# -- a bad manifest stops only its own source ------------------------------------------


def _manifests(archive, source="laptop"):
    return sorted((archive["path"] / f"archive/sources/{source}/manifests").iterdir())


def _remove_version_path(entries):
    (entry,) = [entry for entry in entries if entry.get("action") == "versioned"]
    del entry["version_path"]
    return entry["path"]


def _remove_file_field(name):
    def edit(entries):
        (entry,) = [entry for entry in entries if entry.get("path", "").startswith(".codex/")]
        del entry[name]
        return entry["path"]

    return edit


def _add_rows_entry_without_table(entries):
    entries.append({"type": "rows", "path": ".agent/log.db", "export_path": "x", "rows": 3})
    return ".agent/log.db"


# (how to damage a manifest entry, the field it then lacks, which of two runs to damage)
_MISSING_FIELDS = [
    (_remove_version_path, "version_path", 1),
    (_remove_file_field("size"), "size", 0),
    (_remove_file_field("mtime_ns"), "mtime_ns", 0),
    (_remove_file_field("sha256"), "sha256", 0),
    (_add_rows_entry_without_table, "table", 1),
]


@pytest.mark.parametrize(
    "edit, field, run_index", _MISSING_FIELDS, ids=[case[1] for case in _MISSING_FIELDS]
)
def test_a_manifest_entry_without_a_field_is_an_error_for_its_source_only(
    store, archive, edit, field, run_index
):
    from agent_history.archive.manifest import decode_manifest, encode_manifest

    archive["claude_file"].write_text('{"type":"summary"}\n', encoding="utf-8")
    _settle(archive["claude_file"])
    archive["collect"](hours=1)
    _collect_second_source(archive, "nas")  # sorts after laptop
    manifest = _manifests(archive)[run_index]
    original = manifest.read_bytes()
    run, entries = decode_manifest(original)
    path = edit(entries)  # a hand-edited or foreign manifest
    manifest.write_bytes(encode_manifest(run, entries, 3))

    summary = sync_catalog(store, archive["destination"])

    (error,) = summary.errors
    assert all(part in error for part in ("laptop", run["run_id"], path, field))
    assert _rows(store, "SELECT source, COUNT(*) FROM runs GROUP BY source") == [("nas", 1)]
    manifest.write_bytes(original)

    fixed = sync_catalog(store, archive["destination"])

    assert fixed.errors == []
    assert fixed.runs == 2
    assert _rows(store, "SELECT COUNT(*) FROM runs WHERE source = 'laptop'") == [(2,)]


def test_a_damaged_manifest_is_an_error_for_its_source_only(store, archive):
    _collect_second_source(archive, "nas")
    (manifest,) = _manifests(archive)
    manifest.write_bytes(b"not a manifest")

    summary = sync_catalog(store, archive["destination"])

    (error,) = summary.errors
    assert "laptop" in error and manifest.name in error
    assert _rows(store, "SELECT source FROM runs") == [("nas",)]
