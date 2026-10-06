"""Collector runs whose source folders are missing, unreadable or overlapping."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import zstandard

from agent_history.archive.collect import collect_source
from agent_history.archive.config import parse_config
from agent_history.archive.errors import ArchiveError
from agent_history.archive.manifest import read_manifests
from agent_history.archive.transport import open_destination

T0 = datetime(2026, 10, 2, 6, 15, tzinfo=timezone.utc)
SESSION = ".claude/projects/-home-alex-shop/a1.jsonl"


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {"tmp": tmp_path, "home": home, "dest": tmp_path / "archive", "state": tmp_path / "s"}


def _config(env, *extra_entries):
    entry = {"name": "src", "kind": "live", "platform": "linux", "home": str(env["home"])}
    return parse_config(
        {
            "archive": {"destination": str(env["dest"]), "compression_level": 3},
            "sources": [entry, *extra_entries],
        }
    )


def _write(root: Path, rel: str, data: bytes, mtime: int = 1_790_000_000) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))
    return path


def _collect(env, hours=0, config=None):
    config = config or _config(env)
    return collect_source(
        config, "src", state_dir=env["state"], now=T0 + timedelta(hours=hours), force=True
    )


def _run_entries(env, run_id):
    for run, entries in read_manifests(open_destination(str(env["dest"])), "src"):
        if run["run_id"] == run_id:
            return entries
    raise AssertionError(run_id)


def test_missing_home_fails_the_run_and_marks_nothing_gone(env):
    _write(env["home"], SESSION, b"a\n")
    first = _collect(env)
    env["home"].rename(env["tmp"] / "unmounted")

    with pytest.raises(ArchiveError):
        _collect(env, hours=1)

    runs = list(read_manifests(open_destination(str(env["dest"])), "src"))
    assert [run["run_id"] for run, _entries in runs] == [first.run_id]
    (env["tmp"] / "unmounted").rename(env["home"])
    later = _collect(env, hours=2)
    assert later.gone == 0


def test_unreadable_folder_is_an_error_and_its_files_are_not_gone(env, monkeypatch):
    from agent_history.archive import layouts

    _write(env["home"], SESSION, b"a\n")
    _write(env["home"], ".claude/history.jsonl", b"h\n")
    _collect(env)
    _write(env["home"], ".claude/projects/-home-alex-shop/b2.jsonl", b"b\n")
    _write(env["home"], ".claude/projects/-home-alex-web/c3.jsonl", b"c\n")
    locked = env["home"] / ".claude" / "projects" / "-home-alex-shop"
    real_scandir = layouts.os.scandir

    def scandir(path):
        if not isinstance(path, int) and Path(path) == locked:  # rmtree passes fds
            raise PermissionError(13, "Permission denied", str(path))
        return real_scandir(path)

    monkeypatch.setattr(layouts.os, "scandir", scandir)

    summary = _collect(env, hours=1)

    assert summary.gone == 0
    assert summary.errors == 1
    entries = {entry["path"]: entry for entry in _run_entries(env, summary.run_id)}
    assert entries[".claude/projects/-home-alex-shop"]["type"] == "error"
    assert entries[".claude/projects/-home-alex-web/c3.jsonl"]["action"] == "added"


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permissions that apply to the user running the tests",
)
def test_folder_without_permissions_does_not_abort_the_run(env):
    _write(env["home"], SESSION, b"a\n")
    _collect(env)
    locked = env["home"] / ".claude" / "projects" / "-home-alex-shop"
    locked.chmod(0)
    try:
        summary = _collect(env, hours=1)
    finally:
        locked.chmod(0o755)

    assert (summary.errors, summary.gone) == (1, 0)


def test_differing_copy_in_a_merged_part_is_an_error_not_dropped(env):
    old = env["tmp"] / "old-home"
    _write(env["home"], "notes/a.md", b"live\n", mtime=1_790_000_000)
    _write(old, "notes/a.md", b"older, other text\n", mtime=1_780_000_000)
    _write(old, "notes/z9.md", b"only in the old home\n")
    live = {"name": "src", "kind": "live", "platform": "linux", "home": str(env["home"])}
    live["include"] = ["notes/**"]
    merged = {"name": "src", "kind": "live", "platform": "linux", "home": str(old)}
    merged.update(agents=[], include=["notes/**"])
    config = parse_config(
        {
            "archive": {"destination": str(env["dest"]), "compression_level": 3},
            "sources": [live, merged],
        }
    )

    summary = _collect(env, config=config)

    assert summary.errors == 1
    assert summary.written == 2
    entries = _run_entries(env, summary.run_id)
    (error,) = [entry for entry in entries if entry["type"] == "error"]
    assert error["path"] == "notes/a.md"
    assert "old-home" in error["message"]


def test_an_include_snapshots_a_database_that_no_layout_names(env):
    key = "sk-" + "y" * 40
    db = env["home"] / "tools" / "app" / "store.bin"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE providers (id INTEGER PRIMARY KEY, name TEXT, api_key TEXT)")
    conn.execute("INSERT INTO providers (name, api_key) VALUES ('main', ?)", (key,))
    conn.commit()  # the row stays in store.bin-wal while the connection is open
    entry = {
        "name": "src",
        "kind": "live",
        "platform": "linux",
        "home": str(env["home"]),
        "agents": [],
        "include": ["tools/**"],
    }
    config = parse_config(
        {"archive": {"destination": str(env["dest"]), "compression_level": 3}, "sources": [entry]}
    )
    try:
        summary = _collect(env, config=config)
    finally:
        conn.close()

    entries = {entry["path"]: entry for entry in _run_entries(env, summary.run_id)}
    assert set(entries) == {"tools/app/store.bin"}
    assert entries["tools/app/store.bin"]["kind"] == "sqlite-snapshot"
    assert entries["tools/app/store.bin"]["blanked"] == ["providers.api_key"]
    restored = env["tmp"] / "restored.db"
    archived = env["dest"] / "sources/src/files/tools/app/store.bin.zst"
    restored.write_bytes(zstandard.ZstdDecompressor().decompress(archived.read_bytes()))
    assert key.encode() not in restored.read_bytes()
    with sqlite3.connect(restored) as check:
        assert check.execute("SELECT name, api_key FROM providers").fetchall() == [("main", None)]


def test_a_wildcard_include_leaves_an_agent_database_to_its_layout(env):
    token = "gho_" + "x" * 36
    db = env["home"] / ".copilot" / "data.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, access_token TEXT)")
    conn.execute("INSERT INTO accounts (access_token) VALUES (?)", (token,))
    conn.commit()  # the row stays in data.db-wal while the connection is open
    _write(env["home"], ".copilot/command-history-state.json", b"{}")
    _write(env["home"], "notes/n.md", b"note\n")
    entry = {"name": "src", "kind": "live", "platform": "linux", "home": str(env["home"])}
    entry["include"] = ["**"]
    config = parse_config(
        {"archive": {"destination": str(env["dest"]), "compression_level": 3}, "sources": [entry]}
    )
    try:
        summary = _collect(env, config=config)
    finally:
        conn.close()

    entries = _run_entries(env, summary.run_id)
    assert sorted(entry["path"] for entry in entries) == [".copilot/data.db", "notes/n.md"]
    data_db = next(entry for entry in entries if entry["path"] == ".copilot/data.db")
    assert (data_db["kind"], data_db["agent"]) == ("sqlite-snapshot", "copilot-cli")
    restored = env["tmp"] / "restored.db"
    archived = env["dest"] / "sources/src/files/.copilot/data.db.zst"
    restored.write_bytes(zstandard.ZstdDecompressor().decompress(archived.read_bytes()))
    assert token.encode() not in restored.read_bytes()
    with sqlite3.connect(restored) as check:
        assert check.execute("SELECT COUNT(*) FROM accounts").fetchone() == (1,)
