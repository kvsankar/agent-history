"""Project handlers for the resolution pipeline.

This module provides handlers for project-related commands:
- ProjectListHandler: List all configured projects
- ProjectShowHandler: Show details of a specific project
- ProjectStatsHandler: Show statistics for a project

See docs/design-v2/pipeline-architecture.md for the complete specification.
"""

from collections import defaultdict
from typing import Any, Dict, List

from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope
from agent_history.storage.config import load_config
from agent_history.utils.paths import decode_workspace_path
from agent_history.utils.workspace_ref import WorkspaceContext
from agent_history.core.workspaces import build_scope_metadata


class ProjectListHandler(VerbHandler):
    """Handle 'project list' command.

    Lists all configured projects with their workspace counts and
    optionally session counts.
    """

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """List all configured projects.

        Args:
            scope: Resolved scope (may be empty for project list).
            verb_args: Verb-specific arguments:
                - counts: bool - include session counts (slower)
            output_args: Output formatting options.

        Returns:
            CommandResult with project list data.
        """
        # Load project configuration
        config = load_config()
        projects_config = config.get("projects", {})

        # Build project list
        projects = []
        for name, definition in projects_config.items():
            # Collect all workspaces from the project definition
            all_workspaces = []
            for home_workspaces in definition.values():
                if isinstance(home_workspaces, list):
                    all_workspaces.extend(
                        decode_workspace_path(ws, verify_local=False) for ws in home_workspaces
                    )
                elif isinstance(home_workspaces, str):
                    all_workspaces.append(
                        decode_workspace_path(home_workspaces, verify_local=False)
                    )

            # Use v1-compatible field names: project, source, workspace
            project_info = {
                "project": name,
                "source": list(definition.keys()),
                "workspace": all_workspaces,
            }

            # Add session count if requested
            if verb_args.get("counts"):
                session_count = self._count_project_sessions(name, scope)
                project_info["session_count"] = session_count
            else:
                project_info["session_count"] = ""

            projects.append(project_info)

        # Sort by project name
        projects.sort(key=lambda p: p["project"])

        return CommandResult(
            success=True,
            data=projects,
            data_type="project_list",
            metadata={
                "total_count": len(projects),
            },
        )

    def _count_project_sessions(self, project_name: str, scope: ConcreteScope) -> int:
        """Count sessions for a project from resolved scope.

        Args:
            project_name: Name of the project.
            scope: Resolved ConcreteScope.

        Returns:
            Total session count for the project.
        """
        # The scope should already be filtered to this project
        return sum(len(record.sessions) for record in scope)


class ProjectShowHandler(VerbHandler):
    """Handle 'project show' command.

    Shows detailed information about a specific project including
    workspaces grouped by home and session counts.
    """

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """Show project details.

        Args:
            scope: Resolved scope for the project.
            verb_args: Verb-specific arguments:
                - name: str - project name (required)
            output_args: Output formatting options.

        Returns:
            CommandResult with project details.
        """
        project_name = verb_args.get("name")

        if not project_name:
            # Try to detect from scope or context
            return CommandResult(
                success=False,
                data=None,
                data_type="error",
                errors=["Project name not specified and current workspace is not in a project."],
            )

        # Load project configuration
        config = load_config()
        projects_config = config.get("projects", {})
        project_def = projects_config.get(project_name)

        if not project_def:
            return CommandResult(
                success=False,
                data=None,
                data_type="error",
                errors=[f"Project '{project_name}' not found."],
            )

        # Aggregate data from scope
        workspaces_by_home: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        total_sessions = 0
        metadata = build_scope_metadata(scope) if scope else {"homes": []}

        for record in scope:
            context = WorkspaceContext.from_record(record)
            workspace_info = {
                "workspace": context.workspace_display,
                "workspace_key": context.workspace_key,
                "workspace_display": context.workspace_display,
                "session_count": len(record.sessions),
            }
            workspaces_by_home[context.home].append(workspace_info)
            total_sessions += len(record.sessions)

        # If scope is empty, use project definition
        if not workspaces_by_home:
            for home, workspaces in project_def.items():
                if isinstance(workspaces, list):
                    for ws in workspaces:
                        decoded = decode_workspace_path(ws, verify_local=False)
                        workspaces_by_home[home].append(
                            {
                                "workspace": decoded,
                                "workspace_key": decoded,
                                "workspace_display": decoded,
                                "session_count": 0,
                            }
                        )
                elif isinstance(workspaces, str):
                    decoded = decode_workspace_path(workspaces, verify_local=False)
                    workspaces_by_home[home].append(
                        {
                            "workspace": decoded,
                            "workspace_key": decoded,
                            "workspace_display": decoded,
                            "session_count": 0,
                        }
                    )

        return CommandResult(
            success=True,
            data={
                "project": project_name,
                "workspaces_by_home": dict(workspaces_by_home),
                "total_sessions": total_sessions,
                "total_workspaces": sum(len(ws) for ws in workspaces_by_home.values()),
            },
            data_type="project_details",
            metadata={
                "homes": list(workspaces_by_home.keys()) or metadata.get("homes", []),
                "workspace_display_map": metadata.get("workspace_display_map", {}),
            },
        )


class ProjectStatsHandler(VerbHandler):
    """Handle 'project stats' command.

    Computes aggregate statistics for a project, similar to
    SessionStatsHandler but scoped to a specific project.
    """

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        """Compute statistics for a project.

        Args:
            scope: Resolved scope for the project.
            verb_args: Verb-specific arguments:
                - name: str - project name
                - by: str - grouping dimensions
                - time: bool - include time tracking
            output_args: Output formatting options.

        Returns:
            CommandResult with project statistics.
        """
        project_name = verb_args.get("name")

        if not project_name:
            return CommandResult(
                success=False,
                data=None,
                data_type="error",
                errors=["Project name not specified."],
            )
        from agent_history.handlers.stats import SessionStatsHandler

        result = SessionStatsHandler().execute(scope, verb_args, output_args)
        if isinstance(result.data, dict):
            result.data["project"] = project_name
        if isinstance(result.metadata, dict):
            result.metadata["project"] = project_name
        return result
