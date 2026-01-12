"""Inventory provider for session and workspace discovery."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from agent_history.adapters.remote import RemoteClientError, SSHRemoteClient
from agent_history.backends.claude import get_workspace_sessions
from agent_history.backends.codex import codex_scan_sessions
from agent_history.backends.gemini import gemini_scan_sessions
from agent_history.scope.context import ResolutionContext
from agent_history.scope.home_resolver import get_resolver_for_home
from agent_history.utils.paths import normalize_workspace_name
from agent_history.utils.platform import AGENT_CLAUDE, AGENT_CODEX, AGENT_GEMINI


class InventoryProvider:
    """Collect session and workspace inventory across homes and agents."""

    def __init__(self, context: ResolutionContext, remote_client: Optional[SSHRemoteClient] = None):
        self.context = context
        self.remote_client = remote_client or SSHRemoteClient()

    def list_sessions(self, home: str, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        sessions: List[Dict[str, Any]] = []

        if home == "web":
            return self._list_web_sessions(agent)

        if agent in (None, AGENT_CLAUDE):
            sessions.extend(self._list_claude_sessions(home))
        if agent in (None, AGENT_CODEX):
            sessions.extend(self._list_codex_sessions(home))
        if agent in (None, AGENT_GEMINI):
            sessions.extend(self._list_gemini_sessions(home))

        return sessions

    def list_workspaces(self, home: str, agent: Optional[str] = None) -> List[str]:
        workspaces: set[str] = set()

        if home == "web":
            return self._list_web_workspaces()

        if agent in (None, AGENT_CLAUDE):
            workspaces.update(self._list_claude_workspaces(home))
        if agent in (None, AGENT_CODEX):
            workspaces.update(self._list_codex_workspaces(home))
        if agent in (None, AGENT_GEMINI):
            workspaces.update(self._list_gemini_workspaces(home))

        return sorted(workspaces)

    def _list_claude_sessions(self, home: str) -> List[Dict[str, Any]]:
        if home.startswith("remote:"):
            return self._list_remote_claude_sessions(home)

        resolver = get_resolver_for_home(home)
        projects_dir = resolver.get_claude_dir(self.context)
        if not projects_dir or not projects_dir.exists():
            return []

        return get_workspace_sessions(
            workspace_pattern="*",
            projects_dir=projects_dir,
            skip_message_count=True,
        )

    def _list_codex_sessions(self, home: str) -> List[Dict[str, Any]]:
        if home.startswith("remote:"):
            return self._list_remote_codex_sessions(home)

        resolver = get_resolver_for_home(home)
        sessions_dir = resolver.get_codex_dir(self.context)
        if not sessions_dir or not sessions_dir.exists():
            return []

        return codex_scan_sessions(
            pattern="",
            sessions_dir=sessions_dir,
            skip_message_count=True,
        )

    def _list_gemini_sessions(self, home: str) -> List[Dict[str, Any]]:
        if home.startswith("remote:"):
            return self._list_remote_gemini_sessions(home)

        resolver = get_resolver_for_home(home)
        sessions_dir = resolver.get_gemini_dir(self.context)
        if not sessions_dir or not sessions_dir.exists():
            return []

        return gemini_scan_sessions(
            pattern="",
            sessions_dir=sessions_dir,
            skip_message_count=True,
        )

    def _list_claude_workspaces(self, home: str) -> List[str]:
        if home.startswith("remote:"):
            remote_host = home[7:]
            try:
                workspaces = self.remote_client.list_workspaces(remote_host, agent="claude")
            except RemoteClientError:
                return []
            return [normalize_workspace_name(ws, verify_local=False) for ws in workspaces]

        resolver = get_resolver_for_home(home)
        projects_dir = resolver.get_claude_dir(self.context)
        if not projects_dir or not projects_dir.exists():
            return []

        workspaces: List[str] = []
        for entry in projects_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                workspaces.append(normalize_workspace_name(entry.name, verify_local=True))

        return workspaces

    def _list_codex_workspaces(self, home: str) -> List[str]:
        sessions = self._list_codex_sessions(home)
        return sorted(
            {
                (s.get("workspace_readable") or s.get("workspace", "")).strip()
                for s in sessions
                if s
            }
            - {""}
        )

    def _list_gemini_workspaces(self, home: str) -> List[str]:
        sessions = self._list_gemini_sessions(home)
        return sorted(
            {
                (s.get("workspace_readable") or s.get("workspace", "")).strip()
                for s in sessions
                if s
            }
            - {""}
        )

    def _list_remote_claude_sessions(self, home: str) -> List[Dict[str, Any]]:
        remote_host = home[7:]
        sessions: List[Dict[str, Any]] = []

        try:
            workspaces = self.remote_client.list_workspaces(remote_host, agent="claude")
        except RemoteClientError:
            return sessions

        for workspace in workspaces:
            try:
                sessions.extend(
                    self.remote_client.list_sessions(remote_host, workspace, agent="claude")
                )
            except RemoteClientError:
                continue

        return sessions

    def _list_remote_codex_sessions(self, home: str) -> List[Dict[str, Any]]:
        remote_host = home[7:]
        sessions: List[Dict[str, Any]] = []
        try:
            workspaces = self.remote_client.list_workspaces(remote_host, agent="codex")
        except Exception:
            return []

        for workspace in workspaces:
            try:
                sessions.extend(
                    self.remote_client.list_sessions(remote_host, workspace, agent="codex")
                )
            except RemoteClientError:
                continue

        return sessions

    def _list_remote_gemini_sessions(self, home: str) -> List[Dict[str, Any]]:
        remote_host = home[7:]
        sessions: List[Dict[str, Any]] = []
        try:
            workspaces = self.remote_client.list_workspaces(remote_host, agent="gemini")
        except Exception:
            return []

        for workspace in workspaces:
            try:
                sessions.extend(
                    self.remote_client.list_sessions(remote_host, workspace, agent="gemini")
                )
            except RemoteClientError:
                continue

        return sessions

    def _list_web_sessions(self, agent: Optional[str]) -> List[Dict[str, Any]]:
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

        normalized: List[Dict[str, Any]] = []
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
                    "agent": AGENT_CLAUDE,
                    "home": "web",
                    "modified": modified,
                    "message_count": msg_count if msg_count is not None else 0,
                }
            )

        return normalized

    def _list_web_workspaces(self) -> List[str]:
        sessions = self._list_web_sessions(agent=AGENT_CLAUDE)
        return sorted(
            {
                (s.get("workspace_readable") or s.get("workspace", "")).strip()
                for s in sessions
                if s
            }
            - {""}
        )
