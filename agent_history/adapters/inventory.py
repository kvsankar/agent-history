"""Inventory provider for session and workspace discovery."""

from __future__ import annotations

import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_history.adapters.remote import RemoteClientError, SSHRemoteClient
from agent_history.backends.registry import AgentBackend, get_default_backend_id, iter_backends
from agent_history.scope.context import ResolutionContext
from agent_history.scope.home_resolver import get_resolver_for_home
from agent_history.utils.env import get_env, has_env
from agent_history.utils.paths import normalize_workspace_name
from agent_history.utils.platform import AGENT_CLAUDE
from agent_history.utils.workspace_ref import apply_workspace_ref, build_workspace_ref


class InventoryProvider:
    """Collect session and workspace inventory across homes and agents."""

    def __init__(self, context: ResolutionContext, remote_client: SSHRemoteClient | None = None):
        self.context = context
        self.remote_client = remote_client or SSHRemoteClient()

    def list_sessions(
        self, home: str, agent: str | None = None, workspace: str | None = None
    ) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []

        # In test mode, skip remote probing to avoid slow SSH lookups.
        test_mode = has_env("CAGELENS_TEST_MODE", "AGENT_HISTORY_TEST_MODE")
        if home.startswith("remote:") and test_mode:
            return sessions

        if home == "web":
            return self._list_web_sessions(agent)

        for backend in iter_backends(agent):
            sessions.extend(self._list_backend_sessions(home, backend, workspace=workspace))

        for session in sessions:
            apply_workspace_ref(session)

        return sessions

    def list_workspaces(self, home: str, agent: str | None = None) -> list[str]:
        workspaces: set[str] = set()

        # Avoid remote SSH probing in test mode.
        test_mode = has_env("CAGELENS_TEST_MODE", "AGENT_HISTORY_TEST_MODE")
        if home.startswith("remote:") and test_mode:
            return []

        if home == "web":
            return self._list_web_workspaces()

        for backend in iter_backends(agent):
            workspaces.update(self._list_backend_workspaces(home, backend))

        return sorted(workspaces)

    def list_workspace_summaries(self, home: str, agent: str | None = None) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for backend in iter_backends(agent):
            if home.startswith("remote:"):
                summaries.extend(self._list_remote_workspace_summaries(home, backend))
            else:
                summaries.extend(self._list_local_workspace_summaries(home, backend))
        return _merge_workspace_summaries(home, summaries)

    def _list_backend_sessions(
        self, home: str, backend: AgentBackend, workspace: str | None = None
    ) -> list[dict[str, Any]]:
        if home.startswith("remote:"):
            return self._list_remote_backend_sessions(home, backend, workspace=workspace)

        resolver = get_resolver_for_home(home)
        sessions_dir = backend.get_session_dir(resolver, self.context)
        if not sessions_dir or not sessions_dir.exists():
            return []

        if workspace:
            if backend.id == "claude":
                from agent_history.backends.claude import get_workspace_sessions
                from agent_history.utils.paths import encode_workspace_path

                sessions = get_workspace_sessions(
                    workspace_pattern=workspace,
                    projects_dir=sessions_dir,
                    skip_message_count=True,
                )
                encoded_workspace = encode_workspace_path(workspace)
                for session in sessions:
                    if session.get("workspace") == encoded_workspace:
                        session["workspace_readable"] = workspace
                return sessions
            if backend.id == "codex":
                from agent_history.backends.codex import codex_scan_sessions

                return codex_scan_sessions(
                    pattern=workspace,
                    sessions_dir=sessions_dir,
                    skip_message_count=True,
                )

        sessions = backend.scan_sessions(sessions_dir)
        if workspace:
            sessions = [
                session
                for session in sessions
                if (
                    session.get("workspace_key") == workspace
                    or session.get("workspace_readable") == workspace
                    or session.get("workspace") == workspace
                )
            ]
        return sessions

    def _list_local_workspace_summaries(
        self, home: str, backend: AgentBackend
    ) -> list[dict[str, Any]]:
        resolver = get_resolver_for_home(home)
        sessions_dir = backend.get_session_dir(resolver, self.context)
        if not sessions_dir or not sessions_dir.exists():
            return []

        if backend.id == "claude":
            return _summarize_claude_projects_dir(home, sessions_dir)
        if backend.id == "codex":
            return _summarize_codex_sessions_dir(home, sessions_dir)

        return _summarize_scanned_sessions(home, backend.scan_sessions(sessions_dir))

    def _list_backend_workspaces(self, home: str, backend: AgentBackend) -> list[str]:
        if home.startswith("remote:"):
            remote_host = home[7:]
            try:
                workspaces = self.remote_client.list_workspaces(remote_host, agent=backend.id)
            except Exception:
                return []
            if backend.id == "gemini":
                return workspaces
            return [normalize_workspace_name(ws, verify_local=False) for ws in workspaces]

        resolver = get_resolver_for_home(home)
        sessions_dir = backend.get_session_dir(resolver, self.context)
        if not sessions_dir or not sessions_dir.exists():
            return []

        return backend.list_workspaces(sessions_dir, home)

    def _list_remote_backend_sessions(
        self, home: str, backend: AgentBackend, workspace: str | None = None
    ) -> list[dict[str, Any]]:
        remote_host = home[7:]
        sessions: list[dict[str, Any]] = []

        if workspace:
            try:
                return self.remote_client.list_sessions(remote_host, workspace, agent=backend.id)
            except RemoteClientError:
                return sessions

        try:
            workspaces = self.remote_client.list_workspaces(remote_host, agent=backend.id)
        except Exception:
            return sessions

        for remote_workspace in workspaces:
            try:
                sessions.extend(
                    self.remote_client.list_sessions(
                        remote_host, remote_workspace, agent=backend.id
                    )
                )
            except RemoteClientError:
                continue

        return sessions

    def _list_remote_workspace_summaries(
        self, home: str, backend: AgentBackend
    ) -> list[dict[str, Any]]:
        remote_host = home[7:]
        try:
            return _run_remote_summary_command(remote_host, backend.id)
        except Exception:
            return []

    def _list_web_sessions(self, agent: str | None) -> list[dict[str, Any]]:
        if agent not in (None, AGENT_CLAUDE):
            return []

        from agent_history.backends.web import (
            WebSessionsError,
            build_github_to_workspace_map,
            fetch_web_sessions,
            get_web_cache_dir,
            get_web_session_workspace,
            resolve_web_credentials,
        )

        try:
            token, org_uuid = resolve_web_credentials()
            sessions = fetch_web_sessions(token, org_uuid)
        except WebSessionsError:
            return []

        github_map = build_github_to_workspace_map(self.context.claude_projects_dir)
        cache_dir = get_web_cache_dir()

        normalized: list[dict[str, Any]] = []
        for session in sessions:
            session_id = session.get("uuid") or session.get("id")
            if not session_id:
                continue

            workspace = get_web_session_workspace(session, github_map) or f"session:{session_id}"
            created_raw = session.get("updated_at") or session.get("created_at")
            if not created_raw:
                created_raw = session.get("updatedAt") or session.get("createdAt")

            modified = None
            if created_raw:
                try:
                    modified = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
                except ValueError:
                    modified = None

            msg_count = session.get("message_count")
            if msg_count is None:
                msg_count = session.get("messageCount")

            normalized.append(
                {
                    "id": session_id,
                    "session_id": session_id,
                    "filename": session_id,
                    "file": cache_dir / f"{session_id}.jsonl",
                    "workspace": workspace,
                    "workspace_readable": workspace,
                    "agent": get_default_backend_id(),
                    "home": "web",
                    "modified": modified,
                    "message_count": msg_count if msg_count is not None else 0,
                }
            )

        return normalized

    def _list_web_workspaces(self) -> list[str]:
        sessions = self._list_web_sessions(agent=get_default_backend_id())
        return sorted(
            {(s.get("workspace_readable") or s.get("workspace", "")).strip() for s in sessions if s}
            - {""}
        )


def _summary_record(
    home: str,
    workspace: str,
    count: int,
    modified: datetime | None,
    agent: str,
    readable: str | None = None,
) -> dict[str, Any]:
    display_value = _normalize_summary_workspace(home, readable or workspace)
    ref = build_workspace_ref(display_value)
    return {
        "home": home,
        "workspace": ref.display,
        "workspace_key": ref.key,
        "workspace_display": ref.display,
        "session_count": count,
        "sessions": count,
        "status": _workspace_status(home, ref.display),
        "last_modified": modified or "-",
        "agents": [agent],
    }


def _normalize_summary_workspace(home: str, workspace: str) -> str:
    if home.startswith("windows:") and len(workspace) > 2 and workspace[1:3] in (":/", ":\\"):
        drive = workspace[0].lower()
        rest = workspace[3:].replace("\\", "/").lstrip("/")
        return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"
    return workspace


def _workspace_status(home: str, workspace_display: str) -> str:
    if home.startswith("remote:") or home == "web":
        return "ok"
    if home.startswith("windows:"):
        return "unknown"
    if workspace_display.startswith("[hash:"):
        return "unknown"
    if not workspace_display:
        return "unknown"
    if (
        "/" not in workspace_display
        and "\\" not in workspace_display
        and not (len(workspace_display) > 1 and workspace_display[1] == ":")
    ):
        return "unknown"

    agent_home = get_env("CAGELENS_HOME", "AGENT_HISTORY_HOME")
    check_path = (
        Path(agent_home) / workspace_display.lstrip("/") if agent_home else Path(workspace_display)
    )
    try:
        return "ok" if check_path.exists() else "missing"
    except OSError:
        return "unknown"


def _merge_workspace_summaries(home: str, summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        key = summary.get("workspace_key") or summary.get("workspace")
        if not key:
            continue
        if key not in merged:
            merged[key] = dict(summary)
            merged[key]["agents"] = set(summary.get("agents", []))
            continue
        current = merged[key]
        current["session_count"] += summary.get("session_count", 0)
        current["sessions"] += summary.get("sessions", 0)
        current["agents"].update(summary.get("agents", []))
        if _modified_sort_key(summary.get("last_modified")) > _modified_sort_key(
            current.get("last_modified")
        ):
            current["last_modified"] = summary.get("last_modified")

    rows = list(merged.values())
    for row in rows:
        row["agents"] = sorted(row["agents"])
        if not row.get("last_modified"):
            row["last_modified"] = "-"
        row["home"] = home
    return sorted(rows, key=lambda row: _modified_sort_key(row.get("last_modified")), reverse=True)


def _modified_sort_key(value: Any) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    return 0.0


def _summarize_claude_projects_dir(home: str, projects_dir: Path) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    try:
        workspace_entries = [entry for entry in os.scandir(projects_dir) if entry.is_dir()]
    except OSError:
        return summaries

    verify_local = home == "local"
    use_directory_mtime = home.startswith("windows:")
    for entry in workspace_entries:
        name = entry.name
        if name.startswith(".") or name.startswith(("remote_", "wsl_", "windows_")):
            continue
        count = 0
        latest = 0.0
        try:
            with os.scandir(entry.path) as files:
                for file_entry in files:
                    if not file_entry.name.endswith(".jsonl") or not file_entry.is_file():
                        continue
                    count += 1
                    if use_directory_mtime:
                        continue
                    try:
                        latest = max(latest, file_entry.stat().st_mtime)
                    except OSError:
                        continue
        except OSError:
            continue
        if not count:
            continue
        if use_directory_mtime:
            try:
                latest = entry.stat().st_mtime
            except OSError:
                latest = 0.0
        readable = normalize_workspace_name(name, verify_local=verify_local)
        summaries.append(
            _summary_record(
                home,
                name,
                count,
                datetime.fromtimestamp(latest) if latest else None,
                "claude",
                readable=readable,
            )
        )
    return summaries


def _summarize_codex_sessions_dir(home: str, sessions_dir: Path) -> list[dict[str, Any]]:
    from agent_history.backends.codex import codex_ensure_index_updated

    try:
        sessions_map = codex_ensure_index_updated(sessions_dir)
    except Exception:
        return []

    grouped: dict[str, dict[str, Any]] = {}
    for file_path, workspace in sessions_map.items():
        if not workspace:
            continue
        path = Path(file_path)
        try:
            path.relative_to(sessions_dir)
        except ValueError:
            continue
        if not path.name.startswith("rollout-"):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        item = grouped.setdefault(workspace, {"count": 0, "latest": 0.0})
        item["count"] += 1
        item["latest"] = max(item["latest"], mtime)

    return [
        _summary_record(
            home,
            workspace,
            values["count"],
            datetime.fromtimestamp(values["latest"]) if values["latest"] else None,
            "codex",
            readable=workspace,
        )
        for workspace, values in grouped.items()
        if values["count"]
    ]


def _summarize_scanned_sessions(home: str, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for session in sessions:
        workspace = (
            session.get("workspace_key")
            or session.get("workspace_readable")
            or session.get("workspace")
        )
        agent = session.get("agent") or "unknown"
        if not workspace:
            continue
        item = grouped.setdefault((workspace, agent), {"count": 0, "latest": None})
        item["count"] += 1
        modified = session.get("modified")
        if isinstance(modified, datetime) and (item["latest"] is None or modified > item["latest"]):
            item["latest"] = modified
    return [
        _summary_record(home, workspace, values["count"], values["latest"], agent)
        for (workspace, agent), values in grouped.items()
    ]


def _run_remote_summary_command(remote_host: str, agent: str) -> list[dict[str, Any]]:
    from agent_history.backends.ssh import validate_remote_host

    if not validate_remote_host(remote_host):
        return []
    command = _remote_summary_command(agent)
    if not command:
        return []
    result = subprocess.run(
        ["ssh", remote_host, f"python3 -c {shlex.quote(command)}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        return []
    home = f"remote:{remote_host}"
    summaries: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) < 5:
            continue
        workspace, readable, count_raw, mtime_raw, agent_id = parts[:5]
        try:
            count = int(count_raw)
            mtime = float(mtime_raw)
        except ValueError:
            continue
        if count <= 0:
            continue
        summaries.append(
            _summary_record(
                home,
                workspace,
                count,
                datetime.fromtimestamp(mtime) if mtime else None,
                agent_id,
                readable=readable or workspace,
            )
        )
    return summaries


def _remote_summary_command(agent: str) -> str | None:
    if agent == "claude":
        return r"""
from pathlib import Path
root = Path.home() / ".claude" / "projects"
def resolve_parts(parts, base):
    resolved = []
    current = base
    i = 0
    while i < len(parts):
        match = None
        match_end = i + 1
        for end in range(len(parts), i, -1):
            candidate = "-".join(parts[i:end])
            if (current / candidate).exists():
                match = candidate
                match_end = end
                break
        if match is None:
            resolved.extend(parts[i:])
            break
        resolved.append(match)
        current = current / match
        i = match_end
    return str(base.joinpath(*resolved))
def decode(name):
    if name.startswith("-"):
        return resolve_parts(name[1:].split("-"), Path("/"))
    if len(name) > 2 and name[1:3] == "--":
        return f"/mnt/{name[0].lower()}/" + name[3:].replace("-", "/")
    return name
if root.exists():
    for entry in root.iterdir():
        if not entry.is_dir() or entry.name.startswith(("remote_", "wsl_", "windows_")):
            continue
        count = 0
        latest = 0.0
        for f in entry.glob("*.jsonl"):
            try:
                st = f.stat()
            except OSError:
                continue
            count += 1
            latest = max(latest, st.st_mtime)
        if count:
            print(f"{entry.name}|{decode(entry.name)}|{count}|{latest}|claude")
"""
    if agent == "codex":
        return r"""
from pathlib import Path
import json
root = Path.home() / ".codex" / "sessions"
grouped = {}
if root.exists():
    for f in root.glob("*/*/*/rollout-*.jsonl"):
        try:
            first = f.open(encoding="utf-8").readline()
            entry = json.loads(first)
            cwd = (entry.get("payload") or {}).get("cwd") or ""
            st = f.stat()
        except Exception:
            continue
        if not cwd:
            continue
        count, latest = grouped.get(cwd, (0, 0.0))
        grouped[cwd] = (count + 1, max(latest, st.st_mtime))
for cwd, (count, latest) in grouped.items():
    print(f"{cwd}|{cwd}|{count}|{latest}|codex")
"""
    if agent == "gemini":
        return r"""
from pathlib import Path
root = Path.home() / ".gemini" / "tmp"
if root.exists():
    for ws in root.iterdir():
        chats = ws / "chats"
        if not chats.is_dir():
            continue
        count = 0
        latest = 0.0
        for f in list(chats.glob("*.json")) + list(chats.glob("*.jsonl")):
            try:
                st = f.stat()
            except OSError:
                continue
            count += 1
            latest = max(latest, st.st_mtime)
        if count:
            print(f"{ws.name}|{ws.name}|{count}|{latest}|gemini")
"""
    if agent == "pi":
        return r"""
from pathlib import Path
import json
root = Path.home() / ".pi" / "agent" / "sessions"
grouped = {}
if root.exists():
    for f in root.glob("*/*.jsonl"):
        workspace = f.parent.name
        try:
            with f.open(encoding="utf-8") as handle:
                for line in handle:
                    entry = json.loads(line)
                    if entry.get("type") == "session":
                        workspace = (entry.get("cwd") or workspace)
                        break
            st = f.stat()
        except Exception:
            continue
        count, latest = grouped.get(workspace, (0, 0.0))
        grouped[workspace] = (count + 1, max(latest, st.st_mtime))
for workspace, (count, latest) in grouped.items():
    print(f"{workspace}|{workspace}|{count}|{latest}|pi")
"""
    return None
