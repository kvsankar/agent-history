"""Handlers for project tag commands."""

from __future__ import annotations

from typing import Any

from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope
from agent_history.storage.config import load_config, save_config
from agent_history.storage.project_tags import (
    add_project_tags,
    project_tags_for,
    remove_project_tags,
)


class TagListHandler(VerbHandler):
    """Handle `tag list`."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        config = load_config()
        projects = config.get("projects", {}) or {}
        requested_project = verb_args.get("project")
        if requested_project and requested_project not in projects:
            return CommandResult(
                success=False,
                data={"error": "project_not_found"},
                data_type="error",
                errors=[f"Project not found: {requested_project}"],
            )

        names = [requested_project] if requested_project else sorted(projects)
        rows = [
            {
                "project": project,
                "tags": project_tags_for(config, project),
            }
            for project in names
            if project
        ]
        return CommandResult(
            success=True,
            data=rows,
            data_type="tag_list",
            metadata={"total_count": len(rows)},
        )


class TagAddHandler(VerbHandler):
    """Handle `tag add`."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        project = verb_args.get("project")
        tags = verb_args.get("tags") or []
        config = load_config()
        if not project or project not in (config.get("projects") or {}):
            return CommandResult(
                success=False,
                data={"error": "project_not_found"},
                data_type="error",
                errors=[f"Project not found: {project or ''}".strip()],
            )
        if not tags:
            return CommandResult(
                success=False,
                data={"error": "missing_tag"},
                data_type="error",
                errors=["At least one tag is required"],
            )

        updated, added, existing = add_project_tags(config, project, tags)
        save_config(config)
        return CommandResult(
            success=True,
            data={
                "project": project,
                "tags": updated,
                "added": added,
                "existing": existing,
            },
            data_type="tag_update",
        )


class TagRemoveHandler(VerbHandler):
    """Handle `tag remove`."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        project = verb_args.get("project")
        tags = verb_args.get("tags") or []
        config = load_config()
        if not project or project not in (config.get("projects") or {}):
            return CommandResult(
                success=False,
                data={"error": "project_not_found"},
                data_type="error",
                errors=[f"Project not found: {project or ''}".strip()],
            )
        if not tags:
            return CommandResult(
                success=False,
                data={"error": "missing_tag"},
                data_type="error",
                errors=["At least one tag is required"],
            )

        updated, removed, missing = remove_project_tags(config, project, tags)
        save_config(config)
        return CommandResult(
            success=True,
            data={
                "project": project,
                "tags": updated,
                "removed": removed,
                "missing": missing,
            },
            data_type="tag_update",
        )
