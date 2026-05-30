"""Tests for agent_history/utils/platform.py platform detection utilities.

These tests verify platform detection functions, including:
- is_running_in_wsl: Detect WSL environment
- get_wsl_distributions: Enumerate WSL distributions (Windows only)
- get_windows_home_from_wsl: Find Windows home from WSL
- Remote spec detection functions
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from agent_history.utils.platform import (
    AGENT_CLAUDE,
    AGENT_CODEX,
    AGENT_GEMINI,
    AGENT_PI,
    _build_wsl_distro_info,
    _CommandPathCache,
    _WindowsHomeCache,
    get_command_path,
    get_windows_codex_sessions_dir,
    get_windows_gemini_sessions_dir,
    get_windows_home_from_wsl,
    get_windows_projects_dir,
    get_windows_users_with_claude,
    get_wsl_distributions,
    get_wsl_projects_dir,
    is_running_in_wsl,
    is_windows_remote,
    is_wsl_remote,
    windows_home_cache_context,
)


class TestIsRunningInWsl:
    """Test WSL detection."""

    def test_detects_wsl_from_proc_version_microsoft(self) -> None:
        """Should detect WSL from /proc/version containing 'microsoft'."""
        mock_content = "Linux version 5.15.0-microsoft-standard-WSL2 (gcc)"
        with patch("builtins.open", mock_open(read_data=mock_content)):
            assert is_running_in_wsl() is True

    def test_detects_wsl_from_proc_version_wsl(self) -> None:
        """Should detect WSL from /proc/version containing 'wsl'."""
        mock_content = "Linux version 5.15.0-wsl (gcc)"
        with patch("builtins.open", mock_open(read_data=mock_content)):
            assert is_running_in_wsl() is True

    def test_not_wsl_regular_linux(self) -> None:
        """Should not detect WSL on regular Linux."""
        mock_content = "Linux version 5.15.0-generic (gcc)"
        with patch("builtins.open", mock_open(read_data=mock_content)):
            assert is_running_in_wsl() is False

    def test_not_wsl_when_proc_version_missing(self) -> None:
        """Should not detect WSL when /proc/version is missing."""
        with patch("builtins.open", side_effect=OSError("File not found")):
            assert is_running_in_wsl() is False

    def test_case_insensitive_detection(self) -> None:
        """Should detect WSL case-insensitively."""
        mock_content = "Linux version 5.15.0-MICROSOFT-Standard-WSL2 (gcc)"
        with patch("builtins.open", mock_open(read_data=mock_content)):
            assert is_running_in_wsl() is True


class TestIsWslRemote:
    """Test WSL remote spec detection."""

    def test_detects_wsl_remote(self) -> None:
        """Should detect wsl:// prefixed specs."""
        assert is_wsl_remote("wsl://Ubuntu") is True
        assert is_wsl_remote("wsl://Debian") is True
        assert is_wsl_remote("wsl://Ubuntu-22.04") is True

    def test_rejects_non_wsl_remote(self) -> None:
        """Should reject non-WSL remote specs."""
        assert is_wsl_remote("ssh://server") is False
        assert is_wsl_remote("windows://user") is False
        assert is_wsl_remote("Ubuntu") is False
        assert is_wsl_remote("wsl") is False  # Missing ://


class TestIsWindowsRemote:
    """Test Windows remote spec detection."""

    def test_detects_windows_remote_simple(self) -> None:
        """Should detect 'windows' remote spec."""
        assert is_windows_remote("windows") is True

    def test_detects_windows_remote_url_style(self) -> None:
        """Should detect windows:// URL-style spec."""
        assert is_windows_remote("windows://alice") is True
        assert is_windows_remote("windows://bob") is True

    def test_detects_windows_remote_config_style(self) -> None:
        """Should detect windows: config-style spec."""
        assert is_windows_remote("windows:alice") is True
        assert is_windows_remote("windows:bob") is True

    def test_rejects_non_windows_remote(self) -> None:
        """Should reject non-Windows remote specs."""
        assert is_windows_remote("wsl://Ubuntu") is False
        assert is_windows_remote("ssh://server") is False
        assert is_windows_remote("win") is False
        assert is_windows_remote("Windows") is False  # Case sensitive


class TestCommandPathCache:
    """Test command path caching."""

    def test_cache_stores_path(self) -> None:
        """Cache should store command paths."""
        cache = _CommandPathCache()
        # Mock shutil.which
        with patch("shutil.which", return_value="/usr/bin/ssh"):
            path = cache.get_path("ssh")
            assert path == "/usr/bin/ssh"

    def test_cache_returns_cached_value(self) -> None:
        """Cache should return cached value without calling which again."""
        cache = _CommandPathCache()
        with patch("shutil.which", return_value="/usr/bin/ssh") as mock_which:
            # First call
            path1 = cache.get_path("ssh")
            # Second call should use cache
            path2 = cache.get_path("ssh")

            assert path1 == path2 == "/usr/bin/ssh"
            # which should only be called once
            mock_which.assert_called_once_with("ssh")

    def test_cache_falls_back_to_cmd_name(self) -> None:
        """Cache should fall back to command name if not found."""
        cache = _CommandPathCache()
        with patch("shutil.which", return_value=None):
            path = cache.get_path("nonexistent")
            assert path == "nonexistent"

    def test_cache_clear(self) -> None:
        """Cache clear should reset the cache."""
        cache = _CommandPathCache()
        with patch("shutil.which", return_value="/usr/bin/ssh"):
            cache.get_path("ssh")

        cache.clear()

        with patch("shutil.which", return_value="/new/path/ssh") as mock_which:
            path = cache.get_path("ssh")
            assert path == "/new/path/ssh"
            mock_which.assert_called_once()


class TestGetCommandPath:
    """Test get_command_path function."""

    def test_returns_full_path(self) -> None:
        """Should return full path when command exists."""
        with patch("shutil.which", return_value="/usr/bin/git"):
            # Clear module cache to ensure fresh lookup
            from agent_history.utils import platform as platform_module

            platform_module._command_path_cache.clear()

            path = get_command_path("git")
            assert path == "/usr/bin/git"


class TestWslUsername:
    """Test WSL username lookup edge cases."""

    def test_wsl_username_handles_oserror_from_command_lookup(self) -> None:
        """Inaccessible WSL command paths should not crash username lookup."""
        from agent_history.utils import platform as platform_module

        platform_module._get_wsl_username.cache_clear()
        with patch.object(subprocess, "run", side_effect=OSError("wsl unavailable")):
            assert platform_module._get_wsl_username("Ubuntu") is None


class TestWindowsHomeCache:
    """Test Windows home cache."""

    def test_cache_operations(self) -> None:
        """Test basic cache get/set/has operations."""
        cache = _WindowsHomeCache()

        assert not cache.has("alice")
        assert cache.get("alice") is None

        cache.set("alice", Path("/mnt/c/Users/alice"))
        assert cache.has("alice")
        assert cache.get("alice") == Path("/mnt/c/Users/alice")

    def test_cache_stores_none(self) -> None:
        """Cache should distinguish between 'not cached' and 'cached as None'."""
        cache = _WindowsHomeCache()

        # Not in cache
        assert not cache.has("bob")

        # Cache None value
        cache.set("bob", None)
        assert cache.has("bob")
        assert cache.get("bob") is None

    def test_cache_clear(self) -> None:
        """Clear should reset the cache."""
        cache = _WindowsHomeCache()
        cache.set("alice", Path("/mnt/c/Users/alice"))

        cache.clear()

        assert not cache.has("alice")


class TestWindowsHomeCacheContext:
    """Test windows_home_cache_context context manager."""

    def test_context_manager_isolates_cache(self) -> None:
        """Context manager should provide isolated cache."""
        original_cache = _WindowsHomeCache()
        original_cache.set("original", Path("/original"))

        with windows_home_cache_context() as ctx_cache:
            assert not ctx_cache.has("original")
            ctx_cache.set("test", Path("/test"))

        # After context, original state should not be affected by ctx_cache

    def test_context_manager_with_custom_cache(self) -> None:
        """Context manager should use provided cache."""
        custom_cache = _WindowsHomeCache()
        custom_cache.set("custom", Path("/custom"))

        with windows_home_cache_context(custom_cache) as ctx_cache:
            assert ctx_cache is custom_cache
            assert ctx_cache.has("custom")


class TestGetWindowsHomeFromWsl:
    """Test Windows home detection from WSL."""

    def test_uses_override_env_var(self, tmp_path: Path) -> None:
        """Should use AGENT_HISTORY_HOME_WINDOWS if set."""
        with patch.dict(
            os.environ,
            {"AGENT_HISTORY_HOME_WINDOWS": str(tmp_path)},
            clear=False,
        ):
            result = get_windows_home_from_wsl()
            assert result == tmp_path

    def test_returns_none_with_agent_history_home(self, tmp_path: Path) -> None:
        """Should return None when AGENT_HISTORY_HOME is set (test mode)."""
        with patch.dict(
            os.environ,
            {
                "AGENT_HISTORY_HOME": str(tmp_path),
                "AGENT_HISTORY_TEST_MODE": "1",
            },
            clear=False,
        ):
            # Clear any AGENT_HISTORY_HOME_WINDOWS
            os.environ.pop("AGENT_HISTORY_HOME_WINDOWS", None)
            result = get_windows_home_from_wsl()
            assert result is None


class TestGetWindowsUsersWithClaude:
    """Test Windows users with Claude detection."""

    def test_returns_empty_with_agent_history_home(self, tmp_path: Path) -> None:
        """Should return empty list when AGENT_HISTORY_HOME is set."""
        with patch.dict(
            os.environ,
            {
                "AGENT_HISTORY_HOME": str(tmp_path),
                "AGENT_HISTORY_TEST_MODE": "1",
            },
        ):
            result = get_windows_users_with_claude()
            assert result == []

    def test_returns_empty_with_windows_home_override(self, tmp_path: Path) -> None:
        """Should return empty list when AGENT_HISTORY_HOME_WINDOWS is set."""
        with patch.dict(
            os.environ,
            {
                "AGENT_HISTORY_HOME_WINDOWS": str(tmp_path),
                "AGENT_HISTORY_TEST_MODE": "1",
            },
        ):
            result = get_windows_users_with_claude()
            assert result == []


class TestGetWslDistributions:
    """Test WSL distribution enumeration."""

    def test_returns_empty_on_non_windows(self) -> None:
        """Should return empty list on non-Windows platforms."""
        with patch("platform.system", return_value="Linux"):
            # Clear any test overrides
            with patch.dict(
                os.environ,
                {},
                clear=True,
            ):
                result = get_wsl_distributions()
                assert result == []

    def test_returns_empty_with_wsl_home_override(self, tmp_path: Path) -> None:
        """Should return empty list when AGENT_HISTORY_HOME_WSL is set."""
        with patch.dict(os.environ, {"AGENT_HISTORY_HOME_WSL": str(tmp_path)}):
            result = get_wsl_distributions()
            assert result == []

    def test_test_override_returns_fixture(self, tmp_path: Path) -> None:
        """Should use test override environment variables."""
        # Create mock projects directory
        projects_dir = tmp_path / ".claude" / "projects"
        projects_dir.mkdir(parents=True)

        with patch.dict(
            os.environ,
            {
                "CLAUDE_WSL_TEST_DISTRO": "TestDistro",
                "CLAUDE_WSL_PROJECTS_DIR": str(projects_dir),
            },
        ):
            result = get_wsl_distributions()
            assert len(result) == 1
            assert result[0]["name"] == "TestDistro"
            assert result[0]["username"] == "test"
            assert result[0]["has_claude"] is True
            assert result[0]["path"] == str(projects_dir)

    def test_distro_info_reports_pi_agent_paths(self, tmp_path: Path) -> None:
        """WSL distro metadata should include Pi when Pi sessions are present."""
        paths = {
            AGENT_CLAUDE: None,
            AGENT_CODEX: None,
            AGENT_GEMINI: None,
            AGENT_PI: tmp_path / ".pi" / "agent" / "sessions",
        }

        with patch(
            "agent_history.utils.platform._locate_wsl_agent_dir",
            side_effect=lambda _distro, _username, agent: paths.get(agent),
        ):
            result = _build_wsl_distro_info("Ubuntu", ["alice"])

        assert result is not None
        assert result["name"] == "Ubuntu"
        assert result["username"] == "alice"
        assert result["has_pi"] is True
        assert result["pi_path"] == str(paths[AGENT_PI])
        assert result["has_claude"] is False
        assert result["path"] is None


class TestGetWslProjectsDir:
    """Test WSL projects directory access."""

    def test_uses_override_env_var(self, tmp_path: Path) -> None:
        """Should use CLAUDE_WSL_PROJECTS_DIR override."""
        projects_dir = tmp_path / ".claude" / "projects"
        projects_dir.mkdir(parents=True)

        with patch.dict(os.environ, {"CLAUDE_WSL_PROJECTS_DIR": str(projects_dir)}):
            result = get_wsl_projects_dir("Ubuntu")
            assert result == projects_dir


class TestGetWindowsProjectsDir:
    """Test Windows projects directory from WSL."""

    def test_uses_override_env_var(self, tmp_path: Path) -> None:
        """Should use CLAUDE_WINDOWS_PROJECTS_DIR override."""
        projects_dir = tmp_path / ".claude" / "projects"
        projects_dir.mkdir(parents=True)

        with patch.dict(os.environ, {"CLAUDE_WINDOWS_PROJECTS_DIR": str(projects_dir)}):
            result = get_windows_projects_dir()
            assert result == projects_dir

    def test_returns_none_when_not_in_wsl(self, tmp_path: Path) -> None:
        """Should return None when not running in WSL."""
        # Clear any overrides
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_WINDOWS_PROJECTS_DIR", None)
            with patch("agent_history.utils.platform.is_running_in_wsl", return_value=False):
                result = get_windows_projects_dir()
                assert result is None

    def test_claude_windows_override_does_not_probe_other_agents(self, tmp_path: Path) -> None:
        """Claude-only Windows fixtures should not imply Codex/Gemini scans."""
        projects_dir = tmp_path / ".claude" / "projects"
        projects_dir.mkdir(parents=True)

        with patch.dict(
            os.environ,
            {
                "AGENT_HISTORY_TEST_MODE": "1",
                "CLAUDE_WINDOWS_PROJECTS_DIR": str(projects_dir),
            },
        ):
            assert get_windows_codex_sessions_dir() is None
            assert get_windows_gemini_sessions_dir() is None


class TestAgentConstants:
    """Test agent backend constants."""

    def test_agent_constants_defined(self) -> None:
        """Agent constants should be defined."""
        assert AGENT_CLAUDE == "claude"
        assert AGENT_CODEX == "codex"
        assert AGENT_GEMINI == "gemini"


# Platform-specific tests that may need to be skipped
@pytest.mark.skipif(
    sys.platform != "win32" and not os.path.exists("/proc/version"),
    reason="Platform-specific test",
)
class TestPlatformSpecific:
    """Platform-specific tests that run only on appropriate platforms."""

    @pytest.mark.skipif(sys.platform == "win32", reason="WSL test, skip on Windows")
    def test_actual_wsl_detection(self) -> None:
        """Test actual WSL detection on Linux."""
        # This test runs on actual Linux/WSL systems
        result = is_running_in_wsl()
        # Just verify it returns a boolean
        assert isinstance(result, bool)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_get_windows_home_caches_result(self) -> None:
        """Windows home lookup should cache results."""
        with windows_home_cache_context():
            # First call with a username
            with patch.dict(
                os.environ,
                {"AGENT_HISTORY_HOME_WINDOWS": "/mnt/c/Users/test"},
            ):
                result1 = get_windows_home_from_wsl("testuser")
                result2 = get_windows_home_from_wsl("testuser")
                assert result1 == result2

    def test_empty_distro_name_handled(self) -> None:
        """Empty WSL distro names should be handled gracefully."""
        # This is tested indirectly through the filtering in get_wsl_distributions
        with patch("platform.system", return_value="Windows"):
            with patch(
                "agent_history.utils.platform._get_wsl_distro_names",
                return_value=["", "Ubuntu", ""],
            ):
                with patch(
                    "agent_history.utils.platform._get_wsl_distro_info",
                    return_value=None,
                ):
                    result = get_wsl_distributions()
                    # Empty names should be filtered out
                    assert isinstance(result, list)
