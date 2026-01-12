"""V1 parser tests for Codex CLI golden fixture.

Spec Reference: docs/specs/agents/formats/codex-cli-format.md

These tests validate that the parser correctly extracts messages, tokens,
and tool calls from Codex CLI JSONL session files.

Note: Codex uses a two-level type system (type + payload.type).
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


def count_messages_by_role(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count user and assistant messages in Codex format.

    Codex messages are response_item records with payload.type == "message".
    """
    counts = {"user": 0, "assistant": 0}
    for record in records:
        if record.get("type") == "response_item":
            payload = record.get("payload", {})
            if payload.get("type") == "message":
                role = payload.get("role")
                if role in ("user", "assistant"):
                    counts[role] += 1
    return counts


def get_token_usage(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Extract token usage from event_msg records with token_count payload."""
    for record in records:
        if record.get("type") == "event_msg":
            payload = record.get("payload", {})
            if payload.get("type") == "token_count":
                info = payload.get("info", {})
                total_usage = info.get("total_token_usage", {})
                return {
                    "input": total_usage.get("input_tokens", 0),
                    "output": total_usage.get("output_tokens", 0)
                    + total_usage.get("reasoning_output_tokens", 0),
                }
    return {"input": 0, "output": 0}


def extract_function_calls(records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Extract function call counts from response_item records."""
    tool_counts: Dict[str, int] = {}
    for record in records:
        if record.get("type") == "response_item":
            payload = record.get("payload", {})
            if payload.get("type") == "function_call":
                name = payload.get("name", "unknown")
                tool_counts[name] = tool_counts.get(name, 0) + 1
    return tool_counts


def has_reasoning_blocks(records: List[Dict[str, Any]]) -> bool:
    """Check if any record contains reasoning blocks."""
    for record in records:
        if record.get("type") == "response_item":
            payload = record.get("payload", {})
            if payload.get("type") == "reasoning":
                return True
    return False


def has_function_output(records: List[Dict[str, Any]]) -> bool:
    """Check if any record contains function_call_output."""
    for record in records:
        if record.get("type") == "response_item":
            payload = record.get("payload", {})
            if payload.get("type") == "function_call_output":
                return True
    return False


def get_session_meta(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract session metadata from session_meta record."""
    for record in records:
        if record.get("type") == "session_meta":
            return record.get("payload", {})
    return {}


def get_message_timestamps(records: List[Dict[str, Any]]) -> List[str]:
    """Get timestamps of message records only."""
    timestamps = []
    for record in records:
        if record.get("type") == "response_item":
            payload = record.get("payload", {})
            if payload.get("type") == "message":
                ts = record.get("timestamp")
                if ts:
                    timestamps.append(ts)
    return timestamps


class TestCodexParserGolden:
    """Parse Codex golden fixture and validate against expected values."""

    def test_parse_golden_fixture(self, codex_golden_path: Path):
        """Parse codex_golden.jsonl without errors."""
        records = load_jsonl_records(codex_golden_path)
        assert len(records) > 0, "Fixture should contain records"

    def test_has_session_meta(self, codex_golden_path: Path, codex_expected: Dict[str, Any]):
        """Verify session metadata is present."""
        records = load_jsonl_records(codex_golden_path)
        meta = get_session_meta(records)

        assert meta, "Should have session_meta record"
        assert meta.get("id") == codex_expected["session_id"]

    def test_message_count(self, codex_golden_path: Path, codex_expected: Dict[str, Any]):
        """Verify correct message count."""
        records = load_jsonl_records(codex_golden_path)
        counts = count_messages_by_role(records)
        total = counts["user"] + counts["assistant"]

        expected = codex_expected["message_count"]
        assert total == expected, f"Expected {expected} messages, got {total}"

    def test_user_assistant_breakdown(
        self, codex_golden_path: Path, codex_expected: Dict[str, Any]
    ):
        """Verify user and assistant message counts."""
        records = load_jsonl_records(codex_golden_path)
        counts = count_messages_by_role(records)

        expected_user = codex_expected["user_messages"]
        expected_asst = codex_expected["assistant_messages"]

        assert (
            counts["user"] == expected_user
        ), f"Expected {expected_user} user messages, got {counts['user']}"
        assert (
            counts["assistant"] == expected_asst
        ), f"Expected {expected_asst} assistant messages, got {counts['assistant']}"

    def test_token_totals(self, codex_golden_path: Path, codex_expected: Dict[str, Any]):
        """Verify token totals from token_count event."""
        records = load_jsonl_records(codex_golden_path)
        tokens = get_token_usage(records)

        expected_input = codex_expected["input_tokens"]
        expected_output = codex_expected["output_tokens"]

        assert (
            tokens["input"] == expected_input
        ), f"Expected {expected_input} input tokens, got {tokens['input']}"
        assert (
            tokens["output"] == expected_output
        ), f"Expected {expected_output} output tokens, got {tokens['output']}"

    def test_function_call_extraction(
        self, codex_golden_path: Path, codex_expected: Dict[str, Any]
    ):
        """Verify function calls are extracted correctly."""
        records = load_jsonl_records(codex_golden_path)
        tool_counts = extract_function_calls(records)

        expected_tools = codex_expected["tool_calls"]
        assert tool_counts == expected_tools, f"Expected {expected_tools}, got {tool_counts}"

    def test_reasoning_block_detection(
        self, codex_golden_path: Path, codex_expected: Dict[str, Any]
    ):
        """Verify reasoning blocks are detected."""
        records = load_jsonl_records(codex_golden_path)
        has_reasoning = has_reasoning_blocks(records)

        expected = codex_expected["has_reasoning"]
        assert has_reasoning == expected, f"Expected has_reasoning={expected}, got {has_reasoning}"

    def test_function_output_present(self, codex_golden_path: Path, codex_expected: Dict[str, Any]):
        """Verify function_call_output records are present."""
        records = load_jsonl_records(codex_golden_path)
        has_output = has_function_output(records)

        expected = codex_expected["has_function_output"]
        assert has_output == expected, f"Expected has_function_output={expected}, got {has_output}"

    def test_timestamp_parsing(self, codex_golden_path: Path, codex_expected: Dict[str, Any]):
        """Verify timestamps are parsed correctly."""
        records = load_jsonl_records(codex_golden_path)
        timestamps = get_message_timestamps(records)

        assert len(timestamps) > 0, "Should have timestamps"

        first_ts = timestamps[0]
        last_ts = timestamps[-1]

        expected_first = codex_expected["first_timestamp"]
        expected_last = codex_expected["last_timestamp"]

        assert (
            first_ts == expected_first
        ), f"Expected first timestamp {expected_first}, got {first_ts}"
        assert last_ts == expected_last, f"Expected last timestamp {expected_last}, got {last_ts}"

    def test_two_level_type_system(self, codex_golden_path: Path):
        """Verify two-level type system (type + payload.type) is used."""
        records = load_jsonl_records(codex_golden_path)

        # Check we have different top-level types
        top_level_types = {r.get("type") for r in records}
        expected_types = {"session_meta", "turn_context", "response_item", "event_msg"}
        assert expected_types.issubset(
            top_level_types
        ), f"Missing expected types. Found: {top_level_types}"

        # Check we have different payload types
        payload_types = set()
        for record in records:
            payload = record.get("payload", {})
            if payload_type := payload.get("type"):
                payload_types.add(payload_type)

        expected_payload_types = {
            "message",
            "function_call",
            "function_call_output",
            "reasoning",
            "token_count",
        }
        assert expected_payload_types.issubset(
            payload_types
        ), f"Missing expected payload types. Found: {payload_types}"

    def test_function_call_has_call_id(self, codex_golden_path: Path):
        """Verify function_call records have call_id for linking to output."""
        records = load_jsonl_records(codex_golden_path)

        call_ids = set()
        output_call_ids = set()

        for record in records:
            if record.get("type") == "response_item":
                payload = record.get("payload", {})
                if payload.get("type") == "function_call":
                    call_id = payload.get("call_id")
                    assert call_id, "function_call should have call_id"
                    call_ids.add(call_id)
                elif payload.get("type") == "function_call_output":
                    call_id = payload.get("call_id")
                    assert call_id, "function_call_output should have call_id"
                    output_call_ids.add(call_id)

        # Each function_call_output should reference an existing call_id
        for output_id in output_call_ids:
            assert (
                output_id in call_ids
            ), f"function_call_output references unknown call_id: {output_id}"
