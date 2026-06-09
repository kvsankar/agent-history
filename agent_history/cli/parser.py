"""CLI Parser for cagelens command.

This module provides the CLIParser class that builds the argparse parser
and converts parsed arguments into structured CommandRequest objects.

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from agent_history.backends.registry import get_agent_choices
from agent_history.cli.constants import (
    DEFAULT_AGENT,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_VERB_INDEX,
    DEFAULT_VERB_LIST,
    DEFAULT_VERB_RUN,
    EXPORT_FORMAT_CHOICES,
    EXPORT_FORMAT_MARKDOWN,
    EXPORT_LAYOUT_CHOICES,
    EXPORT_LAYOUT_DEFAULT,
    FLAGS_WITH_VALUES,
    GLOBAL_FLAGS_WITH_VALUES,
    MARKDOWN_DEFAULT_LEVEL,
    MARKDOWN_MAX_LEVEL,
    MIN_SPLIT_LINES,
    OUTPUT_FORMAT_CHOICES,
    RESOURCE_FETCH,
    RESOURCE_GEMINI_INDEX,
    RESOURCE_HOME,
    RESOURCE_INSTALL,
    RESOURCE_PROJECT,
    RESOURCE_RESET,
    RESOURCE_SESSION,
    RESOURCE_STATS,
    RESOURCE_WS,
    SESSION_SUBCOMMANDS,
    WS_SUBCOMMANDS,
)
from agent_history.scope.context import CommandRequest, OutputArgs, ScopeArgs

# Version - will be updated by package metadata
__version__ = "2.0.0"

STATS_DIMENSION_ALIASES = {
    "ws": "workspace",
    "workspaces": "workspace",
    "proj": "project",
    "projects": "project",
    "homes": "home",
    "agents": "agent",
    "days": "day",
    "months": "month",
    "models": "model",
    "tools": "tool",
}


TOP_LEVEL_EPILOG = """\
Progressive help:
  cagelens ws --help              Discover workspaces and workspace flags
  cagelens session --help         List, export, and analyze sessions
  cagelens project --help         Group related workspaces
  cagelens home --help            Configure local, Windows, WSL, web, and remote homes

Common commands:
  cagelens ws                     List all local workspaces with counts
  cagelens session list           List sessions for the current workspace/project
  cagelens session list --aw      List sessions from all local workspaces
  cagelens session export -o DIR  Export current workspace/project sessions
  cagelens stats --sync           Refresh metrics and show stats

Scope shortcuts:
  --aw = all workspaces, --ah = all homes, --glob PAT = workspace glob, --regex RE = workspace regex
  --this = current workspace only, --project NAME = configured workspace group
  --format json is best for automation; table/TSV are for terminal and pipes.
  Quote glob/regex patterns so your shell passes them to cagelens unchanged.

Migration:
  Old short aliases are not part of the current CLI. Use session list, ws, project, and home.
"""


WS_EPILOG = """\
Default behavior:
  cagelens ws lists all workspaces in the selected homes.
  Output columns: HOME, WORKSPACE, SESSIONS, STATUS, MODIFIED.

Examples:
  cagelens ws                     All local workspaces
  cagelens ws --glob "*auth*"             Workspaces whose path contains "auth"
  cagelens ws --ah                Workspaces from all configured homes
  cagelens ws --format json       Machine-readable workspace summaries

Tip:
  Quote glob patterns, for example --glob '/home/user/projects/auth*'.

Next help:
  cagelens ws list --help         Workspace listing options
  cagelens ws export --help       Export sessions from workspaces
  cagelens session --help         Work with individual sessions
"""


WS_LIST_EPILOG = """\
Default behavior:
  Lists every workspace in the selected home scope. Counts and MODIFIED are
  workspace summaries; message content is not parsed for this command.

Examples:
  cagelens ws list
  cagelens ws list --glob "*payments*" --ah
  cagelens ws list --agent codex --format json

Tip:
  Quote glob patterns, for example --glob '/home/user/projects/auth*'.
"""


SESSION_EPILOG = """\
Default behavior:
  cagelens session is the same as cagelens session list.
  Without --aw or a pattern, session commands use the current workspace or its
  auto-detected project.

Examples:
  cagelens session list           Current workspace/project sessions
  cagelens session list --aw      All local workspace sessions
  cagelens session list --glob "*auth*"   Sessions from matching workspaces
  cagelens session export -o DIR  Export current workspace/project sessions
  cagelens stats --sync           Refresh metrics and show stats

Tip:
  Quote glob patterns, for example --glob "*auth*", so the shell does not
  expand them to existing filesystem paths before cagelens sees them.

Next help:
  cagelens session list --help
  cagelens session export --help
  cagelens session stats --help
"""


SESSION_LIST_EPILOG = """\
Default behavior:
  Lists sessions for the current workspace or auto-detected project.
  Output columns: AGENT, HOME, WORKSPACE, FILE, MESSAGES, MODIFIED.
  MESSAGES is populated when available; use --counts to force message counting.

Examples:
  cagelens session list
  cagelens session list --aw --format json
  cagelens session list --glob "*auth*" --since 2026-01-01
  cagelens session list --ah --aw --agent codex

Tip:
  Quote glob patterns, for example --glob '/home/user/projects/auth*'.
"""


SESSION_SHOW_EPILOG = """\
Examples:
  cagelens session list --aw
      First find the FILE or session ID to inspect.

  cagelens session show /path/to/session.jsonl
      Show details for a specific source file.

  cagelens session show SESSION_ID --project myproj
      Search a configured project when the ID is not unique locally.
"""


EXPORT_EPILOG = """\
Output:
  Prefer -o DIR for export destination. Positional workspace/target arguments
  are exact paths or IDs; use --glob or --regex for pattern matching.

Examples:
  cagelens session export --project myproj -o ./exports
  cagelens session export --glob "*auth*" -o ./exports
  cagelens ws export /home/user/project -o ./exports
  cagelens project export myproj -o ./exports
"""


STATS_EPILOG = """\
Stats modes:
  cagelens stats                  Dashboard summary from cached metrics
  cagelens stats --sync           Refresh metrics first, then show summary
  cagelens stats rollup           Tabular rollups for time, tokens, sessions

Examples:
  cagelens stats --time
      Show the dashboard with time coverage and daily time details.

  cagelens stats rollup --metric time --by month
      Show work-period time totals by month.

  cagelens stats rollup --metric time --by project,month
      Show monthly work-period time totals per project.

  cagelens stats rollup --metric time --by workspace,month --project myproj
      Show monthly work-period time totals per workspace in a project.

  cagelens stats rollup --metric tokens --by workspace,model
      Show token totals by workspace and model.

  cagelens stats rollup --metric tokens --by ws,month
      Show compact token totals using K/M/B suffixes.

  cagelens stats rollup --metric tokens --by ws,month --separator
      Add a -- separator before the table.

  cagelens stats rollup --metric tokens --by ws,month --raw --no-total
      Show raw token counts and suppress the default totals row.

  cagelens stats rollup --metric tokens --by agent,month --sort month,agent --asc
      Sort grouped rows chronologically, then by agent.

Tip:
  Summary flags such as --time expand the dashboard. Use stats rollup with
  --metric and --by for monthly, project, workspace, model, or token tables.
"""


STATS_SUMMARY_EPILOG = """\
Summary examples:
  cagelens stats
      Fast cached dashboard for the current workspace or auto-detected project.

  cagelens stats --sync --force
      Rebuild metrics for the selected scope before showing the dashboard.

  cagelens stats --time
      Add time coverage and daily work-period totals to the dashboard.

For monthly totals:
  cagelens stats rollup --metric time --by month
  cagelens stats rollup --metric time --by project,month
"""


STATS_ROLLUP_EPILOG = """\
Rollup examples:
  cagelens stats rollup --metric time --by month
      Work-period time totals by month.

  cagelens stats rollup --metric time --by project,month
      Monthly work-period time totals per project.

  cagelens stats rollup --metric time --by workspace,month --project myproj
      Monthly work-period time totals per workspace in a project.

  cagelens stats rollup --metric tokens --by workspace,model
      Token totals by workspace and model.

  cagelens stats rollup --metric tokens --by ws,month
      Compact token totals using K/M/B suffixes.

  cagelens stats rollup --metric tokens --by ws,month --separator
      Add a -- separator before the table.

  cagelens stats rollup --metric tokens --by ws,month --raw --no-total
      Show raw token counts and suppress the default totals row.

  cagelens stats rollup --metric tokens --by agent,month --sort month,agent --asc
      Sort grouped rows chronologically, then by agent.

  cagelens stats rollup --metric all --by project --format json
      Full metric payload grouped by project.
"""


PROJECT_EPILOG = """\
Projects are named groups of related workspaces across homes.

Examples:
  cagelens project list
  cagelens project add myproj --this
  cagelens project add myproj --glob "*auth*" --dry-run
  cagelens project show myproj
  cagelens session list --project myproj
"""


PROJECT_ADD_EPILOG = """\
Matching:
  Positional workspace arguments are exact paths or IDs. Use --glob for
  shell-style matching and quote the pattern so your shell does not expand it.

Examples:
  cagelens project add myproj --this
      Add the current workspace.

  cagelens project add myproj /home/user/projects/auth
      Add one exact workspace path.

  cagelens project add myproj --glob "*auth*" --dry-run
      Preview all matching local workspaces before writing config.

  cagelens project add myproj --glob "*auth*" --ah
      Add matching workspaces across configured homes.
"""


HOME_EPILOG = """\
Homes are session sources: local, Windows, WSL, Claude web, or SSH remotes.

Examples:
  cagelens home list
  cagelens home add --windows
  cagelens home add --wsl Ubuntu
  cagelens home add user@host
  cagelens ws --ah
"""


HOME_ADD_EPILOG = """\
What this does:
  Adds a source to cagelens config. It does not fetch remote sessions.

Examples:
  cagelens home add user@host
      Add an SSH remote source.

  cagelens fetch -r user@host --aw
      Fetch remote sessions after adding or before offline use.

  cagelens session list -r user@host --aw
      List remote sessions without fetching first.

  cagelens home add --wsl
      Add auto-detected WSL distributions.

  cagelens home add --wsl Ubuntu
      Add one WSL distribution.
"""


GEMINI_INDEX_EPILOG = """\
Examples:
  cagelens gemini-index
      List known Gemini hash-to-path mappings.

  cagelens gemini-index --add
      Add the current directory to the index.

  cagelens gemini-index --add ~/projects/myapp
      Add a specific project path.

  cagelens gemini-index --list --full-hash
      List mappings with full SHA-256 hashes.
"""


FETCH_EPILOG = """\
What this does:
  Fetch copies SSH remote session files into the local cagelens remote cache.
  It does not fetch local, WSL, Windows, or Claude web sessions.

Examples:
  cagelens fetch -r user@host --aw          Fetch all workspaces from one SSH host
  cagelens fetch -r user@host --glob "*auth*"       Fetch matching remote workspaces
  cagelens fetch --ah --aw                  Fetch all configured SSH remotes
  cagelens fetch --agent codex -r host --aw Fetch only Codex sessions

After fetching:
  cagelens session list -r user@host --glob "*auth*"
  cagelens session export -r user@host --glob "*auth*"
"""


RESET_EPILOG = """\
Targets:
  db       Clears cached metrics only. Raw agent session files are not changed.
  cache    Clears cagelens-managed fetch/cache files.
  config   Removes cagelens project/home settings.
  all      Resets db, cache, and config.

Examples:
  cagelens reset db -y
  cagelens reset cache -y
"""


INSTALL_EPILOG = """\
Default locations:
  CLI wrapper   ~/.local/bin/cagelens
  Claude Code   ~/.claude/skills/cagelens/
  Codex CLI     ${CODEX_HOME:-~/.codex}/skills/cagelens/
  Gemini CLI    ~/.gemini/skills/cagelens/
  Pi            ~/.pi/agent/skills/cagelens/

Examples:
  cagelens install                 Install CLI and all supported agent skills
  cagelens install --dry-run        Show exact paths without writing files
  cagelens install --agent codex    Install only the Codex skill package
  cagelens install --skip-cli       Install skill packages only
"""


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
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"Invalid number: {value}") from err


def _validate_markdown_level(value: str) -> int:
    """Validate --markdown-level argument."""
    try:
        level = int(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"Invalid markdown level: {value}") from err
    if level < 1 or level > MARKDOWN_MAX_LEVEL:
        raise argparse.ArgumentTypeError(
            f"--markdown-level must be between 1 and {MARKDOWN_MAX_LEVEL}"
        )
    return level


def _validate_positive_int(value: str) -> int:
    """Validate positive integer CLI arguments."""
    try:
        parsed = int(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"Invalid number: {value}") from err
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


class CLIParser:
    """Parse command line into structured CommandRequest.

    This class builds the argparse parser for cagelens and converts
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

    def parse(self, argv: list[str]) -> CommandRequest:
        """Parse command line arguments.

        Args:
            argv: Command line arguments (sys.argv[1:])

        Returns:
            CommandRequest with parsed command and options
        """
        # Preprocess argv to handle positional patterns that could conflict with subcommands
        argv = self._preprocess_argv(argv)
        args = self.parser.parse_args(argv)
        if getattr(args, "command", None) is None:
            self.parser.print_help()
            raise SystemExit(0)
        return self._build_request(args)

    def _preprocess_argv(self, argv: list[str]) -> list[str]:
        """Preprocess arguments to preserve default verbs with exact workspace args.

        Args:
            argv: Original command line arguments.

        Returns:
            Preprocessed arguments with default verbs inserted when needed.
        """
        if not argv:
            return argv

        result = list(argv)

        # Find the position of a command that supports positional pattern normalization
        # (may be after global flags like --agent).
        cmd_pos = None
        cmd_type = None
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg in (RESOURCE_WS, RESOURCE_SESSION, RESOURCE_STATS):
                cmd_pos = i
                cmd_type = arg
                break
            # Skip global flag values (e.g., --agent gemini)
            if arg.startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                # Check if this is a flag that takes a value
                if arg in GLOBAL_FLAGS_WITH_VALUES:
                    i += 2  # Skip flag and its value
                    continue
            if not arg.startswith("-"):
                return result
            i += 1

        if cmd_pos is None or cmd_type is None:
            return result

        if cmd_type == RESOURCE_STATS:
            return self._preprocess_stats_argv(argv, cmd_pos)

        subcommands = WS_SUBCOMMANDS if cmd_type == RESOURCE_WS else SESSION_SUBCOMMANDS

        # Case 1: Command followed directly by workspace (e.g., "session /repo" or "ws auth")
        # Convert: [cmd, workspace, ...] -> [cmd, list, workspace, ...]
        if cmd_pos + 1 < len(argv):
            next_arg = argv[cmd_pos + 1]
            if not next_arg.startswith("-") and next_arg not in subcommands:
                result = [
                    *list(argv[: cmd_pos + 1]),
                    DEFAULT_VERB_LIST,
                    next_arg,
                    *list(argv[cmd_pos + 2 :]),
                ]
                return result

        # Case 2: Command with explicit verb keeps following workspace args exact.
        if cmd_pos + 2 < len(argv):
            verb = argv[cmd_pos + 1]
            if verb in subcommands:
                if verb == "export":
                    return result
                if cmd_type == RESOURCE_SESSION and verb == "show":
                    return result

        return result

    def _preprocess_stats_argv(self, argv: list[str], cmd_pos: int) -> list[str]:
        """Normalize `stats [summary] [workspace]` around optional subcommands."""
        subcommands = {"summary", "rollup"}

        # Find the first non-flag argument after `stats`, skipping values for
        # flags like --by and --agent. If it is not a stats subcommand, treat
        # the command as `stats summary ...`.
        i = cmd_pos + 1
        explicit_verb_pos = None
        while i < len(argv):
            arg = argv[i]
            if arg.startswith("-"):
                if arg in FLAGS_WITH_VALUES:
                    i += 2
                else:
                    i += 1
                continue
            if arg in subcommands:
                explicit_verb_pos = i
            break

        if explicit_verb_pos is None:
            if any(arg in ("-h", "--help") for arg in argv[cmd_pos + 1 :]):
                return list(argv)
            prefix = [*list(argv[: cmd_pos + 1]), "summary"]
            return [*prefix, *list(argv[cmd_pos + 1 :])]

        verb = argv[explicit_verb_pos]
        prefix = [*list(argv[:cmd_pos]), RESOURCE_STATS, verb]
        suffix_start = explicit_verb_pos + 1
        if explicit_verb_pos > cmd_pos + 1:
            prefix.extend(argv[cmd_pos + 1 : explicit_verb_pos])
        return [*prefix, *list(argv[suffix_start:])]

    def _build_parser(self) -> argparse.ArgumentParser:
        """Build argument parser with all subcommands."""
        parser = argparse.ArgumentParser(
            prog="cagelens",
            description=(
                "Browse, export, and analyze AI coding assistant conversation history "
                "(Claude Code, Codex CLI, Gemini CLI, Pi)."
            ),
            formatter_class=WrappedHelpFormatter,
            epilog=TOP_LEVEL_EPILOG,
        )

        parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

        # Global agent selection flag (before subcommand)
        parser.add_argument(
            "--agent",
            choices=get_agent_choices(),
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
        self._add_stats_parser(subparsers)
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
            description="List, export, and analyze conversation sessions.",
            formatter_class=WrappedHelpFormatter,
            epilog=SESSION_EPILOG,
        )
        session_parser.set_defaults(command=RESOURCE_SESSION, session_verb=DEFAULT_VERB_LIST)
        # Add flags to session top-level so session --glob "*pattern*", session --ah work
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
        sess_list = sess_sub.add_parser(
            DEFAULT_VERB_LIST,
            help="List sessions",
            description="List session files from the resolved workspace scope.",
            formatter_class=WrappedHelpFormatter,
            epilog=SESSION_LIST_EPILOG,
        )
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
        sess_show = sess_sub.add_parser(
            "show",
            help="Show session details",
            description="Show details for one session by ID, filename, or path.",
            formatter_class=WrappedHelpFormatter,
            epilog=SESSION_SHOW_EPILOG,
        )
        sess_show.set_defaults(command=RESOURCE_SESSION, session_verb="show")
        sess_show.add_argument("session_id", help="Session identifier or path")
        self._add_home_scope_flags(sess_show)
        self._add_workspace_scope_flags(sess_show, positional_name="workspace")

        # session export
        sess_export = sess_sub.add_parser(
            "export",
            help="Export sessions to markdown",
            description="Export selected sessions to Markdown or NDJSON.",
            formatter_class=WrappedHelpFormatter,
            epilog=EXPORT_EPILOG,
        )
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
            formatter_class=WrappedHelpFormatter,
            epilog=WS_EPILOG,
        )
        ws_parser.set_defaults(command=RESOURCE_WS, ws_verb=DEFAULT_VERB_LIST)
        # Add flags to ws top-level so ws --local, ws --glob "*pattern*" work
        # Note: include_positional=False to avoid conflict with subcommand selection
        self._add_workspace_scope_flags(ws_parser, include_positional=False)
        self._add_home_scope_flags(ws_parser)
        self._add_agent_filter(ws_parser)
        ws_parser.add_argument(
            "--counts",
            action="store_true",
            help="Accepted for compatibility; workspace counts are always shown",
        )
        self._add_output_format(ws_parser)

        ws_sub = ws_parser.add_subparsers(dest="ws_verb")
        ws_sub.required = False
        ws_sub.default = DEFAULT_VERB_LIST

        # ws list
        ws_list = ws_sub.add_parser(
            DEFAULT_VERB_LIST,
            help="List workspaces",
            description="List workspace summaries from the selected homes.",
            formatter_class=WrappedHelpFormatter,
            epilog=WS_LIST_EPILOG,
        )
        ws_list.set_defaults(command=RESOURCE_WS, ws_verb=DEFAULT_VERB_LIST)
        self._add_workspace_scope_flags(ws_list)
        self._add_home_scope_flags(ws_list)
        self._add_agent_filter(ws_list)
        ws_list.add_argument(
            "--counts",
            action="store_true",
            help="Accepted for compatibility; workspace counts are always shown",
        )
        self._add_output_format(ws_list)

        # ws show
        ws_show = ws_sub.add_parser("show", help="Show workspace details")
        ws_show.set_defaults(command=RESOURCE_WS, ws_verb="show")
        ws_show.add_argument("workspace", nargs="*", help="Workspace path(s)")
        self._add_home_scope_flags(ws_show)
        self._add_agent_filter(ws_show)

        # ws export
        ws_export = ws_sub.add_parser(
            "export",
            help="Export sessions from workspace",
            description="Export sessions from selected workspaces.",
            formatter_class=WrappedHelpFormatter,
            epilog=EXPORT_EPILOG,
        )
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
            formatter_class=WrappedHelpFormatter,
            epilog=PROJECT_EPILOG,
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
        proj_add = proj_sub.add_parser(
            "add",
            help="Add workspace to project",
            description="Add exact or matched workspaces to a named project.",
            formatter_class=WrappedHelpFormatter,
            epilog=PROJECT_ADD_EPILOG,
        )
        proj_add.set_defaults(command=RESOURCE_PROJECT, project_command="add")
        proj_add.add_argument("name", help="Project name")
        self._add_workspace_scope_flags(
            proj_add, positional_name="workspaces", include_project=False
        )
        self._add_home_scope_flags(proj_add)
        proj_add.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview resolved workspaces without updating config",
        )
        proj_add.add_argument("--pick", action="store_true", help="Interactive picker")

        # project remove
        proj_remove = proj_sub.add_parser("remove", help="Remove workspace or project")
        proj_remove.set_defaults(command=RESOURCE_PROJECT, project_command="remove")
        proj_remove.add_argument("name", help="Project name")
        proj_remove.add_argument("workspace", nargs="?", help="Workspace to remove")
        proj_remove.add_argument("--wsl", action="store_true", help="Remove from WSL")
        proj_remove.add_argument("--windows", action="store_true", help="Remove from Windows")

        # project export
        proj_export = proj_sub.add_parser(
            "export",
            help="Export all sessions in project",
            description="Export all sessions in a named project.",
            formatter_class=WrappedHelpFormatter,
            epilog=EXPORT_EPILOG,
        )
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
        self._add_agent_filter(proj_export)

        # project stats
        proj_stats = proj_sub.add_parser("stats", help="Stats for project")
        proj_stats.set_defaults(command=RESOURCE_PROJECT, project_command="stats")
        proj_stats.add_argument("name", help="Project name")
        self._add_stats_options(proj_stats)
        self._add_home_scope_flags(proj_stats)
        self._add_agent_filter(proj_stats)

    # =========================================================================
    # Home subparser
    # =========================================================================

    def _add_home_parser(self, subparsers) -> None:
        """Add home subparser."""
        home_parser = subparsers.add_parser(
            RESOURCE_HOME,
            help="Manage homes",
            description="Manage data sources (local, WSL, Windows, web, SSH remotes).",
            formatter_class=WrappedHelpFormatter,
            epilog=HOME_EPILOG,
        )
        home_parser.set_defaults(command=RESOURCE_HOME, home_verb=DEFAULT_VERB_LIST)
        # Add flags to home top-level so home --local, home --wsl work
        home_parser.add_argument(
            "--wsl",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Show WSL distributions only",
        )
        home_parser.add_argument(
            "--windows",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Show Windows users only",
        )
        home_parser.add_argument(
            "--web",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Show Claude.ai status only",
        )
        home_parser.add_argument(
            "--local",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Show local home only",
        )
        home_parser.add_argument(
            "--remotes",
            action="store_true",
            dest="show_remotes",
            default=argparse.SUPPRESS,
            help="Show SSH remotes only",
        )
        self._add_output_format(home_parser)

        home_sub = home_parser.add_subparsers(dest="home_verb")
        home_sub.required = False
        home_sub.default = DEFAULT_VERB_LIST

        # home list
        home_list = home_sub.add_parser(DEFAULT_VERB_LIST, help="List homes")
        home_list.set_defaults(command=RESOURCE_HOME, home_verb=DEFAULT_VERB_LIST)
        home_list.add_argument(
            "--wsl",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Show WSL distributions only",
        )
        home_list.add_argument(
            "--windows",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Show Windows users only",
        )
        home_list.add_argument(
            "--web",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Show Claude.ai status only",
        )
        home_list.add_argument(
            "--local",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Show local home only",
        )
        home_list.add_argument(
            "--remotes",
            action="store_true",
            dest="show_remotes",
            default=argparse.SUPPRESS,
            help="Show SSH remotes only",
        )
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
        home_add = home_sub.add_parser(
            "add",
            help="Add a home",
            description="Add a local-adjacent, web, or SSH remote source to cagelens config.",
            formatter_class=WrappedHelpFormatter,
            epilog=HOME_ADD_EPILOG,
        )
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
        home_export = home_sub.add_parser(
            "export",
            help="Export all sessions from home(s)",
            description="Export sessions from selected homes.",
            formatter_class=WrappedHelpFormatter,
            epilog=EXPORT_EPILOG,
        )
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
    # Top-level stats parser
    # =========================================================================

    def _add_stats_parser(self, subparsers) -> None:
        """Add top-level stats parser."""
        stats_parser = subparsers.add_parser(
            RESOURCE_STATS,
            help="Usage statistics and rollups",
            description="Analyze cached usage metrics across sessions, workspaces, homes, and projects.",
            formatter_class=WrappedHelpFormatter,
            epilog=STATS_EPILOG,
        )
        stats_parser.set_defaults(command=RESOURCE_STATS, stats_verb="summary")
        self._add_workspace_scope_flags(stats_parser, include_positional=False)
        self._add_stats_options(stats_parser)
        self._add_home_scope_flags(stats_parser)
        self._add_agent_filter(stats_parser)

        stats_sub = stats_parser.add_subparsers(dest="stats_verb")
        stats_sub.required = False
        stats_sub.default = "summary"

        summary = stats_sub.add_parser(
            "summary",
            help="Show cached stats dashboard",
            description="Show a cached stats dashboard for the selected scope.",
            formatter_class=WrappedHelpFormatter,
            epilog=STATS_SUMMARY_EPILOG,
        )
        summary.set_defaults(command=RESOURCE_STATS, stats_verb="summary")
        self._add_workspace_scope_flags(summary)
        self._add_stats_options(summary)
        self._add_home_scope_flags(summary)
        self._add_agent_filter(summary)

        rollup = stats_sub.add_parser(
            "rollup",
            help="Show tabular stats rollups",
            description="Show tabular cached stats grouped by dimensions such as month or project.",
            formatter_class=WrappedHelpFormatter,
            epilog=STATS_ROLLUP_EPILOG,
        )
        rollup.set_defaults(command=RESOURCE_STATS, stats_verb="rollup")
        self._add_workspace_scope_flags(rollup)
        self._add_stats_options(rollup, rollup=True)
        self._add_home_scope_flags(rollup)
        self._add_agent_filter(rollup)

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
                "so cagelens can display readable workspace paths instead of hashes."
            ),
            formatter_class=WrappedHelpFormatter,
            epilog=GEMINI_INDEX_EPILOG,
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
        self._add_output_format(gi_parser)

    def _add_install_parser(self, subparsers) -> None:
        """Add install subparser."""
        install_parser = subparsers.add_parser(
            RESOURCE_INSTALL,
            help="Install CLI and agent skill packages",
            description="Install the CLI wrapper and agent skill packages.",
            formatter_class=WrappedHelpFormatter,
            epilog=INSTALL_EPILOG,
        )
        install_parser.set_defaults(command=RESOURCE_INSTALL, install_verb=DEFAULT_VERB_RUN)
        install_parser.add_argument("--bin-dir", help="Custom binary install directory")
        install_parser.add_argument("--skill-dir", help="Custom agent skill install directory")
        install_parser.add_argument(
            "--dry-run", action="store_true", help="Show install plan without writing files"
        )
        install_parser.add_argument("--skip-cli", action="store_true", help="Skip CLI install")
        install_parser.add_argument(
            "--skip-skill", action="store_true", help="Skip agent skill install"
        )
        install_parser.add_argument(
            "--skip-settings", action="store_true", help="Skip agent settings update"
        )
        install_parser.add_argument(
            "--agent",
            choices=get_agent_choices(),
            default=DEFAULT_AGENT,
            help="Agent skill target to install (default: all supported agents)",
        )

    def _add_reset_parser(self, subparsers) -> None:
        """Add reset subparser."""
        reset_parser = subparsers.add_parser(
            RESOURCE_RESET,
            help="Reset stored data",
            description="Reset cagelens-managed metrics, config, or caches.",
            formatter_class=WrappedHelpFormatter,
            epilog=RESET_EPILOG,
        )
        reset_parser.set_defaults(command=RESOURCE_RESET, reset_verb=DEFAULT_VERB_RUN)
        reset_parser.add_argument(
            "target",
            nargs="?",
            choices=["all", "db", "config", "cache"],
            default="all",
            help="Reset target (default: all)",
        )
        reset_parser.add_argument("-y", "--yes", action="store_true", help="Confirm reset")

    def _add_fetch_parser(self, subparsers) -> None:
        """Add fetch subparser."""
        fetch_parser = subparsers.add_parser(
            RESOURCE_FETCH,
            help="Fetch remote sessions into cache",
            description="Fetch SSH remote sessions into the local cagelens cache.",
            formatter_class=WrappedHelpFormatter,
            epilog=FETCH_EPILOG,
        )
        fetch_parser.set_defaults(command=RESOURCE_FETCH, fetch_verb=DEFAULT_VERB_RUN)
        self._add_workspace_scope_flags(fetch_parser)
        fetch_parser.add_argument(
            "--home",
            action="append",
            dest="homes",
            metavar="NAME",
            default=argparse.SUPPRESS,
            help="Specific saved remote home (repeatable)",
        )
        fetch_parser.add_argument(
            "--ah",
            "--all-homes",
            "--all-remotes",
            dest="all_homes",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Include all configured SSH remotes",
        )
        fetch_parser.add_argument(
            "-r",
            "--remote",
            action="append",
            dest="remotes",
            metavar="HOST",
            default=argparse.SUPPRESS,
            help="SSH remote (user@host) - repeatable",
        )
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
            default=argparse.SUPPRESS,
            help="Specific saved home (repeatable)",
        )
        parser.add_argument(
            "--ah",
            "--all-homes",
            dest="all_homes",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Include all configured homes",
        )
        parser.add_argument(
            "--wsl", action="store_true", default=argparse.SUPPRESS, help="Use WSL home"
        )
        parser.add_argument(
            "--windows", action="store_true", default=argparse.SUPPRESS, help="Use Windows home"
        )
        parser.add_argument(
            "--web",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Include Claude.ai web sessions",
        )
        parser.add_argument(
            "-r",
            "--remote",
            action="append",
            dest="remotes",
            metavar="HOST",
            default=argparse.SUPPRESS,
            help="SSH remote (user@host) - repeatable",
        )
        parser.add_argument(
            "--no-wsl",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Exclude WSL sources (with --ah)",
        )
        parser.add_argument(
            "--no-windows",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Exclude Windows sources (with --ah)",
        )
        parser.add_argument(
            "--no-remote",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Exclude SSH remotes (with --ah)",
        )
        parser.add_argument(
            "--no-web",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Exclude web sessions (with --ah)",
        )
        parser.add_argument(
            "--local",
            action="store_true",
            default=argparse.SUPPRESS,
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
            parser.add_argument(positional_name, nargs="*", help="Exact workspace path/id(s)")
        parser.add_argument(
            "--glob",
            dest="glob_patterns",
            action="append",
            default=argparse.SUPPRESS,
            metavar="PATTERN",
            help="Shell-style workspace glob; quote patterns in your shell (repeatable)",
        )
        parser.add_argument(
            "--regex",
            dest="regex_patterns",
            action="append",
            default=argparse.SUPPRESS,
            metavar="REGEX",
            help="Regular-expression workspace match (repeatable)",
        )
        parser.add_argument(
            "--aw",
            "--all-workspaces",
            dest="all_workspaces",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Use all workspaces in scope",
        )
        parser.add_argument(
            "--this",
            dest="this_only",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Current workspace only (skip project auto-detection)",
        )
        if include_project:
            parser.add_argument(
                "--project",
                action="append",
                dest="projects",
                metavar="NAME",
                default=argparse.SUPPRESS,
                help="Project name (repeatable)",
            )

    def _add_date_filters(self, parser) -> None:
        """Add since/until date filters."""
        parser.add_argument(
            "--since",
            metavar="DATE",
            default=argparse.SUPPRESS,
            help="Only include sessions on/after this date (YYYY-MM-DD)",
        )
        parser.add_argument(
            "--until",
            metavar="DATE",
            default=argparse.SUPPRESS,
            help="Only include sessions on/before this date (YYYY-MM-DD)",
        )

    def _add_agent_filter(self, parser) -> None:
        """Add --agent filter flag to subparser."""
        parser.add_argument(
            "--agent",
            choices=get_agent_choices(),
            default=argparse.SUPPRESS,
            help="Agent backend to use (default: auto-detect)",
        )

    def _add_output_format(self, parser) -> None:
        """Add --format and --width for table output control."""
        parser.add_argument(
            "--format",
            choices=OUTPUT_FORMAT_CHOICES,
            default=argparse.SUPPRESS,
            help="Output format (default: table for TTY, tsv for pipes)",
        )
        parser.add_argument(
            "-w",
            "--width",
            type=int,
            default=argparse.SUPPRESS,
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
            "--format",
            choices=EXPORT_FORMAT_CHOICES,
            default=EXPORT_FORMAT_MARKDOWN,
            dest="export_format",
            help="Export format: markdown or html (default: markdown)",
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
            "--markdown-level",
            type=_validate_markdown_level,
            default=MARKDOWN_DEFAULT_LEVEL,
            help=(
                f"Markdown detail level 1-{MARKDOWN_MAX_LEVEL} "
                f"(default: {MARKDOWN_DEFAULT_LEVEL}, full output)"
            ),
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
            help="Use flat directory structure (alias for --layout flat)",
        )
        parser.add_argument(
            "--layout",
            choices=EXPORT_LAYOUT_CHOICES,
            default=EXPORT_LAYOUT_DEFAULT,
            help=("Export directory layout: tree, squashed, or flat (default: squashed)"),
        )
        parser.add_argument(
            "--source",
            action="store_true",
            dest="include_source",
            help="Include raw source file alongside markdown export",
        )
        self._add_date_filters(parser)

    def _add_stats_options(self, parser, rollup: bool = False) -> None:
        """Add stats options."""
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Refresh source files before showing stats (slower)",
        )
        parser.add_argument(
            "--no-sync",
            action="store_true",
            dest="no_sync",
            help="Use cached metrics without refresh (default)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="With --sync, reprocess unchanged source files too",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress sync progress and informational output",
        )
        parser.add_argument(
            "--by",
            metavar="DIMS",
            help=(
                "Group by dimensions (comma-separated): home, agent, workspace/ws, day, "
                "model, tool" + (", project/proj, month" if rollup else "")
            ),
        )
        if rollup:
            parser.add_argument(
                "--metric",
                choices=["time", "tokens", "all"],
                default="all",
                help="Rollup metric family (default: all)",
            )
            parser.add_argument(
                "--top",
                type=_validate_positive_int,
                default=None,
                help="Limit rollup rows",
            )
            parser.add_argument(
                "--sort",
                metavar="FIELDS",
                help=(
                    "Sort rollup rows by comma-separated fields: metric, tokens, time, "
                    "sessions, messages, input, output, cache-read, or dimensions"
                ),
            )
            sort_direction = parser.add_mutually_exclusive_group()
            sort_direction.add_argument(
                "--asc",
                action="store_const",
                const="asc",
                dest="sort_direction",
                help="Sort rollup rows ascending",
            )
            sort_direction.add_argument(
                "--desc",
                action="store_const",
                const="desc",
                dest="sort_direction",
                help="Sort rollup rows descending",
            )
            parser.add_argument(
                "-c",
                "--total",
                "--totals",
                action="store_true",
                default=True,
                help="Append a totals row to rollup output",
            )
            parser.add_argument(
                "--no-total",
                "--no-totals",
                action="store_false",
                dest="total",
                help="Suppress the default totals row",
            )
            parser.add_argument(
                "--separator",
                action="store_true",
                help="Print a record-separator line before the rollup table",
            )
        parser.add_argument(
            "--models",
            action="store_true",
            help="Show model usage (alias for --by model)",
        )
        parser.add_argument(
            "--tools",
            action="store_true",
            help="Show tool usage (alias for --by tool)",
        )
        parser.add_argument(
            "--by-day",
            action="store_true",
            dest="by_day",
            help="Show daily usage (alias for --by day)",
        )
        parser.add_argument(
            "--by-workspace",
            action="store_true",
            dest="by_workspace",
            help="Show workspace usage (alias for --by workspace)",
        )
        self._add_output_format(parser)
        if rollup:
            parser.add_argument(
                "-H",
                "--human",
                action="store_true",
                default=True,
                help="Human-readable numbers (K/M/B) and time (default for rollups)",
            )
            parser.add_argument(
                "--raw",
                "--no-human",
                action="store_false",
                dest="human",
                help="Use raw numeric values instead of compact K/M/B numbers",
            )
        else:
            parser.add_argument(
                "-H",
                "--human",
                action="store_true",
                help="Human-readable numbers (K/M/B) and time (total hours, minutes, seconds)",
            )
        parser.add_argument(
            "--time",
            action="store_true",
            help=(
                "Not needed for rollups; use --metric time with --by day/month/project/workspace"
                if rollup
                else (
                    "Expand summary time details, including daily totals; "
                    "use `stats rollup --metric time --by month` for monthly totals"
                )
            ),
        )
        parser.add_argument(
            "--top-ws",
            type=self._parse_top_ws,
            default=None,
            metavar="N|all",
            help="Limit workspace rows shown, or use 'all' to show every workspace",
        )
        self._add_date_filters(parser)

    def _parse_top_ws(self, value: str) -> int | str:
        """Parse --top-ws as a positive integer or 'all'."""
        if value.lower() == "all":
            return "all"
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "--top-ws must be a positive integer or 'all'"
            ) from exc
        if parsed <= 0:
            raise argparse.ArgumentTypeError("--top-ws must be greater than zero")
        return parsed

    # =========================================================================
    # Build CommandRequest from parsed args
    # =========================================================================

    def _build_request(self, args: argparse.Namespace) -> CommandRequest:
        """Convert parsed args to CommandRequest."""
        if getattr(args, "command", None) is None:
            raise ValueError("Command is required")
        self._normalize_export_args(args)

        # Determine resource and verb
        resource, verb = self._get_resource_verb(args)

        # Build scope args
        scope_args = self._build_scope_args(args, resource, verb)

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

    def _split_csv_list(self, values: list[str]) -> list[str]:
        """Split comma-separated CLI values into a flat list."""
        result: list[str] = []
        for item in values:
            for part in str(item).split(","):
                stripped = part.strip()
                if stripped:
                    result.append(stripped)
        return result

    def _normalize_export_args(self, args: argparse.Namespace) -> None:
        """Normalize export args when positional output_dir is consumed by nargs='*'."""
        command = getattr(args, "command", None)

        if command == RESOURCE_SESSION and getattr(args, "session_verb", None) == "export":
            if getattr(args, "output_override", None):
                return
            targets = list(getattr(args, "target", None) or [])
            if (
                getattr(args, "output_dir", DEFAULT_OUTPUT_DIR) == DEFAULT_OUTPUT_DIR
                and len(targets) > 1
            ):
                args.output_dir = targets[-1]
                args.target = targets[:-1]

        if command == RESOURCE_WS and getattr(args, "ws_verb", None) == "export":
            if getattr(args, "output_override", None):
                return
            targets = list(getattr(args, "target", None) or [])
            if (
                getattr(args, "output_dir", DEFAULT_OUTPUT_DIR) == DEFAULT_OUTPUT_DIR
                and len(targets) > 1
            ):
                args.output_dir = targets[-1]
                args.target = targets[:-1]

        if command == RESOURCE_HOME and getattr(args, "home_verb", None) == "export":
            if getattr(args, "output_override", None):
                return
            names = list(getattr(args, "names", None) or [])
            if (
                getattr(args, "output_dir", DEFAULT_OUTPUT_DIR) == DEFAULT_OUTPUT_DIR
                and len(names) > 1
            ):
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
        elif command == RESOURCE_STATS:
            return (RESOURCE_STATS, getattr(args, "stats_verb", "summary"))
        elif command == RESOURCE_GEMINI_INDEX:
            return (RESOURCE_GEMINI_INDEX, DEFAULT_VERB_INDEX)
        elif command == RESOURCE_INSTALL:
            return (RESOURCE_INSTALL, DEFAULT_VERB_RUN)
        elif command == RESOURCE_RESET:
            return (RESOURCE_RESET, DEFAULT_VERB_RUN)
        elif command == RESOURCE_FETCH:
            return (RESOURCE_FETCH, DEFAULT_VERB_RUN)
        else:
            raise ValueError(f"Unknown command: {command}")

    def _home_scope_values(
        self, args: argparse.Namespace
    ) -> tuple[bool, str | None, Any, list[str]]:
        """Return home-selection values from parsed args."""
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

        return all_homes, home_type, home_value, home_names

    def _project_scope_values(self, args: argparse.Namespace) -> list[str]:
        """Return project names implied by command flags and project verbs."""
        projects = list(getattr(args, "projects", None) or [])
        if getattr(args, "command", None) == RESOURCE_PROJECT:
            project_name = getattr(args, "name", None)
            project_command = getattr(args, "project_command", None)
            if project_command in ("show", "export", "stats") and project_name:
                projects = [project_name]
        return projects

    def _workspace_scope_patterns(
        self, args: argparse.Namespace
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        """Return exact, glob, regex, and legacy name workspace patterns."""
        patterns = []
        for attr in ["workspace", "target", "workspaces"]:
            value = getattr(args, attr, None)
            if value:
                patterns.extend(value)
        return (
            patterns,
            list(getattr(args, "glob_patterns", None) or []),
            list(getattr(args, "regex_patterns", None) or []),
            list(getattr(args, "name_patterns", None) or []),
        )

    def _session_export_implies_all_workspaces(
        self,
        args: argparse.Namespace,
        *,
        projects: list[str],
        patterns: list[str],
        glob_patterns: list[str],
        regex_patterns: list[str],
        name_patterns: list[str],
        all_workspaces: bool,
        this_only: bool,
    ) -> bool:
        """Return whether session-id export should search all workspaces."""
        session_ids = self._split_csv_list(list(getattr(args, "session_ids", None) or []))
        has_scope = (
            patterns
            or glob_patterns
            or regex_patterns
            or name_patterns
            or projects
            or all_workspaces
            or this_only
        )
        return (
            getattr(args, "command", None) == RESOURCE_SESSION
            and getattr(args, "session_verb", None) == "export"
            and bool(session_ids)
            and not has_scope
        )

    def _build_scope_args(self, args: argparse.Namespace, resource: str, verb: str) -> ScopeArgs:
        """Build ScopeArgs from parsed arguments."""
        all_homes, home_type, home_value, home_names = self._home_scope_values(args)
        all_workspaces = getattr(args, "all_workspaces", False)
        projects = self._project_scope_values(args)
        patterns, glob_patterns, regex_patterns, name_patterns = self._workspace_scope_patterns(
            args
        )

        this_only = getattr(args, "this_only", False)
        if self._session_export_implies_all_workspaces(
            args,
            projects=projects,
            patterns=patterns,
            glob_patterns=glob_patterns,
            regex_patterns=regex_patterns,
            name_patterns=name_patterns,
            all_workspaces=all_workspaces,
            this_only=this_only,
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
            resource=resource,
            verb=verb,
            all_homes=all_homes,
            home_type=home_type,
            home_value=home_value,
            home_names=home_names,
            all_workspaces=all_workspaces,
            projects=projects,
            patterns=patterns,
            glob_patterns=glob_patterns,
            regex_patterns=regex_patterns,
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
    ) -> dict[str, Any]:
        """Build verb-specific arguments."""
        if verb == "export":
            verb_args = self._build_export_verb_args(args, resource)
        elif verb == "stats" or resource == RESOURCE_STATS:
            verb_args = self._build_stats_verb_args(args)
        elif verb == "list":
            verb_args = self._build_list_verb_args(args, resource)
        elif verb == "show":
            verb_args = self._build_show_verb_args(args, resource)
        else:
            verb_args = {}

        # Project management args
        if resource == RESOURCE_PROJECT:
            verb_args["name"] = getattr(args, "name", None)
            if verb == "add":
                verb_args["workspaces"] = getattr(args, "workspaces", [])
                verb_args["pick"] = getattr(args, "pick", False)
                verb_args["dry_run"] = getattr(args, "dry_run", False)
            elif verb == "remove":
                verb_args["workspace"] = getattr(args, "workspace", None)
                verb_args["wsl"] = getattr(args, "wsl", False)
                verb_args["windows"] = getattr(args, "windows", False)

        # Home management args
        if resource == RESOURCE_HOME and verb in ("add", "remove"):
            verb_args["source"] = getattr(args, "source", None)
            verb_args["windows"] = getattr(args, "windows", False)
            verb_args["wsl"] = getattr(args, "wsl", None)
            verb_args["web"] = getattr(args, "web", False)

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
            verb_args["dry_run"] = getattr(args, "dry_run", False)
            agent = getattr(args, "agent", None)
            verb_args["agent"] = None if agent == DEFAULT_AGENT else agent

        if resource == RESOURCE_RESET:
            target = getattr(args, "target", "all")
            verb_args["reset_target"] = target
            verb_args["reset_db"] = target in ("all", "db")
            verb_args["reset_config"] = target in ("all", "config")
            verb_args["reset_cache"] = target in ("all", "cache")
            verb_args["yes"] = getattr(args, "yes", False)

        if resource == RESOURCE_FETCH:
            verb_args["fetch"] = True

        return verb_args

    def _build_export_verb_args(self, args: argparse.Namespace, resource: str) -> dict[str, Any]:
        """Build export-specific arguments."""
        layout = getattr(args, "layout", EXPORT_LAYOUT_DEFAULT)
        flat = getattr(args, "flat", False)
        if flat:
            layout = "flat"
        verb_args = {
            "output_dir": (
                getattr(args, "output_override", None)
                or getattr(args, "output_dir", None)
                or DEFAULT_OUTPUT_DIR
            ),
            "export_format": getattr(args, "export_format", EXPORT_FORMAT_MARKDOWN),
            "force": getattr(args, "force", False),
            "export_json": getattr(args, "export_json", False),
            "minimal": getattr(args, "minimal", False),
            "markdown_level": getattr(args, "markdown_level", MARKDOWN_DEFAULT_LEVEL),
            "split": getattr(args, "split", None),
            "jobs": getattr(args, "jobs", None),
            "flat": flat,
            "layout": layout,
            "include_source": getattr(args, "include_source", False),
        }
        if resource == RESOURCE_SESSION:
            raw_ids = list(getattr(args, "session_ids", None) or [])
            verb_args["session_ids"] = self._split_csv_list(raw_ids)
            verb_args["targets"] = list(getattr(args, "target", None) or [])
        return verb_args

    def _build_stats_verb_args(self, args: argparse.Namespace) -> dict[str, Any]:
        """Build stats-specific arguments."""
        raw_by = getattr(args, "by", None)
        group_by = self._normalize_stats_dimensions(
            self._split_csv_list([raw_by]) if raw_by else []
        )
        alias_groups = [
            ("models", "model"),
            ("tools", "tool"),
            ("by_day", "day"),
            ("by_workspace", "workspace"),
        ]
        for attr, group in alias_groups:
            if getattr(args, attr, False) and group not in group_by:
                group_by.append(group)
        return {
            "sync": getattr(args, "sync", False),
            "no_sync": getattr(args, "no_sync", False),
            "force": getattr(args, "force", False),
            "by": group_by or None,
            "time": getattr(args, "time", False),
            "top_ws": getattr(args, "top_ws", None),
            "human": getattr(args, "human", False),
            "metric": getattr(args, "metric", None),
            "top": getattr(args, "top", None),
            "sort": self._split_csv_list([getattr(args, "sort", None)])
            if getattr(args, "sort", None)
            else None,
            "sort_direction": getattr(args, "sort_direction", None) or "default",
            "total": getattr(args, "total", False),
            "separator": getattr(args, "separator", False),
            "stats_mode": getattr(args, "stats_verb", "summary"),
        }

    def _normalize_stats_dimensions(self, dimensions: list[str]) -> list[str]:
        """Normalize user-facing stats dimension aliases to canonical names."""
        normalized: list[str] = []
        for dimension in dimensions:
            canonical = STATS_DIMENSION_ALIASES.get(dimension, dimension)
            if canonical not in normalized:
                normalized.append(canonical)
        return normalized

    def _build_list_verb_args(self, args: argparse.Namespace, resource: str) -> dict[str, Any]:
        """Build list-specific arguments."""
        verb_args = {"counts": getattr(args, "counts", False)}
        if resource == RESOURCE_HOME:
            for flag in ("local", "wsl", "windows", "web"):
                verb_args[flag] = getattr(args, flag, False)
            verb_args["remotes"] = getattr(args, "show_remotes", False)
        return verb_args

    def _build_show_verb_args(self, args: argparse.Namespace, resource: str) -> dict[str, Any]:
        """Build show-specific arguments."""
        verb_args = {"session_id": getattr(args, "session_id", None)}
        if resource in (RESOURCE_PROJECT, RESOURCE_HOME):
            verb_args["name"] = getattr(args, "name", None)
        return verb_args
