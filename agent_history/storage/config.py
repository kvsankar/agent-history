"""Configuration and project/alias management for agent-history.

This module provides functions for:
- Config directory management (~/.agent-history/)
- Project/alias loading and saving
- Config file management (config.json)
- Home/source management for remote SSH hosts

Environment Variables:
    AGENT_HISTORY_CONFIG_DIR: Override config directory location (for testing)
"""

import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Optional

from agent_history.utils.paths import (
    encode_workspace_path,
    is_cached_workspace,
    is_encoded_workspace_name,
)

__all__ = [
    # Constants
    "CONFIG_DIR_NAME",
    "LEGACY_CONFIG_DIR_NAME",
    # Config directory functions
    "get_config_dir",
    "get_aliases_dir",
    "get_aliases_file",
    "get_projects_file",
    "get_config_file",
    # Config load/save functions
    "load_config",
    "save_config",
    # Home/source functions
    "get_saved_sources",
    "get_saved_homes",
    # Alias/project functions
    "load_aliases",
    "save_aliases",
    "get_alias_for_workspace",
    "get_source_key",
    # Helper functions
    "get_alias_session_count",
    "resolve_alias_workspaces",
]

# =============================================================================
# Constants
# =============================================================================

CONFIG_DIR_NAME = ".agent-history"
LEGACY_CONFIG_DIR_NAME = ".claude-history"

# Lengths of various prefixes used in workspace encoding
WSL_PREFIX_LEN = 6  # Length of "wsl://"
MNT_ENCODED_PREFIX_LEN = 7  # Length of "-mnt-X-" prefix
WINDOWS_PREFIX_LEN = 8  # Length of "windows:"


# =============================================================================
# Config Directory Management
# =============================================================================


def _get_config_dirs() -> tuple[Path, Path]:
    """Return (new_config_dir, legacy_config_dir) under HOME."""
    home_env = os.environ.get("HOME")
    home = Path(home_env) if home_env else Path.home()
    return home / CONFIG_DIR_NAME, home / LEGACY_CONFIG_DIR_NAME


def _apply_secure_permissions(path: Path, mode: int) -> None:
    """Apply POSIX-style permissions unless on Windows."""
    if os.name == "nt":
        return
    os.chmod(path, mode)


def _migrate_legacy_config_dir(new_dir: Path, legacy_dir: Path) -> Path:
    """Migrate legacy ~/.claude-history to ~/.agent-history if needed."""
    if new_dir.exists():
        if legacy_dir.exists():
            try:
                shutil.copytree(legacy_dir, new_dir, dirs_exist_ok=True)
                shutil.rmtree(legacy_dir, ignore_errors=True)
            except OSError as e:
                sys.stderr.write(
                    f"Warning: Could not clean up legacy config dir {legacy_dir}: {e}\n"
                )
        return new_dir
    if not legacy_dir.exists():
        return new_dir

    try:
        legacy_dir.rename(new_dir)
        return new_dir
    except OSError:
        try:
            shutil.copytree(legacy_dir, new_dir, dirs_exist_ok=True)
            shutil.rmtree(legacy_dir, ignore_errors=True)
            return new_dir
        except OSError as e:
            sys.stderr.write(
                f"Warning: Could not migrate legacy config dir {legacy_dir} -> {new_dir}: {e}\n"
            )
            return legacy_dir


def get_config_dir() -> Path:
    """Get the config storage directory (~/.agent-history/, migrates legacy on first use)."""
    # Check for test/override env var first
    override = os.environ.get("AGENT_HISTORY_CONFIG_DIR")
    if override:
        return Path(override)
    new_dir, legacy_dir = _get_config_dirs()
    return _migrate_legacy_config_dir(new_dir, legacy_dir)


def get_aliases_dir() -> Path:
    """Get the aliases storage directory (~/.agent-history/)."""
    return get_config_dir()


def get_aliases_file() -> Path:
    """Get the legacy aliases storage file path (for migration)."""
    return get_aliases_dir() / "aliases.json"


def get_projects_file() -> Path:
    """Get the projects storage file path (now unified with config.json)."""
    return get_config_file()


def get_config_file() -> Path:
    """Get the config file path."""
    return get_config_dir() / "config.json"


# =============================================================================
# Config File Loading/Saving
# =============================================================================


def load_config() -> dict:
    """Load config from storage file. Returns empty structure if not found."""
    config_file = get_config_file()
    config_dir = get_config_dir()
    legacy_projects_file = config_dir / "projects.json"
    legacy_aliases_file = get_aliases_file()

    def _load_legacy_projects() -> dict:
        """Load legacy projects from projects.json or aliases.json."""
        for legacy_path in (legacy_projects_file, legacy_aliases_file):
            if not legacy_path.exists():
                continue
            try:
                with open(legacy_path, encoding="utf-8") as f:
                    data = json.load(f)
                if "aliases" in data and "projects" not in data:
                    data["projects"] = data.pop("aliases")
                if "projects" in data:
                    return data["projects"]
            except (OSError, json.JSONDecodeError):
                continue
        return {}

    if not config_file.exists():
        return {"version": 1, "homes": [], "sources": [], "projects": _load_legacy_projects()}

    try:
        with open(config_file, encoding="utf-8") as f:
            data = json.load(f)
            if "sources" not in data:
                data["sources"] = []
            if "projects" not in data:
                data["projects"] = {}
            if "version" not in data:
                data["version"] = 1
            legacy_projects = _load_legacy_projects()
            if legacy_projects:
                existing = data.get("projects", {})
                for name, cfg in legacy_projects.items():
                    if name not in existing:
                        existing[name] = cfg
                data["projects"] = existing
            # Normalize homes vs sources (use homes as canonical, keep sources for compatibility)
            homes = data.get("homes") or data.get("sources") or []
            data["homes"] = homes
            data["sources"] = homes
            return data
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"Warning: Could not load config file: {e}\n")
        return {"version": 1, "homes": [], "sources": [], "projects": _load_legacy_projects()}


def save_config(data: dict) -> bool:
    """Save config to storage file.

    Args:
        data: Config data dictionary with 'version' and settings

    Returns:
        True on success, False on failure (error printed to stderr)

    Side Effects:
        - Creates ~/.agent-history/ directory with mode 0o700 if missing
        - Writes to ~/.agent-history/config.json with mode 0o600
    """
    config_dir = get_config_dir()
    config_file = get_config_file()

    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        # Set secure permissions on config directory (owner-only access)
        _apply_secure_permissions(config_dir, 0o700)
        if "version" not in data:
            data["version"] = 1
        homes = data.get("homes") or data.get("sources") or []
        data["homes"] = homes
        # Keep sources in sync for backward compatibility
        data["sources"] = homes
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        # Set secure permissions on config file (owner read/write only)
        _apply_secure_permissions(config_file, 0o600)
        return True
    except OSError as e:
        sys.stderr.write(f"Error saving config: {e}\n")
        return False


# =============================================================================
# Home/Source Management
# =============================================================================


def get_saved_sources() -> list:
    """Get list of saved remote sources."""
    config = load_config()
    return config.get("homes") or config.get("sources", [])


def get_saved_homes() -> list:
    """Get list of saved homes (preferred over sources for clarity)."""
    return get_saved_sources()


# =============================================================================
# Project/Alias Management
# =============================================================================


def _sanitize_alias_workspace_entry(workspace: str) -> str:
    """Normalize alias workspace entries, handling legacy absolute paths.

    Note: This function normalizes only absolute path inputs.
    """
    if not workspace:
        return workspace

    lowered = workspace.lower()

    if is_encoded_workspace_name(workspace) or is_cached_workspace(workspace):
        return workspace

    # Handle legacy -mnt-X- encoded format
    if lowered.startswith("-mnt-") and len(workspace) > MNT_ENCODED_PREFIX_LEN:
        drive_letter = workspace[5]
        remainder = workspace[MNT_ENCODED_PREFIX_LEN:]
        if drive_letter.isalpha():
            return f"{drive_letter.upper()}--{remainder}"

    if (
        "/" in workspace
        or "\\" in workspace
        or (len(workspace) > 1 and workspace[1] == ":")
    ):
        return encode_workspace_path(workspace)

    return workspace


def _normalize_aliases(data: dict) -> dict:
    """Normalize stored alias workspace entries for cross-platform compatibility."""
    aliases = data.get("projects", {})
    changed = False

    for sources in aliases.values():
        for source_key, workspaces in list(sources.items()):
            normalized = []
            for workspace in workspaces:
                new_value = _sanitize_alias_workspace_entry(workspace)
                if new_value != workspace:
                    changed = True
                normalized.append(new_value)
            sources[source_key] = normalized

    if changed:
        save_aliases(data)
    return data


def _lock_file(file_handle, exclusive: bool = True):
    """Lock a file handle (cross-platform).

    Args:
        file_handle: Open file handle
        exclusive: True for write lock, False for read lock
    """
    if platform.system() == "Windows":
        import msvcrt

        msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
    else:
        import fcntl

        lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(file_handle.fileno(), lock_type | fcntl.LOCK_NB)


def _unlock_file(file_handle):
    """Unlock a file handle (cross-platform)."""
    if platform.system() == "Windows":
        import msvcrt

        try:
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        except OSError:
            pass
    else:
        import fcntl

        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


def load_aliases() -> dict:
    """Load projects from storage file. Returns empty structure if not found.

    Note: This function is named load_aliases for backward compatibility but
    loads from config.json. It will auto-migrate from legacy aliases/projects files if needed.
    """
    config = load_config()
    projects = config.get("projects", {})
    version = max(config.get("version", 1), 2)
    return _normalize_aliases({"version": version, "projects": projects})


def save_aliases(data: dict) -> bool:
    """Save projects to storage file with file locking.

    Note: This function is named save_aliases for backward compatibility but
    saves to config.json with the new structure.

    Args:
        data: Project data dictionary with 'version' and 'projects' keys

    Returns:
        True on success, False on failure (error printed to stderr)

    Side Effects:
        - Creates ~/.agent-history/ directory with mode 0o700 if missing
        - Writes to ~/.agent-history/projects.json
        - Uses file locking to prevent race conditions
    """
    config_dir = get_config_dir()

    try:
        # Create directory if needed
        config_dir.mkdir(parents=True, exist_ok=True)
        _apply_secure_permissions(config_dir, 0o700)

        # Normalize payload
        if "aliases" in data and "projects" not in data:
            data["projects"] = data.pop("aliases")
        projects = data.get("projects", {})
        version = max(data.get("version", 2), 2)

        # Merge into existing config to preserve other settings
        config = load_config()
        config["projects"] = projects
        config["version"] = max(config.get("version", 1), version)

        return save_config(config)
    except BlockingIOError:
        sys.stderr.write("Error: Projects file is locked by another process\n")
        return False
    except OSError as e:
        sys.stderr.write(f"Error: Could not save projects: {e}\n")
        return False


def get_source_key(remote_host=None, wsl_distro=None, windows_user=None) -> str:
    """Get the source key for aliases based on current context."""
    if remote_host:
        if remote_host.startswith("wsl://"):
            return f"wsl:{remote_host[WSL_PREFIX_LEN:]}"
        elif remote_host.startswith("windows:"):
            return (
                f"windows:{remote_host[WINDOWS_PREFIX_LEN:]}"
                if len(remote_host) > WINDOWS_PREFIX_LEN
                else "windows"
            )
        elif remote_host == "windows":
            return "windows"
        else:
            # Preserve full remote spec (user@host) for SSH authentication
            return f"remote:{remote_host}"
    elif wsl_distro:
        return f"wsl:{wsl_distro}"
    elif windows_user is not None:
        return f"windows:{windows_user}" if windows_user else "windows"
    else:
        return "local"


def get_alias_session_count(alias_name: str, aliases_data: dict) -> int:
    """Count total sessions across all homes for an alias.

    Note: This function requires get_workspace_sessions from the main module.
    When called standalone without that function available, returns 0.
    """
    if alias_name not in aliases_data.get("projects", {}):
        return 0

    # This function depends on get_workspace_sessions which is not in this module.
    # When extracted, it should be updated to import from the appropriate module.
    # For now, we return 0 as a placeholder that maintains the interface.
    return 0


def resolve_alias_workspaces(alias_name: str, source_filter: Optional[str] = None) -> list:
    """
    Resolve an alias to a list of (source_key, workspace) tuples.
    If source_filter is provided, only include matching sources.
    """
    aliases_data = load_aliases()

    if alias_name not in aliases_data.get("projects", {}):
        return []

    alias_config = aliases_data["projects"][alias_name]
    results = []

    for source_key, workspaces in alias_config.items():
        if source_filter and source_key != source_filter:
            continue

        for workspace in workspaces:
            results.append((source_key, workspace))

    return results


def _get_workspace_name_from_path(workspace_dir_name: str) -> str:
    """Extract workspace name from encoded path.

    This is a simplified version for internal use in alias matching.
    The full implementation is in the main module.
    """
    # Simple implementation: return the last segment after splitting by '-'
    # This handles basic cases like '-home-user-project' -> 'project'
    parts = workspace_dir_name.rstrip("-").split("-")
    return parts[-1] if parts else workspace_dir_name


def get_alias_for_workspace(workspace: str, source_key: str = "local") -> Optional[str]:
    """
    Find the alias that contains a given workspace, if any.

    Args:
        workspace: Encoded workspace name (e.g., '-home-user-project')
        source_key: Source identifier like 'local', 'windows', 'wsl:distro', 'remote:hostname'

    Returns:
        Alias name if found, None otherwise
    """

    def _search_aliases(aliases: dict) -> Optional[str]:
        for alias_name, alias_config in aliases.get("projects", {}).items():
            for src_key, workspaces in alias_config.items():
                if (
                    src_key == source_key
                    or source_key.startswith(src_key + ":")
                    or src_key.startswith(source_key + ":")
                ):
                    if workspace in workspaces:
                        return alias_name
                ws_name = _get_workspace_name_from_path(workspace)
                for ws in workspaces:
                    if _get_workspace_name_from_path(ws) == ws_name:
                        return alias_name
        return None

    aliases_data = load_aliases()
    found = _search_aliases(aliases_data)
    return found
