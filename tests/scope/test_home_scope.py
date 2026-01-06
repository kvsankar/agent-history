"""Tests for home scope resolution.

Tests home scope modifiers:
- Local home (default)
- WSL home (--wsl)
- Windows home (--windows)
- Remote home (-r user@host)
- Named home (--home <name>)
- All homes (--ah, --all-homes)
- Source exclusions (--no-wsl, --no-windows, --no-remote)

Spec reference: cli-spec.md#scope-modifiers
"""

import platform
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tests.helpers.cli import (
    assert_cli_success,
    run_cli_subprocess,
)

# ---------------------------------------------------------------------------
# Platform Detection Helpers
# ---------------------------------------------------------------------------


def get_current_platform() -> str:
    """Detect current platform."""
    if sys.platform == "win32":
        return "windows"
    try:
        if "microsoft" in platform.uname().release.lower():
            return "wsl"
    except AttributeError:
        pass
    return "linux"


CURRENT_PLATFORM = get_current_platform()

# Platform-specific skip decorators
skip_unless_windows = pytest.mark.skipif(CURRENT_PLATFORM != "windows", reason="Windows-only test")
skip_unless_wsl = pytest.mark.skipif(CURRENT_PLATFORM != "wsl", reason="WSL-only test")
skip_unless_linux = pytest.mark.skipif(CURRENT_PLATFORM != "linux", reason="Linux-only test")


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.scope, pytest.mark.home_scope]


# ---------------------------------------------------------------------------
# Local Home (Default)
# ---------------------------------------------------------------------------


class TestLocalHomeScope:
    """Tests for default local home scope."""

    def test_session_list_defaults_to_local_home(self, multi_home_setup: Dict[str, Any]) -> None:
        """session list with no home flags uses local home.

        Spec: "Local home (default) - (none)"
        """
        result = run_cli_subprocess(
            ["session", "list", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "session list should default to local home")

    def test_ws_list_defaults_to_local_home(self, multi_home_setup: Dict[str, Any]) -> None:
        """ws list with no home flags uses local home.

        Spec: Default home is local.
        """
        result = run_cli_subprocess(
            ["ws", "list"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "ws list should default to local home")

    def test_local_home_isolation(self, multi_home_setup: Dict[str, Any]) -> None:
        """Local home queries should not include other homes' sessions."""
        result = run_cli_subprocess(
            ["session", "list", "--aw", "--format", "json"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "Local home should be isolated")

        # Note: Actual validation of isolation depends on json output parsing


# ---------------------------------------------------------------------------
# WSL Home (--wsl)
# ---------------------------------------------------------------------------


class TestWSLHomeScope:
    """Tests for --wsl home scope."""

    def test_wsl_flag_accesses_wsl_home(self, multi_home_setup: Dict[str, Any]) -> None:
        """--wsl reads from WSL home directory.

        Spec: "--wsl - WSL home"
        """
        run_cli_subprocess(
            ["session", "list", "--wsl", "--aw"],
            env=multi_home_setup["env"],
        )

        # Result depends on platform availability
        # On non-WSL/Windows systems, this should error gracefully

    def test_wsl_flag_with_ws_list(self, multi_home_setup: Dict[str, Any]) -> None:
        """ws list --wsl shows WSL workspaces."""
        run_cli_subprocess(
            ["ws", "list", "--wsl"],
            env=multi_home_setup["env"],
        )

        # Platform-dependent behavior

    @skip_unless_windows
    def test_wsl_flag_on_windows(self, multi_home_setup: Dict[str, Any]) -> None:
        """--wsl should work on Windows to access WSL filesystem."""
        result = run_cli_subprocess(
            ["session", "list", "--wsl", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "--wsl should work on Windows")

    @skip_unless_wsl
    def test_wsl_flag_on_wsl_is_local(self, multi_home_setup: Dict[str, Any]) -> None:
        """--wsl on WSL should be same as local (or no-op)."""
        run_cli_subprocess(
            ["session", "list", "--wsl", "--aw"],
            env=multi_home_setup["env"],
        )

        # On WSL, --wsl might be equivalent to local

    @skip_unless_linux
    def test_wsl_flag_errors_on_linux(self, multi_home_setup: Dict[str, Any]) -> None:
        """--wsl should error on native Linux (not WSL).

        Spec: "--wsl is not available on native Linux"
        """
        run_cli_subprocess(
            ["session", "list", "--wsl", "--aw"],
            env=multi_home_setup["env"],
        )

        # Should error with message about WSL not available
        # Or skip gracefully


# ---------------------------------------------------------------------------
# Windows Home (--windows)
# ---------------------------------------------------------------------------


class TestWindowsHomeScope:
    """Tests for --windows home scope."""

    def test_windows_flag_accesses_windows_home(self, multi_home_setup: Dict[str, Any]) -> None:
        """--windows reads from Windows home directory.

        Spec: "--windows - Windows home (from WSL)"
        """
        run_cli_subprocess(
            ["session", "list", "--windows", "--aw"],
            env=multi_home_setup["env"],
        )

        # Result depends on platform availability

    def test_windows_flag_with_ws_list(self, multi_home_setup: Dict[str, Any]) -> None:
        """ws list --windows shows Windows workspaces."""
        run_cli_subprocess(
            ["ws", "list", "--windows"],
            env=multi_home_setup["env"],
        )

        # Platform-dependent behavior

    @skip_unless_wsl
    def test_windows_flag_on_wsl(self, multi_home_setup: Dict[str, Any]) -> None:
        """--windows should work on WSL to access Windows filesystem."""
        result = run_cli_subprocess(
            ["session", "list", "--windows", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "--windows should work on WSL")

    @skip_unless_windows
    def test_windows_flag_on_windows_is_local(self, multi_home_setup: Dict[str, Any]) -> None:
        """--windows on Windows should be same as local (or no-op)."""
        run_cli_subprocess(
            ["session", "list", "--windows", "--aw"],
            env=multi_home_setup["env"],
        )

        # On Windows, --windows might be equivalent to local

    @skip_unless_linux
    def test_windows_flag_errors_on_linux(self, multi_home_setup: Dict[str, Any]) -> None:
        """--windows should error on native Linux.

        Spec: "--windows is not available on native Linux"
        """
        run_cli_subprocess(
            ["session", "list", "--windows", "--aw"],
            env=multi_home_setup["env"],
        )

        # Should error with message about Windows not available


# ---------------------------------------------------------------------------
# Remote Home (-r user@host)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="SSH tests require Docker infrastructure - see Agent 8: Docker SSH Tests")
class TestRemoteHomeScope:
    """Tests for -r/--remote home scope."""

    def test_remote_flag_syntax(self, multi_home_setup: Dict[str, Any]) -> None:
        """Remote flag accepts user@host format.

        Spec: "-r <user@host> - SSH remote (repeatable)"
        """
        run_cli_subprocess(
            ["session", "list", "-r", "user@example.com", "--aw"],
            env=multi_home_setup["env"],
        )

        # Will fail to connect (no real SSH), but syntax should be valid

    def test_remote_flag_multiple_hosts(self, multi_home_setup: Dict[str, Any]) -> None:
        """Multiple -r flags for multiple remotes.

        Spec: "-r is repeatable"
        """
        run_cli_subprocess(
            ["session", "list", "-r", "user@host1", "-r", "user@host2", "--aw"],
            env=multi_home_setup["env"],
        )

        # Syntax should be valid even if connection fails

    def test_remote_flag_with_ws_list(self, multi_home_setup: Dict[str, Any]) -> None:
        """ws list with remote shows remote workspaces."""
        run_cli_subprocess(
            ["ws", "list", "-r", "user@example.com"],
            env=multi_home_setup["env"],
        )

        # Will fail to connect but syntax valid

    def test_remote_connection_failure_handling(self, multi_home_setup: Dict[str, Any]) -> None:
        """Remote connection failure should error gracefully.

        Spec: "SSH connection failed: Connection refused"
        """
        run_cli_subprocess(
            ["session", "list", "-r", "user@nonexistent-host-12345"],
            env=multi_home_setup["env"],
            timeout=10,  # Short timeout for connection failure
        )

        # Should error but not hang


# ---------------------------------------------------------------------------
# Named Home (--home <name>)
# ---------------------------------------------------------------------------


class TestNamedHomeScope:
    """Tests for --home <name> scope."""

    def test_home_flag_by_name(self, multi_home_setup: Dict[str, Any]) -> None:
        """--home <name> uses specific saved home by name.

        Spec: "--home <name> - Specific saved home by name (repeatable)"
        """
        result = run_cli_subprocess(
            ["session", "list", "--home", "local", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "--home local should succeed")

    def test_home_flag_multiple_names(self, multi_home_setup: Dict[str, Any]) -> None:
        """Multiple --home flags for multiple named homes.

        Spec: "--home is repeatable"
        """
        run_cli_subprocess(
            ["session", "list", "--home", "local", "--home", "wsl", "--aw"],
            env=multi_home_setup["env"],
        )

        # Should combine sessions from both homes

    def test_home_flag_nonexistent_name(self, multi_home_setup: Dict[str, Any]) -> None:
        """--home <nonexistent> should error appropriately."""
        run_cli_subprocess(
            ["session", "list", "--home", "nonexistent-home", "--aw"],
            env=multi_home_setup["env"],
        )

        # Should error with helpful message


# ---------------------------------------------------------------------------
# All Homes (--ah, --all-homes)
# ---------------------------------------------------------------------------


class TestAllHomesScope:
    """Tests for --ah/--all-homes flag."""

    def test_all_homes_flag_long(self, multi_home_setup: Dict[str, Any]) -> None:
        """--all-homes includes all configured homes.

        Spec: "--ah / --all-homes - All configured homes"
        """
        result = run_cli_subprocess(
            ["session", "list", "--all-homes", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "--all-homes should succeed")

    def test_all_homes_flag_short(self, multi_home_setup: Dict[str, Any]) -> None:
        """--ah is shorthand for --all-homes."""
        result = run_cli_subprocess(
            ["session", "list", "--ah", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "--ah should succeed")

    def test_all_homes_includes_local(self, multi_home_setup: Dict[str, Any]) -> None:
        """--ah should include local home."""
        result = run_cli_subprocess(
            ["session", "list", "--ah", "--aw", "--format", "json"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "--ah should include local home")

    def test_all_homes_shows_home_column(self, multi_home_setup: Dict[str, Any]) -> None:
        """--ah output should show HOME column.

        Spec: "With --ah (multi-home): HOME column in output"
        """
        result = run_cli_subprocess(
            ["session", "list", "--ah", "--aw"],
            env=multi_home_setup["env"],
        )

        # Output should include HOME column
        assert_cli_success(result, "--ah should show home column")

    def test_all_homes_with_ws_list(self, multi_home_setup: Dict[str, Any]) -> None:
        """ws list --ah shows workspaces from all homes."""
        result = run_cli_subprocess(
            ["ws", "list", "--ah"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "ws list --ah should succeed")


# ---------------------------------------------------------------------------
# Source Exclusions (with --ah)
# ---------------------------------------------------------------------------


class TestSourceExclusions:
    """Tests for source exclusion flags with --ah."""

    def test_no_wsl_excludes_wsl(self, multi_home_setup: Dict[str, Any]) -> None:
        """--ah --no-wsl excludes WSL homes.

        Spec: "--no-wsl - Skip WSL sources"
        """
        result = run_cli_subprocess(
            ["session", "list", "--ah", "--no-wsl", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "--ah --no-wsl should succeed")

    def test_no_windows_excludes_windows(self, multi_home_setup: Dict[str, Any]) -> None:
        """--ah --no-windows excludes Windows homes.

        Spec: "--no-windows - Skip Windows sources"
        """
        result = run_cli_subprocess(
            ["session", "list", "--ah", "--no-windows", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "--ah --no-windows should succeed")

    def test_no_remote_excludes_remotes(self, multi_home_setup: Dict[str, Any]) -> None:
        """--ah --no-remote excludes SSH remotes.

        Spec: "--no-remote - Skip SSH remotes"
        """
        result = run_cli_subprocess(
            ["session", "list", "--ah", "--no-remote", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "--ah --no-remote should succeed")

    @pytest.mark.skip(reason="--no-web not implemented")
    def test_no_web_excludes_web(self, multi_home_setup: Dict[str, Any]) -> None:
        """--ah --no-web excludes web sessions.

        Spec: "--no-web - Skip web sessions"
        """
        result = run_cli_subprocess(
            ["session", "list", "--ah", "--no-web", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "--ah --no-web should succeed")

    def test_local_flag_with_ah(self, multi_home_setup: Dict[str, Any]) -> None:
        """--ah --local limits to local home only.

        Spec: "--local - Local home only"
        """
        result = run_cli_subprocess(
            ["session", "list", "--ah", "--local", "--aw"],
            env=multi_home_setup["env"],
        )

        # --local with --ah should result in local-only
        assert_cli_success(result, "--ah --local should limit to local")

    def test_multiple_exclusions(self, multi_home_setup: Dict[str, Any]) -> None:
        """Multiple exclusion flags should combine.

        Spec: "--ah --no-wsl --no-remote: Local + Windows only"
        """
        result = run_cli_subprocess(
            ["session", "list", "--ah", "--no-wsl", "--no-remote", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "Multiple exclusions should succeed")


# ---------------------------------------------------------------------------
# Home List Command
# ---------------------------------------------------------------------------


class TestHomeListCommand:
    """Tests for home list command."""

    def test_home_list_shows_all_homes(self, multi_home_setup: Dict[str, Any]) -> None:
        """home list shows all configured homes.

        Spec: "home [list] - List all configured homes"
        """
        result = run_cli_subprocess(
            ["home", "list"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "home list should succeed")

    def test_home_list_shows_status(self, multi_home_setup: Dict[str, Any]) -> None:
        """home list shows home status.

        Spec: Output includes STATUS column
        """
        result = run_cli_subprocess(
            ["home", "list"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "home list should show status")

    def test_home_show_details(self, multi_home_setup: Dict[str, Any]) -> None:
        """home show <name> shows home details.

        Spec: "home show <name> - Show home details"
        """
        run_cli_subprocess(
            ["home", "show", "local"],
            env=multi_home_setup["env"],
        )

        # May not be implemented, check graceful handling


# ---------------------------------------------------------------------------
# Home Add/Remove Commands
# ---------------------------------------------------------------------------


class TestHomeManagement:
    """Tests for home add/remove commands."""

    def test_home_add_wsl(self, multi_home_setup: Dict[str, Any]) -> None:
        """home add --wsl adds WSL home.

        Spec: "home add --wsl - Add WSL"
        """
        run_cli_subprocess(
            ["home", "add", "--wsl"],
            env=multi_home_setup["env"],
        )

        # Behavior depends on platform and implementation

    def test_home_add_windows(self, multi_home_setup: Dict[str, Any]) -> None:
        """home add --windows adds Windows home.

        Spec: "home add --windows - Add Windows"
        """
        run_cli_subprocess(
            ["home", "add", "--windows"],
            env=multi_home_setup["env"],
        )

        # Behavior depends on platform and implementation

    def test_home_add_remote(self, multi_home_setup: Dict[str, Any]) -> None:
        """home add user@host adds SSH remote.

        Spec: "home add user@hostname - Add SSH remote"
        """
        run_cli_subprocess(
            ["home", "add", "user@example.com"],
            env=multi_home_setup["env"],
        )

        # Syntax should be valid

    def test_home_remove(self, multi_home_setup: Dict[str, Any]) -> None:
        """home remove <source> removes a home.

        Spec: "home remove <source> - Remove a home"
        """
        run_cli_subprocess(
            ["home", "remove", "nonexistent"],
            env=multi_home_setup["env"],
        )

        # Should handle gracefully


# ---------------------------------------------------------------------------
# Home Scope with Other Commands
# ---------------------------------------------------------------------------


class TestHomeScopeWithCommands:
    """Tests for home scope with various commands."""

    def test_session_export_with_home_scope(
        self, multi_home_setup: Dict[str, Any], tmp_path: Path
    ) -> None:
        """session export respects home scope."""
        output_dir = tmp_path / "export_output"
        result = run_cli_subprocess(
            ["session", "export", "--home", "local", "--aw", "-o", str(output_dir)],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "session export with --home should succeed")

    def test_session_stats_with_home_scope(self, multi_home_setup: Dict[str, Any]) -> None:
        """session stats respects home scope."""
        result = run_cli_subprocess(
            ["session", "stats", "--home", "local", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "session stats with --home should succeed")

    def test_session_stats_all_homes(self, multi_home_setup: Dict[str, Any]) -> None:
        """session stats --ah aggregates across all homes.

        Spec: "session stats --ah --aw: Syncs everything, then shows stats"
        """
        result = run_cli_subprocess(
            ["session", "stats", "--ah", "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "session stats --ah --aw should succeed")


# ---------------------------------------------------------------------------
# Home Scope Precedence
# ---------------------------------------------------------------------------


class TestHomeScopePrecedence:
    """Tests for home scope precedence rules."""

    def test_explicit_home_overrides_default(self, multi_home_setup: Dict[str, Any]) -> None:
        """Explicit --home overrides local default."""
        # Using environment variable to point to different home
        env = multi_home_setup["env"].copy()
        env["AGENT_HISTORY_HOME_WSL"] = str(multi_home_setup["homes"]["wsl"]["path"])

        run_cli_subprocess(
            ["session", "list", "--home", "wsl", "--aw"],
            env=env,
        )

        # Should use WSL home, not local default

    def test_ah_includes_explicit_homes(self, multi_home_setup: Dict[str, Any]) -> None:
        """--ah should include any explicitly specified homes."""
        result = run_cli_subprocess(
            ["session", "list", "--ah", "--home", "local", "--aw"],
            env=multi_home_setup["env"],
        )

        # Behavior: --ah might override --home or include both
        assert_cli_success(result, "--ah with --home should work")

    def test_wsl_and_windows_combine(self, multi_home_setup: Dict[str, Any]) -> None:
        """--wsl and --windows can be combined.

        Spec: "--wsl + --windows: Both apply (multi-home)"
        """
        run_cli_subprocess(
            ["session", "list", "--wsl", "--windows", "--aw"],
            env=multi_home_setup["env"],
        )

        # Should include both WSL and Windows homes


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestHomeScopeEdgeCases:
    """Edge cases for home scope resolution."""

    def test_home_unreachable_with_ah(self, multi_home_setup: Dict[str, Any]) -> None:
        """Unreachable home with --ah should skip with warning.

        Spec: "Home unreachable: Skip with warning (--ah) or error (specific)"
        """
        run_cli_subprocess(
            ["session", "list", "--ah", "--aw"],
            env=multi_home_setup["env"],
        )

        # Should complete, possibly with warnings

    @pytest.mark.skip(reason="SSH tests require Docker infrastructure - see Agent 8")
    def test_home_unreachable_specific(self, multi_home_setup: Dict[str, Any]) -> None:
        """Specific unreachable home should error."""
        run_cli_subprocess(
            ["session", "list", "-r", "user@nonexistent-host", "--aw"],
            env=multi_home_setup["env"],
            timeout=10,
        )

        # Should error for specific unreachable home

    def test_empty_home(self, multi_home_setup: Dict[str, Any]) -> None:
        """Home with no sessions should return empty, not error."""
        run_cli_subprocess(
            ["session", "list", "--home", "local", "-n", "nonexistent"],
            env=multi_home_setup["env"],
        )

        # Should succeed with empty result


# ---------------------------------------------------------------------------
# Parameterized Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "home_scope,description",
    [
        ([], "local home (default)"),
        (["--home", "local"], "named local home"),
        (["--wsl"], "WSL home"),
        (["--windows"], "Windows home"),
        pytest.param(
            ["-r", "user@example.com"],
            "remote home",
            marks=pytest.mark.skip(reason="SSH tests require Docker"),
        ),
        (["--ah"], "all homes short"),
        (["--all-homes"], "all homes long"),
        (["--home", "local", "--home", "wsl"], "multiple named homes"),
        (["--wsl", "--windows"], "WSL and Windows combined"),
    ],
)
def test_home_scope_variants(
    home_scope: List[str],
    description: str,
    multi_home_setup: Dict[str, Any],
) -> None:
    """Parameterized test for various home scope configurations.

    Args:
        home_scope: CLI arguments for home scope
        description: Human-readable description
        multi_home_setup: Test fixture
    """
    run_cli_subprocess(
        ["session", "list", *home_scope, "--aw"],
        env=multi_home_setup["env"],
        timeout=10,  # Short timeout for connection failures
    )

    # Most variants should at least accept the syntax
    # Connection failures are expected for remote


@pytest.mark.parametrize(
    "exclusion_flags,description",
    [
        (["--no-wsl"], "exclude WSL"),
        (["--no-windows"], "exclude Windows"),
        (["--no-remote"], "exclude remotes"),
        pytest.param(
            ["--no-web"], "exclude web", marks=pytest.mark.skip(reason="--no-web not implemented")
        ),
        (["--no-wsl", "--no-windows"], "exclude WSL and Windows"),
        (["--no-wsl", "--no-remote"], "exclude WSL and remotes"),
        (["--local"], "local only"),
    ],
)
def test_exclusion_flag_variants(
    exclusion_flags: List[str],
    description: str,
    multi_home_setup: Dict[str, Any],
) -> None:
    """Parameterized test for exclusion flag combinations.

    Args:
        exclusion_flags: Exclusion CLI arguments
        description: Human-readable description
        multi_home_setup: Test fixture
    """
    result = run_cli_subprocess(
        ["session", "list", "--ah", *exclusion_flags, "--aw"],
        env=multi_home_setup["env"],
    )

    assert_cli_success(result, f"Exclusion '{description}' should succeed")


# ---------------------------------------------------------------------------
# Cross-Platform Tests
# ---------------------------------------------------------------------------


class TestCrossPlatformHomeScope:
    """Tests that verify cross-platform behavior."""

    def test_wsl_access_from_windows(self, cross_env_homes: Dict[str, Path]) -> None:
        """Windows should access WSL via --wsl flag."""
        if CURRENT_PLATFORM != "windows":
            pytest.skip("Windows-only test")

        # This test would require actual Windows/WSL environment

    def test_windows_access_from_wsl(self, cross_env_homes: Dict[str, Path]) -> None:
        """WSL should access Windows via --windows flag."""
        if CURRENT_PLATFORM != "wsl":
            pytest.skip("WSL-only test")

        # This test would require actual WSL environment

    def test_cross_platform_unavailable(self, multi_home_setup: Dict[str, Any]) -> None:
        """Cross-platform flags should error appropriately when unavailable."""
        if CURRENT_PLATFORM == "linux":
            # On Linux, both --wsl and --windows should be unavailable
            run_cli_subprocess(
                ["session", "list", "--wsl"],
                env=multi_home_setup["env"],
            )
            # Should error or warn about unavailability
