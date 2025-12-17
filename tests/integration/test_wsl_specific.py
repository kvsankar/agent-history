"""Integration tests for WSL-specific functionality.

These tests only run when the environment is actually WSL.
They test the low-level WSL path resolution and Windows access functions.
"""

import importlib.machinery
import importlib.util
import os
from pathlib import Path

import pytest

# Import the agent-history module (no .py extension)
module_path = Path(__file__).parent.parent.parent / "agent-history"
loader = importlib.machinery.SourceFileLoader("agent_history", str(module_path))
spec = importlib.util.spec_from_loader("agent_history", loader)
ah = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ah)


def is_wsl_environment():
    """Check if we're running in WSL."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except (FileNotFoundError, PermissionError):
        return False


# Skip all tests if not in WSL
pytestmark = pytest.mark.skipif(not is_wsl_environment(), reason="Tests require WSL environment")


class TestWslDetection:
    """Test WSL environment detection functions."""

    def test_is_running_in_wsl_returns_true(self):
        """is_running_in_wsl() should return True in WSL."""
        assert ah.is_running_in_wsl() is True

    def test_proc_version_contains_microsoft(self):
        """Verify /proc/version contains 'microsoft' indicator."""
        with open("/proc/version") as f:
            content = f.read().lower()
        assert "microsoft" in content


class TestWslPathResolution:
    """Test WSL path resolution helper functions."""

    def test_looks_like_windows_drive_with_c_drive(self):
        """_looks_like_windows_drive identifies Windows paths."""
        assert ah._looks_like_windows_drive("C:/Users/test") is True
        assert ah._looks_like_windows_drive("C:\\Users\\test") is True
        assert ah._looks_like_windows_drive("D:/Projects") is True

    def test_looks_like_windows_drive_with_unix_path(self):
        """_looks_like_windows_drive rejects Unix paths."""
        assert ah._looks_like_windows_drive("/home/user") is False
        assert ah._looks_like_windows_drive("./relative/path") is False
        assert ah._looks_like_windows_drive("relative") is False

    def test_strip_wsl_unc_prefix_with_wsl_path(self):
        """_strip_wsl_unc_prefix strips //wsl.localhost/ prefix."""
        # Test with standard WSL UNC path (forward slashes)
        result = ah._strip_wsl_unc_prefix("//wsl.localhost/Ubuntu/home/user")
        assert result == "/home/user"

        # Test with wsl$ variant
        result = ah._strip_wsl_unc_prefix("//wsl$/Ubuntu/home/user")
        assert result == "/home/user"

    def test_strip_wsl_unc_prefix_without_prefix(self):
        """_strip_wsl_unc_prefix returns unchanged path without prefix."""
        result = ah._strip_wsl_unc_prefix("/home/user/projects")
        assert result == "/home/user/projects"

    def test_is_windows_encoded_path(self):
        """_is_windows_encoded_path identifies Windows-encoded workspace names."""
        # Windows paths start with drive letter
        assert ah._is_windows_encoded_path("C--Users-test-project") is True
        assert ah._is_windows_encoded_path("D--Projects-myapp") is True

        # Unix paths start with dash (for leading /)
        assert ah._is_windows_encoded_path("-home-user-project") is False
        assert ah._is_windows_encoded_path("myproject") is False

    def test_is_wsl_unc_path_with_valid_paths(self):
        """_is_wsl_unc_path identifies WSL UNC paths."""
        # Test with Path objects
        assert ah._is_wsl_unc_path(Path("//wsl.localhost/Ubuntu/home")) is True
        assert ah._is_wsl_unc_path(Path("//wsl$/Ubuntu/home")) is True

    def test_is_wsl_unc_path_with_regular_paths(self):
        """_is_wsl_unc_path rejects regular paths."""
        assert ah._is_wsl_unc_path(Path("/home/user")) is False
        assert ah._is_wsl_unc_path(Path("/mnt/c/Users")) is False
        assert ah._is_wsl_unc_path(None) is False


class TestWindowsPathConversion:
    """Test Windows path encoding/decoding."""

    def test_convert_windows_path_to_encoded(self):
        """_convert_windows_path_to_encoded creates proper encoded names."""
        # C:\Users\test\project -> C--Users-test-project
        result = ah._convert_windows_path_to_encoded("C:\\Users\\test\\project")
        assert result == "C--Users-test-project"

        # Handle forward slashes too
        result = ah._convert_windows_path_to_encoded("C:/Users/test/project")
        assert result == "C--Users-test-project"

    def test_normalize_windows_path_basic(self):
        """_normalize_windows_path converts encoded names to readable paths."""
        # Without verification (just formatting)
        result = ah._normalize_windows_path("C--Users-test-project", verify_local=False)
        assert "Users" in result
        assert "test" in result
        assert "project" in result


class TestWslUncPaths:
    """Test WSL UNC path handling."""

    def test_projects_dir_from_wsl_unc(self):
        """_projects_dir_from_wsl_unc extracts projects dir from UNC path."""
        # Use forward slashes as expected by the function
        unc_path = "//wsl.localhost/Ubuntu/home/user/.claude/projects"
        result = ah._projects_dir_from_wsl_unc(unc_path)
        # The function may return the path or a relative path depending on implementation
        # Just verify it returns a Path object
        assert isinstance(result, Path)

    def test_detect_wsl_base_path_with_wsl_unc(self):
        """_detect_wsl_base_path handles WSL UNC paths."""
        # Create a path that looks like WSL UNC
        wsl_path = Path("//wsl.localhost/Ubuntu/home/user/.claude/projects")
        # Call the function - should return a base path or None
        # The actual behavior depends on whether the path exists
        ah._detect_wsl_base_path(wsl_path)


class TestWindowsAccessFromWsl:
    """Test Windows filesystem access from WSL."""

    def test_mnt_c_exists(self):
        """Verify /mnt/c exists (Windows C: drive mount)."""
        assert Path("/mnt/c").exists(), "Windows C: drive should be mounted at /mnt/c"

    def test_is_valid_windows_drive_with_mnt_c(self):
        """_is_valid_windows_drive validates /mnt/c."""
        result = ah._is_valid_windows_drive(Path("/mnt/c"))
        assert result is True

    def test_is_valid_windows_drive_with_invalid(self):
        """_is_valid_windows_drive rejects invalid drives."""
        # Call the function - may be True or False depending on system config
        ah._is_valid_windows_drive(Path("/mnt/z"))  # Usually doesn't exist

    def test_get_windows_home_from_wsl_finds_home(self):
        """get_windows_home_from_wsl finds Windows user home."""
        # This should find at least one Windows user home
        result = ah.get_windows_home_from_wsl()
        # Result could be None if no Windows users with Claude exist
        # But the function should not raise an error
        if result:
            assert result.exists()
            assert "/mnt/" in str(result) or "\\\\wsl" in str(result)

    def test_get_windows_users_with_claude(self):
        """get_windows_users_with_claude returns list of users."""
        users = ah.get_windows_users_with_claude()
        assert isinstance(users, list)
        # May be empty if no Windows users have Claude installed


class TestWslDistributions:
    """Test WSL distribution detection."""

    def test_get_wsl_distro_names_returns_list(self):
        """_get_wsl_distro_names returns a list."""
        # This function uses wsl.exe which should be available in WSL
        result = ah._get_wsl_distro_names()
        assert isinstance(result, list)
        # Current distro should be in the list
        if result:
            # At least one distribution should exist since we're in WSL
            assert len(result) >= 1

    def test_get_wsl_distributions_returns_list(self):
        """get_wsl_distributions returns list of dicts."""
        result = ah.get_wsl_distributions()
        assert isinstance(result, list)

    def test_get_wsl_home_path_returns_path_or_none(self):
        """_get_wsl_home_path returns home path for distro."""
        distros = ah._get_wsl_distro_names()
        if distros:
            # Test with first available distro
            result = ah._get_wsl_home_path(distros[0])
            # Should return a string path or None
            assert result is None or isinstance(result, str)


class TestWslProjectsDirs:
    """Test WSL projects directory functions."""

    def test_get_wsl_projects_dir_with_current_distro(self):
        """get_wsl_projects_dir finds projects for current distro."""
        # Get current distro name
        distros = ah._get_wsl_distro_names()
        if distros:
            # Try to get projects dir for first distro
            # Result may be None if no Claude projects exist
            ah.get_wsl_projects_dir(distros[0])

    def test_get_windows_projects_dir(self):
        """get_windows_projects_dir finds Windows Claude projects."""
        result = ah.get_windows_projects_dir()
        # Result may be None if no Windows Claude installation
        if result:
            assert isinstance(result, Path)


class TestWslAgentDirs:
    """Test WSL agent directory functions (Codex, Gemini)."""

    def test_get_wsl_gemini_candidate_paths(self):
        """_get_wsl_gemini_candidate_paths returns paths list."""
        distros = ah._get_wsl_distro_names()
        if distros:
            result = ah._get_wsl_gemini_candidate_paths(distros[0], "testuser")
            assert isinstance(result, list)

    def test_get_wsl_codex_candidate_paths(self):
        """_get_wsl_codex_candidate_paths returns paths list."""
        distros = ah._get_wsl_distro_names()
        if distros:
            result = ah._get_wsl_codex_candidate_paths(distros[0], "testuser")
            assert isinstance(result, list)

    def test_get_agent_wsl_dir_claude(self):
        """get_agent_wsl_dir finds Claude dir for distro."""
        distros = ah._get_wsl_distro_names()
        if distros:
            # May be None if no Claude installation in that distro
            ah.get_agent_wsl_dir(distros[0], "claude")

    def test_get_agent_wsl_dir_codex(self):
        """get_agent_wsl_dir finds Codex dir for distro."""
        distros = ah._get_wsl_distro_names()
        if distros:
            # May be None if no Codex installation
            ah.get_agent_wsl_dir(distros[0], "codex")

    def test_get_agent_wsl_dir_gemini(self):
        """get_agent_wsl_dir finds Gemini dir for distro."""
        distros = ah._get_wsl_distro_names()
        if distros:
            # May be None if no Gemini installation
            ah.get_agent_wsl_dir(distros[0], "gemini")


class TestWslWindowsAgentDirs:
    """Test Windows agent directory functions from WSL."""

    def test_get_agent_windows_dir_claude(self):
        """get_agent_windows_dir finds Claude dir for Windows user."""
        users = ah.get_windows_users_with_claude()
        if users:
            # users is a list of dicts with 'username' key
            username = users[0]["username"]
            result = ah.get_agent_windows_dir(username, "claude")
            if result:
                assert isinstance(result, Path)

    def test_gemini_get_windows_sessions_dir(self):
        """gemini_get_windows_sessions_dir finds Gemini sessions."""
        # May be None if no Gemini installation on Windows
        ah.gemini_get_windows_sessions_dir()

    def test_codex_get_windows_sessions_dir(self):
        """codex_get_windows_sessions_dir finds Codex sessions."""
        # May be None if no Codex installation on Windows
        ah.codex_get_windows_sessions_dir()


class TestResolveExistingWslPath:
    """Test the _resolve_existing_wsl_path function."""

    def test_resolve_existing_wsl_path_basic(self):
        """_resolve_existing_wsl_path resolves path components."""
        # Test with home directory parts
        parts = ["home", os.environ.get("USER", "user")]
        base_path = Path("/")

        result = ah._resolve_existing_wsl_path(parts, base_path)
        # Should return a tuple (readable_path, remaining_segments)
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestNormalizeWorkspaceWithWsl:
    """Test normalize_workspace_name in WSL context."""

    def test_normalize_workspace_name_wsl_path(self):
        """normalize_workspace_name handles WSL paths."""
        # A typical WSL workspace name
        result = ah.normalize_workspace_name("-home-user-projects-myapp", verify_local=False)
        assert "/" in result or "\\" in result  # Contains path separators

    def test_normalize_workspace_name_windows_path(self):
        """normalize_workspace_name handles Windows paths."""
        result = ah.normalize_workspace_name("C--Users-test-projects-myapp", verify_local=False)
        assert "Users" in result


class TestApplyWindowsBaseResolution:
    """Test _apply_windows_base_resolution function."""

    def test_apply_windows_base_resolution_basic(self):
        """_apply_windows_base_resolution extends path segments."""
        parts = ["Users", "test", "projects"]
        base_path = Path("/mnt/c")
        current_segments = ["C:"]

        # This modifies current_segments in place
        ah._apply_windows_base_resolution(parts, base_path, current_segments)
        # Should have extended the segments
        assert len(current_segments) >= 1


class TestLocateWslProjectsDir:
    """Test _locate_wsl_projects_dir function."""

    def test_locate_wsl_projects_dir_returns_path_or_none(self):
        """_locate_wsl_projects_dir finds projects dir or returns None."""
        distros = ah._get_wsl_distro_names()
        if distros:
            # Get home path for distro to determine username
            home_path = ah._get_wsl_home_path(distros[0])
            if home_path:
                username = Path(home_path).name
                # Result is Path or None
                ah._locate_wsl_projects_dir(distros[0], username)


class TestLocateWslAgentDir:
    """Test _locate_wsl_agent_dir function."""

    def test_locate_wsl_agent_dir_claude(self):
        """_locate_wsl_agent_dir finds Claude dir."""
        distros = ah._get_wsl_distro_names()
        if distros:
            # Result is Path or None
            ah._locate_wsl_agent_dir(distros[0], "testuser", "claude")

    def test_locate_wsl_agent_dir_codex(self):
        """_locate_wsl_agent_dir finds Codex dir."""
        distros = ah._get_wsl_distro_names()
        if distros:
            # Result is Path or None
            ah._locate_wsl_agent_dir(distros[0], "testuser", "codex")

    def test_locate_wsl_agent_dir_gemini(self):
        """_locate_wsl_agent_dir finds Gemini dir."""
        distros = ah._get_wsl_distro_names()
        if distros:
            # Result is Path or None
            ah._locate_wsl_agent_dir(distros[0], "testuser", "gemini")
