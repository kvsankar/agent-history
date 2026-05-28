"""SSH backend for remote operations.

This module provides functions for executing commands on remote hosts
via SSH and listing remote workspaces/sessions.
"""

import re
import subprocess
from typing import List, Optional, Tuple

from agent_history.backends.registry import get_backend

__all__ = [
    "SSHError",
    "check_ssh_connection",
    "list_remote_sessions",
    "list_remote_workspaces",
    "validate_remote_host",
]


class SSHError(Exception):
    """Exception raised when SSH operation fails."""

    def __init__(self, message: str, host: str, returncode: int = 1):
        self.message = message
        self.host = host
        self.returncode = returncode
        super().__init__(message)


def validate_remote_host(remote_host: Optional[str]) -> bool:
    """Validate remote host specification for security.

    Prevents command injection by ensuring the remote host matches
    expected patterns (user@host or just host).

    Args:
        remote_host: Remote host specification to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not remote_host:
        return False

    # Allow alphanumeric, dots, hyphens, underscores in hostname
    # Allow alphanumeric, hyphens, underscores in username
    # Format: user@host or just host
    pattern = r"^([a-zA-Z0-9_-]+@)?[a-zA-Z0-9._-]+$"
    return bool(re.match(pattern, remote_host))


def check_ssh_connection(remote_host: str) -> Tuple[bool, str]:
    """Check if passwordless SSH connection is possible.

    Args:
        remote_host: Full remote spec (user@hostname or hostname)

    Returns:
        Tuple of (success, error_message).
        If success is True, error_message is empty.
        If success is False, error_message contains the reason.
    """
    if not validate_remote_host(remote_host):
        return False, f"Invalid remote host specification: {remote_host}"

    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=5",
                "-o",
                "StrictHostKeyChecking=accept-new",
                remote_host,
                "echo ok",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout.strip() == "ok":
            return True, ""

        # Parse error message
        stderr = result.stderr.strip()
        if "Connection refused" in stderr:
            return False, f"Connection refused by {remote_host}"
        elif "No route to host" in stderr or "Name or service not known" in stderr:
            return False, f"Host not found: {remote_host}"
        elif "Permission denied" in stderr:
            return False, f"Permission denied for {remote_host}"
        else:
            return False, f"SSH connection failed: {stderr or 'unknown error'}"

    except subprocess.TimeoutExpired:
        return False, f"SSH connection timed out for {remote_host}"
    except FileNotFoundError:
        return False, "SSH command not found"
    except Exception as e:
        return False, f"SSH error: {e}"


def _run_remote_command(remote_host: str, cmd: str) -> tuple[str, str | None]:
    try:
        result = subprocess.run(
            ["ssh", remote_host, cmd],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "", f"SSH command timed out for {remote_host}"
    except Exception as e:
        return "", f"SSH error: {e}"

    if result.returncode != 0:
        return "", None
    return result.stdout, None


def _default_parse_remote_workspaces(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def list_remote_workspaces(
    remote_host: str, agent: str = "claude"
) -> Tuple[List[str], Optional[str]]:
    """List workspace directories on remote host.

    Args:
        remote_host: Remote host specification (user@host).
        agent: Registered agent backend id.

    Returns:
        Tuple of (workspaces, error_message).
        If successful, workspaces is a list of workspace names and error_message is None.
        If failed, workspaces is empty and error_message contains the reason.
    """
    if not validate_remote_host(remote_host):
        return [], f"Invalid remote host specification: {remote_host}"

    # First check SSH connection
    connected, error = check_ssh_connection(remote_host)
    if not connected:
        return [], error

    backend = get_backend(agent)
    if backend is None or backend.remote_list_workspaces_command is None:
        return [], f"Remote workspace listing not implemented for {agent}"

    stdout, error = _run_remote_command(remote_host, backend.remote_list_workspaces_command())
    if error:
        return [], error

    parser = backend.remote_parse_workspaces or _default_parse_remote_workspaces
    return parser(stdout), None


def _parse_remote_sessions(output: str, remote_host: str, workspace: str, agent: str) -> list[dict]:
    sessions = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.strip().split("|")
        if len(parts) < 4:
            continue
        entry = {
            "file": parts[0],
            "remote_path": parts[0],
            "filename": parts[0].rsplit("/", 1)[-1],
            "size": int(parts[1]) if parts[1].isdigit() else 0,
            "mtime": int(parts[2]) if parts[2].isdigit() else 0,
            "message_count": int(parts[3]) if parts[3].isdigit() else 0,
            "agent": agent,
            "workspace": workspace,
            "home": f"remote:{remote_host}",
        }
        if len(parts) >= 5 and parts[4]:
            entry["workspace"] = parts[4]
        sessions.append(entry)
    return sessions


def list_remote_sessions(
    remote_host: str, workspace: str, agent: str = "claude"
) -> Tuple[List[dict], Optional[str]]:
    """List sessions for a workspace on remote host.

    Args:
        remote_host: Remote host specification (user@host).
        workspace: Workspace directory name (encoded).
        agent: Registered agent backend id.

    Returns:
        Tuple of (sessions, error_message).
        If successful, sessions is a list of session dicts.
        If failed, sessions is empty and error_message contains the reason.
    """
    if not validate_remote_host(remote_host):
        return [], f"Invalid remote host specification: {remote_host}"

    backend = get_backend(agent)
    if backend is None or backend.remote_list_sessions_command is None:
        return [], f"Remote session listing not implemented for {agent}"

    stdout, error = _run_remote_command(
        remote_host, backend.remote_list_sessions_command(workspace)
    )
    if error:
        return [], error
    return _parse_remote_sessions(stdout, remote_host, workspace, agent), None
