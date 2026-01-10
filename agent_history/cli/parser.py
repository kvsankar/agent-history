"""CLI Parser for agent-history command.

This module provides the CLIParser class that builds the argparse parser
and converts parsed arguments into structured CommandRequest objects.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from agent_history.scope.context import CommandRequest, OutputArgs, ScopeArgs

# Version - will be updated by package metadata
__version__ = "2.0.0"


class WrappedHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom formatter that wraps help text nicely."""

    def __init__(
        self, prog: str, indent_increment: int = 2, max_help_position: int = 30, width: int = 100
    ):
        super().__init__(prog, indent_increment, max_help_position, width)


def _validate_split_lines(value: str) -> int:
    """Validate --split argument."""
    try:
        lines = int(value)
        if lines < 10:
            raise argparse.ArgumentTypeError("--split must be at least 10 lines")
        return lines
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid number: {value}")


class CLIParser:
    """Parse command line into structured CommandRequest.

    This class builds the argparse parser for agent-history and converts
    parsed arguments into CommandRequest objects for processing by the
    scope resolver and verb dispatcher.

    Example:
        parser = CLIParser()
        request = parser.parse(sys.argv[1:])
        # request now contains resource, verb, scope_args, output_args
    """

    def __init__(self):
        """Initialize the parser."""
        self.parser = self._build_parser()

    def parse(self, argv: List[str]) -> CommandRequest:
        """Parse command line arguments.

        Args:
            argv: Command line arguments (sys.argv[1:])

        Returns:
            CommandRequest with parsed command and options
        """
        # Preprocess argv to handle positional patterns that could conflict with subcommands
        argv = self._preprocess_argv(argv)
        args = self.parser.parse_args(argv)
        return self._build_request(args)

    def _preprocess_argv(self, argv: List[str]) -> List[str]:
        """Preprocess arguments to handle positional patterns.

        Converts positional patterns to -n flags for ws and session commands
        when they would otherwise be interpreted as subcommands.

        Args:
            argv: Original command line arguments.

        Returns:
            Preprocessed arguments with patterns converted to -n flags.
        """
        if not argv:
            return argv

        # Known subcommands for each resource
        ws_subcommands = {"list", "show", "export", "stats"}
        session_subcommands = {"list", "show", "export", "stats"}

        result = list(argv)

        # Find the position of ws or session command (may be after global flags like --agent)
        cmd_pos = None
        cmd_type = None
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg in ("ws", "session"):
                cmd_pos = i
                cmd_type = arg
                break
            # Skip global flag values (e.g., --agent gemini)
            if arg.startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                # Check if this is a flag that takes a value
                if arg in ("--agent",):
                    i += 2  # Skip flag and its value
                    continue
            i += 1

        if cmd_pos is None or cmd_type is None:
            return result

        subcommands = ws_subcommands if cmd_type == "ws" else session_subcommands

        # Case 1: Command followed directly by pattern (e.g., "session django" or "ws myproj")
        # Convert: [cmd, pattern, ...] -> [cmd, -n, pattern, ...]
        if cmd_pos + 1 < len(argv):
            next_arg = argv[cmd_pos + 1]
            if not next_arg.startswith("-") and next_arg not in subcommands:
                # Insert -n before the pattern
                result = list(argv[: cmd_pos + 1]) + ["-n", next_arg] + list(argv[cmd_pos + 2 :])
                return result

        # Case 2: Command with verb followed by pattern (e.g., "session list django")
        # Convert non-path patterns after verbs to -n flags for substring matching.
        # Users typically expect "session list django" to match "/home/user/django-app".
        # However, full paths like "/home/user/projects/auth" should remain positional
        # for exact matching to avoid matching "/home/user/projects/auth-infra".
        if cmd_pos + 2 < len(argv):
            verb = argv[cmd_pos + 1]
            if verb in subcommands:
                # Check for patterns after the verb
                new_result = list(argv[: cmd_pos + 2])  # Keep up to and including verb
                i = cmd_pos + 2
                while i < len(argv):
                    arg = argv[i]
                    # If it's a non-flag argument (potential pattern), convert to -n flag
                    # UNLESS it looks like a full path (starts with / or contains path separators)
                    if not arg.startswith("-"):
                        # Keep full paths as positional for exact matching
                        # Convert simple names/patterns to -n for substring matching
                        if arg.startswith("/") or "/" in arg:
                            # It's a path - keep as positional for exact matching
                            new_result.append(arg)
                        else:
                            # It's a simple pattern - convert to -n for substring matching
                            new_result.extend(["-n", arg])
                    else:
                        # Keep flags as-is, including their values
                        new_result.append(arg)
                        # If this flag takes a value, include it
                        if arg in (
                            "-n",
                            "--name",
                            "--format",
                            "--since",
                            "--until",
                            "--agent",
                            "-w",
                            "--width",
                            "-o",
                            "--output",
                            "--split",
                            "--jobs",
                            "--home",
                            "-r",
                            "--remote",
                            "--project",
                            "--by",
                            "--top-ws",
                        ):
                            if i + 1 < len(argv):
                                i += 1
                                new_result.append(argv[i])
                    i += 1
                return new_result

        return result

    def _build_parser(self) -> argparse.ArgumentParser:
        """Build argument parser with all subcommands."""
        parser = argparse.ArgumentParser(
            prog="agent-history",
            description=(
                "Browse and export AI coding assistant conversation history "
                "(Claude Code, Codex CLI, Gemini CLI)"
            ),
            formatter_class=WrappedHelpFormatter,
        )

        parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

        # Global agent selection flag (before subcommand)
        parser.add_argument(
            "--agent",
            choices=["auto", "claude", "codex", "gemini"],
            default="auto",
            help="Agent backend to use (default: auto-detect based on available data)",
        )

        # Create subparsers for commands
        subparsers = parser.add_subparsers(
            dest="command",
            help="Command to execute",
            required=False,
            metavar="COMMAND",
        )

        # Add all resource subparsers
        self._add_session_parser(subparsers)
        self._add_workspace_parser(subparsers)
        self._add_project_parser(subparsers)
        self._add_home_parser(subparsers)
        self._add_gemini_index_parser(subparsers)

        return parser

    # =========================================================================
    # Session subparser
    # =========================================================================

    def _add_session_parser(self, subparsers) -> None:
        """Add session subparser."""
        session_parser = subparsers.add_parser(
            "session",
            help="Session commands",
            description="Browse and export conversation sessions.",
        )
        session_parser.set_defaults(command="session", session_verb="list")
        # Add flags to session top-level so session -n pattern, session --ah work
        # Note: include_positional=False to avoid conflict with subcommand selection
        self._add_workspace_scope_flags(session_parser, include_positional=False)
        self._add_home_scope_flags(session_parser)
        self._add_date_filters(session_parser)
        self._add_agent_filter(session_parser)
        self._add_output_format(session_parser)

        sess_sub = session_parser.add_subparsers(dest="session_verb")
        sess_sub.required = False
        sess_sub.default = "list"

        # session list
        sess_list = sess_sub.add_parser("list", help="List sessions")
        sess_list.set_defaults(command="session", session_verb="list")
        self._add_workspace_scope_flags(sess_list, positional_name="workspace")
        self._add_home_scope_flags(sess_list)
        self._add_date_filters(sess_list)
        self._add_agent_filter(sess_list)
        sess_list.add_argument(
            "--counts",
            action="store_true",
            help="Count messages (slower, required for some sources)",
        )
        self._add_output_format(sess_list)

        # session show
        sess_show = sess_sub.add_parser("show", help="Show session details")
        sess_show.set_defaults(command="session", session_verb="show")
        sess_show.add_argument("session_id", help="Session identifier or path")
        self._add_home_scope_flags(sess_show)
        self._add_workspace_scope_flags(sess_show, positional_name="workspace")

        # session export
        sess_export = sess_sub.add_parser("export", help="Export sessions to markdown")
        sess_export.set_defaults(command="session", session_verb="export")
        self._add_workspace_scope_flags(sess_export, positional_name="target")
        sess_export.add_argument(
            "output_dir",
            nargs="?",
            default="./ai-chats",
            help="Output directory (default: ./ai-chats)",
        )
        self._add_export_options(sess_export)
        self._add_home_scope_flags(sess_export)
        self._add_agent_filter(sess_export)

        # session stats
        sess_stats = sess_sub.add_parser("stats", help="Stats for sessions")
        sess_stats.set_defaults(command="session", session_verb="stats")
        self._add_workspace_scope_flags(sess_stats)
        self._add_stats_options(sess_stats)
        self._add_home_scope_flags(sess_stats)
        self._add_agent_filter(sess_stats)

    # =========================================================================
    # Workspace subparser
    # =========================================================================

    def _add_workspace_parser(self, subparsers) -> None:
        """Add workspace (ws) subparser."""
        ws_parser = subparsers.add_parser(
            "ws",
            help="Workspace commands",
            description="Browse workspaces (project directories with sessions).",
        )
        ws_parser.set_defaults(command="ws", ws_verb="list")
        # Add flags to ws top-level so ws --local, ws -n pattern work
        # Note: include_positional=False to avoid conflict with subcommand selection
        self._add_workspace_scope_flags(ws_parser, include_positional=False)
        self._add_home_scope_flags(ws_parser)
        self._add_agent_filter(ws_parser)
        self._add_output_format(ws_parser)

        ws_sub = ws_parser.add_subparsers(dest="ws_verb")
        ws_sub.required = False
        ws_sub.default = "list"

        # ws list
        ws_list = ws_sub.add_parser("list", help="List workspaces")
        ws_list.set_defaults(command="ws", ws_verb="list")
        self._add_workspace_scope_flags(ws_list)
        self._add_home_scope_flags(ws_list)
        self._add_agent_filter(ws_list)
        self._add_output_format(ws_list)

        # ws show
        ws_show = ws_sub.add_parser("show", help="Show workspace details")
        ws_show.set_defaults(command="ws", ws_verb="show")
        ws_show.add_argument("workspace", nargs="*", help="Workspace path(s)")
        self._add_home_scope_flags(ws_show)
        self._add_agent_filter(ws_show)

        # ws export
        ws_export = ws_sub.add_parser("export", help="Export sessions from workspace")
        ws_export.set_defaults(command="ws", ws_verb="export")
        ws_export.add_argument("target", nargs="*", help="Workspace path(s)")
        ws_export.add_argument(
            "output_dir",
            nargs="?",
            default="./ai-chats",
            help="Output directory (default: ./ai-chats)",
        )
        self._add_export_options(ws_export)
        self._add_home_scope_flags(ws_export)
        self._add_agent_filter(ws_export)

        # ws stats
        ws_stats = ws_sub.add_parser("stats", help="Stats for workspace")
        ws_stats.set_defaults(command="ws", ws_verb="stats")
        self._add_workspace_scope_flags(ws_stats)
        self._add_stats_options(ws_stats)
        self._add_home_scope_flags(ws_stats)
        self._add_agent_filter(ws_stats)

    # =========================================================================
    # Project subparser
    # =========================================================================

    def _add_project_parser(self, subparsers) -> None:
        """Add project subparser."""
        project_parser = subparsers.add_parser(
            "project",
            help="Manage projects",
            description="Manage named workspace groups (projects).",
        )
        project_parser.set_defaults(command="project", project_command="list")
        proj_sub = project_parser.add_subparsers(dest="project_command")
        proj_sub.required = False
        proj_sub.default = "list"

        # project list
        proj_list = proj_sub.add_parser("list", help="List projects")
        proj_list.set_defaults(command="project", project_command="list")
        proj_list.add_argument(
            "-c",
            "--counts",
            action="store_true",
            help="Show session counts (slower)",
        )
        self._add_output_format(proj_list)

        # project show
        proj_show = proj_sub.add_parser("show", help="Show project details")
        proj_show.set_defaults(command="project", project_command="show")
        proj_show.add_argument("name", nargs="?", help="Project name (defaults to current project)")

        # project add
        proj_add = proj_sub.add_parser("add", help="Add workspace to project")
        proj_add.set_defaults(command="project", project_command="add")
        proj_add.add_argument("name", help="Project name")
        proj_add.add_argument("workspaces", nargs="*", help="Workspace paths to add")
        proj_add.add_argument("--pick", action="store_true", help="Interactive picker")
        proj_add.add_argument("--wsl", action="store_true", help="Add from WSL")
        proj_add.add_argument("--windows", action="store_true", help="Add from Windows")
        proj_add.add_argument(
            "--ah",
            "--all-homes",
            action="store_true",
            dest="all_homes",
            help="Add from all homes",
        )

        # project remove
        proj_remove = proj_sub.add_parser("remove", help="Remove workspace or project")
        proj_remove.set_defaults(command="project", project_command="remove")
        proj_remove.add_argument("name", help="Project name")
        proj_remove.add_argument("workspace", nargs="?", help="Workspace to remove")
        proj_remove.add_argument("--wsl", action="store_true", help="Remove from WSL")
        proj_remove.add_argument("--windows", action="store_true", help="Remove from Windows")

        # project export
        proj_export = proj_sub.add_parser("export", help="Export all sessions in project")
        proj_export.set_defaults(command="project", project_command="export")
        proj_export.add_argument("name", help="Project name")
        proj_export.add_argument(
            "output_dir",
            nargs="?",
            default="./ai-chats",
            help="Output directory (default: ./ai-chats)",
        )
        self._add_export_options(proj_export)
        self._add_home_scope_flags(proj_export)

        # project stats
        proj_stats = proj_sub.add_parser("stats", help="Stats for project")
        proj_stats.set_defaults(command="project", project_command="stats")
        proj_stats.add_argument("name", help="Project name")
        self._add_stats_options(proj_stats)
        self._add_home_scope_flags(proj_stats)

    # =========================================================================
    # Home subparser
    # =========================================================================

    def _add_home_parser(self, subparsers) -> None:
        """Add home subparser."""
        home_parser = subparsers.add_parser(
            "home",
            help="Manage homes",
            description="Manage data sources (local, WSL, Windows, web, SSH remotes).",
        )
        home_parser.set_defaults(command="home", home_verb="list")
        # Add flags to home top-level so home --local, home --wsl work
        home_parser.add_argument("--wsl", action="store_true", help="Show WSL distributions only")
        home_parser.add_argument("--windows", action="store_true", help="Show Windows users only")
        home_parser.add_argument("--web", action="store_true", help="Show Claude.ai status only")
        home_parser.add_argument("--local", action="store_true", help="Show local home only")
        home_parser.add_argument("--remotes", action="store_true", help="Show SSH remotes only")
        self._add_output_format(home_parser)

        home_sub = home_parser.add_subparsers(dest="home_verb")
        home_sub.required = False
        home_sub.default = "list"

        # home list
        home_list = home_sub.add_parser("list", help="List homes")
        home_list.set_defaults(command="home", home_verb="list")
        home_list.add_argument("--wsl", action="store_true", help="Show WSL distributions only")
        home_list.add_argument("--windows", action="store_true", help="Show Windows users only")
        home_list.add_argument("--web", action="store_true", help="Show Claude.ai status only")
        home_list.add_argument("--local", action="store_true", help="Show local home only")
        home_list.add_argument("--remotes", action="store_true", help="Show SSH remotes only")
        self._add_output_format(home_list)

        # home show
        home_show = home_sub.add_parser("show", help="Show home details")
        home_show.set_defaults(command="home", home_verb="show")
        home_show.add_argument("name", help="Home name")

        # home add
        home_add = home_sub.add_parser("add", help="Add a home")
        home_add.set_defaults(command="home", home_verb="add")
        home_add.add_argument("source", nargs="?", help="SSH remote (user@hostname)")
        home_add.add_argument("--windows", action="store_true", help="Add Windows as a home")
        home_add.add_argument(
            "--wsl",
            nargs="?",
            const="auto",
            metavar="DISTRO",
            help="Add WSL as a home",
        )
        home_add.add_argument("--web", action="store_true", help="Add Claude.ai web as a home")

        # home remove
        home_remove = home_sub.add_parser("remove", help="Remove a home")
        home_remove.set_defaults(command="home", home_verb="remove")
        home_remove.add_argument("source", nargs="?", help="Source to remove")
        home_remove.add_argument("--windows", action="store_true", help="Remove Windows")
        home_remove.add_argument(
            "--wsl", nargs="?", const="auto", metavar="DISTRO", help="Remove WSL"
        )
        home_remove.add_argument("--web", action="store_true", help="Remove Claude.ai web")

        # home export
        home_export = home_sub.add_parser("export", help="Export all sessions from home(s)")
        home_export.set_defaults(command="home", home_verb="export")
        home_export.add_argument("names", nargs="*", help="Home names (default: local)")
        home_export.add_argument(
            "output_dir",
            nargs="?",
            default="./ai-chats",
            help="Output directory (default: ./ai-chats)",
        )
        self._add_export_options(home_export)
        self._add_home_scope_flags(home_export)

        # home stats
        home_stats = home_sub.add_parser("stats", help="Stats for home(s)")
        home_stats.set_defaults(command="home", home_verb="stats")
        home_stats.add_argument("names", nargs="*", help="Home names (default: local)")
        self._add_stats_options(home_stats)
        self._add_home_scope_flags(home_stats)

    # =========================================================================
    # Gemini index subparser
    # =========================================================================

    def _add_gemini_index_parser(self, subparsers) -> None:
        """Add gemini-index subparser."""
        gi_parser = subparsers.add_parser(
            "gemini-index",
            help="Manage Gemini session index",
            description="Build and manage the Gemini session index for faster lookups.",
        )
        gi_parser.set_defaults(command="gemini-index", gemini_index_verb="list")
        gi_parser.add_argument(
            "--add",
            action="store_true",
            help="Add new sessions to the index",
        )
        gi_parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Rebuild the entire index from scratch",
        )
        gi_parser.add_argument(
            "--path",
            metavar="DIR",
            help="Path to Gemini sessions directory",
        )

    # =========================================================================
    # Common argument groups
    # =========================================================================

    def _add_home_scope_flags(self, parser) -> None:
        """Add home-scope flags shared by ws/session/project commands."""
        parser.add_argument(
            "--home",
            action="append",
            dest="homes",
            metavar="NAME",
            help="Specific saved home (repeatable)",
        )
        parser.add_argument(
            "--ah",
            "--all-homes",
            dest="all_homes",
            action="store_true",
            help="Include all configured homes",
        )
        parser.add_argument("--wsl", action="store_true", help="Use WSL home")
        parser.add_argument("--windows", action="store_true", help="Use Windows home")
        parser.add_argument("--web", action="store_true", help="Include Claude.ai web sessions")
        parser.add_argument(
            "-r",
            "--remote",
            action="append",
            dest="remotes",
            metavar="HOST",
            help="SSH remote (user@host) - repeatable",
        )
        parser.add_argument("--no-wsl", action="store_true", help="Exclude WSL sources (with --ah)")
        parser.add_argument(
            "--no-windows", action="store_true", help="Exclude Windows sources (with --ah)"
        )
        parser.add_argument(
            "--no-remote", action="store_true", help="Exclude SSH remotes (with --ah)"
        )
        parser.add_argument(
            "--no-web", action="store_true", help="Exclude web sessions (with --ah)"
        )
        parser.add_argument(
            "--local",
            action="store_true",
            help="Local home only (use with -r/--home to combine)",
        )

    def _add_workspace_scope_flags(
        self, parser, positional_name: str = "workspace", include_positional: bool = True
    ) -> None:
        """Add workspace scope flags.

        Args:
            parser: The argparse parser to add arguments to.
            positional_name: Name for the positional workspace argument.
            include_positional: Whether to include the positional argument.
                Set to False for parent parsers that have subparsers, to avoid
                conflicts where the positional consumes the subcommand name.
        """
        if include_positional:
            parser.add_argument(positional_name, nargs="*", help="Workspace path(s) (exact)")
        parser.add_argument(
            "-n",
            "--name",
            dest="name_patterns",
            action="append",
            help="Substring match workspace names/paths (repeatable)",
        )
        parser.add_argument(
            "--aw",
            "--all-workspaces",
            dest="all_workspaces",
            action="store_true",
            help="Use all workspaces in scope",
        )
        parser.add_argument(
            "--this",
            dest="this_only",
            action="store_true",
            help="Current workspace only (skip project auto-detection)",
        )
        parser.add_argument(
            "--project",
            action="append",
            dest="projects",
            metavar="NAME",
            help="Project name (repeatable)",
        )

    def _add_date_filters(self, parser) -> None:
        """Add since/until date filters."""
        parser.add_argument(
            "--since",
            metavar="DATE",
            help="Only include sessions on/after this date (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--until",
            metavar="DATE",
            help="Only include sessions on/before this date (YYYY-MM-DD)",
        )

    def _add_agent_filter(self, parser) -> None:
        """Add --agent filter flag to subparser."""
        parser.add_argument(
            "--agent",
            choices=["auto", "claude", "codex", "gemini"],
            default="auto",
            help="Agent backend to use (default: auto-detect)",
        )

    def _add_output_format(self, parser) -> None:
        """Add --format and --width for table output control."""
        parser.add_argument(
            "--format",
            choices=["table", "tsv", "json"],
            default=None,
            help="Output format (default: table for TTY, tsv for pipes)",
        )
        parser.add_argument(
            "-w",
            "--width",
            type=int,
            default=None,
            metavar="COLS",
            help="Table width in columns (default: 120, 0=no limit)",
        )

    def _add_export_options(self, parser) -> None:
        """Add export-related options."""
        parser.add_argument(
            "-o",
            "--output",
            metavar="DIR",
            dest="output_override",
            help="Output directory (default: ./ai-chats)",
        )
        parser.add_argument(
            "--force", action="store_true", help="Force re-export (default: incremental)"
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="export_json",
            help="Export as NDJSON (unified schema) instead of Markdown",
        )
        parser.add_argument(
            "--minimal",
            action="store_true",
            help="Minimal export: omit metadata, keep only conversation content",
        )
        parser.add_argument(
            "--split",
            metavar="LINES",
            type=_validate_split_lines,
            help="Split long conversations into parts (e.g., --split 500)",
        )
        parser.add_argument(
            "--jobs",
            type=int,
            default=None,
            help="Parallelism for exports (default: auto, up to 2)",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress per-file output (show summary only)",
        )
        parser.add_argument(
            "--flat",
            action="store_true",
            help="Use flat directory structure",
        )
        parser.add_argument(
            "--source",
            action="store_true",
            dest="include_source",
            help="Include raw source file alongside markdown export",
        )
        self._add_date_filters(parser)

    def _add_stats_options(self, parser) -> None:
        """Add stats options."""
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Force sync before showing stats",
        )
        parser.add_argument(
            "--no-sync",
            action="store_true",
            dest="no_sync",
            help="Skip auto-sync (faster, uses cached data)",
        )
        parser.add_argument(
            "--force", action="store_true", help="Force re-sync all files (ignore mtime)"
        )
        parser.add_argument(
            "--by",
            metavar="DIMS",
            help="Group by dimensions (comma-separated): home, agent, workspace, day, model, tool",
        )
        self._add_output_format(parser)
        parser.add_argument(
            "-H",
            "--human",
            action="store_true",
            help="Human-readable numbers (K/M/B) and time (Xd Xh Xm)",
        )
        parser.add_argument(
            "--time", action="store_true", help="Show time tracking with daily breakdown"
        )
        parser.add_argument("--tools", action="store_true", help="Show tool usage statistics")
        parser.add_argument("--models", action="store_true", help="Show model usage statistics")
        parser.add_argument(
            "--by-workspace", action="store_true", help="Group statistics by workspace"
        )
        parser.add_argument("--by-day", action="store_true", help="Group statistics by day")
        parser.add_argument(
            "--top-ws",
            type=int,
            default=None,
            help="Limit the number of workspaces shown per home (default: all)",
        )
        self._add_date_filters(parser)

    # =========================================================================
    # Build CommandRequest from parsed args
    # =========================================================================

    def _build_request(self, args: argparse.Namespace) -> CommandRequest:
        """Convert parsed args to CommandRequest."""
        # Determine resource and verb
        resource, verb = self._get_resource_verb(args)

        # Build scope args
        scope_args = self._build_scope_args(args)

        # Build output args (verb needed to handle -o differently for export)
        output_args = self._build_output_args(args, verb)

        # Build verb-specific args
        verb_args = self._build_verb_args(args, resource, verb)

        return CommandRequest(
            resource=resource,
            verb=verb,
            scope_args=scope_args,
            output_args=output_args,
            verb_args=verb_args,
        )

    def _get_resource_verb(self, args: argparse.Namespace) -> tuple[str, str]:
        """Extract resource and verb from parsed args."""
        command = getattr(args, "command", None)

        if command == "session":
            return ("session", getattr(args, "session_verb", "list"))
        elif command == "ws":
            return ("ws", getattr(args, "ws_verb", "list"))
        elif command == "project":
            return ("project", getattr(args, "project_command", "list"))
        elif command == "home":
            return ("home", getattr(args, "home_verb", "list"))
        elif command == "gemini-index":
            return ("gemini-index", "index")
        else:
            # Default to session list
            return ("session", "list")

    def _build_scope_args(self, args: argparse.Namespace) -> ScopeArgs:
        """Build ScopeArgs from parsed arguments."""
        # Home selection
        all_homes = getattr(args, "all_homes", False)
        home_type = None
        home_value = None
        home_names = list(getattr(args, "homes", None) or [])

        # Add remote hosts from -r/--remote flags
        remotes = getattr(args, "remotes", None) or []
        for remote in remotes:
            # Prefix remote hosts with "remote:" for identification
            home_names.append(f"remote:{remote}")

        if getattr(args, "wsl", False):
            home_type = "wsl"
        elif getattr(args, "windows", False):
            home_type = "windows"
        elif getattr(args, "local", False):
            home_type = "local"

        # Workspace selection
        all_workspaces = getattr(args, "all_workspaces", False)
        project = None
        projects = getattr(args, "projects", None)
        if projects and len(projects) == 1:
            project = projects[0]

        # Get positional patterns (exact match)
        patterns = []
        for attr in ["workspace", "target", "workspaces"]:
            value = getattr(args, attr, None)
            if value:
                patterns.extend(value)

        # Get name patterns from -n flag (substring match) - keep separate
        name_patterns = getattr(args, "name_patterns", None) or []

        this_only = getattr(args, "this_only", False)

        # Session filters
        agent = getattr(args, "agent", None)
        if agent == "auto":
            agent = None
        since = getattr(args, "since", None)
        until = getattr(args, "until", None)

        # Exclusions
        no_wsl = getattr(args, "no_wsl", False)
        no_windows = getattr(args, "no_windows", False)
        no_remote = getattr(args, "no_remote", False)
        no_web = getattr(args, "no_web", False)

        return ScopeArgs(
            all_homes=all_homes,
            home_type=home_type,
            home_value=home_value,
            home_names=home_names,
            all_workspaces=all_workspaces,
            project=project,
            patterns=patterns,
            name_patterns=name_patterns,
            this_only=this_only,
            agent=agent,
            since=since,
            until=until,
            no_wsl=no_wsl,
            no_windows=no_windows,
            no_remote=no_remote,
            no_web=no_web,
        )

    def _build_output_args(self, args: argparse.Namespace, verb: str = "") -> OutputArgs:
        """Build OutputArgs from parsed arguments.

        Args:
            args: Parsed arguments namespace.
            verb: The verb being executed (needed because -o means different things
                for export vs other commands).
        """
        format_type = getattr(args, "format", None)

        # For export, -o is the export directory, not the output file
        # So we don't set output_path from output_override for export
        output_path = None
        if verb != "export":
            output_override = getattr(args, "output_override", None)
            if output_override:
                output_path = Path(output_override)

        quiet = getattr(args, "quiet", False)
        human_readable = getattr(args, "human", False)
        width = getattr(args, "width", None)

        return OutputArgs(
            format=format_type,
            output_path=output_path,
            quiet=quiet,
            human_readable=human_readable,
            width=width,
        )

    def _build_verb_args(
        self, args: argparse.Namespace, resource: str, verb: str
    ) -> Dict[str, Any]:
        """Build verb-specific arguments."""
        verb_args: Dict[str, Any] = {}

        # Export-specific args
        if verb == "export":
            # Prefer -o/--output flag over positional output_dir
            verb_args["output_dir"] = (
                getattr(args, "output_override", None)
                or getattr(args, "output_dir", None)
                or "./ai-chats"
            )
            verb_args["force"] = getattr(args, "force", False)
            verb_args["export_json"] = getattr(args, "export_json", False)
            verb_args["minimal"] = getattr(args, "minimal", False)
            verb_args["split"] = getattr(args, "split", None)
            verb_args["jobs"] = getattr(args, "jobs", None)
            verb_args["flat"] = getattr(args, "flat", False)
            verb_args["include_source"] = getattr(args, "include_source", False)

        # Stats-specific args
        elif verb == "stats":
            verb_args["sync"] = getattr(args, "sync", False)
            verb_args["no_sync"] = getattr(args, "no_sync", False)
            verb_args["force"] = getattr(args, "force", False)
            verb_args["by"] = getattr(args, "by", None)
            verb_args["time"] = getattr(args, "time", False)
            verb_args["top_ws"] = getattr(args, "top_ws", None)

        # List-specific args
        elif verb == "list":
            verb_args["counts"] = getattr(args, "counts", False)

        # Show-specific args
        elif verb == "show":
            verb_args["session_id"] = getattr(args, "session_id", None)
            if resource == "project":
                verb_args["name"] = getattr(args, "name", None)
            elif resource == "home":
                verb_args["name"] = getattr(args, "name", None)

        # Project management args
        if resource == "project":
            verb_args["name"] = getattr(args, "name", None)
            if verb == "add":
                verb_args["workspaces"] = getattr(args, "workspaces", [])
                verb_args["pick"] = getattr(args, "pick", False)
            elif verb == "remove":
                verb_args["workspace"] = getattr(args, "workspace", None)

        # Home management args
        if resource == "home" and verb in ("add", "remove"):
            verb_args["source"] = getattr(args, "source", None)

        # Gemini-index args
        if resource == "gemini-index":
            verb_args["add"] = getattr(args, "add", False)
            verb_args["rebuild"] = getattr(args, "rebuild", False)
            verb_args["path"] = getattr(args, "path", None)

        return verb_args
