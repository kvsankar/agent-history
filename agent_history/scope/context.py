"""Context and request types for scope resolution architecture.

This module defines the environment context and command request types used
throughout the scope resolution pipeline. The ResolutionContext captures
the runtime environment state needed for resolution, while CommandRequest
and its related types represent parsed command line inputs.

See docs/design-v2/scope-resolution-v2.md for the complete specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from agent_history.scope.types import ConcreteScope


@dataclass
class ResolutionContext:
    """Environment state needed for scope resolution.

    This dataclass captures all the context information required to resolve
    scope specifications to concrete values. It includes platform detection,
    current working directory analysis, available resources, and configuration.

    The context is built once by ContextBuilder at the start of command
    execution and passed through the resolution pipeline.

    Attributes:
        platform: Operating system identifier ("linux", "wsl", "windows", "darwin").
        is_wsl: Whether the code is running inside WSL (Windows Subsystem for Linux).
        cwd: Current working directory as an absolute Path.
        cwd_home: Home identifier if CWD is within a workspace (e.g., "local", "wsl:Ubuntu").
        cwd_workspace: Workspace path if CWD is within a recognized workspace.
        cwd_project: Project name if CWD is within a project's workspace.
        available_homes: Mapping of home categories to available items.
            Example: {"wsl": ["Ubuntu", "Debian"], "windows": ["alice"], "remote": ["dev"]}
        project_config: Mapping of project names to their definitions.
            Each definition maps home identifiers to lists of workspace paths.
        claude_projects_dir: Path to Claude's projects directory for session scanning.
        codex_sessions_dir: Path to Codex's sessions directory for session scanning.
        gemini_sessions_dir: Path to Gemini's sessions directory for session scanning.
    """

    # Platform
    platform: str = ""
    is_wsl: bool = False

    # Current location
    cwd: Path = field(default_factory=Path.cwd)
    cwd_home: Optional[str] = None
    cwd_workspace: Optional[str] = None
    cwd_project: Optional[str] = None

    # Available resources
    available_homes: Dict[str, List[str]] = field(default_factory=dict)

    # Configuration
    project_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Agent paths (for session scanning)
    claude_projects_dir: Optional[Path] = None
    codex_sessions_dir: Optional[Path] = None
    gemini_sessions_dir: Optional[Path] = None


@dataclass
class ScopeArgs:
    """Scope-related arguments extracted from the command line.

    This dataclass groups all arguments that affect scope resolution,
    including home selection, workspace selection, session filters,
    and exclusion flags.

    Attributes:
        all_homes: If True, search across all available homes (--ah flag).
        home_type: Home category filter ("wsl", "windows", "remote").
        home_value: Specific home within a category (e.g., "Ubuntu" for --wsl=Ubuntu).
        home_names: List of explicit home names from --home flags.
        all_workspaces: If True, search all workspaces in selected homes (--aw flag).
        project: Project name for project-scoped operations (--project flag).
        patterns: Workspace patterns from positional arguments.
        this_only: If True, restrict to current workspace only (--this flag).
        agent: Agent filter ("claude", "codex", "gemini", or None for all).
        since: Start date filter for sessions (date string).
        until: End date filter for sessions (date string).
        no_wsl: Exclude WSL homes when using --ah.
        no_windows: Exclude Windows homes when using --ah.
        no_remote: Exclude remote homes when using --ah.
        no_web: Exclude web sessions when using --ah.
    """

    # Home selection
    all_homes: bool = False
    home_type: Optional[str] = None
    home_value: Optional[str] = None
    home_names: List[str] = field(default_factory=list)

    # Workspace selection
    all_workspaces: bool = False
    project: Optional[str] = None
    patterns: List[str] = field(default_factory=list)  # Positional patterns (exact match)
    name_patterns: List[str] = field(default_factory=list)  # -n patterns (substring match)
    this_only: bool = False

    # Session filters
    agent: Optional[str] = None
    since: Optional[str] = None
    until: Optional[str] = None

    # Exclusions (with --ah)
    no_wsl: bool = False
    no_windows: bool = False
    no_remote: bool = False
    no_web: bool = False


@dataclass
class OutputArgs:
    """Output formatting arguments from the command line.

    This dataclass groups arguments that control how command output
    is formatted and where it is written.

    Attributes:
        format: Output format ("table", "json", "tsv", or None for default).
        output_path: File path for output (None for stdout).
        quiet: If True, suppress non-essential output.
        human_readable: If True, format sizes and dates for human reading.
        width: Maximum table width in columns (None for no limit).
    """

    format: Optional[str] = None
    output_path: Optional[Path] = None
    quiet: bool = False
    human_readable: bool = False
    width: Optional[int] = None


@dataclass
class CommandRequest:
    """Parsed command line request.

    This dataclass represents a fully parsed command line, ready for
    processing by the scope resolver and verb dispatcher.

    Attributes:
        resource: The resource type being operated on ("session", "project", "ws", "home").
        verb: The action to perform ("list", "export", "stats", "show").
        scope_args: Scope-related arguments for resolution.
        output_args: Output formatting arguments.
        verb_args: Additional verb-specific arguments as a dictionary.
    """

    resource: str
    verb: str
    scope_args: ScopeArgs
    output_args: OutputArgs
    verb_args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolutionError:
    """Structured error information from scope resolution.

    This dataclass captures detailed information about errors that occur
    during scope resolution, including the stage where the error occurred,
    the specification that caused it, and possible corrections.

    Attributes:
        stage: Resolution stage where error occurred ("project", "home", "workspace", "session").
        spec: The specification object that failed to resolve.
        reason: Human-readable description of why resolution failed.
        suggestions: List of possible corrections or alternatives.
    """

    stage: str
    spec: Any
    reason: str
    suggestions: List[str] = field(default_factory=list)


@dataclass
class ResolutionResult:
    """Result of scope resolution.

    This dataclass holds the outcome of the scope resolution pipeline,
    including the resolved concrete scope, any errors encountered, and
    warnings that don't prevent execution.

    Attributes:
        scope: The resolved ConcreteScope (may be partial if errors occurred).
        errors: List of ResolutionError objects for failed resolutions.
        warnings: List of warning messages (non-fatal issues).
    """

    scope: ConcreteScope
    errors: List[ResolutionError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Return True if resolution completed without errors."""
        return len(self.errors) == 0

    @property
    def partial(self) -> bool:
        """Return True if resolution had errors but still produced results.

        A partial result indicates that some specifications failed to resolve
        but others succeeded, allowing the command to proceed with reduced scope.
        """
        return len(self.errors) > 0 and len(self.scope) > 0


# =============================================================================
# Context Builder
# =============================================================================


class ContextBuilder:
    """Build resolution context from environment.

    This class detects the runtime environment and builds a ResolutionContext
    that captures all information needed for scope resolution. It performs
    platform detection, workspace/project discovery, home enumeration, and
    configuration loading.

    The context is built once at the start of command execution and passed
    through the resolution pipeline.

    Example:
        builder = ContextBuilder()
        context = builder.build()
        # context now contains platform info, CWD analysis, available homes, etc.
    """

    def build(self) -> ResolutionContext:
        """Build context by detecting environment.

        Returns:
            ResolutionContext with platform info, CWD detection,
            available homes, and configuration loaded.
        """

        from agent_history.storage.config import load_config
        from agent_history.utils.platform import is_running_in_wsl

        ctx = ResolutionContext()

        # Platform detection
        ctx.platform = self._detect_platform()
        ctx.is_wsl = is_running_in_wsl()

        # Current location
        ctx.cwd = Path.cwd()
        ctx.cwd_home, ctx.cwd_workspace = self._detect_cwd_workspace()
        ctx.cwd_project = self._detect_cwd_project(ctx.cwd_workspace, ctx.cwd_home)

        # Available resources
        ctx.available_homes = self._enumerate_available_homes()

        # Configuration
        config = load_config()
        ctx.project_config = config.get("projects", {})

        # Agent paths (for session scanning)
        claude_dir, codex_dir, gemini_dir = self._get_agent_paths()
        ctx.claude_projects_dir = claude_dir
        ctx.codex_sessions_dir = codex_dir
        ctx.gemini_sessions_dir = gemini_dir

        return ctx

    def _detect_platform(self) -> str:
        """Detect current platform: 'linux', 'wsl', 'windows', 'darwin'.

        Returns:
            Platform identifier string.
        """
        import sys

        from agent_history.utils.platform import is_running_in_wsl

        if sys.platform == "win32":
            return "windows"
        elif is_running_in_wsl():
            return "wsl"
        elif sys.platform == "darwin":
            return "darwin"
        else:
            return "linux"

    def _detect_cwd_workspace(self) -> tuple[Optional[str], Optional[str]]:
        """Detect if CWD is within a workspace.

        Checks multiple sources:
        1. If CWD is under Claude projects (~/.claude/projects/)
        2. If CWD matches a workspace path in project configuration
        3. If AGENT_HISTORY_HOME is set, check if CWD relative to it matches a workspace

        Returns:
            Tuple of (home, workspace) where home is "local" and workspace
            is the decoded workspace path, or (None, None) if not in a workspace.
        """
        import os
        import urllib.parse

        cwd = Path.cwd()
        cwd_str = str(cwd)

        # Get Claude projects directory
        claude_projects = Path.home() / ".claude" / "projects"
        env_override = os.environ.get("CLAUDE_PROJECTS_DIR")
        if env_override:
            claude_projects = Path(env_override)

        # Handle AGENT_HISTORY_HOME: if CWD is inside the test home, compute
        # the workspace path relative to it (e.g., /tmp/xxx/home/user/myproject -> /home/user/myproject)
        agent_home = os.environ.get("AGENT_HISTORY_HOME")
        if agent_home:
            try:
                rel = cwd.relative_to(Path(agent_home))
                # Normalize to absolute workspace path
                normalized_cwd = "/" + str(rel).lstrip("/")
                # Encode as workspace pattern: /home/user/myproject -> -home-user-myproject
                encoded_pattern = normalized_cwd.replace("/", "-")
                # Check if this workspace exists in Claude projects
                if claude_projects.exists():
                    for workspace_dir in claude_projects.iterdir():
                        if not workspace_dir.is_dir():
                            continue
                        if (
                            encoded_pattern == workspace_dir.name
                            or encoded_pattern in workspace_dir.name
                        ):
                            return ("local", normalized_cwd)
            except ValueError:
                # CWD is not under AGENT_HISTORY_HOME
                pass

        # Check if CWD is under Claude projects
        try:
            relative = cwd.relative_to(claude_projects)
            # First part of relative path is the encoded workspace name
            if relative.parts:
                encoded_workspace = relative.parts[0]
                # Decode workspace path: replace '-' with '/' and URL-decode
                # Format: -home-user-project -> /home/user/project
                if encoded_workspace.startswith("-"):
                    workspace = encoded_workspace.replace("-", "/")
                    workspace = urllib.parse.unquote(workspace)
                    return ("local", workspace)
                else:
                    # Handle non-standard encoding (e.g., Windows paths)
                    workspace = urllib.parse.unquote(encoded_workspace)
                    return ("local", workspace)
        except ValueError:
            # CWD is not under Claude projects
            pass

        # Check if CWD (as an absolute path) has a corresponding workspace directory
        # in Claude projects. This handles the case where the user is in the actual
        # project directory and sessions exist for it.
        # Example: CWD=/tmp/pytest-xxx/test-workspace, Claude has sessions at
        # .claude/projects/-tmp-pytest-xxx-test-workspace/
        if claude_projects.exists():
            # Encode CWD as workspace pattern
            cwd_encoded = cwd_str.replace("/", "-")
            if not cwd_encoded.startswith("-"):
                cwd_encoded = "-" + cwd_encoded
            for workspace_dir in claude_projects.iterdir():
                if not workspace_dir.is_dir():
                    continue
                # Check for exact match of encoded CWD
                if workspace_dir.name == cwd_encoded:
                    return ("local", cwd_str)

        # Also check if CWD matches a project workspace path
        # This handles the case where the user is in the actual project directory
        from agent_history.storage.config import load_config

        config = load_config()
        projects = config.get("projects", {})

        for project_name, project_def in projects.items():
            for home, workspaces in project_def.items():
                if isinstance(workspaces, list):
                    for ws_path in workspaces:
                        # Decode encoded workspace path if needed
                        # Encoded format: -home-user-projects-auth -> /home/user/projects/auth
                        decoded_ws = ws_path
                        if ws_path.startswith("-"):
                            decoded_ws = ws_path.replace("-", "/")
                        elif "/" not in ws_path and ws_path:
                            # Assume it's encoded without leading dash
                            decoded_ws = "/" + ws_path.replace("-", "/")

                        # Check if CWD ends with the workspace path (decoded)
                        # This allows for test directories like /tmp/xxx/home/user/projects/auth
                        # to match /home/user/projects/auth
                        if cwd_str.endswith(decoded_ws) or cwd_str == decoded_ws:
                            return (home, decoded_ws)

        return (None, None)

    def _detect_cwd_project(self, workspace: Optional[str], home: Optional[str]) -> Optional[str]:
        """Check if workspace belongs to a project.

        Uses the configuration's project definitions to find if the current
        workspace is part of a defined project.

        Args:
            workspace: The workspace path (decoded).
            home: The home identifier (e.g., "local", "wsl:Ubuntu").

        Returns:
            Project name if the workspace belongs to a project, None otherwise.
        """
        if not workspace or not home:
            return None

        from agent_history.storage.config import get_alias_for_workspace

        # get_alias_for_workspace expects an encoded workspace name
        # Convert decoded path to encoded form: /home/user/project -> home-user-project
        encoded_workspace = workspace.replace("/", "-").lstrip("-")

        # Use the config function to find the project/alias for this workspace
        return get_alias_for_workspace(encoded_workspace, home)

    def _enumerate_available_homes(self) -> Dict[str, List[str]]:
        """Enumerate all available homes by category.

        Discovers available WSL distributions, Windows users (if accessible),
        and configured remote hosts.

        Returns:
            Dictionary mapping categories to lists of available items.
            Example: {"wsl": ["Ubuntu", "Debian"], "windows": ["alice"], "remote": ["vm01"]}
        """
        from agent_history.storage.config import get_saved_homes
        from agent_history.utils.platform import (
            get_windows_users_with_claude,
            get_wsl_distributions,
            is_running_in_wsl,
        )

        homes: Dict[str, List[str]] = {
            "wsl": [],
            "windows": [],
            "remote": [],
        }

        # WSL distributions (available from Windows)
        try:
            wsl_distros = get_wsl_distributions()
            homes["wsl"] = [d["name"] for d in wsl_distros if d.get("name")]
        except Exception:
            # Ignore errors during WSL detection
            pass

        # Windows users (available from WSL)
        if is_running_in_wsl():
            try:
                windows_users = get_windows_users_with_claude()
                homes["windows"] = [u["username"] for u in windows_users if u.get("username")]
            except Exception:
                # Ignore errors during Windows user detection
                pass

        # Configured remote hosts
        try:
            saved_homes = get_saved_homes()
            # Filter to only remote hosts (not wsl: or windows: prefixed)
            for home_spec in saved_homes:
                if isinstance(home_spec, str):
                    if home_spec.startswith("remote:"):
                        homes["remote"].append(home_spec[7:])  # Strip "remote:" prefix
                    elif not home_spec.startswith(("wsl:", "windows:")):
                        # Assume bare names are remote hosts
                        homes["remote"].append(home_spec)
                elif isinstance(home_spec, dict) and home_spec.get("name"):
                    name = home_spec["name"]
                    if name.startswith("remote:"):
                        homes["remote"].append(name[7:])
                    elif not name.startswith(("wsl:", "windows:")):
                        homes["remote"].append(name)
        except Exception:
            # Ignore errors during remote home detection
            pass

        return homes

    def _get_agent_paths(self) -> tuple[Optional[Path], Optional[Path], Optional[Path]]:
        """Get paths for Claude, Codex, Gemini session directories.

        Checks environment variables first, then falls back to default paths.

        Returns:
            Tuple of (claude_projects_dir, codex_sessions_dir, gemini_sessions_dir).
            Each may be None if the directory doesn't exist.
        """
        import os

        # Claude projects directory
        claude_env = os.environ.get("CLAUDE_PROJECTS_DIR")
        if claude_env:
            claude_dir = Path(claude_env)
        else:
            claude_dir = Path.home() / ".claude" / "projects"
        claude_dir = claude_dir if claude_dir.exists() else None

        # Codex sessions directory
        codex_env = os.environ.get("CODEX_SESSIONS_DIR")
        if codex_env:
            codex_dir = Path(codex_env)
        else:
            codex_dir = Path.home() / ".codex" / "sessions"
        codex_dir = codex_dir if codex_dir.exists() else None

        # Gemini sessions directory
        gemini_env = os.environ.get("GEMINI_SESSIONS_DIR")
        if gemini_env:
            gemini_dir = Path(gemini_env)
        else:
            gemini_dir = Path.home() / ".gemini" / "tmp"
        gemini_dir = gemini_dir if gemini_dir.exists() else None

        return (claude_dir, codex_dir, gemini_dir)
