"""agent-history: Browse and export AI coding assistant conversation history.

This package provides tools for managing conversation sessions from:
- Claude Code
- Codex CLI
- Gemini CLI

Main entry points:
- python -m agent_history: Run the CLI
- agent_history.cli.main(): Programmatic entry point

Key components:
- cli: Command line interface (parser, orchestrator)
- scope: Scope resolution (types, context, resolver)
- handlers: Command handlers (list, export, stats)
- backends: Session scanning (claude, codex, gemini)
- output: Output formatting (table, json, tsv)
- storage: Configuration management
- utils: Utility functions (paths, platform)
"""

__version__ = "2.0.0"

# Re-export key classes for convenience
from agent_history.cli import CLIParser, CommandOrchestrator, main
from agent_history.handlers import (
    CommandResult,
    DispatchError,
    SessionExportHandler,
    SessionListHandler,
    VerbDispatcher,
    VerbHandler,
    WorkspaceListHandler,
)
from agent_history.output import OutputFormatter
from agent_history.scope.context import (
    CommandRequest,
    ContextBuilder,
    OutputArgs,
    ResolutionContext,
    ResolutionResult,
    ScopeArgs,
)
from agent_history.scope.resolver import ScopeResolver
from agent_history.scope.types import (
    ConcreteRecord,
    ConcreteScope,
    HomeSpec,
    MatchType,
    SessionSpec,
    WorkspaceSpec,
)
from agent_history.types import (
    ContentBlock,
    HomeDict,
    MessageDict,
    MetricsDict,
    ProjectDict,
    SessionDict,
    StatsDict,
    WorkspaceDict,
    WorkspaceSessionsMap,
)

__all__ = [
    # Version
    "__version__",
    # CLI
    "CLIParser",
    "CommandOrchestrator",
    "main",
    # Context
    "CommandRequest",
    "ContextBuilder",
    "OutputArgs",
    "ResolutionContext",
    "ResolutionResult",
    "ScopeArgs",
    # Resolver
    "ScopeResolver",
    # Scope Types
    "ConcreteRecord",
    "ConcreteScope",
    "HomeSpec",
    "MatchType",
    "SessionSpec",
    "WorkspaceSpec",
    # Dict Type Aliases
    "ContentBlock",
    "HomeDict",
    "MessageDict",
    "MetricsDict",
    "ProjectDict",
    "SessionDict",
    "StatsDict",
    "WorkspaceDict",
    "WorkspaceSessionsMap",
    # Handlers
    "CommandResult",
    "DispatchError",
    "SessionExportHandler",
    "SessionListHandler",
    "VerbDispatcher",
    "VerbHandler",
    "WorkspaceListHandler",
    # Output
    "OutputFormatter",
]
