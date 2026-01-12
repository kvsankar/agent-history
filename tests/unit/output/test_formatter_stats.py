from __future__ import annotations

from agent_history.output.formatter import TableFormatter


def test_stats_workspace_display_map_used_in_table() -> None:
    formatter = TableFormatter(width=120)
    stats = {
        "sessions": 1,
        "messages": 2,
        "total_sessions": 1,
        "total_messages": 2,
        "by_workspace": {"abc123def456": {"sessions": 1}},
    }
    metadata = {
        "group_by": ["workspace"],
        "workspace_display_map": {"abc123def456": "/home/user/project"},
    }

    output = formatter.format(stats, "stats", metadata)
    assert "/home/user/project" in output
    assert "abc123def456" not in output
