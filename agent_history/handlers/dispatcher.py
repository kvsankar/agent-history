"""Command dispatcher for routing to handlers.

This module provides the VerbDispatcher class that routes incoming
commands to the appropriate verb handler based on the resource and
verb combination (e.g., "session" + "list" -> SessionListHandler).

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from typing import Dict, Optional

from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import CommandRequest
from agent_history.scope.types import ConcreteScope


class DispatchError(Exception):
    """Error dispatching command to handler.

    Raised when no handler is registered for the requested resource/verb
    combination.

    Attributes:
        message: Human-readable error description.
        resource: The resource that was requested (may be None if unknown).
        verb: The verb that was requested (may be None if unknown).
    """

    def __init__(self, message: str, resource: Optional[str] = None, verb: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.resource = resource
        self.verb = verb


class VerbDispatcher:
    """Dispatch commands to appropriate verb handlers.

    The dispatcher maintains a registry of handlers keyed by resource
    and verb. When dispatch() is called, it looks up the appropriate
    handler and delegates execution to it.

    Handlers are registered using the register() method, typically at
    application startup.

    Example:
        dispatcher = VerbDispatcher()
        dispatcher.register("session", "list", SessionListHandler())
        dispatcher.register("session", "export", SessionExportHandler())
        dispatcher.register("session", "stats", SessionStatsHandler())

        # Later, dispatch a command
        result = dispatcher.dispatch(request, scope)

    Attributes:
        _handlers: Nested dictionary mapping resource -> verb -> handler.
    """

    def __init__(self):
        """Initialize the dispatcher with an empty handler registry."""
        self._handlers: Dict[str, Dict[str, VerbHandler]] = {}

    def register(self, resource: str, verb: str, handler: VerbHandler) -> None:
        """Register a handler for a resource/verb combination.

        Args:
            resource: The resource type (e.g., "session", "project", "ws").
            verb: The verb/action (e.g., "list", "export", "stats", "show").
            handler: The VerbHandler instance to handle this combination.

        Note:
            If a handler is already registered for this combination,
            it will be replaced with the new handler.
        """
        if resource not in self._handlers:
            self._handlers[resource] = {}
        self._handlers[resource][verb] = handler

    def dispatch(self, request: CommandRequest, scope: ConcreteScope) -> CommandResult:
        """Dispatch command to the appropriate handler.

        Looks up the handler for the request's resource/verb combination
        and delegates execution to it.

        Args:
            request: Parsed command request containing resource, verb,
                and arguments.
            scope: Resolved concrete scope containing the sessions
                to operate on.

        Returns:
            CommandResult from the handler's execute() method.

        Raises:
            DispatchError: If no handler is registered for the resource
                or the resource/verb combination.
        """
        resource_handlers = self._handlers.get(request.resource)
        if not resource_handlers:
            raise DispatchError(f"Unknown resource: {request.resource}", resource=request.resource)

        handler = resource_handlers.get(request.verb)
        if not handler:
            available_verbs = list(resource_handlers.keys())
            raise DispatchError(
                f"Unknown verb '{request.verb}' for resource '{request.resource}'. "
                f"Available verbs: {', '.join(available_verbs)}",
                resource=request.resource,
                verb=request.verb,
            )

        return handler.execute(scope, request.verb_args, request.output_args)

    def get_handler(self, resource: str, verb: str) -> Optional[VerbHandler]:
        """Get handler for a resource/verb combination.

        This method is primarily useful for testing and introspection.

        Args:
            resource: The resource type to look up.
            verb: The verb to look up.

        Returns:
            The registered VerbHandler, or None if not found.
        """
        return self._handlers.get(resource, {}).get(verb)

    def list_resources(self) -> list:
        """List all registered resources.

        Returns:
            List of resource names that have handlers registered.
        """
        return list(self._handlers.keys())

    def list_verbs(self, resource: str) -> list:
        """List all registered verbs for a resource.

        Args:
            resource: The resource to list verbs for.

        Returns:
            List of verb names registered for the resource,
            or empty list if resource is not registered.
        """
        return list(self._handlers.get(resource, {}).keys())
