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

# Fluent API
from agent_history.fluent import Context, FluentContext, context
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
    "CLIParser",
    "CommandOrchestrator",
    "CommandRequest",
    "CommandResult",
    "ConcreteRecord",
    "ConcreteScope",
    "ContentBlock",
    "Context",
    "ContextBuilder",
    "DispatchError",
    "FluentContext",
    "HomeDict",
    "HomeSpec",
    "MatchType",
    "MessageDict",
    "MetricsDict",
    "OutputArgs",
    "OutputFormatter",
    "ProjectDict",
    "ResolutionContext",
    "ResolutionResult",
    "ScopeArgs",
    "ScopeResolver",
    "SessionDict",
    "SessionExportHandler",
    "SessionListHandler",
    "SessionSpec",
    "StatsDict",
    "VerbDispatcher",
    "VerbHandler",
    "WorkspaceDict",
    "WorkspaceListHandler",
    "WorkspaceSessionsMap",
    "WorkspaceSpec",
    "__version__",
    "context",
    "main",
]
