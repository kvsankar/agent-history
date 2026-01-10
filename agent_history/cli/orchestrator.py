"""Command orchestrator for agent-history CLI.

This module provides the CommandOrchestrator class that coordinates the
full command pipeline: parsing, context building, scope resolution,
handler dispatch, and output formatting.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from __future__ import annotations

import sys
import traceback
from typing import List, Optional

from agent_history.cli.parser import CLIParser
from agent_history.handlers import (
    CommandResult,
    DispatchError,
    GeminiIndexHandler,
    HomeListHandler,
    ProjectListHandler,
    ProjectShowHandler,
    ProjectStatsHandler,
    SessionExportHandler,
    SessionListHandler,
    SessionStatsHandler,
    VerbDispatcher,
    WorkspaceListHandler,
)
from agent_history.output.formatter import FormatterError, OutputFormatter
from agent_history.scope.context import (
    CommandRequest,
    ContextBuilder,
    ResolutionContext,
    ResolutionResult,
)
from agent_history.scope.resolver import ScopeResolver
from agent_history.storage.metrics import (
    init_metrics_db,
    sync_sessions_to_db,
)


class ErrorHandler:
    """Handle errors throughout the pipeline.

    This class centralizes error handling for the command pipeline,
    providing consistent error messages and exit codes.
    """

    def __init__(self, debug: bool = False):
        """Initialize error handler.

        Args:
            debug: If True, show full stack traces for errors.
        """
        self.debug = debug

    def handle_resolution_errors(self, result: ResolutionResult) -> bool:
        """Handle resolution errors.

        Args:
            result: The resolution result with potential errors.

        Returns:
            True if execution should continue (partial success),
            False if execution should stop.
        """
        if result.success:
            return True

        # Print errors
        for error in result.errors:
            sys.stderr.write(f"Error in {error.stage}: {error.reason}\n")
            if error.suggestions:
                sys.stderr.write(f"  Did you mean: {', '.join(error.suggestions)}\n")

        # Continue if partial success (some data resolved)
        return result.partial

    def handle_dispatch_error(self, error: DispatchError) -> int:
        """Handle dispatch errors.

        Args:
            error: The dispatch error.

        Returns:
            Exit code (always 1 for errors).
        """
        sys.stderr.write(f"Error: {error.message}\n")
        return 1

    def handle_formatter_error(self, error: FormatterError) -> int:
        """Handle formatter errors.

        Args:
            error: The formatter error.

        Returns:
            Exit code (always 1 for errors).
        """
        sys.stderr.write(f"Output error: {error!s}\n")
        return 1

    def handle_execution_error(self, error: Exception) -> int:
        """Handle general execution errors.

        Args:
            error: The exception that occurred.

        Returns:
            Exit code (always 1 for errors).
        """
        sys.stderr.write(f"Error: {error!s}\n")
        if self.debug:
            traceback.print_exc()
        return 1


class CommandOrchestrator:
    """Main orchestrator for command execution.

    The orchestrator coordinates the full pipeline:
    1. Parse command line arguments
    2. Build resolution context from environment
    3. Resolve scope specifications to concrete values
    4. Dispatch to appropriate handler
    5. Format and output results

    Example:
        orchestrator = CommandOrchestrator()
        exit_code = orchestrator.run(sys.argv[1:])
        sys.exit(exit_code)
    """

    def __init__(self, debug: bool = False):
        """Initialize the orchestrator.

        Args:
            debug: If True, enable debug output and full stack traces.
        """
        self.debug = debug
        self.parser = CLIParser()
        self.context_builder = ContextBuilder()
        self.dispatcher = self._create_dispatcher()
        self.formatter = OutputFormatter()
        self.error_handler = ErrorHandler(debug=debug)

    def _create_dispatcher(self) -> VerbDispatcher:
        """Create and configure the verb dispatcher with handlers.

        Returns:
            Configured VerbDispatcher with all handlers registered.
        """
        dispatcher = VerbDispatcher()

        # Session handlers
        dispatcher.register("session", "list", SessionListHandler())
        dispatcher.register("session", "export", SessionExportHandler())
        dispatcher.register("session", "stats", SessionStatsHandler())

        # Workspace handlers
        dispatcher.register("ws", "list", WorkspaceListHandler())

        # Home handlers
        dispatcher.register("home", "list", HomeListHandler())

        # Project handlers
        dispatcher.register("project", "list", ProjectListHandler())
        dispatcher.register("project", "show", ProjectShowHandler())
        dispatcher.register("project", "stats", ProjectStatsHandler())

        # Gemini index handler
        dispatcher.register("gemini-index", "index", GeminiIndexHandler())

        return dispatcher

    def _enrich_verb_args(self, request: CommandRequest, context: ResolutionContext) -> None:
        """Enrich verb_args with context-derived values.

        This fills in default values that require context information,
        such as detecting the current project from CWD.

        Args:
            request: The command request to enrich (modified in place).
            context: Resolution context with CWD information.
        """
        # For project show/stats without explicit name, use CWD project
        if request.resource == "project" and request.verb in ("show", "stats"):
            if not request.verb_args.get("name") and context.cwd_project:
                request.verb_args["name"] = context.cwd_project

    def _handle_stats_sync(self, request: CommandRequest, context: ResolutionContext) -> None:
        """Handle --sync flag for stats commands.

        When --sync is passed, sync session data to the metrics database
        before computing statistics.

        Args:
            request: The command request with verb_args.
            context: Resolution context with platform info.
        """
        if request.verb != "stats":
            return
        if not request.verb_args.get("sync"):
            return

        # Initialize the metrics database
        conn = init_metrics_db()

        try:
            # Determine which agents to sync based on scope
            agents_to_sync = []
            agent_filter = request.scope_args.agent

            if agent_filter:
                agents_to_sync = [agent_filter]
            else:
                # Auto-detect available agents
                agents_to_sync = ["claude", "codex", "gemini"]

            force = request.verb_args.get("force", False)

            # Sync Claude sessions
            if "claude" in agents_to_sync:
                from agent_history.backends.claude import get_claude_projects_dir

                claude_dir = get_claude_projects_dir()
                if claude_dir.exists():
                    sync_sessions_to_db(
                        conn,
                        claude_dir,
                        source_key="local",
                        agent="claude",
                        force=force,
                    )

            # Sync Codex sessions
            if "codex" in agents_to_sync:
                from agent_history.backends.codex import codex_get_home_dir

                codex_dir = codex_get_home_dir()
                if codex_dir.exists():
                    sync_sessions_to_db(
                        conn,
                        codex_dir,
                        source_key="local",
                        agent="codex",
                        force=force,
                    )

            # Sync Gemini sessions
            if "gemini" in agents_to_sync:
                from agent_history.backends.gemini import gemini_get_home_dir

                gemini_dir = gemini_get_home_dir()
                if gemini_dir.exists():
                    sync_sessions_to_db(
                        conn,
                        gemini_dir,
                        source_key="local",
                        agent="gemini",
                        force=force,
                    )

            conn.commit()
        finally:
            conn.close()

    def run(self, argv: List[str]) -> int:
        """Run command pipeline.

        Args:
            argv: Command line arguments (typically sys.argv[1:])

        Returns:
            Exit code: 0 for success, 1 for error
        """
        try:
            # 1. Parse command line
            request = self.parser.parse(argv)

            if self.debug:
                sys.stderr.write(f"Debug: Parsed request: {request}\n")

            # 2. Build context
            context = self.context_builder.build()

            if self.debug:
                sys.stderr.write(f"Debug: Context built: platform={context.platform}\n")

            # 2.5. Enrich verb_args with context-derived values
            self._enrich_verb_args(request, context)

            # 2.6. Handle --sync for stats commands
            self._handle_stats_sync(request, context)

            # 3. Resolve scope
            resolver = ScopeResolver(context)
            resolution = resolver.resolve(request.scope_args)

            if self.debug:
                sys.stderr.write(
                    f"Debug: Resolution: {len(resolution.scope)} records, "
                    f"{len(resolution.errors)} errors\n"
                )

            # Handle resolution errors
            if not self.error_handler.handle_resolution_errors(resolution):
                return 1

            # 4. Dispatch to handler
            try:
                result = self.dispatcher.dispatch(request, resolution.scope)
            except DispatchError as e:
                return self.error_handler.handle_dispatch_error(e)

            if self.debug:
                sys.stderr.write(
                    f"Debug: Handler result: success={result.success}, "
                    f"data_type={result.data_type}\n"
                )

            # 5. Format and output
            try:
                self.formatter.format(result, request.output_args)
            except FormatterError as e:
                return self.error_handler.handle_formatter_error(e)

            return 0 if result.success else 1

        except SystemExit:
            # Let argparse --help and --version exit normally
            raise
        except KeyboardInterrupt:
            sys.stderr.write("\nInterrupted.\n")
            return 130
        except Exception as e:
            return self.error_handler.handle_execution_error(e)

    def run_with_context(
        self, argv: List[str], context: Optional[ResolutionContext] = None
    ) -> CommandResult:
        """Run command pipeline with explicit context.

        This method is useful for testing, allowing injection of a
        custom resolution context instead of auto-detecting from
        the environment.

        Args:
            argv: Command line arguments.
            context: Optional resolution context to use instead of
                auto-detecting from environment.

        Returns:
            CommandResult from the handler.

        Raises:
            DispatchError: If command cannot be dispatched.
            Various exceptions: For other pipeline errors.
        """
        # 1. Parse command line
        request = self.parser.parse(argv)

        # 2. Use provided context or build from environment
        if context is None:
            context = self.context_builder.build()

        # 3. Resolve scope
        resolver = ScopeResolver(context)
        resolution = resolver.resolve(request.scope_args)

        # 4. Dispatch to handler
        return self.dispatcher.dispatch(request, resolution.scope)


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for agent-history CLI.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code: 0 for success, non-zero for errors.
    """
    import os

    if argv is None:
        argv = sys.argv[1:]

    debug = os.environ.get("AGENT_HISTORY_DEBUG", "").lower() in ("1", "true", "yes")
    orchestrator = CommandOrchestrator(debug=debug)
    return orchestrator.run(argv)
