"""
Scope Resolver: 4-stage resolution pipeline for converting scope specifications to concrete values.

This module implements the core scope resolution pipeline that fixes the critical
workspace matching bug. The pipeline progressively resolves specifications through
four stages:

    Stage 0: Build Template   - ScopeArgs -> TemplateScope
    Stage 1: Resolve Projects - Expand ProjectRecords to ScopeRecords
    Stage 2: Resolve Homes    - Resolve HomeSpecs to concrete home strings
    Stage 3: Resolve Workspaces - Resolve WorkspaceSpecs to concrete paths
    Stage 4: Resolve Sessions - Collect sessions for each workspace

CRITICAL FIX: This implementation uses EXACT workspace matching (==) instead of
substring matching (in). The old buggy behavior caused /home/user/projects/auth
to match /home/user/projects/auth-infra, leading to session count inconsistencies.

See docs/design-v2/scope-resolution-v2.md for the complete specification.
See docs/design-v2/pipeline-architecture.md for the algorithm details.
"""

from __future__ import annotations

from typing import Any

from agent_history.backends.gemini import gemini_load_hash_index
from agent_history.scope.cache import SessionCache
from agent_history.scope.context import (
    ResolutionContext,
    ResolutionError,
    ResolutionResult,
    ScopeArgs,
)
from agent_history.scope.home_resolver import get_resolver_for_home
from agent_history.scope.stages import HomeStage, ProjectStage, SessionStage, WorkspaceStage
from agent_history.scope.types import (
    ConcreteScope,
    HomeSpec,
    HomeSpecConcrete,
    HomeSpecFactory,
    MatchType,
    ProjectRecord,
    ScopeRecord,
    SessionSpec,
    SessionSpecAll,
    TemplateScope,
    WorkspaceSpec,
    WorkspaceSpecConcrete,
    WorkspaceSpecFactory,
)
from agent_history.types import SessionDict, WorkspaceSessionsMap


class ScopeResolver:
    """
    Main entry point for scope resolution.

    The ScopeResolver takes scope arguments and a resolution context, then
    progressively resolves specifications through four stages to produce
    a ConcreteScope with actual session data.

    Example usage:
        context = build_resolution_context()
        resolver = ScopeResolver(context)
        result = resolver.resolve(scope_args)
        if result.success:
            for record in result.scope:
                print(f"{record.home}:{record.workspace} - {len(record.sessions)} sessions")

    The key architectural principle is that ALL workspace matching uses EXACT
    equality (==) rather than substring matching (in), which fixes the
    inconsistency bug between session list and project stats commands.
    """

    def __init__(self, context: ResolutionContext):
        """
        Initialize the resolver with a resolution context.

        Args:
            context: Resolution context containing environment state,
                    available homes, project configuration, and agent paths.
        """
        self.context = context

        # Session cache: {home: {workspace: [sessions]}}
        # Loaded once per home, grouped by workspace for O(1) lookup
        self._session_cache: WorkspaceSessionsMap = {}

        from agent_history.adapters.inventory import InventoryProvider

        self._inventory = InventoryProvider(context)

        # Initialize stage modules
        self._cache = SessionCache(context, self._inventory)
        self._project_stage = ProjectStage(context)
        self._home_stage = HomeStage(context)
        self._workspace_stage = WorkspaceStage(
            context,
            enumerate_workspaces_fn=self._enumerate_workspaces,
        )
        self._session_stage = SessionStage(context, self._cache)

    def resolve(self, scope_args: ScopeArgs, load_sessions: bool = True) -> ResolutionResult:
        """
        Resolve scope args through the full 4-stage pipeline.

        This is the main entry point for scope resolution. It takes the
        parsed command arguments and returns a ConcreteScope with fully
        resolved homes, workspaces, and sessions.

        Args:
            scope_args: Scope arguments from command line parsing.
            load_sessions: If False, skip session loading and return
                empty session lists per workspace (useful for fast
                metadata-only commands like `home list`).

        Returns:
            ResolutionResult containing:
            - scope: ConcreteScope with resolved records (may be partial on errors)
            - errors: List of ResolutionError objects for any failures
            - warnings: List of warning messages

        The pipeline stages are:
        1. Build initial template from scope_args
        2. Expand ProjectRecords to ScopeRecords
        3. Resolve HomeSpecs to concrete home strings
        4. Resolve WorkspaceSpecs to concrete paths
        5. Collect sessions for each (home, workspace) pair
        """
        errors: list[ResolutionError] = []
        warnings: list[str] = []

        # Stage 0: Build initial template from arguments
        template = self._build_template(scope_args)

        # Stage 1: Resolve projects (expand ProjectRecords)
        # Use the delegate method to allow test patching
        template, stage_errors = self._resolve_projects(template)
        errors.extend(stage_errors)

        # Stage 2: Resolve homes (expand HomeSpecs)
        template, stage_errors = self._resolve_homes(template)
        errors.extend(stage_errors)

        # Stage 3: Resolve workspaces (expand WorkspaceSpecs)
        template, stage_errors = self._resolve_workspaces(template)
        errors.extend(stage_errors)

        if not load_sessions:
            concrete = self._materialize_scope_without_sessions(template)
        else:
            # Stage 4: Resolve sessions (collect actual sessions)
            concrete, stage_errors = self._resolve_sessions_internal(template)
            errors.extend(stage_errors)

        return ResolutionResult(scope=concrete, errors=errors, warnings=warnings)

    # =========================================================================
    # Stage 0: Build Template
    # =========================================================================

    def _build_template(self, args: ScopeArgs) -> TemplateScope:
        """
        Convert scope arguments to initial template scope (Stage 0).

        This stage parses the command line arguments and builds the initial
        TemplateScope. The key logic determines what the user's intent is:

        Resolution Priority:
        1. Explicit --project flag -> ProjectRecord
        2. CWD is in a project (and not --this) -> ProjectRecord (implicit detection)
        3. Explicit --aw flag -> WorkspaceSpec.All
        4. Explicit patterns -> WorkspaceSpec.Pattern for each (EXACT match!)
        5. --this flag -> WorkspaceSpec.Current
        6. CWD is in a workspace -> WorkspaceSpec.Current
        7. Default -> WorkspaceSpec.All

        Args:
            args: Parsed scope arguments from command line.

        Returns:
            Initial TemplateScope with ScopeRecord or ProjectRecord entries.
        """
        # Determine session spec from filters
        session_spec = self._build_session_spec(args)

        # Determine home spec from arguments
        home_spec = self._build_home_spec(args)

        # CROSS-HOME GUARD: Require pattern/project/--aw for non-local home access
        # This prevents accidentally scanning remote homes with implicit patterns
        # The guard only applies when the user is IN a local workspace - if they're
        # not in a workspace, there's no implicit path that could be mismatched
        non_web_homes = [home for home in args.home_names if home != "web"]
        needs_cross_home = (
            args.home_type in ("wsl", "windows", "remote") or args.all_homes or bool(non_web_homes)
        )
        has_explicit_scope = (
            args.all_workspaces
            or bool(args.projects)
            or self.context.cwd_project
            or bool(args.patterns)
            or bool(args.name_patterns)
        )
        is_in_workspace = bool(self.context.cwd_workspace)
        if needs_cross_home and not has_explicit_scope and is_in_workspace:
            # Determine target description for error message
            if args.home_type == "wsl":
                target = "WSL"
            elif args.home_type == "windows":
                target = "Windows"
            elif args.all_homes:
                target = "all homes"
            else:
                target = "remote"

            raise ValueError(
                f"Cross-home access to {target} requires a workspace pattern.\n\n"
                "Options:\n"
                "  1. Add a workspace pattern: -n <pattern>\n"
                "  2. Use --aw to list all workspaces\n"
                "  3. Use --project to use a project's workspaces"
            )

        # Check for explicit project
        if args.projects:
            return [
                ProjectRecord(project=project, sessions=session_spec)
                for project in dict.fromkeys(args.projects)
            ]

        # Check for --this (current workspace only) - must come before implicit project
        # This forces scope to current workspace only, overriding project expansion
        if args.this_only:
            return [
                ScopeRecord(
                    home=home_spec,
                    workspace=WorkspaceSpecFactory.Current,
                    sessions=session_spec,
                )
            ]

        # Check for explicit patterns
        # Positional patterns: EXACT for paths, CONTAINS for names
        # -n patterns use CONTAINS matching (for discovery by partial name)
        if args.patterns or args.name_patterns:
            records: TemplateScope = []
            # Positional patterns: determine match type based on pattern format
            # - Full paths (starting with / or -) use EXACT matching
            #   This prevents /home/user/projects/auth from matching auth-infra
            # - Simple names (like "react") use CONTAINS matching
            #   This allows "react" to match "/home/user/react-app"
            for pattern in args.patterns:
                # Determine match type based on whether pattern looks like a path
                if pattern.startswith("/") or pattern.startswith("-") or "/" in pattern:
                    # Path-like pattern - use exact match
                    match_type = MatchType.EXACT
                else:
                    # Name-like pattern - use substring match
                    match_type = MatchType.CONTAINS
                workspace_spec = WorkspaceSpecFactory.Pattern(pattern, match_type)
                records.append(
                    ScopeRecord(
                        home=home_spec,
                        workspace=workspace_spec,
                        sessions=session_spec,
                    )
                )
            # -n patterns: CONTAINS matching (substring match for discovery)
            # e.g., "django" matches "/home/user/django-app"
            for pattern in args.name_patterns:
                workspace_spec = WorkspaceSpecFactory.Pattern(pattern, MatchType.CONTAINS)
                records.append(
                    ScopeRecord(
                        home=home_spec,
                        workspace=workspace_spec,
                        sessions=session_spec,
                    )
                )
            return records

        # Check for implicit project detection (CWD in project)
        if self.context.cwd_project:
            return [ProjectRecord(project=self.context.cwd_project, sessions=session_spec)]

        # Check for --aw (all workspaces) - but patterns can still filter
        # If --aw is used without patterns, show all workspaces
        # If --aw is used with patterns, patterns will filter (handled above)
        if args.all_workspaces and not args.patterns and not args.name_patterns:
            return [
                ScopeRecord(
                    home=home_spec,
                    workspace=WorkspaceSpecFactory.All,
                    sessions=session_spec,
                )
            ]

        # Check if CWD is in a workspace (use it as current)
        if self.context.cwd_workspace:
            return [
                ScopeRecord(
                    home=home_spec,
                    workspace=WorkspaceSpecFactory.Current,
                    sessions=session_spec,
                )
            ]

        # Default: all workspaces
        return [
            ScopeRecord(
                home=home_spec,
                workspace=WorkspaceSpecFactory.All,
                sessions=session_spec,
            )
        ]

    def _build_home_spec(self, args: ScopeArgs) -> HomeSpec:
        """
        Build HomeSpec from scope arguments.

        Args:
            args: Parsed scope arguments.

        Returns:
            Appropriate HomeSpec based on the arguments.
        """
        # --ah (all homes)
        if args.all_homes:
            # Special case: --ah --local limits to local
            if args.home_type == "local":
                return HomeSpecFactory.Local

            homes: list[str] = ["local"]

            if not args.no_wsl:
                for distro in self.context.available_homes.get("wsl", []):
                    homes.append(f"wsl:{distro}")

            if not args.no_windows:
                for user in self.context.available_homes.get("windows", []):
                    homes.append(f"windows:{user}")

            if not args.no_remote:
                for remote in self.context.available_homes.get("remote", []):
                    homes.append(f"remote:{remote}")

            if not args.no_web:
                homes.append("web")

            # Deduplicate while preserving order
            seen = set()
            ordered = []
            for home in homes:
                if home not in seen:
                    seen.add(home)
                    ordered.append(home)

            return HomeSpecFactory.Multiple(ordered)

        # Category-based selection (--wsl, --windows, --remote, --local)
        if args.home_type:
            # --local is special - it's not a category, it's the local home
            if args.home_type == "local":
                return HomeSpecFactory.Local
            if args.home_value:
                # --wsl=Ubuntu, --windows=alice, etc.
                return HomeSpecFactory.CategoryItem(args.home_type, args.home_value)
            else:
                # --wsl, --windows, --remote (all of category)
                return HomeSpecFactory.Category(args.home_type)

        # Explicit home names (--home flag, can be repeated)
        if args.home_names:
            if len(args.home_names) == 1:
                # Single home - use Concrete
                return HomeSpecFactory.Concrete(args.home_names[0])
            else:
                # Multiple homes - use Multiple to preserve all values
                return HomeSpecFactory.Multiple(args.home_names)

        # Default: local home only
        return HomeSpecFactory.Local

    def _build_session_spec(self, args: ScopeArgs) -> SessionSpec:
        """
        Build SessionSpec from scope arguments.

        Args:
            args: Parsed scope arguments.

        Returns:
            SessionSpec with appropriate filters.
        """
        from datetime import datetime

        from agent_history.scope.types import SessionFilters, SessionSpecFactory

        # Check if any filters are specified
        has_filters = args.agent or args.since or args.until

        if not has_filters:
            return SessionSpecAll()

        # Parse date strings to datetime objects
        since_dt = None
        until_dt = None
        if args.since:
            since_dt = datetime.strptime(args.since, "%Y-%m-%d")
        if args.until:
            until_dt = datetime.strptime(args.until, "%Y-%m-%d")

        # Build SessionFilters from args
        filters = SessionFilters(
            agent=args.agent,
            since=since_dt,
            until=until_dt,
        )

        return SessionSpecFactory.Filtered(filters)

    # =========================================================================
    # Workspace Enumeration (used by WorkspaceStage)
    # =========================================================================

    def _enumerate_workspaces(self, home: str) -> list[str]:
        """
        List all workspaces in a home.

        This combines workspaces from all agents (Claude, Codex, Gemini)
        in the specified home.

        Args:
            home: Home identifier (e.g., "local", "wsl:Ubuntu", "remote:user@host").

        Returns:
            Sorted list of unique workspace paths.

        Raises:
            ValueError: If SSH connection fails for remote homes.
        """
        return self._inventory.list_workspaces(home)

    def _materialize_scope_without_sessions(self, scope: TemplateScope) -> ConcreteScope:
        """
        Convert a template scope to a concrete scope without loading sessions.

        Used for fast metadata-only commands (e.g., home list) to avoid
        expensive session scans while still preserving workspace identity.
        """
        from agent_history.scope.types import ConcreteRecord, ScopeRecord
        from agent_history.utils.workspace_ref import build_workspace_ref

        concrete: ConcreteScope = []

        for record in scope:
            if not isinstance(record, ScopeRecord):
                continue
            if not isinstance(record.home, HomeSpecConcrete):
                continue
            if not isinstance(record.workspace, WorkspaceSpecConcrete):
                continue

            ref = build_workspace_ref(record.workspace.path)
            concrete.append(
                ConcreteRecord(
                    home=record.home.home,
                    workspace=ref.key,
                    workspace_key=ref.key,
                    workspace_display=ref.display,
                    sessions=[],
                )
            )

        return concrete

    def _enumerate_claude_workspaces(self, home: str) -> list[str]:
        """
        Enumerate workspaces from Claude's projects directory.

        Claude stores session directories with encoded workspace names.
        Each directory name is decoded to get the actual workspace path.

        Args:
            home: Home identifier.

        Returns:
            List of workspace paths found in Claude's projects.
        """
        from agent_history.utils.paths import normalize_workspace_name

        workspaces: list[str] = []

        # Use strategy pattern for home-specific directory resolution
        resolver = get_resolver_for_home(home)
        claude_dir = resolver.get_claude_dir(self.context)

        if not claude_dir or not claude_dir.exists():
            return workspaces

        for entry in claude_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                # Decode the directory name to get workspace path
                workspace = normalize_workspace_name(entry.name, verify_local=True)
                workspaces.append(workspace)

        return workspaces

    def _enumerate_codex_workspaces(self, home: str) -> list[str]:
        """
        Enumerate workspaces from Codex sessions.

        Codex stores workspace information in session metadata.
        This requires scanning the sessions or reading an index.

        Args:
            home: Home identifier.

        Returns:
            List of workspace paths found in Codex sessions.
        """
        workspaces: list[str] = []

        # Use strategy pattern for home-specific directory resolution
        resolver = get_resolver_for_home(home)
        codex_dir = resolver.get_codex_dir(self.context)

        if not codex_dir:
            return workspaces

        # Get all Codex sessions and extract unique workspaces
        codex_sessions = self._load_codex_sessions_for_home(home)
        seen: set[str] = set()
        for session in codex_sessions:
            ws = session.get("workspace_readable") or session.get("workspace", "")
            if ws and ws not in seen:
                seen.add(ws)
                workspaces.append(ws)

        return workspaces

    def _enumerate_gemini_workspaces(self, home: str) -> list[str]:
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
        workspaces: list[str] = []

        # Use strategy pattern for home-specific directory resolution
        resolver = get_resolver_for_home(home)
        gemini_dir = resolver.get_gemini_dir(self.context)

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

    # =========================================================================
    # Session Loading (used by SessionCache)
    # =========================================================================

    def _load_claude_sessions_for_home(self, home: str) -> list[SessionDict]:
        """
        Load all Claude sessions for a home (not filtered by workspace).

        Internal method used by the session cache.

        Args:
            home: Home identifier.

        Returns:
            List of all session dictionaries in the home.
        """
        # Use strategy pattern for home-specific directory resolution
        return self._inventory.list_sessions(home, agent="claude")

    def _load_codex_sessions_for_home(self, home: str) -> list[SessionDict]:
        """
        Load all Codex sessions for a home (not filtered by workspace).

        Internal method used by the session cache.

        Args:
            home: Home identifier.

        Returns:
            List of all session dictionaries in the home.
        """
        # Use strategy pattern for home-specific directory resolution
        return self._inventory.list_sessions(home, agent="codex")

    def _load_gemini_sessions_for_home(self, home: str) -> list[SessionDict]:
        """
        Load all Gemini sessions for a home (not filtered by workspace).

        Internal method used by the session cache.

        Args:
            home: Home identifier.

        Returns:
            List of all session dictionaries in the home.
        """
        # Use strategy pattern for home-specific directory resolution
        return self._inventory.list_sessions(home, agent="gemini")

    # =========================================================================
    # Delegate methods for backward compatibility with tests
    # These delegate to the appropriate stage modules
    # =========================================================================

    def _match_workspaces(self, home: str, pattern: str, match_type: MatchType) -> list[str]:
        """
        Match workspaces against a pattern with specified semantics.

        This method is kept for backward compatibility with tests that patch
        _enumerate_workspaces on the resolver. It uses self._enumerate_workspaces
        directly rather than delegating to avoid patching issues.

        Args:
            home: Home identifier to search in.
            pattern: Pattern to match against.
            match_type: How to interpret the pattern.

        Returns:
            List of matching workspace paths.
        """
        import fnmatch

        all_workspaces = self._enumerate_workspaces(home)
        normalized_pattern = pattern
        if match_type in (MatchType.EXACT, MatchType.PREFIX):
            from agent_history.utils.workspace_ref import build_workspace_ref

            normalized_pattern = build_workspace_ref(pattern).key

        if match_type == MatchType.EXACT:
            return [ws for ws in all_workspaces if ws == normalized_pattern]
        elif match_type == MatchType.PREFIX:
            return [ws for ws in all_workspaces if ws.startswith(normalized_pattern)]
        elif match_type == MatchType.CONTAINS:
            pattern_lower = pattern.lower()
            result = []
            for ws in all_workspaces:
                ws_lower = ws.lower()
                if pattern_lower in ws_lower:
                    result.append(ws)
                elif pattern_lower in ws_lower.replace("/", "-"):
                    result.append(ws)
            return result
        elif match_type == MatchType.GLOB:
            return [ws for ws in all_workspaces if fnmatch.fnmatch(ws, pattern)]
        else:
            return [ws for ws in all_workspaces if ws == pattern]

    def _expand_home_spec(self, spec: HomeSpec) -> tuple[list[str], ResolutionError | None]:
        """
        Expand a HomeSpec to a list of concrete home strings.

        Delegates to HomeStage._expand_home_spec.

        Args:
            spec: HomeSpec to expand.

        Returns:
            Tuple of:
            - List of concrete home identifiers
            - Error if expansion failed (or None)
        """
        return self._home_stage._expand_home_spec(spec)

    def _expand_workspace_spec(
        self, spec: WorkspaceSpec, home: str
    ) -> tuple[list[str], ResolutionError | None]:
        """
        Expand a WorkspaceSpec to a list of concrete workspace paths.

        Delegates to WorkspaceStage._expand_workspace_spec.

        Args:
            spec: WorkspaceSpec to expand.
            home: Home identifier (needed for enumeration).

        Returns:
            Tuple of:
            - List of concrete workspace paths
            - Error if expansion failed (or None)
        """
        return self._workspace_stage._expand_workspace_spec(spec, home)

    def _collect_sessions(
        self, home: str, workspace: str, session_spec: SessionSpec
    ) -> list[SessionDict]:
        """
        Collect sessions for a specific (home, workspace) pair.

        Uses EXACT workspace matching. This method is kept for backward
        compatibility with tests.

        Args:
            home: Concrete home identifier.
            workspace: Concrete workspace path.
            session_spec: SessionSpec for filtering.

        Returns:
            List of session dictionaries matching the criteria.
        """
        from agent_history.backends.registry import iter_backends
        from agent_history.scope.types import SessionSpecAll, SessionSpecFiltered

        all_sessions: list[SessionDict] = []
        for backend in iter_backends():
            collector = getattr(self, f"_collect_{backend.id}_sessions", None)
            if collector is None:
                all_sessions.extend(self._collect_backend_sessions(home, workspace, backend.id))
            else:
                all_sessions.extend(collector(home, workspace))

        # Filter to EXACT workspace match only
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
        if isinstance(session_spec, SessionSpecAll):
            return sessions
        elif isinstance(session_spec, SessionSpecFiltered):
            filters = session_spec.filters
            result = sessions

            def _to_date(value: Any) -> Any:
                return value.date() if hasattr(value, "date") else value

            if filters.agent:
                result = [s for s in result if s.get("agent") == filters.agent]
            if filters.since:
                result = [
                    s
                    for s in result
                    if s.get("modified") and _to_date(s.get("modified")) >= _to_date(filters.since)
                ]
            if filters.until:
                result = [
                    s
                    for s in result
                    if s.get("modified") and _to_date(s.get("modified")) <= _to_date(filters.until)
                ]
            if filters.min_messages is not None:
                result = [s for s in result if s.get("message_count", 0) >= filters.min_messages]
            return result
        else:
            return sessions

    def _collect_backend_sessions(
        self, home: str, workspace: str, agent_id: str
    ) -> list[SessionDict]:
        """Collect sessions for a registered backend by exact workspace."""
        all_sessions = self._inventory.list_sessions(home, agent=agent_id)
        return [
            s
            for s in all_sessions
            if (
                s.get("workspace_key", "") == workspace
                or s.get("workspace_readable", "") == workspace
                or s.get("workspace", "") == workspace
            )
        ]

    def _collect_claude_sessions(self, home: str, workspace: str) -> list[SessionDict]:
        """
        Collect Claude sessions for a specific (home, workspace) pair.

        This method can be mocked in tests to inject session data.

        Args:
            home: Home identifier.
            workspace: Workspace path to filter by (EXACT match).

        Returns:
            List of session dictionaries for the workspace.
        """
        all_sessions = self._load_claude_sessions_for_home(home)
        return [
            s
            for s in all_sessions
            if (
                s.get("workspace_key") == workspace
                or (s.get("workspace_readable") or s.get("workspace", "")) == workspace
            )
        ]

    def _collect_codex_sessions(self, home: str, workspace: str) -> list[SessionDict]:
        """
        Collect Codex sessions for a specific (home, workspace) pair.

        This method can be mocked in tests to inject session data.

        Args:
            home: Home identifier.
            workspace: Workspace path to filter by (EXACT match).

        Returns:
            List of session dictionaries for the workspace.
        """
        all_sessions = self._load_codex_sessions_for_home(home)
        return [
            s
            for s in all_sessions
            if (
                s.get("workspace_key") == workspace
                or (s.get("workspace_readable") or s.get("workspace", "")) == workspace
            )
        ]

    def _collect_gemini_sessions(self, home: str, workspace: str) -> list[SessionDict]:
        """
        Collect Gemini sessions for a specific (home, workspace) pair.

        This method can be mocked in tests to inject session data.

        Args:
            home: Home identifier.
            workspace: Workspace path to filter by (EXACT match).

        Returns:
            List of session dictionaries for the workspace.
        """
        all_sessions = self._load_gemini_sessions_for_home(home)
        return [
            s
            for s in all_sessions
            if (
                s.get("workspace_key", "") == workspace
                or s.get("workspace_readable", "") == workspace
                or s.get("workspace", "") == workspace
            )
        ]

    def _collect_pi_sessions(self, home: str, workspace: str) -> list[SessionDict]:
        """Collect Pi sessions for a specific (home, workspace) pair."""
        return self._collect_backend_sessions(home, workspace, "pi")

    def _resolve_projects(
        self, scope: TemplateScope
    ) -> tuple[TemplateScope, list[ResolutionError]]:
        """
        Expand ProjectRecords to ScopeRecords using project configuration (Stage 1).

        Delegates to ProjectStage.resolve.
        """
        return self._project_stage.resolve(scope)

    def _resolve_homes(self, scope: TemplateScope) -> tuple[TemplateScope, list[ResolutionError]]:
        """
        Resolve HomeSpecs to concrete home strings (Stage 2).

        Delegates to HomeStage.resolve.
        """
        return self._home_stage.resolve(scope)

    def _resolve_workspaces(
        self, scope: TemplateScope
    ) -> tuple[TemplateScope, list[ResolutionError]]:
        """
        Resolve WorkspaceSpecs to concrete workspace paths (Stage 3).

        This implementation uses the resolver's own _enumerate_workspaces
        (patchable by tests) rather than delegating to the stage module.
        """
        from agent_history.backends.gemini import gemini_get_path_for_hash
        from agent_history.scope.types import (
            HomeSpecConcrete,
            WorkspaceSpecAll,
            WorkspaceSpecCurrent,
            WorkspaceSpecEncoded,
            WorkspaceSpecHash,
            WorkspaceSpecPath,
            WorkspaceSpecPattern,
            WorkspaceSpecProject,
        )
        from agent_history.utils.paths import normalize_workspace_name

        result: TemplateScope = []
        errors: list[ResolutionError] = []

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
            spec = record.workspace
            workspaces: list[str] = []
            ws_error: ResolutionError | None = None

            if isinstance(spec, WorkspaceSpecAll):
                try:
                    workspaces = self._enumerate_workspaces(home)
                except ValueError as e:
                    # SSH connection error for remote homes
                    ws_error = ResolutionError(
                        stage="workspace",
                        spec=spec,
                        reason=str(e),
                        suggestions=[],
                    )
            elif isinstance(spec, WorkspaceSpecCurrent):
                if self.context.cwd_workspace:
                    workspaces = [self.context.cwd_workspace]
                else:
                    ws_error = ResolutionError(
                        stage="workspace",
                        spec=spec,
                        reason="Not in a recognized workspace",
                        suggestions=["Use --aw to list all workspaces or specify a pattern"],
                    )
            elif isinstance(spec, WorkspaceSpecProject):
                ws_error = ResolutionError(
                    stage="workspace",
                    spec=spec,
                    reason="Unresolved project reference in workspace expansion",
                    suggestions=["Ensure project resolution runs first"],
                )
            elif isinstance(spec, WorkspaceSpecPath):
                workspaces = [spec.path]
            elif isinstance(spec, WorkspaceSpecEncoded):
                decoded = normalize_workspace_name(spec.encoded, verify_local=True)
                workspaces = [decoded]
            elif isinstance(spec, WorkspaceSpecPattern):
                try:
                    workspaces = self._match_workspaces(home, spec.pattern, spec.match_type)
                except ValueError as e:
                    # SSH connection error for remote homes
                    ws_error = ResolutionError(
                        stage="workspace",
                        spec=spec,
                        reason=str(e),
                        suggestions=[],
                    )
            elif isinstance(spec, WorkspaceSpecHash):
                resolved = gemini_get_path_for_hash(spec.hash)
                if resolved:
                    workspaces = [resolved]
                else:
                    ws_error = ResolutionError(
                        stage="workspace",
                        spec=spec,
                        reason=f"Could not resolve hash '{spec.hash}'",
                        suggestions=[],
                    )
            elif isinstance(spec, WorkspaceSpecConcrete):
                workspaces = [spec.path]
            else:
                ws_error = ResolutionError(
                    stage="workspace",
                    spec=spec,
                    reason=f"Unknown WorkspaceSpec type: {type(spec).__name__}",
                    suggestions=[],
                )

            if ws_error:
                errors.append(ws_error)
                continue

            for ws in workspaces:
                result.append(
                    ScopeRecord(
                        home=record.home,
                        workspace=WorkspaceSpecFactory.Concrete(ws),
                        sessions=record.sessions,
                    )
                )

        return result, errors

    def _resolve_sessions(
        self, scope: TemplateScope
    ) -> tuple[ConcreteScope, list[ResolutionError]]:
        """
        Collect sessions for each (home, workspace) pair (Stage 4).

        Delegates to SessionStage.resolve. This is the external-facing method.
        """
        return self._session_stage.resolve(scope)

    def _resolve_sessions_internal(
        self, scope: TemplateScope
    ) -> tuple[ConcreteScope, list[ResolutionError]]:
        """
        Internal session collection that uses resolver's own methods.

        This method is used by the pipeline to allow test patching of
        _collect_claude_sessions, _collect_codex_sessions, etc.
        """
        from agent_history.scope.types import (
            ConcreteRecord,
            HomeSpecConcrete,
        )

        result: ConcreteScope = []
        errors: list[ResolutionError] = []

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
            from agent_history.utils.workspace_ref import build_workspace_ref

            workspace = record.workspace.path
            workspace_ref = build_workspace_ref(workspace)
            workspace_key = workspace_ref.key
            workspace_display = workspace_ref.display

            # Use the resolver's own _collect_sessions which uses
            # _collect_claude_sessions, etc. (patchable by tests)
            sessions = self._collect_sessions(home, workspace_key, record.sessions)

            # Always include the workspace record, even without sessions
            # This is important for remote workspaces where we may not have
            # implemented session listing yet, but still want to list workspaces
            result.append(
                ConcreteRecord(
                    home=home,
                    workspace=workspace_key,
                    workspace_key=workspace_key,
                    workspace_display=workspace_display,
                    sessions=sessions,
                )
            )

        return result, errors
