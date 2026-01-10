"""Tests for agent_history/utils/paths.py path utilities.

These tests verify workspace path encoding/decoding functions, including:
- normalize_workspace_name: Decode encoded workspace names to readable paths
- get_folder_short_name: Extract folder basename from workspace names
- is_cached_workspace: Detect remote/WSL/Windows prefixes
- convert_windows_path_to_encoded: Encode Windows paths
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from agent_history.utils.paths import (
    CACHED_PREFIXES,
    CACHED_REMOTE_PREFIX,
    CACHED_WINDOWS_PREFIX,
    CACHED_WSL_PREFIX,
    convert_windows_path_to_encoded,
    get_current_workspace_pattern,
    get_folder_short_name,
    get_workspace_name_from_path,
    is_cached_workspace,
    is_native_workspace,
    normalize_workspace_name,
)


class TestIsCachedWorkspace:
    """Test cached workspace prefix detection."""

    def test_detects_remote_prefix(self) -> None:
        """remote_ prefix should be detected as cached."""
        assert is_cached_workspace("remote_server01_home-bob-projects")
        assert is_cached_workspace("remote_myhost_var-www-html")

    def test_detects_wsl_prefix(self) -> None:
        """wsl_ prefix should be detected as cached."""
        assert is_cached_workspace("wsl_Ubuntu_home-user-project")
        assert is_cached_workspace("wsl_Debian_home-dev-app")

    def test_detects_windows_prefix(self) -> None:
        """windows_ prefix should be detected as cached."""
        assert is_cached_workspace("windows_alice_C--Users-alice-project")
        assert is_cached_workspace("windows_bob_D--Projects-myapp")

    def test_rejects_non_cached_workspace(self) -> None:
        """Regular workspace names should not be detected as cached."""
        assert not is_cached_workspace("-home-user-project")
        assert not is_cached_workspace("C--Users-alice-project")
        assert not is_cached_workspace("home-user-project")

    def test_rejects_partial_prefix_match(self) -> None:
        """Prefixes that don't match exactly should be rejected."""
        assert not is_cached_workspace("remoter_server_path")  # Not "remote_"
        assert not is_cached_workspace("wslish_distro_path")  # Not "wsl_"
        assert not is_cached_workspace("windowsy_user_path")  # Not "windows_"

    def test_empty_string(self) -> None:
        """Empty string should not be cached."""
        assert not is_cached_workspace("")

    def test_prefix_only(self) -> None:
        """Just the prefix itself should be detected."""
        assert is_cached_workspace("remote_")
        assert is_cached_workspace("wsl_")
        assert is_cached_workspace("windows_")


class TestIsNativeWorkspace:
    """Test native workspace detection (inverse of cached)."""

    def test_native_workspaces(self) -> None:
        """Regular paths should be native."""
        assert is_native_workspace("-home-user-project")
        assert is_native_workspace("C--Users-alice-project")

    def test_cached_workspaces_not_native(self) -> None:
        """Cached workspaces should not be native."""
        assert not is_native_workspace("remote_server_path")
        assert not is_native_workspace("wsl_Ubuntu_path")
        assert not is_native_workspace("windows_user_path")


class TestNormalizeWorkspaceName:
    """Test workspace path decoding."""

    def test_decode_simple_unix_path(self) -> None:
        """Test decoding -home-user-project to /home/user/project."""
        result = normalize_workspace_name("-home-user-project", verify_local=False)
        assert result == "/home/user/project"

    def test_decode_without_leading_dash(self) -> None:
        """Test decoding path without leading dash."""
        result = normalize_workspace_name("home-user-project", verify_local=False)
        assert result == "/home/user/project"

    def test_decode_deep_path(self) -> None:
        """Test decoding deep path hierarchy."""
        result = normalize_workspace_name("-home-user-projects-org-repo-src", verify_local=False)
        assert result == "/home/user/projects/org/repo/src"

    def test_decode_windows_path(self) -> None:
        """Test Windows path: C--Users-name to C:/Users/name or /C/Users/name."""
        result = normalize_workspace_name("C--Users-alice-project", verify_local=False)
        # On non-Windows, falls back to /C/... format with dashes converted to slashes
        if sys.platform == "win32":
            assert result == "C:\\Users\\alice\\project"
        else:
            # On Linux/WSL without verify_local, dashes are converted to slashes
            assert result == "/C/Users/alice/project"

    def test_decode_windows_path_with_drive_d(self) -> None:
        """Test Windows D: drive path."""
        result = normalize_workspace_name("D--Projects-myapp", verify_local=False)
        if sys.platform == "win32":
            assert result == "D:\\Projects\\myapp"
        else:
            # On Linux/WSL without verify_local, dashes are converted to slashes
            assert result == "/D/Projects/myapp"

    @pytest.mark.parametrize(
        "encoded,expected",
        [
            ("-var-www-html", "/var/www/html"),
            ("-opt-apps-myservice", "/opt/apps/myservice"),
            ("-usr-local-bin", "/usr/local/bin"),
        ],
    )
    def test_decode_various_unix_paths(self, encoded: str, expected: str) -> None:
        """Test various Unix path patterns."""
        result = normalize_workspace_name(encoded, verify_local=False)
        assert result == expected


class TestNormalizeWorkspaceNameWithFilesystem:
    """Test workspace decoding with filesystem verification."""

    @pytest.fixture
    def test_filesystem(self, tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
        """Create a test filesystem structure for path verification."""
        # Create directory structure
        (tmp_path / "home" / "user" / "projects" / "simple").mkdir(parents=True)
        (tmp_path / "home" / "user" / "projects" / "my-app").mkdir(parents=True)
        (tmp_path / "home" / "alice" / "alice" / "projects" / "api").mkdir(parents=True)

        # Set AGENT_HISTORY_HOME to use tmp_path as root for verification
        old_env = os.environ.get("AGENT_HISTORY_HOME")
        os.environ["AGENT_HISTORY_HOME"] = str(tmp_path)

        yield {
            "path": tmp_path,
            "simple": tmp_path / "home" / "user" / "projects" / "simple",
            "my_app": tmp_path / "home" / "user" / "projects" / "my-app",
        }

        # Restore environment
        if old_env is not None:
            os.environ["AGENT_HISTORY_HOME"] = old_env
        else:
            os.environ.pop("AGENT_HISTORY_HOME", None)

    def test_decode_path_with_existing_dir(self, test_filesystem: Dict[str, Any]) -> None:
        """Test decoding when the target directory exists."""
        result = normalize_workspace_name("-home-user-projects-simple", verify_local=True)
        assert result == "/home/user/projects/simple"

    def test_decode_path_with_dashes_in_folder_name(self, test_filesystem: Dict[str, Any]) -> None:
        """Test path with dashes in folder name resolves correctly when exists."""
        # When my-app exists, should preserve the dash
        result = normalize_workspace_name("-home-user-projects-my-app", verify_local=True)
        assert result == "/home/user/projects/my-app"

    def test_decode_deep_hierarchy(self, test_filesystem: Dict[str, Any]) -> None:
        """Test decoding deep path hierarchy with repeated segments."""
        # The bug case: alice/alice/projects/api
        result = normalize_workspace_name("-home-alice-alice-projects-api", verify_local=True)
        assert result == "/home/alice/alice/projects/api"
        assert "alice-projects" not in result


class TestGetFolderShortName:
    """Test extracting folder basename."""

    def test_from_decoded_path(self) -> None:
        """Test extracting basename from decoded path: /home/user/project -> project."""
        assert get_folder_short_name("/home/user/project") == "project"
        assert get_folder_short_name("/home/alice/projects/my-app") == "my-app"

    def test_from_encoded_path(self) -> None:
        """Test extracting basename from encoded path: -home-user-project -> project."""
        assert get_folder_short_name("-home-user-project") == "project"
        assert get_folder_short_name("-home-user-projects-myapp") == "myapp"

    def test_from_windows_encoded_path(self) -> None:
        """Test extracting basename from Windows encoded path."""
        assert get_folder_short_name("C--Users-alice-projects-myapp") == "myapp"
        assert get_folder_short_name("D--Projects-webapp") == "webapp"

    def test_empty_workspace(self) -> None:
        """Empty workspace should return empty string."""
        assert get_folder_short_name("") == ""

    def test_single_segment_path(self) -> None:
        """Single segment path should return the segment."""
        assert get_folder_short_name("/project") == "project"
        assert get_folder_short_name("-project") == "project"


class TestGetWorkspaceNameFromPath:
    """Test workspace name extraction with source tag stripping.

    Note: The function uses a heuristic that joins the last two path parts
    if the second-to-last part is <= 10 characters. This is designed to
    preserve hyphenated project names like "claude-history" but may join
    other short path segments like "projects-myapp".
    """

    def test_simple_path_with_short_parent(self) -> None:
        """Path with short parent joins last two parts."""
        # "projects" is 8 chars <= 10, so joins with "myapp"
        result = get_workspace_name_from_path("-home-user-projects-myapp")
        assert result == "projects-myapp"

    def test_simple_path_short_leaf(self) -> None:
        """Path where only leaf is needed."""
        # Use a path where second-to-last is > 10 chars
        result = get_workspace_name_from_path("-home-user-longdirname123-app")
        assert result == "app"

    def test_windows_path_with_short_parent(self) -> None:
        """Windows path with short parent joins last two parts."""
        # "projects" is <= 10 chars
        result = get_workspace_name_from_path("C--Users-alice-projects-myapp")
        assert result == "projects-myapp"

    def test_remote_source_tag_stripped(self) -> None:
        """Remote source tag should be stripped, then heuristic applied."""
        # After stripping: home-bob-projects-mylib
        # "projects" is <= 10 chars, so joins
        result = get_workspace_name_from_path("remote_server01_home-bob-projects-mylib")
        assert result == "projects-mylib"

    def test_wsl_source_tag_stripped(self) -> None:
        """WSL source tag should be stripped, then heuristic applied."""
        # After stripping: home-user-projects-auth
        # "projects" is <= 10 chars, so joins
        result = get_workspace_name_from_path("wsl_ubuntu_home-user-projects-auth")
        assert result == "projects-auth"

    def test_hyphenated_project_name(self) -> None:
        """Project names with hyphens should be preserved using heuristics."""
        # The heuristic joins last two parts if second-to-last is short
        result = get_workspace_name_from_path("-home-user-claude-history")
        assert result == "claude-history"

    def test_long_second_to_last_part(self) -> None:
        """Long second-to-last part should not trigger joining."""
        result = get_workspace_name_from_path("-home-user-longprojectname-subdir")
        # "longprojectname" is > 10 chars, so should return just "subdir"
        assert result == "subdir"

    def test_short_path(self) -> None:
        """Short path with < 2 parts returns last part."""
        result = get_workspace_name_from_path("project")
        assert result == "project"


class TestGetCurrentWorkspacePattern:
    """Test current workspace pattern generation."""

    def test_generates_pattern_from_cwd(self, tmp_path: Path, monkeypatch) -> None:
        """Should generate pattern based on current working directory."""
        # Create and change to test directory
        test_dir = tmp_path / "home" / "user" / "project"
        test_dir.mkdir(parents=True)
        monkeypatch.chdir(test_dir)

        # Clear AGENT_HISTORY_HOME to use actual cwd
        monkeypatch.delenv("AGENT_HISTORY_HOME", raising=False)

        pattern = get_current_workspace_pattern()
        # Pattern should be path with / replaced by -
        assert "home-user-project" in pattern or "project" in pattern

    def test_pattern_with_agent_history_home(self, tmp_path: Path, monkeypatch) -> None:
        """Pattern should strip AGENT_HISTORY_HOME prefix."""
        test_dir = tmp_path / "home" / "user" / "project"
        test_dir.mkdir(parents=True)
        monkeypatch.chdir(test_dir)
        monkeypatch.setenv("AGENT_HISTORY_HOME", str(tmp_path))

        pattern = get_current_workspace_pattern()
        # Should be relative to AGENT_HISTORY_HOME
        assert pattern == "home-user-project"


class TestConvertWindowsPathToEncoded:
    """Test Windows path encoding."""

    def test_backslash_path(self) -> None:
        """Windows path with backslashes should encode correctly."""
        result = convert_windows_path_to_encoded("C:\\Users\\alice\\project")
        assert result == "C--Users-alice-project"

    def test_forward_slash_path(self) -> None:
        """Windows path with forward slashes should encode correctly."""
        result = convert_windows_path_to_encoded("C:/Users/alice/project")
        assert result == "C--Users-alice-project"

    def test_mixed_slashes(self) -> None:
        """Windows path with mixed slashes should encode correctly."""
        result = convert_windows_path_to_encoded("D:/Projects\\myapp/src")
        assert result == "D--Projects-myapp-src"

    def test_lowercase_drive(self) -> None:
        """Lowercase drive letter should be uppercased."""
        result = convert_windows_path_to_encoded("c:\\Users\\test")
        assert result == "C--Users-test"

    def test_deep_path(self) -> None:
        """Deep Windows path should encode all segments."""
        result = convert_windows_path_to_encoded(
            "C:\\Users\\alice\\Documents\\Projects\\MyApp\\src\\main"
        )
        assert result == "C--Users-alice-Documents-Projects-MyApp-src-main"


class TestCachedPrefixConstants:
    """Test cached prefix constants are correctly defined."""

    def test_prefix_values(self) -> None:
        """Prefix constants should have correct values."""
        assert CACHED_REMOTE_PREFIX == "remote_"
        assert CACHED_WSL_PREFIX == "wsl_"
        assert CACHED_WINDOWS_PREFIX == "windows_"

    def test_prefixes_tuple(self) -> None:
        """CACHED_PREFIXES tuple should contain all prefixes."""
        assert CACHED_REMOTE_PREFIX in CACHED_PREFIXES
        assert CACHED_WSL_PREFIX in CACHED_PREFIXES
        assert CACHED_WINDOWS_PREFIX in CACHED_PREFIXES
        assert len(CACHED_PREFIXES) == 3
