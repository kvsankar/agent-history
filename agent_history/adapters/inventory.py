"""Inventory provider for session and workspace discovery."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from agent_history.adapters.remote import RemoteClientError, SSHRemoteClient
from agent_history.backends.registry import AgentBackend, get_default_backend_id, iter_backends
from agent_history.scope.context import ResolutionContext
from agent_history.scope.home_resolver import get_resolver_for_home
from agent_history.utils.paths import normalize_workspace_name
from agent_history.utils.platform import AGENT_CLAUDE
from agent_history.utils.workspace_ref import apply_workspace_ref


class InventoryProvider:
    """Collect session and workspace inventory across homes and agents."""

    def __init__(self, context: ResolutionContext, remote_client: SSHRemoteClient | None = None):
        self.context = context
        self.remote_client = remote_client or SSHRemoteClient()

    def list_sessions(self, home: str, agent: str | None = None) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []

        # In test mode, skip remote probing to avoid slow SSH lookups.
        test_mode = bool(os.environ.get("AGENT_HISTORY_TEST_MODE"))
        if home.startswith("remote:") and test_mode:
            return sessions

        if home == "web":
            return self._list_web_sessions(agent)

        for backend in iter_backends(agent):
            sessions.extend(self._list_backend_sessions(home, backend))

        for session in sessions:
            apply_workspace_ref(session)

        return sessions

    def list_workspaces(self, home: str, agent: str | None = None) -> list[str]:
        workspaces: set[str] = set()

        # Avoid remote SSH probing in test mode.
        test_mode = bool(os.environ.get("AGENT_HISTORY_TEST_MODE"))
        if home.startswith("remote:") and test_mode:
            return []

        if home == "web":
            return self._list_web_workspaces()

        for backend in iter_backends(agent):
            workspaces.update(self._list_backend_workspaces(home, backend))

        return sorted(workspaces)

    def _list_backend_sessions(self, home: str, backend: AgentBackend) -> list[dict[str, Any]]:
        if home.startswith("remote:"):
            return self._list_remote_backend_sessions(home, backend)

        resolver = get_resolver_for_home(home)
        sessions_dir = backend.get_session_dir(resolver, self.context)
        if not sessions_dir or not sessions_dir.exists():
            return []

        return backend.scan_sessions(sessions_dir)

    def _list_backend_workspaces(self, home: str, backend: AgentBackend) -> list[str]:
        if home.startswith("remote:"):
            remote_host = home[7:]
            try:
                workspaces = self.remote_client.list_workspaces(remote_host, agent=backend.id)
            except Exception:
                return []
            return [normalize_workspace_name(ws, verify_local=False) for ws in workspaces]

        resolver = get_resolver_for_home(home)
        sessions_dir = backend.get_session_dir(resolver, self.context)
        if not sessions_dir or not sessions_dir.exists():
            return []

        return backend.list_workspaces(sessions_dir, home)

    def _list_remote_backend_sessions(
        self, home: str, backend: AgentBackend
    ) -> list[dict[str, Any]]:
        remote_host = home[7:]
        sessions: list[dict[str, Any]] = []

        try:
            workspaces = self.remote_client.list_workspaces(remote_host, agent=backend.id)
        except Exception:
            return sessions

        for workspace in workspaces:
            try:
                sessions.extend(
                    self.remote_client.list_sessions(remote_host, workspace, agent=backend.id)
                )
            except RemoteClientError:
                continue

        return sessions

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
