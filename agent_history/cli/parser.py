"""CLI Parser for agent-history command.

This module provides the CLIParser class that builds the argparse parser
and converts parsed arguments into structured CommandRequest objects.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List

from agent_history.cli.constants import (
    AGENT_CHOICES,
    DEFAULT_AGENT,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_VERB_INDEX,
    DEFAULT_VERB_LIST,
    DEFAULT_VERB_RUN,
    FLAGS_WITH_VALUES,
    GLOBAL_FLAGS_WITH_VALUES,
    MIN_SPLIT_LINES,
    OUTPUT_FORMAT_CHOICES,
    RESOURCE_FETCH,
    RESOURCE_GEMINI_INDEX,
    RESOURCE_HOME,
    RESOURCE_INSTALL,
    RESOURCE_PROJECT,
    RESOURCE_RESET,
    RESOURCE_SESSION,
    RESOURCE_WS,
    SESSION_SUBCOMMANDS,
    WS_SUBCOMMANDS,
)
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
        if lines < MIN_SPLIT_LINES:
            raise argparse.ArgumentTypeError(f"--split must be at least {MIN_SPLIT_LINES} lines")
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

        result = list(argv)

        def _looks_like_path(value: str) -> bool:
            if value.startswith("/"):
                return True
            if "/" in value:
                return True
            if "\\" in value:
                return True
            return len(value) > 1 and value[1] == ":"

        # Find the position of ws or session command (may be after global flags like --agent)
        cmd_pos = None
        cmd_type = None
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg in (RESOURCE_WS, RESOURCE_SESSION):
                cmd_pos = i
                cmd_type = arg
                break
            # Skip global flag values (e.g., --agent gemini)
            if arg.startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                # Check if this is a flag that takes a value
                if arg in GLOBAL_FLAGS_WITH_VALUES:
                    i += 2  # Skip flag and its value
                    continue
            i += 1

        if cmd_pos is None or cmd_type is None:
            return result

        subcommands = WS_SUBCOMMANDS if cmd_type == RESOURCE_WS else SESSION_SUBCOMMANDS

        # Case 1: Command followed directly by pattern (e.g., "session django" or "ws myproj")
        # Convert: [cmd, pattern, ...] -> [cmd, -n, pattern, ...]
        if cmd_pos + 1 < len(argv):
            next_arg = argv[cmd_pos + 1]
            if (
                not next_arg.startswith("-")
                and next_arg not in subcommands
                and not _looks_like_path(next_arg)
            ):
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
                if cmd_type == RESOURCE_SESSION and verb == "show":
                    return result
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
                        if _looks_like_path(arg):
                            # It's a path - keep as positional for exact matching
                            new_result.append(arg)
                        else:
                            # It's a simple pattern - convert to -n for substring matching
                            new_result.extend(["-n", arg])
                    else:
                        # Keep flags as-is, including their values
                        new_result.append(arg)
                        # If this flag takes a value, include it
                        if arg in FLAGS_WITH_VALUES:
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
            choices=AGENT_CHOICES,
            default=DEFAULT_AGENT,
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
        self._add_install_parser(subparsers)
        self._add_reset_parser(subparsers)
        self._add_fetch_parser(subparsers)

        return parser

    # =========================================================================
    # Session subparser
    # =========================================================================

    def _add_session_parser(self, subparsers) -> None:
        """Add session subparser."""
        session_parser = subparsers.add_parser(
            RESOURCE_SESSION,
            help="Session commands",
            description="Browse and export conversation sessions.",
        )
        session_parser.set_defaults(command=RESOURCE_SESSION, session_verb=DEFAULT_VERB_LIST)
        # Add flags to session top-level so session -n pattern, session --ah work
        # Note: include_positional=False to avoid conflict with subcommand selection
        self._add_workspace_scope_flags(session_parser, include_positional=False)
        self._add_home_scope_flags(session_parser)
        self._add_date_filters(session_parser)
        self._add_agent_filter(session_parser)
        self._add_output_format(session_parser)

        sess_sub = session_parser.add_subparsers(dest="session_verb")
        sess_sub.required = False
        sess_sub.default = DEFAULT_VERB_LIST

        # session list
        sess_list = sess_sub.add_parser(DEFAULT_VERB_LIST, help="List sessions")
        sess_list.set_defaults(command=RESOURCE_SESSION, session_verb=DEFAULT_VERB_LIST)
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
        sess_show.set_defaults(command=RESOURCE_SESSION, session_verb="show")
        sess_show.add_argument("session_id", help="Session identifier or path")
        self._add_home_scope_flags(sess_show)
        self._add_workspace_scope_flags(sess_show, positional_name="workspace")

        # session export
        sess_export = sess_sub.add_parser("export", help="Export sessions to markdown")
        sess_export.set_defaults(command=RESOURCE_SESSION, session_verb="export")
        self._add_workspace_scope_flags(sess_export, positional_name="target")
        sess_export.add_argument(
            "--session",
            "--session-id",
            dest="session_ids",
            action="append",
            metavar="ID",
            help="Export specific session IDs or filenames (repeatable or comma-separated)",
        )
        sess_export.add_argument(
            "output_dir",
            nargs="?",
            default=DEFAULT_OUTPUT_DIR,
            help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
        )
        self._add_export_options(sess_export)
        self._add_home_scope_flags(sess_export)
        self._add_agent_filter(sess_export)

        # session stats
        sess_stats = sess_sub.add_parser("stats", help="Stats for sessions")
        sess_stats.set_defaults(command=RESOURCE_SESSION, session_verb="stats")
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
            RESOURCE_WS,
            help="Workspace commands",
            description="Browse workspaces (project directories with sessions).",
        )
        ws_parser.set_defaults(command=RESOURCE_WS, ws_verb=DEFAULT_VERB_LIST)
        # Add flags to ws top-level so ws --local, ws -n pattern work
        # Note: include_positional=False to avoid conflict with subcommand selection
        self._add_workspace_scope_flags(ws_parser, include_positional=False)
        self._add_home_scope_flags(ws_parser)
        self._add_agent_filter(ws_parser)
        self._add_output_format(ws_parser)

        ws_sub = ws_parser.add_subparsers(dest="ws_verb")
        ws_sub.required = False
        ws_sub.default = DEFAULT_VERB_LIST

        # ws list
        ws_list = ws_sub.add_parser(DEFAULT_VERB_LIST, help="List workspaces")
        ws_list.set_defaults(command=RESOURCE_WS, ws_verb=DEFAULT_VERB_LIST)
        self._add_workspace_scope_flags(ws_list)
        self._add_home_scope_flags(ws_list)
        self._add_agent_filter(ws_list)
        self._add_output_format(ws_list)

        # ws show
        ws_show = ws_sub.add_parser("show", help="Show workspace details")
        ws_show.set_defaults(command=RESOURCE_WS, ws_verb="show")
        ws_show.add_argument("workspace", nargs="*", help="Workspace path(s)")
        self._add_home_scope_flags(ws_show)
        self._add_agent_filter(ws_show)

        # ws export
        ws_export = ws_sub.add_parser("export", help="Export sessions from workspace")
        ws_export.set_defaults(command=RESOURCE_WS, ws_verb="export")
        ws_export.add_argument("target", nargs="*", help="Workspace path(s)")
        ws_export.add_argument(
            "output_dir",
            nargs="?",
            default=DEFAULT_OUTPUT_DIR,
            help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
        )
        self._add_export_options(ws_export)
        self._add_home_scope_flags(ws_export)
        self._add_agent_filter(ws_export)

        # ws stats
        ws_stats = ws_sub.add_parser("stats", help="Stats for workspace")
        ws_stats.set_defaults(command=RESOURCE_WS, ws_verb="stats")
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
            RESOURCE_PROJECT,
            help="Manage projects",
            description="Manage named workspace groups (projects).",
        )
        project_parser.set_defaults(command=RESOURCE_PROJECT, project_command=DEFAULT_VERB_LIST)
        proj_sub = project_parser.add_subparsers(dest="project_command")
        proj_sub.required = False
        proj_sub.default = DEFAULT_VERB_LIST

        # project list
        proj_list = proj_sub.add_parser(DEFAULT_VERB_LIST, help="List projects")
        proj_list.set_defaults(command=RESOURCE_PROJECT, project_command=DEFAULT_VERB_LIST)
        proj_list.add_argument(
            "-c",
            "--counts",
            action="store_true",
            help="Show session counts (slower)",
        )
        self._add_output_format(proj_list)

        # project show
        proj_show = proj_sub.add_parser("show", help="Show project details")
        proj_show.set_defaults(command=RESOURCE_PROJECT, project_command="show")
        proj_show.add_argument("name", nargs="?", help="Project name (defaults to current project)")

        # project add
        proj_add = proj_sub.add_parser("add", help="Add workspace to project")
        proj_add.set_defaults(command=RESOURCE_PROJECT, project_command="add")
        proj_add.add_argument("name", help="Project name")
        self._add_workspace_scope_flags(
            proj_add, positional_name="workspaces", include_project=False
        )
        self._add_home_scope_flags(proj_add)
        proj_add.add_argument("--pick", action="store_true", help="Interactive picker")

        # project remove
        proj_remove = proj_sub.add_parser("remove", help="Remove workspace or project")
        proj_remove.set_defaults(command=RESOURCE_PROJECT, project_command="remove")
        proj_remove.add_argument("name", help="Project name")
        proj_remove.add_argument("workspace", nargs="?", help="Workspace to remove")
        proj_remove.add_argument("--wsl", action="store_true", help="Remove from WSL")
        proj_remove.add_argument("--windows", action="store_true", help="Remove from Windows")

        # project export
        proj_export = proj_sub.add_parser("export", help="Export all sessions in project")
        proj_export.set_defaults(command=RESOURCE_PROJECT, project_command="export")
        proj_export.add_argument("name", help="Project name")
        proj_export.add_argument(
            "output_dir",
            nargs="?",
            default=DEFAULT_OUTPUT_DIR,
            help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
        )
        self._add_export_options(proj_export)
        self._add_home_scope_flags(proj_export)

        # project stats
        proj_stats = proj_sub.add_parser("stats", help="Stats for project")
        proj_stats.set_defaults(command=RESOURCE_PROJECT, project_command="stats")
        proj_stats.add_argument("name", help="Project name")
        self._add_stats_options(proj_stats)
        self._add_home_scope_flags(proj_stats)

    # =========================================================================
    # Home subparser
    # =========================================================================

    def _add_home_parser(self, subparsers) -> None:
        """Add home subparser."""
        home_parser = subparsers.add_parser(
            RESOURCE_HOME,
            help="Manage homes",
            description="Manage data sources (local, WSL, Windows, web, SSH remotes).",
        )
        home_parser.set_defaults(command=RESOURCE_HOME, home_verb=DEFAULT_VERB_LIST)
        # Add flags to home top-level so home --local, home --wsl work
        home_parser.add_argument("--wsl", action="store_true", help="Show WSL distributions only")
        home_parser.add_argument("--windows", action="store_true", help="Show Windows users only")
        home_parser.add_argument("--web", action="store_true", help="Show Claude.ai status only")
        home_parser.add_argument("--local", action="store_true", help="Show local home only")
        home_parser.add_argument("--remotes", action="store_true", help="Show SSH remotes only")
        self._add_output_format(home_parser)

        home_sub = home_parser.add_subparsers(dest="home_verb")
        home_sub.required = False
        home_sub.default = DEFAULT_VERB_LIST

        # home list
        home_list = home_sub.add_parser(DEFAULT_VERB_LIST, help="List homes")
        home_list.set_defaults(command=RESOURCE_HOME, home_verb=DEFAULT_VERB_LIST)
        home_list.add_argument("--wsl", action="store_true", help="Show WSL distributions only")
        home_list.add_argument("--windows", action="store_true", help="Show Windows users only")
        home_list.add_argument("--web", action="store_true", help="Show Claude.ai status only")
        home_list.add_argument("--local", action="store_true", help="Show local home only")
        home_list.add_argument("--remotes", action="store_true", help="Show SSH remotes only")
        home_list.add_argument(
            "--counts",
            action="store_true",
            help="Show session counts (may be slower)",
        )
        self._add_output_format(home_list)

        # home show
        home_show = home_sub.add_parser("show", help="Show home details")
        home_show.set_defaults(command=RESOURCE_HOME, home_verb="show")
        home_show.add_argument("name", help="Home name")

        # home add
        home_add = home_sub.add_parser("add", help="Add a home")
        home_add.set_defaults(command=RESOURCE_HOME, home_verb="add")
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
        home_remove.set_defaults(command=RESOURCE_HOME, home_verb="remove")
        home_remove.add_argument("source", nargs="?", help="Source to remove")
        home_remove.add_argument("--windows", action="store_true", help="Remove Windows")
        home_remove.add_argument(
            "--wsl", nargs="?", const="auto", metavar="DISTRO", help="Remove WSL"
        )
        home_remove.add_argument("--web", action="store_true", help="Remove Claude.ai web")

        # home export
        home_export = home_sub.add_parser("export", help="Export all sessions from home(s)")
        home_export.set_defaults(command=RESOURCE_HOME, home_verb="export")
        home_export.add_argument("names", nargs="*", help="Home names (default: local)")
        home_export.add_argument(
            "output_dir",
            nargs="?",
            default=DEFAULT_OUTPUT_DIR,
            help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
        )
        self._add_export_options(home_export)
        self._add_home_scope_flags(home_export)

        # home stats
        home_stats = home_sub.add_parser("stats", help="Stats for home(s)")
        home_stats.set_defaults(command=RESOURCE_HOME, home_verb="stats")
        home_stats.add_argument("names", nargs="*", help="Home names (default: local)")
        self._add_stats_options(home_stats)
        self._add_home_scope_flags(home_stats)

    # =========================================================================
    # Gemini index subparser
    # =========================================================================

    def _add_gemini_index_parser(self, subparsers) -> None:
        """Add gemini-index subparser."""
        gi_parser = subparsers.add_parser(
            RESOURCE_GEMINI_INDEX,
            help="Manage Gemini session index",
            description=(
                "Manage the Gemini hash-to-path index. By default, lists all mappings. "
                "Use --add to add project paths to the index. "
                "For each path added, computes its SHA-256 hash and checks if Gemini "
                "has sessions for that project. If sessions exist, adds the mapping "
                "so agent-history can display readable workspace paths instead of hashes."
            ),
        )
        gi_parser.set_defaults(command=RESOURCE_GEMINI_INDEX, gemini_index_verb=DEFAULT_VERB_LIST)
        gi_parser.add_argument(
            "--add",
            "-a",
            nargs="*",
            dest="add_paths",
            metavar="PATH",
            help="Add project directories to index (default: current directory if no paths given)",
        )
        gi_parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Rebuild the entire index from scratch",
        )
        gi_parser.add_argument(
            "--list",
            "-l",
            action="store_true",
            dest="list_index",
            help="List all mappings in the hash index (default if no options)",
        )
        gi_parser.add_argument(
            "--full-hash",
            action="store_true",
            help="Show full SHA-256 hashes instead of truncated (with --list)",
        )

    def _add_install_parser(self, subparsers) -> None:
        """Add install subparser."""
        install_parser = subparsers.add_parser(
            RESOURCE_INSTALL,
            help="Install CLI and Claude skill",
            description="Install the CLI binary and Claude skill files.",
        )
        install_parser.set_defaults(command=RESOURCE_INSTALL, install_verb=DEFAULT_VERB_RUN)
        install_parser.add_argument("--bin-dir", help="Custom binary install directory")
        install_parser.add_argument("--skill-dir", help="Custom skill install directory")
        install_parser.add_argument("--skip-cli", action="store_true", help="Skip CLI install")
        install_parser.add_argument("--skip-skill", action="store_true", help="Skip skill install")
        install_parser.add_argument(
            "--skip-settings", action="store_true", help="Skip settings update"
        )

    def _add_reset_parser(self, subparsers) -> None:
        """Add reset subparser."""
        reset_parser = subparsers.add_parser(
            RESOURCE_RESET,
            help="Reset stored data",
            description="Reset metrics database, config, and caches.",
        )
        reset_parser.set_defaults(command=RESOURCE_RESET, reset_verb=DEFAULT_VERB_RUN)
        reset_parser.add_argument(
            "what",
            nargs="?",
            choices=["all", "db", "config", "settings"],
            default="all",
            help="What to reset (default: all)",
        )
        reset_parser.add_argument("-y", "--yes", action="store_true", help="Confirm reset")
        reset_parser.add_argument("--db", action="store_true", help="Reset metrics database")
        reset_parser.add_argument("--config", action="store_true", help="Reset config files")
        reset_parser.add_argument("--settings", action="store_true", help="Reset caches")

    def _add_fetch_parser(self, subparsers) -> None:
        """Add fetch subparser."""
        fetch_parser = subparsers.add_parser(
            RESOURCE_FETCH,
            help="Fetch remote sessions into cache",
            description="Fetch remote sessions and cache them locally.",
        )
        fetch_parser.set_defaults(command=RESOURCE_FETCH, fetch_verb=DEFAULT_VERB_RUN)
        self._add_workspace_scope_flags(fetch_parser)
        self._add_home_scope_flags(fetch_parser)
        self._add_agent_filter(fetch_parser)


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
        self,
        parser,
        positional_name: str = "workspace",
        include_positional: bool = True,
        include_project: bool = True,
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
        if include_project:
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
            choices=AGENT_CHOICES,
            default=DEFAULT_AGENT,
            help="Agent backend to use (default: auto-detect)",
        )

    def _add_output_format(self, parser) -> None:
        """Add --format and --width for table output control."""
        parser.add_argument(
            "--format",
            choices=OUTPUT_FORMAT_CHOICES,
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
            help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
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
        self._normalize_export_args(args)

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

    def _split_csv_list(self, values: List[str]) -> List[str]:
        """Split comma-separated CLI values into a flat list."""
        result: List[str] = []
        for item in values:
            for part in str(item).split(","):
                part = part.strip()
                if part:
                    result.append(part)
        return result

    def _normalize_export_args(self, args: argparse.Namespace) -> None:
        """Normalize export args when positional output_dir is consumed by nargs='*'."""
        command = getattr(args, "command", None)

        if command == RESOURCE_WS and getattr(args, "ws_verb", None) == "export":
            if getattr(args, "output_override", None):
                return
            targets = list(getattr(args, "target", None) or [])
            if getattr(args, "output_dir", DEFAULT_OUTPUT_DIR) == DEFAULT_OUTPUT_DIR and len(targets) > 1:
                args.output_dir = targets[-1]
                args.target = targets[:-1]

        if command == RESOURCE_HOME and getattr(args, "home_verb", None) == "export":
            if getattr(args, "output_override", None):
                return
            names = list(getattr(args, "names", None) or [])
            if getattr(args, "output_dir", DEFAULT_OUTPUT_DIR) == DEFAULT_OUTPUT_DIR and len(names) > 1:
                args.output_dir = names[-1]
                args.names = names[:-1]

    def _get_resource_verb(self, args: argparse.Namespace) -> tuple[str, str]:
        """Extract resource and verb from parsed args."""
        command = getattr(args, "command", None)

        if command == RESOURCE_SESSION:
            return (RESOURCE_SESSION, getattr(args, "session_verb", DEFAULT_VERB_LIST))
        elif command == RESOURCE_WS:
            return (RESOURCE_WS, getattr(args, "ws_verb", DEFAULT_VERB_LIST))
        elif command == RESOURCE_PROJECT:
            return (RESOURCE_PROJECT, getattr(args, "project_command", DEFAULT_VERB_LIST))
        elif command == RESOURCE_HOME:
            return (RESOURCE_HOME, getattr(args, "home_verb", DEFAULT_VERB_LIST))
        elif command == RESOURCE_GEMINI_INDEX:
            return (RESOURCE_GEMINI_INDEX, DEFAULT_VERB_INDEX)
        elif command == RESOURCE_INSTALL:
            return (RESOURCE_INSTALL, DEFAULT_VERB_RUN)
        elif command == RESOURCE_RESET:
            return (RESOURCE_RESET, DEFAULT_VERB_RUN)
        elif command == RESOURCE_FETCH:
            return (RESOURCE_FETCH, DEFAULT_VERB_RUN)
        else:
            # Default to session list
            return (RESOURCE_SESSION, DEFAULT_VERB_LIST)

    def _build_scope_args(self, args: argparse.Namespace) -> ScopeArgs:
        """Build ScopeArgs from parsed arguments."""
        # Home selection
        all_homes = getattr(args, "all_homes", False)
        home_type = None
        home_value = None
        home_names = list(getattr(args, "homes", None) or [])
        command = getattr(args, "command", None)

        if command == RESOURCE_HOME:
            name = getattr(args, "name", None)
            if name:
                home_names.append(name)
            names = getattr(args, "names", None) or []
            home_names.extend(names)

        # Add remote hosts from -r/--remote flags
        remotes = getattr(args, "remotes", None) or []
        for remote in remotes:
            # Prefix remote hosts with "remote:" for identification
            home_names.append(f"remote:{remote}")

        if getattr(args, "web", False):
            home_names.append("web")

        if getattr(args, "wsl", False):
            home_type = "wsl"
        elif getattr(args, "windows", False):
            home_type = "windows"
        elif getattr(args, "local", False):
            home_type = "local"

        # Workspace selection
        all_workspaces = getattr(args, "all_workspaces", False)
        projects = list(getattr(args, "projects", None) or [])
        if command == RESOURCE_PROJECT:
            project_name = getattr(args, "name", None)
            project_command = getattr(args, "project_command", None)
            if project_command in ("show", "export", "stats") and project_name:
                projects = [project_name]

        # Get positional patterns (exact match)
        patterns = []
        for attr in ["workspace", "target", "workspaces"]:
            value = getattr(args, attr, None)
            if value:
                patterns.extend(value)

        # Get name patterns from -n flag (substring match) - keep separate
        name_patterns = getattr(args, "name_patterns", None) or []

        this_only = getattr(args, "this_only", False)

        # Session ID selection for session export (implies all workspaces if no scope)
        session_ids = self._split_csv_list(list(getattr(args, "session_ids", None) or []))
        if (
            command == RESOURCE_SESSION
            and getattr(args, "session_verb", None) == "export"
            and session_ids
            and not (patterns or name_patterns or projects or all_workspaces or this_only)
        ):
            all_workspaces = True

        # Session filters
        agent = getattr(args, "agent", None)
        if agent == DEFAULT_AGENT:
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
            projects=projects,
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
                or DEFAULT_OUTPUT_DIR
            )
            verb_args["force"] = getattr(args, "force", False)
            verb_args["export_json"] = getattr(args, "export_json", False)
            verb_args["minimal"] = getattr(args, "minimal", False)
            verb_args["split"] = getattr(args, "split", None)
            verb_args["jobs"] = getattr(args, "jobs", None)
            verb_args["flat"] = getattr(args, "flat", False)
            verb_args["include_source"] = getattr(args, "include_source", False)
            if resource == RESOURCE_SESSION:
                raw_ids = list(getattr(args, "session_ids", None) or [])
                verb_args["session_ids"] = self._split_csv_list(raw_ids)

        # Stats-specific args
        elif verb == "stats":
            verb_args["sync"] = getattr(args, "sync", False)
            verb_args["no_sync"] = getattr(args, "no_sync", False)
            verb_args["force"] = getattr(args, "force", False)
            raw_by = getattr(args, "by", None)
            verb_args["by"] = self._split_csv_list([raw_by]) if raw_by else None
            verb_args["time"] = getattr(args, "time", False)
            verb_args["top_ws"] = getattr(args, "top_ws", None)

        # List-specific args
        elif verb == "list":
            verb_args["counts"] = getattr(args, "counts", False)

        # Show-specific args
        elif verb == "show":
            verb_args["session_id"] = getattr(args, "session_id", None)
            if resource == RESOURCE_PROJECT:
                verb_args["name"] = getattr(args, "name", None)
            elif resource == RESOURCE_HOME:
                verb_args["name"] = getattr(args, "name", None)

        # Project management args
        if resource == RESOURCE_PROJECT:
            verb_args["name"] = getattr(args, "name", None)
            if verb == "add":
                verb_args["workspaces"] = getattr(args, "workspaces", [])
                verb_args["pick"] = getattr(args, "pick", False)
            elif verb == "remove":
                verb_args["workspace"] = getattr(args, "workspace", None)
                verb_args["wsl"] = getattr(args, "wsl", False)
                verb_args["windows"] = getattr(args, "windows", False)

        # Home management args
        if resource == RESOURCE_HOME and verb in ("add", "remove"):
            verb_args["source"] = getattr(args, "source", None)

        # Gemini-index args
        if resource == RESOURCE_GEMINI_INDEX:
            verb_args["add_paths"] = getattr(args, "add_paths", None)
            verb_args["rebuild"] = getattr(args, "rebuild", False)
            verb_args["list_index"] = getattr(args, "list_index", False)
            verb_args["full_hash"] = getattr(args, "full_hash", False)

        if resource == RESOURCE_INSTALL:
            verb_args["bin_dir"] = getattr(args, "bin_dir", None)
            verb_args["skill_dir"] = getattr(args, "skill_dir", None)
            verb_args["skip_cli"] = getattr(args, "skip_cli", False)
            verb_args["skip_skill"] = getattr(args, "skip_skill", False)
            verb_args["skip_settings"] = getattr(args, "skip_settings", False)

        if resource == RESOURCE_RESET:
            what = getattr(args, "what", "all")
            verb_args["reset_db"] = getattr(args, "db", False) or what == "db"
            verb_args["reset_config"] = getattr(args, "config", False) or what == "config"
            verb_args["reset_settings"] = getattr(args, "settings", False) or what == "settings"
            verb_args["yes"] = getattr(args, "yes", False)

        if resource == RESOURCE_FETCH:
            verb_args["fetch"] = True

        return verb_args
