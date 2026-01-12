"""
Session Cache - Efficient session loading and caching for scope resolution.

This module provides a session cache that loads sessions from all agents
(Claude, Codex, Gemini) and groups them by workspace for O(1) lookup.

The cache is loaded lazily per home to avoid unnecessary I/O operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from agent_history.scope.context import ResolutionContext


class SessionCache:
    """
    Session cache for efficient session retrieval.

    Caches sessions by home and workspace for O(1) lookup.
    Sessions are loaded lazily when first requested for a home.
    """

    def __init__(self, context: ResolutionContext, inventory_provider: Optional[Any] = None):
        """
        Initialize the session cache with a resolution context.

        Args:
            context: Resolution context containing agent paths.
        """
        self.context = context
        if inventory_provider is None:
            from agent_history.adapters.inventory import InventoryProvider

            inventory_provider = InventoryProvider(context)
        self.inventory_provider = inventory_provider
        # Session cache: {home: {workspace: [sessions]}}
        # Loaded once per home, grouped by workspace for O(1) lookup
        self._cache: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    def get_sessions(self, home: str, workspace: str) -> List[Dict[str, Any]]:
        """
        Get sessions for a specific (home, workspace) pair.

        Args:
            home: Home identifier.
            workspace: Workspace path.

        Returns:
            List of session dictionaries for the workspace.
        """
        # Ensure cache is populated for this home
        workspace_sessions = self._ensure_cache(home)

        # Return sessions for the workspace (or empty list if not found)
        return workspace_sessions.get(workspace, [])

    def _ensure_cache(self, home: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Ensure session cache is populated for a home.

        Loads all sessions from all agents (Claude, Codex, Gemini) for the
        given home and groups them by workspace for O(1) lookup.

        Args:
            home: Home identifier to load sessions for.

        Returns:
            Dictionary mapping workspace -> list of sessions.
        """
        if home in self._cache:
            return self._cache[home]

        # Group sessions by workspace
        workspace_sessions: Dict[str, List[Dict[str, Any]]] = {}

        all_sessions = self.inventory_provider.list_sessions(home)
        for session in all_sessions:
            ws = session.get("workspace_readable") or session.get("workspace", "")
            if ws:
                if ws not in workspace_sessions:
                    workspace_sessions[ws] = []
                workspace_sessions[ws].append(session)
            # Also index by raw workspace (hash) if different
            raw_ws = session.get("workspace", "")
            if raw_ws and raw_ws != ws:
                if raw_ws not in workspace_sessions:
                    workspace_sessions[raw_ws] = []
                workspace_sessions[raw_ws].append(session)

        self._cache[home] = workspace_sessions
        return workspace_sessions

    def _load_claude_sessions(self, home: str) -> List[Dict[str, Any]]:
        """
        Load all Claude sessions for a home (not filtered by workspace).

        Args:
            home: Home identifier.

        Returns:
            List of all session dictionaries in the home.
        """
        from agent_history.backends.claude import get_workspace_sessions

        # Handle different home types
        if home == "local":
            # Use default Claude projects directory
            projects_dir = self.context.claude_projects_dir
        elif home.startswith("wsl:"):
            # WSL homes - adjust base path
            # TODO: Implement WSL path resolution
            return []
        elif home == "windows":
            # Windows homes - adjust for Windows paths
            # TODO: Implement Windows path resolution
            return []
        elif home.startswith("remote:"):
            # Remote homes - scan for cached workspaces with remote_ prefix
            # Cached remote workspaces are named: remote_{remote_name}_{encoded_path}
            remote_name = home[7:]  # Extract name after "remote:"
            prefix = f"remote_{remote_name}_"
            projects_dir = self.context.claude_projects_dir
            if not projects_dir or not projects_dir.exists():
                return []
            # Scan for matching remote cache workspaces
            all_sessions = get_workspace_sessions(
                workspace_pattern=prefix,
                projects_dir=projects_dir,
                skip_message_count=True,
                include_cached=True,
            )
            # Decode workspace paths: remote_vm01_-home-user-project -> /home/user/project
            for session in all_sessions:
                ws = session.get("workspace", "")
                if ws.startswith(prefix):
                    encoded_path = ws[len(prefix):]
                    # Decode: -home-user-project -> /home/user/project
                    if encoded_path.startswith("-"):
                        decoded = encoded_path.replace("-", "/")
                        session["workspace_readable"] = decoded
            return all_sessions
        else:
            # Unknown home type - use default
            projects_dir = self.context.claude_projects_dir

        if not projects_dir or not projects_dir.exists():
            return []

        # Get all sessions using backend function
        # Skip message count by default for faster loading during scope resolution
        # Message counts can be computed later if needed
        all_sessions = get_workspace_sessions(
            workspace_pattern="*",
            projects_dir=projects_dir,
            skip_message_count=True,
        )

        return all_sessions

    def _load_codex_sessions(self, home: str) -> List[Dict[str, Any]]:
        """
        Load all Codex sessions for a home (not filtered by workspace).

        Args:
            home: Home identifier.

        Returns:
            List of all session dictionaries in the home.
        """
        from agent_history.backends.codex import codex_scan_sessions

        # Handle different home types
        if home == "local":
            # Use Codex sessions directory from context (respects env var override)
            sessions_dir = self.context.codex_sessions_dir
        elif home.startswith("wsl:"):
            # WSL homes - not yet supported for Codex
            # TODO: Implement WSL path resolution for Codex
            return []
        elif home == "windows":
            # Windows homes - not yet supported for Codex
            # TODO: Implement Windows path resolution for Codex
            return []
        elif home.startswith("remote:"):
            # Remote homes - skip for now
            # TODO: Implement remote session collection for Codex
            return []
        else:
            # Unknown home type - use default from context
            sessions_dir = self.context.codex_sessions_dir

        # Get all sessions using backend function
        # Empty pattern matches all workspaces
        # Skip message count by default for faster loading during scope resolution
        all_sessions = codex_scan_sessions(
            pattern="",
            sessions_dir=sessions_dir,
            skip_message_count=True,
        )

        return all_sessions

    def _load_gemini_sessions(self, home: str) -> List[Dict[str, Any]]:
        """
        Load all Gemini sessions for a home (not filtered by workspace).

        Args:
            home: Home identifier.

        Returns:
            List of all session dictionaries in the home.
        """
        from agent_history.backends.gemini import gemini_scan_sessions

        # Handle different home types
        if home == "local":
            # Use Gemini sessions directory from context (respects env var override)
            sessions_dir = self.context.gemini_sessions_dir
        elif home.startswith("wsl:"):
            # WSL homes - not yet supported for Gemini
            # TODO: Implement WSL path resolution for Gemini
            return []
        elif home == "windows":
            # Windows homes - not yet supported for Gemini
            # TODO: Implement Windows path resolution for Gemini
            return []
        elif home.startswith("remote:"):
            # Remote homes - skip for now
            # TODO: Implement remote session collection for Gemini
            return []
        else:
            # Unknown home type - use default from context
            sessions_dir = self.context.gemini_sessions_dir

        # Get all sessions using backend function
        # Empty pattern matches all workspaces
        # Skip message count by default for faster loading during scope resolution
        all_sessions = gemini_scan_sessions(
            pattern="",
            sessions_dir=sessions_dir,
            skip_message_count=True,
        )

        return all_sessions

    def clear(self) -> None:
        """Clear the session cache."""
        self._cache.clear()
