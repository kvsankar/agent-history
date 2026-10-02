"""Tests for archive configuration loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_history.archive.config import ArchiveConfigError, load_config, parse_config


def _config(**overrides):
    data = {
        "archive": {"destination": "/srv/archive"},
        "sources": [{"name": "laptop", "kind": "live", "platform": "linux", "home": "/home/alex"}],
    }
    data.update(overrides)
    return data


def test_defaults_apply():
    config = parse_config(_config())

    assert config.destination == "/srv/archive"
    assert config.compression_level == 19
    assert config.min_interval_hours == 0
    assert config.health_url is None
    (source,) = config.sources
    assert source.name == "laptop"
    assert source.kind == "live"
    assert source.platform == "linux"
    assert source.parts[0].home == Path("/home/alex")


def test_home_expands_user(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    data = _config(sources=[{"name": "laptop", "kind": "live", "platform": "linux", "home": "~"}])

    config = parse_config(data)

    assert config.sources[0].parts[0].home == tmp_path


def test_entries_with_one_name_merge_into_one_source():
    data = _config(
        sources=[
            {"name": "laptop", "kind": "live", "platform": "linux", "home": "/home/alex"},
            {
                "name": "laptop",
                "kind": "live",
                "platform": "linux",
                "roots": {"claude": "/old/raw/laptop/claude"},
            },
        ]
    )

    config = parse_config(data)

    (source,) = config.sources
    assert len(source.parts) == 2
    assert source.parts[1].roots == {"claude": Path("/old/raw/laptop/claude")}


def test_merged_entries_must_agree_on_kind():
    data = _config(
        sources=[
            {"name": "laptop", "kind": "live", "platform": "linux", "home": "/a"},
            {"name": "laptop", "kind": "imported", "platform": "linux", "home": "/b"},
        ]
    )

    with pytest.raises(ArchiveConfigError, match="laptop"):
        parse_config(data)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ({"name": "x", "kind": "copied", "platform": "linux", "home": "/a"}, "kind"),
        ({"name": "x", "kind": "live", "platform": "beos", "home": "/a"}, "platform"),
        ({"name": "x", "kind": "live", "platform": "linux"}, "home"),
        ({"name": "x/y", "kind": "live", "platform": "linux", "home": "/a"}, "name"),
        (
            {"name": "x", "kind": "live", "platform": "linux", "home": "/a", "agents": ["cursor"]},
            "cursor",
        ),
        (
            {"name": "x", "kind": "live", "platform": "linux", "roots": {"cursor": "/a"}},
            "cursor",
        ),
    ],
)
def test_invalid_sources_are_rejected(source, message):
    with pytest.raises(ArchiveConfigError, match=message):
        parse_config(_config(sources=[source]))


def test_destination_is_required():
    with pytest.raises(ArchiveConfigError, match="destination"):
        parse_config(_config(archive={}))


@pytest.mark.parametrize("level", [0, 23, "high"])
def test_compression_level_must_be_in_range(level):
    with pytest.raises(ArchiveConfigError, match="compression_level"):
        parse_config(_config(archive={"destination": "/a", "compression_level": level}))


def test_load_config_reads_json_file(tmp_path):
    path = tmp_path / "archive.json"
    path.write_text(json.dumps(_config()), encoding="utf-8")

    assert load_config(path).sources[0].name == "laptop"


def test_load_config_reports_missing_file(tmp_path):
    with pytest.raises(ArchiveConfigError, match="not found"):
        load_config(tmp_path / "missing.json")


def test_workers_default_and_validation():
    assert 1 <= parse_config(_config()).workers <= 4
    assert parse_config(_config(archive={"destination": "/a", "workers": 3})).workers == 3
    with pytest.raises(ArchiveConfigError, match="workers"):
        parse_config(_config(archive={"destination": "/a", "workers": 0}))


def test_unknown_settings_are_rejected():
    with pytest.raises(ArchiveConfigError, match="worker"):
        parse_config(_config(archive={"destination": "/a", "worker": 3}))
