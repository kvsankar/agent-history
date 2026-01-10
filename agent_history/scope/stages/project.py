"""
Stage 1: Project Resolution - Expand ProjectRecords to ScopeRecords.

This stage looks up project definitions and expands each ProjectRecord
into multiple ScopeRecords - one for each (home, workspace) pair
defined in the project configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Tuple

from agent_history.scope.context import ResolutionError
from agent_history.scope.types import (
    HomeSpecFactory,
    ProjectRecord,
    ScopeRecord,
    TemplateScope,
    WorkspaceSpecFactory,
)

if TYPE_CHECKING:
    from agent_history.scope.context import ResolutionContext


class ProjectStage:
    """
    Stage 1: Expand ProjectRecords to ScopeRecords using project configuration.
    """

    def __init__(self, context: ResolutionContext):
        """
        Initialize the project stage with a resolution context.

        Args:
            context: Resolution context containing project configuration.
        """
        self.context = context

    def resolve(self, scope: TemplateScope) -> Tuple[TemplateScope, List[ResolutionError]]:
        """
        Expand ProjectRecords to ScopeRecords using project configuration.

        This stage looks up project definitions and expands each ProjectRecord
        into multiple ScopeRecords - one for each (home, workspace) pair
        defined in the project configuration.

        Args:
            scope: Template scope that may contain ProjectRecords.

        Returns:
            Tuple of:
            - Updated template scope with ProjectRecords expanded
            - List of errors (e.g., project not found)
        """
        result: TemplateScope = []
        errors: List[ResolutionError] = []

        for record in scope:
            if isinstance(record, ProjectRecord):
                # Look up project definition
                project_def = self.context.project_config.get(record.project)

                if not project_def:
                    errors.append(
                        ResolutionError(
                            stage="project",
                            spec=record,
                            reason=f"Project '{record.project}' not found in configuration",
                            suggestions=list(self.context.project_config.keys()),
                        )
                    )
                    continue

                # Expand project to scope records
                # Project definition format: {home: [workspace1, workspace2, ...], ...}
                for home_key, workspaces in project_def.items():
                    if isinstance(workspaces, list):
                        for ws in workspaces:
                            result.append(
                                ScopeRecord(
                                    home=HomeSpecFactory.Concrete(home_key),
                                    # Use Path spec for exact workspace from project definition
                                    workspace=WorkspaceSpecFactory.Path(ws),
                                    sessions=record.sessions,
                                )
                            )
                    else:
                        # Single workspace as string
                        result.append(
                            ScopeRecord(
                                home=HomeSpecFactory.Concrete(home_key),
                                workspace=WorkspaceSpecFactory.Path(workspaces),
                                sessions=record.sessions,
                            )
                        )
            else:
                # Pass through ScopeRecords unchanged
                result.append(record)

        return result, errors
