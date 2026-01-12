"""
Stage 2: Home Resolution - Resolve HomeSpecs to concrete home strings.

This stage expands symbolic home specifications to actual home
identifiers like "local", "wsl:Ubuntu", "remote:dev", etc.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, List, Optional, Tuple

from agent_history.scope.context import ResolutionError
from agent_history.scope.types import (
    HomeSpec,
    HomeSpecAll,
    HomeSpecCategory,
    HomeSpecCategoryItem,
    HomeSpecConcrete,
    HomeSpecCurrent,
    HomeSpecFactory,
    HomeSpecLocal,
    HomeSpecMultiple,
    ProjectRecord,
    ScopeRecord,
    TemplateScope,
)

if TYPE_CHECKING:
    from agent_history.scope.context import ResolutionContext


class HomeStage:
    """
    Stage 2: Resolve HomeSpecs to concrete home strings.

    HomeSpec.All -> all available homes
    HomeSpec.Local -> ["local"]
    HomeSpec.Current -> home containing CWD
    HomeSpec.Category("wsl") -> ["wsl:Ubuntu", "wsl:Debian", ...]
    HomeSpec.CategoryItem("wsl", "Ubuntu") -> ["wsl:Ubuntu"]
    HomeSpec.Concrete(x) -> [x] (already resolved)
    """

    def __init__(self, context: ResolutionContext):
        """
        Initialize the home stage with a resolution context.

        Args:
            context: Resolution context containing available homes.
        """
        self.context = context

    def resolve(self, scope: TemplateScope) -> Tuple[TemplateScope, List[ResolutionError]]:
        """
        Resolve HomeSpecs to concrete home strings.

        Args:
            scope: Template scope with HomeSpecs to resolve.

        Returns:
            Tuple of:
            - Updated template scope with concrete homes
            - List of errors (e.g., no homes in category)
        """
        result: TemplateScope = []
        errors: List[ResolutionError] = []

        for record in scope:
            if isinstance(record, ProjectRecord):
                # ProjectRecords should have been expanded in Stage 1
                errors.append(
                    ResolutionError(
                        stage="home",
                        spec=record,
                        reason="Unresolved project record in home resolution stage",
                        suggestions=["Ensure project resolution runs before home resolution"],
                    )
                )
                continue

            # Expand the home spec
            homes, home_error = self._expand_home_spec(record.home)

            if home_error:
                errors.append(home_error)
                continue

            # Create a record for each resolved home
            for home in homes:
                result.append(
                    ScopeRecord(
                        home=HomeSpecFactory.Concrete(home),
                        workspace=record.workspace,
                        sessions=record.sessions,
                    )
                )

        return result, errors

    def _expand_home_spec(self, spec: HomeSpec) -> Tuple[List[str], Optional[ResolutionError]]:
        """
        Expand a HomeSpec to a list of concrete home strings.

        Args:
            spec: HomeSpec to expand.

        Returns:
            Tuple of:
            - List of concrete home identifiers
            - Error if expansion failed (or None)
        """
        if isinstance(spec, HomeSpecAll):
            return self._get_all_homes(), None

        elif isinstance(spec, HomeSpecLocal):
            return ["local"], None

        elif isinstance(spec, HomeSpecCurrent):
            if self.context.cwd_home:
                return [self.context.cwd_home], None
            # Default to local if not in a known workspace
            return ["local"], None

        elif isinstance(spec, HomeSpecCategory):
            items = self.context.available_homes.get(spec.category, [])
            if not items:
                # In test environments (AGENT_HISTORY_HOME set), return empty instead of error
                # This allows the command to proceed with available homes only
                if os.environ.get("AGENT_HISTORY_HOME"):
                    return [], None
                return [], ResolutionError(
                    stage="home",
                    spec=spec,
                    reason=f"No {spec.category} homes available",
                    suggestions=list(self.context.available_homes.keys()),
                )
            return [f"{spec.category}:{item}" for item in items], None

        elif isinstance(spec, HomeSpecCategoryItem):
            return [f"{spec.category}:{spec.item}"], None

        elif isinstance(spec, HomeSpecConcrete):
            return [spec.home], None

        elif isinstance(spec, HomeSpecMultiple):
            # Return all homes from the tuple
            return list(spec.homes), None

        else:
            return [], ResolutionError(
                stage="home",
                spec=spec,
                reason=f"Unknown HomeSpec type: {type(spec).__name__}",
                suggestions=[],
            )

    def _get_all_homes(self) -> List[str]:
        """
        Get all available homes.

        Returns:
            List of all home identifiers (local + all category items).
        """
        homes = ["local"]

        for category, items in self.context.available_homes.items():
            for item in items:
                homes.append(f"{category}:{item}")

        return homes
