"""Command handlers for the agent-history CLI.

This module provides the handler framework for executing commands:
- VerbHandler: Abstract base class for all command handlers
- CommandResult: Dataclass for handler execution results
- VerbDispatcher: Routes commands to appropriate handlers
- DispatchError: Exception for dispatch failures
- SessionListHandler: Handler for 'session list' command
- WorkspaceListHandler: Handler for 'ws list' command
- HomeListHandler: Handler for 'home list' command
- GeminiIndexHandler: Handler for 'gemini-index' command
- SessionExportHandler: Handler for 'session export' command
- SessionStatsHandler: Handler for 'session stats' command
- ProjectListHandler: Handler for 'project list' command
- ProjectShowHandler: Handler for 'project show' command
- ProjectStatsHandler: Handler for 'project stats' command
"""

from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.handlers.dispatcher import DispatchError, VerbDispatcher
from agent_history.handlers.export import SessionExportHandler
from agent_history.handlers.list import (
    GeminiIndexHandler,
    HomeListHandler,
    SessionListHandler,
    WorkspaceListHandler,
)
from agent_history.handlers.project import (
    ProjectListHandler,
    ProjectShowHandler,
    ProjectStatsHandler,
)
from agent_history.handlers.stats import SessionStatsHandler

__all__ = [
    # Base classes
    "CommandResult",
    "VerbHandler",
    # Dispatcher
    "DispatchError",
    "VerbDispatcher",
    # List handlers
    "SessionListHandler",
    "WorkspaceListHandler",
    "HomeListHandler",
    "GeminiIndexHandler",
    # Export handlers
    "SessionExportHandler",
    # Stats handlers
    "SessionStatsHandler",
    # Project handlers
    "ProjectListHandler",
    "ProjectShowHandler",
    "ProjectStatsHandler",
]
