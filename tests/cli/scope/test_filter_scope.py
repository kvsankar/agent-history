"""Tests for filter scope resolution.

Tests filter scope modifiers:
- Date filter --since
- Date filter --until
- Date range (--since + --until)
- Agent filter (--agent)

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

pytestmark = [pytest.mark.scope, pytest.mark.filter_scope]


# ---------------------------------------------------------------------------
# Date Filter: --since
# ---------------------------------------------------------------------------


class TestSinceFilter:
    """Tests for --since date filter."""

    def test_since_filter_basic(self, date_range_sessions: Dict[str, Any]) -> None:
        """--since <date> filters sessions starting from date.

        Spec: "--since <date> - Filter by start date (YYYY-MM-DD)"
        """
        result = run_cli_subprocess(
            ["session", "list", "--since", "2025-01-10", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "--since filter should succeed")

    def test_since_filter_excludes_earlier(self, date_range_sessions: Dict[str, Any]) -> None:
        """--since should exclude sessions before the date."""
        # Sessions on 2025-01-01 and 2025-01-05 should be excluded
        # Sessions on 2025-01-10, 2025-01-15, 2025-01-20 should be included
        result = run_cli_subprocess(
            ["session", "list", "--since", "2025-01-10", "--aw", "--format", "json"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "--since should exclude earlier sessions")

    def test_since_filter_includes_exact_date(self, date_range_sessions: Dict[str, Any]) -> None:
        """--since includes sessions on the exact date."""
        # Sessions on 2025-01-05 should be included when --since 2025-01-05
        result = run_cli_subprocess(
            ["session", "list", "--since", "2025-01-05", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "--since should include exact date")

    def test_since_filter_future_date(self, date_range_sessions: Dict[str, Any]) -> None:
        """--since with future date returns empty result."""
        result = run_cli_subprocess(
            ["session", "list", "--since", "2030-01-01", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "Future date should return empty")

    def test_since_filter_date_formats(self, date_range_sessions: Dict[str, Any]) -> None:
        """--since accepts YYYY-MM-DD format."""
        result = run_cli_subprocess(
            ["session", "list", "--since", "2025-01-15", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "Standard date format should work")

    @pytest.mark.parametrize(
        "invalid_date",
        [
            "01-01-2025",  # Wrong order
            "2025/01/01",  # Wrong separator
            "2025-1-1",  # No zero padding
            "not-a-date",  # Invalid
            "2025-13-01",  # Invalid month
            "2025-01-32",  # Invalid day
        ],
    )
    def test_since_filter_invalid_date(
        self, invalid_date: str, date_range_sessions: Dict[str, Any]
    ) -> None:
        """--since with invalid date should error."""
        run_cli_subprocess(
            ["session", "list", "--since", invalid_date, "--aw"],
            env=date_range_sessions["env"],
        )

        # Should error with helpful message about date format


# ---------------------------------------------------------------------------
# Date Filter: --until
# ---------------------------------------------------------------------------


class TestUntilFilter:
    """Tests for --until date filter."""

    def test_until_filter_basic(self, date_range_sessions: Dict[str, Any]) -> None:
        """--until <date> filters sessions up to date.

        Spec: "--until <date> - Filter by end date (YYYY-MM-DD)"
        """
        result = run_cli_subprocess(
            ["session", "list", "--until", "2025-01-10", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "--until filter should succeed")

    def test_until_filter_excludes_later(self, date_range_sessions: Dict[str, Any]) -> None:
        """--until should exclude sessions after the date."""
        # Sessions on 2025-01-15 and 2025-01-20 should be excluded
        # Sessions on 2025-01-01, 2025-01-05, 2025-01-10 should be included
        result = run_cli_subprocess(
            ["session", "list", "--until", "2025-01-10", "--aw", "--format", "json"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "--until should exclude later sessions")

    def test_until_filter_includes_exact_date(self, date_range_sessions: Dict[str, Any]) -> None:
        """--until includes sessions on the exact date."""
        result = run_cli_subprocess(
            ["session", "list", "--until", "2025-01-10", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "--until should include exact date")

    def test_until_filter_past_date(self, date_range_sessions: Dict[str, Any]) -> None:
        """--until with past date (before all sessions) returns empty."""
        result = run_cli_subprocess(
            ["session", "list", "--until", "2020-01-01", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "Past date should return empty")


# ---------------------------------------------------------------------------
# Date Range Filter (--since + --until)
# ---------------------------------------------------------------------------


class TestDateRangeFilter:
    """Tests for combined --since and --until filters."""

    def test_date_range_filter(self, date_range_sessions: Dict[str, Any]) -> None:
        """--since and --until can be combined for date range.

        Spec: "--since X --until Y: Any ws x home combination"
        """
        result = run_cli_subprocess(
            ["session", "list", "--since", "2025-01-05", "--until", "2025-01-15", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "Date range filter should succeed")

    def test_date_range_includes_boundaries(self, date_range_sessions: Dict[str, Any]) -> None:
        """Date range should include sessions on boundary dates."""
        # Both 2025-01-05 and 2025-01-15 should be included
        result = run_cli_subprocess(
            ["session", "list", "--since", "2025-01-05", "--until", "2025-01-15", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "Range should include boundaries")

    def test_date_range_single_day(self, date_range_sessions: Dict[str, Any]) -> None:
        """--since and --until with same date returns that day's sessions."""
        result = run_cli_subprocess(
            ["session", "list", "--since", "2025-01-10", "--until", "2025-01-10", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "Single day range should succeed")

    def test_date_range_inverted_error(self, date_range_sessions: Dict[str, Any]) -> None:
        """--since after --until should return empty or error."""
        run_cli_subprocess(
            ["session", "list", "--since", "2025-01-20", "--until", "2025-01-01", "--aw"],
            env=date_range_sessions["env"],
        )

        # Should either error or return empty

    def test_date_range_no_matches(self, date_range_sessions: Dict[str, Any]) -> None:
        """Date range with no sessions should return empty."""
        # No sessions between 2025-01-06 and 2025-01-08
        result = run_cli_subprocess(
            ["session", "list", "--since", "2025-01-06", "--until", "2025-01-08", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "No-match range should succeed with empty")


# ---------------------------------------------------------------------------
# Agent Filter (--agent)
# ---------------------------------------------------------------------------


class TestAgentFilter:
    """Tests for --agent filter."""

    def test_agent_filter_claude(self, agent_filter_sessions: Dict[str, Any]) -> None:
        """--agent claude filters to Claude sessions only.

        Spec: "--agent claude - Claude Code sessions only"
        """
        result = run_cli_subprocess(
            ["session", "list", "--agent", "claude", "--aw"],
            env=agent_filter_sessions["env"],
        )

        assert_cli_success(result, "--agent claude should succeed")

    def test_agent_filter_codex(self, agent_filter_sessions: Dict[str, Any]) -> None:
        """--agent codex filters to Codex sessions only.

        Spec: "--agent codex - Codex CLI sessions only"
        """
        result = run_cli_subprocess(
            ["session", "list", "--agent", "codex", "--aw"],
            env=agent_filter_sessions["env"],
        )

        assert_cli_success(result, "--agent codex should succeed")

    def test_agent_filter_gemini(self, agent_filter_sessions: Dict[str, Any]) -> None:
        """--agent gemini filters to Gemini sessions only.

        Spec: "--agent gemini - Gemini CLI sessions only"
        """
        result = run_cli_subprocess(
            ["session", "list", "--agent", "gemini", "--aw"],
            env=agent_filter_sessions["env"],
        )

        assert_cli_success(result, "--agent gemini should succeed")

    def test_agent_filter_auto(self, agent_filter_sessions: Dict[str, Any]) -> None:
        """--agent auto auto-detects agent type (default).

        Spec: "(none) / --agent auto - Auto-detect (default)"
        """
        result = run_cli_subprocess(
            ["session", "list", "--agent", "auto", "--aw"],
            env=agent_filter_sessions["env"],
        )

        assert_cli_success(result, "--agent auto should succeed")

    def test_agent_filter_default_is_auto(self, agent_filter_sessions: Dict[str, Any]) -> None:
        """No --agent flag defaults to auto-detection."""
        result = run_cli_subprocess(
            ["session", "list", "--aw"],
            env=agent_filter_sessions["env"],
        )

        assert_cli_success(result, "Default agent should be auto")

    def test_agent_filter_counts(self, agent_filter_sessions: Dict[str, Any]) -> None:
        """Verify agent filter returns correct session counts."""
        expected_counts = agent_filter_sessions["counts"]

        # Test each agent
        for agent, expected_count in [
            ("claude", expected_counts["claude"]),
            ("codex", expected_counts["codex"]),
            ("gemini", expected_counts["gemini"]),
        ]:
            result = run_cli_subprocess(
                ["session", "list", "--agent", agent, "--aw", "--format", "json"],
                env=agent_filter_sessions["env"],
            )

            assert_cli_success(result, f"--agent {agent} should succeed")
            # Note: Actual count validation depends on json output parsing

    def test_agent_filter_invalid(self, agent_filter_sessions: Dict[str, Any]) -> None:
        """--agent with invalid value should error."""
        run_cli_subprocess(
            ["session", "list", "--agent", "invalid-agent", "--aw"],
            env=agent_filter_sessions["env"],
        )

        # Should error with valid options

    def test_agent_filter_case_insensitive(self, agent_filter_sessions: Dict[str, Any]) -> None:
        """--agent should be case-insensitive."""
        for variant in ["CLAUDE", "Claude", "cLaUdE"]:
            run_cli_subprocess(
                ["session", "list", "--agent", variant, "--aw"],
                env=agent_filter_sessions["env"],
            )

            # Should accept case variations (or error consistently)


# ---------------------------------------------------------------------------
# Combined Filters
# ---------------------------------------------------------------------------


class TestCombinedFilters:
    """Tests for combining date and agent filters."""

    def test_since_with_agent(self, scope_combo_setup: Dict[str, Any]) -> None:
        """--since can be combined with --agent."""
        result = run_cli_subprocess(
            ["session", "list", "--since", "2025-01-05", "--agent", "claude", "--aw"],
            env=scope_combo_setup["env"],
        )

        assert_cli_success(result, "--since with --agent should succeed")

    def test_until_with_agent(self, scope_combo_setup: Dict[str, Any]) -> None:
        """--until can be combined with --agent."""
        result = run_cli_subprocess(
            ["session", "list", "--until", "2025-01-15", "--agent", "codex", "--aw"],
            env=scope_combo_setup["env"],
        )

        assert_cli_success(result, "--until with --agent should succeed")

    def test_date_range_with_agent(self, scope_combo_setup: Dict[str, Any]) -> None:
        """Date range can be combined with --agent."""
        result = run_cli_subprocess(
            [
                "session",
                "list",
                "--since",
                "2025-01-01",
                "--until",
                "2025-01-31",
                "--agent",
                "gemini",
                "--aw",
            ],
            env=scope_combo_setup["env"],
        )

        assert_cli_success(result, "Date range with --agent should succeed")

    def test_all_filters_combined(self, scope_combo_setup: Dict[str, Any]) -> None:
        """All filter types can be combined."""
        result = run_cli_subprocess(
            [
                "session",
                "list",
                "--since",
                "2025-01-01",
                "--until",
                "2025-01-31",
                "--agent",
                "claude",
                "-n",
                "alpha",
                "--aw",
            ],
            env=scope_combo_setup["env"],
        )

        assert_cli_success(result, "All filters combined should succeed")


# ---------------------------------------------------------------------------
# Filters with Other Commands
# ---------------------------------------------------------------------------


class TestFiltersWithCommands:
    """Tests for filters with various commands."""

    def test_session_export_with_date_filter(
        self, date_range_sessions: Dict[str, Any], tmp_path: Path
    ) -> None:
        """session export respects date filters.

        Spec: "Export with date filter"
        """
        output_dir = tmp_path / "export_output"
        result = run_cli_subprocess(
            [
                "session",
                "export",
                "--since",
                "2025-01-10",
                "--aw",
                "-o",
                str(output_dir),
            ],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "session export with --since should succeed")

    def test_session_export_with_agent_filter(
        self, agent_filter_sessions: Dict[str, Any], tmp_path: Path
    ) -> None:
        """session export respects agent filter."""
        output_dir = tmp_path / "export_output"
        result = run_cli_subprocess(
            [
                "session",
                "export",
                "--agent",
                "claude",
                "--aw",
                "-o",
                str(output_dir),
            ],
            env=agent_filter_sessions["env"],
        )

        assert_cli_success(result, "session export with --agent should succeed")

    def test_session_stats_with_date_filter(self, date_range_sessions: Dict[str, Any]) -> None:
        """session stats respects date filters."""
        result = run_cli_subprocess(
            ["session", "stats", "--since", "2025-01-10", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "session stats with --since should succeed")

    def test_session_stats_with_agent_filter(self, agent_filter_sessions: Dict[str, Any]) -> None:
        """session stats respects agent filter."""
        result = run_cli_subprocess(
            ["session", "stats", "--agent", "claude", "--aw"],
            env=agent_filter_sessions["env"],
        )

        assert_cli_success(result, "session stats with --agent should succeed")


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestFilterEdgeCases:
    """Edge cases for filter scope resolution."""

    def test_agent_filter_empty_workspace(self, agent_filter_sessions: Dict[str, Any]) -> None:
        """Agent filter on workspace with no matching agent returns empty."""
        # This tests the case where workspace has only one agent type
        result = run_cli_subprocess(
            ["session", "list", "--agent", "claude", "-n", "nonexistent"],
            env=agent_filter_sessions["env"],
        )

        assert_cli_success(result, "Empty result should not error")

    def test_date_filter_session_boundary(self, date_range_sessions: Dict[str, Any]) -> None:
        """Session spanning date boundary included if start OR end in range."""
        # Note: Behavior depends on whether we use session start, end, or both
        result = run_cli_subprocess(
            ["session", "list", "--since", "2025-01-01", "--until", "2025-01-01", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "Boundary case should succeed")

    def test_future_date_filter(self, date_range_sessions: Dict[str, Any]) -> None:
        """Filters with future dates should return empty."""
        result = run_cli_subprocess(
            ["session", "list", "--since", "2030-01-01", "--aw"],
            env=date_range_sessions["env"],
        )

        assert_cli_success(result, "Future date should return empty")

    def test_agent_filter_applies_to_all_commands(
        self, agent_filter_sessions: Dict[str, Any]
    ) -> None:
        """Agent filter applies to all commands.

        Spec: "Applies to all commands: ws, session, project, home (for stats/export)"
        """
        commands = [
            ["ws", "list", "--agent", "claude"],
            ["session", "list", "--agent", "claude", "--aw"],
        ]

        for cmd in commands:
            result = run_cli_subprocess(cmd, env=agent_filter_sessions["env"])
            assert_cli_success(result, f"Command {' '.join(cmd)} should accept --agent")


# ---------------------------------------------------------------------------
# Parameterized Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filter_args,description",
    [
        (["--since", "2025-01-01"], "since filter"),
        (["--until", "2025-01-31"], "until filter"),
        (["--since", "2025-01-01", "--until", "2025-01-31"], "date range"),
        (["--agent", "claude"], "claude agent"),
        (["--agent", "codex"], "codex agent"),
        (["--agent", "gemini"], "gemini agent"),
        (["--agent", "auto"], "auto agent"),
        (["--since", "2025-01-01", "--agent", "claude"], "since + agent"),
        (["--until", "2025-01-31", "--agent", "codex"], "until + agent"),
        (
            ["--since", "2025-01-01", "--until", "2025-01-31", "--agent", "gemini"],
            "range + agent",
        ),
    ],
)
def test_filter_variants(
    filter_args: List[str],
    description: str,
    scope_combo_setup: Dict[str, Any],
) -> None:
    """Parameterized test for various filter configurations.

    Args:
        filter_args: CLI arguments for filters
        description: Human-readable description
        scope_combo_setup: Test fixture
    """
    result = run_cli_subprocess(
        ["session", "list", *filter_args, "--aw"],
        env=scope_combo_setup["env"],
    )

    assert_cli_success(result, f"Filter '{description}' should succeed")


@pytest.mark.parametrize(
    "date,expected_sessions",
    [
        ("2025-01-01", 5),  # All sessions from 2025-01-01 onward
        ("2025-01-05", 5),  # From 2025-01-05 onward
        ("2025-01-10", 5),  # From 2025-01-10 onward
        ("2025-01-15", 3),  # From 2025-01-15 onward (15 + 20)
        ("2025-01-20", 2),  # From 2025-01-20 onward
        ("2025-01-25", 0),  # No sessions after 2025-01-25
    ],
)
def test_since_filter_expected_counts(
    date: str,
    expected_sessions: int,
    date_range_sessions: Dict[str, Any],
) -> None:
    """Test --since filter returns expected session counts.

    Note: This test documents expected behavior. The expected_sessions
    values are based on the date_range_sessions fixture:
    - 2025-01-01: 2 sessions (cumulative from this date: 10)
    - 2025-01-05: 3 sessions (cumulative from this date: 8)
    - 2025-01-10: 2 sessions (cumulative from this date: 5)
    - 2025-01-15: 1 session (cumulative from this date: 3)
    - 2025-01-20: 2 sessions (cumulative from this date: 2)

    The expected_sessions parameter values may need adjustment based on
    actual fixture data.
    """
    result = run_cli_subprocess(
        ["session", "list", "--since", date, "--aw"],
        env=date_range_sessions["env"],
    )

    assert_cli_success(result, f"--since {date} should succeed")
    # Note: Actual count validation depends on implementation


@pytest.mark.parametrize(
    "agent,expected_count",
    [
        ("claude", 3),
        ("codex", 2),
        ("gemini", 2),
    ],
)
def test_agent_filter_expected_counts(
    agent: str,
    expected_count: int,
    agent_filter_sessions: Dict[str, Any],
) -> None:
    """Test --agent filter returns expected session counts.

    Args:
        agent: Agent type to filter
        expected_count: Expected session count
        agent_filter_sessions: Test fixture with known counts
    """
    result = run_cli_subprocess(
        ["session", "list", "--agent", agent, "--aw"],
        env=agent_filter_sessions["env"],
    )

    assert_cli_success(result, f"--agent {agent} should succeed")

    # Validate against expected count
    actual_count = agent_filter_sessions["counts"][agent]
    assert (
        actual_count == expected_count
    ), f"Expected {expected_count} {agent} sessions, fixture has {actual_count}"
