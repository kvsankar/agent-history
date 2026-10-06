"""Which session a transcript file is, and which session started it.

The stats readers, the lineage model and the export use these rules, so a
session has one ID everywhere.

Claude writes each line with the sessionId of the conversation it belongs
to, so one file can hold several:

- A continued session starts with lines copied from the earlier session.
  Its own ID is the one in its file name.
- A main session whose lines carry no sessionId is named by its file name.
- A sub-agent's lines carry its parent's sessionId, and its file sits in
  ``<parent>/subagents/`` (older versions wrote ``agent-*.jsonl`` next to
  the sessions). The parent is the session whose folder holds the file,
  when the lines name that session or carry no sessionId; otherwise it is
  the last sessionId, because the parent was continued while the agent
  ran. Agent IDs are short and repeat across sessions, so a sub-agent's
  session ID is ``<parent>:<agentId>``.

A Codex rollout's first session_meta describes it. A spawned sub-agent or a
forked rollout later repeats the session_meta of the thread it came from.

Gemini CLI writes a sub-agent's chat to ``chats/<parent>/<agentId>.jsonl``,
with ``kind: "subagent"`` in its metadata. Its own sessionId is the agentId,
and the folder names the session that started it.
"""

from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Sequence

_AGENT_PREFIX = "agent-"

# Sub-agent transcripts below a Claude session folder. A workflow's folder
# also holds journal.jsonl, which records workflow steps and is no session.
CLAUDE_SUBAGENT_PATTERNS = (
    "subagents/agent-*.jsonl",
    "subagents/workflows/*/agent-*.jsonl",
)
# Transcripts of context compaction, which are not sub-agent sessions.
CLAUDE_COMPACTION_PREFIX = "agent-acompact-"


def claude_subagent_files(directory: Path, session_folders: str = "") -> Iterator[Path]:
    """Sub-agent transcripts below ``directory``, without compaction transcripts.

    ``directory`` is a session folder, or a workspace folder with
    ``session_folders="*"``.
    """
    for pattern in CLAUDE_SUBAGENT_PATTERNS:
        full_pattern = f"{session_folders}/{pattern}" if session_folders else pattern
        for path in directory.glob(full_pattern):
            if not path.name.startswith(CLAUDE_COMPACTION_PREFIX):
                yield path


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


def claude_main_session_id(jsonl_file: Path, session_ids: Sequence[str]) -> str:
    """ID of a main (not sub-agent) Claude transcript.

    A file whose lines carry no sessionId is named by its file name.
    """
    stem = claude_file_stem(jsonl_file)
    if stem in session_ids:
        return stem
    return session_ids[0] if session_ids else stem


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


def gemini_subagent_parent(chat_file: Path) -> Optional[str]:
    """Session that started a Gemini sub-agent chat ``chats/<parent>/<agentId>.jsonl``.

    The folder is the parent's session ID with each character other than a letter,
    digit, ``_`` or ``-`` replaced by ``_``, which leaves the usual UUIDs unchanged.
    """
    folder = chat_file.parent
    return folder.name if folder.parent.name == "chats" else None


def gemini_session_identity(
    chat_file: Path, kind: Any, session_id: Optional[str]
) -> Dict[str, Any]:
    """session_id, parent_session_id and is_agent of one Gemini chat file.

    ``kind`` is the chat metadata's ``kind`` and ``session_id`` its ``sessionId``.
    A chat is a sub-agent's when it is ``"subagent"`` or the file lies in a folder
    below ``chats``. A sub-agent's short ID can repeat across sessions, so, as for
    Claude, its session ID is ``<parent>:<sessionId>`` when the parent is known.
    """
    parent = gemini_subagent_parent(chat_file)
    is_agent = kind == "subagent" or parent is not None
    if is_agent and session_id:
        session_id = claude_subagent_session_id(parent, session_id)
    return {"session_id": session_id, "parent_session_id": parent, "is_agent": is_agent}


def codex_meta_parent(payload: Dict[str, Any]) -> Optional[str]:
    """Parent thread named in a Codex session_meta payload, if any."""
    source = payload.get("source")
    subagent = source.get("subagent") if isinstance(source, dict) else None
    spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
    spawn_parent = spawn.get("parent_thread_id") if isinstance(spawn, dict) else None
    return payload.get("parent_thread_id") or spawn_parent or payload.get("forked_from_id")


def codex_meta_is_subagent(payload: Dict[str, Any]) -> bool:
    """Whether a session_meta payload describes a thread another thread started.

    Its source names a sub-agent: a spawned agent (``thread_spawn``) or
    another kind, such as a review thread (``{"other": "guardian"}``).
    """
    source = payload.get("source")
    return (isinstance(source, dict) and "subagent" in source) or payload.get(
        "thread_source"
    ) == "subagent"


class CodexSessionMeta:
    """Fold a rollout's session_meta payloads into its identity.

    The first payload with an ID describes the rollout. A later payload
    only names the parent, when the first did not and its ID differs.
    """

    def __init__(self) -> None:
        self.payload: Optional[Dict[str, Any]] = None
        self.parent_session_id: Optional[str] = None

    @property
    def session_id(self) -> Optional[str]:
        return self.payload.get("id") if self.payload else None

    @property
    def is_subagent(self) -> bool:
        return codex_meta_is_subagent(self.payload) if self.payload else False

    def add(self, payload: Any) -> bool:
        """Add one session_meta payload; True when it now describes the rollout."""
        if not isinstance(payload, dict):
            return False
        if self.session_id is None:
            self.payload = payload
            self.parent_session_id = codex_meta_parent(payload)
            return True
        later_id = payload.get("id")
        if self.parent_session_id is None and later_id and later_id != self.session_id:
            self.parent_session_id = later_id
        return False
