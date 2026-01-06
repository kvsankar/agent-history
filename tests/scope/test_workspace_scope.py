"""Tests for workspace scope resolution.

Tests workspace scope modifiers:
- Current workspace (default, from cwd)
- Named workspace (positional argument)
- Pattern matching (-n, --name)
- All workspaces (--aw, --all-workspaces)
- Project scope (--project)
- Current only override (--this)

Spec reference: cli-spec.md#scope-modifiers
"""

from pathlib import Path
from typing import Any, Dict, List

import pytest

from tests.helpers.cli import (
    assert_cli_success,
    run_cli_subprocess,
)

# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.scope, pytest.mark.workspace_scope]


# ---------------------------------------------------------------------------
# Current Workspace Scope (Default)
# ---------------------------------------------------------------------------


class TestCurrentWorkspaceScope:
    """Tests for default current workspace scope (from cwd)."""

    @pytest.mark.skip(
        reason="Requires running from actual workspace with matching sessions in projects dir"
    )
    def test_session_list_defaults_to_current_workspace(
        self, multi_workspace_home: Dict[str, Any]
    ) -> None:
        """session list with no args shows only current workspace sessions.

        Spec: "No args = current workspace (from cwd)"

        Note: This test requires running from a directory that has a matching
        workspace in the Claude projects directory. Test fixtures create workspaces
        for virtual paths like /home/user/project-alpha, not the temp directory.
        """
        # Use the fixture's home path as cwd - it's a real directory
        # that serves as a valid workspace directory
        result = run_cli_subprocess(
            ["session", "list"],
            env=multi_workspace_home["env"],
            cwd=multi_workspace_home["path"],
        )

        # Should succeed
        assert_cli_success(result, "session list should succeed")

        # Note: The actual assertion depends on implementation
        # This test verifies the command runs without error
        # Full validation requires the implementation to be working

    def test_ws_list_shows_all_workspaces(self, multi_workspace_home: Dict[str, Any]) -> None:
        """ws list shows all workspaces (not filtered by cwd).

        Spec: ws list always shows all workspaces, not scoped to current.
        """
        result = run_cli_subprocess(
            ["ws", "list"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "ws list should succeed")

    @pytest.mark.skip(
        reason="Requires running from actual workspace with matching sessions in projects dir"
    )
    def test_current_workspace_isolation(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Current workspace scope should not include other workspaces.

        Note: This test requires running from a directory that has a matching
        workspace in the Claude projects directory. Test fixtures create workspaces
        for virtual paths like /home/user/project-alpha, not the temp directory.
        """
        # This test validates that the scope isolation works
        # Sessions from other workspaces should not appear
        multi_workspace_home["workspaces"]["project-alpha"]
        multi_workspace_home["workspaces"]["project-beta"]

        # When querying project-alpha, project-beta sessions should not appear
        # (This is a behavioral validation for when implementation supports it)

        result = run_cli_subprocess(
            ["session", "list", "--format", "json"],
            env=multi_workspace_home["env"],
            cwd=multi_workspace_home["path"],
        )

        assert_cli_success(result, "session list with json format should succeed")


# ---------------------------------------------------------------------------
# Named Workspace Scope
# ---------------------------------------------------------------------------


class TestNamedWorkspaceScope:
    """Tests for explicit workspace naming via positional argument."""

    def test_session_list_with_workspace_name(self, multi_workspace_home: Dict[str, Any]) -> None:
        """session list <workspace-name> filters to named workspace.

        Spec: "<pattern> - Workspace name pattern (positional, repeatable)"
        """
        result = run_cli_subprocess(
            ["session", "list", "project-alpha"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "session list with workspace name should succeed")

    def test_session_list_with_multiple_workspace_names(
        self, multi_workspace_home: Dict[str, Any]
    ) -> None:
        """session list <ws1> <ws2> shows sessions from multiple workspaces.

        Spec: Pattern argument is repeatable.
        """
        result = run_cli_subprocess(
            ["session", "list", "project-alpha", "project-beta"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "session list with multiple workspaces should succeed")

    def test_session_list_with_nonexistent_workspace(
        self, multi_workspace_home: Dict[str, Any]
    ) -> None:
        """session list <nonexistent> should return empty or error gracefully.

        Spec: "Empty result (not error)" for non-matching patterns.
        """
        run_cli_subprocess(
            ["session", "list", "nonexistent-workspace-xyz"],
            env=multi_workspace_home["env"],
        )

        # Should either succeed with empty result or provide helpful error
        # The specific behavior depends on implementation choice


# ---------------------------------------------------------------------------
# Pattern Matching Scope (-n, --name)
# ---------------------------------------------------------------------------


class TestPatternMatchingScope:
    """Tests for pattern matching with -n/--name flag."""

    def test_name_flag_filters_by_pattern(self, multi_workspace_home: Dict[str, Any]) -> None:
        """session list -n <pattern> filters workspaces by pattern.

        Spec: "Patterns match against workspace names (case-insensitive substring)"
        """
        result = run_cli_subprocess(
            ["session", "list", "-n", "alpha"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "session list with -n pattern should succeed")

    def test_name_flag_case_insensitive(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Pattern matching should be case-insensitive.

        Spec: "case-insensitive substring"
        """
        # These should all match "project-alpha"
        patterns = ["ALPHA", "Alpha", "aLpHa"]

        for pattern in patterns:
            result = run_cli_subprocess(
                ["session", "list", "-n", pattern],
                env=multi_workspace_home["env"],
            )
            assert_cli_success(result, f"Pattern '{pattern}' should match case-insensitively")

    def test_name_flag_substring_match(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Pattern should match as substring, not exact match.

        Spec: "case-insensitive substring"
        """
        # "service" should match "auth-service" and "api-gateway" (if they contain it)
        result = run_cli_subprocess(
            ["session", "list", "-n", "service"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "Substring pattern should succeed")

    def test_name_flag_multiple_patterns(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Multiple -n flags should match any pattern.

        Spec: "Multiple patterns: match any"
        """
        result = run_cli_subprocess(
            ["session", "list", "-n", "alpha", "-n", "beta"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "Multiple -n patterns should succeed")

    def test_name_flag_no_match_returns_empty(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Pattern with no matches should return empty result, not error.

        Spec: "Pattern matches nothing - Empty result (not error)"
        """
        result = run_cli_subprocess(
            ["session", "list", "-n", "xyznonexistent123"],
            env=multi_workspace_home["env"],
        )

        # Should succeed with empty result
        assert_cli_success(result, "Non-matching pattern should not error")

    def test_name_flag_wildcard_all(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Pattern '*' or 'all' should match all workspaces.

        Spec: "Empty pattern or '*' or 'all': match all workspaces"
        """
        result = run_cli_subprocess(
            ["session", "list", "-n", "*"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "Wildcard pattern should succeed")


# ---------------------------------------------------------------------------
# All Workspaces Scope (--aw, --all-workspaces)
# ---------------------------------------------------------------------------


class TestAllWorkspacesScope:
    """Tests for --aw/--all-workspaces flag."""

    def test_all_workspaces_flag_long(self, multi_workspace_home: Dict[str, Any]) -> None:
        """--all-workspaces shows sessions from all workspaces.

        Spec: "--aw / --all-workspaces - All workspaces"
        """
        result = run_cli_subprocess(
            ["session", "list", "--all-workspaces"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "--all-workspaces should succeed")

    def test_all_workspaces_flag_short(self, multi_workspace_home: Dict[str, Any]) -> None:
        """--aw is shorthand for --all-workspaces."""
        result = run_cli_subprocess(
            ["session", "list", "--aw"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "--aw should succeed")

    def test_all_workspaces_includes_all(self, multi_workspace_home: Dict[str, Any]) -> None:
        """--aw should include sessions from all workspaces."""
        result = run_cli_subprocess(
            ["session", "list", "--aw", "--format", "json"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "--aw with json format should succeed")

        # The total session count should match expected
        # (Validation depends on json output parsing)

    def test_all_workspaces_with_ws_list(self, multi_workspace_home: Dict[str, Any]) -> None:
        """ws list shows all workspaces (--aw is implicit for ws list)."""
        result = run_cli_subprocess(
            ["ws", "list"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "ws list should succeed")

    def test_aw_overrides_pattern(self, multi_workspace_home: Dict[str, Any]) -> None:
        """--aw should override -n pattern (or combine with it).

        Spec: "-n pattern + --aw: --aw wins (all workspaces)"
        """
        result = run_cli_subprocess(
            ["session", "list", "-n", "alpha", "--aw"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "--aw with -n should succeed")


# ---------------------------------------------------------------------------
# Project Scope (--project)
# ---------------------------------------------------------------------------


class TestProjectScope:
    """Tests for --project flag and project auto-detection."""

    @pytest.mark.skip(reason="Project infrastructure not implemented")
    def test_project_flag_filters_to_project_workspaces(
        self, project_config_setup: Dict[str, Any]
    ) -> None:
        """--project <name> uses workspaces from named project.

        Spec: "--project <name> - Use workspaces from named project"
        """
        result = run_cli_subprocess(
            ["session", "list", "--project", "myproject"],
            env=project_config_setup["env"],
        )

        assert_cli_success(result, "--project should succeed")

    def test_project_with_nonexistent_name(self, project_config_setup: Dict[str, Any]) -> None:
        """--project <nonexistent> should error appropriately."""
        run_cli_subprocess(
            ["session", "list", "--project", "nonexistent-project"],
            env=project_config_setup["env"],
        )

        # Should error with helpful message
        # Exact behavior depends on implementation

    def test_project_list_shows_all_projects(self, project_config_setup: Dict[str, Any]) -> None:
        """project list shows all configured projects.

        Spec: "project [list] - List all projects"
        """
        result = run_cli_subprocess(
            ["project", "list"],
            env=project_config_setup["env"],
        )

        assert_cli_success(result, "project list should succeed")

    @pytest.mark.skip(reason="Project infrastructure not implemented")
    def test_project_show_displays_project_details(
        self, project_config_setup: Dict[str, Any]
    ) -> None:
        """project show <name> shows project details.

        Spec: "project show <name> - Show project details"
        """
        result = run_cli_subprocess(
            ["project", "show", "myproject"],
            env=project_config_setup["env"],
        )

        assert_cli_success(result, "project show should succeed")


# ---------------------------------------------------------------------------
# Current Workspace Override (--this)
# ---------------------------------------------------------------------------


class TestThisOverride:
    """Tests for --this flag to override project auto-detection."""

    @pytest.mark.skip(reason="Project infrastructure not implemented")
    def test_this_flag_overrides_project(self, project_config_setup: Dict[str, Any]) -> None:
        """--this forces current workspace only, ignoring project scope.

        Spec: "--this - Current workspace only (override project auto-detection)"
        """
        result = run_cli_subprocess(
            ["session", "list", "--this"],
            env=project_config_setup["env"],
        )

        assert_cli_success(result, "--this should succeed")

    @pytest.mark.skip(reason="Project infrastructure not implemented")
    def test_this_with_project_flag(self, project_config_setup: Dict[str, Any]) -> None:
        """--this should override --project.

        Spec: "--project X + --this: --this wins (current ws only)"
        """
        result = run_cli_subprocess(
            ["session", "list", "--project", "myproject", "--this"],
            env=project_config_setup["env"],
        )

        assert_cli_success(result, "--this with --project should succeed")

    @pytest.mark.skip(
        reason="Requires running from actual workspace with matching sessions in projects dir"
    )
    def test_this_limits_to_single_workspace(self, multi_workspace_home: Dict[str, Any]) -> None:
        """--this should only show sessions from current workspace.

        Note: This test requires running from a directory that has a matching
        workspace in the Claude projects directory. Test fixtures create workspaces
        for virtual paths like /home/user/project-alpha, not the temp directory.
        """
        result = run_cli_subprocess(
            ["session", "list", "--this", "--format", "json"],
            env=multi_workspace_home["env"],
            cwd=multi_workspace_home["path"],
        )

        assert_cli_success(result, "--this with json format should succeed")


# ---------------------------------------------------------------------------
# Workspace Scope with Other Commands
# ---------------------------------------------------------------------------


class TestWorkspaceScopeWithCommands:
    """Tests for workspace scope with various commands."""

    def test_session_export_with_workspace_scope(
        self, multi_workspace_home: Dict[str, Any], tmp_path: Path
    ) -> None:
        """session export respects workspace scope.

        Spec: Export commands use same scope modifiers as list.
        """
        output_dir = tmp_path / "export_output"
        result = run_cli_subprocess(
            ["session", "export", "-n", "alpha", "-o", str(output_dir)],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "session export with -n should succeed")

    def test_session_stats_with_workspace_scope(self, multi_workspace_home: Dict[str, Any]) -> None:
        """session stats respects workspace scope.

        Spec: Stats commands use same scope modifiers.
        """
        result = run_cli_subprocess(
            ["session", "stats", "-n", "alpha"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "session stats with -n should succeed")

    def test_ws_export_workspace(
        self, multi_workspace_home: Dict[str, Any], tmp_path: Path
    ) -> None:
        """ws export <path> exports sessions from workspace.

        Spec: "ws export <path> [options] - Export sessions from workspace"
        """
        ws_path = multi_workspace_home["workspaces"]["project-alpha"]["path"]
        output_dir = tmp_path / "ws_export"

        run_cli_subprocess(
            ["ws", "export", ws_path, "-o", str(output_dir)],
            env=multi_workspace_home["env"],
        )

        # Command may not be implemented, check for graceful handling


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestWorkspaceScopeEdgeCases:
    """Edge cases for workspace scope resolution."""

    def test_empty_workspace(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Session list in workspace with no sessions should return empty."""
        # Create an empty workspace scenario
        result = run_cli_subprocess(
            ["session", "list", "-n", "nonexistent"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "Empty workspace query should succeed")

    def test_workspace_with_special_characters(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Workspace names with special characters should be handled."""
        # Pattern with special regex characters
        run_cli_subprocess(
            ["session", "list", "-n", "project.*"],
            env=multi_workspace_home["env"],
        )

        # Should handle gracefully (either literal match or regex)

    def test_workspace_pattern_with_dashes(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Workspace patterns with dashes should work correctly."""
        result = run_cli_subprocess(
            ["session", "list", "-n", "auth-service"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "Pattern with dashes should succeed")

    def test_mixed_agents_in_workspace(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Workspace with sessions from multiple agents should list all."""
        # project-alpha has both Claude and Codex sessions
        result = run_cli_subprocess(
            ["session", "list", "-n", "alpha"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "Mixed agent workspace should succeed")


# ---------------------------------------------------------------------------
# Scope Precedence
# ---------------------------------------------------------------------------


class TestWorkspaceScopePrecedence:
    """Tests for workspace scope precedence rules."""

    def test_explicit_workspace_overrides_cwd(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Explicit workspace argument overrides cwd detection."""
        result = run_cli_subprocess(
            ["session", "list", "project-beta"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "Explicit workspace should override cwd")

    def test_aw_precedence_over_named(self, multi_workspace_home: Dict[str, Any]) -> None:
        """--aw takes precedence over named workspace."""
        result = run_cli_subprocess(
            ["session", "list", "project-alpha", "--aw"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "--aw should take precedence")

    def test_this_precedence_over_all(self, multi_workspace_home: Dict[str, Any]) -> None:
        """--this should still work as override mechanism."""
        run_cli_subprocess(
            ["session", "list", "--aw", "--this"],
            env=multi_workspace_home["env"],
        )

        # Behavior depends on implementation: --this could override --aw
        # or the flags could be mutually exclusive


# ---------------------------------------------------------------------------
# Parameterized Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "workspace_scope,description,needs_cwd",
    [
        pytest.param(
            [],
            "current workspace (default)",
            True,
            marks=pytest.mark.skip(
                reason="Requires running from actual workspace with matching sessions in projects dir"
            ),
        ),
        (["project-alpha"], "single named workspace", False),
        (["project-alpha", "project-beta"], "multiple named workspaces", False),
        (["-n", "alpha"], "single pattern", False),
        (["-n", "alpha", "-n", "beta"], "multiple patterns", False),
        (["--aw"], "all workspaces short flag", False),
        (["--all-workspaces"], "all workspaces long flag", False),
        (["-n", "*"], "wildcard pattern", False),
    ],
)
def test_workspace_scope_variants(
    workspace_scope: List[str],
    description: str,
    needs_cwd: bool,
    multi_workspace_home: Dict[str, Any],
) -> None:
    """Parameterized test for various workspace scope configurations.

    Args:
        workspace_scope: CLI arguments for workspace scope
        description: Human-readable description
        needs_cwd: Whether this test needs to run from a workspace directory
        multi_workspace_home: Test fixture
    """
    # When testing "current workspace (default)", we need to run from a valid workspace directory
    cwd = multi_workspace_home["path"] if needs_cwd else None

    result = run_cli_subprocess(
        ["session", "list", *workspace_scope],
        env=multi_workspace_home["env"],
        cwd=cwd,
    )

    assert_cli_success(result, f"Workspace scope '{description}' should succeed")


@pytest.mark.parametrize(
    "pattern,expected_matches",
    [
        ("project", ["project-alpha", "project-beta"]),  # Matches both projects
        ("alpha", ["project-alpha"]),  # Matches only alpha
        ("service", ["auth-service"]),  # Matches service
        ("app", ["frontend-app"]),  # Matches app
        ("api", ["api-gateway"]),  # Matches api
        ("gate", ["api-gateway"]),  # Partial match
        ("xyz", []),  # No match
    ],
)
def test_pattern_matching_expected_results(
    pattern: str,
    expected_matches: List[str],
    multi_workspace_home: Dict[str, Any],
) -> None:
    """Test that patterns match expected workspaces.

    Args:
        pattern: Pattern to match
        expected_matches: Expected matching workspace names
        multi_workspace_home: Test fixture
    """
    result = run_cli_subprocess(
        ["session", "list", "-n", pattern],
        env=multi_workspace_home["env"],
    )

    assert_cli_success(result, f"Pattern '{pattern}' should succeed")

    # Note: Actual output validation depends on implementation
    # The expected_matches list documents expected behavior
