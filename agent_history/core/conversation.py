"""Conversation graph analysis utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class ConversationGraph:
    """Represents the structure of a conversation with potential forks."""

    messages: List[Dict[str, Any]]
    uuid_to_msg: Dict[str, Dict[str, Any]]
    uuid_to_children: Dict[str, List[str]]
    fork_points: List[str]
    branches: List[Dict[str, Any]]
    is_linear: bool


def analyze_conversation_graph(messages: List[Dict[str, Any]]) -> ConversationGraph:
    """Analyze conversation structure to detect forks and branches."""
    from collections import defaultdict

    uuid_to_msg = {msg["uuid"]: msg for msg in messages if msg.get("uuid")}
    uuid_to_children: Dict[str, List[str]] = defaultdict(list)

    for msg in messages:
        parent = msg.get("parentUuid")
        if parent:
            uuid_to_children[parent].append(msg["uuid"])

    fork_points = [parent for parent, children in uuid_to_children.items() if len(children) > 1]

    branches: List[Dict[str, Any]] = []
    for fork_uuid in fork_points:
        parent_msg = uuid_to_msg.get(fork_uuid)
        children = uuid_to_children[fork_uuid]

        branch_info: Dict[str, Any] = {
            "fork_uuid": fork_uuid,
            "fork_timestamp": parent_msg.get("timestamp") if parent_msg else None,
            "fork_type": parent_msg.get("role") if parent_msg else None,
            "branches": [],
        }

        for child_uuid in children:
            child_msg = uuid_to_msg.get(child_uuid)
            if child_msg:
                branch_info["branches"].append(
                    {
                        "uuid": child_uuid,
                        "timestamp": child_msg.get("timestamp"),
                        "type": child_msg.get("role"),
                    }
                )

        branches.append(branch_info)

    return ConversationGraph(
        messages=messages,
        uuid_to_msg=uuid_to_msg,
        uuid_to_children=dict(uuid_to_children),
        fork_points=fork_points,
        branches=branches,
        is_linear=len(fork_points) == 0,
    )


def generate_graph_summary(graph: ConversationGraph) -> List[str]:
    """Generate markdown summary of conversation graph structure."""
    if graph.is_linear:
        return []

    lines = ["", "### Conversation Structure", ""]
    lines.append(
        f"This conversation has **{len(graph.fork_points)} fork point(s)** "
        f"where the conversation branched into multiple paths."
    )
    lines.append("")

    for i, branch_info in enumerate(graph.branches, 1):
        fork_uuid = branch_info["fork_uuid"]
        fork_ts = branch_info.get("fork_timestamp")
        fork_type = branch_info.get("fork_type")

        lines.append(f"**Fork {i}** at {fork_type or 'message'} `{fork_uuid[:8]}...`")
        if fork_ts:
            lines.append(f"- Fork time: {fork_ts}")
        lines.append(f"- Branches: {len(branch_info['branches'])}")

        for j, branch in enumerate(branch_info["branches"], 1):
            branch_uuid = branch.get("uuid", "")
            branch_ts = branch.get("timestamp")
            branch_type = branch.get("type")
            lines.append(
                f"  - Branch {j}: [{branch_type} `{branch_uuid[:8]}...`](#msg-{branch_uuid}) "
                f"({branch_ts})"
            )
        lines.append("")

    return lines


def generate_mermaid_graph(graph: ConversationGraph, max_nodes: int = 50) -> List[str]:
    """Generate Mermaid diagram of conversation graph."""
    if graph.is_linear or not graph.fork_points:
        return []

    lines = ["", "### Conversation Graph", ""]
    lines.append("```mermaid")
    lines.append("graph TD")

    relevant_uuids: set[str] = set()
    for fork_uuid in graph.fork_points:
        relevant_uuids.add(fork_uuid)
        for child_uuid in graph.uuid_to_children.get(fork_uuid, []):
            relevant_uuids.add(child_uuid)
            for grandchild in graph.uuid_to_children.get(child_uuid, [])[:2]:
                relevant_uuids.add(grandchild)

    truncated = list(relevant_uuids)[:max_nodes]
    for uuid in truncated:
        msg = graph.uuid_to_msg.get(uuid)
        if msg:
            role = msg.get("role", "?")[0].upper()
            short_id = uuid[:6]
            lines.append(f'    {short_id}["{role}: {short_id}"]')

    for uuid in truncated:
        msg = graph.uuid_to_msg.get(uuid)
        parent = msg.get("parentUuid") if msg else None
        if parent:
            parent_short = None
            for u in truncated:
                if u == parent or u.startswith(parent[:6]):
                    parent_short = u[:6]
                    break
            if parent_short:
                lines.append(f"    {parent_short} --> {uuid[:6]}")

    for fork_uuid in graph.fork_points:
        if fork_uuid in truncated or any(u.startswith(fork_uuid[:6]) for u in truncated):
            lines.append(f"    style {fork_uuid[:6]} fill:#ff9,stroke:#f66")

    lines.append("```")
    lines.append("")
    return lines
