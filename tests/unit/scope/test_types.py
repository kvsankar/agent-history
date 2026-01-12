"""Unit tests for agent_history/scope/types.py.

This module tests the core type system for the v2 scope resolution architecture:
- MatchType enum for workspace matching strategies
- HomeSpec types for specifying homes (local, WSL, remote, etc.)
- WorkspaceSpec types for specifying workspaces
- SessionSpec types for specifying sessions
- SessionFilters for filtering sessions by criteria
- Record types (ScopeRecord, ProjectRecord, ConcreteRecord)

Each type is tested for:
- Correct creation/instantiation
- Immutability where applicable (frozen dataclasses)
- String representation
- Factory methods where available
"""

from datetime import datetime
from typing import Any, Dict, List

import pytest

from agent_history.scope.types import (
    # Records
    ConcreteRecord,
    # Home specs
    HomeSpec,
    HomeSpecAll,
    HomeSpecCategory,
    HomeSpecCategoryItem,
    HomeSpecConcrete,
    HomeSpecCurrent,
    HomeSpecFactory,
    HomeSpecLocal,
    # Match types
    MatchType,
    ProjectRecord,
    ScopeRecord,
    # Session specs
    SessionFilters,
    SessionSpec,
    SessionSpecAll,
    SessionSpecByFile,
    SessionSpecById,
    SessionSpecFactory,
    SessionSpecFiltered,
    SessionSpecList,
    # Workspace specs
    WorkspaceSpec,
    WorkspaceSpecAll,
    WorkspaceSpecConcrete,
    WorkspaceSpecCurrent,
    WorkspaceSpecEncoded,
    WorkspaceSpecFactory,
    WorkspaceSpecHash,
    WorkspaceSpecPath,
    WorkspaceSpecPattern,
    WorkspaceSpecProject,
)

# =============================================================================
# MatchType Enum Tests
# =============================================================================


class TestMatchTypeEnum:
    """Tests for the MatchType enumeration."""

    def test_matchtype_exact_exists(self) -> None:
        """EXACT match type should exist."""
        assert hasattr(MatchType, "EXACT")
        assert MatchType.EXACT is not None

    def test_matchtype_prefix_exists(self) -> None:
        """PREFIX match type should exist."""
        assert hasattr(MatchType, "PREFIX")
        assert MatchType.PREFIX is not None

    def test_matchtype_contains_exists(self) -> None:
        """CONTAINS match type should exist."""
        assert hasattr(MatchType, "CONTAINS")
        assert MatchType.CONTAINS is not None

    def test_matchtype_glob_exists(self) -> None:
        """GLOB match type should exist."""
        assert hasattr(MatchType, "GLOB")
        assert MatchType.GLOB is not None

    def test_matchtype_exact_value_is_correct(self) -> None:
        """EXACT should have string value 'exact'."""
        assert MatchType.EXACT.value == "exact"

    def test_matchtype_prefix_value_is_correct(self) -> None:
        """PREFIX should have string value 'prefix'."""
        assert MatchType.PREFIX.value == "prefix"

    def test_matchtype_contains_value_is_correct(self) -> None:
        """CONTAINS should have string value 'contains'."""
        assert MatchType.CONTAINS.value == "contains"

    def test_matchtype_glob_value_is_correct(self) -> None:
        """GLOB should have string value 'glob'."""
        assert MatchType.GLOB.value == "glob"

    def test_matchtype_str_returns_value(self) -> None:
        """String conversion should return the enum value."""
        assert str(MatchType.EXACT) == "exact"
        assert str(MatchType.PREFIX) == "prefix"
        assert str(MatchType.CONTAINS) == "contains"
        assert str(MatchType.GLOB) == "glob"

    def test_matchtype_has_exactly_four_values(self) -> None:
        """MatchType should have exactly four values."""
        assert len(MatchType) == 4


# =============================================================================
# HomeSpec Type Tests
# =============================================================================


class TestHomeSpecAll:
    """Tests for HomeSpecAll - all available homes."""

    def test_homespecall_creation_succeeds(self) -> None:
        """HomeSpecAll should be creatable without arguments."""
        spec = HomeSpecAll()
        assert spec is not None

    def test_homespecall_str_representation(self) -> None:
        """HomeSpecAll should have correct string representation."""
        spec = HomeSpecAll()
        assert str(spec) == "HomeSpec.All"

    def test_homespecall_is_homespec_subclass(self) -> None:
        """HomeSpecAll should be a subclass of HomeSpec."""
        spec = HomeSpecAll()
        assert isinstance(spec, HomeSpec)

    def test_homespecall_is_frozen(self) -> None:
        """HomeSpecAll should be immutable (frozen dataclass)."""
        spec = HomeSpecAll()
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.some_attr = "value"  # type: ignore


class TestHomeSpecLocal:
    """Tests for HomeSpecLocal - local home only."""

    def test_homespeclocal_creation_succeeds(self) -> None:
        """HomeSpecLocal should be creatable without arguments."""
        spec = HomeSpecLocal()
        assert spec is not None

    def test_homespeclocal_str_representation(self) -> None:
        """HomeSpecLocal should have correct string representation."""
        spec = HomeSpecLocal()
        assert str(spec) == "HomeSpec.Local"

    def test_homespeclocal_is_homespec_subclass(self) -> None:
        """HomeSpecLocal should be a subclass of HomeSpec."""
        spec = HomeSpecLocal()
        assert isinstance(spec, HomeSpec)

    def test_homespeclocal_is_frozen(self) -> None:
        """HomeSpecLocal should be immutable (frozen dataclass)."""
        spec = HomeSpecLocal()
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.some_attr = "value"  # type: ignore


class TestHomeSpecCurrent:
    """Tests for HomeSpecCurrent - home containing current working directory."""

    def test_homespeccurrent_creation_succeeds(self) -> None:
        """HomeSpecCurrent should be creatable without arguments."""
        spec = HomeSpecCurrent()
        assert spec is not None

    def test_homespeccurrent_str_representation(self) -> None:
        """HomeSpecCurrent should have correct string representation."""
        spec = HomeSpecCurrent()
        assert str(spec) == "HomeSpec.Current"

    def test_homespeccurrent_is_homespec_subclass(self) -> None:
        """HomeSpecCurrent should be a subclass of HomeSpec."""
        spec = HomeSpecCurrent()
        assert isinstance(spec, HomeSpec)

    def test_homespeccurrent_is_frozen(self) -> None:
        """HomeSpecCurrent should be immutable (frozen dataclass)."""
        spec = HomeSpecCurrent()
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.some_attr = "value"  # type: ignore


class TestHomeSpecCategory:
    """Tests for HomeSpecCategory - all homes of a category."""

    def test_homespeccategory_creation_with_wsl(self) -> None:
        """HomeSpecCategory should be creatable with WSL category."""
        spec = HomeSpecCategory(category="wsl")
        assert spec.category == "wsl"

    def test_homespeccategory_creation_with_windows(self) -> None:
        """HomeSpecCategory should be creatable with Windows category."""
        spec = HomeSpecCategory(category="windows")
        assert spec.category == "windows"

    def test_homespeccategory_creation_with_remote(self) -> None:
        """HomeSpecCategory should be creatable with remote category."""
        spec = HomeSpecCategory(category="remote")
        assert spec.category == "remote"

    def test_homespeccategory_str_representation(self) -> None:
        """HomeSpecCategory should have correct string representation."""
        spec = HomeSpecCategory(category="wsl")
        assert str(spec) == "HomeSpec.Category('wsl')"

    def test_homespeccategory_is_homespec_subclass(self) -> None:
        """HomeSpecCategory should be a subclass of HomeSpec."""
        spec = HomeSpecCategory(category="wsl")
        assert isinstance(spec, HomeSpec)

    def test_homespeccategory_is_frozen(self) -> None:
        """HomeSpecCategory should be immutable (frozen dataclass)."""
        spec = HomeSpecCategory(category="wsl")
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.category = "windows"


class TestHomeSpecCategoryItem:
    """Tests for HomeSpecCategoryItem - specific home within a category."""

    def test_homespeccategoryitem_creation_with_wsl_ubuntu(self) -> None:
        """HomeSpecCategoryItem should be creatable with WSL Ubuntu."""
        spec = HomeSpecCategoryItem(category="wsl", item="Ubuntu")
        assert spec.category == "wsl"
        assert spec.item == "Ubuntu"

    def test_homespeccategoryitem_creation_with_remote_dev(self) -> None:
        """HomeSpecCategoryItem should be creatable with remote dev."""
        spec = HomeSpecCategoryItem(category="remote", item="dev")
        assert spec.category == "remote"
        assert spec.item == "dev"

    def test_homespeccategoryitem_creation_with_windows_alice(self) -> None:
        """HomeSpecCategoryItem should be creatable with Windows user."""
        spec = HomeSpecCategoryItem(category="windows", item="alice")
        assert spec.category == "windows"
        assert spec.item == "alice"

    def test_homespeccategoryitem_str_representation(self) -> None:
        """HomeSpecCategoryItem should have correct string representation."""
        spec = HomeSpecCategoryItem(category="wsl", item="Ubuntu")
        assert str(spec) == "HomeSpec.CategoryItem('wsl', 'Ubuntu')"

    def test_homespeccategoryitem_is_homespec_subclass(self) -> None:
        """HomeSpecCategoryItem should be a subclass of HomeSpec."""
        spec = HomeSpecCategoryItem(category="wsl", item="Ubuntu")
        assert isinstance(spec, HomeSpec)

    def test_homespeccategoryitem_is_frozen(self) -> None:
        """HomeSpecCategoryItem should be immutable (frozen dataclass)."""
        spec = HomeSpecCategoryItem(category="wsl", item="Ubuntu")
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.item = "Debian"


class TestHomeSpecConcrete:
    """Tests for HomeSpecConcrete - already-resolved home string."""

    def test_homespecconcrete_creation_with_local(self) -> None:
        """HomeSpecConcrete should be creatable with local home."""
        spec = HomeSpecConcrete(home="local")
        assert spec.home == "local"

    def test_homespecconcrete_creation_with_wsl_distro(self) -> None:
        """HomeSpecConcrete should be creatable with WSL distro."""
        spec = HomeSpecConcrete(home="wsl:Ubuntu")
        assert spec.home == "wsl:Ubuntu"

    def test_homespecconcrete_creation_with_remote(self) -> None:
        """HomeSpecConcrete should be creatable with remote server."""
        spec = HomeSpecConcrete(home="remote:dev")
        assert spec.home == "remote:dev"

    def test_homespecconcrete_str_representation(self) -> None:
        """HomeSpecConcrete should have correct string representation."""
        spec = HomeSpecConcrete(home="local")
        assert str(spec) == "HomeSpec.Concrete('local')"

    def test_homespecconcrete_is_homespec_subclass(self) -> None:
        """HomeSpecConcrete should be a subclass of HomeSpec."""
        spec = HomeSpecConcrete(home="local")
        assert isinstance(spec, HomeSpec)

    def test_homespecconcrete_is_frozen(self) -> None:
        """HomeSpecConcrete should be immutable (frozen dataclass)."""
        spec = HomeSpecConcrete(home="local")
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.home = "wsl:Ubuntu"


class TestHomeSpecFactory:
    """Tests for HomeSpecFactory - convenience factory methods."""

    def test_homespecfactory_all_returns_homespecall(self) -> None:
        """Factory.All should return a HomeSpecAll instance."""
        spec = HomeSpecFactory.All
        assert isinstance(spec, HomeSpecAll)

    def test_homespecfactory_local_returns_homespeclocal(self) -> None:
        """Factory.Local should return a HomeSpecLocal instance."""
        spec = HomeSpecFactory.Local
        assert isinstance(spec, HomeSpecLocal)

    def test_homespecfactory_current_returns_homespeccurrent(self) -> None:
        """Factory.Current should return a HomeSpecCurrent instance."""
        spec = HomeSpecFactory.Current
        assert isinstance(spec, HomeSpecCurrent)

    def test_homespecfactory_category_returns_homespeccategory(self) -> None:
        """Factory.Category() should return a HomeSpecCategory instance."""
        spec = HomeSpecFactory.Category("wsl")
        assert isinstance(spec, HomeSpecCategory)
        assert spec.category == "wsl"

    def test_homespecfactory_categoryitem_returns_homespeccategoryitem(self) -> None:
        """Factory.CategoryItem() should return a HomeSpecCategoryItem instance."""
        spec = HomeSpecFactory.CategoryItem("wsl", "Ubuntu")
        assert isinstance(spec, HomeSpecCategoryItem)
        assert spec.category == "wsl"
        assert spec.item == "Ubuntu"

    def test_homespecfactory_concrete_returns_homespecconcrete(self) -> None:
        """Factory.Concrete() should return a HomeSpecConcrete instance."""
        spec = HomeSpecFactory.Concrete("local")
        assert isinstance(spec, HomeSpecConcrete)
        assert spec.home == "local"


# =============================================================================
# WorkspaceSpec Type Tests
# =============================================================================


class TestWorkspaceSpecAll:
    """Tests for WorkspaceSpecAll - all workspaces in the home."""

    def test_workspacespecall_creation_succeeds(self) -> None:
        """WorkspaceSpecAll should be creatable without arguments."""
        spec = WorkspaceSpecAll()
        assert spec is not None

    def test_workspacespecall_str_representation(self) -> None:
        """WorkspaceSpecAll should have correct string representation."""
        spec = WorkspaceSpecAll()
        assert str(spec) == "WorkspaceSpec.All"

    def test_workspacespecall_is_workspacespec_subclass(self) -> None:
        """WorkspaceSpecAll should be a subclass of WorkspaceSpec."""
        spec = WorkspaceSpecAll()
        assert isinstance(spec, WorkspaceSpec)

    def test_workspacespecall_is_frozen(self) -> None:
        """WorkspaceSpecAll should be immutable (frozen dataclass)."""
        spec = WorkspaceSpecAll()
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.some_attr = "value"  # type: ignore


class TestWorkspaceSpecCurrent:
    """Tests for WorkspaceSpecCurrent - current working directory."""

    def test_workspacespeccurrent_creation_succeeds(self) -> None:
        """WorkspaceSpecCurrent should be creatable without arguments."""
        spec = WorkspaceSpecCurrent()
        assert spec is not None

    def test_workspacespeccurrent_str_representation(self) -> None:
        """WorkspaceSpecCurrent should have correct string representation."""
        spec = WorkspaceSpecCurrent()
        assert str(spec) == "WorkspaceSpec.Current"

    def test_workspacespeccurrent_is_workspacespec_subclass(self) -> None:
        """WorkspaceSpecCurrent should be a subclass of WorkspaceSpec."""
        spec = WorkspaceSpecCurrent()
        assert isinstance(spec, WorkspaceSpec)

    def test_workspacespeccurrent_is_frozen(self) -> None:
        """WorkspaceSpecCurrent should be immutable (frozen dataclass)."""
        spec = WorkspaceSpecCurrent()
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.some_attr = "value"  # type: ignore


class TestWorkspaceSpecProject:
    """Tests for WorkspaceSpecProject - named project reference."""

    def test_workspacespecproject_creation_with_name(self) -> None:
        """WorkspaceSpecProject should be creatable with project name."""
        spec = WorkspaceSpecProject(name="myapp")
        assert spec.name == "myapp"

    def test_workspacespecproject_str_representation(self) -> None:
        """WorkspaceSpecProject should have correct string representation."""
        spec = WorkspaceSpecProject(name="myapp")
        assert str(spec) == "WorkspaceSpec.Project('myapp')"

    def test_workspacespecproject_is_workspacespec_subclass(self) -> None:
        """WorkspaceSpecProject should be a subclass of WorkspaceSpec."""
        spec = WorkspaceSpecProject(name="myapp")
        assert isinstance(spec, WorkspaceSpec)

    def test_workspacespecproject_is_frozen(self) -> None:
        """WorkspaceSpecProject should be immutable (frozen dataclass)."""
        spec = WorkspaceSpecProject(name="myapp")
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.name = "other"


class TestWorkspaceSpecPath:
    """Tests for WorkspaceSpecPath - explicit absolute path."""

    def test_workspacespecpath_creation_with_absolute_path(self) -> None:
        """WorkspaceSpecPath should be creatable with absolute path."""
        spec = WorkspaceSpecPath(path="/home/user/projects/auth")
        assert spec.path == "/home/user/projects/auth"

    def test_workspacespecpath_str_representation(self) -> None:
        """WorkspaceSpecPath should have correct string representation."""
        spec = WorkspaceSpecPath(path="/home/user/projects/auth")
        assert str(spec) == "WorkspaceSpec.Path('/home/user/projects/auth')"

    def test_workspacespecpath_is_workspacespec_subclass(self) -> None:
        """WorkspaceSpecPath should be a subclass of WorkspaceSpec."""
        spec = WorkspaceSpecPath(path="/home/user/projects/auth")
        assert isinstance(spec, WorkspaceSpec)

    def test_workspacespecpath_is_frozen(self) -> None:
        """WorkspaceSpecPath should be immutable (frozen dataclass)."""
        spec = WorkspaceSpecPath(path="/home/user/projects/auth")
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.path = "/other/path"


class TestWorkspaceSpecEncoded:
    """Tests for WorkspaceSpecEncoded - Claude-style encoded path."""

    def test_workspacespecencoded_creation_with_encoded_path(self) -> None:
        """WorkspaceSpecEncoded should be creatable with encoded path."""
        spec = WorkspaceSpecEncoded(encoded="home-user-projects-auth")
        assert spec.encoded == "home-user-projects-auth"

    def test_workspacespecencoded_str_representation(self) -> None:
        """WorkspaceSpecEncoded should have correct string representation."""
        spec = WorkspaceSpecEncoded(encoded="home-user-projects-auth")
        assert str(spec) == "WorkspaceSpec.Encoded('home-user-projects-auth')"

    def test_workspacespecencoded_is_workspacespec_subclass(self) -> None:
        """WorkspaceSpecEncoded should be a subclass of WorkspaceSpec."""
        spec = WorkspaceSpecEncoded(encoded="home-user-projects-auth")
        assert isinstance(spec, WorkspaceSpec)

    def test_workspacespecencoded_is_frozen(self) -> None:
        """WorkspaceSpecEncoded should be immutable (frozen dataclass)."""
        spec = WorkspaceSpecEncoded(encoded="home-user-projects-auth")
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.encoded = "other-path"


class TestWorkspaceSpecPattern:
    """Tests for WorkspaceSpecPattern - pattern with match semantics."""

    def test_workspacespecpattern_creation_with_exact_match(self) -> None:
        """WorkspaceSpecPattern should be creatable with EXACT match type."""
        spec = WorkspaceSpecPattern(pattern="/home/user/projects/auth", match_type=MatchType.EXACT)
        assert spec.pattern == "/home/user/projects/auth"
        assert spec.match_type == MatchType.EXACT

    def test_workspacespecpattern_creation_with_prefix_match(self) -> None:
        """WorkspaceSpecPattern should be creatable with PREFIX match type."""
        spec = WorkspaceSpecPattern(pattern="/home/user/projects/", match_type=MatchType.PREFIX)
        assert spec.pattern == "/home/user/projects/"
        assert spec.match_type == MatchType.PREFIX

    def test_workspacespecpattern_creation_with_contains_match(self) -> None:
        """WorkspaceSpecPattern should be creatable with CONTAINS match type."""
        spec = WorkspaceSpecPattern(pattern="auth", match_type=MatchType.CONTAINS)
        assert spec.pattern == "auth"
        assert spec.match_type == MatchType.CONTAINS

    def test_workspacespecpattern_creation_with_glob_match(self) -> None:
        """WorkspaceSpecPattern should be creatable with GLOB match type."""
        spec = WorkspaceSpecPattern(pattern="*/projects/*", match_type=MatchType.GLOB)
        assert spec.pattern == "*/projects/*"
        assert spec.match_type == MatchType.GLOB

    def test_workspacespecpattern_str_representation_exact(self) -> None:
        """WorkspaceSpecPattern with EXACT should have correct string repr."""
        spec = WorkspaceSpecPattern(pattern="/home/user/projects/auth", match_type=MatchType.EXACT)
        assert str(spec) == "WorkspaceSpec.Pattern('/home/user/projects/auth', exact)"

    def test_workspacespecpattern_str_representation_glob(self) -> None:
        """WorkspaceSpecPattern with GLOB should have correct string repr."""
        spec = WorkspaceSpecPattern(pattern="*/projects/*", match_type=MatchType.GLOB)
        assert str(spec) == "WorkspaceSpec.Pattern('*/projects/*', glob)"

    def test_workspacespecpattern_is_workspacespec_subclass(self) -> None:
        """WorkspaceSpecPattern should be a subclass of WorkspaceSpec."""
        spec = WorkspaceSpecPattern(pattern="/home/user/projects/auth", match_type=MatchType.EXACT)
        assert isinstance(spec, WorkspaceSpec)

    def test_workspacespecpattern_is_frozen(self) -> None:
        """WorkspaceSpecPattern should be immutable (frozen dataclass)."""
        spec = WorkspaceSpecPattern(pattern="/home/user/projects/auth", match_type=MatchType.EXACT)
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.pattern = "other"


class TestWorkspaceSpecHash:
    """Tests for WorkspaceSpecHash - Gemini-style hash reference."""

    def test_workspacespechash_creation_with_hash(self) -> None:
        """WorkspaceSpecHash should be creatable with hash value."""
        spec = WorkspaceSpecHash(hash="abc123def")
        assert spec.hash == "abc123def"

    def test_workspacespechash_str_representation(self) -> None:
        """WorkspaceSpecHash should have correct string representation."""
        spec = WorkspaceSpecHash(hash="abc123def")
        assert str(spec) == "WorkspaceSpec.Hash('abc123def')"

    def test_workspacespechash_is_workspacespec_subclass(self) -> None:
        """WorkspaceSpecHash should be a subclass of WorkspaceSpec."""
        spec = WorkspaceSpecHash(hash="abc123def")
        assert isinstance(spec, WorkspaceSpec)

    def test_workspacespechash_is_frozen(self) -> None:
        """WorkspaceSpecHash should be immutable (frozen dataclass)."""
        spec = WorkspaceSpecHash(hash="abc123def")
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.hash = "other"


class TestWorkspaceSpecConcrete:
    """Tests for WorkspaceSpecConcrete - already-resolved workspace path."""

    def test_workspacespecconcrete_creation_with_path(self) -> None:
        """WorkspaceSpecConcrete should be creatable with concrete path."""
        spec = WorkspaceSpecConcrete(path="/home/user/projects/auth")
        assert spec.path == "/home/user/projects/auth"

    def test_workspacespecconcrete_str_representation(self) -> None:
        """WorkspaceSpecConcrete should have correct string representation."""
        spec = WorkspaceSpecConcrete(path="/home/user/projects/auth")
        assert str(spec) == "WorkspaceSpec.Concrete('/home/user/projects/auth')"

    def test_workspacespecconcrete_is_workspacespec_subclass(self) -> None:
        """WorkspaceSpecConcrete should be a subclass of WorkspaceSpec."""
        spec = WorkspaceSpecConcrete(path="/home/user/projects/auth")
        assert isinstance(spec, WorkspaceSpec)

    def test_workspacespecconcrete_is_frozen(self) -> None:
        """WorkspaceSpecConcrete should be immutable (frozen dataclass)."""
        spec = WorkspaceSpecConcrete(path="/home/user/projects/auth")
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.path = "/other/path"


class TestWorkspaceSpecFactory:
    """Tests for WorkspaceSpecFactory - convenience factory methods."""

    def test_workspacespecfactory_all_returns_workspacespecall(self) -> None:
        """Factory.All should return a WorkspaceSpecAll instance."""
        spec = WorkspaceSpecFactory.All
        assert isinstance(spec, WorkspaceSpecAll)

    def test_workspacespecfactory_current_returns_workspacespeccurrent(self) -> None:
        """Factory.Current should return a WorkspaceSpecCurrent instance."""
        spec = WorkspaceSpecFactory.Current
        assert isinstance(spec, WorkspaceSpecCurrent)

    def test_workspacespecfactory_project_returns_workspacespecproject(self) -> None:
        """Factory.Project() should return a WorkspaceSpecProject instance."""
        spec = WorkspaceSpecFactory.Project("myapp")
        assert isinstance(spec, WorkspaceSpecProject)
        assert spec.name == "myapp"

    def test_workspacespecfactory_path_returns_workspacespecpath(self) -> None:
        """Factory.Path() should return a WorkspaceSpecPath instance."""
        spec = WorkspaceSpecFactory.Path("/home/user/projects/auth")
        assert isinstance(spec, WorkspaceSpecPath)
        assert spec.path == "/home/user/projects/auth"

    def test_workspacespecfactory_encoded_returns_workspacespecencoded(self) -> None:
        """Factory.Encoded() should return a WorkspaceSpecEncoded instance."""
        spec = WorkspaceSpecFactory.Encoded("home-user-projects-auth")
        assert isinstance(spec, WorkspaceSpecEncoded)
        assert spec.encoded == "home-user-projects-auth"

    def test_workspacespecfactory_pattern_returns_workspacespecpattern(self) -> None:
        """Factory.Pattern() should return a WorkspaceSpecPattern instance."""
        spec = WorkspaceSpecFactory.Pattern("/home/user/projects/auth", MatchType.EXACT)
        assert isinstance(spec, WorkspaceSpecPattern)
        assert spec.pattern == "/home/user/projects/auth"
        assert spec.match_type == MatchType.EXACT

    def test_workspacespecfactory_hash_returns_workspacespechash(self) -> None:
        """Factory.Hash() should return a WorkspaceSpecHash instance."""
        spec = WorkspaceSpecFactory.Hash("abc123def")
        assert isinstance(spec, WorkspaceSpecHash)
        assert spec.hash == "abc123def"

    def test_workspacespecfactory_concrete_returns_workspacespecconcrete(self) -> None:
        """Factory.Concrete() should return a WorkspaceSpecConcrete instance."""
        spec = WorkspaceSpecFactory.Concrete("/home/user/projects/auth")
        assert isinstance(spec, WorkspaceSpecConcrete)
        assert spec.path == "/home/user/projects/auth"


# =============================================================================
# SessionFilters Tests
# =============================================================================


class TestSessionFilters:
    """Tests for SessionFilters - criteria for filtering sessions."""

    def test_sessionfilters_default_values_are_none(self) -> None:
        """SessionFilters default values should all be None."""
        filters = SessionFilters()
        assert filters.agent is None
        assert filters.since is None
        assert filters.until is None
        assert filters.min_messages is None

    def test_sessionfilters_with_agent_only(self) -> None:
        """SessionFilters should accept agent filter alone."""
        filters = SessionFilters(agent="claude")
        assert filters.agent == "claude"
        assert filters.since is None
        assert filters.until is None
        assert filters.min_messages is None

    def test_sessionfilters_with_since_only(self) -> None:
        """SessionFilters should accept since filter alone."""
        since_date = datetime(2024, 1, 1)
        filters = SessionFilters(since=since_date)
        assert filters.agent is None
        assert filters.since == since_date
        assert filters.until is None
        assert filters.min_messages is None

    def test_sessionfilters_with_until_only(self) -> None:
        """SessionFilters should accept until filter alone."""
        until_date = datetime(2024, 12, 31)
        filters = SessionFilters(until=until_date)
        assert filters.agent is None
        assert filters.since is None
        assert filters.until == until_date
        assert filters.min_messages is None

    def test_sessionfilters_with_min_messages_only(self) -> None:
        """SessionFilters should accept min_messages filter alone."""
        filters = SessionFilters(min_messages=10)
        assert filters.agent is None
        assert filters.since is None
        assert filters.until is None
        assert filters.min_messages == 10

    def test_sessionfilters_with_all_fields_populated(self) -> None:
        """SessionFilters should accept all fields."""
        since_date = datetime(2024, 1, 1)
        until_date = datetime(2024, 12, 31)
        filters = SessionFilters(
            agent="claude",
            since=since_date,
            until=until_date,
            min_messages=5,
        )
        assert filters.agent == "claude"
        assert filters.since == since_date
        assert filters.until == until_date
        assert filters.min_messages == 5

    def test_sessionfilters_str_representation_empty(self) -> None:
        """SessionFilters with no filters should have clean string repr."""
        filters = SessionFilters()
        assert str(filters) == "SessionFilters()"

    def test_sessionfilters_str_representation_with_agent(self) -> None:
        """SessionFilters with agent should show it in string repr."""
        filters = SessionFilters(agent="claude")
        assert str(filters) == "SessionFilters(agent='claude')"

    def test_sessionfilters_str_representation_with_since(self) -> None:
        """SessionFilters with since should show ISO format in string repr."""
        since_date = datetime(2024, 1, 15, 10, 30, 0)
        filters = SessionFilters(since=since_date)
        assert "since=2024-01-15T10:30:00" in str(filters)

    def test_sessionfilters_str_representation_with_min_messages(self) -> None:
        """SessionFilters with min_messages should show it in string repr."""
        filters = SessionFilters(min_messages=10)
        assert str(filters) == "SessionFilters(min_messages=10)"

    def test_sessionfilters_str_representation_with_multiple_fields(self) -> None:
        """SessionFilters with multiple fields should show all in string repr."""
        filters = SessionFilters(agent="gemini", min_messages=3)
        result = str(filters)
        assert "agent='gemini'" in result
        assert "min_messages=3" in result

    def test_sessionfilters_accepts_different_agents(self) -> None:
        """SessionFilters should accept various agent types."""
        for agent in ["claude", "codex", "gemini"]:
            filters = SessionFilters(agent=agent)
            assert filters.agent == agent


# =============================================================================
# SessionSpec Type Tests
# =============================================================================


class TestSessionSpecAll:
    """Tests for SessionSpecAll - all sessions in workspace."""

    def test_sessionspecall_creation_succeeds(self) -> None:
        """SessionSpecAll should be creatable without arguments."""
        spec = SessionSpecAll()
        assert spec is not None

    def test_sessionspecall_str_representation(self) -> None:
        """SessionSpecAll should have correct string representation."""
        spec = SessionSpecAll()
        assert str(spec) == "SessionSpec.All"

    def test_sessionspecall_is_sessionspec_subclass(self) -> None:
        """SessionSpecAll should be a subclass of SessionSpec."""
        spec = SessionSpecAll()
        assert isinstance(spec, SessionSpec)

    def test_sessionspecall_is_frozen(self) -> None:
        """SessionSpecAll should be immutable (frozen dataclass)."""
        spec = SessionSpecAll()
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.some_attr = "value"  # type: ignore


class TestSessionSpecFiltered:
    """Tests for SessionSpecFiltered - sessions matching filters."""

    def test_sessionspecfiltered_creation_with_filters(self) -> None:
        """SessionSpecFiltered should be creatable with SessionFilters."""
        filters = SessionFilters(agent="claude")
        spec = SessionSpecFiltered(filters=filters)
        assert spec.filters.agent == "claude"

    def test_sessionspecfiltered_str_representation(self) -> None:
        """SessionSpecFiltered should have correct string representation."""
        filters = SessionFilters(agent="claude")
        spec = SessionSpecFiltered(filters=filters)
        assert "SessionSpec.Filtered" in str(spec)
        assert "agent='claude'" in str(spec)

    def test_sessionspecfiltered_is_sessionspec_subclass(self) -> None:
        """SessionSpecFiltered should be a subclass of SessionSpec."""
        spec = SessionSpecFiltered(filters=SessionFilters())
        assert isinstance(spec, SessionSpec)

    def test_sessionspecfiltered_hash_works(self) -> None:
        """SessionSpecFiltered should be hashable for use in sets/dicts."""
        filters = SessionFilters(agent="claude")
        spec = SessionSpecFiltered(filters=filters)
        # Should not raise
        hash_value = hash(spec)
        assert isinstance(hash_value, int)

    def test_sessionspecfiltered_equality_same_filters(self) -> None:
        """SessionSpecFiltered with same filters should be equal."""
        filters1 = SessionFilters(agent="claude", min_messages=5)
        filters2 = SessionFilters(agent="claude", min_messages=5)
        spec1 = SessionSpecFiltered(filters=filters1)
        spec2 = SessionSpecFiltered(filters=filters2)
        assert spec1 == spec2

    def test_sessionspecfiltered_equality_different_filters(self) -> None:
        """SessionSpecFiltered with different filters should not be equal."""
        spec1 = SessionSpecFiltered(filters=SessionFilters(agent="claude"))
        spec2 = SessionSpecFiltered(filters=SessionFilters(agent="gemini"))
        assert spec1 != spec2

    def test_sessionspecfiltered_equality_with_non_filtered(self) -> None:
        """SessionSpecFiltered should not equal non-SessionSpecFiltered."""
        spec = SessionSpecFiltered(filters=SessionFilters())
        assert spec != "not a spec"
        assert spec != 42
        assert spec != SessionSpecAll()


class TestSessionSpecList:
    """Tests for SessionSpecList - concrete list of sessions."""

    def test_sessionspeclist_creation_with_empty_list(self) -> None:
        """SessionSpecList should be creatable with empty list."""
        spec = SessionSpecList(sessions=tuple())
        assert spec.sessions == tuple()

    def test_sessionspeclist_creation_with_sessions(self) -> None:
        """SessionSpecList should be creatable with session data."""
        sessions = ({"id": "sess-1"}, {"id": "sess-2"})
        spec = SessionSpecList(sessions=sessions)
        assert len(spec.sessions) == 2

    def test_sessionspeclist_str_representation(self) -> None:
        """SessionSpecList should show session count in string repr."""
        sessions = ({"id": "sess-1"}, {"id": "sess-2"}, {"id": "sess-3"})
        spec = SessionSpecList(sessions=sessions)
        assert str(spec) == "SessionSpec.List([3 sessions])"

    def test_sessionspeclist_is_sessionspec_subclass(self) -> None:
        """SessionSpecList should be a subclass of SessionSpec."""
        spec = SessionSpecList(sessions=tuple())
        assert isinstance(spec, SessionSpec)

    def test_sessionspeclist_is_frozen(self) -> None:
        """SessionSpecList should be immutable (frozen dataclass)."""
        spec = SessionSpecList(sessions=tuple())
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.sessions = tuple([{"id": "new"}])


class TestSessionSpecByFile:
    """Tests for SessionSpecByFile - session identified by filename."""

    def test_sessionspecbyfile_creation_with_filename(self) -> None:
        """SessionSpecByFile should be creatable with filename."""
        spec = SessionSpecByFile(filename="session-001.jsonl")
        assert spec.filename == "session-001.jsonl"

    def test_sessionspecbyfile_str_representation(self) -> None:
        """SessionSpecByFile should have correct string representation."""
        spec = SessionSpecByFile(filename="session-001.jsonl")
        assert str(spec) == "SessionSpec.ByFile('session-001.jsonl')"

    def test_sessionspecbyfile_is_sessionspec_subclass(self) -> None:
        """SessionSpecByFile should be a subclass of SessionSpec."""
        spec = SessionSpecByFile(filename="session-001.jsonl")
        assert isinstance(spec, SessionSpec)

    def test_sessionspecbyfile_is_frozen(self) -> None:
        """SessionSpecByFile should be immutable (frozen dataclass)."""
        spec = SessionSpecByFile(filename="session-001.jsonl")
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.filename = "other.jsonl"


class TestSessionSpecById:
    """Tests for SessionSpecById - session identified by ID."""

    def test_sessionspecbyid_creation_with_id(self) -> None:
        """SessionSpecById should be creatable with session ID."""
        spec = SessionSpecById(session_id="abc123")
        assert spec.session_id == "abc123"

    def test_sessionspecbyid_str_representation(self) -> None:
        """SessionSpecById should have correct string representation."""
        spec = SessionSpecById(session_id="abc123")
        assert str(spec) == "SessionSpec.ById('abc123')"

    def test_sessionspecbyid_is_sessionspec_subclass(self) -> None:
        """SessionSpecById should be a subclass of SessionSpec."""
        spec = SessionSpecById(session_id="abc123")
        assert isinstance(spec, SessionSpec)

    def test_sessionspecbyid_is_frozen(self) -> None:
        """SessionSpecById should be immutable (frozen dataclass)."""
        spec = SessionSpecById(session_id="abc123")
        with pytest.raises(Exception):  # FrozenInstanceError
            spec.session_id = "other"


class TestSessionSpecFactory:
    """Tests for SessionSpecFactory - convenience factory methods."""

    def test_sessionspecfactory_all_returns_sessionspecall(self) -> None:
        """Factory.All should return a SessionSpecAll instance."""
        spec = SessionSpecFactory.All
        assert isinstance(spec, SessionSpecAll)

    def test_sessionspecfactory_filtered_returns_sessionspecfiltered(self) -> None:
        """Factory.Filtered() should return a SessionSpecFiltered instance."""
        filters = SessionFilters(agent="claude")
        spec = SessionSpecFactory.Filtered(filters)
        assert isinstance(spec, SessionSpecFiltered)
        assert spec.filters.agent == "claude"

    def test_sessionspecfactory_list_returns_sessionspeclist(self) -> None:
        """Factory.List() should return a SessionSpecList instance."""
        sessions: List[Dict[str, Any]] = [{"id": "sess-1"}, {"id": "sess-2"}]
        spec = SessionSpecFactory.List(sessions)
        assert isinstance(spec, SessionSpecList)
        assert len(spec.sessions) == 2

    def test_sessionspecfactory_list_converts_to_tuple(self) -> None:
        """Factory.List() should convert list to tuple for immutability."""
        sessions: List[Dict[str, Any]] = [{"id": "sess-1"}]
        spec = SessionSpecFactory.List(sessions)
        assert isinstance(spec.sessions, tuple)

    def test_sessionspecfactory_byfile_returns_sessionspecbyfile(self) -> None:
        """Factory.ByFile() should return a SessionSpecByFile instance."""
        spec = SessionSpecFactory.ByFile("session-001.jsonl")
        assert isinstance(spec, SessionSpecByFile)
        assert spec.filename == "session-001.jsonl"

    def test_sessionspecfactory_byid_returns_sessionspecbyid(self) -> None:
        """Factory.ById() should return a SessionSpecById instance."""
        spec = SessionSpecFactory.ById("abc123")
        assert isinstance(spec, SessionSpecById)
        assert spec.session_id == "abc123"


# =============================================================================
# Record Type Tests
# =============================================================================


class TestScopeRecord:
    """Tests for ScopeRecord - combines home, workspace, and session specs."""

    def test_scoperecord_creation_with_all_specs(self) -> None:
        """ScopeRecord should be creatable with all three specs."""
        record = ScopeRecord(
            home=HomeSpecFactory.Local,
            workspace=WorkspaceSpecFactory.Current,
            sessions=SessionSpecFactory.All,
        )
        assert isinstance(record.home, HomeSpecLocal)
        assert isinstance(record.workspace, WorkspaceSpecCurrent)
        assert isinstance(record.sessions, SessionSpecAll)

    def test_scoperecord_str_representation(self) -> None:
        """ScopeRecord should have correct string representation."""
        record = ScopeRecord(
            home=HomeSpecFactory.Local,
            workspace=WorkspaceSpecFactory.Current,
            sessions=SessionSpecFactory.All,
        )
        result = str(record)
        assert "ScopeRecord" in result
        assert "HomeSpec.Local" in result
        assert "WorkspaceSpec.Current" in result
        assert "SessionSpec.All" in result

    def test_scoperecord_is_frozen(self) -> None:
        """ScopeRecord should be immutable (frozen dataclass)."""
        record = ScopeRecord(
            home=HomeSpecFactory.Local,
            workspace=WorkspaceSpecFactory.Current,
            sessions=SessionSpecFactory.All,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            record.home = HomeSpecFactory.All  # type: ignore

    def test_scoperecord_with_concrete_specs(self) -> None:
        """ScopeRecord should work with concrete specs."""
        record = ScopeRecord(
            home=HomeSpecFactory.Concrete("local"),
            workspace=WorkspaceSpecFactory.Concrete("/home/user/projects/auth"),
            sessions=SessionSpecFactory.All,
        )
        assert isinstance(record.home, HomeSpecConcrete)
        assert isinstance(record.workspace, WorkspaceSpecConcrete)

    def test_scoperecord_with_filtered_sessions(self) -> None:
        """ScopeRecord should work with filtered session spec."""
        filters = SessionFilters(agent="claude", min_messages=5)
        record = ScopeRecord(
            home=HomeSpecFactory.Local,
            workspace=WorkspaceSpecFactory.Current,
            sessions=SessionSpecFactory.Filtered(filters),
        )
        assert isinstance(record.sessions, SessionSpecFiltered)


class TestProjectRecord:
    """Tests for ProjectRecord - expands to multiple scope records."""

    def test_projectrecord_creation_with_project_name(self) -> None:
        """ProjectRecord should be creatable with just project name."""
        record = ProjectRecord(project="myapp")
        assert record.project == "myapp"

    def test_projectrecord_default_sessions_is_all(self) -> None:
        """ProjectRecord should default to SessionSpecAll."""
        record = ProjectRecord(project="myapp")
        assert isinstance(record.sessions, SessionSpecAll)

    def test_projectrecord_creation_with_custom_sessions(self) -> None:
        """ProjectRecord should accept custom session spec."""
        filters = SessionFilters(agent="claude")
        record = ProjectRecord(
            project="myapp",
            sessions=SessionSpecFiltered(filters),
        )
        assert isinstance(record.sessions, SessionSpecFiltered)

    def test_projectrecord_str_representation(self) -> None:
        """ProjectRecord should have correct string representation."""
        record = ProjectRecord(project="myapp")
        result = str(record)
        assert "ProjectRecord" in result
        assert "project='myapp'" in result
        assert "SessionSpec.All" in result

    def test_projectrecord_is_frozen(self) -> None:
        """ProjectRecord should be immutable (frozen dataclass)."""
        record = ProjectRecord(project="myapp")
        with pytest.raises(Exception):  # FrozenInstanceError
            record.project = "other"


class TestConcreteRecord:
    """Tests for ConcreteRecord - fully-resolved record."""

    def test_concreterecord_creation_with_all_values(self) -> None:
        """ConcreteRecord should be creatable with all values."""
        sessions: List[Dict[str, Any]] = [
            {"id": "sess-1", "messages": 10},
            {"id": "sess-2", "messages": 5},
        ]
        record = ConcreteRecord(
            home="local",
            workspace="/home/user/projects/auth",
            sessions=sessions,
        )
        assert record.home == "local"
        assert record.workspace == "/home/user/projects/auth"
        assert len(record.sessions) == 2

    def test_concreterecord_creation_with_empty_sessions(self) -> None:
        """ConcreteRecord should be creatable with empty sessions list."""
        record = ConcreteRecord(
            home="local",
            workspace="/home/user/projects/auth",
            sessions=[],
        )
        assert record.sessions == []

    def test_concreterecord_str_representation(self) -> None:
        """ConcreteRecord should show session count in string repr."""
        sessions: List[Dict[str, Any]] = [{"id": "sess-1"}, {"id": "sess-2"}]
        record = ConcreteRecord(
            home="local",
            workspace="/home/user/projects/auth",
            sessions=sessions,
        )
        result = str(record)
        assert "ConcreteRecord" in result
        assert "home='local'" in result
        assert "workspace='/home/user/projects/auth'" in result
        assert "[2 sessions]" in result

    def test_concreterecord_with_wsl_home(self) -> None:
        """ConcreteRecord should work with WSL home identifier."""
        record = ConcreteRecord(
            home="wsl:Ubuntu",
            workspace="/home/user/projects/auth",
            sessions=[],
        )
        assert record.home == "wsl:Ubuntu"

    def test_concreterecord_with_remote_home(self) -> None:
        """ConcreteRecord should work with remote home identifier."""
        record = ConcreteRecord(
            home="remote:dev",
            workspace="/home/user/projects/auth",
            sessions=[],
        )
        assert record.home == "remote:dev"

    def test_concreterecord_is_mutable(self) -> None:
        """ConcreteRecord should be mutable (not frozen)."""
        record = ConcreteRecord(
            home="local",
            workspace="/home/user/projects/auth",
            sessions=[],
        )
        # Should not raise - ConcreteRecord is mutable
        record.sessions.append({"id": "new-session"})
        assert len(record.sessions) == 1
