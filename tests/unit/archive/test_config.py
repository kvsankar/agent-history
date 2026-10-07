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
            {
                "name": "laptop",
                "kind": "live",
                "platform": "linux",
                "home": "/home/alex",
                "agents": ["codex", "gemini"],
            },
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


@pytest.mark.parametrize("value", ["notes.md", ".claude/**", ["notes.md", 5], {"a": 1}, 5])
def test_exclude_must_be_a_list_of_patterns(value):
    source = {"name": "x", "kind": "live", "platform": "linux", "home": "/a", "exclude": value}

    with pytest.raises(ArchiveConfigError, match="Source x: exclude must be a list of"):
        parse_config(_config(sources=[source]))


def test_exclude_may_be_empty_or_absent():
    source = {"name": "x", "kind": "live", "platform": "linux", "home": "/a", "exclude": []}

    (part,) = parse_config(_config(sources=[source])).sources[0].parts

    assert part.exclude == ()


def test_excludes_may_name_agent_folders():
    source = {"name": "x", "kind": "live", "platform": "linux", "home": "/home/alex"}
    source["exclude"] = [".claude/projects/scratch/**"]

    (parsed,) = parse_config(_config(sources=[source])).sources

    assert parsed.parts[0].exclude == (".claude/projects/scratch/**",)


def test_destination_is_required():
    with pytest.raises(ArchiveConfigError, match="destination"):
        parse_config(_config(archive={}))


@pytest.mark.parametrize("level", [0, 23, "high"])
def test_compression_level_must_be_in_range(level):
    with pytest.raises(ArchiveConfigError, match="compression_level"):
        parse_config(_config(archive={"destination": "/a", "compression_level": level}))


@pytest.mark.parametrize(
    "url",
    ["hc-ping.example/abc", "ftp://hc-ping.example/abc", "https://", "http://[::1/ping", 5],
)
def test_health_url_must_be_an_http_url(url):
    with pytest.raises(ArchiveConfigError, match="health_url"):
        parse_config(_config(archive={"destination": "/a", "health_url": url}))


@pytest.mark.parametrize("url", ["https://hc-ping.example/abc", "http://nas:8000/ping/1"])
def test_health_url_accepts_http_and_https(url):
    assert parse_config(_config(archive={"destination": "/a", "health_url": url})).health_url == url


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


def test_unknown_top_level_settings_are_rejected():
    data = _config()
    data["source"] = data.pop("sources")  # misspelt: would load with no sources

    with pytest.raises(ArchiveConfigError, match=r"Unknown setting in the configuration: source$"):
        parse_config(data)


@pytest.mark.parametrize(
    "second",
    [
        {"roots": {"claude": "/old/raw/laptop/claude"}},
        {"home": "/mnt/old-laptop/home/alex", "agents": ["claude", "pi"]},
        {"home": "/home/alex", "agents": ["claude"]},
    ],
)
def test_entries_of_one_source_may_not_cover_the_same_agent(second):
    first = {"name": "laptop", "kind": "live", "platform": "linux", "home": "/home/alex"}
    data = _config(
        sources=[first, {"name": "laptop", "kind": "live", "platform": "linux", **second}]
    )

    with pytest.raises(ArchiveConfigError, match="claude") as raised:
        parse_config(data)

    assert "entries 1 and 2" in str(raised.value)
    assert "own source name" in str(raised.value)


def test_a_roots_override_outside_the_agents_filter_does_not_count():
    first = {"name": "laptop", "kind": "live", "platform": "linux", "home": "/home/alex"}
    second = {"name": "laptop", "kind": "live", "platform": "linux", "home": "/data"}
    second.update(agents=["cagelens"], roots={"claude": "/old/claude"})
    data = _config(sources=[{**first, "agents": ["claude", "codex"]}, second])

    (source,) = parse_config(data).sources

    assert len(source.parts) == 2


@pytest.mark.parametrize("value", [["notes/**"], [], "notes/**"])
def test_include_is_refused(value):
    source = {"name": "x", "kind": "live", "platform": "linux", "home": "/a", "include": value}

    with pytest.raises(ArchiveConfigError) as raised:
        parse_config(_config(sources=[source]))

    message = str(raised.value)
    assert message.startswith("Source 'x': include is not supported")
    assert "only the files that the agent layouts select" in message


def test_an_empty_agents_list_is_refused():
    first = {"name": "laptop", "kind": "live", "platform": "linux", "home": "/home/alex"}
    second = {"name": "laptop", "kind": "live", "platform": "linux", "home": "/data"}
    second["agents"] = []

    with pytest.raises(ArchiveConfigError) as raised:
        parse_config(_config(sources=[first, second]))

    message = str(raised.value)
    assert message.startswith("Source laptop: agents is empty")
    assert "leave agents out to read every agent" in message
