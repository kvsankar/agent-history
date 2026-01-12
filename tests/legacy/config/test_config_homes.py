from __future__ import annotations

import json
from pathlib import Path

from tests.helpers.module_loader import load_agent_history


def _set_config_dir(tmp_path: Path, monkeypatch) -> Path:
    """Point AGENT_HISTORY_CONFIG_DIR at a temp location."""
    config_dir = tmp_path / "config"
    monkeypatch.setenv("AGENT_HISTORY_CONFIG_DIR", str(config_dir))
    return config_dir


def test_save_config_uses_homes_key(tmp_path, monkeypatch):
    """Config writes a homes list (and keeps sources in sync for compatibility)."""
    config_dir = _set_config_dir(tmp_path, monkeypatch)

    ah = load_agent_history()
    data = ah.load_config()
    data["homes"] = ["remote@example.com"]
    assert ah.save_config(data)

    config_file = config_dir / "config.json"
    contents = json.loads(config_file.read_text())
    assert contents["homes"] == ["remote@example.com"]
    assert contents.get("sources") == ["remote@example.com"]


def test_load_config_maps_legacy_sources(tmp_path, monkeypatch):
    """Legacy config using sources is normalized to homes on load."""
    config_dir = _set_config_dir(tmp_path, monkeypatch)
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({"version": 1, "sources": ["wsl:Legacy"]}))

    ah = load_agent_history()
    data = ah.load_config()
    assert data["homes"] == ["wsl:Legacy"]
    assert data["sources"] == ["wsl:Legacy"]
