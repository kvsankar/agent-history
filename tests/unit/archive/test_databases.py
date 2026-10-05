"""Tests for archiving agent SQLite databases."""

from __future__ import annotations

import itertools
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import zstandard

from agent_history.archive.collect import collect_source
from agent_history.archive.config import parse_config
from agent_history.archive.manifest import read_manifests
from agent_history.archive.transport import open_destination
from agent_history.archive.verify import verify_source

T0 = datetime(2026, 10, 2, 6, 15, tzinfo=timezone.utc)
TOKEN = "gho_SECRETVALUE1234567890"


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {
        "home": home,
        "dest": tmp_path / "archive",
        "state": tmp_path / "state",
        "tmp": tmp_path,
    }


def _collect(env, hours=0):
    config = parse_config(
        {
            "archive": {"destination": str(env["dest"]), "compression_level": 3},
            "sources": [
                {"name": "src", "kind": "live", "platform": "linux", "home": str(env["home"])}
            ],
        }
    )
    return collect_source(config, "src", state_dir=env["state"], now=T0 + timedelta(hours=hours))


def _entries(env, run_id):
    for run, entries in read_manifests(open_destination(str(env["dest"])), "src"):
        if run["run_id"] == run_id:
            return [entry for entry in entries if entry["type"] != "run"]
    raise AssertionError(run_id)


def _restore(env, rel, tmp_name="restored.db"):
    data = (env["dest"] / "sources" / "src" / "files" / f"{rel}.zst").read_bytes()
    raw = zstandard.ZstdDecompressor().decompress(data)
    path = env["tmp"] / tmp_name
    path.write_bytes(raw)
    return path, raw


def _copilot_data_db(env):
    path = env["home"] / ".copilot" / "data.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, login TEXT, access_token TEXT)")
    conn.execute("CREATE TABLE settings (id INTEGER, github_access_token TEXT, theme TEXT)")
    conn.execute("CREATE TABLE usage (session TEXT, input_tokens INTEGER, client_secret TEXT)")
    conn.execute("INSERT INTO accounts VALUES (1, 'alex', ?)", (TOKEN,))
    conn.execute("INSERT INTO settings VALUES (1, ?, 'dark')", (TOKEN,))
    conn.execute("INSERT INTO usage VALUES ('s1', 42, ?)", (TOKEN,))
    conn.commit()
    return conn


def test_snapshot_includes_wal_content_and_blanks_credentials(env):
    conn = _copilot_data_db(env)  # stays open, so recent writes are still in the WAL

    summary = _collect(env)

    conn.close()
    path, raw = _restore(env, ".copilot/data.db")
    restored = sqlite3.connect(path)
    assert restored.execute("SELECT login, access_token FROM accounts").fetchall() == [
        ("alex", None)
    ]
    assert restored.execute("SELECT github_access_token, theme FROM settings").fetchall() == [
        (None, "dark")
    ]
    assert restored.execute("SELECT input_tokens, client_secret FROM usage").fetchall() == [
        (42, None)
    ]
    assert TOKEN.encode() not in raw
    (entry,) = _entries(env, summary.run_id)
    assert entry["kind"] == "sqlite-snapshot"
    assert sorted(entry["blanked"]) == [
        "accounts.access_token",
        "settings.github_access_token",
        "usage.client_secret",
    ]


def test_not_null_credential_columns_are_blanked_with_allowed_values(env):
    path = env["home"] / ".copilot" / "data.db"
    path.parent.mkdir(parents=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE accounts (id INTEGER PRIMARY KEY, login TEXT, "
        "access_token TEXT NOT NULL, refresh_token BLOB NOT NULL, api_key INTEGER NOT NULL)"
    )
    # REPLACE would delete a row if two rows were given the same blank value.
    conn.execute(
        "CREATE TABLE keys (id INTEGER, client_secret TEXT NOT NULL UNIQUE ON CONFLICT REPLACE)"
    )
    conn.execute(
        "CREATE TABLE checked (id INTEGER, secret TEXT NOT NULL CHECK (length(secret) > 8))"
    )
    conn.execute(
        "CREATE TABLE strict_keys (id INTEGER, password TEXT NOT NULL) STRICT"
        if sqlite3.sqlite_version_info >= (3, 37)
        else "CREATE TABLE strict_keys (id INTEGER, password TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO accounts VALUES (1, 'alex', ?, ?, 7)", (TOKEN, TOKEN.encode()))
    conn.executemany("INSERT INTO keys VALUES (?, ?)", [(1, TOKEN), (2, TOKEN + "2")])
    conn.execute("INSERT INTO checked VALUES (1, ?)", (TOKEN,))
    conn.execute("INSERT INTO strict_keys VALUES (1, ?)", (TOKEN,))
    conn.commit()
    conn.close()

    summary = _collect(env)

    assert summary.errors == 0
    restored_path, raw = _restore(env, ".copilot/data.db")
    restored = sqlite3.connect(restored_path)
    assert restored.execute(
        "SELECT login, access_token, refresh_token, api_key FROM accounts"
    ).fetchall() == [("alex", "", b"", 0)]
    secrets = [row[0] for row in restored.execute("SELECT client_secret FROM keys")]
    assert len(set(secrets)) == 2
    (checked,) = restored.execute("SELECT secret FROM checked").fetchone()
    assert checked != TOKEN
    assert restored.execute("SELECT password FROM strict_keys").fetchall() == [("",)]
    assert TOKEN.encode() not in raw
    (entry,) = _entries(env, summary.run_id)
    assert entry["blanked"] == [
        "accounts.access_token",
        "accounts.api_key",
        "accounts.refresh_token",
        "checked.secret",
        "keys.client_secret",
        "strict_keys.password",
    ]


def test_unchanged_database_is_not_copied_again(env):
    _copilot_data_db(env).close()
    _advance_mtime(env["home"] / ".copilot" / "data.db")
    _collect(env)

    later = _collect(env, hours=1)

    assert _entries(env, later.run_id) == []


def test_changed_database_keeps_the_previous_snapshot(env):
    conn = _copilot_data_db(env)
    _collect(env)
    conn.execute("INSERT INTO accounts VALUES (2, 'sam', 'x')")
    conn.commit()
    conn.close()
    _advance_mtime(env["home"] / ".copilot" / "data.db")

    summary = _collect(env, hours=1)

    (entry,) = _entries(env, summary.run_id)
    assert entry["action"] == "versioned"
    assert (env["dest"] / "sources" / "src" / entry["version_path"]).exists()
    path, _raw = _restore(env, ".copilot/data.db")
    assert sqlite3.connect(path).execute("SELECT COUNT(*) FROM accounts").fetchone() == (2,)
    assert verify_source(open_destination(str(env["dest"])), "src").ok


def _logs_db(env, name="logs_2.sqlite"):
    path = env["home"] / ".codex" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, ts INTEGER, body BLOB)")
    return conn


def _add_logs(conn, ids):
    conn.executemany("INSERT INTO logs VALUES (?, ?, ?)", [(i, 1000 + i, f"line {i}") for i in ids])
    conn.commit()
    _advance_mtime(Path(conn.execute("PRAGMA database_list").fetchone()[2]))


_STAMPS = itertools.count(1_700_000_000, 10)


def _advance_mtime(path):
    """Writes within one filesystem tick can leave the time unchanged; set a later one."""
    stamp = next(_STAMPS)
    os.utime(path, (stamp, stamp))


def _exported_rows(env, entry):
    data = (
        env["dest"] / "sources" / "src" / "files" / (entry["export_path"] + ".zst")
    ).read_bytes()
    lines = zstandard.ZstdDecompressor().decompress(data).decode().splitlines()
    return [json.loads(line) for line in lines]


def test_log_database_exports_only_new_rows(env):
    conn = _logs_db(env)
    _add_logs(conn, [1, 2, 3])
    first = _collect(env)
    _add_logs(conn, [4, 5])
    conn.close()
    second = _collect(env, hours=1)

    (entry1,) = _entries(env, first.run_id)
    (entry2,) = _entries(env, second.run_id)
    assert entry1["type"] == "rows"
    assert [row["id"] for row in _exported_rows(env, entry1)] == [1, 2, 3]
    assert (entry2["from_key"], entry2["to_key"], entry2["rows"]) == (3, 5, 2)
    assert [row["id"] for row in _exported_rows(env, entry2)] == [4, 5]
    assert _exported_rows(env, entry2)[0]["body"] == "line 4"
    assert not (env["dest"] / "sources" / "src" / "files" / ".codex" / "logs_2.sqlite.zst").exists()
    assert verify_source(open_destination(str(env["dest"])), "src").ok


def test_recreated_log_database_exports_from_the_start(env):
    conn = _logs_db(env)
    _add_logs(conn, [1, 2, 3, 4])
    conn.close()
    _collect(env)
    (env["home"] / ".codex" / "logs_2.sqlite").unlink()
    conn = _logs_db(env)
    _add_logs(conn, [1, 2])
    conn.close()

    summary = _collect(env, hours=1)

    (entry,) = _entries(env, summary.run_id)
    assert entry["reset"] is True
    assert [row["id"] for row in _exported_rows(env, entry)] == [1, 2]


@pytest.mark.parametrize("lose_state", [False, True])
def test_recreated_log_database_that_grew_past_the_last_key_is_a_reset(env, lose_state):
    conn = _logs_db(env)
    _add_logs(conn, [1, 2, 3])
    conn.close()
    _collect(env)
    (env["home"] / ".codex" / "logs_2.sqlite").unlink()
    conn = _logs_db(env)
    rows = [(i, 9000 + i, f"after {i}") for i in range(1, 6)]
    conn.executemany("INSERT INTO logs VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()
    _advance_mtime(env["home"] / ".codex" / "logs_2.sqlite")
    if lose_state:  # the state is rebuilt from the manifests
        for path in env["state"].rglob("*.json"):
            path.unlink()

    summary = _collect(env, hours=1)

    (entry,) = _entries(env, summary.run_id)
    assert entry["reset"] is True
    assert entry["from_key"] is None
    assert [row["body"] for row in _exported_rows(env, entry)] == [r[2] for r in rows]


def test_log_table_starting_again_below_the_old_keys_is_a_reset(env):
    conn = _logs_db(env)
    _add_logs(conn, [5, 6, 7])
    _collect(env)
    conn.execute("DELETE FROM logs")
    _add_logs(conn, range(1, 10))  # rows 5 to 7 even have the same content as before
    conn.close()

    summary = _collect(env, hours=1)

    (entry,) = _entries(env, summary.run_id)
    assert entry["reset"] is True
    assert [row["id"] for row in _exported_rows(env, entry)] == list(range(1, 10))


def test_pruned_log_rows_are_not_a_reset(env):
    conn = _logs_db(env)
    _add_logs(conn, [1, 2, 3])
    _collect(env)
    conn.execute("DELETE FROM logs WHERE id <= 2")
    _add_logs(conn, [4, 5])
    conn.close()

    summary = _collect(env, hours=1)

    (entry,) = _entries(env, summary.run_id)
    assert (entry["reset"], entry["from_key"], entry["to_key"]) == (False, 3, 5)
    assert [row["id"] for row in _exported_rows(env, entry)] == [4, 5]


def test_log_rows_pruned_past_the_last_export_are_exported_once(env):
    conn = _logs_db(env)
    _add_logs(conn, [1, 2, 3])
    _collect(env)
    conn.execute("DELETE FROM logs WHERE id <= 4")
    _add_logs(conn, [6, 7])
    conn.close()

    summary = _collect(env, hours=1)

    (entry,) = _entries(env, summary.run_id)
    assert entry["reset"] is False
    assert [row["id"] for row in _exported_rows(env, entry)] == [6, 7]


def test_exported_log_rows_have_credential_columns_blanked(env):
    path = env["home"] / ".codex" / "logs_2.sqlite"
    path.parent.mkdir(parents=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE logs (id INTEGER PRIMARY KEY, body TEXT, api_key TEXT, input_tokens INTEGER)"
    )
    conn.execute("INSERT INTO logs VALUES (1, 'line 1', ?, 42)", (TOKEN,))
    conn.commit()
    conn.close()

    summary = _collect(env)

    (entry,) = _entries(env, summary.run_id)
    assert _exported_rows(env, entry) == [
        {"id": 1, "body": "line 1", "api_key": None, "input_tokens": 42}
    ]
    assert entry["blanked"] == ["logs.api_key"]
    data = (
        env["dest"] / "sources" / "src" / "files" / (entry["export_path"] + ".zst")
    ).read_bytes()
    assert TOKEN.encode() not in zstandard.ZstdDecompressor().decompress(data)


def test_dry_run_counts_new_log_rows_without_compressing(env, monkeypatch):
    from agent_history.archive import databases

    conn = _logs_db(env)
    _add_logs(conn, [1, 2, 3])
    conn.close()

    def fail(*args, **kwargs):
        raise AssertionError("dry run compressed rows")

    monkeypatch.setattr(databases, "compress_file", fail)
    config = parse_config(
        {
            "archive": {"destination": str(env["dest"]), "compression_level": 3},
            "sources": [
                {"name": "src", "kind": "live", "platform": "linux", "home": str(env["home"])}
            ],
        }
    )

    summary = collect_source(config, "src", state_dir=env["state"], now=T0, dry_run=True)

    assert summary.errors == 0
    (entry,) = summary.entries
    assert (entry["type"], entry["rows"], entry["to_key"]) == ("rows", 3, 3)
    assert "export_path" not in entry


def test_new_log_file_name_starts_its_own_export(env):
    old = _logs_db(env)
    _add_logs(old, [1, 2])
    old.close()
    _collect(env)
    new = _logs_db(env, "logs_3.sqlite")
    _add_logs(new, [1])
    new.close()

    summary = _collect(env, hours=1)

    (entry,) = _entries(env, summary.run_id)
    assert entry["path"] == ".codex/logs_3.sqlite"
    assert entry["from_key"] is None


def test_log_database_without_new_rows_writes_nothing(env):
    conn = _logs_db(env)
    _add_logs(conn, [1])
    _collect(env)
    conn.execute("UPDATE logs SET ts = 5 WHERE id = 1")
    conn.commit()
    conn.close()
    _advance_mtime(env["home"] / ".codex" / "logs_2.sqlite")

    summary = _collect(env, hours=1)

    assert summary.written == 0


def test_unreadable_database_is_recorded_and_the_run_continues(env):
    bad = env["home"] / ".codex" / "state_5.sqlite"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"not a database at all" * 100)
    (env["home"] / ".codex" / "history.jsonl").write_text("h\n", encoding="utf-8")

    summary = _collect(env)

    assert summary.errors == 1
    assert summary.written == 1
    errors = [e for e in _entries(env, summary.run_id) if e["type"] == "error"]
    assert errors[0]["path"] == ".codex/state_5.sqlite"


def test_recently_modified_database_is_checked_again(env):
    conn = _copilot_data_db(env)
    conn.close()  # modified just now
    db = env["home"] / ".copilot" / "data.db"
    first = _collect(env)
    stamp = db.stat().st_mtime_ns
    conn = sqlite3.connect(db)
    conn.execute("UPDATE settings SET theme = 'pale'")  # same size, same page
    conn.commit()
    conn.close()
    os.utime(db, ns=(stamp, stamp))

    second = _collect(env, hours=1)

    (entry1,) = _entries(env, first.run_id)
    (entry2,) = _entries(env, second.run_id)
    assert entry1["racy"] is True
    assert entry2["action"] == "versioned"


@pytest.mark.parametrize("kind", ["snapshot", "log"])
def test_racy_check_uses_the_time_the_database_was_read(env, monkeypatch, kind):
    """A slow copy must not hide that the database was modified just before it was read."""
    import time as time_module

    from agent_history.archive import databases as databases_module

    if kind == "snapshot":
        _copilot_data_db(env).close()  # modified just now
    else:
        conn = _logs_db(env)
        conn.executemany("INSERT INTO logs VALUES (?, ?, ?)", [(1, 1, "a")])
        conn.commit()
        conn.close()
    real_time_ns = time_module.time_ns
    offset = [0]
    monkeypatch.setattr(time_module, "time_ns", lambda: real_time_ns() + offset[0])
    real_backup = databases_module.backup_database

    def slow_backup(*args, **kwargs):
        real_backup(*args, **kwargs)
        offset[0] = 10_000_000_000  # the copy took ten seconds

    monkeypatch.setattr(databases_module, "backup_database", slow_backup)

    summary = _collect(env)

    (entry,) = _entries(env, summary.run_id)
    assert entry["racy"] is True


def test_database_that_cannot_be_opened_read_only_is_copied_first(env, monkeypatch):
    """Network filesystems (WSL's /mnt/c) cannot open WAL databases read-only."""
    from agent_history.archive import databases

    def refuse(path):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(databases, "_open_read_only", refuse)
    conn = _copilot_data_db(env)  # open: recent rows are only in the WAL

    summary = _collect(env)

    conn.close()
    assert summary.errors == 0
    path, _raw = _restore(env, ".copilot/data.db")
    assert sqlite3.connect(path).execute("SELECT login FROM accounts").fetchall() == [("alex",)]
