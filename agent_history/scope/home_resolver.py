"""
Home Resolver Strategy Pattern.

This module implements a strategy pattern for resolving agent directories
across different home types (local, WSL, Windows, remote).

The strategy pattern eliminates repeated switch statements throughout the
resolver code, making it easier to add new home types and ensuring consistent
behavior across all directory resolution operations.

Usage:
    resolver = get_resolver_for_home("local")
    claude_dir = resolver.get_claude_dir(context)
    codex_dir = resolver.get_codex_dir(context)
    gemini_dir = resolver.get_gemini_dir(context)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from agent_history.scope.context import ResolutionContext


class HomeResolver(ABC):
    """
    Abstract base class for home-specific directory resolution.

    Each concrete implementation handles a different home type:
    - LocalHomeResolver: Local filesystem (default)
    - WSLHomeResolver: Windows Subsystem for Linux
    - WindowsHomeResolver: Windows from Linux
    - RemoteHomeResolver: Remote machines via SSH/etc.

    The resolver provides access to agent-specific directories within
    a home, abstracting away the path differences between home types.
    """

    @property
    @abstractmethod
    def home_type(self) -> str:
        """
        Return the home type identifier.

        Returns:
            Home type string (e.g., "local", "wsl", "windows", "remote").
        """
        ...

    @abstractmethod
    def get_claude_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Claude projects directory for this home.

        Args:
            context: Resolution context containing environment configuration.

        Returns:
            Path to Claude projects directory, or None if not available.
        """
        ...

    @abstractmethod
    def get_codex_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Codex sessions directory for this home.

        Args:
            context: Resolution context containing environment configuration.

        Returns:
            Path to Codex sessions directory, or None if not available.
        """
        ...

    @abstractmethod
    def get_gemini_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Gemini sessions directory for this home.

        Args:
            context: Resolution context containing environment configuration.

        Returns:
            Path to Gemini sessions directory, or None if not available.
        """
        ...


class LocalHomeResolver(HomeResolver):
    """
    Resolver for local filesystem homes.

    This is the default and most common resolver. It uses the directories
    configured in the ResolutionContext, which respect environment variable
    overrides for testing.
    """

    @property
    def home_type(self) -> str:
        return "local"

    def get_claude_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the local Claude projects directory.

        Uses context.claude_projects_dir which respects AGENT_HISTORY_HOME
        environment variable for testing.
        """
        return context.claude_projects_dir

    def get_codex_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the local Codex sessions directory.

        Uses context.codex_sessions_dir which respects CODEX_SESSIONS_DIR
        environment variable for testing.
        """
        return context.codex_sessions_dir

    def get_gemini_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the local Gemini sessions directory.

        Uses context.gemini_sessions_dir which respects GEMINI_SESSIONS_DIR
        environment variable for testing.
        """
        return context.gemini_sessions_dir


class WSLHomeResolver(HomeResolver):
    """
    Resolver for Windows Subsystem for Linux homes.

    WSL homes are accessed from within Linux, reaching Windows filesystems
    via /mnt/c or /mnt/d style paths. The specific WSL distribution is
    identified by the suffix (e.g., "wsl:Ubuntu").

    TODO: Implement WSL path resolution logic.
    """

    def __init__(self, distro: Optional[str] = None):
        """
        Initialize WSL resolver.

        Args:
            distro: WSL distribution name (e.g., "Ubuntu", "Debian").
                   If None, uses the default distribution.
        """
        self._distro = distro

    @property
    def home_type(self) -> str:
        return "wsl"

    @property
    def distro(self) -> Optional[str]:
        """Return the WSL distribution name."""
        return self._distro

    def get_claude_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Claude projects directory for WSL home.

        Uses get_wsl_projects_dir() from platform utils which supports
        the CLAUDE_WSL_PROJECTS_DIR test override.
        """
        from agent_history.utils.platform import get_wsl_projects_dir

        if self._distro:
            return get_wsl_projects_dir(self._distro)
        return None

    def get_codex_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Codex sessions directory for WSL home.

        TODO: Implement WSL path resolution for Codex.
        """
        return None

    def get_gemini_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Gemini sessions directory for WSL home.

        TODO: Implement WSL path resolution for Gemini.
        """
        return None


class WindowsHomeResolver(HomeResolver):
    """
    Resolver for Windows homes accessed from Linux.

    Windows homes are accessed via mount points or network paths.
    This handles cases where Linux is the host and Windows
    filesystems are accessed remotely or via mount.

    TODO: Implement Windows path resolution logic.
    """

    def __init__(self, user: Optional[str] = None):
        """
        Initialize Windows resolver.

        Args:
            user: Windows username for path resolution.
        """
        self._user = user

    @property
    def home_type(self) -> str:
        return "windows"

    @property
    def user(self) -> Optional[str]:
        """Return the Windows username."""
        return self._user

    def get_claude_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Claude projects directory for Windows home.

        TODO: Implement Windows path resolution.
        Windows paths would be something like:
        /mnt/c/Users/<username>/.claude/projects/
        or via network: //hostname/Users/<username>/.claude/projects/
        """
        return None

    def get_codex_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Codex sessions directory for Windows home.

        TODO: Implement Windows path resolution for Codex.
        """
        return None

    def get_gemini_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Gemini sessions directory for Windows home.

        TODO: Implement Windows path resolution for Gemini.
        """
        return None


class RemoteHomeResolver(HomeResolver):
    """
    Resolver for remote machine homes.

    Remote homes are accessed via SSH, SFTP, or other remote protocols.
    The specific remote machine is identified by the suffix (e.g., "remote:dev").

    TODO: Implement remote path resolution logic.
    """

    def __init__(self, remote_name: Optional[str] = None):
        """
        Initialize remote resolver.

        Args:
            remote_name: Name of the remote machine (e.g., "dev", "prod").
        """
        self._remote_name = remote_name

    @property
    def home_type(self) -> str:
        return "remote"

    @property
    def remote_name(self) -> Optional[str]:
        """Return the remote machine name."""
        return self._remote_name

    def get_claude_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Claude projects directory for remote home.

        TODO: Implement remote path resolution.
        This would require SSH/SFTP access or cached remote data.
        """
        return None

    def get_codex_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Codex sessions directory for remote home.

        TODO: Implement remote path resolution for Codex.
        """
        return None

    def get_gemini_dir(self, context: ResolutionContext) -> Optional[Path]:
        """
        Get the Gemini sessions directory for remote home.

        TODO: Implement remote path resolution for Gemini.
        """
        return None


def get_resolver_for_home(home: str) -> HomeResolver:
    """
    Factory function to get the appropriate resolver for a home type.

    Parses the home string and returns the appropriate resolver instance.
    Home strings follow the format:
    - "local" -> LocalHomeResolver
    - "wsl:Ubuntu" -> WSLHomeResolver(distro="Ubuntu")
    - "wsl" (no suffix) -> WSLHomeResolver()
    - "windows" -> WindowsHomeResolver()
    - "windows:alice" -> WindowsHomeResolver(user="alice")
    - "remote:dev" -> RemoteHomeResolver(remote_name="dev")

    Args:
        home: Home identifier string.

    Returns:
        Appropriate HomeResolver instance for the home type.

    Examples:
        >>> resolver = get_resolver_for_home("local")
        >>> isinstance(resolver, LocalHomeResolver)
        True

        >>> resolver = get_resolver_for_home("wsl:Ubuntu")
        >>> isinstance(resolver, WSLHomeResolver)
        True
        >>> resolver.distro
        'Ubuntu'
    """
    if home == "local":
        return LocalHomeResolver()

    if home.startswith("wsl:"):
        distro = home[4:]  # Extract distro name after "wsl:"
        return WSLHomeResolver(distro=distro if distro else None)

    if home == "wsl":
        return WSLHomeResolver()

    if home.startswith("windows:"):
        user = home[8:]  # Extract user after "windows:"
        return WindowsHomeResolver(user=user if user else None)

    if home == "windows":
        return WindowsHomeResolver()

    if home.startswith("remote:"):
        remote_name = home[7:]  # Extract remote name after "remote:"
        return RemoteHomeResolver(remote_name=remote_name if remote_name else None)

    # Default to local for unknown home types
    return LocalHomeResolver()
