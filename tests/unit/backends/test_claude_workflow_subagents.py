"""Sub-agents of a Claude workflow are sessions like other sub-agents.

Claude keeps them at ``<session>/subagents/workflows/<workflow>/agent-*.jsonl``,
beside a ``journal.jsonl`` that records workflow steps and is not a session.
Compaction transcripts (``agent-acompact-*``) stay out, as they do for
``<session>/subagents/``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from agent_history.backends.claude import get_workspace_sessions
from agent_history.backends.registry import get_backend
from agent_history.core.lineage import build_timeline_lineage
from agent_history.utils.platform import AGENT_CLAUDE

PARENT = "parent-session"
WORKSPACE = "-home-alex-project"


def _write_line(path: Path, entry: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    return path


def _claude_line(uuid: str, agent_id: str | None = None) -> dict:
    entry = {
        "type": "user",
        "sessionId": PARENT,
        "uuid": uuid,
        "timestamp": "2026-06-09T10:00:00.000Z",
        "message": {"role": "user", "content": "hello"},
    }
    if agent_id:
        entry.update({"agentId": agent_id, "isSidechain": True})
    return entry


def _projects(tmp_path: Path) -> Path:
    """A workspace with a session, a sub-agent and a workflow's sub-agent."""
    projects = tmp_path / "projects"
    workspace = projects / WORKSPACE
    _write_line(workspace / f"{PARENT}.jsonl", _claude_line("u-1"))
    subagents = workspace / PARENT / "subagents"
    _write_line(subagents / "agent-a1.jsonl", _claude_line("u-2", "a1"))
    _write_line(subagents / "agent-acompact-1.jsonl", _claude_line("u-3", "acompact-1"))
    workflow = subagents / "workflows" / "wf_1"
    _write_line(workflow / "agent-w1.jsonl", _claude_line("u-4", "w1"))
    _write_line(workflow / "agent-acompact-2.jsonl", _claude_line("u-5", "acompact-2"))
    _write_line(workflow / "journal.jsonl", {"type": "step"})
    return projects


EXPECTED = {f"{PARENT}.jsonl", "agent-a1.jsonl", "agent-w1.jsonl"}


def test_scanner_lists_workflow_sub_agents(tmp_path: Path) -> None:
    sessions = get_workspace_sessions(
        "*", projects_dir=_projects(tmp_path), skip_message_count=True
    )

    assert {Path(session["file"]).name for session in sessions} == EXPECTED


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None or shutil.which("python3") is None,
    reason="the remote listing script runs under bash and python3 on POSIX hosts",
)
def test_remote_listing_script_lists_workflow_sub_agents(tmp_path: Path) -> None:
    home = tmp_path / "home"
    shutil.copytree(_projects(tmp_path), home / ".claude" / "projects")
    backend = get_backend("claude")
    assert backend is not None
    assert backend.remote_list_sessions_command is not None

    result = subprocess.run(
        ["bash", "-c", backend.remote_list_sessions_command(WORKSPACE)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "HOME": str(home)},
    )

    listed = {Path(line.split("|")[0]).name for line in result.stdout.splitlines() if line}
    assert listed == EXPECTED


def test_lineage_finds_workflow_sub_agents_of_a_session(tmp_path: Path) -> None:
    parent = _projects(tmp_path) / WORKSPACE / f"{PARENT}.jsonl"
    session = {
        "agent": AGENT_CLAUDE,
        "file": parent,
        "filename": parent.name,
        "workspace": WORKSPACE,
        "workspace_readable": "/home/alex/project",
        "modified": datetime(2026, 6, 9, 10, 0, 0),
    }

    lineage = build_timeline_lineage([session], include_related=True)

    assert sorted(
        (record["kind"], record["session_id"])
        for record in lineage
        if record.get("kind") in ("main", "subagent")
    ) == [("main", PARENT), ("subagent", f"{PARENT}:a1"), ("subagent", f"{PARENT}:w1")]
