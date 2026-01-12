"""Handlers for resource verbs that were previously stubbed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.handlers.export import SessionExportHandler
from agent_history.handlers.list import HomeListHandler, WorkspaceListHandler
from agent_history.handlers.stats import SessionStatsHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope
from agent_history.storage.config import load_config, save_config
from agent_history.utils.paths import decode_workspace_path, encode_workspace_path


def _read_messages_from_file(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".json":
        from agent_history.backends.gemini import gemini_read_json_messages

        messages, _ = gemini_read_json_messages(path)
        return messages

    from agent_history.backends.claude import read_jsonl_messages

    return read_jsonl_messages(path)


class SessionShowHandler(VerbHandler):
    """Handler for 'session show' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        target = verb_args.get("session_id")
        if not target:
            return CommandResult(
                success=False,
                data={"error": "missing_session_id"},
                data_type="error",
                errors=["session show requires a session id or file path"],
            )

        path = Path(target)
        if path.exists():
            try:
                messages = _read_messages_from_file(path)
                return CommandResult(
                    success=True,
                    data={
                        "file": str(path),
                        "filename": path.name,
                        "message_count": len(messages),
                    },
                    data_type="session_show",
                )
            except (OSError, json.JSONDecodeError) as exc:
                return CommandResult(
                    success=False,
                    data={"error": "read_failed"},
                    data_type="error",
                    errors=[str(exc)],
                )

        # Fall back to searching the resolved scope
        for record in scope:
            for session in record.sessions:
                if target in (
                    session.get("filename"),
                    session.get("id"),
                    session.get("session_id"),
                ):
                    payload = dict(session)
                    payload["home"] = record.home
                    payload["workspace"] = record.workspace
                    return CommandResult(success=True, data=payload, data_type="session_show")

        return CommandResult(
            success=False,
            data={"error": "session_not_found"},
            data_type="error",
            errors=[f"No session found for {target}"],
        )


class WorkspaceShowHandler(VerbHandler):
    """Handler for 'ws show' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        handler = WorkspaceListHandler()
        aggregated = handler._aggregate_workspaces(scope)
        if not aggregated:
            return CommandResult(
                success=False,
                data={"error": "workspace_not_found"},
                data_type="error",
                errors=["No matching workspace found"],
            )
        workspace_list = list(aggregated.values())
        return CommandResult(success=True, data=workspace_list, data_type="workspace_list")


class WorkspaceExportHandler(VerbHandler):
    """Handler for 'ws export' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        return SessionExportHandler().execute(scope, verb_args, output_args)


class WorkspaceStatsHandler(VerbHandler):
    """Handler for 'ws stats' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        return SessionStatsHandler().execute(scope, verb_args, output_args)


class HomeShowHandler(VerbHandler):
    """Handler for 'home show' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        handler = HomeListHandler()
        known_homes = handler._enumerate_known_homes()
        aggregated = handler._aggregate_homes(scope, known_homes)
        name = verb_args.get("name")
        if name:
            home = aggregated.get(name)
            if not home:
                return CommandResult(
                    success=False,
                    data={"error": "home_not_found"},
                    data_type="error",
                    errors=[f"No home found for {name}"],
                )
            return CommandResult(success=True, data=[home], data_type="home_list")
        return CommandResult(success=True, data=list(aggregated.values()), data_type="home_list")


class HomeExportHandler(VerbHandler):
    """Handler for 'home export' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        return SessionExportHandler().execute(scope, verb_args, output_args)


class HomeStatsHandler(VerbHandler):
    """Handler for 'home stats' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        return SessionStatsHandler().execute(scope, verb_args, output_args)


class ProjectAddHandler(VerbHandler):
    """Handler for 'project add' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        name = verb_args.get("name")
        if not name:
            return CommandResult(
                success=False,
                data={"error": "missing_project"},
                data_type="error",
                errors=["Project name is required"],
            )

        workspaces_by_home: Dict[str, List[str]] = {}
        for record in scope:
            workspaces_by_home.setdefault(record.home, [])
            if record.workspace not in workspaces_by_home[record.home]:
                workspaces_by_home[record.home].append(record.workspace)

        if not workspaces_by_home:
            explicit = verb_args.get("workspaces") or []
            if explicit:
                workspaces_by_home["local"] = list(explicit)

        if not workspaces_by_home:
            return CommandResult(
                success=False,
                data={"error": "missing_workspace"},
                data_type="error",
                errors=["At least one workspace is required"],
            )

        config = load_config()
        projects = config.get("projects", {})
        project_def = projects.setdefault(name, {})

        from agent_history.utils.paths import decode_workspace_path

        added = 0
        for home_key, workspaces in workspaces_by_home.items():
            workspace_list = project_def.setdefault(home_key, [])
            for workspace in workspaces:
                decoded = decode_workspace_path(workspace, verify_local=False)
                if decoded not in workspace_list:
                    workspace_list.append(decoded)
                    added += 1

        config["projects"] = projects
        save_config(config)
        return CommandResult(
            success=True,
            data={
                "project": name,
                "added": added,
                "workspaces": project_def,
            },
            data_type="project_update",
        )


class ProjectRemoveHandler(VerbHandler):
    """Handler for 'project remove' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        name = verb_args.get("name")
        workspace = verb_args.get("workspace")
        if not name:
            return CommandResult(
                success=False,
                data={"error": "missing_project"},
                data_type="error",
                errors=["Project name is required"],
            )

        home_key = "local"
        if verb_args.get("wsl"):
            home_key = "wsl"
        elif verb_args.get("windows"):
            home_key = "windows"

        config = load_config()
        projects = config.get("projects", {})
        project_def = projects.get(name)
        if not project_def:
            return CommandResult(
                success=False,
                data={"error": "project_not_found"},
                data_type="error",
                errors=[f"Project not found: {name}"],
            )

        removed = 0
        if workspace:
            decoded = decode_workspace_path(workspace, verify_local=False)
            encoded = encode_workspace_path(decoded)
            workspaces = project_def.get(home_key, [])
            if decoded in workspaces or encoded in workspaces:
                workspaces = [ws for ws in workspaces if ws not in (decoded, encoded)]
                project_def[home_key] = workspaces
                removed = 1

            if not project_def.get(home_key):
                project_def.pop(home_key, None)

            if not project_def:
                projects.pop(name, None)
        else:
            projects.pop(name, None)
            removed = 1

        config["projects"] = projects
        save_config(config)
        return CommandResult(
            success=True,
            data={"project": name, "removed": removed},
            data_type="project_update",
        )


class ProjectExportHandler(VerbHandler):
    """Handler for 'project export' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        return SessionExportHandler().execute(scope, verb_args, output_args)
