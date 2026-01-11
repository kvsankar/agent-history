"""Pythonic API for agent_history.

This module provides simple, idiomatic Python functions for querying
and exporting agent session history. It favors explicit keyword arguments
over method chaining, and generators over eager collection.

Example usage:
    from agent_history import api

    # List sessions (returns list)
    sessions = api.list_sessions("myproject", since="2024-01-01")

    # Iterate sessions (generator - memory efficient)
    for session in api.sessions("myproject"):
        print(session["filename"])

    # Export sessions
    result = api.export("myproject", "./exports/", minimal=True)

    # Get statistics
    stats = api.stats(all_workspaces=True, by="model")

See docs/design-v2/scope-resolution-v2.md for the underlying architecture.
"""

from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

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
    ScopeArgs,
)
from agent_history.scope.resolver import ScopeResolver
from agent_history.scope.types import ConcreteScope

# Type aliases for clarity
SessionDict = Dict[str, Any]
WorkspaceDict = Dict[str, Any]
HomeDict = Dict[str, Any]
StatsDict = Dict[str, Any]


# =============================================================================
# Internal Helpers
# =============================================================================


def _build_scope_args(  # noqa: PLR0913, C901
    pattern: Optional[str] = None,
    *,
    patterns: Optional[List[str]] = None,
    project: Optional[str] = None,
    all_workspaces: bool = False,
    this_only: bool = False,
    all_homes: bool = False,
    home: Optional[str] = None,
    home_type: Optional[str] = None,
    no_wsl: bool = False,
    no_windows: bool = False,
    no_remote: bool = False,
    since: Optional[str] = None,
    until: Optional[str] = None,
    agent: Optional[str] = None,
) -> ScopeArgs:
    """Build ScopeArgs from function parameters."""
    args = ScopeArgs()

    # Patterns
    if pattern:
        args.patterns.append(pattern)
    if patterns:
        args.patterns.extend(patterns)

    # Workspace scope
    if project:
        args.project = project
    if all_workspaces:
        args.all_workspaces = True
    if this_only:
        args.this_only = True

    # Home scope
    if all_homes:
        args.all_homes = True
    if home:
        args.home_names.append(home)
    if home_type:
        args.home_type = home_type
    if no_wsl:
        args.no_wsl = True
    if no_windows:
        args.no_windows = True
    if no_remote:
        args.no_remote = True

    # Filters
    if since:
        args.since = since
    if until:
        args.until = until
    if agent:
        args.agent = agent

    return args


def _resolve_scope(
    scope_args: ScopeArgs,
    context: Optional[ResolutionContext] = None,
) -> ConcreteScope:
    """Resolve scope args to a ConcreteScope."""
    if context is None:
        context = ContextBuilder().build()
    resolver = ScopeResolver(context)
    result = resolver.resolve(scope_args)
    return result.scope


def _build_output_args(
    format: Optional[str] = None,
    quiet: bool = False,
) -> OutputArgs:
    """Build OutputArgs from function parameters."""
    args = OutputArgs()
    if format:
        args.format = format
    if quiet:
        args.quiet = True
    return args


# =============================================================================
# Generator Functions (lazy iteration)
# =============================================================================


def sessions(  # noqa: PLR0913
    pattern: Optional[str] = None,
    *,
    patterns: Optional[List[str]] = None,
    project: Optional[str] = None,
    all_workspaces: bool = False,
    this_only: bool = False,
    all_homes: bool = False,
    home: Optional[str] = None,
    home_type: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    agent: Optional[str] = None,
    context: Optional[ResolutionContext] = None,
) -> Iterator[SessionDict]:
    """Iterate over sessions matching the given criteria.

    This is a generator that yields sessions one at a time, making it
    memory-efficient for large result sets.

    Args:
        pattern: Workspace pattern to match (path or substring).
        patterns: Multiple workspace patterns.
        project: Project name from configuration.
        all_workspaces: Include all workspaces in scope.
        this_only: Restrict to current workspace only.
        all_homes: Search all available homes.
        home: Specific home name (e.g., "wsl:Ubuntu").
        home_type: Home category ("wsl", "windows", "remote").
        since: Include sessions modified on/after this date (YYYY-MM-DD).
        until: Include sessions modified on/before this date (YYYY-MM-DD).
        agent: Filter by agent type ("claude", "codex", "gemini").
        context: Optional pre-built ResolutionContext.

    Yields:
        Session dictionaries with keys like 'filename', 'file', 'timestamp',
        plus 'home' and 'workspace' added for context.

    Examples:
        # Iterate all sessions in a workspace
        for session in sessions("myproject"):
            print(session["filename"])

        # Filter with list comprehension
        recent = [s for s in sessions(all_workspaces=True, since="2024-01-01")]

        # Count sessions efficiently
        count = sum(1 for _ in sessions("myproject"))
    """
    scope_args = _build_scope_args(
        pattern,
        patterns=patterns,
        project=project,
        all_workspaces=all_workspaces,
        this_only=this_only,
        all_homes=all_homes,
        home=home,
        home_type=home_type,
        since=since,
        until=until,
        agent=agent,
    )
    scope = _resolve_scope(scope_args, context)

    for record in scope:
        for session in record.sessions:
            # Add context to each session
            enriched = dict(session)
            enriched["home"] = record.home
            enriched["workspace"] = record.workspace
            yield enriched


def workspaces(
    pattern: Optional[str] = None,
    *,
    patterns: Optional[List[str]] = None,
    project: Optional[str] = None,
    all_workspaces: bool = False,
    all_homes: bool = False,
    home: Optional[str] = None,
    home_type: Optional[str] = None,
    context: Optional[ResolutionContext] = None,
) -> Iterator[WorkspaceDict]:
    """Iterate over workspaces matching the given criteria.

    Yields workspace summaries with session counts.

    Args:
        pattern: Workspace pattern to match.
        patterns: Multiple workspace patterns.
        project: Project name from configuration.
        all_workspaces: Include all workspaces.
        all_homes: Search all available homes.
        home: Specific home name.
        home_type: Home category filter.
        context: Optional pre-built ResolutionContext.

    Yields:
        Workspace dictionaries with 'workspace', 'home', 'session_count'.

    Example:
        for ws in workspaces(all_workspaces=True):
            print(f"{ws['workspace']}: {ws['session_count']} sessions")
    """
    scope_args = _build_scope_args(
        pattern,
        patterns=patterns,
        project=project,
        all_workspaces=all_workspaces,
        all_homes=all_homes,
        home=home,
        home_type=home_type,
    )
    scope = _resolve_scope(scope_args, context)

    for record in scope:
        yield {
            "workspace": record.workspace,
            "home": record.home,
            "session_count": len(record.sessions),
            "sessions": record.sessions,
        }


def homes(
    *,
    all_homes: bool = True,
    home_type: Optional[str] = None,
    no_wsl: bool = False,
    no_windows: bool = False,
    no_remote: bool = False,
    context: Optional[ResolutionContext] = None,
) -> Iterator[HomeDict]:
    """Iterate over available homes.

    Args:
        all_homes: Include all homes (default True for this function).
        home_type: Filter by home type.
        no_wsl: Exclude WSL homes.
        no_windows: Exclude Windows homes.
        no_remote: Exclude remote homes.
        context: Optional pre-built ResolutionContext.

    Yields:
        Home dictionaries with 'home', 'workspace_count', 'session_count'.

    Example:
        for home in homes():
            print(f"{home['home']}: {home['session_count']} sessions")
    """
    scope_args = _build_scope_args(
        all_homes=all_homes,
        all_workspaces=True,  # Need all workspaces to count
        home_type=home_type,
        no_wsl=no_wsl,
        no_windows=no_windows,
        no_remote=no_remote,
    )
    scope = _resolve_scope(scope_args, context)

    # Aggregate by home
    home_data: Dict[str, Dict[str, Any]] = {}
    for record in scope:
        if record.home not in home_data:
            home_data[record.home] = {
                "home": record.home,
                "workspaces": set(),
                "session_count": 0,
            }
        home_data[record.home]["workspaces"].add(record.workspace)
        home_data[record.home]["session_count"] += len(record.sessions)

    for home_info in home_data.values():
        yield {
            "home": home_info["home"],
            "workspace_count": len(home_info["workspaces"]),
            "session_count": home_info["session_count"],
        }


# =============================================================================
# List Functions (eager, return lists)
# =============================================================================


def list_sessions(  # noqa: PLR0913
    pattern: Optional[str] = None,
    *,
    patterns: Optional[List[str]] = None,
    project: Optional[str] = None,
    all_workspaces: bool = False,
    this_only: bool = False,
    all_homes: bool = False,
    home: Optional[str] = None,
    home_type: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    agent: Optional[str] = None,
    format: Optional[str] = None,
    context: Optional[ResolutionContext] = None,
) -> CommandResult:
    """List sessions matching the given criteria.

    Returns a CommandResult with session data. For iteration, prefer
    the `sessions()` generator instead.

    Args:
        pattern: Workspace pattern to match.
        patterns: Multiple workspace patterns.
        project: Project name from configuration.
        all_workspaces: Include all workspaces.
        this_only: Restrict to current workspace.
        all_homes: Search all homes.
        home: Specific home name.
        home_type: Home category filter.
        since: Date filter (YYYY-MM-DD).
        until: Date filter (YYYY-MM-DD).
        agent: Agent type filter.
        format: Output format ("table", "json", "tsv").
        context: Optional pre-built ResolutionContext.

    Returns:
        CommandResult with:
            - data: List of session dictionaries
            - metadata: {"total_count": int, "homes": [...], "workspaces": [...]}

    Example:
        result = list_sessions("myproject", since="2024-01-01")
        print(f"Found {len(result.data)} sessions")
    """
    scope_args = _build_scope_args(
        pattern,
        patterns=patterns,
        project=project,
        all_workspaces=all_workspaces,
        this_only=this_only,
        all_homes=all_homes,
        home=home,
        home_type=home_type,
        since=since,
        until=until,
        agent=agent,
    )
    scope = _resolve_scope(scope_args, context)
    output_args = _build_output_args(format=format)

    handler = SessionListHandler()
    return handler.execute(scope, {}, output_args)


def list_workspaces(  # noqa: PLR0913
    pattern: Optional[str] = None,
    *,
    patterns: Optional[List[str]] = None,
    project: Optional[str] = None,
    all_workspaces: bool = False,
    all_homes: bool = False,
    home: Optional[str] = None,
    home_type: Optional[str] = None,
    format: Optional[str] = None,
    context: Optional[ResolutionContext] = None,
) -> CommandResult:
    """List workspaces matching the given criteria.

    Args:
        pattern: Workspace pattern to match.
        patterns: Multiple workspace patterns.
        project: Project name from configuration.
        all_workspaces: Include all workspaces.
        all_homes: Search all homes.
        home: Specific home name.
        home_type: Home category filter.
        format: Output format.
        context: Optional pre-built ResolutionContext.

    Returns:
        CommandResult with workspace summaries.

    Example:
        result = list_workspaces(all_workspaces=True)
        for ws in result.data:
            print(f"{ws['workspace']}: {ws['session_count']} sessions")
    """
    scope_args = _build_scope_args(
        pattern,
        patterns=patterns,
        project=project,
        all_workspaces=all_workspaces,
        all_homes=all_homes,
        home=home,
        home_type=home_type,
    )
    scope = _resolve_scope(scope_args, context)
    output_args = _build_output_args(format=format)

    handler = WorkspaceListHandler()
    return handler.execute(scope, {}, output_args)


def list_homes(
    *,
    all_homes: bool = True,
    home_type: Optional[str] = None,
    no_wsl: bool = False,
    no_windows: bool = False,
    no_remote: bool = False,
    format: Optional[str] = None,
    context: Optional[ResolutionContext] = None,
) -> CommandResult:
    """List available homes with session counts.

    Args:
        all_homes: Include all homes (default True).
        home_type: Filter by home type.
        no_wsl: Exclude WSL homes.
        no_windows: Exclude Windows homes.
        no_remote: Exclude remote homes.
        format: Output format.
        context: Optional pre-built ResolutionContext.

    Returns:
        CommandResult with home summaries.

    Example:
        result = list_homes()
        for home in result.data:
            print(f"{home['home']}: {home['session_count']} sessions")
    """
    scope_args = _build_scope_args(
        all_homes=all_homes,
        all_workspaces=True,
        home_type=home_type,
        no_wsl=no_wsl,
        no_windows=no_windows,
        no_remote=no_remote,
    )
    scope = _resolve_scope(scope_args, context)
    output_args = _build_output_args(format=format)

    handler = HomeListHandler()
    return handler.execute(scope, {}, output_args)


# =============================================================================
# Export Function
# =============================================================================


def export(  # noqa: PLR0913
    pattern: Optional[str] = None,
    output_dir: Optional[Union[str, Path]] = None,
    *,
    patterns: Optional[List[str]] = None,
    project: Optional[str] = None,
    all_workspaces: bool = False,
    all_homes: bool = False,
    home: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    agent: Optional[str] = None,
    format: str = "markdown",
    minimal: bool = False,
    split: Optional[int] = None,
    flat: bool = False,
    force: bool = False,
    include_source: bool = False,
    quiet: bool = False,
    context: Optional[ResolutionContext] = None,
) -> CommandResult:
    """Export sessions to files.

    Args:
        pattern: Workspace pattern to match.
        output_dir: Output directory (default: ./ai-chats).
        patterns: Multiple workspace patterns.
        project: Project name from configuration.
        all_workspaces: Include all workspaces.
        all_homes: Search all homes.
        home: Specific home name.
        since: Date filter (YYYY-MM-DD).
        until: Date filter (YYYY-MM-DD).
        agent: Agent type filter.
        format: Export format ("markdown" or "json").
        minimal: Omit metadata in markdown output.
        split: Split files at this many lines.
        flat: Use flat directory structure.
        force: Overwrite existing files.
        include_source: Copy raw source files.
        quiet: Suppress per-file output.
        context: Optional pre-built ResolutionContext.

    Returns:
        CommandResult with:
            - data: {"exported": int, "skipped": int, "failed": int}

    Example:
        result = export("myproject", "./exports/", minimal=True)
        print(f"Exported {result.data['exported']} sessions")
    """
    scope_args = _build_scope_args(
        pattern,
        patterns=patterns,
        project=project,
        all_workspaces=all_workspaces,
        all_homes=all_homes,
        home=home,
        since=since,
        until=until,
        agent=agent,
    )
    scope = _resolve_scope(scope_args, context)
    output_args = _build_output_args(quiet=quiet)

    verb_args = {
        "output_dir": Path(output_dir) if output_dir else Path.cwd() / "ai-chats",
        "minimal": minimal,
        "split": split,
        "flat": flat,
        "force": force,
        "include_source": include_source,
        "export_json": format == "json",
    }

    handler = SessionExportHandler()
    return handler.execute(scope, verb_args, output_args)


# =============================================================================
# Stats Function
# =============================================================================


def stats(  # noqa: PLR0913
    pattern: Optional[str] = None,
    *,
    patterns: Optional[List[str]] = None,
    project: Optional[str] = None,
    all_workspaces: bool = False,
    all_homes: bool = False,
    home: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    agent: Optional[str] = None,
    by: Optional[str] = None,
    include_time: bool = False,
    top: Optional[int] = None,
    context: Optional[ResolutionContext] = None,
) -> CommandResult:
    """Get statistics for sessions matching the criteria.

    Args:
        pattern: Workspace pattern to match.
        patterns: Multiple workspace patterns.
        project: Project name from configuration.
        all_workspaces: Include all workspaces.
        all_homes: Search all homes.
        home: Specific home name.
        since: Date filter (YYYY-MM-DD).
        until: Date filter (YYYY-MM-DD).
        agent: Agent type filter.
        by: Grouping dimension ("agent", "model", "tool", "day").
        include_time: Include time tracking stats.
        top: Limit breakdowns to top N items.
        context: Optional pre-built ResolutionContext.

    Returns:
        CommandResult with statistics.

    Example:
        result = stats(all_workspaces=True, by="model")
        print(f"Total sessions: {result.data['sessions']}")
    """
    scope_args = _build_scope_args(
        pattern,
        patterns=patterns,
        project=project,
        all_workspaces=all_workspaces,
        all_homes=all_homes,
        home=home,
        since=since,
        until=until,
        agent=agent,
    )
    scope = _resolve_scope(scope_args, context)
    output_args = OutputArgs()

    verb_args = {
        "by": by,
        "time": include_time,
        "top": top,
    }

    handler = SessionStatsHandler()
    return handler.execute(scope, verb_args, output_args)


# =============================================================================
# Utility Functions
# =============================================================================


def count_sessions(
    pattern: Optional[str] = None,
    *,
    all_workspaces: bool = False,
    all_homes: bool = False,
    since: Optional[str] = None,
    until: Optional[str] = None,
    agent: Optional[str] = None,
    context: Optional[ResolutionContext] = None,
) -> int:
    """Count sessions matching the criteria.

    This is more efficient than len(list(sessions(...))) as it
    doesn't build session dictionaries.

    Args:
        pattern: Workspace pattern to match.
        all_workspaces: Include all workspaces.
        all_homes: Search all homes.
        since: Date filter.
        until: Date filter.
        agent: Agent type filter.
        context: Optional pre-built ResolutionContext.

    Returns:
        Total count of matching sessions.

    Example:
        count = count_sessions("myproject")
        print(f"Found {count} sessions")
    """
    scope_args = _build_scope_args(
        pattern,
        all_workspaces=all_workspaces,
        all_homes=all_homes,
        since=since,
        until=until,
        agent=agent,
    )
    scope = _resolve_scope(scope_args, context)
    return sum(len(record.sessions) for record in scope)


def count_workspaces(
    *,
    all_workspaces: bool = True,
    all_homes: bool = False,
    context: Optional[ResolutionContext] = None,
) -> int:
    """Count workspaces.

    Args:
        all_workspaces: Include all workspaces (default True).
        all_homes: Search all homes.
        context: Optional pre-built ResolutionContext.

    Returns:
        Total count of workspaces.
    """
    scope_args = _build_scope_args(
        all_workspaces=all_workspaces,
        all_homes=all_homes,
    )
    scope = _resolve_scope(scope_args, context)
    return len({record.workspace for record in scope})
