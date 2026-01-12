"""SSH backend for remote operations.

This module provides functions for executing commands on remote hosts
via SSH and listing remote workspaces/sessions.
"""

import re
import subprocess
import sys
from typing import List, Optional, Tuple

__all__ = [
    "validate_remote_host",
    "check_ssh_connection",
    "list_remote_workspaces",
    "SSHError",
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
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=accept-new",
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


def list_remote_workspaces(remote_host: str, agent: str = "claude") -> Tuple[List[str], Optional[str]]:
    """List workspace directories on remote host.

    Args:
        remote_host: Remote host specification (user@host).
        agent: Agent type ("claude", "codex", or "gemini").

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

    # Determine the command based on agent type
    if agent == "claude":
        # List all directories in ~/.claude/projects/
        # We'll filter for workspace names (starting with -) in Python
        cmd = 'ls -1 ~/.claude/projects/ 2>/dev/null || true'
    elif agent == "codex":
        # Codex uses date-based directory structure
        cmd = '''for f in ~/.codex/sessions/*/*/*/*.jsonl; do
            [ -f "$f" ] || continue
            line=$(grep -m1 '"cwd"' "$f" | head -1)
            echo "$line" | sed 's/.*"cwd":"\\([^"]*\\)".*/\\1/'
        done | sort -u'''
    elif agent == "gemini":
        # Gemini uses hash directories under ~/.gemini/tmp
        cmd = 'ls -1 ~/.gemini/tmp 2>/dev/null || true'
    else:
        return [], f"Unknown agent type: {agent}"

    try:
        result = subprocess.run(
            ["ssh", remote_host, cmd],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            # Empty result is not an error - just no workspaces
            return [], None

        # Parse output - one item per line
        items = [
            line.strip() for line in result.stdout.strip().split("\n")
            if line.strip()
        ]

        if agent == "claude":
            # Filter for workspace directories (start with -) and exclude remote caches
            workspaces = [
                ws for ws in items
                if ws.startswith("-")  # Encoded workspace names start with -
                and not ws.startswith("remote_") and not ws.startswith("wsl_")
            ]
            return workspaces, None

        return items, None

    except subprocess.TimeoutExpired:
        return [], f"SSH command timed out for {remote_host}"
    except Exception as e:
        return [], f"SSH error: {e}"


def list_remote_sessions(
    remote_host: str,
    workspace: str,
    agent: str = "claude"
) -> Tuple[List[dict], Optional[str]]:
    """List sessions for a workspace on remote host.

    Args:
        remote_host: Remote host specification (user@host).
        workspace: Workspace directory name (encoded).
        agent: Agent type ("claude", "codex", or "gemini").

    Returns:
        Tuple of (sessions, error_message).
        If successful, sessions is a list of session dicts.
        If failed, sessions is empty and error_message contains the reason.
    """
    if not validate_remote_host(remote_host):
        return [], f"Invalid remote host specification: {remote_host}"

    # Sanitize workspace name
    safe_workspace = workspace.replace("'", "'\\''")

    if agent == "claude":
        cmd = f'''cd ~/.claude/projects/'{safe_workspace}' 2>/dev/null && \
for f in *.jsonl; do
    [ -f "$f" ] || continue
    size=$(stat -c %s "$f" 2>/dev/null || stat -f %z "$f" 2>/dev/null)
    mtime=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null)
    lines=$(wc -l < "$f")
    echo "$f|$size|$mtime|$lines"
done'''
    elif agent == "codex":
        cmd = f'''ws='{safe_workspace}'
for f in ~/.codex/sessions/*/*/*/*.jsonl; do
    [ -f "$f" ] || continue
    line=$(grep -m1 '"cwd"' "$f" | head -1)
    cwd=$(echo "$line" | sed 's/.*"cwd":"\\([^"]*\\)".*/\\1/')
    if [ -n "$cwd" ] && [ "$cwd" = "$ws" ]; then
        size=$(stat -c %s "$f" 2>/dev/null || stat -f %z "$f" 2>/dev/null)
        mtime=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null)
        lines=$(wc -l < "$f")
        echo "$f|$size|$mtime|$lines|$cwd"
    fi
done'''
    elif agent == "gemini":
        cmd = f'''for f in ~/.gemini/tmp/'{safe_workspace}'/chats/*.json; do
    [ -f "$f" ] || continue
    size=$(stat -c %s "$f" 2>/dev/null || stat -f %z "$f" 2>/dev/null)
    mtime=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null)
    lines=$(wc -l < "$f")
    echo "$f|$size|$mtime|$lines"
done'''
    else:
        return [], f"Remote session listing not implemented for {agent}"

    try:
        result = subprocess.run(
            ["ssh", remote_host, cmd],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return [], None

        sessions = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.strip().split("|")
            if len(parts) >= 4:
                entry = {
                    "file": parts[0],
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

        return sessions, None

    except subprocess.TimeoutExpired:
        return [], f"SSH command timed out for {remote_host}"
    except Exception as e:
        return [], f"SSH error: {e}"
