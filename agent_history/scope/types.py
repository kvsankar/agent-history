"""
Type system for the v2 scope resolution architecture.

This module defines the core types used throughout the scope resolution pipeline:
- Specification types (HomeSpec, WorkspaceSpec, SessionSpec) - how users express intent
- Record types (ScopeRecord, ProjectRecord, ConcreteRecord) - how scopes are structured
- Supporting types (MatchType, SessionFilters) - configuration and matching

The key architectural principle is separation of concerns:
- Specifications capture user intent (may be symbolic, pattern-based, or concrete)
- Resolution converts specifications to concrete values using context
- Expansion breaks one record into multiple when a specification matches multiple items
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

# =============================================================================
# Match Types
# =============================================================================


class MatchType(Enum):
    """
    Defines how workspace patterns are matched against actual workspaces.

    This is CRITICAL for fixing the original bug where substring matching
    caused /home/user/projects/auth to match /home/user/projects/auth-infra.
    """

    EXACT = "exact"
    """Exact equality: workspace == pattern. This is the default and safest option."""

    PREFIX = "prefix"
    """Prefix matching: workspace.startswith(pattern). Useful for directory hierarchies."""

    CONTAINS = "contains"
    """Substring matching: pattern in workspace. The OLD BUGGY behavior - use sparingly!"""

    GLOB = "glob"
    """Glob/fnmatch-style matching: fnmatch.fnmatch(workspace, pattern). For wildcards."""

    def __str__(self) -> str:
        return self.value


# =============================================================================
# Home Specification
# =============================================================================


class HomeSpec(ABC):
    """
    Abstract base class for home specifications.

    A HomeSpec describes which home(s) to include in scope resolution.
    Homes can be: local, WSL distros (wsl:Ubuntu), Windows users (windows:alice),
    or remote connections (remote:server).

    Subclasses represent different ways users can specify homes:
    - All: All available homes
    - Local: Just the local home
    - Current: The home containing the current working directory
    - Category: All homes of a category (wsl, windows, remote)
    - CategoryItem: A specific home within a category
    - Concrete: An already-resolved home string
    """

    @abstractmethod
    def __str__(self) -> str:
        """Return a human-readable string representation."""
        pass


@dataclass(frozen=True)
class HomeSpecAll(HomeSpec):
    """All available homes (--ah flag)."""

    def __str__(self) -> str:
        return "HomeSpec.All"


@dataclass(frozen=True)
class HomeSpecLocal(HomeSpec):
    """Local home only (default when no flags specified)."""

    def __str__(self) -> str:
        return "HomeSpec.Local"


@dataclass(frozen=True)
class HomeSpecCurrent(HomeSpec):
    """Home containing the current working directory."""

    def __str__(self) -> str:
        return "HomeSpec.Current"


@dataclass(frozen=True)
class HomeSpecCategory(HomeSpec):
    """
    All homes of a category.

    Examples:
        HomeSpecCategory("wsl")     # All WSL distros
        HomeSpecCategory("windows") # All Windows users
        HomeSpecCategory("remote")  # All configured remote connections
    """

    category: str

    def __str__(self) -> str:
        return f"HomeSpec.Category({self.category!r})"


@dataclass(frozen=True)
class HomeSpecCategoryItem(HomeSpec):
    """
    A specific home within a category.

    Examples:
        HomeSpecCategoryItem("wsl", "Ubuntu")   # wsl:Ubuntu
        HomeSpecCategoryItem("remote", "dev")   # remote:dev
        HomeSpecCategoryItem("windows", "alice") # windows:alice
    """

    category: str
    item: str

    def __str__(self) -> str:
        return f"HomeSpec.CategoryItem({self.category!r}, {self.item!r})"


@dataclass(frozen=True)
class HomeSpecConcrete(HomeSpec):
    """
    An already-resolved home string.

    This is the result of resolution - a concrete home identifier like
    "local", "wsl:Ubuntu", "remote:dev", etc.
    """

    home: str

    def __str__(self) -> str:
        return f"HomeSpec.Concrete({self.home!r})"


@dataclass(frozen=True)
class HomeSpecMultiple(HomeSpec):
    """
    Multiple explicit home names (--home flag used multiple times).

    This preserves all home names when the user specifies multiple --home values.

    Examples:
        HomeSpecMultiple(("local", "remote:vm01"))  # Two explicit homes
        HomeSpecMultiple(("wsl:Ubuntu", "wsl:Debian"))  # Multiple WSL distros
    """

    homes: tuple  # Using tuple for immutability (frozen=True requires hashable)

    def __str__(self) -> str:
        return f"HomeSpec.Multiple({list(self.homes)!r})"


# Convenience namespace for creating HomeSpec instances
class HomeSpecFactory:
    """Factory for creating HomeSpec instances with a clean API."""

    All: HomeSpec = HomeSpecAll()
    Local: HomeSpec = HomeSpecLocal()
    Current: HomeSpec = HomeSpecCurrent()

    @staticmethod
    def Category(category: str) -> HomeSpec:
        return HomeSpecCategory(category)

    @staticmethod
    def CategoryItem(category: str, item: str) -> HomeSpec:
        return HomeSpecCategoryItem(category, item)

    @staticmethod
    def Concrete(home: str) -> HomeSpec:
        return HomeSpecConcrete(home)

    @staticmethod
    def Multiple(homes: List[str]) -> HomeSpec:
        return HomeSpecMultiple(tuple(homes))


# =============================================================================
# Workspace Specification
# =============================================================================


class WorkspaceSpec(ABC):
    """
    Abstract base class for workspace specifications.

    A WorkspaceSpec describes which workspace(s) to include in scope resolution.
    Workspaces are directories where coding sessions take place.

    Subclasses represent different ways users can specify workspaces:
    - All: All workspaces in the home
    - Current: The current working directory
    - Project: A named project (expands to multiple workspaces)
    - Path: An explicit absolute path
    - Encoded: Claude-style encoded path (e.g., home-user-projects-auth)
    - Pattern: A pattern with specified match semantics
    - Hash: Gemini-style hash reference
    - Concrete: An already-resolved workspace path
    """

    @abstractmethod
    def __str__(self) -> str:
        """Return a human-readable string representation."""
        pass


@dataclass(frozen=True)
class WorkspaceSpecAll(WorkspaceSpec):
    """All workspaces in the home (--aw flag)."""

    def __str__(self) -> str:
        return "WorkspaceSpec.All"


@dataclass(frozen=True)
class WorkspaceSpecCurrent(WorkspaceSpec):
    """Current working directory as the workspace."""

    def __str__(self) -> str:
        return "WorkspaceSpec.Current"


@dataclass(frozen=True)
class WorkspaceSpecProject(WorkspaceSpec):
    """
    A project reference that will expand to multiple workspaces.

    Projects are named collections of workspaces defined in configuration.
    A project might include the same logical project across multiple homes.

    Example:
        WorkspaceSpecProject("myapp")  # Expands to all workspaces in project "myapp"
    """

    name: str

    def __str__(self) -> str:
        return f"WorkspaceSpec.Project({self.name!r})"


@dataclass(frozen=True)
class WorkspaceSpecPath(WorkspaceSpec):
    """
    An explicit absolute path to a workspace.

    Example:
        WorkspaceSpecPath("/home/user/projects/auth")
    """

    path: str

    def __str__(self) -> str:
        return f"WorkspaceSpec.Path({self.path!r})"


@dataclass(frozen=True)
class WorkspaceSpecEncoded(WorkspaceSpec):
    """
    Claude-style encoded workspace path.

    Claude stores workspace directories with slashes replaced by hyphens.
    Example: /home/user/projects/auth becomes home-user-projects-auth

    Example:
        WorkspaceSpecEncoded("home-user-projects-auth")
    """

    encoded: str

    def __str__(self) -> str:
        return f"WorkspaceSpec.Encoded({self.encoded!r})"


@dataclass(frozen=True)
class WorkspaceSpecPattern(WorkspaceSpec):
    """
    A pattern with specified match semantics.

    This allows flexible matching while being explicit about the match type,
    which is critical for avoiding the substring matching bug.

    Examples:
        WorkspaceSpecPattern("/home/user/projects/auth", MatchType.EXACT)
        WorkspaceSpecPattern("auth", MatchType.CONTAINS)  # Old buggy behavior
        WorkspaceSpecPattern("*/projects/*", MatchType.GLOB)
    """

    pattern: str
    match_type: MatchType

    def __str__(self) -> str:
        return f"WorkspaceSpec.Pattern({self.pattern!r}, {self.match_type})"


@dataclass(frozen=True)
class WorkspaceSpecHash(WorkspaceSpec):
    """
    Gemini-style hash reference.

    Gemini uses hash-based workspace identifiers in its index.

    Example:
        WorkspaceSpecHash("abc123def")
    """

    hash: str

    def __str__(self) -> str:
        return f"WorkspaceSpec.Hash({self.hash!r})"


@dataclass(frozen=True)
class WorkspaceSpecConcrete(WorkspaceSpec):
    """
    An already-resolved workspace path.

    This is the result of resolution - a concrete absolute path.
    """

    path: str

    def __str__(self) -> str:
        return f"WorkspaceSpec.Concrete({self.path!r})"


# Convenience namespace for creating WorkspaceSpec instances
class WorkspaceSpecFactory:
    """Factory for creating WorkspaceSpec instances with a clean API."""

    All: WorkspaceSpec = WorkspaceSpecAll()
    Current: WorkspaceSpec = WorkspaceSpecCurrent()

    @staticmethod
    def Project(name: str) -> WorkspaceSpec:
        return WorkspaceSpecProject(name)

    @staticmethod
    def Path(path: str) -> WorkspaceSpec:
        return WorkspaceSpecPath(path)

    @staticmethod
    def Encoded(encoded: str) -> WorkspaceSpec:
        return WorkspaceSpecEncoded(encoded)

    @staticmethod
    def Pattern(pattern: str, match_type: MatchType) -> WorkspaceSpec:
        return WorkspaceSpecPattern(pattern, match_type)

    @staticmethod
    def Hash(hash: str) -> WorkspaceSpec:
        return WorkspaceSpecHash(hash)

    @staticmethod
    def Concrete(path: str) -> WorkspaceSpec:
        return WorkspaceSpecConcrete(path)


# =============================================================================
# Session Filters
# =============================================================================


@dataclass
class SessionFilters:
    """
    Filters to apply when collecting sessions.

    These filters narrow down which sessions are included in the scope.
    All filters are optional; None means no filtering on that attribute.
    """

    agent: Optional[str] = None
    """Agent type: "claude", "codex", "gemini", or None for all agents."""

    since: Optional[datetime] = None
    """Include only sessions after this datetime."""

    until: Optional[datetime] = None
    """Include only sessions before this datetime."""

    min_messages: Optional[int] = None
    """Include only sessions with at least this many messages."""

    def __str__(self) -> str:
        parts = []
        if self.agent:
            parts.append(f"agent={self.agent!r}")
        if self.since:
            parts.append(f"since={self.since.isoformat()}")
        if self.until:
            parts.append(f"until={self.until.isoformat()}")
        if self.min_messages is not None:
            parts.append(f"min_messages={self.min_messages}")
        return f"SessionFilters({', '.join(parts)})"


# =============================================================================
# Session Specification
# =============================================================================


class SessionSpec(ABC):
    """
    Abstract base class for session specifications.

    A SessionSpec describes which session(s) to include within a workspace.

    Subclasses represent different ways users can specify sessions:
    - All: All sessions in the workspace
    - Filtered: Sessions matching specific filters
    - List: A concrete list of sessions
    - ByFile: A single session by filename
    - ById: A single session by ID
    """

    @abstractmethod
    def __str__(self) -> str:
        """Return a human-readable string representation."""
        pass


@dataclass(frozen=True)
class SessionSpecAll(SessionSpec):
    """All sessions in the workspace."""

    def __str__(self) -> str:
        return "SessionSpec.All"


@dataclass(frozen=True)
class SessionSpecFiltered(SessionSpec):
    """
    Sessions matching specific filters.

    Example:
        SessionSpecFiltered(SessionFilters(agent="claude", since=datetime(2024, 1, 1)))
    """

    filters: SessionFilters

    def __str__(self) -> str:
        return f"SessionSpec.Filtered({self.filters})"

    def __hash__(self) -> int:
        # Custom hash since SessionFilters is not frozen
        return hash(
            (
                self.filters.agent,
                self.filters.since,
                self.filters.until,
                self.filters.min_messages,
            )
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SessionSpecFiltered):
            return False
        return (
            self.filters.agent == other.filters.agent
            and self.filters.since == other.filters.since
            and self.filters.until == other.filters.until
            and self.filters.min_messages == other.filters.min_messages
        )


@dataclass(frozen=True)
class SessionSpecList(SessionSpec):
    """
    A concrete list of sessions.

    This is typically used when sessions have already been collected
    and we want to pass them through the pipeline.
    """

    sessions: tuple  # Using tuple for immutability (frozen=True requires hashable)

    def __str__(self) -> str:
        return f"SessionSpec.List([{len(self.sessions)} sessions])"


@dataclass(frozen=True)
class SessionSpecByFile(SessionSpec):
    """
    A single session identified by filename.

    Example:
        SessionSpecByFile("session-001.jsonl")
    """

    filename: str

    def __str__(self) -> str:
        return f"SessionSpec.ByFile({self.filename!r})"


@dataclass(frozen=True)
class SessionSpecById(SessionSpec):
    """
    A single session identified by session ID.

    Example:
        SessionSpecById("abc123")
    """

    session_id: str

    def __str__(self) -> str:
        return f"SessionSpec.ById({self.session_id!r})"


# Convenience namespace for creating SessionSpec instances
class SessionSpecFactory:
    """Factory for creating SessionSpec instances with a clean API."""

    All: SessionSpec = SessionSpecAll()

    @staticmethod
    def Filtered(filters: SessionFilters) -> SessionSpec:
        return SessionSpecFiltered(filters)

    @staticmethod
    def List(sessions: List[Any]) -> SessionSpec:
        return SessionSpecList(tuple(sessions))

    @staticmethod
    def ByFile(filename: str) -> SessionSpec:
        return SessionSpecByFile(filename)

    @staticmethod
    def ById(session_id: str) -> SessionSpec:
        return SessionSpecById(session_id)


# =============================================================================
# Record Types
# =============================================================================


@dataclass(frozen=True)
class ScopeRecord:
    """
    A scope record combining home, workspace, and session specifications.

    This is the primary record type in the template scope. It captures
    user intent about which sessions to include across homes and workspaces.

    Example:
        ScopeRecord(
            home=HomeSpecFactory.Local,
            workspace=WorkspaceSpecFactory.Current,
            sessions=SessionSpecFactory.All,
        )
    """

    home: HomeSpec
    workspace: WorkspaceSpec
    sessions: SessionSpec

    def __str__(self) -> str:
        return (
            f"ScopeRecord(home={self.home}, workspace={self.workspace}, sessions={self.sessions})"
        )


@dataclass(frozen=True)
class ProjectRecord:
    """
    A project record that expands to multiple scope records.

    Projects are named collections of workspaces. A ProjectRecord is
    expanded during resolution to ScopeRecords for each workspace
    in the project definition.

    Example:
        ProjectRecord("myapp")  # Expands to all workspaces in project "myapp"
        ProjectRecord("myapp", SessionSpecFiltered(SessionFilters(agent="claude")))
    """

    project: str
    sessions: SessionSpec = field(default_factory=lambda: SessionSpecAll())

    def __str__(self) -> str:
        return f"ProjectRecord(project={self.project!r}, sessions={self.sessions})"


@dataclass
class ConcreteRecord:
    """
    A fully-resolved record with concrete values.

    This is the output of the resolution pipeline. All specifications
    have been resolved to actual values.

    Attributes:
        home: Concrete home identifier (e.g., "local", "wsl:Ubuntu")
        workspace: Full absolute workspace path
        sessions: List of actual session dictionaries
    """

    home: str
    workspace: str
    sessions: List[Dict[str, Any]]
    workspace_key: Optional[str] = None
    workspace_display: Optional[str] = None

    def __str__(self) -> str:
        return f"ConcreteRecord(home={self.home!r}, workspace={self.workspace!r}, sessions=[{len(self.sessions)} sessions])"


# =============================================================================
# Type Aliases
# =============================================================================

# A template scope contains records that may need resolution
TemplateScope = List[Union[ScopeRecord, ProjectRecord]]
"""
Template scope: contains specifications that need resolution.

This is the input to the resolution pipeline. Records may contain
symbolic specifications like HomeSpec.All or WorkspaceSpec.Current
that need to be resolved against the runtime context.
"""

# A concrete scope contains fully-resolved records
ConcreteScope = List[ConcreteRecord]
"""
Concrete scope: contains fully-resolved records.

This is the output of the resolution pipeline. All specifications
have been resolved to actual values, and sessions have been collected.
"""
