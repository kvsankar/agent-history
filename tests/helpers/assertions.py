"""Custom assertions for V1 tests."""

from typing import Any, Dict


def assert_message_count(parsed: Dict[str, Any], expected: int, agent: str = "") -> None:
    """Assert parsed session has expected message count."""
    actual = len(parsed.get("messages", []))
    assert actual == expected, f"{agent} message count: expected {expected}, got {actual}"


def assert_user_assistant_count(
    parsed: Dict[str, Any],
    expected_user: int,
    expected_assistant: int,
    agent: str = "",
) -> None:
    """Assert parsed session has expected user and assistant message counts."""
    messages = parsed.get("messages", [])
    user_count = sum(1 for m in messages if m.get("role") == "user")
    assistant_count = sum(1 for m in messages if m.get("role") == "assistant")

    assert (
        user_count == expected_user
    ), f"{agent} user messages: expected {expected_user}, got {user_count}"
    assert (
        assistant_count == expected_assistant
    ), f"{agent} assistant messages: expected {expected_assistant}, got {assistant_count}"


def assert_token_totals(
    parsed: Dict[str, Any],
    expected_input: int,
    expected_output: int,
    agent: str = "",
) -> None:
    """Assert parsed session has expected token totals."""
    messages = parsed.get("messages", [])
    total_input = sum(m.get("input_tokens", 0) for m in messages)
    total_output = sum(m.get("output_tokens", 0) for m in messages)

    assert (
        total_input == expected_input
    ), f"{agent} input tokens: expected {expected_input}, got {total_input}"
    assert (
        total_output == expected_output
    ), f"{agent} output tokens: expected {expected_output}, got {total_output}"


def assert_tool_counts(
    parsed: Dict[str, Any],
    expected_tools: Dict[str, int],
    agent: str = "",
) -> None:
    """Assert parsed session has expected tool call counts."""
    messages = parsed.get("messages", [])
    actual_tools: Dict[str, int] = {}

    for msg in messages:
        for tool_call in msg.get("tool_calls", []):
            name = tool_call.get("name", "unknown")
            actual_tools[name] = actual_tools.get(name, 0) + 1

    assert (
        actual_tools == expected_tools
    ), f"{agent} tool counts: expected {expected_tools}, got {actual_tools}"


def assert_stats_invariants(stats: Dict[str, Any]) -> None:
    """Assert stats satisfy mathematical invariants."""
    # Message counts add up
    user_msgs = stats.get("user_messages", 0)
    asst_msgs = stats.get("assistant_messages", 0)
    total_msgs = stats.get("messages", 0)
    assert (
        user_msgs + asst_msgs == total_msgs
    ), f"Message count invariant: {user_msgs} + {asst_msgs} != {total_msgs}"

    # Token totals are non-negative
    assert stats.get("input_tokens", 0) >= 0, "Input tokens must be non-negative"
    assert stats.get("output_tokens", 0) >= 0, "Output tokens must be non-negative"


def assert_golden_totals(
    actual: Dict[str, Any],
    expected: Dict[str, Any],
) -> None:
    """Assert actual stats match expected golden totals."""
    for key in ["sessions", "messages", "input_tokens", "output_tokens"]:
        actual_val = actual.get(key, 0)
        expected_val = expected.get(key, 0)
        assert (
            actual_val == expected_val
        ), f"Golden {key}: expected {expected_val}, got {actual_val}"


def assert_has_field(record: Dict[str, Any], field: str, message: str = "") -> None:
    """Assert record has expected field."""
    assert field in record, f"{message}Field '{field}' not found in record"


def assert_timestamp_format(timestamp: str, message: str = "") -> None:
    """Assert timestamp is in ISO 8601 format."""
    import re

    # ISO 8601 pattern: YYYY-MM-DDTHH:MM:SS.sssZ or similar
    iso_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    assert re.match(
        iso_pattern, timestamp
    ), f"{message}Timestamp '{timestamp}' not in ISO 8601 format"
