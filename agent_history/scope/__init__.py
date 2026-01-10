"""
Scope resolution module for agent-history.

This module provides the 4-stage scope resolution pipeline that converts
user scope specifications into concrete (home, workspace, sessions) tuples.

Main Components:
- ScopeResolver: Main orchestrator for the resolution pipeline
- ResolutionContext: Environment and configuration context
- ScopeArgs: Parsed command-line arguments
- ResolutionResult: Pipeline output with resolved scope and errors

Stage Modules (agent_history.scope.stages):
- ProjectStage: Stage 1 - Expand project references
- HomeStage: Stage 2 - Resolve home specifications
- WorkspaceStage: Stage 3 - Resolve workspace patterns
- SessionStage: Stage 4 - Collect sessions

Supporting Modules:
- cache: SessionCache for efficient session loading
- home_resolver: Strategy pattern for home-specific path resolution
- types: Type definitions for scope specifications
"""

from agent_history.scope.cache import SessionCache
from agent_history.scope.context import (
    ContextBuilder,
    ResolutionContext,
    ResolutionError,
    ResolutionResult,
    ScopeArgs,
)
from agent_history.scope.home_resolver import (
    HomeResolver,
    LocalHomeResolver,
    RemoteHomeResolver,
    WindowsHomeResolver,
    WSLHomeResolver,
    get_resolver_for_home,
)
from agent_history.scope.resolver import ScopeResolver
from agent_history.scope.stages import HomeStage, ProjectStage, SessionStage, WorkspaceStage
from agent_history.scope.types import (
    ConcreteRecord,
    ConcreteScope,
    HomeSpec,
    HomeSpecFactory,
    MatchType,
    ProjectRecord,
    ScopeRecord,
    SessionFilters,
    SessionSpec,
    SessionSpecFactory,
    TemplateScope,
    WorkspaceSpec,
    WorkspaceSpecFactory,
)

__all__ = [
    # Main resolver
    "ScopeResolver",
    # Context and results
    "ResolutionContext",
    "ResolutionError",
    "ResolutionResult",
    "ScopeArgs",
    "ContextBuilder",
    # Stage modules
    "ProjectStage",
    "HomeStage",
    "WorkspaceStage",
    "SessionStage",
    # Cache
    "SessionCache",
    # Home resolvers
    "HomeResolver",
    "LocalHomeResolver",
    "WSLHomeResolver",
    "WindowsHomeResolver",
    "RemoteHomeResolver",
    "get_resolver_for_home",
    # Types
    "ConcreteRecord",
    "ConcreteScope",
    "HomeSpec",
    "HomeSpecFactory",
    "MatchType",
    "ProjectRecord",
    "ScopeRecord",
    "SessionFilters",
    "SessionSpec",
    "SessionSpecFactory",
    "TemplateScope",
    "WorkspaceSpec",
    "WorkspaceSpecFactory",
]
