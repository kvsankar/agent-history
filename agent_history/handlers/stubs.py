"""Handlers for resource verbs that were previously stubbed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_history.core.workspaces import build_workspace_metadata
from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.handlers.export import SessionExportHandler
from agent_history.handlers.list import HomeListHandler, WorkspaceListHandler
from agent_history.handlers.stats import SessionStatsHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope
from agent_history.storage.config import load_config, save_config
from agent_history.utils.paths import decode_workspace_path
from agent_history.utils.workspace_ref import (
    WorkspaceContext,
    attach_workspace_context,
    build_workspace_ref,
)


def _read_messages_from_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        from agent_history.backends.gemini import gemini_read_json_messages

        messages, _ = gemini_read_json_messages(path)
        return messages

    from agent_history.backends.claude import read_jsonl_messages

    return read_jsonl_messages(path)


def _session_matches_target(session: dict[str, Any], target: str) -> bool:
    """Return True when target names the session by id, file name, or stem."""
    candidates: set[str] = set()
    for key in ("filename", "id", "session_id"):
        value = session.get(key)
        if value:
            candidates.add(str(value))
    file_value = session.get("file")
    if file_value:
        path = Path(str(file_value))
        candidates.add(str(file_value))
        candidates.add(path.name)
        candidates.add(path.stem)
    filename = session.get("filename")
    if filename:
        path = Path(str(filename))
        candidates.add(path.name)
        candidates.add(path.stem)

    if target in candidates:
        return True
    return len(target) >= 8 and any(candidate.startswith(target) for candidate in candidates)


class SessionShowHandler(VerbHandler):
    """Handler for 'session show' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
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
                    metadata={"workspace_display_map": {}},
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
                if _session_matches_target(session, target):
                    payload = dict(session)
                    payload.setdefault("workspace_raw", payload.get("workspace"))
                    context = WorkspaceContext.from_record(record)
                    attach_workspace_context(
                        payload,
                        context=context,
                    )
                    return CommandResult(
                        success=True,
                        data=payload,
                        data_type="session_show",
                        metadata=build_workspace_metadata([context]),
                    )

        return CommandResult(
            success=False,
            data={"error": "session_not_found"},
            data_type="error",
            errors=[f"No session found for {target}"],
        )


class WorkspaceShowHandler(VerbHandler):
    """Handler for 'ws show' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        handler = WorkspaceListHandler()
        result = handler.execute(scope, {}, output_args)
        if not result.data:
            return CommandResult(
                success=False,
                data={"error": "workspace_not_found"},
                data_type="error",
                errors=["No matching workspace found"],
            )
        return result


class WorkspaceExportHandler(VerbHandler):
    """Handler for 'ws export' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        return SessionExportHandler().execute(scope, verb_args, output_args)


class WorkspaceStatsHandler(VerbHandler):
    """Handler for 'ws stats' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        return SessionStatsHandler().execute(scope, verb_args, output_args)


class HomeShowHandler(VerbHandler):
    """Handler for 'home show' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        handler = HomeListHandler()
        result = handler.execute(scope, {}, output_args)
        name = verb_args.get("name")
        if name:
            home = None
            for item in result.data or []:
                if item.get("home") == name:
                    home = item
                    break
            if not home:
                return CommandResult(
                    success=False,
                    data={"error": "home_not_found"},
                    data_type="error",
                    errors=[f"No home found for {name}"],
                )
            return CommandResult(
                success=True,
                data=[home],
                data_type="home_list",
                metadata=result.metadata or {},
            )
        return result


class HomeExportHandler(VerbHandler):
    """Handler for 'home export' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        return SessionExportHandler().execute(scope, verb_args, output_args)


class HomeStatsHandler(VerbHandler):
    """Handler for 'home stats' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        return SessionStatsHandler().execute(scope, verb_args, output_args)


class ProjectAddHandler(VerbHandler):
    """Handler for 'project add' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        name = verb_args.get("name")
        if not name:
            return CommandResult(
                success=False,
                data={"error": "missing_project"},
                data_type="error",
                errors=["Project name is required"],
            )

        inventory_rows = verb_args.get("workspace_rows") or []
        workspaces_by_home = self._workspaces_from_inventory_rows(inventory_rows)
        if not inventory_rows:
            self._add_scope_workspaces(workspaces_by_home, scope)
        self._merge_explicit_workspaces(workspaces_by_home, verb_args.get("workspaces") or [])

        if not workspaces_by_home:
            return CommandResult(
                success=False,
                data={
                    "error": "no_matching_workspaces",
                    "project": name,
                },
                data_type="error",
                errors=["No matching workspaces found for project add"],
            )

        dry_run = bool(verb_args.get("dry_run"))
        config = load_config()
        projects = config.get("projects", {})
        project_def = self._normalized_project_def(projects.get(name, {}))
        added, existing, rows = self._apply_project_additions(
            project_def, workspaces_by_home, dry_run=dry_run
        )

        current_total = sum(len(workspaces) for workspaces in project_def.values())
        projected_total = current_total + (added if dry_run else 0)

        if dry_run:
            return CommandResult(
                success=True,
                data={
                    "project": name,
                    "dry_run": True,
                    "would_add": added,
                    "existing": existing,
                    "project_workspaces": projected_total,
                    "workspaces": rows,
                },
                data_type="project_update",
                warnings=["Dry run: project config was not updated."],
            )

        projects[name] = project_def

        config["projects"] = projects
        save_config(config)
        return CommandResult(
            success=True,
            data={
                "project": name,
                "dry_run": False,
                "added": added,
                "existing": existing,
                "project_workspaces": current_total,
                "workspaces": project_def,
                "resolved_workspaces": rows,
            },
            data_type="project_update",
        )

    def _add_scope_workspaces(
        self, workspaces_by_home: dict[str, dict[str, str]], scope: ConcreteScope
    ) -> None:
        for record in scope:
            if not record.sessions:
                continue
            context = WorkspaceContext.from_record(record)
            workspaces_by_home.setdefault(context.home, {})
            workspaces_by_home[context.home].setdefault(
                context.workspace_key, context.workspace_display
            )

    def _merge_explicit_workspaces(
        self, workspaces_by_home: dict[str, dict[str, str]], explicit: list[str]
    ) -> None:
        if not explicit:
            return
        if not workspaces_by_home:
            workspaces_by_home["local"] = {workspace: workspace for workspace in explicit}
            return

        normalized = {workspace.replace("\\", "/"): workspace for workspace in explicit}
        matched = set()
        for workspaces in workspaces_by_home.values():
            for key, value in list(workspaces.items()):
                norm_value = value.replace("\\", "/")
                if norm_value in normalized:
                    workspaces[key] = normalized[norm_value]
                    matched.add(norm_value)
        for norm_value, raw_value in normalized.items():
            if norm_value not in matched:
                workspaces_by_home.setdefault("local", {})
                workspaces_by_home["local"].setdefault(raw_value, raw_value)

    def _normalized_project_def(self, project_def: dict[str, Any]) -> dict[str, list[str]]:
        normalized_project: dict[str, list[str]] = {}
        for home, workspaces in project_def.items():
            values = workspaces if isinstance(workspaces, list) else [workspaces]
            seen_keys: set[str] = set()
            normalized_values: list[str] = []
            for value in values:
                ref = build_workspace_ref(str(value))
                if ref.key in seen_keys:
                    continue
                seen_keys.add(ref.key)
                normalized_values.append(ref.display)
            if normalized_values:
                normalized_project[home] = normalized_values
        return normalized_project

    def _apply_project_additions(
        self,
        project_def: dict[str, list[str]],
        workspaces_by_home: dict[str, dict[str, str]],
        *,
        dry_run: bool,
    ) -> tuple[int, int, list[dict[str, str]]]:
        from agent_history.utils.paths import decode_workspace_path

        added = 0
        existing = 0
        rows = []
        existing_keys_by_home = {
            home: {build_workspace_ref(workspace).key for workspace in workspaces}
            for home, workspaces in project_def.items()
        }
        for home_key, workspaces in workspaces_by_home.items():
            workspace_list = project_def.setdefault(home_key, [])
            existing_keys = existing_keys_by_home.setdefault(home_key, set())
            for workspace in workspaces.values():
                ref = build_workspace_ref(decode_workspace_path(workspace, verify_local=False))
                decoded = ref.display
                if ref.key not in existing_keys:
                    added += 1
                    status = "would_add" if dry_run else "added"
                    if not dry_run:
                        workspace_list.append(decoded)
                        existing_keys.add(ref.key)
                else:
                    existing += 1
                    status = "exists"
                rows.append({"home": home_key, "workspace": decoded, "status": status})
        return added, existing, rows

    def _workspaces_from_inventory_rows(
        self, rows: list[dict[str, Any]]
    ) -> dict[str, dict[str, str]]:
        workspaces_by_home: dict[str, dict[str, str]] = {}
        for row in rows:
            home = str(row.get("home") or "")
            workspace = str(
                row.get("workspace_display")
                or row.get("workspace")
                or row.get("workspace_key")
                or ""
            )
            if not home or not workspace:
                continue
            ref = build_workspace_ref(workspace)
            workspaces_by_home.setdefault(home, {})
            workspaces_by_home[home].setdefault(ref.key, ref.display)
        return workspaces_by_home


class ProjectRemoveHandler(VerbHandler):
    """Handler for 'project remove' command."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
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
            workspaces = project_def.get(home_key, [])
            kept: list[str] = []
            for ws in workspaces:
                if decode_workspace_path(ws, verify_local=False) == decoded:
                    removed += 1
                else:
                    kept.append(ws)
            if removed:
                if kept:
                    project_def[home_key] = kept
                else:
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
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        return SessionExportHandler().execute(scope, verb_args, output_args)
