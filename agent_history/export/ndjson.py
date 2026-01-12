"""NDJSON export for session export.

This module provides functions to export sessions to NDJSON format
with a unified message schema.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from agent_history.core.ndjson import build_ndjson_records

def build_output_filename_ndjson(
    jsonl_file: Path, source_tag: str, messages: List[Dict[str, Any]]
) -> str:
    """Build NDJSON output filename with optional timestamp prefix.

    Args:
        jsonl_file: Source session file.
        source_tag: Source prefix (e.g., "wsl_Ubuntu_").
        messages: List of messages (for timestamp extraction).

    Returns:
        Output filename (e.g., "20240115120000_session-123.ndjson").
    """
    ts_prefix = None
    if messages and messages[0].get("timestamp"):
        try:
            timestamp = messages[0]["timestamp"]
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            ts_prefix = dt.strftime("%Y%m%d%H%M%S")
        except (ValueError, AttributeError):
            pass

    if ts_prefix:
        return f"{source_tag}{ts_prefix}_{jsonl_file.stem}.ndjson"
    return f"{source_tag}{jsonl_file.stem}.ndjson"


def write_ndjson_export(
    output_file: Path,
    agent_type: str,
    messages: List[Dict[str, Any]],
    session: Dict[str, Any],
    quiet: bool,
) -> None:
    """Write session to NDJSON file in unified format.

    The unified format normalizes messages from different agents to a
    common schema with fields: timestamp, role, content.
    Roles are normalized to: user, assistant, system.

    Args:
        output_file: Output file path.
        agent_type: Agent type (claude, codex, gemini).
        messages: Pre-read messages.
        session: Session metadata.
        quiet: If True, suppress per-file output.
    """
    records = build_ndjson_records(agent_type, messages, session)
    lines = [json.dumps(record, ensure_ascii=False) for record in records]

    output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not quiet:
        print(output_file)


def normalize_message_to_unified(msg: Dict[str, Any], agent_type: str) -> Dict[str, Any]:
    """Normalize a message to unified schema.

    The unified schema has:
    - timestamp: ISO format timestamp
    - role: "user", "assistant", or "system"
    - content: Message content as string

    Args:
        msg: Original message dictionary.
        agent_type: Agent type for role normalization.

    Returns:
        Normalized message dictionary.
    """
    # Normalize role: different agents may use different role names
    role = msg.get("role", "assistant")
    # Normalize "model" role (used by Gemini) to "assistant"
    if role == "model":
        role = "assistant"
    # Ensure role is one of the expected values
    if role not in ("user", "assistant", "system"):
        role = "assistant"

    # Extract content - handle both string and list content formats
    content = msg.get("content", "")
    if isinstance(content, list):
        # Claude sometimes has content as a list of blocks
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            elif isinstance(item, str):
                text_parts.append(item)
        content = "\n".join(text_parts)

    unified = {
        "timestamp": msg.get("timestamp", ""),
        "role": role,
        "content": content,
    }

    return unified
