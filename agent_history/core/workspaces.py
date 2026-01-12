"""Pure workspace aggregation helpers."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from agent_history.scope.types import ConcreteRecord
from agent_history.types import WorkspaceDict
from agent_history.utils.workspace_ref import WorkspaceContext

StatusLookup = Callable[[str, str], str]


def aggregate_workspaces(
    records: Iterable[ConcreteRecord],
    status_lookup: Optional[StatusLookup] = None,
) -> Dict[str, WorkspaceDict]:
    """Aggregate sessions by workspace across records."""
    workspaces: Dict[str, WorkspaceDict] = OrderedDict()

    for record in records:
        context = WorkspaceContext.from_record(record)
        key = f"{context.home}:{context.workspace_key}"

        if key not in workspaces:
            status = (
                status_lookup(context.workspace_display, context.home)
                if status_lookup
                else "unknown"
            )
            workspaces[key] = {
                "home": context.home,
                "workspace": context.workspace_display,
                "workspace_key": context.workspace_key,
                "workspace_display": context.workspace_display,
                "session_count": 0,
                "sessions": 0,
                "status": status,
                "last_modified": None,
                "agents": set(),
            }

        ws_data = workspaces[key]
        ws_data["session_count"] += len(record.sessions)
        ws_data["sessions"] += len(record.sessions)

        for session in record.sessions:
            modified = session.get("modified")
            if modified:
                if ws_data["last_modified"] is None or modified > ws_data["last_modified"]:
                    ws_data["last_modified"] = modified

            agent = session.get("agent")
            if agent:
                ws_data["agents"].add(agent)

    for ws_data in workspaces.values():
        ws_data["agents"] = sorted(ws_data["agents"])

    return workspaces


def build_workspace_rows(
    records: Iterable[ConcreteRecord],
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Build workspace rows and a display map for stats output."""
    rows: List[Dict[str, Any]] = []
    display_map: Dict[str, str] = {}

    for record in records:
        context = WorkspaceContext.from_record(record)
        display_map.setdefault(context.workspace_key, context.workspace_display)

        session_count = len(record.sessions)
        message_count = sum(s.get("message_count", 0) for s in record.sessions)
        rows.append(
            {
                "home": context.home,
                "workspace": context.workspace_display,
                "workspace_key": context.workspace_key,
                "workspace_display": context.workspace_display,
                "sessions": session_count,
                "messages": message_count,
            }
        )

    return rows, display_map


def build_workspace_metadata(
    contexts: Iterable[WorkspaceContext],
) -> Dict[str, Any]:
    """Build homes/workspaces metadata from workspace contexts."""
    homes: set[str] = set()
    workspaces: set[str] = set()
    display_map: Dict[str, str] = {}

    for context in contexts:
        homes.add(context.home)
        workspaces.add(context.workspace_display)
        display_map.setdefault(context.workspace_key, context.workspace_display)

    return {
        "homes": sorted(homes),
        "workspaces": sorted(workspaces),
        "workspace_display_map": display_map,
    }


def build_workspace_display_map(
    records: Iterable[ConcreteRecord],
) -> Dict[str, str]:
    """Build a mapping of workspace key to display name."""
    contexts = (WorkspaceContext.from_record(record) for record in records)
    return build_workspace_metadata(contexts)["workspace_display_map"]


def build_scope_metadata(
    records: Iterable[ConcreteRecord],
) -> Dict[str, Any]:
    """Build homes/workspaces metadata with display mapping."""
    contexts = (WorkspaceContext.from_record(record) for record in records)
    return build_workspace_metadata(contexts)
