"""Projects from the legacy aliases.json are merged once, not on every load."""

import json

from agent_history.storage.config import load_config, save_config


def _setup(tmp_path, monkeypatch, config_projects):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("AGENT_HISTORY_CONFIG_DIR", raising=False)
    (config_dir / "aliases.json").write_text(
        json.dumps(
            {
                "version": 1,
                "aliases": {
                    "kept": {"local": ["/home/user/kept"]},
                    "removed": {"local": ["/home/user/removed"]},
                },
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "config.json").write_text(
        json.dumps({"version": 2, "homes": [], "projects": config_projects}), encoding="utf-8"
    )


def test_legacy_projects_missing_from_config_are_merged_on_first_load(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, {"kept": {"local": ["/home/user/kept"]}})

    assert set(load_config()["projects"]) == {"kept", "removed"}


def test_a_project_removed_after_the_merge_stays_removed(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, {"kept": {"local": ["/home/user/kept"]}})
    config = load_config()
    assert save_config(config)

    config = load_config()
    del config["projects"]["removed"]
    assert save_config(config)

    assert set(load_config()["projects"]) == {"kept"}


def test_a_merged_project_renamed_in_config_does_not_return(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, {})
    config = load_config()
    config["projects"]["renamed"] = config["projects"].pop("removed")
    assert save_config(config)

    assert set(load_config()["projects"]) == {"kept", "renamed"}
