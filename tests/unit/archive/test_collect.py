"""Tests for collecting a source into a local archive."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import zstandard

from agent_history.archive.collect import CollectLockedError, collect_source
from agent_history.archive.config import parse_config
from agent_history.archive.manifest import read_manifests
from agent_history.archive.transport import open_destination
from agent_history.archive.verify import verify_source

T0 = datetime(2026, 10, 2, 6, 15, tzinfo=timezone.utc)
SESSION = ".claude/projects/-home-alex-shop/a1.jsonl"


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    dest = tmp_path / "archive"
    state = tmp_path / "state"
    home.mkdir()
    return {"home": home, "dest": dest, "state": state}


def _config(env, **archive):
    settings = {"destination": str(env["dest"]), "compression_level": 3}
    settings.update(archive)
    return parse_config(
        {
            "archive": settings,
            "sources": [
                {"name": "src", "kind": "live", "platform": "linux", "home": str(env["home"])}
            ],
        }
    )


def _write(env, rel, data: bytes, mtime: float = None):
    path = env["home"] / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _archived(env, rel) -> bytes:
    path = env["dest"] / "sources" / "src" / "files" / f"{rel}.zst"
    return zstandard.ZstdDecompressor().decompress(path.read_bytes())


def _collect(env, now=T0, **kwargs):
    config = kwargs.pop("config", None) or _config(env)
    return collect_source(config, "src", state_dir=env["state"], now=now, **kwargs)


def _entries(env, run_id):
    destination = open_destination(str(env["dest"]))
    for run, entries in read_manifests(destination, "src"):
        if run["run_id"] == run_id:
            return {entry["path"]: entry for entry in entries if entry["type"] == "file"}
    raise AssertionError(f"no manifest for {run_id}")


def test_first_run_archives_files_and_writes_a_manifest(env):
    path = _write(env, SESSION, b'{"n": 1}\n', mtime=1_790_000_000)

    summary = _collect(env)

    assert summary.written == 1
    assert _archived(env, SESSION) == b'{"n": 1}\n'
    archived = env["dest"] / "sources" / "src" / "files" / f"{SESSION}.zst"
    assert archived.stat().st_mtime == pytest.approx(path.stat().st_mtime)
    entry = _entries(env, summary.run_id)[SESSION]
    assert entry["action"] == "added"
    assert entry["agent"] == "claude"
    assert entry["size"] == 9
    assert entry["sha256"] == hashlib.sha256(b'{"n": 1}\n').hexdigest()
    assert (env["dest"] / "ARCHIVE.json").exists()
    assert (env["dest"] / "sources" / "src" / "SOURCE.json").exists()


def test_unchanged_files_are_not_rewritten(env):
    _write(env, SESSION, b"a\n", mtime=1_790_000_000)
    _collect(env)

    summary = _collect(env, now=T0 + timedelta(hours=1))

    assert summary.written == 0
    assert _entries(env, summary.run_id) == {}


def test_recently_modified_file_is_checked_again(env):
    """A change in the same timestamp tick as the read can keep size and time unchanged."""
    path = _write(env, SESSION, b"abc\n")  # modified just now
    first = _collect(env)
    stamp = path.stat().st_mtime_ns
    path.write_bytes(b"xyz\n")  # same size; force the same time to model one tick
    os.utime(path, ns=(stamp, stamp))

    second = _collect(env, now=T0 + timedelta(hours=1))

    assert _entries(env, first.run_id)[SESSION]["racy"] is True
    assert _entries(env, second.run_id)[SESSION]["action"] == "versioned"
    assert _archived(env, SESSION) == b"xyz\n"


def test_appended_file_is_updated_in_place(env):
    _write(env, SESSION, b"a\n", mtime=1_790_000_000)
    _collect(env)
    _write(env, SESSION, b"a\nb\n", mtime=1_790_000_100)

    summary = _collect(env, now=T0 + timedelta(hours=1))

    assert _entries(env, summary.run_id)[SESSION]["action"] == "updated"
    assert _archived(env, SESSION) == b"a\nb\n"
    assert not (env["dest"] / "sources" / "src" / "versions").exists()


@pytest.mark.parametrize("new", [b"x\n", b"changed-start\nmore\n"])
def test_rewritten_file_keeps_the_previous_version(env, new):
    _write(env, SESSION, b"original\n", mtime=1_790_000_000)
    _collect(env)
    _write(env, SESSION, new, mtime=1_790_000_100)

    summary = _collect(env, now=T0 + timedelta(hours=1))

    entry = _entries(env, summary.run_id)[SESSION]
    assert entry["action"] == "versioned"
    assert entry["previous_sha256"] == hashlib.sha256(b"original\n").hexdigest()
    version = env["dest"] / "sources" / "src" / entry["version_path"]
    assert zstandard.ZstdDecompressor().decompress(version.read_bytes()) == b"original\n"
    assert _archived(env, SESSION) == new


def test_deleted_source_file_is_kept_and_reported_gone(env):
    path = _write(env, SESSION, b"a\n")
    _collect(env)
    path.unlink()

    summary = _collect(env, now=T0 + timedelta(hours=1))

    assert _entries(env, summary.run_id)[SESSION]["action"] == "gone"
    assert _archived(env, SESSION) == b"a\n"
    later = _collect(env, now=T0 + timedelta(hours=2))
    assert _entries(env, later.run_id) == {}


def test_min_interval_skips_recent_runs_unless_forced(env):
    _write(env, SESSION, b"a\n")
    config = _config(env, min_interval_hours=20)
    _collect(env, config=config)
    _write(env, SESSION, b"a\nb\n", mtime=1_800_000_000)

    skipped = _collect(env, now=T0 + timedelta(hours=1), config=config)
    forced = _collect(env, now=T0 + timedelta(hours=1), config=config, force=True)

    assert skipped.skipped_reason == "min_interval"
    assert forced.written == 1


def test_missing_state_is_rebuilt_from_manifests(env):
    _write(env, SESSION, b"a\n")
    _collect(env)
    for state_file in env["state"].rglob("*.json"):
        state_file.unlink()

    summary = _collect(env, now=T0 + timedelta(hours=1))

    assert summary.written == 0


def test_dry_run_writes_nothing(env):
    _write(env, SESSION, b"a\n")

    summary = _collect(env, dry_run=True)

    assert summary.written == 1
    assert not env["dest"].exists()
    assert not env["state"].exists() or not list(env["state"].rglob("*.json"))


def test_a_held_lock_stops_a_second_run(env):
    from agent_history.archive.collect import source_lock

    _write(env, SESSION, b"a\n")
    config = _config(env)
    with source_lock(env["state"], config.destination, "src"):
        with pytest.raises(CollectLockedError):
            _collect(env, config=config)


def test_unreadable_file_is_recorded_and_retried(env, monkeypatch):
    from agent_history.archive import collect as collect_module

    _write(env, SESSION, b"a\n")
    real = collect_module.compress_file

    def failing(src, *args, **kwargs):
        raise OSError("device busy")

    monkeypatch.setattr(collect_module, "compress_file", failing)
    first = _collect(env)
    monkeypatch.setattr(collect_module, "compress_file", real)
    second = _collect(env, now=T0 + timedelta(hours=1))

    assert first.errors == 1
    assert first.written == 0
    assert second.written == 1


def test_verify_passes_then_detects_corruption_and_unlisted_files(env):
    _write(env, SESSION, b"a\n")
    _write(env, ".codex/history.jsonl", b"h\n")
    _collect(env)
    destination = open_destination(str(env["dest"]))

    clean = verify_source(destination, "src")
    archived = env["dest"] / "sources" / "src" / "files" / f"{SESSION}.zst"
    archived.write_bytes(zstandard.ZstdCompressor().compress(b"tampered\n"))
    stray = env["dest"] / "sources" / "src" / "files" / "stray.jsonl.zst"
    stray.write_bytes(zstandard.ZstdCompressor().compress(b"x"))
    dirty = verify_source(destination, "src")

    assert clean.checked == 2
    assert clean.ok
    assert dirty.mismatched == [SESSION]
    assert dirty.unlisted == ["stray.jsonl"]
    assert not dirty.ok


def test_verify_checks_versions(env):
    _write(env, SESSION, b"original\n", mtime=1_790_000_000)
    _collect(env)
    _write(env, SESSION, b"new\n", mtime=1_790_000_100)
    _collect(env, now=T0 + timedelta(hours=1))

    report = verify_source(open_destination(str(env["dest"])), "src")

    assert report.checked == 2
    assert report.ok


def test_archive_with_unknown_format_is_refused(env):
    from agent_history.archive.errors import ArchiveError

    env["dest"].mkdir()
    (env["dest"] / "ARCHIVE.json").write_text('{"format": 99}', encoding="utf-8")
    _write(env, SESSION, b"a\n")

    with pytest.raises(ArchiveError, match="format"):
        _collect(env)


def test_source_kind_is_recorded(env):
    import json

    _write(env, SESSION, b"a\n")
    _collect(env)

    descriptor = json.loads((env["dest"] / "sources" / "src" / "SOURCE.json").read_text())
    assert descriptor == {"name": "src", "kind": "live", "platform": "linux", "note": ""}


def test_paths_are_never_written_outside_the_archive(env):
    _write(env, SESSION, b"a\n")
    _collect(env)

    written = [p for p in env["dest"].rglob("*") if p.is_file()]
    assert all(Path(os.path.commonpath([env["dest"], p])) == env["dest"] for p in written)


def test_staging_lives_in_the_state_folder_and_is_removed(env, monkeypatch):
    import tempfile as tempfile_module

    from agent_history.archive import collect as collect_module

    _write(env, SESSION, b"a\n")
    seen = []
    real = collect_module.compress_file

    def spy(src, dst, *args, **kwargs):
        seen.append(Path(dst))
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(collect_module, "compress_file", spy)
    monkeypatch.setattr(tempfile_module, "tempdir", str(env["home"] / "no-system-temp"))

    _collect(env)

    assert seen
    assert all(env["state"] in path.parents for path in seen)
    assert not list((env["state"]).rglob("*.zst"))


def test_large_runs_transfer_in_batches(env, monkeypatch):
    from agent_history.archive import collect as collect_module

    for index in range(5):
        _write(
            env, f".claude/projects/p/s{index}.jsonl", bytes(range(256)) * 40, mtime=1_790_000_000
        )
    from agent_history.archive.transport import LocalDestination

    monkeypatch.setattr(collect_module, "BATCH_BYTES", 1)
    calls = []
    real_put = LocalDestination.put_tree

    def counting(self, staging):
        calls.append(sum(1 for p in Path(staging).rglob("*") if p.is_file()))
        return real_put(self, staging)

    monkeypatch.setattr(LocalDestination, "put_tree", counting)

    summary = _collect(env, config=_config(env, workers=1))

    assert summary.written == 5
    assert len(calls) >= 2
    assert verify_source(open_destination(str(env["dest"])), "src").ok


def test_dry_run_does_not_compress(env, monkeypatch):
    from agent_history.archive import collect as collect_module

    _write(env, SESSION, b"original\n", mtime=1_790_000_000)
    _collect(env)
    _write(env, SESSION, b"rewritten\n", mtime=1_790_000_100)

    def fail(*args, **kwargs):
        raise AssertionError("dry run compressed a file")

    monkeypatch.setattr(collect_module, "compress_file", fail)
    summary = _collect(env, now=T0 + timedelta(hours=1), dry_run=True)

    assert [entry["action"] for entry in summary.entries] == ["versioned"]


def test_parallel_workers_give_the_same_archive(env):
    for index in range(20):
        _write(
            env, f".claude/projects/p/s{index}.jsonl", f"{index}\n".encode(), mtime=1_790_000_000
        )
    config = _config(env, workers=4)

    summary = _collect(env, config=config)

    assert summary.written == 20
    assert _archived(env, ".claude/projects/p/s7.jsonl") == b"7\n"
    assert verify_source(open_destination(str(env["dest"])), "src").ok


def test_a_slow_file_does_not_hold_up_the_others(env, monkeypatch):
    import threading

    from agent_history.archive import collect as collect_module

    _write(env, ".claude/projects/p/a-slow.jsonl", b"slow\n", mtime=1_790_000_000)
    for index in range(30):
        _write(env, f".claude/projects/p/s{index:02}.jsonl", b"x\n", mtime=1_790_000_000)
    others_done = threading.Event()
    finished = []
    real = collect_module.compress_file

    def gated(src, *args, **kwargs):
        result = real(src, *args, **kwargs)
        if Path(src).name == "a-slow.jsonl":
            assert others_done.wait(timeout=10), "other files waited for the slow one"
        else:
            finished.append(src)
            if len(finished) == 30:
                others_done.set()
        return result

    monkeypatch.setattr(collect_module, "compress_file", gated)

    summary = _collect(env, config=_config(env, workers=2))

    assert summary.written == 31
    paths = [entry["path"] for entry in summary.entries]
    assert paths == sorted(paths)


def test_large_files_use_multithreaded_compression(env, monkeypatch):
    from agent_history.archive import collect as collect_module

    _write(env, SESSION, b"y" * 2048, mtime=1_790_000_000)
    monkeypatch.setattr(collect_module, "LARGE_FILE_BYTES", 1024)
    seen = []
    real = collect_module.compress_file

    def spy(*args, **kwargs):
        seen.append(kwargs.get("threads", 0))
        return real(*args, **kwargs)

    monkeypatch.setattr(collect_module, "compress_file", spy)

    _collect(env, config=_config(env, workers=3))

    assert seen == [3]
    assert _archived(env, SESSION) == b"y" * 2048


def test_only_one_large_file_uses_extra_threads_at_a_time(env, monkeypatch):
    import threading
    import time as time_module

    from agent_history.archive import collect as collect_module

    for index in range(4):
        _write(env, f".claude/projects/p/big{index}.jsonl", b"b" * 4096, mtime=1_790_000_000)
    monkeypatch.setattr(collect_module, "LARGE_FILE_BYTES", 1024)
    active = []
    peak = [0]
    lock = threading.Lock()
    real = collect_module.compress_file

    def tracking(*args, **kwargs):
        if kwargs.get("threads"):
            with lock:
                active.append(1)
                peak[0] = max(peak[0], len(active))
            time_module.sleep(0.05)
            with lock:
                active.pop()
        return real(*args, **kwargs)

    monkeypatch.setattr(collect_module, "compress_file", tracking)

    summary = _collect(env, config=_config(env, workers=4))

    assert summary.written == 4
    assert peak[0] == 1
