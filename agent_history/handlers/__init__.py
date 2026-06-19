"""Command handlers for the cagelens CLI.

This module provides the handler framework for executing commands:
- VerbHandler: Abstract base class for all command handlers
- CommandResult: Dataclass for handler execution results
- VerbDispatcher: Routes commands to appropriate handlers
- DispatchError: Exception for dispatch failures
- SessionListHandler: Handler for 'session list' command
- WorkspaceListHandler: Handler for 'ws list' command
- HomeListHandler: Handler for 'home list' command
- HomeAddHandler: Handler for 'home add' command
- HomeRemoveHandler: Handler for 'home remove' command
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
from agent_history.handlers.home import HomeAddHandler, HomeRemoveHandler
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
from agent_history.handlers.stubs import (
    HomeExportHandler,
    HomeShowHandler,
    HomeStatsHandler,
    ProjectAddHandler,
    ProjectExportHandler,
    ProjectRemoveHandler,
    SessionShowHandler,
    WorkspaceExportHandler,
    WorkspaceShowHandler,
    WorkspaceStatsHandler,
)
from agent_history.handlers.tag import TagAddHandler, TagListHandler, TagRemoveHandler
from agent_history.handlers.utilities import FetchHandler, InstallHandler, ResetHandler

__all__ = [
    # Base classes
    "CommandResult",
    # Dispatcher
    "DispatchError",
    "FetchHandler",
    "GeminiIndexHandler",
    # Home management handlers
    "HomeAddHandler",
    "HomeExportHandler",
    "HomeListHandler",
    "HomeRemoveHandler",
    "HomeShowHandler",
    "HomeStatsHandler",
    # Utility handlers
    "InstallHandler",
    "ProjectAddHandler",
    "ProjectExportHandler",
    # Project handlers
    "ProjectListHandler",
    "ProjectRemoveHandler",
    "ProjectShowHandler",
    "ProjectStatsHandler",
    "ResetHandler",
    # Export handlers
    "SessionExportHandler",
    # List handlers
    "SessionListHandler",
    # Stub handlers (not yet implemented)
    "SessionShowHandler",
    # Stats handlers
    "SessionStatsHandler",
    "TagAddHandler",
    "TagListHandler",
    "TagRemoveHandler",
    "VerbDispatcher",
    "VerbHandler",
    "WorkspaceExportHandler",
    "WorkspaceListHandler",
    "WorkspaceShowHandler",
    "WorkspaceStatsHandler",
]
