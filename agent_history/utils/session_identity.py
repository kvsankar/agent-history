"""Which session a transcript file is, and which session started it.

The stats readers, the lineage model and the export use these rules, so a
session has one ID everywhere.

Claude writes each line with the sessionId of the conversation it belongs
to, so one file can hold several:

- A continued session starts with lines copied from the earlier session.
  Its own ID is the one in its file name.
- A sub-agent's lines carry its parent's sessionId, and its file sits in
  ``<parent>/subagents/`` (older versions wrote ``agent-*.jsonl`` next to
  the sessions). The parent is the session whose folder holds the file,
  when the lines name that session or carry no sessionId; otherwise it is
  the last sessionId, because the parent was continued while the agent
  ran. Agent IDs are short and repeat across sessions, so a sub-agent's
  session ID is ``<parent>:<agentId>``.

A Codex rollout's first session_meta describes it. A spawned sub-agent or a
forked rollout later repeats the session_meta of the thread it came from.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Sequence

_AGENT_PREFIX = "agent-"


def claude_file_stem(jsonl_file: Path) -> str:
    """File name without any extension (``abc.jsonl`` and ``abc.jsonl.gz`` give ``abc``)."""
    return jsonl_file.name.split(".")[0]


def claude_subagent_owner(jsonl_file: Path) -> Optional[str]:
    """Name of the session folder that holds ``<session>/subagents/.../agent-*.jsonl``."""
    parts = jsonl_file.parts
    for index in range(len(parts) - 2, 0, -1):
        if parts[index] == "subagents":
            return parts[index - 1]
    return None


def claude_is_subagent(jsonl_file: Path, agent_id: Optional[str]) -> bool:
    """Whether a Claude file is a sub-agent transcript."""
    return claude_file_stem(jsonl_file).startswith(_AGENT_PREFIX) or bool(agent_id)


def claude_agent_id(jsonl_file: Path, agent_id: Optional[str]) -> str:
    """The agentId from the lines, or else the one in an ``agent-<id>`` file name."""
    if agent_id:
        return agent_id
    stem = claude_file_stem(jsonl_file)
    return stem[len(_AGENT_PREFIX) :] if stem.startswith(_AGENT_PREFIX) else stem


def claude_main_session_id(jsonl_file: Path, session_ids: Sequence[str]) -> Optional[str]:
    """ID of a main (not sub-agent) Claude transcript."""
    stem = claude_file_stem(jsonl_file)
    if stem in session_ids:
        return stem
    return session_ids[0] if session_ids else None


def claude_subagent_parent(jsonl_file: Path, session_ids: Sequence[str]) -> Optional[str]:
    """Session that started a Claude sub-agent."""
    owner = claude_subagent_owner(jsonl_file)
    if owner and (owner in session_ids or not session_ids):
        return owner
    return session_ids[-1] if session_ids else None


def claude_subagent_session_id(parent: Optional[str], agent_id: str) -> str:
    """Session ID of a sub-agent: ``<parent>:<agentId>``, or the agentId alone without a parent."""
    return f"{parent}:{agent_id}" if parent else agent_id


def claude_session_identity(
    jsonl_file: Path, session_ids: Sequence[str], agent_id: Optional[str]
) -> Dict[str, Any]:
    """session_id, parent_session_id, is_agent and agent_id of one Claude file.

    ``session_ids`` are the distinct sessionIds of the file's lines in order,
    and ``agent_id`` is the first agentId, if any.
    """
    if not claude_is_subagent(jsonl_file, agent_id):
        return {
            "session_id": claude_main_session_id(jsonl_file, session_ids),
            "parent_session_id": None,
            "is_agent": False,
            "agent_id": None,
        }
    parent = claude_subagent_parent(jsonl_file, session_ids)
    own_agent_id = claude_agent_id(jsonl_file, agent_id)
    return {
        "session_id": claude_subagent_session_id(parent, own_agent_id),
        "parent_session_id": parent,
        "is_agent": True,
        "agent_id": own_agent_id,
    }
