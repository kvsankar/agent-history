"""Command orchestrator for agent-history CLI.

This module provides the CommandOrchestrator class that coordinates the
full command pipeline: parsing, context building, scope resolution,
handler dispatch, and output formatting.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from __future__ import annotations

import sys
import traceback

from agent_history.cli.parser import CLIParser
from agent_history.handlers import (
    CommandResult,
    DispatchError,
    FetchHandler,
    GeminiIndexHandler,
    HomeAddHandler,
    HomeExportHandler,
    HomeListHandler,
    HomeRemoveHandler,
    HomeShowHandler,
    HomeStatsHandler,
    InstallHandler,
    ProjectAddHandler,
    ProjectExportHandler,
    ProjectListHandler,
    ProjectRemoveHandler,
    ProjectShowHandler,
    ProjectStatsHandler,
    ResetHandler,
    SessionExportHandler,
    SessionListHandler,
    SessionShowHandler,
    SessionStatsHandler,
    VerbDispatcher,
    WorkspaceExportHandler,
    WorkspaceListHandler,
    WorkspaceShowHandler,
    WorkspaceStatsHandler,
)
from agent_history.output.formatter import FormatterError, OutputFormatter
from agent_history.scope.context import (
    CommandRequest,
    ContextBuilder,
    ResolutionContext,
    ResolutionResult,
)
from agent_history.scope.resolver import ScopeResolver
from agent_history.storage.metrics import init_metrics_db, sync_scope_to_db


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
        dispatcher.register("session", "show", SessionShowHandler())

        # Workspace handlers
        dispatcher.register("ws", "list", WorkspaceListHandler())
        dispatcher.register("ws", "show", WorkspaceShowHandler())
        dispatcher.register("ws", "export", WorkspaceExportHandler())
        dispatcher.register("ws", "stats", WorkspaceStatsHandler())

        # Home handlers
        dispatcher.register("home", "list", HomeListHandler())
        dispatcher.register("home", "add", HomeAddHandler())
        dispatcher.register("home", "remove", HomeRemoveHandler())
        dispatcher.register("home", "show", HomeShowHandler())
        dispatcher.register("home", "export", HomeExportHandler())
        dispatcher.register("home", "stats", HomeStatsHandler())

        # Project handlers
        dispatcher.register("project", "list", ProjectListHandler())
        dispatcher.register("project", "show", ProjectShowHandler())
        dispatcher.register("project", "stats", ProjectStatsHandler())
        dispatcher.register("project", "add", ProjectAddHandler())
        dispatcher.register("project", "remove", ProjectRemoveHandler())
        dispatcher.register("project", "export", ProjectExportHandler())

        # Gemini index handler
        dispatcher.register("gemini-index", "index", GeminiIndexHandler())

        # Utility handlers
        dispatcher.register("install", "run", InstallHandler())
        dispatcher.register("reset", "run", ResetHandler())
        dispatcher.register("fetch", "run", FetchHandler())

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

    def _check_remote_connectivity(
        self, request: CommandRequest, context: ResolutionContext
    ) -> bool:
        """Check SSH connectivity to all specified remote hosts upfront.

        This provides early failure with helpful error messages before
        attempting any scope resolution or data operations.

        Note: This check is skipped if the cross-home guard would trigger,
        allowing the guard error to be shown instead of SSH errors.

        Args:
            request: The command request with scope_args.
            context: Resolution context with CWD workspace info.

        Returns:
            True if all remotes are reachable (or no remotes specified),
            False if any remote failed connectivity check.
        """
        from agent_history.backends.ssh import check_ssh_connection

        # First, check if cross-home guard would trigger
        # If so, skip SSH check - let the resolver show the guard error instead
        args = request.scope_args
        needs_cross_home = (
            args.home_type in ("wsl", "windows", "remote")
            or args.all_homes
            or bool(args.home_names)
        )
        has_explicit_scope = (
            args.all_workspaces
            or bool(args.projects)
            or context.cwd_project
            or bool(args.patterns)
            or bool(args.name_patterns)
        )
        is_in_workspace = bool(context.cwd_workspace)

        if needs_cross_home and not has_explicit_scope and is_in_workspace:
            # Cross-home guard will trigger - skip SSH check
            return True

        # Collect all remote hosts to check
        remotes_to_check: list[str] = []

        # Check -r/--remote flags
        if request.scope_args.home_type == "remote" and request.scope_args.home_value:
            remotes_to_check.append(request.scope_args.home_value)

        # Check --home flags for remote: prefixed homes
        for home in request.scope_args.home_names:
            if home.startswith("remote:"):
                remotes_to_check.append(home[7:])  # Remove "remote:" prefix
            elif "@" in home and not home.startswith(("wsl:", "windows:")):
                # Looks like user@host format
                remotes_to_check.append(home)

        if not remotes_to_check:
            return True

        # Check connectivity to each remote
        all_ok = True
        for remote_host in remotes_to_check:
            success, _error = check_ssh_connection(remote_host)
            if not success:
                sys.stderr.write(f"Error: Cannot connect to {remote_host} via passwordless SSH\n")
                sys.stderr.write(f"Setup: ssh-copy-id {remote_host}\n")
                all_ok = False

        return all_ok

    def _handle_stats_sync(self, request: CommandRequest, scope) -> None:
        """Auto-sync stats scope unless --no-sync is specified."""
        if request.verb != "stats":
            return
        if request.verb_args.get("no_sync"):
            return

        conn = init_metrics_db()
        try:
            force = request.verb_args.get("force", False)
            sync_scope_to_db(conn, scope, force=force)
            conn.commit()
            request.verb_args["sync"] = True
        finally:
            conn.close()

    def run(self, argv: list[str]) -> int:
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

            # 2.7. Pre-flight check: verify SSH connectivity to remotes
            # (skipped if cross-home guard would trigger - let guard error show first)
            if not self._check_remote_connectivity(request, context):
                return 1

            self._prepare_scope_for_project_counts(request)

            # Config-only home management does not operate on workspaces or
            # sessions. Dispatch it directly so source flags like
            # `home add --windows` are not interpreted as cross-home scope.
            direct_result = self._dispatch_config_home_management(request)
            if direct_result is not None:
                return direct_result

            if self._is_workspace_count_list(request):
                return self._run_workspace_count_list(request, context)

            # 3. Resolve scope
            resolver = ScopeResolver(context)
            resolution = resolver.resolve(
                request.scope_args,
                load_sessions=self._should_load_sessions(request),
            )

            if self.debug:
                sys.stderr.write(
                    f"Debug: Resolution: {len(resolution.scope)} records, "
                    f"{len(resolution.errors)} errors\n"
                )

            # Handle resolution errors
            if not self.error_handler.handle_resolution_errors(resolution):
                return 1

            # 3.5. Auto-sync stats after scope resolution (unless --no-sync)
            self._handle_stats_sync(request, resolution.scope)

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

    def _dispatch_config_home_management(self, request: CommandRequest) -> int | None:
        if request.resource != "home" or request.verb not in ("add", "remove"):
            return None
        try:
            result = self.dispatcher.dispatch(request, [])
        except DispatchError as e:
            return self.error_handler.handle_dispatch_error(e)
        try:
            self.formatter.format(result, request.output_args)
        except FormatterError as e:
            return self.error_handler.handle_formatter_error(e)
        return 0 if result.success else 1

    def _is_workspace_count_list(self, request: CommandRequest) -> bool:
        return (
            request.resource == "ws"
            and request.verb == "list"
            and bool(request.verb_args.get("counts"))
        )

    def _prepare_scope_for_project_counts(self, request: CommandRequest) -> None:
        """Expand project-list counts to all configured projects when needed."""
        if not (
            request.resource == "project"
            and request.verb == "list"
            and request.verb_args.get("counts")
            and not request.scope_args.projects
        ):
            return

        from agent_history.storage.config import load_config

        projects_cfg = load_config().get("projects", {})
        request.scope_args.projects = list(projects_cfg.keys())

    def _should_load_sessions(self, request: CommandRequest) -> bool:
        """Return whether scope resolution needs session data for this request."""
        metadata_only_lists = {"home", "ws", "project"}
        if request.verb == "list" and request.resource in metadata_only_lists:
            return bool(request.verb_args.get("counts"))
        return True

    def _run_workspace_count_list(self, request: CommandRequest, context: ResolutionContext) -> int:
        """Run `ws list --counts` with source-level workspace summaries."""
        from agent_history.adapters.inventory import InventoryProvider

        allowed = self._workspace_count_allowed_scopes(request, context)
        if allowed is None:
            return 1

        inventory = InventoryProvider(context)
        rows = []
        for home, workspace_keys in allowed.items():
            for row in inventory.list_workspace_summaries(home, agent=request.scope_args.agent):
                key = row.get("workspace_key") or row.get("workspace")
                if workspace_keys is None or key in workspace_keys:
                    rows.append(row)

        rows.sort(key=lambda row: str(row.get("last_modified", "")), reverse=True)
        homes = sorted({row.get("home") for row in rows if row.get("home")})
        workspaces = sorted({row.get("workspace") for row in rows if row.get("workspace")})
        display_map = {
            row.get("workspace_key"): row.get("workspace_display")
            for row in rows
            if row.get("workspace_key") and row.get("workspace_display")
        }
        result = CommandResult(
            success=True,
            data=rows,
            data_type="workspace_list",
            metadata={
                "total_count": len(rows),
                "homes": homes,
                "workspaces": workspaces,
                "total_sessions": sum(row.get("session_count", 0) for row in rows),
                "workspace_display_map": display_map,
            },
        )
        try:
            self.formatter.format(result, request.output_args)
        except FormatterError as e:
            return self.error_handler.handle_formatter_error(e)
        return 0

    def _workspace_count_allowed_scopes(
        self, request: CommandRequest, context: ResolutionContext
    ) -> dict[str, set[str] | None] | None:
        if self._workspace_counts_include_all_workspaces(request):
            return dict.fromkeys(self._selected_homes_for_workspace_counts(request, context), None)

        resolver = ScopeResolver(context)
        resolution = resolver.resolve(request.scope_args, load_sessions=False)
        if not self.error_handler.handle_resolution_errors(resolution):
            return None

        allowed: dict[str, set[str] | None] = {}
        for record in resolution.scope:
            allowed.setdefault(record.home, set()).add(record.workspace_key or record.workspace)
        return allowed

    def _workspace_counts_include_all_workspaces(self, request: CommandRequest) -> bool:
        return (
            request.scope_args.all_workspaces
            and not request.scope_args.patterns
            and not request.scope_args.name_patterns
            and not request.scope_args.projects
        )

    def _selected_homes_for_workspace_counts(
        self, request: CommandRequest, context: ResolutionContext
    ) -> list[str]:
        args = request.scope_args
        homes: list[str] = []
        if args.all_homes:
            homes.append("local")
            for category, items in context.available_homes.items():
                if category == "wsl" and args.no_wsl:
                    continue
                if category == "windows" and args.no_windows:
                    continue
                if category == "remote" and args.no_remote:
                    continue
                for item in items:
                    homes.append(f"{category}:{item}")
            if not args.no_web:
                homes.extend(home for home in args.home_names if home == "web")
        elif args.home_names:
            homes.extend(args.home_names)
        elif args.home_type:
            if args.home_type == "local":
                homes.append("local")
            else:
                for item in context.available_homes.get(args.home_type, []):
                    homes.append(f"{args.home_type}:{item}")
        else:
            homes.append("local")
        return list(dict.fromkeys(homes))

    def run_with_context(
        self, argv: list[str], context: ResolutionContext | None = None
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

        # Auto-sync stats after scope resolution (unless --no-sync)
        self._handle_stats_sync(request, resolution.scope)

        # 4. Dispatch to handler
        return self.dispatcher.dispatch(request, resolution.scope)


def main(argv: list[str] | None = None) -> int:
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
