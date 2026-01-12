"""Tests for the Pythonic API (agent_history.api).

These tests verify the simple function-based API works correctly,
including generators, list functions, export, and stats.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_history import api
from agent_history.scope.context import ResolutionContext
from agent_history.scope.types import ConcreteRecord

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_context():
    """Create a mock ResolutionContext."""
    ctx = MagicMock(spec=ResolutionContext)
    ctx.cwd = Path("/home/user/projects/myapp")
    ctx.platform = "linux"
    return ctx


@pytest.fixture
def mock_scope():
    """Create a mock ConcreteScope with test data."""
    # ConcreteScope is just List[ConcreteRecord]
    return [
        ConcreteRecord(
            home="local",
            workspace="/home/user/projects/myapp",
            sessions=[
                {"filename": "session1.jsonl", "file": "/path/to/session1.jsonl"},
                {"filename": "session2.jsonl", "file": "/path/to/session2.jsonl"},
            ],
        ),
        ConcreteRecord(
            home="local",
            workspace="/home/user/projects/auth",
            sessions=[
                {"filename": "session3.jsonl", "file": "/path/to/session3.jsonl"},
            ],
        ),
    ]


@pytest.fixture
def mock_multi_home_scope():
    """Create a mock scope with multiple homes."""
    return [
        ConcreteRecord(
            home="local",
            workspace="/home/user/projects/app",
            sessions=[{"filename": "s1.jsonl"}],
        ),
        ConcreteRecord(
            home="wsl:Ubuntu",
            workspace="/home/user/projects/api",
            sessions=[{"filename": "s2.jsonl"}, {"filename": "s3.jsonl"}],
        ),
    ]


# =============================================================================
# Test _build_scope_args Helper
# =============================================================================


class TestBuildScopeArgs:
    """Tests for the _build_scope_args helper function."""

    def test_empty_args(self):
        """Test building with no arguments."""
        args = api._build_scope_args()
        assert args.patterns == []
        assert args.all_workspaces is False
        assert args.all_homes is False

    def test_single_pattern(self):
        """Test with a single pattern."""
        args = api._build_scope_args("myproject")
        assert args.patterns == ["myproject"]

    def test_multiple_patterns(self):
        """Test with multiple patterns."""
        args = api._build_scope_args("app", patterns=["auth", "api"])
        assert args.patterns == ["app", "auth", "api"]

    def test_project_arg(self):
        """Test project parameter."""
        args = api._build_scope_args(project="myapp")
        assert args.project == "myapp"

    def test_all_workspaces(self):
        """Test all_workspaces flag."""
        args = api._build_scope_args(all_workspaces=True)
        assert args.all_workspaces is True

    def test_this_only(self):
        """Test this_only flag."""
        args = api._build_scope_args(this_only=True)
        assert args.this_only is True

    def test_all_homes(self):
        """Test all_homes flag."""
        args = api._build_scope_args(all_homes=True)
        assert args.all_homes is True

    def test_home_name(self):
        """Test specific home name."""
        args = api._build_scope_args(home="wsl:Ubuntu")
        assert "wsl:Ubuntu" in args.home_names

    def test_home_type(self):
        """Test home type filter."""
        args = api._build_scope_args(home_type="wsl")
        assert args.home_type == "wsl"

    def test_exclusion_flags(self):
        """Test home exclusion flags."""
        args = api._build_scope_args(no_wsl=True, no_windows=True, no_remote=True)
        assert args.no_wsl is True
        assert args.no_windows is True
        assert args.no_remote is True

    def test_date_filters(self):
        """Test since/until filters."""
        args = api._build_scope_args(since="2024-01-01", until="2024-12-31")
        assert args.since == "2024-01-01"
        assert args.until == "2024-12-31"

    def test_agent_filter(self):
        """Test agent type filter."""
        args = api._build_scope_args(agent="claude")
        assert args.agent == "claude"


# =============================================================================
# Test Generator Functions
# =============================================================================


class TestSessionsGenerator:
    """Tests for the sessions() generator function."""

    def test_sessions_yields_sessions(self, mock_scope):
        """Test that sessions() yields session dicts."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            result = list(api.sessions("myapp"))

        assert len(result) == 3
        assert result[0]["filename"] == "session1.jsonl"
        assert result[2]["filename"] == "session3.jsonl"

    def test_sessions_adds_context(self, mock_scope):
        """Test that sessions include home and workspace."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            result = list(api.sessions("myapp"))

        assert result[0]["home"] == "local"
        assert result[0]["workspace"] == "/home/user/projects/myapp"

    def test_sessions_is_lazy(self, mock_scope):
        """Test that sessions() is a generator (lazy)."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            gen = api.sessions("myapp")

        # Should be a generator, not a list
        assert hasattr(gen, "__iter__")
        assert hasattr(gen, "__next__")

    def test_sessions_empty_scope(self):
        """Test sessions() with empty scope."""
        empty_scope = []  # ConcreteScope is just List[ConcreteRecord]
        with patch.object(api, "_resolve_scope", return_value=empty_scope):
            result = list(api.sessions("nonexistent"))

        assert result == []


class TestWorkspacesGenerator:
    """Tests for the workspaces() generator function."""

    def test_workspaces_yields_workspace_info(self, mock_scope):
        """Test that workspaces() yields workspace dicts."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            result = list(api.workspaces(all_workspaces=True))

        assert len(result) == 2
        assert result[0]["workspace"] == "/home/user/projects/myapp"
        assert result[0]["session_count"] == 2
        assert result[1]["workspace"] == "/home/user/projects/auth"
        assert result[1]["session_count"] == 1

    def test_workspaces_includes_home(self, mock_scope):
        """Test that workspaces include home info."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            result = list(api.workspaces(all_workspaces=True))

        assert result[0]["home"] == "local"


class TestHomesGenerator:
    """Tests for the homes() generator function."""

    def test_homes_yields_home_info(self, mock_multi_home_scope):
        """Test that homes() yields home dicts."""
        with patch.object(api, "_resolve_scope", return_value=mock_multi_home_scope):
            result = list(api.homes())

        assert len(result) == 2
        # Find local and wsl homes
        home_map = {h["home"]: h for h in result}
        assert "local" in home_map
        assert "wsl:Ubuntu" in home_map
        assert home_map["local"]["session_count"] == 1
        assert home_map["wsl:Ubuntu"]["session_count"] == 2

    def test_homes_counts_workspaces(self, mock_multi_home_scope):
        """Test that homes include workspace counts."""
        with patch.object(api, "_resolve_scope", return_value=mock_multi_home_scope):
            result = list(api.homes())

        home_map = {h["home"]: h for h in result}
        assert home_map["local"]["workspace_count"] == 1
        assert home_map["wsl:Ubuntu"]["workspace_count"] == 1


# =============================================================================
# Test List Functions
# =============================================================================


class TestListSessions:
    """Tests for list_sessions() function."""

    def test_list_sessions_returns_command_result(self, mock_scope):
        """Test that list_sessions returns a CommandResult."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            result = api.list_sessions("myapp")

        assert hasattr(result, "success")
        assert hasattr(result, "data")
        assert result.success is True

    def test_list_sessions_calls_handler(self, mock_scope):
        """Test that list_sessions uses SessionListHandler."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            with patch("agent_history.api.SessionListHandler") as mock_handler:
                mock_handler.return_value.execute.return_value = MagicMock(success=True)
                api.list_sessions("myapp")

        mock_handler.return_value.execute.assert_called_once()


class TestListWorkspaces:
    """Tests for list_workspaces() function."""

    def test_list_workspaces_returns_command_result(self, mock_scope):
        """Test that list_workspaces returns a CommandResult."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            result = api.list_workspaces(all_workspaces=True)

        assert hasattr(result, "success")
        assert result.success is True


class TestListHomes:
    """Tests for list_homes() function."""

    def test_list_homes_returns_command_result(self, mock_scope):
        """Test that list_homes returns a CommandResult."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            result = api.list_homes()

        assert hasattr(result, "success")
        assert result.success is True


# =============================================================================
# Test Export Function
# =============================================================================


class TestExport:
    """Tests for export() function."""

    def test_export_returns_command_result(self, mock_scope, tmp_path):
        """Test that export returns a CommandResult."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            with patch("agent_history.api.SessionExportHandler") as mock_handler:
                mock_handler.return_value.execute.return_value = MagicMock(
                    success=True,
                    data={"exported": 3, "skipped": 0, "failed": 0},
                )
                result = api.export("myapp", tmp_path)

        assert result.success is True
        assert result.data["exported"] == 3

    def test_export_passes_options(self, mock_scope, tmp_path):
        """Test that export passes options to handler."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            with patch("agent_history.api.SessionExportHandler") as mock_handler:
                mock_handler.return_value.execute.return_value = MagicMock(success=True)
                api.export(
                    "myapp",
                    tmp_path,
                    minimal=True,
                    split=1000,
                    flat=True,
                    force=True,
                )

        call_args = mock_handler.return_value.execute.call_args
        verb_args = call_args[0][1]
        assert verb_args["minimal"] is True
        assert verb_args["split"] == 1000
        assert verb_args["flat"] is True
        assert verb_args["force"] is True


# =============================================================================
# Test Stats Function
# =============================================================================


class TestStats:
    """Tests for stats() function."""

    def test_stats_returns_command_result(self, mock_scope):
        """Test that stats returns a CommandResult."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            with patch("agent_history.api.SessionStatsHandler") as mock_handler:
                mock_handler.return_value.execute.return_value = MagicMock(
                    success=True,
                    data={"sessions": 3},
                )
                result = api.stats("myapp")

        assert result.success is True
        assert result.data["sessions"] == 3

    def test_stats_passes_grouping(self, mock_scope):
        """Test that stats passes grouping options."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            with patch("agent_history.api.SessionStatsHandler") as mock_handler:
                mock_handler.return_value.execute.return_value = MagicMock(success=True)
                api.stats("myapp", by="model", include_time=True, top=10)

        call_args = mock_handler.return_value.execute.call_args
        verb_args = call_args[0][1]
        assert verb_args["by"] == "model"
        assert verb_args["time"] is True
        assert verb_args["top"] == 10


# =============================================================================
# Test Utility Functions
# =============================================================================


class TestCountSessions:
    """Tests for count_sessions() function."""

    def test_count_sessions_returns_int(self, mock_scope):
        """Test that count_sessions returns an integer."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            count = api.count_sessions("myapp")

        assert count == 3

    def test_count_sessions_empty(self):
        """Test count_sessions with empty scope."""
        empty_scope = []  # ConcreteScope is just List[ConcreteRecord]
        with patch.object(api, "_resolve_scope", return_value=empty_scope):
            count = api.count_sessions("nonexistent")

        assert count == 0


class TestCountWorkspaces:
    """Tests for count_workspaces() function."""

    def test_count_workspaces_returns_int(self, mock_scope):
        """Test that count_workspaces returns an integer."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            count = api.count_workspaces()

        assert count == 2


# =============================================================================
# Integration-Style Tests
# =============================================================================


class TestApiPatterns:
    """Test common usage patterns with the API."""

    def test_pattern_list_comprehension(self, mock_scope):
        """Test using list comprehension with sessions()."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            filenames = [s["filename"] for s in api.sessions("myapp")]

        assert len(filenames) == 3
        assert "session1.jsonl" in filenames

    def test_pattern_filter_with_generator(self, mock_scope):
        """Test filtering sessions with generator expression."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            auth_sessions = [
                s for s in api.sessions(all_workspaces=True) if "auth" in s["workspace"]
            ]

        assert len(auth_sessions) == 1

    def test_pattern_count_with_sum(self, mock_scope):
        """Test counting with sum()."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            count = sum(1 for _ in api.sessions("myapp"))

        assert count == 3

    def test_pattern_first_session(self, mock_scope):
        """Test getting first session with next()."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            first = next(api.sessions("myapp"), None)

        assert first is not None
        assert first["filename"] == "session1.jsonl"

    def test_pattern_any_match(self, mock_scope):
        """Test using any() with sessions."""
        with patch.object(api, "_resolve_scope", return_value=mock_scope):
            has_session1 = any(s["filename"] == "session1.jsonl" for s in api.sessions("myapp"))

        assert has_session1 is True


class TestApiWithRealContext:
    """Integration tests using real context building."""

    def test_list_sessions_with_empty_scope(self, tmp_path):
        """Test list_sessions with a real but empty scope."""
        # Create a minimal mock context that returns empty results
        result = api.list_sessions("nonexistent-pattern-xyz")
        # Should succeed even with no results
        assert result.success is True
        assert result.data == []

    def test_count_sessions_with_empty_scope(self):
        """Test count_sessions with real but empty scope."""
        count = api.count_sessions("nonexistent-pattern-xyz")
        assert count == 0
