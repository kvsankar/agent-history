"""Platform detection utilities for agent-history.

This module provides functions for detecting the current platform environment,
including WSL, Windows, and cross-platform path resolution.
"""

import os
import platform
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Agent backend identifiers (needed for WSL distro info)
AGENT_CLAUDE = "claude"
AGENT_CODEX = "codex"
AGENT_GEMINI = "gemini"
AGENT_PI = "pi"


def _get_wsl_timeout() -> float:
    raw = os.environ.get("AGENT_HISTORY_WSL_TIMEOUT", "").strip()
    if not raw:
        return 2.0
    try:
        timeout = float(raw)
    except ValueError:
        return 2.0
    return max(0.5, timeout)


def _get_unc_timeout() -> float:
    raw = os.environ.get("AGENT_HISTORY_UNC_TIMEOUT", "").strip()
    if not raw:
        return 0.5
    try:
        timeout = float(raw)
    except ValueError:
        return 0.5
    return max(0.1, timeout)


__all__ = [
    # Agent constants
    "AGENT_CLAUDE",
    "AGENT_CODEX",
    "AGENT_GEMINI",
    "AGENT_PI",
    # Command path resolution
    "get_command_path",
    "get_windows_codex_sessions_dir",
    "get_windows_gemini_sessions_dir",
    # Windows detection
    "get_windows_home_from_wsl",
    "get_windows_pi_sessions_dir",
    "get_windows_projects_dir",
    "get_windows_users_with_claude",
    "get_wsl_codex_sessions_dir",
    "get_wsl_distribution_names",
    "get_wsl_distributions",
    "get_wsl_gemini_sessions_dir",
    "get_wsl_pi_sessions_dir",
    "get_wsl_projects_dir",
    # WSL detection
    "is_running_in_wsl",
    "is_windows_remote",
    # Remote spec detection
    "is_wsl_remote",
    # Cache management (for testing)
    "windows_home_cache_context",
]


# ============================================================================
# Command Path Cache
# ============================================================================


class _CommandPathCache:
    """Cache for external command path resolution.

    Caches results of shutil.which() lookups to avoid repeated
    filesystem searches for the same commands.

    This class wraps the cache to make it testable and clearable,
    following Rhodes' NO-GLOBAL-MUTABLE principle.
    """

    def __init__(self) -> None:
        self._paths: dict[str, str] = {}

    def get_path(self, cmd: str) -> str:
        """Get absolute path for command, with caching.

        Args:
            cmd: Command name (e.g., 'ssh', 'rsync')

        Returns:
            Absolute path or original command name if not found.
        """
        if cmd not in self._paths:
            path = shutil.which(cmd)
            self._paths[cmd] = path if path else cmd
        return self._paths[cmd]

    def clear(self) -> None:
        """Clear cache (useful for testing)."""
        self._paths.clear()


# Module instance (can be replaced in tests)
_command_path_cache = _CommandPathCache()


def get_command_path(cmd: str) -> str:
    """Get absolute path for an external command.

    Uses shutil.which() to find the command in PATH, then caches the result.
    Falls back to the command name if not found (lets subprocess handle the error).

    Args:
        cmd: Command name (e.g., 'ssh', 'rsync', 'wsl')

    Returns:
        Absolute path to the command, or the original name if not found.
    """
    return _command_path_cache.get_path(cmd)


# ============================================================================
# Windows Home Cache
# ============================================================================


class _WindowsHomeCache:
    """Cache for Windows home directory lookups.

    Avoids repeated slow filesystem operations when looking up
    Windows user home directories from WSL.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Optional[Path]] = {}

    def get(self, key: str) -> Optional[Path]:
        """Get cached value for key."""
        return self._cache.get(key)

    def has(self, key: str) -> bool:
        """Check if key is cached."""
        return key in self._cache

    def set(self, key: str, value: Optional[Path]) -> None:
        """Set cached value for key."""
        self._cache[key] = value

    def clear(self) -> None:
        """Clear cache (useful for testing)."""
        self._cache.clear()


# Use holder dict to avoid global statement (PLW0603)
_cache_holder: dict[str, _WindowsHomeCache] = {"instance": _WindowsHomeCache()}


def _get_windows_home_cache() -> _WindowsHomeCache:
    """Get the current Windows home cache instance."""
    return _cache_holder["instance"]


@contextmanager
def windows_home_cache_context(cache: Optional[_WindowsHomeCache] = None):
    """Context manager to temporarily override the Windows home cache.

    This enables testing without affecting global state. When used in tests,
    provides an isolated cache instance that doesn't affect other tests.

    Args:
        cache: Optional cache instance to use. If None, creates a new empty cache.

    Yields:
        The active cache instance.

    Example:
        def test_windows_home_caching():
            cache = _WindowsHomeCache()
            with windows_home_cache_context(cache):
                # Test with isolated cache
                result = get_windows_user_home("alice")
                assert cache.has("alice")
    """
    old_cache = _cache_holder["instance"]
    try:
        _cache_holder["instance"] = cache if cache is not None else _WindowsHomeCache()
        yield _cache_holder["instance"]
    finally:
        _cache_holder["instance"] = old_cache


# ============================================================================
# WSL Detection
# ============================================================================


def is_running_in_wsl() -> bool:
    """Detect if we're running inside WSL."""
    try:
        with open("/proc/version") as f:
            content = f.read().lower()
            return "microsoft" in content or "wsl" in content
    except OSError:
        return False


# ============================================================================
# Windows Home Detection from WSL
# ============================================================================


def _find_user_home_on_drives(username: str) -> Optional[Path]:
    """Find Windows user home by username across all drives."""
    mnt = Path("/mnt")
    if not mnt.exists():
        return None
    for drive in sorted(mnt.iterdir()):
        if drive.is_dir() and len(drive.name) == 1 and drive.name.isalpha():
            user_path = drive / "Users" / username
            if user_path.exists() and (user_path / ".claude" / "projects").exists():
                return user_path
    return None


def _get_userprofile_via_cmd() -> Optional[Path]:
    """Get Windows home via cmd.exe USERPROFILE variable."""
    try:
        result = subprocess.run(
            [get_command_path("cmd.exe"), "/c", "echo %USERPROFILE%"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        win_path = result.stdout.strip()
        if not win_path or win_path == "%USERPROFILE%":
            return None

        result = subprocess.run(
            [get_command_path("wslpath"), win_path],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        wsl_path = Path(result.stdout.strip())
        if wsl_path.exists() and (wsl_path / ".claude" / "projects").exists():
            return wsl_path
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _find_claude_user_in_drive(drive: Path) -> Optional[Path]:
    """Find first user with Claude installed in a drive."""
    users_dir = drive / "Users"
    if not users_dir.exists():
        return None
    for user_dir in users_dir.iterdir():
        if user_dir.is_dir() and not user_dir.is_symlink():
            if (user_dir / ".claude" / "projects").exists():
                return user_dir
    return None


def _scan_drives_for_claude_user() -> Optional[Path]:
    """Scan all drives for any user with Claude installed."""
    mnt = Path("/mnt")
    if not mnt.exists():
        return None
    for drive in sorted(mnt.iterdir()):
        if not (drive.is_dir() and len(drive.name) == 1 and drive.name.isalpha()):
            continue
        user_home = _find_claude_user_in_drive(drive)
        if user_home:
            return user_home
    return None


def get_windows_home_from_wsl(username: Optional[str] = None) -> Optional[Path]:
    """
    Get Windows user home directory from WSL.

    Args:
        username: Optional Windows username. If None, uses USERPROFILE.

    Returns:
        Path to Windows home directory, or None if not found.

    If AGENT_HISTORY_HOME_WINDOWS is set, uses that path instead of probing
    the real Windows filesystem (for testing).
    """
    # Check for test override - use injected Windows home path
    windows_home_override = os.environ.get("AGENT_HISTORY_HOME_WINDOWS")
    if windows_home_override:
        return Path(windows_home_override)

    # When using an isolated AGENT_HISTORY_HOME in test mode, don't probe the host.
    if os.environ.get("AGENT_HISTORY_TEST_MODE") and os.environ.get("AGENT_HISTORY_HOME"):
        return None

    cache_key = username or "_default_"
    cache = _get_windows_home_cache()

    # Check cache first to avoid slow filesystem operations
    if cache.has(cache_key):
        return cache.get(cache_key)

    if username:
        result = _find_user_home_on_drives(username)
        cache.set(cache_key, result)
        return result

    # Primary approach: use Windows USERPROFILE
    home = _get_userprofile_via_cmd()
    if home:
        cache.set(cache_key, home)
        return home

    # Fallback: scan all drives
    result = _scan_drives_for_claude_user()
    cache.set(cache_key, result)
    return result


# ============================================================================
# Windows Users with Claude Detection
# ============================================================================


def _is_valid_windows_drive(drive: Path) -> bool:
    """Check if path is a valid single-letter Windows drive mount."""
    return drive.is_dir() and len(drive.name) == 1 and drive.name.isalpha()


def _scan_users_in_drive(drive: Path, results: list):
    """Scan a drive for Windows users with Claude installed."""
    users_dir = drive / "Users"
    if not users_dir.exists():
        return

    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir() or user_dir.is_symlink():
            continue
        claude_dir = user_dir / ".claude" / "projects"
        if claude_dir.exists():
            workspace_count = len([d for d in claude_dir.iterdir() if d.is_dir()])
            results.append(
                {
                    "username": user_dir.name,
                    "drive": drive.name,
                    "path": user_dir,
                    "claude_dir": claude_dir,
                    "workspace_count": workspace_count,
                }
            )


def get_windows_users_with_claude():
    """Get list of all Windows users with Claude Code installed.

    If overrides are set (AGENT_HISTORY_HOME_WINDOWS or CLAUDE_WINDOWS_PROJECTS_DIR),
    returns empty list to skip real Windows filesystem scanning (for testing
    with injected fixtures).
    """
    # If running under a test/override home, avoid probing the host filesystem.
    if os.environ.get("AGENT_HISTORY_TEST_MODE") and (
        os.environ.get("AGENT_HISTORY_HOME") or os.environ.get("AGENT_HISTORY_HOME_WINDOWS")
    ):
        return []
    if os.environ.get("CLAUDE_WINDOWS_PROJECTS_DIR"):
        return []

    results = []
    mnt = Path("/mnt")

    if not mnt.exists():
        return results

    for drive in sorted(mnt.iterdir()):
        if _is_valid_windows_drive(drive):
            _scan_users_in_drive(drive, results)

    return results


# ============================================================================
# Remote Spec Detection
# ============================================================================


def is_wsl_remote(remote_spec: str) -> bool:
    """Check if remote spec is a WSL distribution (wsl://DistroName)."""
    return remote_spec.startswith("wsl://")


def is_windows_remote(remote_spec: str) -> bool:
    """Check if remote spec is Windows from WSL.

    Recognizes formats:
    - 'windows' (no specific user)
    - 'windows://username' (URL-style)
    - 'windows:username' (config-style)
    """
    return (
        remote_spec == "windows"
        or remote_spec.startswith("windows://")
        or remote_spec.startswith("windows:")
    )


# ============================================================================
# WSL Distribution Detection (from Windows)
# ============================================================================


def _path_exists_with_timeout(path: Path, timeout: float = 5.0) -> bool:
    """Check if a path exists with a timeout (for UNC paths that may block).

    Args:
        path: Path to check
        timeout: Maximum time to wait in seconds

    Returns:
        True if path exists, False if doesn't exist or timeout reached.
    """

    def check_exists() -> bool:
        return path.exists()

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(check_exists)
            return future.result(timeout=timeout)
    except (FuturesTimeoutError, OSError):
        return False


def _get_wsl_candidate_paths(distro_name: str, username: str) -> list:
    """Return candidate UNC paths for a WSL distro."""
    return [
        Path(f"//wsl.localhost/{distro_name}/home/{username}/.claude/projects"),
        Path(f"//wsl$/{distro_name}/home/{username}/.claude/projects"),
    ]


def _get_wsl_gemini_candidate_paths(distro_name: str, username: str) -> list:
    """Return candidate UNC paths for Gemini sessions in a WSL distro."""
    return [
        Path(f"//wsl.localhost/{distro_name}/home/{username}/.gemini/tmp"),
        Path(f"//wsl$/{distro_name}/home/{username}/.gemini/tmp"),
    ]


def _get_wsl_codex_candidate_paths(distro_name: str, username: str) -> list:
    """Return candidate UNC paths for Codex sessions in a WSL distro."""
    return [
        Path(f"//wsl.localhost/{distro_name}/home/{username}/.codex/sessions"),
        Path(f"//wsl$/{distro_name}/home/{username}/.codex/sessions"),
    ]


def _get_wsl_pi_candidate_paths(distro_name: str, username: str) -> list:
    """Return candidate UNC paths for Pi sessions in a WSL distro."""
    return [
        Path(f"//wsl.localhost/{distro_name}/home/{username}/.pi/agent/sessions"),
        Path(f"//wsl$/{distro_name}/home/{username}/.pi/agent/sessions"),
    ]


@lru_cache(maxsize=32)
def _wsl_unc_available(distro_name: str) -> bool:
    """Check whether the WSL UNC base path is reachable."""
    timeout = _get_unc_timeout()
    bases = [
        Path(f"//wsl.localhost/{distro_name}/home"),
        Path(f"//wsl$/{distro_name}/home"),
    ]
    for base in bases:
        try:
            if _path_exists_with_timeout(base, timeout=timeout):
                return True
        except OSError:
            continue
    return False


def _locate_wsl_projects_dir(distro_name: str, username: str):
    """Find the first accessible UNC path for a WSL distro."""
    return _locate_wsl_agent_dir(distro_name, username, AGENT_CLAUDE)


def _locate_wsl_agent_dir(distro_name: str, username: str, agent: str) -> Optional[Path]:
    """Find the first accessible UNC path for an agent in a WSL distro."""
    if not _wsl_unc_available(distro_name):
        return None

    from agent_history.backends.registry import get_backend

    backend = get_backend(agent)
    if backend is None or backend.wsl_candidate_paths is None:
        return None
    candidates = backend.wsl_candidate_paths(distro_name, username)

    for candidate in candidates:
        try:
            if _path_exists_with_timeout(candidate, timeout=_get_unc_timeout()):
                return candidate
        except OSError:
            continue
    return None


def _get_wsl_usernames_from_unc(distro_name: str) -> list:
    """Discover WSL usernames via UNC paths when wsl.exe is unavailable."""
    if not _wsl_unc_available(distro_name):
        return []
    for base in [
        Path(f"//wsl.localhost/{distro_name}/home"),
        Path(f"//wsl$/{distro_name}/home"),
    ]:
        try:
            return [p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")]
        except (OSError, PermissionError):
            continue
    return []


def _build_wsl_distro_info(distro_name: str, usernames: list) -> Optional[dict]:
    """Build WSL distro info from one or more candidate usernames."""
    for username in usernames:
        claude_path = _locate_wsl_projects_dir(distro_name, username)
        codex_path = _locate_wsl_agent_dir(distro_name, username, AGENT_CODEX)
        gemini_path = _locate_wsl_agent_dir(distro_name, username, AGENT_GEMINI)
        has_claude = claude_path is not None
        has_codex = codex_path is not None
        has_gemini = gemini_path is not None
        if has_claude or has_codex or has_gemini:
            return {
                "name": distro_name,
                "username": username,
                "has_claude": has_claude,
                "has_codex": has_codex,
                "has_gemini": has_gemini,
                "path": str(claude_path) if claude_path else None,
                "codex_path": str(codex_path) if codex_path else None,
                "gemini_path": str(gemini_path) if gemini_path else None,
            }

    if not usernames:
        return None

    username = usernames[0]
    return {
        "name": distro_name,
        "username": username,
        "has_claude": False,
        "has_codex": False,
        "has_gemini": False,
        "path": None,
        "codex_path": None,
        "gemini_path": None,
    }


def _get_wsl_distro_names() -> list:
    """Get list of WSL distribution names.

    Notes:
        On Windows, `wsl --list --quiet` typically returns UTF-16 with a BOM and
        may include stray null terminators. We decode with 'utf-16' (to consume
        the BOM correctly), fall back to UTF-8 if needed, and strip any BOM or
        nulls per line before returning clean distro names.
    """
    try:
        result = subprocess.run(
            [get_command_path("wsl"), "--list", "--quiet"],
            check=False,
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []

        raw = result.stdout
        # Prefer utf-16 (consumes BOM). Fallback to utf-8 if decode fails.
        try:
            text = raw.decode("utf-16")
        except UnicodeError:
            text = raw.decode("utf-8", errors="ignore")

        names = []
        for line in text.splitlines():
            # Clean BOM on first line, nulls, and any incidental markers
            cleaned = line.lstrip("\ufeff").replace("\x00", "").strip()
            # Newer WSL may show a leading '* ' for default in some modes; be tolerant
            if cleaned.startswith("* "):
                cleaned = cleaned[2:].strip()
            if cleaned:
                names.append(cleaned)
        return names
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _get_wsl_distro_info(distro_name: str) -> Optional[dict]:
    """Get info for a single WSL distribution. Returns None on failure."""
    try:
        user_result = subprocess.run(
            [get_command_path("wsl"), "-d", distro_name, "whoami"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_get_wsl_timeout(),
        )
        if user_result.returncode != 0:
            usernames = _get_wsl_usernames_from_unc(distro_name)
            return _build_wsl_distro_info(distro_name, usernames)

        username = user_result.stdout.strip()
        return _build_wsl_distro_info(distro_name, [username])
    except (subprocess.TimeoutExpired, FileNotFoundError):
        usernames = _get_wsl_usernames_from_unc(distro_name)
        return _build_wsl_distro_info(distro_name, usernames) if usernames else None


def get_wsl_distributions() -> list:
    """Get list of available WSL distributions.

    Returns:
        List of dicts with distro info: {'name': str, 'username': str, 'has_claude': bool, ...}

    Test override:
        If environment variables are set:
          - CLAUDE_WSL_TEST_DISTRO: name of a synthetic distro
          - CLAUDE_WSL_PROJECTS_DIR: path to a projects dir for that distro
        then return a single entry using those values. This enables real
        filesystem E2E tests without mocking wsl.exe.

        If AGENT_HISTORY_HOME_WSL is set, skip WSL scanning entirely (for testing
        with injected fixtures).
    """
    if os.environ.get("AGENT_HISTORY_TEST_MODE") and os.environ.get("CLAUDE_WINDOWS_PROJECTS_DIR"):
        if not os.environ.get("CLAUDE_WSL_TEST_DISTRO") and not os.environ.get(
            "AGENT_HISTORY_HOME_WSL"
        ):
            return []

    # Skip WSL scanning if WSL home is overridden for testing
    if os.environ.get("AGENT_HISTORY_HOME_WSL"):
        return []

    # Test override
    test_distro = os.environ.get("CLAUDE_WSL_TEST_DISTRO")
    test_projects = os.environ.get("CLAUDE_WSL_PROJECTS_DIR")
    if test_distro and test_projects:
        p = Path(test_projects)
        if p.exists():
            return [
                {
                    "name": test_distro,
                    "username": "test",
                    "has_claude": True,
                    "has_codex": False,
                    "has_gemini": False,
                    "path": str(p),
                    "codex_path": None,
                    "gemini_path": None,
                }
            ]

    if platform.system() != "Windows":
        return []

    distributions = []
    for distro_name in _get_wsl_distro_names():
        if not distro_name:
            continue
        info = _get_wsl_distro_info(distro_name)
        if info:
            distributions.append(info)
    return distributions


def get_wsl_distribution_names() -> list[str]:
    """Get list of WSL distribution names without per-distro probing.

    Returns:
        List of WSL distribution names.

    Test override:
        If CLAUDE_WSL_TEST_DISTRO and CLAUDE_WSL_PROJECTS_DIR are set,
        return just the synthetic distro name.

        If AGENT_HISTORY_HOME_WSL is set, skip WSL scanning entirely.
    """
    if os.environ.get("AGENT_HISTORY_HOME_WSL"):
        return []

    test_distro = os.environ.get("CLAUDE_WSL_TEST_DISTRO")
    test_projects = os.environ.get("CLAUDE_WSL_PROJECTS_DIR")
    if test_distro and test_projects:
        if Path(test_projects).exists():
            return [test_distro]

    if platform.system() != "Windows":
        return []

    return _get_wsl_distro_names()


# ============================================================================
# WSL Username Helper
# ============================================================================


@lru_cache(maxsize=32)
def _get_wsl_username(distro_name: str) -> Optional[str]:
    """Get username from a WSL distribution.

    DRY-EXTRACT-WSL: Common helper to avoid duplicating subprocess call.

    Args:
        distro_name: WSL distribution name

    Returns:
        Username string or None on failure
    """
    try:
        result = subprocess.run(
            [get_command_path("wsl"), "-d", distro_name, "whoami"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_get_wsl_timeout(),
        )
        if result.returncode == 0:
            username = result.stdout.strip()
            return username if username else None
        usernames = _get_wsl_usernames_from_unc(distro_name)
        return usernames[0] if usernames else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


# ============================================================================
# WSL Projects Directory Access
# ============================================================================


def get_wsl_projects_dir(distro_name: str) -> Optional[Path]:
    """Get Claude projects directory for a WSL distribution.

    Args:
        distro_name: WSL distribution name (e.g., 'Ubuntu', 'Debian')

    Returns:
        Path to .claude/projects in WSL, accessible from Windows.
        Returns None if the distribution is inaccessible or Claude is not installed.
    """
    # Test override (DRY-EXTRACT-WSL: same pattern as other WSL functions)
    override = os.environ.get("CLAUDE_WSL_PROJECTS_DIR")
    if override and Path(override).exists():
        return Path(override)

    # Get username using common helper
    username = _get_wsl_username(distro_name)
    if username:
        return _locate_wsl_projects_dir(distro_name, username)
    return None


def _get_wsl_agent_sessions_dir(distro_name: str, agent: str, env_var: str) -> Optional[Path]:
    """Get a WSL agent sessions directory with optional override."""
    override = os.environ.get(env_var)
    if override and Path(override).exists():
        return Path(override)

    username = _get_wsl_username(distro_name)
    if not username:
        return None

    return _locate_wsl_agent_dir(distro_name, username, agent)


def get_wsl_codex_sessions_dir(distro_name: str) -> Optional[Path]:
    """Get Codex sessions directory for a WSL distribution."""
    return _get_wsl_agent_sessions_dir(distro_name, AGENT_CODEX, "CODEX_WSL_SESSIONS_DIR")


def get_wsl_gemini_sessions_dir(distro_name: str) -> Optional[Path]:
    """Get Gemini sessions directory for a WSL distribution."""
    return _get_wsl_agent_sessions_dir(distro_name, AGENT_GEMINI, "GEMINI_WSL_SESSIONS_DIR")


def get_wsl_pi_sessions_dir(distro_name: str) -> Optional[Path]:
    """Get Pi sessions directory for a WSL distribution."""
    return _get_wsl_agent_sessions_dir(distro_name, AGENT_PI, "PI_WSL_SESSIONS_DIR")


def get_windows_projects_dir(username: Optional[str] = None):
    """Get Claude projects directory for Windows from WSL.

    Args:
        username: Optional Windows username. If None, auto-detects from USERPROFILE.

    Returns:
        Path to .claude/projects in Windows, accessible from WSL.
        Returns None if not running in WSL, user not found, or Claude not installed.
    """
    # Test override
    override = os.environ.get("CLAUDE_WINDOWS_PROJECTS_DIR")
    if override and Path(override).exists():
        return Path(override)

    if not is_running_in_wsl():
        return None

    windows_home = get_windows_home_from_wsl(username)

    if not windows_home:
        return None

    projects_dir = windows_home / ".claude" / "projects"

    if not projects_dir.exists():
        return None

    return projects_dir


def get_windows_codex_sessions_dir(username: Optional[str] = None) -> Optional[Path]:
    """Get Codex sessions directory for Windows (from WSL)."""
    override = os.environ.get("CODEX_WINDOWS_SESSIONS_DIR")
    if override and Path(override).exists():
        return Path(override)

    if os.environ.get("AGENT_HISTORY_TEST_MODE") and os.environ.get("CLAUDE_WINDOWS_PROJECTS_DIR"):
        return None

    if not is_running_in_wsl():
        return None

    windows_home = get_windows_home_from_wsl(username)
    if not windows_home:
        return None

    sessions_dir = windows_home / ".codex" / "sessions"
    return sessions_dir if sessions_dir.exists() else None


def get_windows_gemini_sessions_dir(username: Optional[str] = None) -> Optional[Path]:
    """Get Gemini sessions directory for Windows (from WSL)."""
    override = os.environ.get("GEMINI_WINDOWS_SESSIONS_DIR")
    if override and Path(override).exists():
        return Path(override)

    if os.environ.get("AGENT_HISTORY_TEST_MODE") and os.environ.get("CLAUDE_WINDOWS_PROJECTS_DIR"):
        return None

    if not is_running_in_wsl():
        return None

    windows_home = get_windows_home_from_wsl(username)
    if not windows_home:
        return None

    sessions_dir = windows_home / ".gemini" / "tmp"
    return sessions_dir if sessions_dir.exists() else None


def get_windows_pi_sessions_dir(username: Optional[str] = None) -> Optional[Path]:
    """Get Pi sessions directory for Windows (from WSL)."""
    override = os.environ.get("PI_WINDOWS_SESSIONS_DIR")
    if override and Path(override).exists():
        return Path(override)

    if os.environ.get("AGENT_HISTORY_TEST_MODE") and os.environ.get("CLAUDE_WINDOWS_PROJECTS_DIR"):
        return None

    if not is_running_in_wsl():
        return None

    windows_home = get_windows_home_from_wsl(username)
    if not windows_home:
        return None

    sessions_dir = windows_home / ".pi" / "agent" / "sessions"
    return sessions_dir if sessions_dir.exists() else None
