"""Path utility functions for workspace path encoding/decoding.

This module handles conversion between filesystem paths and Claude Code's
dash-encoded workspace directory names. It supports Windows, Unix, and WSL paths.

Claude Code encodes workspace paths by replacing '/' with '-'. For example:
    /home/user/my-project -> -home-user-my-project
    C:\\Users\\alice\\project -> C--Users-alice-project

The decoding process can optionally verify against the filesystem to correctly
handle directory names that contain dashes (e.g., 'my-project').
"""

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

__all__ = [
    # Constants
    "MIN_WINDOWS_PATH_LEN",
    "MIN_ENCODED_PATH_LEN",
    "REMOTE_PARTS_WITH_PATH",
    "MAX_SHORT_PART_LEN",
    "CACHED_REMOTE_PREFIX",
    "CACHED_WSL_PREFIX",
    "CACHED_WINDOWS_PREFIX",
    "CACHED_PREFIXES",
    # Public functions
    "is_cached_workspace",
    "is_native_workspace",
    "normalize_workspace_name",
    "get_folder_short_name",
    "get_current_workspace_pattern",
    "get_workspace_name_from_path",
    "convert_windows_path_to_encoded",
]

# ============================================================================
# Named Constants
# ============================================================================

# Path parsing constants with explicit derivation
MIN_WINDOWS_PATH_LEN = len("C:")  # Minimum for "C:" style paths
MIN_ENCODED_PATH_LEN = len("C--")  # Minimum for Windows encoded paths

# Remote/WSL parsing constants
REMOTE_PARTS_WITH_PATH = 3  # Parts in "remote_hostname_path" after split

# Display constants
MAX_SHORT_PART_LEN = 10  # Max length for "short" path component heuristic

# Cached workspace prefixes
CACHED_REMOTE_PREFIX = "remote_"
CACHED_WSL_PREFIX = "wsl_"
CACHED_WINDOWS_PREFIX = "windows_"
# Tuple for efficient membership testing
CACHED_PREFIXES = (CACHED_REMOTE_PREFIX, CACHED_WSL_PREFIX, CACHED_WINDOWS_PREFIX)


# ============================================================================
# Workspace Type Detection
# ============================================================================


def is_cached_workspace(name: str) -> bool:
    """Check if a workspace/directory name is a cached remote, WSL, or Windows workspace.

    Cached workspaces are created when fetching from remote SSH hosts, WSL
    distributions, or Windows (from WSL). They have prefixes like:
    - 'remote_hostname_...'
    - 'wsl_distro_...'
    - 'windows_username_...'

    Args:
        name: Workspace or directory name to check

    Returns:
        True if this is a cached workspace, False otherwise.
    """
    return any(name.startswith(prefix) for prefix in CACHED_PREFIXES)


def is_native_workspace(name: str) -> bool:
    """Check if a workspace/directory name is a native (non-cached) workspace.

    This is the inverse of is_cached_workspace().

    Args:
        name: Workspace or directory name to check

    Returns:
        True if this is a native workspace, False if cached.
    """
    return not is_cached_workspace(name)


# ============================================================================
# Internal Helper Functions
# ============================================================================


def _is_windows_encoded_path(name: str) -> bool:
    """Check if name is a Windows-style encoded path (e.g., 'C--path-to-dir')."""
    # Must be at least 3 chars, start with drive letter (A-Z), followed by "--"
    return len(name) >= MIN_ENCODED_PATH_LEN and name[0].isalpha() and name[1:3] == "--"


def _build_current_path(base_path: Path, segments: list[str]) -> Path:
    """Build current path from base and accumulated segments.

    Args:
        base_path: Base path
        segments: List of path segments

    Returns:
        Combined path
    """
    return base_path / "/".join(segments) if segments else base_path


def _find_longest_matching_segment(
    parts: list[str],
    start_idx: int,
    current_path: Path,
    unc_mode: bool,
) -> tuple[Optional[str], int]:
    """Find longest matching segment starting at start_idx.

    Args:
        parts: List of dash-split path components
        start_idx: Starting index in parts
        current_path: Current filesystem path
        unc_mode: Whether in UNC path mode (skip is_dir check)

    Returns:
        Tuple of (matched_segment, parts_consumed) or (None, 0) if no match
    """
    for end_idx in range(len(parts), start_idx, -1):
        candidate = "-".join(parts[start_idx:end_idx])
        candidate_path = current_path / candidate

        try:
            exists = candidate_path.exists()
            is_dir = candidate_path.is_dir() if not unc_mode else True

            if exists and is_dir:
                return candidate, end_idx - start_idx
        except OSError:
            continue

    return None, 0


def _resolve_path_segments(parts: list[str], base_path: Path) -> list[str]:
    """Resolve dash-separated parts to actual filesystem path segments.

    Tries progressively longer combinations of parts to handle directory
    names that contain dashes (e.g., 'my-project' encoded as 'my-project').

    When a path segment doesn't exist but the parent does, remaining parts
    are joined with dashes to preserve potential dashed folder names.

    Args:
        parts: List of dash-split path components
        base_path: Base path to verify against filesystem

    Returns:
        List of resolved path segments
    """
    path_segments: list[str] = []
    i = 0
    unc_mode = _is_wsl_unc_path(base_path)

    while i < len(parts):
        current_path = _build_current_path(base_path, path_segments)

        match, consumed = _find_longest_matching_segment(parts, i, current_path, unc_mode)

        if match:
            path_segments.append(match)
            i += consumed
        else:
            # No filesystem match found - check if this is a non-existent leaf
            # If the current path exists (parent found) but the next segment doesn't,
            # join all remaining parts as a single dashed segment (preserves folder names with dashes)
            try:
                parent_exists = current_path.exists() and current_path.is_dir()
            except OSError:
                parent_exists = False

            if parent_exists and i < len(parts) and len(path_segments) > 1:
                # Parent exists (deeper than root), join remaining parts as a single leaf segment
                remaining = "-".join(parts[i:])
                path_segments.append(remaining)
                break
            else:
                # No parent context, use single part as-is
                path_segments.append(parts[i])
                i += 1

    return path_segments


def _generate_merge_segments(parts: list, mask: int) -> list:
    """Generate segment list from parts based on merge mask."""
    segments = []
    current = parts[0]
    for i in range(1, len(parts)):
        if mask & (1 << (i - 1)):
            current += "-" + parts[i]
        else:
            segments.append(current)
            current = parts[i]
    segments.append(current)
    return segments


def _find_deepest_existing_index(segments: list, base_path: Path) -> int:
    """Find the deepest index where the path exists under base_path."""
    deepest = -1
    probe = base_path
    for idx, seg in enumerate(segments):
        probe = probe.joinpath(seg)
        try:
            if probe.exists():
                deepest = idx
            else:
                break
        except OSError:
            break
    return deepest


def _get_fallback_from_base(base_path: Path, parts: list) -> tuple:
    """Return first child dir as fallback, or original parts if nothing found."""
    try:
        existing = [
            child.name
            for child in base_path.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        ]
        if existing:
            return [existing[0]], False
    except OSError:
        pass
    return parts, False


def _resolve_existing_wsl_path(parts: list, base_path: Path) -> tuple:
    """Try all segment merges to find the deepest existing path under base_path.

    This is used for UNC WSL paths on Windows where directory names may contain
    dashes that were split into separate parts. Returns the best-matching
    segment list (trimmed to the deepest existing prefix). If nothing exists,
    returns the original parts and a False flag.
    """
    if not base_path or not parts:
        return parts, False

    best_segments = None
    best_depth = -1
    best_full_segments = None
    n = len(parts)

    for mask in range(1 << (n - 1)):
        segments = _generate_merge_segments(parts, mask)
        deepest = _find_deepest_existing_index(segments, base_path)

        # Decide whether to update best result
        should_update = deepest > best_depth
        if best_segments is not None and deepest == best_depth:
            should_update = len(segments) < len(best_segments)

        if should_update:
            best_depth = deepest
            best_segments = segments[: deepest + 1] if deepest >= 0 else None
            if deepest == len(segments) - 1:
                best_full_segments = segments

        # Track best full match
        if deepest == len(segments) - 1:
            if best_full_segments is None or len(segments) < len(best_full_segments):
                best_full_segments = segments

    if best_full_segments is not None:
        return best_full_segments, True
    if best_segments is not None:
        return best_segments, False

    return _get_fallback_from_base(base_path, parts)


def _normalize_windows_path(workspace_dir_name: str, verify_local: bool) -> str:
    """Normalize a Windows-style encoded path (e.g., 'C--Users-alice-projects').

    Args:
        workspace_dir_name: Encoded name starting with drive letter and '--'
        verify_local: If True, verify against /mnt/<drive>/ filesystem

    Returns:
        Decoded path (e.g., 'C:\\Users\\alice\\projects' on Windows, '/mnt/c/...' on WSL)
    """
    drive_letter = workspace_dir_name[0].upper()
    rest = workspace_dir_name[3:]  # Skip 'C--'
    parts = rest.split("-")

    # On Windows, return a native drive path
    if sys.platform == "win32":
        drive_root = Path(f"{drive_letter}:\\")
        if verify_local:
            resolved = _resolve_path_segments(parts, drive_root)
            return str(drive_root.joinpath(*resolved))
        else:
            # Without verification, just join with backslashes
            return f"{drive_letter}:\\" + "\\".join(parts)

    # On WSL, prefer /mnt/<drive> if available
    if verify_local:
        mnt_base = Path(f"/mnt/{drive_letter.lower()}")
        if mnt_base.exists():
            path_segments = _resolve_path_segments(parts, mnt_base)
            if path_segments:
                # Return a WSL-usable path: /mnt/<drive>/<segments>
                return "/mnt/" + drive_letter.lower() + "/" + "/".join(path_segments)

    # Fallback: POSIX-style drive path
    return f"/{drive_letter}/" + rest.replace("-", "/")


def _format_unc_path(base_path: Path, readable_path: str) -> str:
    """Format a UNC path string from a base and POSIX-readable path."""
    base_str = str(base_path)
    if base_str.startswith("//"):
        base_str = "\\" + base_str.lstrip("/")
    if not base_str.startswith("\\\\"):
        base_str = "\\\\" + base_str.lstrip("\\")
    base_str = base_str.replace("/", "\\").rstrip("\\")
    suffix = readable_path.lstrip("/")
    if suffix:
        suffix = suffix.replace("/", "\\")
        return f"{base_str}\\{suffix}"
    return base_str


def _is_wsl_unc_path(path: Path | None) -> bool:
    """Check if path is a WSL UNC path (e.g., \\\\wsl.localhost\\Ubuntu)."""
    if not path:
        return False
    base_str = str(path)
    # Normalize extended UNC (\\?\UNC\wsl.localhost\...) to standard UNC
    if base_str.startswith("\\\\?\\UNC\\"):
        base_str = "\\\\" + base_str[8:]
    return (
        base_str.startswith("\\\\wsl.localhost\\")
        or base_str.startswith("\\\\wsl$\\")
        or base_str.startswith("//wsl.localhost/")
        or base_str.startswith("//wsl$/")
    )


def _normalize_unix_path(encoded: str, verify_local: bool, base_path: Optional[Path] = None) -> str:
    """Normalize a Unix-style encoded path (e.g., 'home-user-my-project').

    Args:
        encoded: Encoded path without leading dash
        verify_local: If True, verify against filesystem
        base_path: Base path for verification (e.g., //wsl.localhost/Ubuntu)

    Returns:
        Decoded path (e.g., '/home/user/my-project')
    """
    parts = encoded.split("-")

    if base_path and (_is_wsl_unc_path(base_path) or sys.platform == "win32"):
        resolved_segments, found_full = _resolve_existing_wsl_path(parts, Path(base_path))
        segments = list(resolved_segments) if resolved_segments else list(parts)
        if not found_full and len(segments) < len(parts):
            segments.append("-".join(parts[len(segments) :]))
        readable_path = "/" + "/".join(segments)
        marker = "" if found_full else " [missing]"
        base_str = str(base_path)
        if base_str.startswith("/") and not base_str.startswith("//"):
            return readable_path + marker
        return _format_unc_path(base_path, readable_path) + marker

    if not verify_local:
        return "/" + encoded.replace("-", "/")

    # Use AGENT_HISTORY_HOME as base for filesystem probing if set (for testing)
    # This allows verifying paths against a mock filesystem
    agent_home = os.environ.get("AGENT_HISTORY_HOME")
    if agent_home and not base_path:
        effective_base = Path(agent_home)
    else:
        effective_base = base_path if base_path else Path("/")
    path_segments = _resolve_path_segments(parts, effective_base)

    # path_segments now contains the best resolution based on filesystem probing
    # If no directories matched, each part becomes a separate segment (correct behavior)

    path_segments, partial_marker = _apply_windows_base_resolution(parts, base_path, path_segments)

    readable_path = "/" + "/".join(path_segments)
    return readable_path + partial_marker


def _apply_windows_base_resolution(
    parts: list[str], base_path: Optional[Path], current_segments: list[str]
):
    """Handle Windows base paths when normalizing Unix-style encodings."""
    if not base_path or sys.platform != "win32":
        return current_segments, ""

    resolved_segments, found_full = _resolve_existing_wsl_path(parts, Path(base_path))
    if not resolved_segments:
        return current_segments, ""

    combined_segments = list(resolved_segments)
    if not found_full and len(resolved_segments) < len(parts):
        combined_segments.append("-".join(parts[len(resolved_segments) :]))

    final_path = Path(base_path).joinpath(*combined_segments)
    try:
        full_exists = len(resolved_segments) == len(parts) and final_path.exists()
    except OSError:
        full_exists = False

    if full_exists:
        return combined_segments, ""
    return combined_segments, " [missing]"


# ============================================================================
# Public Path Functions
# ============================================================================


@lru_cache(maxsize=1024)
def _normalize_workspace_name_cached(
    workspace_dir_name: str, verify_local: bool, base_path_str: Optional[str]
) -> str:
    """Cached implementation of normalize_workspace_name.

    This internal function is cached to avoid repeated filesystem operations
    when decoding the same workspace name multiple times.

    Args:
        workspace_dir_name: Encoded workspace name
        verify_local: If True, verify against filesystem
        base_path_str: String representation of base_path (for hashability)

    Returns:
        Decoded path
    """
    base_path = Path(base_path_str) if base_path_str else None

    # Handle Windows-style paths (e.g., 'C--Users-alice-projects-myapp')
    if _is_windows_encoded_path(workspace_dir_name):
        return _normalize_windows_path(workspace_dir_name, verify_local)

    # Remove leading dash for Unix paths
    encoded = workspace_dir_name[1:] if workspace_dir_name.startswith("-") else workspace_dir_name

    return _normalize_unix_path(encoded, verify_local, base_path)


def normalize_workspace_name(
    workspace_dir_name: str, verify_local: bool = True, base_path: Optional[Path] = None
) -> str:
    """Convert workspace directory name to readable path.

    Claude Code encodes workspace paths by replacing '/' with '-'. This function
    reverses that encoding, optionally verifying against the filesystem to
    correctly handle directory names that contain dashes.

    Results are cached to avoid repeated filesystem operations when decoding
    the same workspace name multiple times.

    Set AGENT_HISTORY_SKIP_PATH_VERIFY=1 to skip filesystem verification
    for faster performance (useful in CI/CD or when paths are not important).

    Args:
        workspace_dir_name: Encoded workspace name (e.g., '-home-user-my-project')
        verify_local: If True, verify against local filesystem to handle dashes correctly
        base_path: Base path to prepend when verifying (for WSL: //wsl.localhost/Ubuntu)

    Returns:
        Decoded path (e.g., '/home/user/my-project')
    """
    # Allow skipping verification via environment variable for performance
    if os.environ.get("AGENT_HISTORY_SKIP_PATH_VERIFY", "").lower() in ("1", "true", "yes"):
        verify_local = False

    # Convert base_path to string for cache key (Path is unhashable)
    base_path_str = str(base_path) if base_path else None
    return _normalize_workspace_name_cached(workspace_dir_name, verify_local, base_path_str)


def get_folder_short_name(workspace: str) -> str:
    """Get convenience short name from workspace directory name or path.

    Takes either an encoded workspace name or a decoded path and returns
    just the final directory name (basename).

    Args:
        workspace: Encoded workspace name (e.g., '-home-alice-projects-foo')
                   or decoded path (e.g., '/home/alice/projects/foo')

    Returns:
        Short name (e.g., 'foo')

    Examples:
        - '-home-alice-projects-foo' -> 'foo'
        - 'C--Users-alice-projects-bar' -> 'bar'
        - '/home/alice/projects/foo' -> 'foo'
        - '-home-alice-projects-foo-feature' -> 'foo-feature'
    """
    if not workspace:
        return workspace

    # If it looks like a decoded path (contains /), just get basename
    if "/" in workspace:
        return Path(workspace).name

    # Otherwise, decode the workspace name first
    decoded = normalize_workspace_name(workspace, verify_local=False)
    return Path(decoded).name


def get_current_workspace_pattern():
    """
    Detect the current workspace based on the current working directory.
    Returns a pattern that can be used to match the workspace directory.
    """
    cwd = Path.cwd()

    # If AGENT_HISTORY_HOME is set and cwd is inside it, strip the prefix so the pattern
    # matches encoded workspace names (which don't include the temp root).
    agent_home = os.environ.get("AGENT_HISTORY_HOME")
    if agent_home:
        try:
            rel = cwd.relative_to(Path(agent_home))
            cwd_str = "/" + str(rel).lstrip("/")
        except ValueError:
            cwd_str = str(cwd)
    else:
        cwd_str = str(cwd)

    # Normalize Windows backslashes to forward slashes before encoding
    cwd_str = cwd_str.replace("\\", "/")

    # Handle Windows paths (C:\path\to\project -> C--path-to-project)
    if sys.platform == "win32" and len(cwd_str) >= MIN_WINDOWS_PATH_LEN and cwd_str[1] == ":":
        # Extract drive letter and path
        drive = cwd_str[0]
        path_part = cwd_str[2:].lstrip("\\").lstrip("/")
        # Convert backslashes and forward slashes to dashes
        path_part = path_part.replace("\\", "-").replace("/", "-")
        workspace_pattern = f"{drive}--{path_part}"
    else:
        # Unix/Linux paths (/home/user/projects/myapp -> home-user-projects-myapp)
        workspace_pattern = cwd_str.lstrip("/").replace("/", "-")

    return workspace_pattern


def get_workspace_name_from_path(workspace_dir_name: str) -> str:
    """
    Extract clean workspace name from directory name.
    Removes source tags and normalizes path.

    Examples:
        'C--Users-alice-projects-myapp' -> 'myapp'
        'remote_server01_home-bob-projects-mylib' -> 'mylib'
        'wsl_ubuntu_home-user-projects-auth' -> 'auth'
    """
    # Remove source tags if present
    if workspace_dir_name.startswith(CACHED_REMOTE_PREFIX):
        # remote_hostname_path -> path
        parts = workspace_dir_name.split("_", 2)
        if len(parts) >= REMOTE_PARTS_WITH_PATH:
            workspace_dir_name = parts[2]
    elif workspace_dir_name.startswith(CACHED_WSL_PREFIX):
        # wsl_distro_path -> path
        parts = workspace_dir_name.split("_", 2)
        if len(parts) >= REMOTE_PARTS_WITH_PATH:
            workspace_dir_name = parts[2]

    # Get the last path component (workspace name)
    # home-alice-projects-myapp -> myapp
    # C--Users-alice-projects-myapp -> myapp
    path_parts = workspace_dir_name.split("-")

    # Find the workspace name (usually last component or last few)
    # Simple heuristic: take last part, or last 2 if hyphenated (e.g., claude-history)
    if len(path_parts) >= MIN_WINDOWS_PATH_LEN:
        # Check if last 2 parts form a common pattern
        last_two = "-".join(path_parts[-2:])
        # If the second-to-last part is short (likely part of name like "claude-history")
        if len(path_parts[-2]) <= MAX_SHORT_PART_LEN:
            return last_two

    return path_parts[-1] if path_parts else workspace_dir_name


def convert_windows_path_to_encoded(path: str) -> str:
    """Convert Windows absolute path (C:\\... or C:/...) to encoded format.

    Args:
        path: Windows path like 'C:\\Users\\alice\\project' or 'C:/Users/alice/project'

    Returns:
        Encoded workspace name like 'C--Users-alice-project'
    """
    drive = path[0].upper()
    rest = path[2:].lstrip("/\\").replace("\\", "/").replace("/", "-")
    return f"{drive}--{rest}"
