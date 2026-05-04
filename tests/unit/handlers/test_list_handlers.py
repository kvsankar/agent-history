from __future__ import annotations

from datetime import datetime

from agent_history.handlers.list import WorkspaceListHandler
from agent_history.scope.types import ConcreteRecord


def test_workspace_list_uses_display_for_hash() -> None:
    handler = WorkspaceListHandler()
    record = ConcreteRecord(
        home="local",
        workspace="abc123def456",
        workspace_key="abc123def456",
        workspace_display="[hash:abc123de]",
        sessions=[{"modified": datetime(2025, 1, 1, 12, 0)}],
    )

    workspaces = handler._aggregate_workspaces([record])
    assert len(workspaces) == 1
    ws_data = next(iter(workspaces.values()))

    assert ws_data["workspace"] == "[hash:abc123de]"
    assert ws_data["workspace_key"] == "abc123def456"
    assert ws_data["workspace_display"] == "[hash:abc123de]"
    assert ws_data["status"] == "unknown"
