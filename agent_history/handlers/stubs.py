"""Stub handlers for not-yet-implemented commands.

These handlers exist to satisfy the CLI interface requirements but
return "not implemented" results. They are placeholders for future
implementation.
"""

from typing import Any, Dict

from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope


class NotImplementedHandler(VerbHandler):
    """Base class for stub handlers that return "not implemented" results.

    Subclasses only need to override the class attributes to customize
    the error message.
    """

    resource: str = "unknown"
    verb: str = "unknown"

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """Return a "not implemented" result.

        Args:
            scope: Resolved scope (unused).
            verb_args: Verb arguments (unused).
            output_args: Output options (unused).

        Returns:
            CommandResult with success=False and "not implemented" message.
        """
        return CommandResult(
            success=False,
            data={"error": "not_implemented"},
            data_type="error",
            metadata={
                "message": f"The '{self.resource} {self.verb}' command is not yet implemented.",
            },
        )


class SessionShowHandler(NotImplementedHandler):
    """Stub handler for 'session show' command."""

    resource = "session"
    verb = "show"


class WorkspaceShowHandler(NotImplementedHandler):
    """Stub handler for 'ws show' command."""

    resource = "ws"
    verb = "show"


class WorkspaceExportHandler(NotImplementedHandler):
    """Stub handler for 'ws export' command."""

    resource = "ws"
    verb = "export"


class WorkspaceStatsHandler(NotImplementedHandler):
    """Stub handler for 'ws stats' command."""

    resource = "ws"
    verb = "stats"


class HomeShowHandler(NotImplementedHandler):
    """Stub handler for 'home show' command."""

    resource = "home"
    verb = "show"


class HomeExportHandler(NotImplementedHandler):
    """Stub handler for 'home export' command."""

    resource = "home"
    verb = "export"


class HomeStatsHandler(NotImplementedHandler):
    """Stub handler for 'home stats' command."""

    resource = "home"
    verb = "stats"


class ProjectAddHandler(NotImplementedHandler):
    """Stub handler for 'project add' command."""

    resource = "project"
    verb = "add"


class ProjectRemoveHandler(NotImplementedHandler):
    """Stub handler for 'project remove' command."""

    resource = "project"
    verb = "remove"


class ProjectExportHandler(NotImplementedHandler):
    """Stub handler for 'project export' command."""

    resource = "project"
    verb = "export"
