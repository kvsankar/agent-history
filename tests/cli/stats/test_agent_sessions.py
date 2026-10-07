"""Stats count sub-agent sessions as the metrics database marks them."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from agent_history.core.stats import overlay_metrics
from tests.helpers.cli import assert_cli_success, run_cli_subprocess

pytestmark = pytest.mark.stats

PARENT = "11111111-1111-4111-8111-111111111111"


def _write_line(path: Path, entry: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")


def _user_line(uuid: str, agent_id: str | None = None) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "type": "user",
        "sessionId": PARENT,
        "uuid": uuid,
        "timestamp": "2026-06-09T10:00:00.000Z",
        "message": {"role": "user", "content": "hello"},
    }
    if agent_id:
        entry.update({"agentId": agent_id, "isSidechain": True})
    return entry


def test_stats_count_main_and_agent_sessions(stats_test_home: Dict[str, Any]) -> None:
    workspace = stats_test_home["claude_dir"] / "-home-alex-project"
    _write_line(workspace / f"{PARENT}.jsonl", _user_line("u-1"))
    _write_line(workspace / PARENT / "subagents" / "agent-a1.jsonl", _user_line("u-2", "a1"))

    result = run_cli_subprocess(
        ["session", "stats", "--sync", "--aw", "--format", "json"],
        env=stats_test_home["env"],
        cwd=stats_test_home["path"],
    )

    assert_cli_success(result, "session stats should succeed")
    stats = json.loads(result.stdout)
    assert (stats["sessions"], stats["main_sessions"], stats["agent_sessions"]) == (2, 1, 1)


def test_overlay_takes_agent_sessions_from_the_database() -> None:
    """Sessions the database has not read yet count as main sessions."""
    stats = {"sessions": 5, "main_sessions": 5, "agent_sessions": 0, "tokens": {}}

    overlaid = overlay_metrics(stats, {"agent_sessions": 2})

    assert (overlaid["main_sessions"], overlaid["agent_sessions"]) == (3, 2)
