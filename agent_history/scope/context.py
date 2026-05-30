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
from typing import TYPE_CHECKING, Any

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
        pi_sessions_dir: Path to Pi's sessions directory for session scanning.
    """

    # Platform
    platform: str = ""
    is_wsl: bool = False

    # Current location
    cwd: Path = field(default_factory=Path.cwd)
    cwd_home: str | None = None
    cwd_workspace: str | None = None
    cwd_project: str | None = None

    # Available resources
    available_homes: dict[str, list[str]] = field(default_factory=dict)

    # Configuration
    project_config: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Agent paths (for session scanning)
    claude_projects_dir: Path | None = None
    codex_sessions_dir: Path | None = None
    gemini_sessions_dir: Path | None = None
    pi_sessions_dir: Path | None = None


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
        projects: Project names for project-scoped operations (--project flag, repeatable).
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
    home_type: str | None = None
    home_value: str | None = None
    home_names: list[str] = field(default_factory=list)

    # Workspace selection
    all_workspaces: bool = False
    projects: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)  # Positional patterns (exact match)
    name_patterns: list[str] = field(default_factory=list)  # -n patterns (substring match)
    this_only: bool = False

    # Session filters
    agent: str | None = None
    since: str | None = None
    until: str | None = None

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

    format: str | None = None
    output_path: Path | None = None
    quiet: bool = False
    human_readable: bool = False
    width: int | None = None


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
    verb_args: dict[str, Any] = field(default_factory=dict)


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
    suggestions: list[str] = field(default_factory=list)


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
    errors: list[ResolutionError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

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
        claude_dir, codex_dir, gemini_dir, pi_dir = self._get_agent_paths()
        ctx.claude_projects_dir = claude_dir
        ctx.codex_sessions_dir = codex_dir
        ctx.gemini_sessions_dir = gemini_dir
        ctx.pi_sessions_dir = pi_dir

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

    def _detect_cwd_workspace(self) -> tuple[str | None, str | None]:
        """Detect if CWD is within a workspace.

        Checks multiple sources:
        1. If CWD is under Claude projects (~/.claude/projects/)
        2. If CWD matches a workspace path in project configuration
        3. If AGENT_HISTORY_HOME is set, check if CWD relative to it matches a workspace

        Returns:
            Tuple of (home, workspace) where home is "local" and workspace
            is the decoded workspace path, or (None, None) if not in a workspace.
        """
        cwd = Path.cwd()
        cwd_str = str(cwd)
        cwd_str_normalized = cwd_str.replace("\\", "/")
        claude_projects = self._get_claude_projects_dir()

        for detector in (
            self._workspace_from_agent_home,
            self._workspace_from_claude_projects_dir,
            self._workspace_from_existing_claude_dir,
        ):
            result = detector(cwd, claude_projects)
            if result != (None, None):
                return result

        project_result = self._workspace_from_project_config(cwd_str_normalized)
        if project_result != (None, None):
            return project_result

        return (None, None)

    def _get_claude_projects_dir(self) -> Path:
        """Return the configured Claude projects directory."""
        import os

        env_override = os.environ.get("CLAUDE_PROJECTS_DIR")
        if env_override:
            return Path(env_override)
        return Path.home() / ".claude" / "projects"

    def _workspace_from_agent_home(
        self,
        cwd: Path,
        claude_projects: Path,
    ) -> tuple[str | None, str | None]:
        """Detect synthetic test workspaces rooted under AGENT_HISTORY_HOME."""
        import os
        import urllib.parse

        from agent_history.utils.paths import encode_workspace_path

        agent_home = os.environ.get("AGENT_HISTORY_HOME")
        if not agent_home:
            return (None, None)

        try:
            rel = cwd.relative_to(Path(agent_home))
        except ValueError:
            return (None, None)

        normalized_cwd = "/" + str(rel).replace("\\", "/").lstrip("/")
        encoded_pattern = encode_workspace_path(normalized_cwd)
        if not claude_projects.exists():
            return (None, None)

        for workspace_dir in claude_projects.iterdir():
            if not workspace_dir.is_dir():
                continue
            dir_name = urllib.parse.unquote(workspace_dir.name)
            if encoded_pattern == dir_name or encoded_pattern in dir_name:
                return ("local", normalized_cwd)
        return (None, None)

    def _workspace_from_claude_projects_dir(
        self,
        cwd: Path,
        claude_projects: Path,
    ) -> tuple[str | None, str | None]:
        """Detect when CWD is inside Claude's encoded projects directory."""
        import urllib.parse

        from agent_history.utils.paths import normalize_workspace_name

        try:
            relative = cwd.relative_to(claude_projects)
        except ValueError:
            return (None, None)

        if not relative.parts:
            return (None, None)
        encoded_workspace = urllib.parse.unquote(relative.parts[0])
        workspace = normalize_workspace_name(encoded_workspace, verify_local=True)
        return ("local", workspace)

    def _workspace_from_existing_claude_dir(
        self,
        cwd: Path,
        claude_projects: Path,
    ) -> tuple[str | None, str | None]:
        """Detect actual project directories that have Claude sessions."""
        from agent_history.utils.paths import encode_workspace_path

        if not claude_projects.exists():
            return (None, None)

        cwd_str = str(cwd)
        cwd_encoded = encode_workspace_path(cwd_str.replace("\\", "/"))
        for workspace_dir in claude_projects.iterdir():
            if workspace_dir.is_dir() and workspace_dir.name == cwd_encoded:
                return ("local", cwd_str)
        return (None, None)

    def _workspace_from_project_config(
        self,
        cwd_str_normalized: str,
    ) -> tuple[str | None, str | None]:
        """Detect CWD by matching readable paths in project config."""
        from agent_history.storage.config import load_config

        config = load_config()
        for project_def in config.get("projects", {}).values():
            if not isinstance(project_def, dict):
                continue
            for home, workspaces in project_def.items():
                if not isinstance(workspaces, list):
                    continue
                for ws_path in workspaces:
                    if not ws_path:
                        continue
                    decoded_ws = self._decode_config_workspace_path(ws_path)
                    if cwd_str_normalized.endswith(decoded_ws) or cwd_str_normalized == decoded_ws:
                        return (home, decoded_ws)

        return (None, None)

    def _decode_config_workspace_path(self, ws_path: str) -> str:
        """Return a readable workspace path from config storage."""
        from agent_history.utils.paths import normalize_workspace_name

        if "/" in ws_path or "\\" in ws_path:
            return ws_path.replace("\\", "/")
        return normalize_workspace_name(ws_path, verify_local=False)

    def _detect_cwd_project(self, workspace: str | None, home: str | None) -> str | None:
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

        from agent_history.storage.config import get_alias_for_workspace, load_config

        config = load_config()
        for project_name, project_def in config.get("projects", {}).items():
            if not isinstance(project_def, dict):
                continue
            workspaces = project_def.get(home, [])
            if isinstance(workspaces, list) and workspace in workspaces:
                return str(project_name)

        # get_alias_for_workspace expects an encoded workspace name
        from agent_history.utils.paths import encode_workspace_path

        encoded_workspace = encode_workspace_path(workspace).lstrip("-")

        # Use the config function to find the project/alias for this workspace
        return get_alias_for_workspace(encoded_workspace, home)

    def _enumerate_available_homes(self) -> dict[str, list[str]]:
        """Enumerate all available homes by category.

        Discovers available WSL distributions, Windows users (if accessible),
        and configured remote hosts.

        Returns:
            Dictionary mapping categories to lists of available items.
            Example: {"wsl": ["Ubuntu", "Debian"], "windows": ["alice"], "remote": ["vm01"]}
        """
        homes: dict[str, list[str]] = {
            "wsl": [],
            "windows": [],
            "remote": [],
        }

        if not self._should_skip_platform_scan():
            self._add_detected_platform_homes(homes)
        self._add_saved_remote_homes(homes)

        return homes

    def _platform_scan_overrides(self) -> tuple[bool, bool, bool]:
        """Return test-mode and host override state for platform probing."""
        import os

        has_wsl_override = bool(
            os.environ.get("CLAUDE_WSL_TEST_DISTRO") or os.environ.get("AGENT_HISTORY_HOME_WSL")
        )
        has_windows_override = bool(
            os.environ.get("CLAUDE_WINDOWS_PROJECTS_DIR")
            or os.environ.get("AGENT_HISTORY_HOME_WINDOWS")
        )
        return (
            bool(os.environ.get("AGENT_HISTORY_TEST_MODE")),
            has_wsl_override,
            has_windows_override,
        )

    def _should_skip_platform_scan(self) -> bool:
        """Return True when injected test homes make host probing unnecessary."""
        import os

        test_mode, has_wsl_override, has_windows_override = self._platform_scan_overrides()
        injected_home_envs = (
            "AGENT_HISTORY_HOME",
            "AGENT_HISTORY_HOME_WSL",
            "AGENT_HISTORY_HOME_WINDOWS",
            "AGENT_HISTORY_CONFIG_DIR",
            "CLAUDE_PROJECTS_DIR",
            "CODEX_SESSIONS_DIR",
            "GEMINI_SESSIONS_DIR",
            "PI_CODING_AGENT_SESSION_DIR",
            "PI_SESSIONS_DIR",
        )
        return (
            test_mode
            and any(os.environ.get(name) for name in injected_home_envs)
            and not has_wsl_override
            and not has_windows_override
        )

    def _add_detected_platform_homes(self, homes: dict[str, list[str]]) -> None:
        """Populate WSL and Windows homes from host platform probes."""
        from agent_history.utils.platform import (
            get_windows_users_with_claude,
            get_wsl_distributions,
            is_running_in_wsl,
        )

        test_mode, has_wsl_override, has_windows_override = self._platform_scan_overrides()
        scan_wsl = not (test_mode and has_windows_override and not has_wsl_override)
        scan_windows = not (test_mode and has_wsl_override and not has_windows_override)

        if scan_wsl:
            try:
                homes["wsl"] = [
                    distro["name"] for distro in get_wsl_distributions() if distro.get("name")
                ]
            except Exception:
                pass

        if scan_windows and is_running_in_wsl():
            try:
                homes["windows"] = [
                    user["username"]
                    for user in get_windows_users_with_claude()
                    if user.get("username")
                ]
            except Exception:
                pass

    def _add_saved_remote_homes(self, homes: dict[str, list[str]]) -> None:
        """Append configured SSH remote homes."""
        from agent_history.storage.config import get_saved_homes

        try:
            saved_homes = get_saved_homes()
            for home_spec in saved_homes:
                remote = self._remote_name_from_home_spec(home_spec)
                if remote:
                    homes["remote"].append(remote)
        except Exception:
            pass

    def _remote_name_from_home_spec(self, home_spec: Any) -> str | None:
        """Normalize a configured home entry to a remote host name."""
        if isinstance(home_spec, dict):
            home_spec = home_spec.get("name")
        if not isinstance(home_spec, str) or home_spec == "web":
            return None
        if home_spec.startswith("remote:"):
            return home_spec[7:]
        if home_spec.startswith(("wsl:", "windows:")):
            return None
        return home_spec

    def _get_agent_paths(
        self,
    ) -> tuple[Path | None, Path | None, Path | None, Path | None]:
        """Get paths for Claude, Codex, Gemini, and Pi session directories.

        Checks environment variables first, then falls back to default paths.

        Returns:
            Tuple of (claude_projects_dir, codex_sessions_dir, gemini_sessions_dir, pi_sessions_dir).
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

        pi_env = os.environ.get("PI_CODING_AGENT_SESSION_DIR") or os.environ.get("PI_SESSIONS_DIR")
        if pi_env:
            pi_dir = Path(pi_env)
        else:
            pi_dir = Path.home() / ".pi" / "agent" / "sessions"
        pi_dir = pi_dir if pi_dir.exists() else None

        return (claude_dir, codex_dir, gemini_dir, pi_dir)


def build_resolution_context() -> ResolutionContext:
    """Build resolution context from environment.

    This is a convenience function that creates a ContextBuilder and
    returns the built context.

    Returns:
        ResolutionContext with platform info, CWD detection,
        available homes, and configuration loaded.
    """
    builder = ContextBuilder()
    return builder.build()
