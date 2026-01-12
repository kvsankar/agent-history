"""
Stage 3: Workspace Resolution - Resolve WorkspaceSpecs to concrete paths.

CRITICAL: This is where we fix the substring matching bug!

The old implementation used substring matching:
    pattern in workspace  # BUGGY!

This caused /home/user/projects/auth to match /home/user/projects/auth-infra.

The new implementation uses EXACT matching by default:
    workspace == pattern  # CORRECT!
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from agent_history.scope.context import ResolutionError
from agent_history.scope.types import (
    HomeSpecConcrete,
    MatchType,
    ProjectRecord,
    ScopeRecord,
    TemplateScope,
    WorkspaceSpec,
    WorkspaceSpecAll,
    WorkspaceSpecConcrete,
    WorkspaceSpecCurrent,
    WorkspaceSpecEncoded,
    WorkspaceSpecFactory,
    WorkspaceSpecHash,
    WorkspaceSpecPath,
    WorkspaceSpecPattern,
    WorkspaceSpecProject,
)

if TYPE_CHECKING:
    from agent_history.scope.context import ResolutionContext


class WorkspaceStage:
    """
    Stage 3: Resolve WorkspaceSpecs to concrete workspace paths.

    Match behavior by WorkspaceSpec type:
    - WorkspaceSpec.Pattern with MatchType.EXACT: == (not 'in')
    - WorkspaceSpec.Path: used directly (exact)
    - WorkspaceSpec.Current: exact CWD workspace
    - WorkspaceSpec.All: enumerate all workspaces
    - WorkspaceSpec.Encoded: decode and use exact path
    - WorkspaceSpec.Hash: resolve hash and use exact path
    """

    def __init__(
        self,
        context: ResolutionContext,
        enumerate_workspaces_fn: Optional[Callable[[str], List[str]]] = None,
    ):
        """
        Initialize the workspace stage with a resolution context.

        Args:
            context: Resolution context containing workspace information.
            enumerate_workspaces_fn: Optional function to enumerate workspaces for a home.
                                    If not provided, uses _enumerate_workspaces_default.
        """
        self.context = context
        self._enumerate_workspaces_fn = (
            enumerate_workspaces_fn or self._enumerate_workspaces_default
        )

    def resolve(self, scope: TemplateScope) -> Tuple[TemplateScope, List[ResolutionError]]:
        """
        Resolve WorkspaceSpecs to concrete workspace paths.

        Args:
            scope: Template scope with WorkspaceSpecs to resolve.

        Returns:
            Tuple of:
            - Updated template scope with concrete workspaces
            - List of errors
        """
        result: TemplateScope = []
        errors: List[ResolutionError] = []

        for record in scope:
            if isinstance(record, ProjectRecord):
                errors.append(
                    ResolutionError(
                        stage="workspace",
                        spec=record,
                        reason="Unresolved project record in workspace resolution stage",
                        suggestions=["Ensure project resolution runs before workspace resolution"],
                    )
                )
                continue

            # Home should be concrete at this point
            if not isinstance(record.home, HomeSpecConcrete):
                errors.append(
                    ResolutionError(
                        stage="workspace",
                        spec=record,
                        reason="Home not resolved before workspace resolution",
                        suggestions=["Ensure home resolution runs before workspace resolution"],
                    )
                )
                continue

            home = record.home.home

            # Expand the workspace spec
            workspaces, ws_error = self._expand_workspace_spec(record.workspace, home)

            if ws_error:
                errors.append(ws_error)
                continue

            # Create a record for each resolved workspace
            for ws in workspaces:
                result.append(
                    ScopeRecord(
                        home=record.home,
                        workspace=WorkspaceSpecFactory.Concrete(ws),
                        sessions=record.sessions,
                    )
                )

        return result, errors

    def _expand_workspace_spec(
        self, spec: WorkspaceSpec, home: str
    ) -> Tuple[List[str], Optional[ResolutionError]]:
        """
        Expand a WorkspaceSpec to a list of concrete workspace paths.

        CRITICAL: This method implements proper match semantics to fix
        the substring matching bug.

        Args:
            spec: WorkspaceSpec to expand.
            home: Home identifier (needed for enumeration).

        Returns:
            Tuple of:
            - List of concrete workspace paths
            - Error if expansion failed (or None)
        """
        if isinstance(spec, WorkspaceSpecAll):
            return self._enumerate_workspaces(home), None

        elif isinstance(spec, WorkspaceSpecCurrent):
            if self.context.cwd_workspace:
                return [self.context.cwd_workspace], None
            # Error when not in a recognized workspace
            return [], ResolutionError(
                stage="workspace",
                spec=spec,
                reason="Not in a recognized workspace",
                suggestions=["Use --aw to list all workspaces or specify a pattern"],
            )

        elif isinstance(spec, WorkspaceSpecProject):
            # ProjectRecord should have been expanded in Stage 1
            return [], ResolutionError(
                stage="workspace",
                spec=spec,
                reason="Unresolved project reference in workspace expansion",
                suggestions=["Ensure project resolution runs first"],
            )

        elif isinstance(spec, WorkspaceSpecPath):
            # Exact path - use directly
            return [spec.path], None

        elif isinstance(spec, WorkspaceSpecEncoded):
            # Decode the encoded path
            decoded = self._decode_workspace_path(spec.encoded)
            return [decoded], None

        elif isinstance(spec, WorkspaceSpecPattern):
            # Match workspaces against pattern with proper semantics
            return self._match_workspaces(home, spec.pattern, spec.match_type), None

        elif isinstance(spec, WorkspaceSpecHash):
            # Resolve Gemini hash
            resolved = self._resolve_gemini_hash(spec.hash)
            if resolved:
                return [resolved], None
            return [], ResolutionError(
                stage="workspace",
                spec=spec,
                reason=f"Could not resolve hash '{spec.hash}'",
                suggestions=[],
            )

        elif isinstance(spec, WorkspaceSpecConcrete):
            # Already concrete
            return [spec.path], None

        else:
            return [], ResolutionError(
                stage="workspace",
                spec=spec,
                reason=f"Unknown WorkspaceSpec type: {type(spec).__name__}",
                suggestions=[],
            )

    def _enumerate_workspaces(self, home: str) -> List[str]:
        """
        List all workspaces in a home.

        This combines workspaces from all agents (Claude, Codex, Gemini)
        in the specified home.

        Args:
            home: Home identifier (e.g., "local", "wsl:Ubuntu").

        Returns:
            Sorted list of unique workspace paths.
        """
        return self._enumerate_workspaces_fn(home)

    def _enumerate_workspaces_default(self, home: str) -> List[str]:
        """
        Default implementation to enumerate workspaces.

        Combines workspaces from Claude, Codex, and Gemini.

        Args:
            home: Home identifier.

        Returns:
            Sorted list of unique workspace paths.
        """
        workspaces: set[str] = set()

        # Claude workspaces
        claude_workspaces = self._enumerate_claude_workspaces(home)
        workspaces.update(claude_workspaces)

        # Codex workspaces
        codex_workspaces = self._enumerate_codex_workspaces(home)
        workspaces.update(codex_workspaces)

        # Gemini workspaces
        gemini_workspaces = self._enumerate_gemini_workspaces(home)
        workspaces.update(gemini_workspaces)

        return sorted(workspaces)

    def _enumerate_claude_workspaces(self, home: str) -> List[str]:
        """
        Enumerate workspaces from Claude's projects directory.

        Claude stores session directories with encoded workspace names.
        Each directory name is decoded to get the actual workspace path.

        Args:
            home: Home identifier.

        Returns:
            List of workspace paths found in Claude's projects.
        """
        workspaces: List[str] = []

        if home != "local":
            # TODO: Handle non-local homes (WSL, remote)
            return workspaces

        claude_dir = self.context.claude_projects_dir
        if not claude_dir or not claude_dir.exists():
            return workspaces

        for entry in claude_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                # Decode the directory name to get workspace path
                workspace = self._decode_workspace_path(entry.name)
                workspaces.append(workspace)

        return workspaces

    def _enumerate_codex_workspaces(self, home: str) -> List[str]:
        """
        Enumerate workspaces from Codex sessions.

        Codex stores workspace information in session metadata.
        This requires scanning the sessions or reading an index.

        Args:
            home: Home identifier.

        Returns:
            List of workspace paths found in Codex sessions.
        """
        from agent_history.backends.codex import codex_scan_sessions

        workspaces: List[str] = []

        if home != "local":
            # TODO: Handle non-local homes (WSL, remote)
            return workspaces

        # Get all Codex sessions and extract unique workspaces
        sessions_dir = self.context.codex_sessions_dir
        codex_sessions = codex_scan_sessions(
            pattern="",
            sessions_dir=sessions_dir,
            skip_message_count=True,
        )
        seen: set[str] = set()
        for session in codex_sessions:
            ws = session.get("workspace_readable") or session.get("workspace", "")
            if ws and ws not in seen:
                seen.add(ws)
                workspaces.append(ws)

        return workspaces

    def _enumerate_gemini_workspaces(self, home: str) -> List[str]:
        """
        Enumerate workspaces from Gemini sessions.

        Gemini uses hash-based workspace identifiers. This method:
        1. Scans all Gemini session directories
        2. For each hash, looks up the readable path in the hash index
        3. Returns either the resolved path or the hash as a workspace

        Args:
            home: Home identifier.

        Returns:
            List of workspace paths found in Gemini sessions.
        """
        from agent_history.backends.gemini import gemini_load_hash_index

        workspaces: List[str] = []

        if home != "local":
            # TODO: Handle non-local homes (WSL, remote)
            return workspaces

        # Use context's gemini_sessions_dir (respects GEMINI_SESSIONS_DIR env var)
        gemini_dir = self.context.gemini_sessions_dir
        if not gemini_dir or not gemini_dir.exists():
            return workspaces

        # Load the hash index for path resolution
        hash_index = gemini_load_hash_index()
        hashes_map = hash_index.get("hashes", {})

        # Scan for hash directories that contain session files
        for hash_dir in gemini_dir.iterdir():
            if not hash_dir.is_dir():
                continue
            chats_dir = hash_dir / "chats"
            if not chats_dir.exists():
                continue
            # Check if there are any session files
            if not any(chats_dir.glob("session-*.json")):
                continue

            project_hash = hash_dir.name
            # Look up the readable path in the hash index
            readable_path = hashes_map.get(project_hash)
            if readable_path:
                workspaces.append(readable_path)
            else:
                # Fall back to using the hash as workspace identifier
                workspaces.append(project_hash)

        return workspaces

    def _match_workspaces(self, home: str, pattern: str, match_type: MatchType) -> List[str]:
        """
        Match workspaces against a pattern with specified semantics.

        CRITICAL FIX: This method uses the proper match type instead of
        always doing substring matching.

        Match types:
        - EXACT: workspace == pattern (THE FIX!)
        - PREFIX: workspace.startswith(pattern)
        - CONTAINS: pattern.lower() in workspace.lower() (old buggy behavior)
        - GLOB: fnmatch.fnmatch(workspace, pattern)

        Args:
            home: Home identifier to search in.
            pattern: Pattern to match against.
            match_type: How to interpret the pattern.

        Returns:
            List of matching workspace paths.
        """
        all_workspaces = self._enumerate_workspaces(home)
        normalized_pattern = pattern
        if match_type in (MatchType.EXACT, MatchType.PREFIX):
            from agent_history.utils.workspace_ref import build_workspace_ref

            normalized_pattern = build_workspace_ref(pattern).key

        if match_type == MatchType.EXACT:
            # THE FIX: Exact equality, no substring matching!
            return [ws for ws in all_workspaces if ws == normalized_pattern]

        elif match_type == MatchType.PREFIX:
            # Prefix matching - useful for directory hierarchies
            return [ws for ws in all_workspaces if ws.startswith(normalized_pattern)]

        elif match_type == MatchType.CONTAINS:
            # Substring matching - the OLD BUGGY behavior
            # Only use when explicitly requested!
            # Also check if pattern matches with path separators replaced by dashes
            # (handles patterns like "split-target" matching "/home/user/split/target")
            pattern_lower = pattern.lower()
            result = []
            for ws in all_workspaces:
                ws_lower = ws.lower()
                # Check direct substring match
                if pattern_lower in ws_lower:
                    result.append(ws)
                # Also check if pattern matches when slashes in workspace are dashes
                # (e.g., "split-target" matches "/home/user/split/target" via "-split-target")
                elif pattern_lower in ws_lower.replace("/", "-"):
                    result.append(ws)
            return result

        elif match_type == MatchType.GLOB:
            # Glob/fnmatch-style matching
            return [ws for ws in all_workspaces if fnmatch.fnmatch(ws, pattern)]

        else:
            # Unknown match type - default to exact
            return [ws for ws in all_workspaces if ws == pattern]

    def _decode_workspace_path(self, encoded: str) -> str:
        """
        Decode a Claude-style encoded workspace path.

        Claude encodes workspace paths by replacing slashes with hyphens.
        Example: /home/user/projects/auth -> -home-user-projects-auth

        This method uses normalize_workspace_name which verifies against the
        filesystem to correctly handle directory names that contain dashes
        (e.g., 'my-project' vs 'my/project').

        Args:
            encoded: Encoded workspace name.

        Returns:
            Decoded absolute path.
        """
        from agent_history.utils.paths import normalize_workspace_name

        # Use the proper decoding function that handles dashed names correctly
        return normalize_workspace_name(encoded, verify_local=True)

    def _resolve_gemini_hash(self, hash_value: str) -> Optional[str]:
        """
        Resolve a Gemini hash to a workspace path.

        Args:
            hash_value: Gemini hash identifier.

        Returns:
            Workspace path if found, None otherwise.
        """
        from agent_history.backends.gemini import gemini_get_path_for_hash

        return gemini_get_path_for_hash(hash_value)
