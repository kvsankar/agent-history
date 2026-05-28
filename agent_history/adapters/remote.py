"""Remote client adapters for SSH-based session access."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_history.backends import ssh as ssh_backend
from agent_history.backends.registry import get_backend
from agent_history.storage.config import get_config_dir


class RemoteClientError(RuntimeError):
    """Raised when remote operations fail."""


@dataclass
class RemoteFetchResult:
    fetched: int
    skipped: int
    errors: int


class SSHRemoteClient:
    """Remote client backed by SSH commands."""

    def list_workspaces(self, remote_host: str, agent: str = "claude") -> list[str]:
        workspaces, error = ssh_backend.list_remote_workspaces(remote_host, agent=agent)
        if error:
            raise RemoteClientError(error)
        return workspaces

    def list_sessions(
        self, remote_host: str, workspace: str, agent: str = "claude"
    ) -> list[dict[str, Any]]:
        sessions, error = ssh_backend.list_remote_sessions(remote_host, workspace, agent=agent)
        if error:
            raise RemoteClientError(error)

        backend = get_backend(agent)
        if backend and backend.remote_workspace_readable:
            readable_ws = backend.remote_workspace_readable(workspace)
        else:
            readable_ws = workspace
        normalized: list[dict[str, Any]] = []
        remote_filenames: set[str] = set()
        cache_dir = _remote_cache_dir(remote_host, agent, workspace)

        for session in sessions:
            file_value = session.get("file") or session.get("filename")
            if not file_value:
                continue
            file_path = Path(str(file_value))
            filename = session.get("filename") or file_path.name

            entry = dict(session)
            entry["filename"] = filename
            entry["workspace"] = workspace
            entry["workspace_readable"] = readable_ws
            entry.setdefault("agent", agent)
            entry["remote_path"] = entry.get("remote_path") or str(file_path)

            if file_path.is_absolute() and file_path.exists():
                entry["file"] = file_path
            else:
                entry["file"] = file_path
                remote_path = None
                if backend and backend.remote_file_path:
                    remote_path = backend.remote_file_path(workspace, filename, entry)
                entry["remote_path"] = remote_path or str(file_path)

            mtime = session.get("mtime")
            if isinstance(mtime, (int, float)):
                entry["modified"] = datetime.fromtimestamp(mtime)

            remote_filenames.add(filename)
            try:
                local_copy = self.ensure_local_copy(remote_host, workspace, entry)
                if local_copy:
                    entry["file"] = local_copy
            except RemoteClientError:
                pass

            normalized.append(entry)

        _purge_missing_cache_files(cache_dir, remote_filenames)

        return normalized

    def ensure_local_copy(
        self, remote_host: str, workspace: str, session: dict[str, Any]
    ) -> Path | None:
        """Ensure a remote session file is cached locally.

        Returns the local cached path if available, otherwise None.
        """
        file_value = session.get("file")
        if file_value:
            file_path = Path(str(file_value))
            if file_path.exists():
                return file_path

        filename = session.get("filename")
        if not filename:
            return None

        if not ssh_backend.validate_remote_host(remote_host):
            raise RemoteClientError(f"Invalid remote host: {remote_host}")

        if not _is_safe_component(filename):
            raise RemoteClientError("Unsafe remote filename")

        agent = session.get("agent", "claude")
        workspace_value = session.get("workspace") or workspace
        cache_dir = _remote_cache_dir(remote_host, agent, workspace_value)
        cache_dir.mkdir(parents=True, exist_ok=True)
        dest = cache_dir / filename
        remote_mtime = session.get("mtime")
        if dest.exists():
            if isinstance(remote_mtime, (int, float)):
                local_mtime = dest.stat().st_mtime
                if local_mtime >= float(remote_mtime):
                    return dest
            else:
                return dest

        remote_path = session.get("remote_path")
        if not remote_path:
            backend = get_backend(agent)
            if backend and backend.remote_file_path:
                remote_path = backend.remote_file_path(workspace_value, filename, session)
            else:
                remote_path = str(file_value)
        if ".." in remote_path:
            raise RemoteClientError("Unsafe remote path")

        cmd = [
            "ssh",
            remote_host,
            "sh",
            "-c",
            f"cat {shlex.quote(remote_path)}",
        ]

        result = subprocess.run(cmd, capture_output=True, check=False)
        if result.returncode != 0:
            return None

        dest.write_bytes(result.stdout)
        if isinstance(remote_mtime, (int, float)):
            try:
                os.utime(dest, (float(remote_mtime), float(remote_mtime)))
            except OSError:
                pass
        return dest

    def fetch_all(self, remote_host: str, workspaces: list[str]) -> RemoteFetchResult:
        fetched = 0
        skipped = 0
        errors = 0

        for workspace in workspaces:
            try:
                sessions = self.list_sessions(remote_host, workspace, agent="claude")
            except RemoteClientError:
                errors += 1
                continue

            for session in sessions:
                try:
                    local = self.ensure_local_copy(remote_host, workspace, session)
                    if local:
                        fetched += 1
                    else:
                        errors += 1
                except RemoteClientError:
                    errors += 1

        return RemoteFetchResult(fetched=fetched, skipped=skipped, errors=errors)


def _remote_cache_dir(remote_host: str, agent: str, workspace: str) -> Path:
    safe_host = re.sub(r"[^A-Za-z0-9._-]", "_", remote_host)
    safe_ws = _safe_cache_component(workspace)
    return get_config_dir() / "remote-cache" / safe_host / agent / safe_ws


def _safe_cache_component(value: str) -> str:
    cleaned = value.strip().replace("\\", "/").strip("/")
    cleaned = cleaned.replace("/", "-")
    return re.sub(r"[^A-Za-z0-9._-]", "_", cleaned)


def _is_safe_component(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9._-]+$", value))


def _purge_missing_cache_files(cache_dir: Path, keep_files: set[str]) -> None:
    """Remove cached files that no longer exist on the remote."""
    if not cache_dir.exists():
        return

    for entry in cache_dir.iterdir():
        if entry.is_file() and entry.name not in keep_files:
            try:
                entry.unlink()
            except OSError:
                continue

    try:
        if not any(cache_dir.iterdir()):
            cache_dir.rmdir()
    except OSError:
        pass
