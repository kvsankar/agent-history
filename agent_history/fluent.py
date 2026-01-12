"""Fluent/chained API for agent_history scope resolution pipeline.

This module provides a fluent interface for building and executing queries
against the agent_history data. It wraps the scope resolution pipeline
with a chainable API that makes common operations more intuitive.

Example usage:
    from agent_history.fluent import context

    # List all sessions in current workspace
    result = context().scope().list()

    # List sessions matching pattern with filter
    result = context().scope("myproject").filter(since="2024-01-01").list()

    # Export all workspaces to markdown
    result = context().scope(all_workspaces=True).export("./export/")

    # Get stats for all homes
    result = context().home(all_homes=True).scope(all_workspaces=True).stats()

The fluent API follows a progressive disclosure pattern:
1. Create context with context()
2. Optionally configure home with .home()
3. Define scope with .scope()
4. Optionally filter with .filter()
5. Execute with .list(), .export(), .stats(), etc.

See docs/design-v2/scope-resolution-v2.md for the underlying architecture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from agent_history.handlers.base import CommandResult
from agent_history.handlers.export import SessionExportHandler
from agent_history.handlers.list import (
    HomeListHandler,
    SessionListHandler,
    WorkspaceListHandler,
)
from agent_history.handlers.stats import SessionStatsHandler
from agent_history.scope.context import (
    ContextBuilder,
    OutputArgs,
    ResolutionContext,
    ResolutionResult,
    ScopeArgs,
)
from agent_history.scope.resolver import ScopeResolver
from agent_history.scope.types import ConcreteScope
from agent_history.utils.workspace_ref import attach_workspace_context


class FluentContext:
    """Fluent interface for agent_history operations.

    This class provides a chainable API for building scope queries and
    executing commands against the agent_history data. It wraps the
    underlying scope resolution pipeline with a more intuitive interface.

    The class is designed to be used through method chaining:
        context().scope("myproject").filter(since="2024-01-01").list()

    All configuration methods return `self` to enable chaining.
    Terminal methods (list, export, stats) execute the query and return results.

    Attributes:
        _context: The underlying ResolutionContext from ContextBuilder.
        _scope_args: Accumulated scope arguments from method calls.
        _output_args: Output formatting arguments.
        _scope: Cached resolved scope (lazily computed).
        _result: Cached resolution result (lazily computed).
    """

    def __init__(self, resolution_context: Optional[ResolutionContext] = None):
        """Initialize a new FluentContext.

        Args:
            resolution_context: Optional pre-built ResolutionContext.
                If not provided, one will be built using ContextBuilder.
        """
        if resolution_context is not None:
            self._context = resolution_context
        else:
            self._context = ContextBuilder().build()
        self._scope_args = ScopeArgs()
        self._output_args = OutputArgs()
        self._scope: Optional[ConcreteScope] = None
        self._result: Optional[ResolutionResult] = None

    # =========================================================================
    # Configuration Methods (return self for chaining)
    # =========================================================================

    def scope(
        self,
        pattern: Optional[str] = None,
        *,
        project: Optional[str] = None,
        all_workspaces: bool = False,
        this_only: bool = False,
    ) -> FluentContext:
        """Define the scope (what workspaces to operate on).

        This method configures which workspaces will be included in the query.
        Multiple patterns can be added by calling this method multiple times.

        Args:
            pattern: Workspace pattern to match. Can be:
                - An absolute path like "/home/user/projects/myapp"
                - A simple name like "myapp" for substring matching
                - A glob pattern like "*/projects/*"
            project: Project name to use (from configuration).
                Projects are named collections of workspaces.
            all_workspaces: If True, include all workspaces in the home.
                Equivalent to the --aw CLI flag.
            this_only: If True, restrict to current workspace only.
                Equivalent to the --this CLI flag.

        Returns:
            self for method chaining.

        Examples:
            # Single pattern
            context().scope("myproject").list()

            # Multiple patterns (call multiple times)
            context().scope("auth").scope("api").list()

            # By project name
            context().scope(project="myapp").list()

            # All workspaces
            context().scope(all_workspaces=True).list()

            # Current workspace only
            context().scope(this_only=True).list()
        """
        if pattern:
            self._scope_args.patterns.append(pattern)
        if project:
            self._scope_args.projects.append(project)
        if all_workspaces:
            self._scope_args.all_workspaces = True
        if this_only:
            self._scope_args.this_only = True
        # Invalidate cached scope
        self._scope = None
        self._result = None
        return self

    def pattern(self, pattern: str) -> FluentContext:
        """Add a workspace pattern (alias for scope(pattern)).

        This is a convenience method for adding patterns when scope()
        has already been called with other options.

        Args:
            pattern: Workspace pattern to match.

        Returns:
            self for method chaining.

        Example:
            context().scope(all_workspaces=True).pattern("auth").list()
        """
        return self.scope(pattern)

    def name_pattern(self, pattern: str) -> FluentContext:
        """Add a name pattern for substring matching.

        Name patterns use CONTAINS matching (substring), unlike positional
        patterns which may use EXACT matching for path-like patterns.

        This is equivalent to the -n CLI flag.

        Args:
            pattern: Pattern for substring matching.

        Returns:
            self for method chaining.

        Example:
            context().scope().name_pattern("django").list()
        """
        self._scope_args.name_patterns.append(pattern)
        self._scope = None
        self._result = None
        return self

    def home(
        self,
        home_name: Optional[str] = None,
        *,
        home_type: Optional[str] = None,
        all_homes: bool = False,
        no_wsl: bool = False,
        no_windows: bool = False,
        no_remote: bool = False,
        no_web: bool = False,
    ) -> FluentContext:
        """Specify home(s) to search.

        Homes represent different contexts where sessions can be stored:
        - "local": The current machine
        - "wsl:Ubuntu": A WSL distribution
        - "windows:alice": A Windows user
        - "remote:dev": A remote connection

        Args:
            home_name: Explicit home name (e.g., "wsl:Ubuntu").
            home_type: Home category filter ("wsl", "windows", "remote", "local").
            all_homes: If True, search all available homes (--ah flag).
            no_wsl: If True, exclude WSL homes when using all_homes.
            no_windows: If True, exclude Windows homes when using all_homes.
            no_remote: If True, exclude remote homes when using all_homes.
            no_web: If True, exclude web sessions when using all_homes.

        Returns:
            self for method chaining.

        Examples:
            # Search all homes
            context().home(all_homes=True).scope(all_workspaces=True).list()

            # Search specific WSL distribution
            context().home(home_type="wsl", home_name="Ubuntu").scope().list()

            # All homes except WSL
            context().home(all_homes=True, no_wsl=True).scope(all_workspaces=True).list()
        """
        if all_homes:
            self._scope_args.all_homes = True
        if home_type:
            self._scope_args.home_type = home_type
            if home_name:
                self._scope_args.home_value = home_name
        elif home_name:
            self._scope_args.home_names.append(home_name)
        if no_wsl:
            self._scope_args.no_wsl = True
        if no_windows:
            self._scope_args.no_windows = True
        if no_remote:
            self._scope_args.no_remote = True
        if no_web:
            self._scope_args.no_web = True
        # Invalidate cached scope
        self._scope = None
        self._result = None
        return self

    def filter(
        self,
        *,
        since: Optional[str] = None,
        until: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> FluentContext:
        """Apply filters to the session query.

        Filters narrow down which sessions are included in the results.
        All filters are optional and can be combined.

        Args:
            since: Include only sessions modified on or after this date.
                Format: "YYYY-MM-DD" (e.g., "2024-01-01").
            until: Include only sessions modified on or before this date.
                Format: "YYYY-MM-DD" (e.g., "2024-12-31").
            agent: Filter by agent type. Valid values:
                - "claude": Claude Code sessions
                - "codex": Codex CLI sessions
                - "gemini": Gemini CLI sessions

        Returns:
            self for method chaining.

        Examples:
            # Sessions from 2024
            context().scope().filter(since="2024-01-01", until="2024-12-31").list()

            # Only Claude sessions
            context().scope().filter(agent="claude").list()

            # Claude sessions from last month
            context().scope().filter(agent="claude", since="2024-12-01").list()
        """
        if since:
            self._scope_args.since = since
        if until:
            self._scope_args.until = until
        if agent:
            self._scope_args.agent = agent
        # Invalidate cached scope
        self._scope = None
        self._result = None
        return self

    def output(
        self,
        *,
        format: Optional[str] = None,
        output_path: Optional[Union[str, Path]] = None,
        quiet: bool = False,
        human_readable: bool = False,
        width: Optional[int] = None,
    ) -> FluentContext:
        """Configure output formatting options.

        These options control how results are formatted and where they
        are written.

        Args:
            format: Output format. Valid values depend on the command:
                - "table": Human-readable table (default for list)
                - "json": JSON output
                - "tsv": Tab-separated values
            output_path: Write output to this file instead of stdout.
            quiet: If True, suppress non-essential output.
            human_readable: If True, format sizes and dates for humans.
            width: Maximum table width in columns.

        Returns:
            self for method chaining.

        Example:
            context().scope().output(format="json").list()
        """
        if format:
            self._output_args.format = format
        if output_path:
            self._output_args.output_path = (
                Path(output_path) if isinstance(output_path, str) else output_path
            )
        if quiet:
            self._output_args.quiet = True
        if human_readable:
            self._output_args.human_readable = True
        if width:
            self._output_args.width = width
        return self

    # =========================================================================
    # Internal Resolution
    # =========================================================================

    def _resolve(self) -> ConcreteScope:
        """Internal: resolve the scope.

        Lazily computes the resolved scope on first access.
        Subsequent calls return the cached result.

        Returns:
            ConcreteScope with resolved records.
        """
        if self._scope is None:
            resolver = ScopeResolver(self._context)
            self._result = resolver.resolve(self._scope_args)
            self._scope = self._result.scope
        return self._scope

    def _get_result(self) -> ResolutionResult:
        """Internal: get the full resolution result.

        Returns:
            ResolutionResult including scope, errors, and warnings.
        """
        self._resolve()  # Ensure resolution has happened
        assert self._result is not None
        return self._result

    # =========================================================================
    # Terminal Methods (execute and return results)
    # =========================================================================

    def list(
        self,
        *,
        format: Optional[str] = None,
    ) -> CommandResult:
        """List sessions matching the scope.

        This is a terminal method that executes the query and returns results.

        Args:
            format: Output format override ("table", "json", "tsv").

        Returns:
            CommandResult containing:
                - success: bool
                - data: List of session dictionaries
                - data_type: "session_list"
                - metadata: {"total_count": int, "homes": [...], "workspaces": [...]}

        Example:
            result = context().scope("myproject").list()
            for session in result.data:
                print(session["filename"])
        """
        if format:
            self._output_args.format = format

        scope = self._resolve()
        handler = SessionListHandler()
        return handler.execute(scope, {}, self._output_args)

    def list_workspaces(
        self,
        *,
        format: Optional[str] = None,
    ) -> CommandResult:
        """List workspaces matching the scope.

        This aggregates sessions by workspace and provides summary statistics.

        Args:
            format: Output format override ("table", "json", "tsv").

        Returns:
            CommandResult containing:
                - success: bool
                - data: List of workspace summary dictionaries
                - data_type: "workspace_list"
                - metadata: {"total_count": int, "total_sessions": int}

        Example:
            result = context().home(all_homes=True).scope(all_workspaces=True).list_workspaces()
            for ws in result.data:
                print(f"{ws['workspace']}: {ws['session_count']} sessions")
        """
        if format:
            self._output_args.format = format

        scope = self._resolve()
        handler = WorkspaceListHandler()
        return handler.execute(scope, {}, self._output_args)

    def list_homes(
        self,
        *,
        format: Optional[str] = None,
    ) -> CommandResult:
        """List homes with session counts.

        This lists all available homes (local, WSL, Windows, remote) and
        aggregates session/workspace counts for each.

        Args:
            format: Output format override ("table", "json", "tsv").

        Returns:
            CommandResult containing:
                - success: bool
                - data: List of home summary dictionaries
                - data_type: "home_list"
                - metadata: {"total_count": int, "total_workspaces": int, "total_sessions": int}

        Example:
            result = context().home(all_homes=True).scope(all_workspaces=True).list_homes()
            for home in result.data:
                print(f"{home['home']}: {home['session_count']} sessions")
        """
        if format:
            self._output_args.format = format

        scope = self._resolve()
        handler = HomeListHandler()
        return handler.execute(scope, {}, self._output_args)

    def export(
        self,
        output_dir: Optional[Union[str, Path]] = None,
        *,
        format: str = "markdown",
        minimal: bool = False,
        split: Optional[int] = None,
        flat: bool = False,
        force: bool = False,
        include_source: bool = False,
    ) -> CommandResult:
        """Export sessions to files.

        This is a terminal method that exports sessions matching the scope
        to markdown (or other formats) files.

        Args:
            output_dir: Directory for output files. Defaults to "./ai-chats".
            format: Export format ("markdown" or "json").
            minimal: If True, omit metadata in markdown output.
            split: Split files at this many lines. None to disable.
            flat: If True, use flat directory structure (no workspace subdirs).
            force: If True, overwrite existing files.
            include_source: If True, copy raw source files alongside exports.

        Returns:
            CommandResult containing:
                - success: bool
                - data: {"exported": int, "skipped": int, "failed": int, "output_dir": str}
                - data_type: "export_result"
                - metadata: {"homes": [...], "workspaces": [...]}

        Example:
            result = context().scope("myproject").export("./exports/")
            print(f"Exported {result.data['exported']} sessions")
        """
        scope = self._resolve()

        verb_args: dict[str, Any] = {
            "output_dir": Path(output_dir) if output_dir else Path.cwd() / "ai-chats",
            "minimal": minimal,
            "split": split,
            "flat": flat,
            "force": force,
            "include_source": include_source,
            "export_json": format == "json",
        }

        handler = SessionExportHandler()
        return handler.execute(scope, verb_args, self._output_args)

    def stats(
        self,
        *,
        by: Optional[str] = None,
        include_time: bool = False,
        top: Optional[int] = None,
    ) -> CommandResult:
        """Get statistics for sessions in scope.

        This computes aggregate statistics across all sessions matching
        the scope.

        Args:
            by: Grouping dimension for breakdowns:
                - "agent": Group by agent type
                - "model": Group by model name
                - "tool": Group by tool usage
                - "home": Group by home
                - "workspace": Group by workspace
                - "day": Group by date
            include_time: If True, include time tracking statistics.
            top: Limit breakdowns to top N items.

        Returns:
            CommandResult containing:
                - success: bool
                - data: Statistics dictionary with counts and breakdowns
                - data_type: "stats"
                - metadata: {"total_sessions": int, "homes": [...], "workspaces": [...]}

        Example:
            result = context().scope(all_workspaces=True).stats(by="model")
            print(f"Total sessions: {result.data['sessions']}")
            for model, info in result.data['by_model'].items():
                print(f"  {model}: {info['messages']} messages")
        """
        scope = self._resolve()

        verb_args: dict[str, Any] = {
            "by": by,
            "time": include_time,
            "top": top,
        }

        handler = SessionStatsHandler()
        return handler.execute(scope, verb_args, self._output_args)

    # =========================================================================
    # Convenience Properties
    # =========================================================================

    @property
    def resolution_context(self) -> ResolutionContext:
        """Access the underlying ResolutionContext.

        This provides access to platform info, CWD detection, available homes,
        and other context information.

        Returns:
            The ResolutionContext used for resolution.
        """
        return self._context

    @property
    def scope_args(self) -> ScopeArgs:
        """Access the accumulated ScopeArgs.

        This is useful for debugging or advanced manipulation.

        Returns:
            The ScopeArgs built from method calls.
        """
        return self._scope_args

    @property
    def sessions(self) -> list[dict[str, Any]]:
        """Get the resolved sessions as a flat list.

        This is a convenience property that resolves the scope and
        flattens all sessions into a single list.

        Returns:
            List of session dictionaries.

        Example:
            sessions = context().scope("myproject").sessions
            print(f"Found {len(sessions)} sessions")
        """
        scope = self._resolve()
        sessions = []
        for record in scope:
            for session in record.sessions:
                session_copy = dict(session)
                session_copy["home"] = record.home
                session_copy.setdefault("workspace_raw", session_copy.get("workspace"))
                session_copy["workspace"] = record.workspace
                attach_workspace_context(
                    session_copy,
                    workspace=record.workspace,
                    workspace_key=record.workspace_key,
                    workspace_display=record.workspace_display,
                )
                sessions.append(session_copy)
        return sessions

    @property
    def workspaces(self) -> list[str]:
        """Get the unique workspace paths from resolved scope.

        Returns:
            Sorted list of unique workspace paths.

        Example:
            workspaces = context().scope(all_workspaces=True).workspaces
            for ws in workspaces:
                print(ws)
        """
        scope = self._resolve()
        return sorted({record.workspace for record in scope})

    @property
    def homes(self) -> list[str]:
        """Get the unique home identifiers from resolved scope.

        Returns:
            Sorted list of unique home identifiers.

        Example:
            homes = context().home(all_homes=True).scope(all_workspaces=True).homes
            for home in homes:
                print(home)
        """
        scope = self._resolve()
        return sorted({record.home for record in scope})

    @property
    def session_count(self) -> int:
        """Get the total number of sessions in resolved scope.

        Returns:
            Total count of sessions.

        Example:
            count = context().scope("myproject").session_count
            print(f"Found {count} sessions")
        """
        scope = self._resolve()
        return sum(len(record.sessions) for record in scope)

    @property
    def errors(self) -> list[Any]:
        """Get any errors from the resolution process.

        Returns:
            List of ResolutionError objects.
        """
        result = self._get_result()
        return result.errors

    @property
    def warnings(self) -> list[str]:
        """Get any warnings from the resolution process.

        Returns:
            List of warning messages.
        """
        result = self._get_result()
        return result.warnings

    @property
    def success(self) -> bool:
        """Check if resolution completed without errors.

        Returns:
            True if no errors occurred during resolution.
        """
        result = self._get_result()
        return result.success


# =============================================================================
# Factory Function
# =============================================================================


def context(resolution_context: Optional[ResolutionContext] = None) -> FluentContext:
    """Create a new FluentContext for building queries.

    This is the main entry point for the fluent API. It creates a new
    FluentContext that can be configured through method chaining.

    Args:
        resolution_context: Optional pre-built ResolutionContext.
            If not provided, one will be built automatically.

    Returns:
        A new FluentContext ready for configuration.

    Examples:
        # Basic usage
        result = context().scope("myproject").list()

        # With filters
        result = context().scope().filter(since="2024-01-01", agent="claude").list()

        # Multi-home query
        result = context().home(all_homes=True).scope(all_workspaces=True).stats()
    """
    return FluentContext(resolution_context)


# =============================================================================
# Convenience Aliases
# =============================================================================

# For even shorter imports
Context = FluentContext
