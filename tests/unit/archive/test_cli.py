"""Tests for the `cagelens archive` commands."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from agent_history.cli.orchestrator import main

SESSION = ".claude/projects/-home-alex-shop/a1.jsonl"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    session = home / SESSION
    session.parent.mkdir(parents=True)
    session.write_text('{"type":"user"}\n', encoding="utf-8")
    os.utime(session, (1_700_000_000, 1_700_000_000))
    config = tmp_path / "archive.json"
    config.write_text(
        json.dumps(
            {
                "archive": {"destination": str(tmp_path / "archive"), "compression_level": 3},
                "sources": [
                    {"name": "laptop", "kind": "live", "platform": "linux", "home": str(home)}
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / "cagelens"))
    return {"config": str(config), "tmp": tmp_path, "home": home}


def test_collect_verify_and_catalog(setup, capsys):
    config = setup["config"]

    assert main(["archive", "collect", "--config", config]) == 0
    assert "laptop: 1 written" in capsys.readouterr().out
    assert main(["archive", "verify", "--config", config, "--all"]) == 0
    assert "laptop: checked 1, ok" in capsys.readouterr().out
    assert main(["archive", "catalog", "sync", "--config", config]) == 0
    capsys.readouterr()
    assert main(["archive", "catalog", "status", "--config", config, "--json"]) == 0
    (status,) = json.loads(capsys.readouterr().out)
    assert status["source"] == "laptop"
    assert status["files"] == 1
    assert (setup["tmp"] / "cagelens" / "archive-catalog.db").exists()


def _rename_configured_source(setup, name):
    config = json.loads(open(setup["config"], encoding="utf-8").read())
    config["sources"][0]["name"] = name
    with open(setup["config"], "w", encoding="utf-8") as handle:
        json.dump(config, handle)


def _catalogued_sources(config, capsys):
    capsys.readouterr()
    assert main(["archive", "catalog", "status", "--config", config, "--json"]) == 0
    return [row["source"] for row in json.loads(capsys.readouterr().out)]


def test_catalog_sync_includes_archive_sources_missing_from_the_config(setup, capsys):
    # The archive also holds a source this machine's configuration does not name, such
    # as another machine's or a retired one's.
    config = setup["config"]
    assert main(["archive", "collect", "--config", config]) == 0
    _rename_configured_source(setup, "desktop")

    assert main(["archive", "catalog", "sync", "--config", config]) == 0

    assert _catalogued_sources(config, capsys) == ["laptop"]


def test_catalog_source_may_name_an_archive_source_missing_from_the_config(setup, capsys):
    config = setup["config"]
    assert main(["archive", "collect", "--config", config]) == 0
    _rename_configured_source(setup, "desktop")

    assert main(["archive", "catalog", "rebuild", "--config", config, "--source", "laptop"]) == 0

    assert _catalogued_sources(config, capsys) == ["laptop"]


def test_catalog_source_that_is_not_in_the_archive_is_an_error(setup, capsys):
    config = setup["config"]
    assert main(["archive", "collect", "--config", config]) == 0
    capsys.readouterr()

    assert main(["archive", "catalog", "sync", "--config", config, "--source", "nope"]) == 1
    assert "nope" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["sync", "rebuild"])
def test_catalog_with_a_destination_needs_no_config_file(setup, capsys, action):
    assert main(["archive", "collect", "--config", setup["config"]]) == 0
    capsys.readouterr()
    destination = str(setup["tmp"] / "archive")

    # No --config, and the default configuration file does not exist.
    code = main(["archive", "catalog", action, "--destination", destination])

    assert code == 0, capsys.readouterr().err
    assert _catalogued_sources(setup["config"], capsys) == ["laptop"]


def test_verify_checks_archive_sources_missing_from_the_config(setup, capsys):
    config = setup["config"]
    assert main(["archive", "collect", "--config", config]) == 0
    _rename_configured_source(setup, "desktop")
    capsys.readouterr()

    assert main(["archive", "verify", "--config", config]) == 0

    assert capsys.readouterr().out.splitlines() == ["laptop: checked 1, ok"]


def test_verify_with_a_destination_needs_no_config_file(setup, capsys):
    assert main(["archive", "collect", "--config", setup["config"]]) == 0
    capsys.readouterr()

    # No --config, and the default configuration file does not exist.
    code = main(["archive", "verify", "--destination", str(setup["tmp"] / "archive")])

    assert code == 0, capsys.readouterr().err
    assert "laptop: checked 1, ok" in capsys.readouterr().out


def test_verify_of_a_source_that_is_not_in_the_archive_is_an_error(setup, capsys):
    config = setup["config"]
    assert main(["archive", "collect", "--config", config]) == 0
    capsys.readouterr()

    assert main(["archive", "verify", "--config", config, "--source", "nope"]) == 1
    assert "nope" in capsys.readouterr().err


def test_catalog_status_shows_only_the_named_sources(setup, capsys):
    config = _two_sources(setup)
    assert main(["archive", "collect", "--config", config]) == 0
    assert main(["archive", "catalog", "sync", "--config", config]) == 0
    capsys.readouterr()

    assert main(["archive", "catalog", "status", "--source", "other", "--json"]) == 0

    assert [row["source"] for row in json.loads(capsys.readouterr().out)] == ["other"]


def test_dry_run_lists_actions_without_writing(setup, capsys):
    assert main(["archive", "collect", "--config", setup["config"], "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert f"added {SESSION}" in out
    assert not (setup["tmp"] / "archive").exists()


JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlc2lnbmF0dXJl"


def _logs_db(setup):
    import sqlite3

    path = setup["home"] / ".codex" / "logs_2.sqlite"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY, message TEXT)")
        conn.executemany(
            "INSERT INTO logs VALUES (?, ?)", [(1, "started"), (2, f"token {JWT} sent")]
        )
    conn.close()
    os.utime(path, (1_700_000_000, 1_700_000_000))


def test_dry_run_shows_the_rows_and_jwts_of_a_log_export(setup, capsys):
    _logs_db(setup)

    assert main(["archive", "collect", "--config", setup["config"], "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "rows .codex/logs_2.sqlite (2 rows, 1 JWT redacted)" in out


@pytest.mark.parametrize("dry_run", [True, False])
def test_json_output_lists_each_sources_entries(setup, capsys, dry_run):
    _logs_db(setup)
    args = ["archive", "collect", "--config", setup["config"], "--json"]

    assert main(args + (["--dry-run"] if dry_run else [])) == 0

    (result,) = json.loads(capsys.readouterr().out)
    entries = {entry["path"]: entry for entry in result["entries"]}
    assert entries[SESSION]["action"] == "added"
    assert (
        entries[".codex/logs_2.sqlite"]["rows"],
        entries[".codex/logs_2.sqlite"]["redacted"],
    ) == (
        2,
        {"jwt": 1},
    )


def _two_sources(setup) -> str:
    other = setup["tmp"] / "other-home"
    session = other / SESSION
    session.parent.mkdir(parents=True)
    session.write_text('{"type":"user"}\n', encoding="utf-8")
    path = setup["tmp"] / "two.json"
    config = json.loads((setup["tmp"] / "archive.json").read_text(encoding="utf-8"))
    config["sources"].append(
        {"name": "other", "kind": "live", "platform": "linux", "home": str(other)}
    )
    path.write_text(json.dumps(config), encoding="utf-8")
    return str(path)


def test_a_locked_source_is_skipped_and_the_rest_are_collected(setup, capsys):
    from agent_history.archive.state import source_lock

    config = _two_sources(setup)
    state_dir = setup["tmp"] / "cagelens" / "archive-state"
    destination = str(setup["tmp"] / "archive")

    with source_lock(state_dir, destination, "laptop"):
        code = main(["archive", "collect", "--config", config])

    out = capsys.readouterr().out
    assert code == 0
    assert "laptop: skipped (locked)" in out
    assert "other: 1 written" in out


def _lock_at_destination(setup, source, age=timedelta(minutes=5)):
    """A lock of another machine's run that started ``age`` ago."""
    lock = setup["tmp"] / "archive" / "sources" / source / "LOCK"
    lock.mkdir(parents=True)
    started_at = (datetime.now(timezone.utc) - age).isoformat(timespec="seconds")
    owner = {"host": "other-laptop", "pid": 4242, "started_at": started_at}
    (lock / "owner.json").write_text(json.dumps(owner), encoding="utf-8")
    return lock


def test_a_lock_left_for_over_a_day_fails_its_source(setup, capsys):
    config = _two_sources(setup)
    assert main(["archive", "collect", "--config", config]) == 0
    lock = _lock_at_destination(setup, "laptop", age=timedelta(hours=25))
    capsys.readouterr()

    code = main(["archive", "collect", "--config", config])

    captured = capsys.readouterr()
    assert code == 1
    assert "skipped" not in captured.out
    assert "other-laptop" in captured.err
    assert "--break-lock" in captured.err
    assert lock.is_dir()


def test_a_source_locked_at_the_destination_is_skipped_with_its_owner(setup, capsys):
    config = _two_sources(setup)
    assert main(["archive", "collect", "--config", config]) == 0
    lock = _lock_at_destination(setup, "laptop")
    capsys.readouterr()

    code = main(["archive", "collect", "--config", config])

    captured = capsys.readouterr()
    assert code == 0
    assert "laptop: skipped (locked)" in captured.out
    assert "other-laptop" in captured.err
    assert lock.is_dir()

    assert main(["archive", "collect", "--config", config, "--break-lock"]) == 0
    assert "laptop: 0 written" in capsys.readouterr().out
    assert not lock.exists()


def test_a_lock_without_a_readable_owner_fails_its_source(setup, capsys, monkeypatch):
    from agent_history.archive import state

    monkeypatch.setattr(state, "LOCK_SETTLE_SECONDS", 0)
    config = _two_sources(setup)
    assert main(["archive", "collect", "--config", config]) == 0
    lock = setup["tmp"] / "archive" / "sources" / "laptop" / "LOCK"
    lock.mkdir()
    (lock / "owner.json").write_bytes(b"")
    capsys.readouterr()

    code = main(["archive", "collect", "--config", config])

    captured = capsys.readouterr()
    assert code == 1
    assert "skipped" not in captured.out
    assert "laptop:" in captured.err
    assert "--break-lock" in captured.err
    assert main(["archive", "collect", "--config", config, "--break-lock"]) == 0
    assert not lock.exists()


def test_a_failing_source_does_not_stop_the_others(setup, capsys, monkeypatch):
    from agent_history.archive import collect as collect_module
    from agent_history.archive.errors import ArchiveError

    config = _two_sources(setup)
    real = collect_module.collect_source

    def failing_for_laptop(config, name, **kwargs):
        if name == "laptop":
            raise ArchiveError("Copying files to nas failed: connection closed")
        return real(config, name, **kwargs)

    monkeypatch.setattr(collect_module, "collect_source", failing_for_laptop)

    code = main(["archive", "collect", "--config", config, "--json"])

    captured = capsys.readouterr()
    assert code == 1
    assert "laptop: Copying files to nas failed" in captured.err
    results = {item["source"]: item for item in json.loads(captured.out)}
    assert results["laptop"]["error"] == "Copying files to nas failed: connection closed"
    assert results["other"]["written"] == 1


def test_a_damaged_manifest_fails_its_source_and_the_rest_are_collected(setup, capsys):
    config = _two_sources(setup)
    assert main(["archive", "collect", "--config", config]) == 0
    manifests = setup["tmp"] / "archive" / "sources" / "laptop" / "manifests"
    damaged = manifests / "20991231T000000Z-laptop-ffff.jsonl.zst"
    damaged.write_bytes(b"\x28\xb5\x2f\xfd not a zstd frame")
    other = setup["tmp"] / "other-home" / SESSION
    other.write_text('{"type":"user"}\n{"type":"assistant"}\n', encoding="utf-8")
    capsys.readouterr()

    code = main(["archive", "collect", "--config", config])

    captured = capsys.readouterr()
    assert code == 1
    assert "laptop:" in captured.err
    assert "20991231T000000Z-laptop-ffff.jsonl.zst" in captured.err
    assert "other: 1 written" in captured.out


def test_an_unexpected_failure_does_not_stop_the_other_sources(setup, capsys, monkeypatch):
    from agent_history.archive import collect as collect_module

    config = _two_sources(setup)
    real = collect_module.collect_source

    def failing_for_laptop(config, name, **kwargs):
        if name == "laptop":
            raise RuntimeError("something unforeseen")
        return real(config, name, **kwargs)

    monkeypatch.setattr(collect_module, "collect_source", failing_for_laptop)

    code = main(["archive", "collect", "--config", config, "--json"])

    captured = capsys.readouterr()
    assert code == 1
    assert "laptop: RuntimeError: something unforeseen" in captured.err
    results = {item["source"]: item for item in json.loads(captured.out)}
    assert results["laptop"]["error"] == "RuntimeError: something unforeseen"
    assert results["other"]["written"] == 1


def test_collect_to_another_destination_keeps_its_own_state(setup, capsys):
    """--destination must not use, or change, the configured destination's state."""
    config = setup["config"]
    other = setup["tmp"] / "other-archive"
    assert main(["archive", "collect", "--config", config]) == 0
    capsys.readouterr()

    assert main(["archive", "collect", "--config", config, "--destination", str(other)]) == 0
    assert "laptop: 1 written" in capsys.readouterr().out
    session = setup["home"] / SESSION
    session.write_text('{"type":"user"}\n{"type":"assistant"}\n', encoding="utf-8")
    assert main(["archive", "collect", "--config", config]) == 0
    assert "laptop: 1 written" in capsys.readouterr().out

    for destination in (setup["tmp"] / "archive", other):
        assert (
            main(["archive", "verify", "--config", config, "--destination", str(destination)]) == 0
        )
    manifests = setup["tmp"] / "archive" / "sources" / "laptop" / "manifests"
    assert len(list(manifests.iterdir())) == 2
    assert len(list((other / "sources" / "laptop" / "manifests").iterdir())) == 1


def test_unknown_source_is_an_error(setup, capsys):
    assert main(["archive", "collect", "--config", setup["config"], "--source", "nope"]) == 1
    assert "Unknown source: nope" in capsys.readouterr().err


def test_missing_config_is_an_error(tmp_path, capsys):
    assert main(["archive", "collect", "--config", str(tmp_path / "none.json")]) == 1
    assert "not found" in capsys.readouterr().err


def test_verify_problems_give_exit_code_2(setup, capsys):
    config = setup["config"]
    main(["archive", "collect", "--config", config])
    archived = setup["tmp"] / "archive" / "sources" / "laptop" / "files" / f"{SESSION}.zst"
    archived.write_bytes(b"not zstd")
    capsys.readouterr()

    assert main(["archive", "verify", "--config", config]) == 2
    assert f"mismatched: {SESSION}" in capsys.readouterr().out


def test_verify_reports_a_damaged_manifest_for_its_source_and_checks_the_rest(setup, capsys):
    config = _two_sources(setup)
    assert main(["archive", "collect", "--config", config]) == 0
    manifests = setup["tmp"] / "archive" / "sources" / "laptop" / "manifests"
    damaged = manifests / "20991231T000000Z-laptop-ffff.jsonl.zst"
    damaged.write_bytes(b"\x28\xb5\x2f\xfd not a zstd frame")
    capsys.readouterr()

    assert main(["archive", "verify", "--config", config]) == 2
    out = capsys.readouterr().out
    assert "laptop: error: " in out
    assert damaged.name in out
    assert "other: checked 1, ok" in out

    assert main(["archive", "verify", "--config", config, "--json"]) == 2
    results = {item["source"]: item for item in json.loads(capsys.readouterr().out)}
    assert results["laptop"]["ok"] is False
    assert damaged.name in results["laptop"]["error"]
    assert results["other"]["ok"] is True
    assert results["other"]["checked"] == 1


def test_verify_prints_files_that_could_not_be_read(setup, capsys, monkeypatch):
    from agent_history.archive import verify

    config = setup["config"]
    main(["archive", "collect", "--config", config])
    capsys.readouterr()
    monkeypatch.setattr(
        verify,
        "verify_source",
        lambda *args, **kwargs: verify.VerifyReport(errors=[f"{SESSION}: connection dropped"]),
    )

    assert main(["archive", "verify", "--config", config]) == 2
    assert f"errors: {SESSION}: connection dropped" in capsys.readouterr().out


def test_verify_prints_pending_runs(setup, capsys, monkeypatch):
    from agent_history.archive import verify

    config = setup["config"]
    main(["archive", "collect", "--config", config])
    capsys.readouterr()
    monkeypatch.setattr(
        verify,
        "verify_source",
        lambda *args, **kwargs: verify.VerifyReport(pending=["20261002T061500Z-laptop-3f2a"]),
    )

    assert main(["archive", "verify", "--config", config]) == 2
    assert "pending: 20261002T061500Z-laptop-3f2a" in capsys.readouterr().out


def test_archive_is_listed_in_main_help(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])

    assert "archive" in capsys.readouterr().out
