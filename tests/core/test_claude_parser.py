"""V1 parser tests for Claude Code golden fixture.

Spec Reference: docs/specs/agents/formats/claude-code-format.md

These tests validate that the parser correctly extracts messages, tokens,
and tool calls from Claude Code JSONL session files.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

pytestmark = pytest.mark.v1


def load_jsonl_records(path: Path) -> List[Dict[str, Any]]:
    """Load all records from a JSONL file."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def count_messages_by_type(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count user and assistant messages."""
    counts = {"user": 0, "assistant": 0}
    for record in records:
        record_type = record.get("type")
        if record_type in ("user", "assistant"):
            counts[record_type] += 1
    return counts


def sum_tokens(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Sum input and output tokens from assistant messages."""
    input_tokens = 0
    output_tokens = 0
    for record in records:
        if record.get("type") == "assistant":
            usage = record.get("message", {}).get("usage", {})
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
    return {"input": input_tokens, "output": output_tokens}


def extract_tool_calls(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Extract tool call counts from assistant messages."""
    tool_counts: Dict[str, int] = {}
    for record in records:
        if record.get("type") == "assistant":
            content = record.get("message", {}).get("content", [])
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name", "unknown")
                    tool_counts[name] = tool_counts.get(name, 0) + 1
    return tool_counts


def has_thinking_blocks(records: List[Dict[str, Any]]) -> bool:
    """Check if any assistant message contains thinking blocks."""
    for record in records:
        if record.get("type") == "assistant":
            content = record.get("message", {}).get("content", [])
            for block in content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    return True
    return False


def has_tool_results(records: List[Dict[str, Any]]) -> bool:
    """Check if any user message contains tool results."""
    for record in records:
        if record.get("type") == "user":
            content = record.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        return True
    return False


class TestClaudeParserGolden:
    """Parse Claude golden fixture and validate against expected values."""

    def test_parse_golden_fixture(self, claude_golden_path: Path):
        """Parse claude_golden.jsonl without errors."""
        records = load_jsonl_records(claude_golden_path)
        assert len(records) > 0, "Fixture should contain records"

    def test_message_count(self, claude_golden_path: Path, claude_expected: Dict[str, Any]):
        """Verify correct message count."""
        records = load_jsonl_records(claude_golden_path)
        counts = count_messages_by_type(records)
        total = counts["user"] + counts["assistant"]

        expected = claude_expected["message_count"]
        assert total == expected, f"Expected {expected} messages, got {total}"

    def test_user_assistant_breakdown(
        self, claude_golden_path: Path, claude_expected: Dict[str, Any]
    ):
        """Verify user and assistant message counts."""
        records = load_jsonl_records(claude_golden_path)
        counts = count_messages_by_type(records)

        expected_user = claude_expected["user_messages"]
        expected_asst = claude_expected["assistant_messages"]

        assert (
            counts["user"] == expected_user
        ), f"Expected {expected_user} user messages, got {counts['user']}"
        assert (
            counts["assistant"] == expected_asst
        ), f"Expected {expected_asst} assistant messages, got {counts['assistant']}"

    def test_token_totals(self, claude_golden_path: Path, claude_expected: Dict[str, Any]):
        """Verify token totals from usage fields."""
        records = load_jsonl_records(claude_golden_path)
        tokens = sum_tokens(records)

        expected_input = claude_expected["input_tokens"]
        expected_output = claude_expected["output_tokens"]

        assert (
            tokens["input"] == expected_input
        ), f"Expected {expected_input} input tokens, got {tokens['input']}"
        assert (
            tokens["output"] == expected_output
        ), f"Expected {expected_output} output tokens, got {tokens['output']}"

    def test_tool_call_extraction(self, claude_golden_path: Path, claude_expected: Dict[str, Any]):
        """Verify tool calls are extracted correctly."""
        records = load_jsonl_records(claude_golden_path)
        tool_counts = extract_tool_calls(records)

        expected_tools = claude_expected["tool_calls"]
        assert tool_counts == expected_tools, f"Expected {expected_tools}, got {tool_counts}"

    def test_thinking_block_detection(
        self, claude_golden_path: Path, claude_expected: Dict[str, Any]
    ):
        """Verify thinking blocks are detected."""
        records = load_jsonl_records(claude_golden_path)
        has_thinking = has_thinking_blocks(records)

        expected = claude_expected["has_thinking"]
        assert has_thinking == expected, f"Expected has_thinking={expected}, got {has_thinking}"

    def test_tool_result_linking(self, claude_golden_path: Path, claude_expected: Dict[str, Any]):
        """Verify tool results are present in user messages."""
        records = load_jsonl_records(claude_golden_path)
        has_results = has_tool_results(records)

        expected = claude_expected["has_tool_results"]
        assert has_results == expected, f"Expected has_tool_results={expected}, got {has_results}"

    def test_timestamp_parsing(self, claude_golden_path: Path, claude_expected: Dict[str, Any]):
        """Verify timestamps are parsed correctly."""
        records = load_jsonl_records(claude_golden_path)

        # Get first and last timestamps
        timestamps = [r.get("timestamp") for r in records if r.get("timestamp")]
        assert len(timestamps) > 0, "Should have timestamps"

        first_ts = timestamps[0]
        last_ts = timestamps[-1]

        expected_first = claude_expected["first_timestamp"]
        expected_last = claude_expected["last_timestamp"]

        assert (
            first_ts == expected_first
        ), f"Expected first timestamp {expected_first}, got {first_ts}"
        assert last_ts == expected_last, f"Expected last timestamp {expected_last}, got {last_ts}"

    def test_session_id_consistency(
        self, claude_golden_path: Path, claude_expected: Dict[str, Any]
    ):
        """Verify all messages have the same session ID."""
        records = load_jsonl_records(claude_golden_path)

        expected_session_id = claude_expected["session_id"]
        for record in records:
            session_id = record.get("sessionId")
            assert (
                session_id == expected_session_id
            ), f"Expected sessionId {expected_session_id}, got {session_id}"

    def test_uuid_parent_chain(self, claude_golden_path: Path):
        """Verify UUID parent chain is intact."""
        records = load_jsonl_records(claude_golden_path)

        # Build UUID set
        uuid_set = {r.get("uuid") for r in records if r.get("uuid")}

        # First message should have no parent
        assert records[0].get("parentUuid") is None, "First message should have no parent"

        # Subsequent messages should reference existing UUIDs
        for i, record in enumerate(records[1:], 1):
            parent_uuid = record.get("parentUuid")
            if parent_uuid:
                assert parent_uuid in uuid_set or parent_uuid in [
                    r.get("uuid") for r in records[:i]
                ], f"Parent UUID {parent_uuid} not found for message {i}"
