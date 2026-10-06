"""Paths that differ only in letter case, archived to a destination that ignores case.

NTFS, SMB shares and the default APFS volumes treat ``Plan.md`` and ``plan.md`` as one
name. The tests model such a destination on any platform with a local destination that
matches each name to an existing entry of its folder whose name folds equal.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pytest
import zstandard

from agent_history.archive.collect import collect_source
from agent_history.archive.config import parse_config
from agent_history.archive.layouts import archive_file_path
from agent_history.archive.manifest import read_manifests
from agent_history.archive.transport import LocalDestination, _check_rel
from agent_history.archive.verify import verify_source

from .test_collect import T0

OLD = ".claude/projects/-home-alex-Shop/a1.jsonl"
NEW = ".claude/projects/-home-alex-shop/a1.jsonl"


class FoldingDestination(LocalDestination):
    """A local destination that ignores letter case, as NTFS, SMB and default APFS do.

    Each name is matched to an existing entry of its folder whose name folds equal, so an
    existing name keeps its case, and a new name is created as given.
    """

    def _path(self, rel: str) -> Path:
        path = self.root
        for part in _check_rel(rel).split("/"):
            path = path / _existing_name(path, part)
        return path


def _existing_name(folder: Path, name: str) -> str:
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.name.casefold() == name.casefold():
                    return entry.name
    except (FileNotFoundError, NotADirectoryError):
        pass
    return name


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {"home": home, "dest": tmp_path / "archive", "state": tmp_path / "state"}


def _config(env):
    return parse_config(
        {
            "archive": {"destination": str(env["dest"]), "compression_level": 3},
            "sources": [
                {"name": "src", "kind": "live", "platform": "linux", "home": str(env["home"])}
            ],
        }
    )


def _write(env, rel: str, data: bytes, mtime: float) -> Path:
    path = env["home"] / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))
    return path


def _collect(env, destination, now=T0, **kwargs):
    return collect_source(
        _config(env), "src", state_dir=env["state"], now=now, destination=destination, **kwargs
    )


def _entries(destination, run_id: str) -> list[dict]:
    for run, entries in read_manifests(destination, "src"):
        if run["run_id"] == run_id:
            return entries
    raise AssertionError(f"no manifest for {run_id}")


def _actions(entries: list[dict]) -> list[tuple[str, str]]:
    return sorted((entry["path"], entry.get("action") or entry["type"]) for entry in entries)


def _content(destination, rel: str) -> bytes:
    with destination.open_binary(rel) as handle:
        return zstandard.ZstdDecompressor().decompress(handle.read())


def _archived(destination, path: str) -> bytes:
    return _content(destination, archive_file_path("src", path))


def _version(destination, entries: list[dict], path: str) -> bytes:
    (entry,) = [e for e in entries if e["path"] == path and e.get("action") == "displaced"]
    return _content(destination, f"sources/src/{entry['version_path']}")


def _assert_verified(destination):
    report = verify_source(destination, "src")
    assert report.ok, vars(report)


def _rename(env, old: str, new: str) -> None:
    """Rename the first folder or file whose name differs, as a user would."""
    old_parts, new_parts = old.split("/"), new.split("/")
    depth = next(i for i, (a, b) in enumerate(zip(old_parts, new_parts)) if a != b)
    folder = env["home"].joinpath(*old_parts[:depth])
    (folder / old_parts[depth]).rename(folder / new_parts[depth])


@pytest.fixture
def case_sensitive_home(env):
    """Skip where the temporary folder ignores letter case: it cannot hold both names."""
    probe = env["home"] / "Probe"
    probe.touch()
    try:
        if (env["home"] / "probe").exists():
            pytest.skip("the temporary folder ignores letter case")
    finally:
        probe.unlink()


@pytest.mark.parametrize(
    ("old", "new"),
    [(OLD, NEW), (".claude/projects/p/Plan.jsonl", ".claude/projects/p/plan.jsonl")],
)
def test_a_case_only_rename_keeps_the_old_copy_as_a_version(env, old, new):
    destination = FoldingDestination(env["dest"])
    _write(env, old, b"first\n", mtime=1_790_000_000)
    _collect(env, destination)
    _rename(env, old, new)
    _write(env, new, b"second, rewritten\n", mtime=1_790_000_100)

    dry = _collect(env, destination, now=T0 + timedelta(hours=1), dry_run=True)
    second = _collect(env, destination, now=T0 + timedelta(hours=1))

    entries = _entries(destination, second.run_id)
    assert _actions(dry.entries) == _actions(entries)
    assert _actions(entries) == [(old, "displaced"), (old, "gone"), (new, "added")]
    (displaced,) = [e for e in entries if e.get("action") == "displaced"]
    assert displaced["displaced_by"] == new
    assert displaced["previous_size"] == len(b"first\n")
    assert second.errors == 0
    assert _version(destination, entries, old) == b"first\n"
    assert _archived(destination, new) == b"second, rewritten\n"
    _assert_verified(destination)


def test_a_folder_renamed_back_to_its_old_case_is_archived_again(env):
    destination = FoldingDestination(env["dest"])
    _write(env, OLD, b"first\n", mtime=1_790_000_000)
    _collect(env, destination)
    _rename(env, OLD, NEW)
    _write(env, NEW, b"second\n", mtime=1_790_000_100)
    _collect(env, destination, now=T0 + timedelta(hours=1))
    projects = env["home"] / ".claude" / "projects"
    (projects / "-home-alex-shop").rename(projects / "-home-alex-Shop")
    _write(env, OLD, b"first\n", mtime=1_790_000_000)  # back as it was at the first run

    third = _collect(env, destination, now=T0 + timedelta(hours=2))

    entries = _entries(destination, third.run_id)
    assert _actions(entries) == [(OLD, "added"), (NEW, "displaced"), (NEW, "gone")]
    assert _version(destination, entries, NEW) == b"second\n"
    assert _archived(destination, OLD) == b"first\n"
    _assert_verified(destination)


def test_two_live_paths_that_differ_only_in_case_never_overwrite_each_other(
    env, case_sensitive_home
):
    destination = FoldingDestination(env["dest"])
    upper = ".claude/projects/P/a.jsonl"
    lower = ".claude/projects/p/a.jsonl"
    _write(env, upper, b"upper\n", mtime=1_790_000_000)
    _write(env, lower, b"lower, longer\n", mtime=1_790_000_000)

    runs = [_collect(env, destination, now=T0 + timedelta(hours=hour)) for hour in (0, 1)]

    for run in runs:
        assert run.errors == 1
        (error,) = [e for e in run.entries if e["type"] == "error"]
        assert error["path"] == lower
        assert upper in error["message"]
    assert _archived(destination, upper) == b"upper\n"
    _assert_verified(destination)


def test_a_new_path_that_differs_in_case_from_a_live_archived_one_is_not_archived(
    env, case_sensitive_home
):
    """The new path sorts first, so the walk reaches it before the archived one."""
    destination = FoldingDestination(env["dest"])
    lower = ".claude/projects/p/a.jsonl"
    upper = ".claude/projects/P/a.jsonl"
    _write(env, lower, b"lower\n", mtime=1_790_000_000)
    _collect(env, destination)
    _write(env, upper, b"upper, longer\n", mtime=1_790_000_100)

    second = _collect(env, destination, now=T0 + timedelta(hours=1))

    assert [(e["type"], e["path"]) for e in second.entries] == [("error", upper)]
    assert _archived(destination, lower) == b"lower\n"
    _assert_verified(destination)


def test_a_displaced_copy_stays_when_the_new_file_cannot_be_archived(env, monkeypatch):
    from agent_history.archive import collect as collect_module

    destination = FoldingDestination(env["dest"])
    _write(env, OLD, b"first\n", mtime=1_790_000_000)
    _collect(env, destination)
    _rename(env, OLD, NEW)
    _write(env, NEW, b"second, rewritten\n", mtime=1_790_000_100)
    real = collect_module.compress_file

    def failing(src, *args, **kwargs):
        if Path(src).parent.name == "-home-alex-shop":
            raise OSError("device busy")
        return real(src, *args, **kwargs)

    monkeypatch.setattr(collect_module, "compress_file", failing)
    second = _collect(env, destination, now=T0 + timedelta(hours=1))

    assert _actions(_entries(destination, second.run_id)) == [(OLD, "gone"), (NEW, "error")]
    assert _archived(destination, OLD) == b"first\n"
    _assert_verified(destination)


def test_a_rename_stopped_while_placing_is_finished_by_the_next_run(env):
    class Stops(FoldingDestination):
        def place(self, keeps, puts):
            super().place(keeps, [])
            raise OSError("connection dropped")

    destination = FoldingDestination(env["dest"])
    _write(env, OLD, b"first\n", mtime=1_790_000_000)
    _collect(env, destination)
    _rename(env, OLD, NEW)
    _write(env, NEW, b"second, rewritten\n", mtime=1_790_000_100)
    with pytest.raises(OSError):
        _collect(env, Stops(env["dest"]), now=T0 + timedelta(hours=1))

    third = _collect(env, destination, now=T0 + timedelta(hours=2))

    assert third.written == 0  # the interrupted run was finished, not repeated
    assert _archived(destination, NEW) == b"second, rewritten\n"
    run_ids = [run["run_id"] for run, _entries in read_manifests(destination, "src")]
    assert _version(destination, _entries(destination, run_ids[1]), OLD) == b"first\n"
    _assert_verified(destination)


def test_a_case_sensitive_destination_keeps_both_names_as_before(env, case_sensitive_home):
    destination = LocalDestination(env["dest"])
    _write(env, OLD, b"first\n", mtime=1_790_000_000)
    _collect(env, destination)
    _rename(env, OLD, NEW)
    _write(env, NEW, b"second\n", mtime=1_790_000_100)
    _write(env, ".claude/projects/P/a.jsonl", b"upper\n", mtime=1_790_000_100)
    _write(env, ".claude/projects/p/a.jsonl", b"lower\n", mtime=1_790_000_100)

    second = _collect(env, destination, now=T0 + timedelta(hours=1))

    assert _actions(_entries(destination, second.run_id)) == [
        (OLD, "gone"),
        (NEW, "added"),
        (".claude/projects/P/a.jsonl", "added"),
        (".claude/projects/p/a.jsonl", "added"),
    ]
    assert _archived(destination, OLD) == b"first\n"
    assert _archived(destination, NEW) == b"second\n"
    assert not (env["dest"] / "sources" / "src" / "versions").exists()
    _assert_verified(destination)
