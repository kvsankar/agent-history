"""Stats sync requirements for tool/time breakdowns."""

import json
from typing import Any, Dict

import pytest

from tests.helpers.cli import assert_cli_success, run_cli_subprocess


pytestmark = pytest.mark.stats


def _load_json_output(result) -> Any:
    output = (result.stdout or "").strip()
    assert output, f"Expected JSON output, got empty stdout:\nstderr: {result.stderr}"
    return json.loads(output)


def test_session_stats_by_tool_uses_synced_metrics(
    stats_test_home: Dict[str, Any],
    setup_claude_stats_fixture: Any,
) -> None:
    """--by tool should include tool usage from synced metrics."""
    result = run_cli_subprocess(
        ["session", "stats", "--sync", "--aw", "--by", "tool", "--format", "json"],
        env=stats_test_home["env"],
        cwd=stats_test_home["path"],
    )

    assert_cli_success(result, "session stats --by tool should succeed")
    stats = _load_json_output(result)
    tools = stats.get("by_tool", {})
    assert "Read" in tools, "Expected tool usage counts for Read in stats output"


def test_session_stats_time_tracking_uses_synced_metrics(
    stats_test_home: Dict[str, Any],
    setup_claude_stats_fixture: Any,
) -> None:
    """--time should report non-zero tracked work time after sync."""
    result = run_cli_subprocess(
        ["session", "stats", "--sync", "--aw", "--time", "--format", "json"],
        env=stats_test_home["env"],
        cwd=stats_test_home["path"],
    )

    assert_cli_success(result, "session stats --time should succeed")
    stats = _load_json_output(result)
    time_stats = stats.get("time_stats", {})
    total_seconds = time_stats.get("total_duration_seconds", 0)
    assert total_seconds > 0, "Expected non-zero tracked time in stats output"
