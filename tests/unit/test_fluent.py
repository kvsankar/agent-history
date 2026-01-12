"""Tests for the fluent/chained API in agent_history/fluent.py.

This module tests the FluentContext class and the context() factory function
that provide a chainable interface for building scope queries.

Test Coverage:
1. FluentContext initialization and basic configuration
2. Method chaining (scope, home, filter, output)
3. Terminal methods (list, list_workspaces, list_homes, export, stats)
4. Convenience properties (sessions, workspaces, homes, session_count)
5. Integration with the underlying scope resolution pipeline
6. Error handling and edge cases

See docs/design-v2/scope-resolution-v2.md for the underlying architecture.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_history.fluent import Context, FluentContext, context
from agent_history.handlers.base import CommandResult
from agent_history.scope.context import ResolutionContext, ScopeArgs
from agent_history.scope.types import (
    ConcreteRecord,
    ConcreteScope,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_context() -> ResolutionContext:
    """Create a mock ResolutionContext for testing.

    Provides:
    - available_homes: wsl=[Ubuntu], remote=[vm01]
    - project_config: testproj with local workspaces
    - cwd_workspace: /home/user/current
    - cwd_home: local
    """
    ctx = ResolutionContext()
    ctx.platform = "linux"
    ctx.is_wsl = False
    ctx.cwd = Path("/home/user/current")
    ctx.cwd_home = "local"
    ctx.cwd_workspace = "/home/user/current"
    ctx.cwd_project = None

    ctx.available_homes = {
        "wsl": ["Ubuntu"],
        "windows": [],
        "remote": ["vm01"],
    }

    ctx.project_config = {
        "testproj": {
            "local": ["/home/user/auth"],
        },
        "multiworkspace": {
            "local": ["/home/user/proj1", "/home/user/proj2"],
        },
    }

    ctx.claude_projects_dir = None
    ctx.codex_sessions_dir = None
    ctx.gemini_sessions_dir = None

    return ctx


@pytest.fixture
def mock_sessions() -> list[dict]:
    """Create mock session data for testing."""
    return [
        {
            "id": "s1",
            "workspace_readable": "/home/user/auth",
            "agent": "claude",
            "message_count": 10,
        },
        {
            "id": "s2",
            "workspace_readable": "/home/user/auth",
            "agent": "claude",
            "message_count": 5,
        },
        {
            "id": "s3",
            "workspace_readable": "/home/user/api",
            "agent": "codex",
            "message_count": 8,
        },
    ]


@pytest.fixture
def mock_scope(mock_sessions: list[dict]) -> ConcreteScope:
    """Create a mock ConcreteScope for testing terminal methods."""
    return [
        ConcreteRecord(
            home="local",
            workspace="/home/user/auth",
            sessions=[mock_sessions[0], mock_sessions[1]],
        ),
        ConcreteRecord(
            home="local",
            workspace="/home/user/api",
            sessions=[mock_sessions[2]],
        ),
    ]


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestContextFactory:
    """Tests for the context() factory function."""

    def test_context_returns_fluent_context(self) -> None:
        """context() should return a FluentContext instance."""
        result = context()
        assert isinstance(result, FluentContext)

    def test_context_with_custom_resolution_context(self, mock_context: ResolutionContext) -> None:
        """context() should accept a custom ResolutionContext."""
        result = context(mock_context)
        assert result.resolution_context is mock_context

    def test_context_alias_matches_fluent_context(self) -> None:
        """Context should be an alias for FluentContext."""
        assert Context is FluentContext


class TestFluentContextInit:
    """Tests for FluentContext initialization."""

    def test_init_builds_context_if_not_provided(self) -> None:
        """FluentContext should build ResolutionContext if not provided."""
        fc = FluentContext()
        assert fc._context is not None
        assert isinstance(fc._context, ResolutionContext)

    def test_init_uses_provided_context(self, mock_context: ResolutionContext) -> None:
        """FluentContext should use provided ResolutionContext."""
        fc = FluentContext(mock_context)
        assert fc._context is mock_context

    def test_init_creates_empty_scope_args(self) -> None:
        """FluentContext should start with empty ScopeArgs."""
        fc = FluentContext()
        assert isinstance(fc._scope_args, ScopeArgs)
        assert fc._scope_args.patterns == []
        assert fc._scope_args.projects == []
        assert not fc._scope_args.all_workspaces


# =============================================================================
# Scope Method Tests
# =============================================================================


class TestScopeMethod:
    """Tests for the scope() method."""

    def test_scope_returns_self_for_chaining(self, mock_context: ResolutionContext) -> None:
        """scope() should return self for method chaining."""
        fc = FluentContext(mock_context)
        result = fc.scope("myproject")
        assert result is fc

    def test_scope_adds_pattern(self, mock_context: ResolutionContext) -> None:
        """scope(pattern) should add pattern to scope_args."""
        fc = FluentContext(mock_context)
        fc.scope("myproject")
        assert "myproject" in fc._scope_args.patterns

    def test_scope_multiple_patterns(self, mock_context: ResolutionContext) -> None:
        """Multiple scope() calls should accumulate patterns."""
        fc = FluentContext(mock_context)
        fc.scope("auth").scope("api")
        assert "auth" in fc._scope_args.patterns
        assert "api" in fc._scope_args.patterns
        assert len(fc._scope_args.patterns) == 2

    def test_scope_with_project(self, mock_context: ResolutionContext) -> None:
        """scope(project=) should set project in scope_args."""
        fc = FluentContext(mock_context)
        fc.scope(project="testproj")
        assert fc._scope_args.projects == ["testproj"]

    def test_scope_with_all_workspaces(self, mock_context: ResolutionContext) -> None:
        """scope(all_workspaces=True) should set flag."""
        fc = FluentContext(mock_context)
        fc.scope(all_workspaces=True)
        assert fc._scope_args.all_workspaces is True

    def test_scope_with_this_only(self, mock_context: ResolutionContext) -> None:
        """scope(this_only=True) should set flag."""
        fc = FluentContext(mock_context)
        fc.scope(this_only=True)
        assert fc._scope_args.this_only is True

    def test_scope_invalidates_cached_scope(self, mock_context: ResolutionContext) -> None:
        """scope() should invalidate any cached resolution."""
        fc = FluentContext(mock_context)
        fc._scope = []  # Simulate cached scope
        fc._result = MagicMock()
        fc.scope("newpattern")
        assert fc._scope is None
        assert fc._result is None


class TestPatternMethod:
    """Tests for the pattern() method."""

    def test_pattern_adds_pattern(self, mock_context: ResolutionContext) -> None:
        """pattern() should add to patterns list."""
        fc = FluentContext(mock_context)
        fc.pattern("mypattern")
        assert "mypattern" in fc._scope_args.patterns

    def test_pattern_returns_self(self, mock_context: ResolutionContext) -> None:
        """pattern() should return self for chaining."""
        fc = FluentContext(mock_context)
        result = fc.pattern("test")
        assert result is fc


class TestNamePatternMethod:
    """Tests for the name_pattern() method."""

    def test_name_pattern_adds_to_list(self, mock_context: ResolutionContext) -> None:
        """name_pattern() should add to name_patterns list."""
        fc = FluentContext(mock_context)
        fc.name_pattern("django")
        assert "django" in fc._scope_args.name_patterns

    def test_name_pattern_returns_self(self, mock_context: ResolutionContext) -> None:
        """name_pattern() should return self for chaining."""
        fc = FluentContext(mock_context)
        result = fc.name_pattern("test")
        assert result is fc


# =============================================================================
# Home Method Tests
# =============================================================================


class TestHomeMethod:
    """Tests for the home() method."""

    def test_home_returns_self_for_chaining(self, mock_context: ResolutionContext) -> None:
        """home() should return self for method chaining."""
        fc = FluentContext(mock_context)
        result = fc.home(all_homes=True)
        assert result is fc

    def test_home_with_all_homes(self, mock_context: ResolutionContext) -> None:
        """home(all_homes=True) should set flag."""
        fc = FluentContext(mock_context)
        fc.home(all_homes=True)
        assert fc._scope_args.all_homes is True

    def test_home_with_type(self, mock_context: ResolutionContext) -> None:
        """home(home_type=) should set home_type."""
        fc = FluentContext(mock_context)
        fc.home(home_type="wsl")
        assert fc._scope_args.home_type == "wsl"

    def test_home_with_type_and_name(self, mock_context: ResolutionContext) -> None:
        """home(home_type=, home_name=) should set both."""
        fc = FluentContext(mock_context)
        fc.home(home_type="wsl", home_name="Ubuntu")
        assert fc._scope_args.home_type == "wsl"
        assert fc._scope_args.home_value == "Ubuntu"

    def test_home_with_name_only(self, mock_context: ResolutionContext) -> None:
        """home(home_name=) should add to home_names."""
        fc = FluentContext(mock_context)
        fc.home(home_name="wsl:Ubuntu")
        assert "wsl:Ubuntu" in fc._scope_args.home_names

    def test_home_exclusion_flags(self, mock_context: ResolutionContext) -> None:
        """home() should handle exclusion flags."""
        fc = FluentContext(mock_context)
        fc.home(all_homes=True, no_wsl=True, no_windows=True, no_remote=True, no_web=True)
        assert fc._scope_args.no_wsl is True
        assert fc._scope_args.no_windows is True
        assert fc._scope_args.no_remote is True
        assert fc._scope_args.no_web is True


# =============================================================================
# Filter Method Tests
# =============================================================================


class TestFilterMethod:
    """Tests for the filter() method."""

    def test_filter_returns_self_for_chaining(self, mock_context: ResolutionContext) -> None:
        """filter() should return self for method chaining."""
        fc = FluentContext(mock_context)
        result = fc.filter(since="2024-01-01")
        assert result is fc

    def test_filter_with_since(self, mock_context: ResolutionContext) -> None:
        """filter(since=) should set since date."""
        fc = FluentContext(mock_context)
        fc.filter(since="2024-01-01")
        assert fc._scope_args.since == "2024-01-01"

    def test_filter_with_until(self, mock_context: ResolutionContext) -> None:
        """filter(until=) should set until date."""
        fc = FluentContext(mock_context)
        fc.filter(until="2024-12-31")
        assert fc._scope_args.until == "2024-12-31"

    def test_filter_with_agent(self, mock_context: ResolutionContext) -> None:
        """filter(agent=) should set agent filter."""
        fc = FluentContext(mock_context)
        fc.filter(agent="claude")
        assert fc._scope_args.agent == "claude"

    def test_filter_multiple_params(self, mock_context: ResolutionContext) -> None:
        """filter() should handle multiple parameters."""
        fc = FluentContext(mock_context)
        fc.filter(since="2024-01-01", until="2024-12-31", agent="claude")
        assert fc._scope_args.since == "2024-01-01"
        assert fc._scope_args.until == "2024-12-31"
        assert fc._scope_args.agent == "claude"


# =============================================================================
# Output Method Tests
# =============================================================================


class TestOutputMethod:
    """Tests for the output() method."""

    def test_output_returns_self_for_chaining(self, mock_context: ResolutionContext) -> None:
        """output() should return self for method chaining."""
        fc = FluentContext(mock_context)
        result = fc.output(format="json")
        assert result is fc

    def test_output_format(self, mock_context: ResolutionContext) -> None:
        """output(format=) should set output format."""
        fc = FluentContext(mock_context)
        fc.output(format="json")
        assert fc._output_args.format == "json"

    def test_output_path(self, mock_context: ResolutionContext) -> None:
        """output(output_path=) should set output path."""
        fc = FluentContext(mock_context)
        fc.output(output_path="/tmp/output.txt")
        assert fc._output_args.output_path == Path("/tmp/output.txt")

    def test_output_quiet(self, mock_context: ResolutionContext) -> None:
        """output(quiet=True) should set quiet mode."""
        fc = FluentContext(mock_context)
        fc.output(quiet=True)
        assert fc._output_args.quiet is True


# =============================================================================
# Method Chaining Tests
# =============================================================================


class TestMethodChaining:
    """Tests for method chaining behavior."""

    def test_full_chain(self, mock_context: ResolutionContext) -> None:
        """All methods should chain together correctly."""
        fc = FluentContext(mock_context)
        result = (
            fc.home(all_homes=True)
            .scope("myproject")
            .pattern("auth")
            .filter(since="2024-01-01", agent="claude")
            .output(format="json")
        )
        assert result is fc
        assert fc._scope_args.all_homes is True
        assert "myproject" in fc._scope_args.patterns
        assert "auth" in fc._scope_args.patterns
        assert fc._scope_args.since == "2024-01-01"
        assert fc._scope_args.agent == "claude"
        assert fc._output_args.format == "json"

    def test_chain_order_independence(self, mock_context: ResolutionContext) -> None:
        """Methods should work in any order."""
        fc1 = FluentContext(mock_context)
        fc1.scope("pattern").home(all_homes=True).filter(agent="claude")

        fc2 = FluentContext(mock_context)
        fc2.filter(agent="claude").home(all_homes=True).scope("pattern")

        # Both should have equivalent scope_args
        assert fc1._scope_args.patterns == fc2._scope_args.patterns
        assert fc1._scope_args.all_homes == fc2._scope_args.all_homes
        assert fc1._scope_args.agent == fc2._scope_args.agent


# =============================================================================
# Terminal Method Tests
# =============================================================================


class TestListMethod:
    """Tests for the list() terminal method."""

    def test_list_returns_command_result(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """list() should return a CommandResult."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            result = fc.list()

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.data_type == "session_list"

    def test_list_with_format_override(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """list(format=) should override output format."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            fc.list(format="json")

        # Format should be set in output_args
        assert fc._output_args.format == "json"

    def test_list_session_count_in_metadata(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """list() should include session count in metadata."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            result = fc.list()

        assert "total_count" in result.metadata
        assert result.metadata["total_count"] == 3  # 2 + 1 sessions


class TestListWorkspacesMethod:
    """Tests for the list_workspaces() terminal method."""

    def test_list_workspaces_returns_command_result(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """list_workspaces() should return a CommandResult."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            result = fc.list_workspaces()

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.data_type == "workspace_list"


class TestListHomesMethod:
    """Tests for the list_homes() terminal method."""

    def test_list_homes_returns_command_result(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """list_homes() should return a CommandResult."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            result = fc.list_homes()

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.data_type == "home_list"


class TestExportMethod:
    """Tests for the export() terminal method."""

    def test_export_returns_command_result(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope, tmp_path: Path
    ) -> None:
        """export() should return a CommandResult."""
        fc = FluentContext(mock_context)

        # Export to temp directory
        with patch.object(fc, "_resolve", return_value=mock_scope):
            # Mock the handler to avoid actual file operations
            with patch("agent_history.fluent.SessionExportHandler.execute") as mock_execute:
                mock_execute.return_value = CommandResult(
                    success=True,
                    data={"exported": 0, "skipped": 0, "failed": 0},
                    data_type="export_result",
                )
                result = fc.export(tmp_path / "exports")

        assert isinstance(result, CommandResult)
        assert result.data_type == "export_result"

    def test_export_with_options(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope, tmp_path: Path
    ) -> None:
        """export() should pass options to handler."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            with patch("agent_history.fluent.SessionExportHandler.execute") as mock_execute:
                mock_execute.return_value = CommandResult(
                    success=True,
                    data={},
                    data_type="export_result",
                )
                fc.export(
                    tmp_path / "exports",
                    format="json",
                    minimal=True,
                    split=1000,
                    flat=True,
                    force=True,
                )

                # Check that handler was called with correct verb_args
                call_args = mock_execute.call_args
                verb_args = call_args[0][1]
                assert verb_args["minimal"] is True
                assert verb_args["split"] == 1000
                assert verb_args["flat"] is True
                assert verb_args["force"] is True
                assert verb_args["export_json"] is True


class TestStatsMethod:
    """Tests for the stats() terminal method."""

    def test_stats_returns_command_result(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """stats() should return a CommandResult."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            result = fc.stats()

        assert isinstance(result, CommandResult)
        assert result.success is True
        assert result.data_type == "stats"

    def test_stats_with_grouping(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """stats(by=) should set grouping dimension."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            result = fc.stats(by="model")

        assert result.metadata.get("group_by") == ["model"]

    def test_stats_with_time(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """stats(include_time=True) should include time stats."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            result = fc.stats(include_time=True)

        assert result.metadata.get("include_time") is True


# =============================================================================
# Convenience Properties Tests
# =============================================================================


class TestConvenienceProperties:
    """Tests for convenience properties."""

    def test_sessions_property(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """sessions property should return flattened session list."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            sessions = fc.sessions

        assert len(sessions) == 3
        # Check that home and workspace are added
        assert all("home" in s for s in sessions)
        assert all("workspace" in s for s in sessions)

    def test_workspaces_property(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """workspaces property should return unique workspace paths."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            workspaces = fc.workspaces

        assert len(workspaces) == 2
        assert "/home/user/auth" in workspaces
        assert "/home/user/api" in workspaces

    def test_homes_property(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """homes property should return unique home identifiers."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            homes = fc.homes

        assert len(homes) == 1
        assert "local" in homes

    def test_session_count_property(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """session_count property should return total session count."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            count = fc.session_count

        assert count == 3

    def test_resolution_context_property(self, mock_context: ResolutionContext) -> None:
        """resolution_context property should return the context."""
        fc = FluentContext(mock_context)
        assert fc.resolution_context is mock_context

    def test_scope_args_property(self, mock_context: ResolutionContext) -> None:
        """scope_args property should return the accumulated args."""
        fc = FluentContext(mock_context)
        fc.scope("pattern").filter(agent="claude")
        assert "pattern" in fc.scope_args.patterns
        assert fc.scope_args.agent == "claude"


# =============================================================================
# Resolution Result Properties Tests
# =============================================================================


class TestResolutionResultProperties:
    """Tests for properties accessing ResolutionResult."""

    def test_errors_property_empty_on_success(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """errors property should be empty on successful resolution."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            with patch.object(fc, "_get_result") as mock_get_result:
                mock_result = MagicMock()
                mock_result.errors = []
                mock_get_result.return_value = mock_result
                errors = fc.errors

        assert errors == []

    def test_warnings_property(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """warnings property should return resolution warnings."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            with patch.object(fc, "_get_result") as mock_get_result:
                mock_result = MagicMock()
                mock_result.warnings = ["test warning"]
                mock_get_result.return_value = mock_result
                warnings = fc.warnings

        assert warnings == ["test warning"]

    def test_success_property_true_on_success(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """success property should be True on successful resolution."""
        fc = FluentContext(mock_context)

        with patch.object(fc, "_resolve", return_value=mock_scope):
            with patch.object(fc, "_get_result") as mock_get_result:
                mock_result = MagicMock()
                mock_result.success = True
                mock_get_result.return_value = mock_result
                success = fc.success

        assert success is True


# =============================================================================
# Lazy Resolution Tests
# =============================================================================


class TestLazyResolution:
    """Tests for lazy resolution behavior."""

    def test_scope_cached_after_first_resolve(self, mock_context: ResolutionContext) -> None:
        """Resolved scope should be cached."""
        fc = FluentContext(mock_context)
        mock_scope: ConcreteScope = []

        with patch("agent_history.fluent.ScopeResolver.resolve") as mock_resolve:
            mock_result = MagicMock()
            mock_result.scope = mock_scope
            mock_resolve.return_value = mock_result

            # First access
            _ = fc._resolve()
            # Second access
            _ = fc._resolve()

        # Should only resolve once
        assert mock_resolve.call_count == 1

    def test_scope_method_invalidates_cache(self, mock_context: ResolutionContext) -> None:
        """scope() should invalidate cached resolution."""
        fc = FluentContext(mock_context)

        with patch("agent_history.fluent.ScopeResolver.resolve") as mock_resolve:
            mock_result = MagicMock()
            mock_result.scope = []
            mock_resolve.return_value = mock_result

            # First access
            _ = fc._resolve()
            # Modify scope
            fc.scope("newpattern")
            # Second access after modification
            _ = fc._resolve()

        # Should resolve twice (cache was invalidated)
        assert mock_resolve.call_count == 2


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests with the real scope resolution pipeline."""

    def test_real_context_builder(self) -> None:
        """FluentContext should work with real ContextBuilder."""
        # This just verifies no exceptions are raised during initialization
        fc = context()
        assert fc._context is not None
        assert isinstance(fc._context, ResolutionContext)

    def test_full_fluent_chain_with_empty_scope(self, mock_context: ResolutionContext) -> None:
        """Full chain should work even when scope is empty."""
        fc = FluentContext(mock_context)

        # Use a pattern that won't match anything
        with patch("agent_history.fluent.ScopeResolver.resolve") as mock_resolve:
            mock_result = MagicMock()
            mock_result.scope = []
            mock_result.success = True
            mock_result.errors = []
            mock_result.warnings = []
            mock_resolve.return_value = mock_result

            result = fc.scope("nonexistent-pattern").filter(agent="claude").list()

        assert result.success is True
        assert result.data == []


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Edge cases and error handling tests."""

    def test_empty_scope_args(self, mock_context: ResolutionContext) -> None:
        """Empty scope args should resolve with defaults."""
        fc = FluentContext(mock_context)

        with patch("agent_history.fluent.ScopeResolver.resolve") as mock_resolve:
            mock_result = MagicMock()
            mock_result.scope = []
            mock_resolve.return_value = mock_result

            _ = fc._resolve()

        # ScopeResolver.resolve should be called with empty ScopeArgs
        mock_resolve.assert_called_once()

    def test_multiple_agents_filter(self, mock_context: ResolutionContext) -> None:
        """filter(agent=) should only set one agent at a time."""
        fc = FluentContext(mock_context)
        fc.filter(agent="claude").filter(agent="codex")
        # Last value wins
        assert fc._scope_args.agent == "codex"

    def test_path_with_spaces(
        self, mock_context: ResolutionContext, mock_scope: ConcreteScope
    ) -> None:
        """Paths with spaces should be handled correctly."""
        fc = FluentContext(mock_context)
        fc.scope("/home/user/my project")
        assert "/home/user/my project" in fc._scope_args.patterns

    def test_none_values_ignored(self, mock_context: ResolutionContext) -> None:
        """Methods should ignore None values."""
        fc = FluentContext(mock_context)
        fc.scope(None).filter(since=None, until=None, agent=None)
        assert fc._scope_args.patterns == []
        assert fc._scope_args.since is None
        assert fc._scope_args.until is None
        assert fc._scope_args.agent is None


# =============================================================================
# Documentation Examples Tests
# =============================================================================


class TestDocumentationExamples:
    """Tests that verify the examples in the docstrings work correctly."""

    def test_basic_list_example(self, mock_context: ResolutionContext) -> None:
        """Test: context().scope().list()"""
        fc = context(mock_context)

        with patch("agent_history.fluent.ScopeResolver.resolve") as mock_resolve:
            mock_result = MagicMock()
            mock_result.scope = []
            mock_resolve.return_value = mock_result

            result = fc.scope().list()

        assert isinstance(result, CommandResult)

    def test_pattern_with_filter_example(self, mock_context: ResolutionContext) -> None:
        """Test: context().scope("myproject").filter(since="2024-01-01").list()"""
        fc = context(mock_context)

        with patch("agent_history.fluent.ScopeResolver.resolve") as mock_resolve:
            mock_result = MagicMock()
            mock_result.scope = []
            mock_resolve.return_value = mock_result

            result = fc.scope("myproject").filter(since="2024-01-01").list()

        assert "myproject" in fc._scope_args.patterns
        assert fc._scope_args.since == "2024-01-01"
        assert isinstance(result, CommandResult)

    def test_all_workspaces_export_example(
        self, mock_context: ResolutionContext, tmp_path: Path
    ) -> None:
        """Test: context().scope(all_workspaces=True).export("./export/")"""
        fc = context(mock_context)

        with patch("agent_history.fluent.ScopeResolver.resolve") as mock_resolve:
            mock_result = MagicMock()
            mock_result.scope = []
            mock_resolve.return_value = mock_result

            with patch("agent_history.fluent.SessionExportHandler.execute") as mock_execute:
                mock_execute.return_value = CommandResult(
                    success=True,
                    data={},
                    data_type="export_result",
                )
                result = fc.scope(all_workspaces=True).export(tmp_path / "export")

        assert fc._scope_args.all_workspaces is True
        assert isinstance(result, CommandResult)

    def test_multi_home_stats_example(self, mock_context: ResolutionContext) -> None:
        """Test: context().home(all_homes=True).scope(all_workspaces=True).stats()"""
        fc = context(mock_context)

        with patch("agent_history.fluent.ScopeResolver.resolve") as mock_resolve:
            mock_result = MagicMock()
            mock_result.scope = []
            mock_resolve.return_value = mock_result

            result = fc.home(all_homes=True).scope(all_workspaces=True).stats()

        assert fc._scope_args.all_homes is True
        assert fc._scope_args.all_workspaces is True
        assert isinstance(result, CommandResult)
