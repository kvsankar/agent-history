from __future__ import annotations

from datetime import datetime

from agent_history.core.workspaces import aggregate_workspaces, build_workspace_rows
from agent_history.scope.types import ConcreteRecord


def test_aggregate_workspaces_uses_display_and_status() -> None:
    record = ConcreteRecord(
        home="local",
        workspace="abc123def456",
        workspace_key="abc123def456",
        workspace_display="[hash:abc123de]",
        sessions=[{"modified": datetime(2025, 1, 1, 12, 0), "agent": "claude"}],
    )

    def status_lookup(workspace: str, home: str) -> str:
        assert workspace == "[hash:abc123de]"
        assert home == "local"
        return "unknown"

    workspaces = aggregate_workspaces([record], status_lookup=status_lookup)
    ws_data = next(iter(workspaces.values()))

    assert ws_data["workspace"] == "[hash:abc123de]"
    assert ws_data["workspace_key"] == "abc123def456"
    assert ws_data["status"] == "unknown"
    assert ws_data["session_count"] == 1
    assert ws_data["agents"] == ["claude"]


def test_build_workspace_rows_returns_display_map() -> None:
    record = ConcreteRecord(
        home="local",
        workspace="/home/user/project",
        workspace_key="/home/user/project",
        workspace_display="/home/user/project",
        sessions=[{"message_count": 2}],
    )

    rows, display_map = build_workspace_rows([record])
    assert len(rows) == 1
    assert rows[0]["workspace"] == "/home/user/project"
    assert rows[0]["sessions"] == 1
    assert rows[0]["messages"] == 2
    assert display_map["/home/user/project"] == "/home/user/project"
