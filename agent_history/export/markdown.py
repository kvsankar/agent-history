"""Markdown generation for session export.

This module provides functions to convert session messages to readable Markdown format.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_history.backends.claude import read_jsonl_messages
from agent_history.utils.platform import AGENT_CLAUDE, AGENT_CODEX, AGENT_GEMINI


def parse_jsonl_to_markdown(
    jsonl_file: Path,
    minimal: bool = False,
    messages: Optional[List[Dict[str, Any]]] = None,
    display_file: Optional[str] = None,
    show_graph: bool = True,
    agent_type: str = AGENT_CLAUDE,
) -> str:
    """Convert a Claude Code JSONL session file to readable Markdown.

    Args:
        jsonl_file: Path to the JSONL file.
        minimal: If True, omit metadata.
        messages: Pre-parsed messages (optional).
        display_file: File name to display in header.
        show_graph: If True, include conversation graph analysis.
        agent_type: Agent type (claude, codex, gemini).

    Returns:
        Markdown formatted string.
    """
    if messages is None:
        messages = read_jsonl_messages(jsonl_file)

    # Build header
    md_lines = generate_markdown_file_header(jsonl_file, messages, display_file, agent_type)

    md_lines.extend(["", "---", ""])

    # Build message index for parent references
    uuid_to_index = {msg["uuid"]: i for i, msg in enumerate(messages, 1) if msg.get("uuid")}

    # Generate message sections
    for i, msg in enumerate(messages, 1):
        md_lines.extend(generate_message_section(msg, i, minimal, uuid_to_index))

    return "\n".join(md_lines)


def _get_agent_header_title(agent_type: str) -> str:
    """Get the header title for the given agent type.

    Args:
        agent_type: Agent type (claude, codex, gemini).

    Returns:
        Header title string.
    """
    if agent_type == AGENT_CODEX:
        return "Codex Conversation"
    elif agent_type == AGENT_GEMINI:
        return "Gemini Conversation"
    else:
        return "Claude Code Session"


def generate_markdown_file_header(
    jsonl_file: Path,
    messages: List[Dict[str, Any]],
    display_file: Optional[str] = None,
    agent_type: str = AGENT_CLAUDE,
) -> List[str]:
    """Generate markdown header for a session file.

    Args:
        jsonl_file: Source file path.
        messages: List of messages.
        display_file: Override display filename.
        agent_type: Agent type (claude, codex, gemini).

    Returns:
        List of markdown header lines.
    """
    header_title = _get_agent_header_title(agent_type)

    # For Codex and Gemini, use simpler header format (no filename)
    if agent_type in (AGENT_CODEX, AGENT_GEMINI):
        lines = [f"# {header_title}", ""]
    else:
        display_name = display_file or jsonl_file.name
        lines = [f"# {header_title}: {display_name}", ""]

    if messages:
        first_ts = messages[0].get("timestamp", "")
        last_ts = messages[-1].get("timestamp", "") if len(messages) > 1 else ""
        if first_ts:
            lines.append(f"**Started:** {first_ts}")
        if last_ts:
            lines.append(f"**Ended:** {last_ts}")
        lines.append(f"**Messages:** {len(messages)}")

    return lines


def generate_message_section(
    msg: Dict[str, Any],
    index: int,
    minimal: bool,
    uuid_to_index: Dict[str, int],
) -> List[str]:
    """Generate markdown section for a single message.

    Args:
        msg: Message dictionary.
        index: Message index (1-based).
        minimal: If True, omit metadata.
        uuid_to_index: Mapping of UUID to message index.

    Returns:
        List of markdown lines for the message.
    """
    role = msg.get("role", "unknown")
    content = msg.get("content", "")
    timestamp = msg.get("timestamp", "")

    # Role emoji and header
    role_display = "User" if role == "user" else "Assistant"
    lines = [f"## Message {index}: {role_display}", ""]

    if timestamp:
        lines.append(f"*{timestamp}*")
        lines.append("")

    # Add content
    lines.append(content)
    lines.append("")

    # Add metadata if not minimal
    if not minimal:
        metadata_lines = generate_metadata_section(msg, uuid_to_index)
        if metadata_lines:
            lines.extend(metadata_lines)

    lines.append("---")
    lines.append("")

    return lines


def generate_metadata_section(
    msg: Dict[str, Any], uuid_to_index: Dict[str, int]
) -> List[str]:
    """Generate metadata section for a message.

    Args:
        msg: Message dictionary.
        uuid_to_index: Mapping of UUID to message index.

    Returns:
        List of metadata lines.
    """
    lines = []

    # Common metadata fields
    if msg.get("model"):
        lines.append(f"**Model:** {msg['model']}")

    if msg.get("usage"):
        usage = msg["usage"]
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        lines.append(f"**Tokens:** {input_tokens} in / {output_tokens} out")

    if msg.get("cwd"):
        lines.append(f"**CWD:** {msg['cwd']}")

    if msg.get("gitBranch"):
        lines.append(f"**Branch:** {msg['gitBranch']}")

    # Parent reference
    parent_uuid = msg.get("parentUuid")
    if parent_uuid and parent_uuid in uuid_to_index:
        lines.append(f"**Reply to:** Message {uuid_to_index[parent_uuid]}")

    if lines:
        lines.insert(0, "")
        lines.insert(1, "<details>")
        lines.insert(2, "<summary>Metadata</summary>")
        lines.insert(3, "")
        lines.append("")
        lines.append("</details>")

    return lines


def generate_part_markdown(
    messages: List[Dict[str, Any]],
    jsonl_file: Path,
    minimal: bool,
    part_num: int,
    total_parts: int,
    start_idx: int,
    end_idx: int,
    display_file: Optional[str] = None,
) -> str:
    """Generate markdown for a single part of a split conversation.

    Args:
        messages: Messages for this part.
        jsonl_file: Source file path.
        minimal: If True, omit metadata.
        part_num: Part number (1-based).
        total_parts: Total number of parts.
        start_idx: Starting message index (0-based).
        end_idx: Ending message index (0-based, exclusive).
        display_file: Override display filename.

    Returns:
        Markdown string for this part.
    """
    display_name = display_file or jsonl_file.name

    lines = [
        f"# Claude Code Session: {display_name} (Part {part_num}/{total_parts})",
        "",
        f"**Messages:** {start_idx + 1} - {end_idx} of total",
        "",
    ]

    lines.extend(["", "---", ""])

    # Build UUID index for this part
    uuid_to_index = {
        msg["uuid"]: start_idx + i for i, msg in enumerate(messages, 1) if msg.get("uuid")
    }

    for i, msg in enumerate(messages):
        global_idx = start_idx + i + 1
        lines.extend(generate_message_section(msg, global_idx, minimal, uuid_to_index))

    return "\n".join(lines)
