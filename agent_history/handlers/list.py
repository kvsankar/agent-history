"""List handlers for session, workspace, and home commands.

This module provides handlers for listing resources resolved by the scope
resolution pipeline. Each handler receives an already-resolved ConcreteScope
with EXACT workspace matching - the handlers do NOT do pattern matching.

The key architectural principle is that scope resolution (with exact matching)
happens before the handler runs. Handlers only format and output the results.

See docs/design-v2/pipeline-architecture.md for the complete specification.
See docs/design-v2/code-reuse-mapping.md for code reuse details.
"""

from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.types import HomeDict, SessionDict, WorkspaceDict
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope
from agent_history.utils.platform import AGENT_CLAUDE, AGENT_CODEX, AGENT_GEMINI


class SessionListHandler(VerbHandler):
    """Handle 'session list' command.

    Lists sessions from a resolved scope. The scope has already been
    resolved with EXACT workspace matching by the ScopeResolver.

    This handler:
    1. Flattens the ConcreteScope to a list of session dicts
    2. Adds home/workspace context to each session
    3. Sorts by modification time (newest first)
    4. Returns the session list for output formatting

    The handler does NOT do any pattern matching - that's done by the resolver.
    """

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """List sessions from resolved scope.

        The scope is already resolved with EXACT matching - just flatten and format.

        Args:
            scope: Resolved ConcreteScope with sessions.
            verb_args: Verb-specific arguments (e.g., sort options, counts).
            output_args: Output formatting options.

        Returns:
            CommandResult with session list data.
        """
        # Flatten scope to session list
        sessions = self._flatten_sessions(scope)

        # Populate message counts if --counts flag is set
        if verb_args.get("counts", False):
            self._populate_message_counts(sessions)

        # Sort by modified time (newest first)
        sessions.sort(key=lambda s: s.get("modified") or datetime.min, reverse=True)

        # Collect unique homes and workspaces for metadata
        homes = set()
        workspaces = set()
        for record in scope:
            homes.add(record.home)
            workspaces.add(record.workspace)

        return CommandResult(
            success=True,
            data=sessions,
            data_type="session_list",
            metadata={
                "total_count": len(sessions),
                "homes": sorted(homes),
                "workspaces": sorted(workspaces),
                "record_count": len(scope),
            },
        )

    def _flatten_sessions(self, scope: ConcreteScope) -> List[SessionDict]:
        """Flatten ConcreteScope to list of session dicts.

        Each session dict is augmented with home and workspace context
        from its parent ConcreteRecord.

        Args:
            scope: ConcreteScope to flatten.

        Returns:
            List of session dictionaries with home/workspace context.
        """
        sessions = []
        for record in scope:
            for session in record.sessions:
                # Add home/workspace context to each session
                session_with_context = dict(session)
                session_with_context["home"] = record.home
                session_with_context["workspace"] = record.workspace
                # Ensure workspace_readable is set for display
                if "workspace_readable" not in session_with_context:
                    session_with_context["workspace_readable"] = record.workspace
                sessions.append(session_with_context)
        return sessions

    def _populate_message_counts(self, sessions: List[SessionDict]) -> None:
        """Populate message_count for sessions that have it skipped.

        When scope resolution loads sessions with skip_message_count=True,
        the message_count field is 0 and message_count_skipped is True.
        This method counts messages for such sessions.

        Args:
            sessions: List of session dicts to update in place.
        """
        for session in sessions:
            # Skip if message count was already computed
            if not session.get("message_count_skipped", False):
                continue

            file_path = session.get("file")
            if not file_path:
                continue

            if isinstance(file_path, str):
                file_path = Path(file_path)

            if not file_path.exists():
                continue

            # Count messages based on agent type
            agent = session.get("agent", AGENT_CLAUDE)
            try:
                if agent == AGENT_GEMINI:
                    from agent_history.backends.gemini import gemini_count_messages

                    session["message_count"] = gemini_count_messages(file_path)
                elif agent == AGENT_CODEX:
                    from agent_history.backends.codex import codex_count_messages

                    session["message_count"] = codex_count_messages(file_path)
                else:
                    # Claude - use the internal count function
                    from agent_history.backends.claude import _count_file_messages

                    session["message_count"] = _count_file_messages(
                        file_path, skip_count=False, use_cached_counts=True
                    )
                session["message_count_skipped"] = False
            except Exception:
                # Keep the 0 count if there's an error
                pass


class WorkspaceListHandler(VerbHandler):
    """Handle 'ws list' command.

    Lists unique workspaces from a resolved scope, aggregating session
    counts and status for each workspace.

    This handler:
    1. Aggregates sessions by workspace
    2. Computes summary statistics (session count, last modified)
    3. Returns workspace summary for output formatting

    The handler does NOT do any pattern matching - that's done by the resolver.
    """

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """List workspaces from resolved scope.

        Aggregates sessions by workspace and provides summary statistics.

        Args:
            scope: Resolved ConcreteScope with sessions.
            verb_args: Verb-specific arguments.
            output_args: Output formatting options.

        Returns:
            CommandResult with workspace list data.
        """
        # Aggregate by (home, workspace) pair
        workspaces = self._aggregate_workspaces(scope)

        # Convert to list and sort by last modified (newest first)
        workspace_list = sorted(
            workspaces.values(), key=lambda w: w.get("last_modified") or datetime.min, reverse=True
        )

        # Collect unique homes for metadata
        homes = set()
        for record in scope:
            homes.add(record.home)

        return CommandResult(
            success=True,
            data=workspace_list,
            data_type="workspace_list",
            metadata={
                "total_count": len(workspace_list),
                "homes": sorted(homes),
                "total_sessions": sum(w.get("session_count", 0) for w in workspace_list),
            },
        )

    def _aggregate_workspaces(self, scope: ConcreteScope) -> Dict[str, WorkspaceDict]:
        """Aggregate sessions by workspace.

        Groups all sessions by (home, workspace) and computes summary
        statistics for each group.

        Args:
            scope: ConcreteScope to aggregate.

        Returns:
            Dictionary mapping (home:workspace) key to workspace summary dict.
        """
        # Use OrderedDict to preserve insertion order
        workspaces: Dict[str, WorkspaceDict] = OrderedDict()

        for record in scope:
            # Create unique key for (home, workspace) pair
            key = f"{record.home}:{record.workspace}"

            if key not in workspaces:
                # Compute workspace status
                status = self._check_workspace_status(record.workspace, record.home)

                workspaces[key] = {
                    "home": record.home,
                    "workspace": record.workspace,
                    "session_count": 0,
                    "sessions": 0,  # Alias for session_count (legacy compatibility)
                    "status": status,
                    "last_modified": None,
                    "agents": set(),
                }

            ws_data = workspaces[key]
            ws_data["session_count"] += len(record.sessions)
            ws_data["sessions"] += len(record.sessions)  # Keep in sync

            # Track latest modification time
            for session in record.sessions:
                modified = session.get("modified")
                if modified:
                    if ws_data["last_modified"] is None or modified > ws_data["last_modified"]:
                        ws_data["last_modified"] = modified

                # Track agents
                agent = session.get("agent")
                if agent:
                    ws_data["agents"].add(agent)

        # Convert agent sets to sorted lists for serialization
        for ws_data in workspaces.values():
            ws_data["agents"] = sorted(ws_data["agents"])

        return workspaces

    def _check_workspace_status(self, workspace_path: str, home: str) -> str:
        """Check if workspace path exists on filesystem.

        Args:
            workspace_path: Decoded workspace path.
            home: Home identifier (for remote detection).

        Returns:
            'ok' if exists, 'missing' if not, 'unknown' if cannot determine.
        """
        import os
        import re
        from pathlib import Path

        # Clean path (remove any existing markers)
        clean_path = workspace_path.replace(" [missing]", "").strip()

        # For hashed paths, we don't know the original path
        if clean_path.startswith("[hash:"):
            return "unknown"
        # Heuristic: Gemini-style hash (no slashes, long hex string)
        if "/" not in clean_path and re.fullmatch(r"[0-9a-fA-F]{16,64}", clean_path):
            return "unknown"

        # For remote sources, we can't easily check - assume ok
        if home.startswith("remote:") or home == "web":
            return "ok"

        # Use AGENT_HISTORY_HOME if set (for testing)
        agent_home = os.environ.get("AGENT_HISTORY_HOME")
        if agent_home:
            # In test mode, check under AGENT_HISTORY_HOME
            check_path = Path(agent_home) / clean_path.lstrip("/")
        else:
            check_path = Path(clean_path)

        return "ok" if check_path.exists() else "missing"


class HomeListHandler(VerbHandler):
    """Handle 'home list' command.

    Lists available homes (local, WSL, Windows, remote) with their status
    and session counts. Unlike session/workspace list commands, home list
    always includes known homes even if they have no sessions.

    This handler:
    1. Enumerates all known homes (local + detected WSL/Windows/remote)
    2. Aggregates session/workspace counts from the resolved scope
    3. Returns home summary for output formatting
    """

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """List homes with their status and session counts.

        Always includes "local" home. Includes WSL distributions, Windows users,
        and configured remote hosts when available.

        Args:
            scope: Resolved ConcreteScope with sessions (for aggregating counts).
            verb_args: Verb-specific arguments.
            output_args: Output formatting options.

        Returns:
            CommandResult with home list data.
        """
        # Get all known homes (always includes local, plus detected WSL/Windows/remote)
        known_homes = self._enumerate_known_homes()

        # Aggregate session/workspace counts from the scope
        homes = self._aggregate_homes(scope, known_homes)

        # Convert to list and sort: local first, then by type, then alphabetically
        home_list = sorted(
            homes.values(),
            key=lambda h: (
                0 if h.get("home") == "local" else 1,  # local first
                h.get("type", "z"),  # then by type
                h.get("home", ""),  # then alphabetically
            ),
        )

        return CommandResult(
            success=True,
            data=home_list,
            data_type="home_list",
            metadata={
                "total_count": len(home_list),
                "total_workspaces": sum(h.get("workspace_count", 0) for h in home_list),
                "total_sessions": sum(h.get("session_count", 0) for h in home_list),
            },
        )

    def _enumerate_known_homes(self) -> Dict[str, HomeDict]:
        """Enumerate all known homes.

        Always includes "local". Detects WSL distributions (from Windows),
        Windows users (from WSL), and configured remote hosts.

        Returns:
            Dictionary mapping home identifier to home info dict.
        """
        from agent_history.storage.config import get_saved_homes
        from agent_history.utils.platform import (
            get_windows_users_with_claude,
            get_wsl_distributions,
            is_running_in_wsl,
        )

        homes: Dict[str, HomeDict] = OrderedDict()

        # Always include local home
        homes["local"] = {
            "home": "local",
            "type": "local",
            "status": "ok",
            "workspace_count": 0,
            "session_count": 0,
            "last_modified": None,
            "workspaces": set(),
            "agents": set(),
        }

        # Web home (Claude.ai web sessions)
        homes["web"] = {
            "home": "web",
            "type": "web",
            "status": "ok",
            "workspace_count": 0,
            "session_count": 0,
            "last_modified": None,
            "workspaces": set(),
            "agents": set(),
        }

        # WSL distributions (available from Windows)
        try:
            wsl_distros = get_wsl_distributions()
            for distro in wsl_distros:
                name = distro.get("name")
                if name:
                    home_key = f"wsl:{name}"
                    homes[home_key] = {
                        "home": home_key,
                        "type": "wsl",
                        "status": "ok",
                        "workspace_count": 0,
                        "session_count": 0,
                        "last_modified": None,
                        "workspaces": set(),
                        "agents": set(),
                    }
        except Exception:
            pass

        # Windows users (available from WSL)
        if is_running_in_wsl():
            try:
                windows_users = get_windows_users_with_claude()
                for user in windows_users:
                    username = user.get("username")
                    if username:
                        home_key = f"windows:{username}"
                        homes[home_key] = {
                            "home": home_key,
                            "type": "windows",
                            "status": "ok",
                            "workspace_count": 0,
                            "session_count": 0,
                            "last_modified": None,
                            "workspaces": set(),
                            "agents": set(),
                        }
            except Exception:
                pass

        # Configured remote hosts
        try:
            saved_homes = get_saved_homes()
            for home_spec in saved_homes:
                if isinstance(home_spec, str):
                    if home_spec == "web":
                        continue
                    if home_spec.startswith("remote:"):
                        name = home_spec[7:]
                        home_key = f"remote:{name}"
                    elif not home_spec.startswith(("wsl:", "windows:", "local")):
                        home_key = f"remote:{home_spec}"
                    else:
                        continue
                elif isinstance(home_spec, dict) and home_spec.get("name"):
                    name = home_spec["name"]
                    if name == "web":
                        continue
                    if name.startswith("remote:"):
                        home_key = name
                    elif not name.startswith(("wsl:", "windows:", "local")):
                        home_key = f"remote:{name}"
                    else:
                        continue
                else:
                    continue

                if home_key not in homes:
                    homes[home_key] = {
                        "home": home_key,
                        "type": "remote",
                        "status": "configured",
                        "workspace_count": 0,
                        "session_count": 0,
                        "last_modified": None,
                        "workspaces": set(),
                        "agents": set(),
                    }
        except Exception:
            pass

        return homes

    def _aggregate_homes(
        self, scope: ConcreteScope, known_homes: Dict[str, HomeDict]
    ) -> Dict[str, HomeDict]:
        """Aggregate workspaces and sessions by home.

        Updates the known_homes dictionary with session/workspace counts
        from the resolved scope. Also adds any homes found in the scope
        that weren't in known_homes.

        Args:
            scope: ConcreteScope to aggregate.
            known_homes: Pre-populated dictionary of known homes.

        Returns:
            Updated dictionary mapping home identifier to home summary dict.
        """
        homes = known_homes

        for record in scope:
            home_key = record.home

            if home_key not in homes:
                # Home found in scope but not in known homes - add it
                home_type = "unknown"
                if home_key == "local":
                    home_type = "local"
                elif home_key.startswith("wsl:"):
                    home_type = "wsl"
                elif home_key.startswith("windows:"):
                    home_type = "windows"
                elif home_key.startswith("remote:"):
                    home_type = "remote"

                homes[home_key] = {
                    "home": home_key,
                    "type": home_type,
                    "status": "ok",
                    "workspace_count": 0,
                    "session_count": 0,
                    "last_modified": None,
                    "workspaces": set(),
                    "agents": set(),
                }

            home_data = homes[home_key]

            # Track unique workspaces
            if record.workspace not in home_data["workspaces"]:
                home_data["workspaces"].add(record.workspace)
                home_data["workspace_count"] += 1

            # Count sessions
            home_data["session_count"] += len(record.sessions)

            # Track latest modification time and agents
            for session in record.sessions:
                modified = session.get("modified")
                if modified:
                    if home_data["last_modified"] is None or modified > home_data["last_modified"]:
                        home_data["last_modified"] = modified

                agent = session.get("agent")
                if agent:
                    home_data["agents"].add(agent)

        # Convert sets to sorted lists for serialization
        for home_data in homes.values():
            home_data["workspaces"] = sorted(home_data["workspaces"])
            home_data["agents"] = sorted(home_data["agents"])

        return homes


class GeminiIndexHandler(VerbHandler):
    """Handle 'gemini-index' command.

    Manages the Gemini session index for faster lookups.

    This handler:
    1. Lists indexed sessions (default)
    2. Adds new sessions to the index (--add)
    3. Rebuilds the index from scratch (--rebuild)
    """

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """Execute gemini-index command.

        Args:
            scope: Resolved ConcreteScope (may be empty for index operations).
            verb_args: Verb-specific arguments (add_paths, rebuild, list_index, full_hash).
            output_args: Output formatting options.

        Returns:
            CommandResult with index status.
        """
        from agent_history.backends.gemini import (
            gemini_add_paths_to_index,
            gemini_load_hash_index,
            gemini_rebuild_hash_index,
            HASH_DISPLAY_LEN,
        )

        add_paths = verb_args.get("add_paths")
        rebuild_mode = verb_args.get("rebuild", False)
        full_hash = verb_args.get("full_hash", False)

        if rebuild_mode:
            result = gemini_rebuild_hash_index()
            return CommandResult(
                success=True,
                data={"action": "rebuild", **result},
                data_type="gemini_index",
                metadata={"message": "Gemini index rebuilt"},
            )
        elif add_paths is not None:
            # --add was specified (even with empty list means use current directory)
            paths = add_paths if add_paths else ["."]
            path_objects = [Path(p).expanduser().resolve() for p in paths]

            result = gemini_add_paths_to_index(path_objects)

            return CommandResult(
                success=True,
                data={
                    "action": "add",
                    "added": result["added"],
                    "existing": result["existing"],
                    "no_sessions": result["no_sessions"],
                    "mappings": result["mappings"],
                },
                data_type="gemini_index",
                metadata={
                    "message": f"Added {result['added']} path(s) to index"
                },
            )
        else:
            # Default: list/show index status
            index = gemini_load_hash_index()
            mappings = index.get("hashes", {})

            formatted_mappings = []
            for project_hash, path in sorted(mappings.items(), key=lambda x: x[1]):
                display_hash = project_hash if full_hash else project_hash[:HASH_DISPLAY_LEN]
                formatted_mappings.append({
                    "hash": display_hash,
                    "path": path,
                })

            return CommandResult(
                success=True,
                data={
                    "action": "list",
                    "indexed_sessions": len(mappings),
                    "mappings": formatted_mappings,
                },
                data_type="gemini_index",
                metadata={
                    "message": f"Found {len(mappings)} indexed path(s)"
                    if mappings else "Hash index is empty. Use 'gemini-index --add <path>' to add mappings."
                },
            )
