"""
Stage 4: Session Resolution - Collect sessions for each workspace.

CRITICAL: This stage uses EXACT workspace matching when collecting
sessions! Sessions are only included if their workspace field matches
the target workspace exactly (==), not via substring matching (in).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from agent_history.scope.context import ResolutionError
from agent_history.scope.types import (
    ConcreteRecord,
    ConcreteScope,
    HomeSpecConcrete,
    ProjectRecord,
    SessionSpec,
    SessionSpecAll,
    SessionSpecFiltered,
    TemplateScope,
    WorkspaceSpecConcrete,
)

if TYPE_CHECKING:
    from agent_history.scope.cache import SessionCache
    from agent_history.scope.context import ResolutionContext


class SessionStage:
    """
    Stage 4: Collect sessions for each (home, workspace) pair.

    Uses the SessionCache to efficiently retrieve and filter sessions.
    """

    def __init__(self, context: ResolutionContext, session_cache: SessionCache):
        """
        Initialize the session stage with a resolution context and cache.

        Args:
            context: Resolution context containing session information.
            session_cache: Session cache for efficient session retrieval.
        """
        self.context = context
        self.session_cache = session_cache

    def resolve(
        self, scope: TemplateScope
    ) -> Tuple[ConcreteScope, List[ResolutionError]]:
        """
        Collect sessions for each (home, workspace) pair.

        Args:
            scope: Template scope with concrete homes and workspaces.

        Returns:
            Tuple of:
            - ConcreteScope with actual session data
            - List of errors
        """
        result: ConcreteScope = []
        errors: List[ResolutionError] = []

        for record in scope:
            if isinstance(record, ProjectRecord):
                errors.append(
                    ResolutionError(
                        stage="session",
                        spec=record,
                        reason="Unresolved project record in session resolution stage",
                        suggestions=[],
                    )
                )
                continue

            # Extract concrete values
            if not isinstance(record.home, HomeSpecConcrete):
                errors.append(
                    ResolutionError(
                        stage="session",
                        spec=record,
                        reason="Home not resolved before session collection",
                        suggestions=[],
                    )
                )
                continue

            if not isinstance(record.workspace, WorkspaceSpecConcrete):
                errors.append(
                    ResolutionError(
                        stage="session",
                        spec=record,
                        reason="Workspace not resolved before session collection",
                        suggestions=[],
                    )
                )
                continue

            home = record.home.home
            workspace = record.workspace.path

            # Collect sessions with EXACT workspace matching
            sessions = self._collect_sessions(home, workspace, record.sessions)

            # Only include if sessions exist
            if sessions:
                result.append(
                    ConcreteRecord(
                        home=home,
                        workspace=workspace,
                        sessions=sessions,
                    )
                )

        return result, errors

    def _collect_sessions(
        self, home: str, workspace: str, session_spec: SessionSpec
    ) -> List[Dict[str, Any]]:
        """
        Collect sessions for a specific (home, workspace) pair.

        CRITICAL: This method uses EXACT workspace matching!
        A session is only included if session.workspace == target_workspace,
        not if target_workspace is a substring of session.workspace.

        This is the key fix for the session count inconsistency bug.

        Args:
            home: Concrete home identifier.
            workspace: Concrete workspace path.
            session_spec: SessionSpec for filtering.

        Returns:
            List of session dictionaries matching the criteria.
        """
        # Get sessions from cache (already grouped by workspace)
        all_sessions = self.session_cache.get_sessions(home, workspace)

        # CRITICAL FIX: Filter to EXACT workspace match only!
        # This is THE FIX for the substring matching bug.
        # Sessions from /home/user/auth-infra should NOT appear when
        # searching for /home/user/auth.
        # Check both workspace_readable AND workspace fields, since either could match.
        sessions = [
            s
            for s in all_sessions
            if (
                s.get("workspace_key", "") == workspace
                or s.get("workspace_readable", "") == workspace
                or s.get("workspace", "") == workspace
            )
        ]

        # Apply session spec filters
        sessions = self._apply_session_filters(sessions, session_spec)

        return sessions

    def _apply_session_filters(
        self, sessions: List[Dict[str, Any]], session_spec: SessionSpec
    ) -> List[Dict[str, Any]]:
        """
        Apply SessionSpec filters to a list of sessions.

        Args:
            sessions: List of session dictionaries.
            session_spec: SessionSpec with filter criteria.

        Returns:
            Filtered list of sessions.
        """
        if isinstance(session_spec, SessionSpecAll):
            return sessions

        elif isinstance(session_spec, SessionSpecFiltered):
            filters = session_spec.filters
            result = sessions

            # Filter by agent
            if filters.agent:
                result = [s for s in result if s.get("agent") == filters.agent]

            # Filter by date range
            if filters.since:
                result = [
                    s for s in result if s.get("modified") and s.get("modified") >= filters.since
                ]

            if filters.until:
                result = [
                    s for s in result if s.get("modified") and s.get("modified") <= filters.until
                ]

            # Filter by message count
            if filters.min_messages is not None:
                result = [s for s in result if s.get("message_count", 0) >= filters.min_messages]

            return result

        else:
            # Unknown spec type - return all
            return sessions
