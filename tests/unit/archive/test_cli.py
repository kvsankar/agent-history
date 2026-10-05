"""Tests for the `cagelens archive` commands."""

from __future__ import annotations

import json
import os

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


def test_dry_run_lists_actions_without_writing(setup, capsys):
    assert main(["archive", "collect", "--config", setup["config"], "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert f"added {SESSION}" in out
    assert not (setup["tmp"] / "archive").exists()


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


def test_archive_is_listed_in_main_help(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])

    assert "archive" in capsys.readouterr().out
