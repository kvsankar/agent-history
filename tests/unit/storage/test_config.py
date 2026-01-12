"""Unit tests for agent_history/storage/config.py."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from agent_history.storage.config import (
    get_alias_for_workspace,
    get_config_dir,
    get_config_file,
    get_saved_homes,
    get_saved_sources,
    load_aliases,
    load_config,
    save_aliases,
    save_config,
)

# =============================================================================
# Test Helpers
# =============================================================================


def _set_config_dir(tmp_path: Path, monkeypatch) -> Path:
    """Point AGENT_HISTORY_CONFIG_DIR at a temp location."""
    config_dir = tmp_path / "config"
    monkeypatch.setenv("AGENT_HISTORY_CONFIG_DIR", str(config_dir))
    return config_dir


# =============================================================================
# Test Config Directory Functions
# =============================================================================


class TestConfigDir:
    """Tests for config directory resolution functions."""

    def test_get_config_dir_default(self, tmp_path, monkeypatch):
        """Default should be ~/.agent-history/."""
        # Clear any override
        monkeypatch.delenv("AGENT_HISTORY_CONFIG_DIR", raising=False)
        # Set HOME to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        config_dir = get_config_dir()

        assert config_dir == tmp_path / ".agent-history"

    def test_get_config_dir_from_env(self, tmp_path, monkeypatch):
        """AGENT_HISTORY_CONFIG_DIR should override default."""
        custom_config = tmp_path / "test-config"
        monkeypatch.setenv("AGENT_HISTORY_CONFIG_DIR", str(custom_config))

        result = get_config_dir()

        assert result == custom_config

    def test_get_config_file_returns_config_json(self, tmp_path, monkeypatch):
        """get_config_file should return path to config.json."""
        config_dir = _set_config_dir(tmp_path, monkeypatch)

        result = get_config_file()

        assert result == config_dir / "config.json"


# =============================================================================
# Test Config Load/Save
# =============================================================================


class TestConfigLoadSave:
    """Tests for config file loading and saving."""

    def test_load_config_empty(self, tmp_path, monkeypatch):
        """Loading non-existent config returns empty dict with defaults."""
        _set_config_dir(tmp_path, monkeypatch)

        result = load_config()

        assert isinstance(result, dict)
        assert result.get("version") == 1
        assert result.get("homes") == []
        assert result.get("sources") == []
        assert result.get("projects") == {}

    def test_save_and_load_config(self, tmp_path, monkeypatch):
        """Config should round-trip correctly."""
        _set_config_dir(tmp_path, monkeypatch)

        # Save config
        original_data = {
            "version": 1,
            "homes": ["remote@example.com", "wsl:Ubuntu"],
            "projects": {"myproject": {"local": ["-home-user-myproject"]}},
        }
        assert save_config(original_data)

        # Load and verify
        loaded = load_config()

        assert loaded["version"] == 1
        assert loaded["homes"] == ["remote@example.com", "wsl:Ubuntu"]
        assert loaded["sources"] == ["remote@example.com", "wsl:Ubuntu"]  # Kept in sync
        assert loaded["projects"] == {"myproject": {"local": ["-home-user-myproject"]}}

    def test_config_file_permissions(self, tmp_path, monkeypatch):
        """Config file should have secure permissions (0o600)."""
        config_dir = _set_config_dir(tmp_path, monkeypatch)

        save_config({"version": 1, "homes": []})

        config_file = config_dir / "config.json"
        assert config_file.exists()

        file_mode = config_file.stat().st_mode
        # Check that only owner has read/write (0o600)
        if sys.platform == "win32":
            pytest.skip("Windows does not enforce POSIX chmod semantics")
        assert stat.S_IMODE(file_mode) == 0o600

    def test_config_dir_permissions(self, tmp_path, monkeypatch):
        """Config directory should have secure permissions (0o700)."""
        config_dir = _set_config_dir(tmp_path, monkeypatch)

        save_config({"version": 1, "homes": []})

        assert config_dir.exists()
        dir_mode = config_dir.stat().st_mode
        # Check that only owner has rwx (0o700)
        if sys.platform == "win32":
            pytest.skip("Windows does not enforce POSIX chmod semantics")
        assert stat.S_IMODE(dir_mode) == 0o700

    def test_save_config_adds_version(self, tmp_path, monkeypatch):
        """save_config should add version if missing."""
        _set_config_dir(tmp_path, monkeypatch)

        # Save without version
        assert save_config({"homes": ["test@host"]})

        loaded = load_config()
        assert loaded["version"] == 1

    def test_load_config_normalizes_sources_to_homes(self, tmp_path, monkeypatch):
        """Legacy config with sources should be normalized to homes."""
        config_dir = _set_config_dir(tmp_path, monkeypatch)
        config_dir.mkdir(parents=True, exist_ok=True)

        # Write legacy format with sources only
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"version": 1, "sources": ["wsl:Legacy"]}))

        loaded = load_config()

        assert loaded["homes"] == ["wsl:Legacy"]
        assert loaded["sources"] == ["wsl:Legacy"]


# =============================================================================
# Test Alias/Project Functions
# =============================================================================


class TestAliases:
    """Tests for alias/project management functions."""

    def test_load_aliases_empty(self, tmp_path, monkeypatch):
        """Empty aliases returns proper structure."""
        _set_config_dir(tmp_path, monkeypatch)

        result = load_aliases()

        assert isinstance(result, dict)
        assert "version" in result
        assert result.get("projects") == {}

    def test_save_and_load_aliases(self, tmp_path, monkeypatch):
        """Aliases should round-trip correctly."""
        _set_config_dir(tmp_path, monkeypatch)

        original = {
            "version": 2,
            "projects": {
                "myproject": {
                    "local": ["-home-user-myproject", "-home-user-myproject2"],
                    "remote:server": ["-home-remote-project"],
                },
                "other": {"local": ["-home-user-other"]},
            },
        }
        assert save_aliases(original)

        loaded = load_aliases()

        assert loaded["projects"]["myproject"]["local"] == [
            "-home-user-myproject",
            "-home-user-myproject2",
        ]
        assert loaded["projects"]["myproject"]["remote:server"] == ["-home-remote-project"]
        assert loaded["projects"]["other"]["local"] == ["-home-user-other"]

    def test_get_alias_for_workspace_found(self, tmp_path, monkeypatch):
        """Should find alias containing workspace."""
        _set_config_dir(tmp_path, monkeypatch)

        # Setup aliases
        aliases = {
            "version": 2,
            "projects": {
                "myproject": {"local": ["-home-user-myproject"]},
                "other": {"local": ["-home-user-other"]},
            },
        }
        save_aliases(aliases)

        result = get_alias_for_workspace("-home-user-myproject", "local")

        assert result == "myproject"

    def test_get_alias_for_workspace_not_found(self, tmp_path, monkeypatch):
        """Should return None if workspace not in any alias."""
        _set_config_dir(tmp_path, monkeypatch)

        # Setup aliases without the target workspace
        aliases = {
            "version": 2,
            "projects": {
                "myproject": {"local": ["-home-user-myproject"]},
            },
        }
        save_aliases(aliases)

        result = get_alias_for_workspace("-home-user-unknown", "local")

        assert result is None

    def test_get_alias_for_workspace_different_source_matches_by_name(self, tmp_path, monkeypatch):
        """Should find alias by workspace name even with different source (fallback behavior)."""
        _set_config_dir(tmp_path, monkeypatch)

        aliases = {
            "version": 2,
            "projects": {
                "myproject": {"remote:server": ["-home-user-myproject"]},
            },
        }
        save_aliases(aliases)

        # Looking in local, but alias is under remote:server
        # The function falls back to workspace name matching
        result = get_alias_for_workspace("-home-user-myproject", "local")

        # Due to fallback matching by workspace name, it finds the alias
        assert result == "myproject"

    def test_get_alias_for_workspace_no_name_match(self, tmp_path, monkeypatch):
        """Should return None if workspace name doesn't match any alias."""
        _set_config_dir(tmp_path, monkeypatch)

        aliases = {
            "version": 2,
            "projects": {
                "myproject": {"remote:server": ["-home-user-different"]},
            },
        }
        save_aliases(aliases)

        # Workspace name 'myproject' vs 'different' - no match
        result = get_alias_for_workspace("-home-user-myproject", "local")

        assert result is None

    def test_save_aliases_migrates_aliases_to_projects(self, tmp_path, monkeypatch):
        """Legacy 'aliases' key should be migrated to 'projects'."""
        _set_config_dir(tmp_path, monkeypatch)

        # Save with legacy 'aliases' key
        legacy = {
            "version": 2,
            "aliases": {"myproject": {"local": ["-home-user-myproject"]}},
        }
        assert save_aliases(legacy)

        loaded = load_aliases()

        assert "myproject" in loaded["projects"]
        assert loaded["projects"]["myproject"]["local"] == ["-home-user-myproject"]


# =============================================================================
# Test Homes/Sources Functions
# =============================================================================


class TestHomes:
    """Tests for home/source management functions."""

    def test_get_saved_homes_empty(self, tmp_path, monkeypatch):
        """Empty config returns empty list."""
        _set_config_dir(tmp_path, monkeypatch)

        result = get_saved_homes()

        assert result == []

    def test_get_saved_homes_with_data(self, tmp_path, monkeypatch):
        """Should return configured homes."""
        _set_config_dir(tmp_path, monkeypatch)

        # Setup config with homes
        save_config(
            {
                "version": 1,
                "homes": ["remote@server1", "wsl:Ubuntu", "windows:User"],
            }
        )

        result = get_saved_homes()

        assert result == ["remote@server1", "wsl:Ubuntu", "windows:User"]

    def test_get_saved_sources_returns_same_as_homes(self, tmp_path, monkeypatch):
        """get_saved_sources should return same as get_saved_homes."""
        _set_config_dir(tmp_path, monkeypatch)

        save_config(
            {
                "version": 1,
                "homes": ["remote@server"],
            }
        )

        homes = get_saved_homes()
        sources = get_saved_sources()

        assert homes == sources == ["remote@server"]

    def test_get_saved_homes_falls_back_to_sources(self, tmp_path, monkeypatch):
        """Should fall back to sources if homes is missing."""
        config_dir = _set_config_dir(tmp_path, monkeypatch)
        config_dir.mkdir(parents=True, exist_ok=True)

        # Write config with only sources (legacy format)
        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "sources": ["legacy@server"],
                }
            )
        )

        result = get_saved_homes()

        assert result == ["legacy@server"]
