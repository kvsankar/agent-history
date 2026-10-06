"""Tests for archiving agent SQLite databases."""

from __future__ import annotations

import base64
import itertools
import json
import os
import sqlite3
from contextlib import closing
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


@pytest.mark.parametrize("module", ["fts5", "fts4"])
def test_credential_columns_of_full_text_tables_are_blanked_with_their_index(env, module):
    """A full-text table keeps each value in a shadow table and its words in an index."""
    conn = _copilot_data_db(env)
    conn.execute(f"CREATE VIRTUAL TABLE notes USING {module}(title, api_key)")
    conn.executemany(
        "INSERT INTO notes VALUES (?, ?)", [("deploy steps", TOKEN), ("other notes", None)]
    )
    conn.commit()
    conn.close()

    summary = _collect(env)

    path, raw = _restore(env, ".copilot/data.db")
    restored = sqlite3.connect(path)
    assert restored.execute("SELECT title, api_key FROM notes ORDER BY title").fetchall() == [
        ("deploy steps", None),
        ("other notes", None),
    ]
    found = restored.execute("SELECT title FROM notes WHERE notes MATCH 'deploy'").fetchall()
    assert found == [("deploy steps",)]
    assert restored.execute("SELECT * FROM notes WHERE notes MATCH 'gho'").fetchall() == []
    restored.close()
    assert TOKEN.encode() not in raw
    assert b"secretvalue1234567890" not in raw.lower()  # the indexed word
    (entry,) = _entries(env, summary.run_id)
    assert "notes.api_key" in entry["blanked"]


@pytest.mark.parametrize(("columns", "fails"), [("title, body", False), ("title, api_key", True)])
def test_a_full_text_table_whose_module_is_missing_fails_only_with_credential_columns(
    tmp_path, monkeypatch, columns, fails
):
    """Without the table's module its columns cannot be read or blanked."""
    from agent_history.archive import databases
    from agent_history.archive.layouts import DatabaseRule

    path = tmp_path / "data.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(f"CREATE VIRTUAL TABLE notes USING fts5({columns})")
        conn.execute("CREATE TABLE accounts (login TEXT, access_token TEXT)")
        conn.commit()
    real = databases._column_info

    def no_module(conn, table):
        if table == "notes":
            raise sqlite3.OperationalError("no such module: fts5")
        return real(conn, table)

    monkeypatch.setattr(databases, "_column_info", no_module)
    rule = DatabaseRule(pattern="data.db", mode="snapshot")

    if fails:
        with pytest.raises(sqlite3.OperationalError):
            databases.blank_credentials(path, rule)
    else:
        assert databases.blank_credentials(path, rule) == ["accounts.access_token"]


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


def _change_log_keys(env, change):
    """Rewrite the state's log_keys with ``change``; returns the state file's path."""
    from agent_history.archive.state import state_path

    path = state_path(env["state"], str(env["dest"]), "src")
    state = json.loads(path.read_text(encoding="utf-8"))
    state["log_keys"] = change(state["log_keys"])
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def _with_last_key(value):
    return lambda keys: {
        name: (value if not name.endswith("::identity") else found) for name, found in keys.items()
    }


def _with_identity(change):
    return lambda keys: {
        name: (change(found) if name.endswith("::identity") else found)
        for name, found in keys.items()
    }


@pytest.mark.parametrize(
    "change",
    [
        _with_last_key("3"),
        _with_last_key([3]),
        _with_last_key({"key": 3}),
        _with_last_key(True),
        _with_identity(lambda identity: "x"),
        _with_identity(lambda identity: {**identity, "first_key": "1"}),
        _with_identity(lambda identity: {**identity, "first_key": None}),
        _with_identity(lambda identity: {**identity, "first_sha256": 5}),
        _with_identity(lambda identity: {**identity, "last_sha256": ["a"]}),
        _with_identity(lambda identity: {"last_sha256": identity["last_sha256"]}),
    ],
    ids=[
        "last-key-text-beside-a-number-identity",
        "last-key-list",
        "last-key-object",
        "last-key-boolean",
        "identity-text",
        "first-key-text",
        "first-key-missing",
        "first-hash-number",
        "last-hash-list",
        "identity-without-first-key",
    ],
)
def test_log_keys_of_another_type_rebuild_the_state_with_a_warning(env, capsys, change):
    conn = _logs_db(env)
    _add_logs(conn, [1, 2, 3])
    _collect(env)
    path = _change_log_keys(env, change)
    _add_logs(conn, [4])
    conn.close()
    capsys.readouterr()

    summary = _collect(env, hours=1)

    assert summary.errors == 0
    assert str(path) in capsys.readouterr().err
    (entry,) = _entries(env, summary.run_id)
    assert (entry["from_key"], entry["rows"], entry["reset"]) == (3, 1, False)
    assert [row["id"] for row in _exported_rows(env, entry)] == [4]


def test_a_text_last_key_beside_number_keys_exports_from_the_start(env):
    """A state from before table identities, whose key has another type than the table's.

    Such a key cannot place the next row, so the run exports every row again rather than
    fail on every run or skip rows.
    """
    conn = _logs_db(env)
    _add_logs(conn, [1, 2, 3])
    _collect(env)
    _change_log_keys(
        env, lambda keys: {name: "3" for name in keys if not name.endswith("::identity")}
    )
    _add_logs(conn, [4])
    conn.close()

    summary = _collect(env, hours=1)

    assert summary.errors == 0
    (entry,) = _entries(env, summary.run_id)
    assert entry["reset"] is True
    assert [row["id"] for row in _exported_rows(env, entry)] == [1, 2, 3, 4]


def test_log_exports_of_runs_in_the_same_second_do_not_collide(env, monkeypatch):
    from types import SimpleNamespace

    from agent_history.archive import manifest as manifest_module

    monkeypatch.setattr(manifest_module, "secrets", SimpleNamespace(token_hex=lambda n: "abcd"))
    conn = _logs_db(env)
    _add_logs(conn, [1, 2])
    first = _collect(env)
    _add_logs(conn, [3])
    conn.close()
    second = _collect(env)

    (entry1,) = _entries(env, first.run_id)
    (entry2,) = _entries(env, second.run_id)
    assert entry1["export_path"] != entry2["export_path"]
    assert [row["id"] for row in _exported_rows(env, entry1)] == [1, 2]
    assert [row["id"] for row in _exported_rows(env, entry2)] == [3]
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


def _b64url(text):
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()


JWT_HEADER = _b64url('{"alg":"HS256","typ":"JWT"}')
JWT_PAYLOAD = _b64url('{"sub":"alex","exp":1790000000}')
JWT = f"{JWT_HEADER}.{JWT_PAYLOAD}.{_b64url('signature-bytes-for-alex')}"
JWT_UNSIGNED = f"{JWT_HEADER}.{JWT_PAYLOAD}."
JWT_TRUNCATED = f"{JWT_HEADER}.{JWT_PAYLOAD[:20]}"


def _text_logs_db(env, rows):
    path = env["home"] / ".codex" / "logs_2.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, target TEXT, "
        "feedback_log_body TEXT, line INTEGER)"
    )
    conn.executemany("INSERT INTO logs VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    _advance_mtime(path)
    return conn


def _raw_export(env, entry):
    data = (
        env["dest"] / "sources" / "src" / "files" / (entry["export_path"] + ".zst")
    ).read_bytes()
    return zstandard.ZstdDecompressor().decompress(data)


def test_exported_log_rows_have_jwts_replaced_in_every_text_column(env):
    rows = [
        (1, "http", f"sending request: authorization: Bearer {JWT} (retry 1)", 10),
        (2, f"ws {JWT}", f"two tokens {JWT},{JWT_UNSIGNED} done", 11),
        (3, "session", f"header was {JWT_TRUNCATED}… cut", 12),
    ]
    _text_logs_db(env, rows).close()

    summary = _collect(env)

    (entry,) = _entries(env, summary.run_id)
    assert _exported_rows(env, entry) == [
        {
            "id": 1,
            "target": "http",
            "feedback_log_body": "sending request: authorization: Bearer [redacted-jwt] (retry 1)",
            "line": 10,
        },
        {
            "id": 2,
            "target": "ws [redacted-jwt]",
            "feedback_log_body": "two tokens [redacted-jwt],[redacted-jwt] done",
            "line": 11,
        },
        {
            "id": 3,
            "target": "session",
            "feedback_log_body": "header was [redacted-jwt]… cut",
            "line": 12,
        },
    ]
    assert entry["redacted"] == {"jwt": 5}
    raw = _raw_export(env, entry)
    assert JWT_HEADER.encode() not in raw
    assert JWT_PAYLOAD[:20].encode() not in raw
    assert verify_source(open_destination(str(env["dest"])), "src").ok


def test_log_text_that_only_resembles_a_jwt_is_exported_unchanged(env):
    blob = _b64url('{"cursor": "page-2", "filters": ["a", "b"]}' * 3)
    bodies = [
        "plain line without tokens",
        "eyJ followed by short text. eyJabc.def.ghi",
        f"base64 without dots {blob}",
        f"one dot {JWT_HEADER}.{_b64url('not json payload')}",
        "version 1.2.3 and file.name.ext and a.b.c",
    ]
    _text_logs_db(env, [(i, "t", body, i) for i, body in enumerate(bodies, start=1)]).close()

    summary = _collect(env)

    (entry,) = _entries(env, summary.run_id)
    assert [row["feedback_log_body"] for row in _exported_rows(env, entry)] == bodies
    assert "redacted" not in entry


def _base64url_json_blob(size: int) -> str:
    """Base64url of a JSON array of objects: about one "eyJ" every 18 characters, no dots."""
    return _b64url(json.dumps([{"k": i} for i in range(size // 8)], separators=(",", ":")))[:size]


@pytest.mark.parametrize(
    "text",
    [
        _base64url_json_blob(1_000_000),
        _base64url_json_blob(1_000_000) + ".x",
        "eyJ" * 333_333 + ".eyJ",
    ],
    ids=["base64url-without-dots", "base64url-then-a-dot", "repeated-header"],
)
def test_jwt_replacement_takes_linear_time_on_long_base64url_text(text):
    """Each "eyJ" in a long run without a JWT used to scan the rest of the run again.

    A 1 MB value took minutes; it now takes well under a second. The bound is generous.
    """
    import time

    from agent_history.archive.databases import replace_jwts

    started = time.perf_counter()
    replaced, count = replace_jwts(text)

    assert time.perf_counter() - started < 5
    assert (replaced, count) == (text, 0)


def test_jwt_replacement_matches_the_pattern_everywhere():
    """The linear scan replaces exactly what JWT_PATTERN.subn replaces."""
    import random

    from agent_history.archive.databases import JWT_PATTERN, JWT_PLACEHOLDER, replace_jwts

    pieces = ["eyJ", "eyJ", "abcdefghij", "k", "-_", ".", ".", " ", ",", "eyJabcdefghij"]
    rng = random.Random(5)
    texts = [JWT, JWT_UNSIGNED, JWT_TRUNCATED, f"a {JWT}.{JWT} b", f"x{JWT}y.{JWT}"]
    texts += ["".join(rng.choice(pieces) for _ in range(rng.randint(1, 40))) for _ in range(3000)]
    for text in texts:
        assert replace_jwts(text) == JWT_PATTERN.subn(JWT_PLACEHOLDER, text), text


def test_jwt_redaction_keeps_the_reset_identity_stable(env):
    conn = _text_logs_db(env, [(i, "t", f"token {JWT} line {i}", i) for i in (1, 2, 3)])
    first = _collect(env)
    conn.executemany(
        "INSERT INTO logs VALUES (?, ?, ?, ?)",
        [(i, "t", f"token {JWT} line {i}", i) for i in (4, 5)],
    )
    conn.commit()
    conn.close()
    _advance_mtime(env["home"] / ".codex" / "logs_2.sqlite")

    second = _collect(env, hours=1)

    (entry1,) = _entries(env, first.run_id)
    (entry2,) = _entries(env, second.run_id)
    assert entry2["reset"] is False
    assert [row["id"] for row in _exported_rows(env, entry2)] == [4, 5]
    assert entry1["identity"]["first_sha256"] == entry2["identity"]["first_sha256"]
    assert (entry1["redacted"], entry2["redacted"]) == ({"jwt": 3}, {"jwt": 2})
    assert verify_source(open_destination(str(env["dest"])), "src").ok


def test_dry_run_reports_the_jwt_count(env):
    _text_logs_db(env, [(1, "t", f"token {JWT}", 1), (2, "t", "no token", 2)]).close()
    config = parse_config(
        {
            "archive": {"destination": str(env["dest"]), "compression_level": 3},
            "sources": [
                {"name": "src", "kind": "live", "platform": "linux", "home": str(env["home"])}
            ],
        }
    )

    summary = collect_source(config, "src", state_dir=env["state"], now=T0, dry_run=True)

    (entry,) = summary.entries
    assert (entry["rows"], entry["redacted"]) == (2, {"jwt": 1})


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
