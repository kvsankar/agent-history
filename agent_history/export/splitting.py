"""Conversation splitting logic for session export.

This module provides functions to split long conversations into multiple parts
at intelligent break points.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent_history.export.markdown import generate_part_markdown

# =============================================================================
# Constants
# =============================================================================

# Conversation splitting constants
SPLIT_MIN_FACTOR = 0.8  # Minimum lines before considering split (80% of target)
SPLIT_MAX_FACTOR = 1.3  # Maximum lines before forcing split (130% of target)
HEADER_LINES_ESTIMATE = 30  # Approximate header size in lines
METADATA_LINES_ESTIMATE = 20  # Approximate metadata section size in lines
MIN_MESSAGES_FOR_SPLIT = 2  # Minimum messages to consider splitting
MIN_SPLIT_POINTS = 2  # Minimum split points (start + end)

# Split point scoring weights
SCORE_USER_MESSAGE_NEXT = 100  # Next message is User (best - starting new topic)
SCORE_TOOL_RESULT = 50  # Current message is tool result (action complete)
SCORE_TIME_GAP_LARGE = 30  # Time gap > 5 minutes
SCORE_TIME_GAP_MEDIUM = 10  # Time gap > 1 minute
SCORE_DISTANCE_PENALTY = 0.05  # Penalty per line away from target

# Time gap thresholds (in seconds)
TIME_GAP_LARGE = 300  # 5 minutes
TIME_GAP_MEDIUM = 60  # 1 minute

# Markdown markers for tool content
TOOL_RESULT_MARKER = "**[Tool Result:"


def generate_markdown_parts(
    messages: List[Dict[str, Any]],
    jsonl_file: Path,
    minimal: bool,
    split_lines: int,
    display_file: Optional[str] = None,
    markdown_level: int = 4,
) -> Optional[List[Tuple[int, int, str, int, int]]]:
    """Generate multiple markdown parts from messages, split at smart break points.

    Args:
        messages: List of messages.
        jsonl_file: Source file path.
        minimal: If True, omit metadata.
        split_lines: Target lines per part.
        display_file: Override display filename.

    Returns:
        List of (part_num, total_parts, markdown, start_msg, end_msg) tuples,
        or None if splitting not needed.
    """
    if not split_lines or len(messages) == 0:
        return None

    # Find all split points
    split_points = [0]  # Start with message 0
    remaining_messages = messages

    while True:
        split_idx = find_best_split_point(remaining_messages, split_lines, minimal)

        if split_idx is None or split_idx >= len(remaining_messages):
            break

        global_idx = split_points[-1] + split_idx
        split_points.append(global_idx)
        remaining_messages = messages[global_idx:]

    # Add end point
    split_points.append(len(messages))

    # If only one part, no splitting needed
    if len(split_points) <= MIN_SPLIT_POINTS:
        return None

    total_parts = len(split_points) - 1
    parts = []

    for part_num in range(total_parts):
        start_idx = split_points[part_num]
        end_idx = split_points[part_num + 1]
        part_messages = messages[start_idx:end_idx]

        # Generate markdown for this part
        part_md = generate_part_markdown(
            part_messages,
            jsonl_file,
            minimal,
            part_num + 1,
            total_parts,
            start_idx,
            end_idx,
            display_file,
            markdown_level,
        )

        parts.append((part_num + 1, total_parts, part_md, start_idx, end_idx))

    return parts


def find_best_split_point(
    messages: List[Dict[str, Any]], target_lines: int, minimal: bool
) -> Optional[int]:
    """Find the optimal message index to split a conversation.

    Args:
        messages: List of messages.
        target_lines: Target number of lines per part.
        minimal: If True, less metadata overhead.

    Returns:
        Message index to split at, or None if no split needed.
    """
    min_lines = int(target_lines * SPLIT_MIN_FACTOR)
    max_lines = int(target_lines * SPLIT_MAX_FACTOR)

    current_lines = HEADER_LINES_ESTIMATE
    best_split = None
    best_score = -1

    for i, msg in enumerate(messages):
        current_lines += estimate_message_lines(msg.get("content", ""), not minimal)

        if current_lines > max_lines:
            return i if i > 0 else 1

        if current_lines >= min_lines:
            score = calculate_split_score(messages, i, msg, current_lines, target_lines)
            if score > best_score:
                best_score = score
                best_split = i + 1

    return best_split


def estimate_message_lines(msg_content: str, has_metadata: bool) -> int:
    """Estimate number of lines a message will take in markdown.

    Args:
        msg_content: Message content string.
        has_metadata: If True, include metadata overhead.

    Returns:
        Estimated line count.
    """
    lines = 0
    lines += 1  # Message header (## Message N)
    lines += 1  # Empty line
    lines += 1  # Timestamp
    lines += 1  # Empty line
    lines += len(msg_content.split("\n"))  # Content
    lines += 1  # Empty line
    if has_metadata:
        lines += METADATA_LINES_ESTIMATE
        lines += 1  # Empty line
    lines += 1  # Separator (---)
    lines += 1  # Empty line
    return lines


def calculate_split_score(
    messages: List[Dict[str, Any]],
    index: int,
    msg: Dict[str, Any],
    current_lines: int,
    target_lines: int,
) -> float:
    """Calculate a score for splitting at this position.

    Higher scores indicate better split points.

    Args:
        messages: List of messages.
        index: Current message index.
        msg: Current message.
        current_lines: Current line count.
        target_lines: Target line count.

    Returns:
        Split score (higher is better).
    """
    score = 0.0

    # Best: next message is from User (starting new topic)
    if index + 1 < len(messages) and messages[index + 1].get("role") == "user":
        score += SCORE_USER_MESSAGE_NEXT

    # Good: current message is a tool result (action complete)
    if msg.get("content") and TOOL_RESULT_MARKER in msg.get("content", ""):
        score += SCORE_TOOL_RESULT

    # Bonus for time gaps
    if index + 1 < len(messages):
        time_gap = get_time_gap(msg, messages[index + 1])
        if time_gap >= TIME_GAP_LARGE:
            score += SCORE_TIME_GAP_LARGE
        elif time_gap >= TIME_GAP_MEDIUM:
            score += SCORE_TIME_GAP_MEDIUM

    # Penalty for distance from target
    distance = abs(current_lines - target_lines)
    score -= distance * SCORE_DISTANCE_PENALTY

    return score


def get_time_gap(msg1: Dict[str, Any], msg2: Dict[str, Any]) -> float:
    """Calculate time gap between two messages in seconds.

    Args:
        msg1: First message.
        msg2: Second message.

    Returns:
        Time gap in seconds, or 0 if timestamps unavailable.
    """
    try:
        ts1 = msg1.get("timestamp", "")
        ts2 = msg2.get("timestamp", "")
        if not ts1 or not ts2:
            return 0

        dt1 = datetime.fromisoformat(ts1.replace("Z", "+00:00"))
        dt2 = datetime.fromisoformat(ts2.replace("Z", "+00:00"))
        return abs((dt2 - dt1).total_seconds())
    except (ValueError, TypeError):
        return 0
