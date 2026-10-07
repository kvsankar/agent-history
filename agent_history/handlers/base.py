"""Base classes for command handlers.

This module defines the abstract base class for verb handlers and the
CommandResult dataclass that all handlers return. Handlers implement
the execute() method to perform command-specific logic on a resolved
concrete scope.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List

from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope


@dataclass
class CommandResult:
    """Result of command execution.

    This dataclass captures the outcome of executing a verb handler,
    including the command-specific data, status, and any messages.

    Attributes:
        success: Whether the command completed successfully.
        data: Command-specific result data (e.g., session list, stats dict).
        data_type: Type hint for the output formatter to determine rendering.
            Common values: "session_list", "stats", "project_details",
            "exported_files", "workspace_list".
        metadata: Additional context about the result (e.g., counts, homes).
        errors: List of error messages encountered during execution.
        warnings: List of warning messages (non-fatal issues).
    """

    success: bool
    data: Any
    data_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Ensure mutable defaults are properly initialized."""
        if self.metadata is None:
            self.metadata = {}
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class VerbHandler(ABC):
    """Abstract base class for verb handlers.

    Verb handlers implement command-specific logic for operations like
    listing sessions, exporting data, computing statistics, etc.

    Each handler receives a resolved ConcreteScope containing the actual
    sessions to operate on, along with verb-specific arguments and
    output formatting options.

    Subclasses must implement the execute() method to perform their
    specific operation.

    Example:
        class SessionListHandler(VerbHandler):
            def execute(
                self,
                scope: ConcreteScope,
                verb_args: Dict[str, Any],
                output_args: OutputArgs
            ) -> CommandResult:
                sessions = []
                for record in scope:
                    for session in record.sessions:
                        session['home'] = record.home
                        sessions.append(session)
                return CommandResult(
                    success=True,
                    data=sessions,
                    data_type='session_list',
                    metadata={'total_count': len(sessions)}
                )
    """

    @abstractmethod
    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """Execute the verb on the given scope.

        Args:
            scope: Resolved concrete scope containing sessions to process.
                Each ConcreteRecord in the scope has:
                - home: string identifier (e.g., "local", "wsl:Ubuntu")
                - workspace: absolute path string
                - sessions: list of session dictionaries
            verb_args: Verb-specific arguments extracted from the command line.
                The contents depend on the verb (e.g., export options for
                SessionExportHandler, display options for SessionShowHandler).
            output_args: Output formatting options from the command line.
                Includes format type, output path, quiet mode, etc.

        Returns:
            CommandResult containing:
            - success: bool indicating if execution succeeded
            - data: the command-specific result data
            - data_type: string hint for the output formatter
            - metadata: optional additional context
            - errors: list of any error messages
            - warnings: list of any warning messages
        """
        pass
