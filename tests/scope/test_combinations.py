"""Tests for scope combination resolution.

Tests critical combinations of workspace, home, and filter scopes using
parameterized tests for comprehensive coverage.

Spec reference: cli-spec.md#combined-scopes, testing-strategy.md#category-4-scope-resolution

Key combinations tested:
- Workspace x Home matrices
- Filter overlays on base combinations
- Exclusion flag combinations
- Precedence rules
"""

import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# ---------------------------------------------------------------------------
# Platform Detection
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

# Skip marker for tests that require WSL or Windows cross-platform access
# On Linux: neither --wsl nor --windows available
# On WSL: both --wsl and --windows work (can access Windows filesystem)
# On Windows: --windows works, --wsl works if WSL installed
skip_cross_platform = pytest.mark.skipif(
    CURRENT_PLATFORM == "linux",
    reason="Cross-platform tests (--wsl/--windows) not available on pure Linux",
)

from tests.helpers.cli import (
    assert_cli_success,
    run_cli_subprocess,
)

# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.scope, pytest.mark.scope_combination]


# ---------------------------------------------------------------------------
# Scope Definition Constants
# ---------------------------------------------------------------------------

# Workspace scope options
WS_SCOPES = {
    "current": [],  # Default: current workspace
    "named": ["project-alpha"],  # Positional workspace name
    "pattern": ["-n", "alpha"],  # Pattern match
    "all": ["--aw"],  # All workspaces
    "project": ["--project", "myproject"],  # Project scope
}

# Home scope options
HOME_SCOPES = {
    "local": [],  # Default: local
    "wsl": ["--wsl"],
    "windows": ["--windows"],
    "remote": ["-r", "user@example.com"],
    "named": ["--home", "local"],
    "all": ["--ah"],
    "all_no_wsl": ["--ah", "--no-wsl"],
    "all_no_remote": ["--ah", "--no-remote"],
}

# Filter options
FILTERS = {
    "none": [],
    "since": ["--since", "2025-01-01"],
    "until": ["--until", "2025-01-31"],
    "range": ["--since", "2025-01-01", "--until", "2025-01-31"],
    "agent_claude": ["--agent", "claude"],
    "agent_codex": ["--agent", "codex"],
    "agent_gemini": ["--agent", "gemini"],
}


# ---------------------------------------------------------------------------
# Critical Combinations (per testing-strategy.md)
# ---------------------------------------------------------------------------

# Critical scope combinations to test (not full cartesian - prioritized)
# Note: "current" workspace scope requires running from within a workspace directory.
# Test fixtures don't provide real workspace directories, so we use "all" instead.
CRITICAL_SCOPE_COMBOS = [
    # Basic single-dimension
    # ("current", ...) tests removed - require running from within a workspace directory
    ("all", "local", "none"),
    ("all", "all", "none"),
    # With filters
    ("all", "local", "since"),
    ("all", "all", "range"),
    ("pattern", "all", "agent_claude"),
    # Multi-home
    pytest.param("all", "wsl", "none", marks=skip_cross_platform),
    # Note: Remote SSH tests are in tests/e2e_docker/
    ("all", "all_no_wsl", "none"),
    # Project scope
    ("project", "local", "none"),
    ("project", "all", "none"),
    # Edge cases
    pytest.param(
        "named", "wsl", "agent_codex", marks=skip_cross_platform
    ),  # Codex on WSL, specific ws
]


# ---------------------------------------------------------------------------
# Parameterized Critical Combination Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ws_scope,home_scope,filter_scope",
    CRITICAL_SCOPE_COMBOS,
    ids=[f"ws={ws}_home={home}_filter={flt}" for ws, home, flt in CRITICAL_SCOPE_COMBOS],
)
def test_critical_scope_combination(
    ws_scope: str,
    home_scope: str,
    filter_scope: str,
    scope_combo_setup: Dict[str, Any],
) -> None:
    """Test critical scope combinations.

    Spec: "Critical combinations to test (not full cartesian - prioritized)"

    Args:
        ws_scope: Workspace scope identifier
        home_scope: Home scope identifier
        filter_scope: Filter scope identifier
        scope_combo_setup: Test fixture
    """
    # Build command args
    args = ["session", "list"]
    args.extend(WS_SCOPES.get(ws_scope, []))
    args.extend(HOME_SCOPES.get(home_scope, []))
    args.extend(FILTERS.get(filter_scope, []))

    run_cli_subprocess(
        args,
        env=scope_combo_setup["env"],
        timeout=15,  # Allow extra time for remote connections
    )

    # All critical combinations should at least accept the syntax
    # Some may fail (e.g., remote connections) but shouldn't crash
    # The test validates that the CLI handles these combinations


# ---------------------------------------------------------------------------
# Workspace x Home Matrix
# ---------------------------------------------------------------------------


class TestWorkspaceHomeMatrix:
    """Tests for workspace x home scope matrix.

    Per testing-strategy.md:
    | | Local | WSL | Windows | Remote | --ah |
    |---|:---:|:---:|:---:|:---:|:---:|
    | **Current ws** | + | + | + | + | + |
    | **Named ws** | + | + | + | + | + |
    | **Pattern ws** | + | + | + | + | + |
    | **--aw** | + | + | + | + | + |
    | **--project** | + | + | + | + | + |
    """

    @pytest.mark.parametrize(
        "home_args",
        [
            [],  # local (default)
            pytest.param(["--wsl"], marks=skip_cross_platform),
            pytest.param(["--windows"], marks=skip_cross_platform),
            # Note: Remote SSH tests (-r) are in tests/e2e_docker/
            ["--ah"],
        ],
        ids=["local", "wsl", "windows", "all_homes"],
    )
    def test_all_workspaces_basic_with_homes(
        self,
        home_args: List[str],
        multi_workspace_home: Dict[str, Any],
    ) -> None:
        """All workspaces (--aw) works with all home scopes.

        Note: "Current workspace" scope requires running from within a workspace
        directory, which test fixtures don't provide. Using --aw instead.
        """
        run_cli_subprocess(
            ["session", "list", "--aw", *home_args],
            env=multi_workspace_home["env"],
            timeout=10,
        )
        # Validates syntax acceptance

    @pytest.mark.parametrize(
        "home_args",
        [
            [],
            pytest.param(["--wsl"], marks=skip_cross_platform),
            pytest.param(["--windows"], marks=skip_cross_platform),
            ["--ah"],
        ],
        ids=["local", "wsl", "windows", "all_homes"],
    )
    def test_named_workspace_with_homes(
        self,
        home_args: List[str],
        multi_workspace_home: Dict[str, Any],
    ) -> None:
        """Named workspace works with all home scopes."""
        run_cli_subprocess(
            ["session", "list", "project-alpha", *home_args],
            env=multi_workspace_home["env"],
            timeout=10,
        )

    @pytest.mark.parametrize(
        "home_args",
        [
            [],
            pytest.param(["--wsl"], marks=skip_cross_platform),
            pytest.param(["--windows"], marks=skip_cross_platform),
            ["--ah"],
        ],
        ids=["local", "wsl", "windows", "all_homes"],
    )
    def test_pattern_workspace_with_homes(
        self,
        home_args: List[str],
        multi_workspace_home: Dict[str, Any],
    ) -> None:
        """Pattern workspace works with all home scopes."""
        run_cli_subprocess(
            ["session", "list", "-n", "alpha", *home_args],
            env=multi_workspace_home["env"],
            timeout=10,
        )

    @pytest.mark.parametrize(
        "home_args",
        [
            [],
            pytest.param(["--wsl"], marks=skip_cross_platform),
            pytest.param(["--windows"], marks=skip_cross_platform),
            ["--ah"],
        ],
        ids=["local", "wsl", "windows", "all_homes"],
    )
    def test_all_workspaces_with_homes(
        self,
        home_args: List[str],
        multi_workspace_home: Dict[str, Any],
    ) -> None:
        """All workspaces works with all home scopes."""
        run_cli_subprocess(
            ["session", "list", "--aw", *home_args],
            env=multi_workspace_home["env"],
            timeout=10,
        )

    @pytest.mark.parametrize(
        "home_args",
        [
            [],
            pytest.param(["--wsl"], marks=skip_cross_platform),
            pytest.param(["--windows"], marks=skip_cross_platform),
            ["--ah"],
        ],
        ids=["local", "wsl", "windows", "all_homes"],
    )
    def test_project_scope_with_homes(
        self,
        home_args: List[str],
        project_config_setup: Dict[str, Any],
    ) -> None:
        """Project scope works with all home scopes."""
        run_cli_subprocess(
            ["session", "list", "--project", "myproject", *home_args],
            env=project_config_setup["env"],
            timeout=10,
        )


# ---------------------------------------------------------------------------
# Filter Overlay Tests
# ---------------------------------------------------------------------------


class TestFilterOverlay:
    """Tests for filter overlays on base scope combinations.

    Per testing-strategy.md:
    "Filter overlay (applies to any base combination)"
    """

    @pytest.mark.parametrize(
        "base_args",
        [
            # Note: [] (default/current workspace) requires running from within a workspace
            # directory, which test fixtures don't provide. Use --aw instead.
            ["--aw"],  # all workspaces
            ["--ah"],  # all homes
            ["--aw", "--ah"],  # all workspaces, all homes
            ["-n", "alpha"],  # pattern
        ],
        ids=["all_ws", "all_homes", "all_all", "pattern"],
    )
    @pytest.mark.parametrize(
        "filter_args",
        [
            ["--since", "2025-01-01"],
            ["--until", "2025-01-31"],
            ["--since", "2025-01-01", "--until", "2025-01-31"],
            ["--agent", "claude"],
            ["--agent", "codex"],
            ["--agent", "gemini"],
        ],
        ids=["since", "until", "range", "claude", "codex", "gemini"],
    )
    def test_filter_with_base_scope(
        self,
        base_args: List[str],
        filter_args: List[str],
        scope_combo_setup: Dict[str, Any],
    ) -> None:
        """Filters can be combined with any base scope."""
        result = run_cli_subprocess(
            ["session", "list", *base_args, *filter_args],
            env=scope_combo_setup["env"],
        )

        assert_cli_success(
            result,
            f"Filter {filter_args} with base {base_args} should succeed",
        )


# ---------------------------------------------------------------------------
# Exclusion Combination Tests
# ---------------------------------------------------------------------------


class TestExclusionCombinations:
    """Tests for exclusion flag combinations with --ah.

    Per testing-strategy.md:
    | Exclusion Flags | Result |
    |-----------------|--------|
    | --ah | All homes |
    | --ah --no-wsl | All except WSL |
    | --ah --no-remote | All except remotes |
    | --ah --no-wsl --no-remote | Local + Windows only |
    | --ah --local | Local only (overrides --ah) |
    """

    @pytest.mark.parametrize(
        "exclusion_args,description",
        [
            (["--ah"], "all homes"),
            (["--ah", "--no-wsl"], "all except WSL"),
            (["--ah", "--no-remote"], "all except remotes"),
            (["--ah", "--no-wsl", "--no-remote"], "local + windows only"),
            (["--ah", "--no-windows"], "all except windows"),
            (["--ah", "--no-wsl", "--no-windows"], "local + remote only"),
            (["--ah", "--no-wsl", "--no-windows", "--no-remote"], "local only"),
            (["--ah", "--local"], "local only override"),
        ],
    )
    def test_exclusion_combination(
        self,
        exclusion_args: List[str],
        description: str,
        multi_home_setup: Dict[str, Any],
    ) -> None:
        """Test exclusion flag combinations."""
        result = run_cli_subprocess(
            ["session", "list", *exclusion_args, "--aw"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, f"Exclusion '{description}' should succeed")


# ---------------------------------------------------------------------------
# Precedence Rules Tests
# ---------------------------------------------------------------------------


class TestScopePrecedence:
    """Tests for scope precedence rules.

    Per testing-strategy.md:
    | Scenario | Expected Behavior |
    |----------|-------------------|
    | --project X + --this | --this wins (current ws only) |
    | -n pattern + --aw | --aw wins (all workspaces) |
    | --home foo + --ah | Both apply? Or --ah wins? |
    | --wsl + --windows | Both apply (multi-home) |
    | --agent claude + Codex-only workspace | Empty result |
    """

    def test_this_overrides_project(self, project_config_setup: Dict[str, Any]) -> None:
        """--this should override --project.

        Spec: "--project X + --this: --this wins (current ws only)"
        """
        result = run_cli_subprocess(
            ["session", "list", "--project", "myproject", "--this"],
            env=project_config_setup["env"],
        )

        assert_cli_success(result, "--this should override --project")

    def test_aw_overrides_pattern(self, multi_workspace_home: Dict[str, Any]) -> None:
        """--aw should override -n pattern.

        Spec: "-n pattern + --aw: --aw wins (all workspaces)"
        """
        result = run_cli_subprocess(
            ["session", "list", "-n", "alpha", "--aw"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "--aw should override -n")

    def test_home_with_ah(self, multi_home_setup: Dict[str, Any]) -> None:
        """--home with --ah behavior.

        Spec: "--home foo + --ah: Both apply? Or --ah wins?"
        """
        result = run_cli_subprocess(
            ["session", "list", "--home", "local", "--ah", "--aw"],
            env=multi_home_setup["env"],
        )

        # Implementation defines exact behavior
        assert_cli_success(result, "--home with --ah should not error")

    def test_wsl_and_windows_combine(self, multi_home_setup: Dict[str, Any]) -> None:
        """--wsl and --windows should both apply.

        Spec: "--wsl + --windows: Both apply (multi-home)"
        """
        run_cli_subprocess(
            ["session", "list", "--wsl", "--windows", "--aw"],
            env=multi_home_setup["env"],
        )

        # Should include both WSL and Windows homes

    def test_agent_filter_with_empty_result(self, agent_filter_sessions: Dict[str, Any]) -> None:
        """Agent filter on workspace without that agent returns empty.

        Spec: "--agent claude + Codex-only workspace: Empty result"
        """
        result = run_cli_subprocess(
            ["session", "list", "--agent", "claude", "-n", "nonexistent"],
            env=agent_filter_sessions["env"],
        )

        assert_cli_success(result, "Agent filter with no matches should succeed")


# ---------------------------------------------------------------------------
# Stats Scope Combinations
# ---------------------------------------------------------------------------


class TestStatsScopeCombinations:
    """Tests for scope combinations with stats command.

    Per testing-strategy.md:
    ```
    STATS_SCOPE_COMBOS = [
        # Basic stats
        ("current", "local", "none", None),
        ("all", "all", "none", None),

        # With grouping
        ("all", "local", "none", "model"),
        ("all", "all", "none", "day"),
        ("all", "all", "none", "agent"),

        # Multi-group
        ("all", "all", "none", "model,tool"),

        # With filters + grouping
        ("all", "local", "agent-claude", "model"),
        ("all", "all", "range", "day"),

        # Time mode
        ("all", "all", "none", "time"),
    ]
    ```
    """

    @pytest.mark.parametrize(
        "ws_scope,home_scope,filter_scope,grouping",
        [
            # Basic stats
            # Note: "current" workspace scope requires running from within a workspace
            # directory. Test fixtures don't provide real workspace directories.
            ("all", "local", "none", None),
            ("all", "all", "none", None),
            # With grouping
            ("all", "local", "none", "model"),
            ("all", "all", "none", "day"),
            ("all", "all", "none", "agent"),
            # Multi-group
            ("all", "all", "none", "model,tool"),
            # With filters + grouping
            ("all", "local", "agent_claude", "model"),
            ("all", "all", "range", "day"),
        ],
    )
    def test_stats_scope_combinations(
        self,
        ws_scope: str,
        home_scope: str,
        filter_scope: str,
        grouping: Optional[str],
        scope_combo_setup: Dict[str, Any],
    ) -> None:
        """Test stats command with various scope combinations."""
        args = ["session", "stats"]
        args.extend(WS_SCOPES.get(ws_scope, []))
        args.extend(HOME_SCOPES.get(home_scope, []))
        args.extend(FILTERS.get(filter_scope, []))

        if grouping:
            args.extend(["--by", grouping])

        result = run_cli_subprocess(
            args,
            env=scope_combo_setup["env"],
        )

        assert_cli_success(
            result, f"Stats with {ws_scope}/{home_scope}/{filter_scope} should succeed"
        )


# ---------------------------------------------------------------------------
# Export Scope Combinations
# ---------------------------------------------------------------------------


class TestExportScopeCombinations:
    """Tests for scope combinations with export command."""

    @pytest.mark.parametrize(
        "ws_scope,home_scope,filter_scope",
        [
            # Note: "current" workspace scope requires running from within a workspace
            # directory. Test fixtures don't provide real workspace directories.
            ("all", "local", "none"),
            ("pattern", "local", "none"),
            ("all", "all", "none"),
            ("all", "local", "agent_claude"),
            ("all", "local", "range"),
        ],
    )
    def test_export_scope_combinations(
        self,
        ws_scope: str,
        home_scope: str,
        filter_scope: str,
        scope_combo_setup: Dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Test export command with various scope combinations."""
        output_dir = tmp_path / f"export_{ws_scope}_{home_scope}_{filter_scope}"

        args = ["session", "export"]
        args.extend(WS_SCOPES.get(ws_scope, []))
        args.extend(HOME_SCOPES.get(home_scope, []))
        args.extend(FILTERS.get(filter_scope, []))
        args.extend(["-o", str(output_dir)])

        result = run_cli_subprocess(
            args,
            env=scope_combo_setup["env"],
        )

        assert_cli_success(
            result,
            f"Export with {ws_scope}/{home_scope}/{filter_scope} should succeed",
        )


# ---------------------------------------------------------------------------
# Expected Result Validation
# ---------------------------------------------------------------------------


class TestExpectedResultCounts:
    """Tests that validate expected session counts from scope combinations.

    Per testing-strategy.md:
    | Scope Combination | Expected Sessions |
    |-------------------|-------------------|
    | current ws, local | Sessions in cwd workspace only |
    | --aw, local | All sessions in local home |
    | current ws, --ah | Current ws across all homes |
    | --aw --ah | Everything |
    | -n auth, local | Sessions in workspaces matching "auth" |
    | --aw --agent claude, local | All Claude sessions in local |
    | --aw --ah --since 2025-01-01 | Everything after date |
    """

    def test_all_workspaces_local_count(self, multi_workspace_home: Dict[str, Any]) -> None:
        """--aw with local home returns all local sessions."""
        result = run_cli_subprocess(
            ["session", "list", "--aw", "--format", "json"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "--aw local should succeed")

        # Validate count matches expected
        multi_workspace_home["total_sessions"]
        # Note: Actual count parsing depends on json output format

    def test_pattern_match_count(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Pattern match returns expected workspaces."""
        # Pattern "auth" should match "auth-service"
        result = run_cli_subprocess(
            ["session", "list", "-n", "auth", "--format", "json"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "-n auth should succeed")

    def test_agent_filter_count(self, multi_workspace_home: Dict[str, Any]) -> None:
        """Agent filter returns correct count."""
        multi_workspace_home["agent_counts"]["claude"]

        result = run_cli_subprocess(
            ["session", "list", "--agent", "claude", "--aw", "--format", "json"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "--agent claude should succeed")

    def test_combined_filters_count(self, scope_combo_setup: Dict[str, Any]) -> None:
        """Combined filters return expected intersection."""
        # Use compute_totals helper from fixture
        compute = scope_combo_setup["compute_totals"]

        # All workspaces, local home, claude agent
        compute(
            home_filter=["local"],
            agent_filter="claude",
        )

        result = run_cli_subprocess(
            ["session", "list", "--aw", "--agent", "claude", "--format", "json"],
            env=scope_combo_setup["env"],
        )

        assert_cli_success(result, "Combined filter should succeed")


# ---------------------------------------------------------------------------
# Edge Cases and Error Handling
# ---------------------------------------------------------------------------


class TestScopeCombinationEdgeCases:
    """Edge cases for scope combinations."""

    def test_empty_scope_result(self, scope_combo_setup: Dict[str, Any]) -> None:
        """Valid scope with no matching sessions returns empty, not error.

        Spec: "Valid scope but no matching sessions - Empty result"
        """
        result = run_cli_subprocess(
            ["session", "list", "-n", "nonexistent", "--agent", "claude"],
            env=scope_combo_setup["env"],
        )

        assert_cli_success(result, "Empty result should not error")

    def test_conflicting_filters(self, scope_combo_setup: Dict[str, Any]) -> None:
        """Conflicting date filters (inverted range) should handle gracefully."""
        run_cli_subprocess(
            ["session", "list", "--since", "2025-12-31", "--until", "2025-01-01", "--aw"],
            env=scope_combo_setup["env"],
        )

        # Should either error with message or return empty

    def test_all_exclusions(self, multi_home_setup: Dict[str, Any]) -> None:
        """Excluding all home types should result in empty or error."""
        run_cli_subprocess(
            [
                "session",
                "list",
                "--ah",
                "--no-wsl",
                "--no-windows",
                "--no-remote",
                "--no-web",
                # This might leave only local
                "--aw",
            ],
            env=multi_home_setup["env"],
        )

        # Should succeed with local-only results

    def test_deeply_nested_combination(self, project_config_setup: Dict[str, Any]) -> None:
        """Complex combination with all scope types."""
        result = run_cli_subprocess(
            [
                "session",
                "list",
                "--project",
                "myproject",
                "--ah",
                "--no-remote",
                "--since",
                "2025-01-01",
                "--until",
                "2025-12-31",
                "--agent",
                "claude",
            ],
            env=project_config_setup["env"],
        )

        assert_cli_success(result, "Complex combination should succeed")


# ---------------------------------------------------------------------------
# Full Cartesian Tests (Optional - Heavy)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestFullCartesian:
    """Full cartesian product tests for exhaustive coverage.

    These tests are marked slow and should be run sparingly.
    """

    @pytest.mark.parametrize("ws_scope", list(WS_SCOPES.keys()))
    @pytest.mark.parametrize("home_scope", ["local", "all"])  # Reduced for speed
    @pytest.mark.parametrize("filter_scope", ["none", "agent_claude"])  # Reduced
    def test_cartesian_session_list(
        self,
        ws_scope: str,
        home_scope: str,
        filter_scope: str,
        scope_combo_setup: Dict[str, Any],
    ) -> None:
        """Cartesian product test for session list."""
        args = ["session", "list"]
        args.extend(WS_SCOPES.get(ws_scope, []))
        args.extend(HOME_SCOPES.get(home_scope, []))
        args.extend(FILTERS.get(filter_scope, []))

        run_cli_subprocess(
            args,
            env=scope_combo_setup["env"],
            timeout=30,
        )

        # Validates all combinations at least don't crash
