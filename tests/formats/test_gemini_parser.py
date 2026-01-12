"""V1 parser tests for Gemini CLI golden fixture.

Spec Reference: docs/specs/agents/formats/gemini-cli-format.md

These tests validate that the parser correctly extracts messages, tokens,
and tool calls from Gemini CLI JSON session files.

Note: Gemini uses a single JSON file (not JSONL) with a messages array.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

pytestmark = pytest.mark.v1


def load_gemini_session(path: Path) -> Dict[str, Any]:
    """Load a Gemini session from JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def count_messages_by_type(session: Dict[str, Any]) -> Dict[str, int]:
    """Count user and gemini messages."""
    counts = {"user": 0, "gemini": 0}
    for message in session.get("messages", []):
        msg_type = message.get("type")
        if msg_type in ("user", "gemini"):
            counts[msg_type] += 1
    return counts


def sum_tokens(session: Dict[str, Any]) -> Dict[str, int]:
    """Sum input and output tokens from gemini messages."""
    input_tokens = 0
    output_tokens = 0
    for message in session.get("messages", []):
        if message.get("type") == "gemini":
            tokens = message.get("tokens", {})
            input_tokens += tokens.get("input", 0)
            output_tokens += tokens.get("output", 0)
    return {"input": input_tokens, "output": output_tokens}


def extract_tool_calls(session: Dict[str, Any]) -> Dict[str, int]:
    """Extract tool call counts from gemini messages."""
    tool_counts: Dict[str, int] = {}
    for message in session.get("messages", []):
        if message.get("type") == "gemini":
            for tool_call in message.get("toolCalls", []):
                name = tool_call.get("name", "unknown")
                tool_counts[name] = tool_counts.get(name, 0) + 1
    return tool_counts


def has_thoughts(session: Dict[str, Any]) -> bool:
    """Check if any gemini message contains thoughts."""
    for message in session.get("messages", []):
        if message.get("type") == "gemini":
            if message.get("thoughts"):
                return True
    return False


def has_tool_results(session: Dict[str, Any]) -> bool:
    """Check if any tool call has a result."""
    for message in session.get("messages", []):
        if message.get("type") == "gemini":
            for tool_call in message.get("toolCalls", []):
                if tool_call.get("result"):
                    return True
    return False


def get_message_timestamps(session: Dict[str, Any]) -> List[str]:
    """Get timestamps of all messages."""
    return [m.get("timestamp") for m in session.get("messages", []) if m.get("timestamp")]


class TestGeminiParserGolden:
    """Parse Gemini golden fixture and validate against expected values."""

    def test_parse_golden_fixture(self, gemini_golden_path: Path):
        """Parse gemini_golden.json without errors."""
        session = load_gemini_session(gemini_golden_path)
        assert session, "Fixture should load successfully"
        assert "messages" in session, "Session should have messages array"

    def test_session_metadata(self, gemini_golden_path: Path, gemini_expected: Dict[str, Any]):
        """Verify session metadata is correct."""
        session = load_gemini_session(gemini_golden_path)

        assert session.get("sessionId") == gemini_expected["session_id"]
        assert session.get("projectHash") == gemini_expected["workspace"]
        assert session.get("startTime"), "Should have startTime"
        assert session.get("lastUpdated"), "Should have lastUpdated"

    def test_message_count(self, gemini_golden_path: Path, gemini_expected: Dict[str, Any]):
        """Verify correct message count."""
        session = load_gemini_session(gemini_golden_path)
        counts = count_messages_by_type(session)
        total = counts["user"] + counts["gemini"]

        expected = gemini_expected["message_count"]
        assert total == expected, f"Expected {expected} messages, got {total}"

    def test_user_assistant_breakdown(
        self, gemini_golden_path: Path, gemini_expected: Dict[str, Any]
    ):
        """Verify user and gemini message counts."""
        session = load_gemini_session(gemini_golden_path)
        counts = count_messages_by_type(session)

        expected_user = gemini_expected["user_messages"]
        expected_gemini = gemini_expected["assistant_messages"]  # "gemini" maps to "assistant"

        assert (
            counts["user"] == expected_user
        ), f"Expected {expected_user} user messages, got {counts['user']}"
        assert (
            counts["gemini"] == expected_gemini
        ), f"Expected {expected_gemini} gemini messages, got {counts['gemini']}"

    def test_token_totals(self, gemini_golden_path: Path, gemini_expected: Dict[str, Any]):
        """Verify token totals from tokens field."""
        session = load_gemini_session(gemini_golden_path)
        tokens = sum_tokens(session)

        expected_input = gemini_expected["input_tokens"]
        expected_output = gemini_expected["output_tokens"]

        assert (
            tokens["input"] == expected_input
        ), f"Expected {expected_input} input tokens, got {tokens['input']}"
        assert (
            tokens["output"] == expected_output
        ), f"Expected {expected_output} output tokens, got {tokens['output']}"

    def test_tool_call_extraction(self, gemini_golden_path: Path, gemini_expected: Dict[str, Any]):
        """Verify tool calls are extracted correctly."""
        session = load_gemini_session(gemini_golden_path)
        tool_counts = extract_tool_calls(session)

        expected_tools = gemini_expected["tool_calls"]
        assert tool_counts == expected_tools, f"Expected {expected_tools}, got {tool_counts}"

    def test_thoughts_detection(self, gemini_golden_path: Path, gemini_expected: Dict[str, Any]):
        """Verify thoughts are detected."""
        session = load_gemini_session(gemini_golden_path)
        has_thinking = has_thoughts(session)

        expected = gemini_expected["has_thoughts"]
        assert has_thinking == expected, f"Expected has_thoughts={expected}, got {has_thinking}"

    def test_tool_results_present(self, gemini_golden_path: Path, gemini_expected: Dict[str, Any]):
        """Verify tool results are present in toolCalls."""
        session = load_gemini_session(gemini_golden_path)
        has_results = has_tool_results(session)

        expected = gemini_expected["has_tool_results"]
        assert has_results == expected, f"Expected has_tool_results={expected}, got {has_results}"

    def test_timestamp_parsing(self, gemini_golden_path: Path, gemini_expected: Dict[str, Any]):
        """Verify timestamps are parsed correctly."""
        session = load_gemini_session(gemini_golden_path)
        timestamps = get_message_timestamps(session)

        assert len(timestamps) > 0, "Should have timestamps"

        first_ts = timestamps[0]
        last_ts = timestamps[-1]

        expected_first = gemini_expected["first_timestamp"]
        expected_last = gemini_expected["last_timestamp"]

        assert (
            first_ts == expected_first
        ), f"Expected first timestamp {expected_first}, got {first_ts}"
        assert last_ts == expected_last, f"Expected last timestamp {expected_last}, got {last_ts}"

    def test_json_not_jsonl_format(self, gemini_golden_path: Path):
        """Verify Gemini uses JSON format (not JSONL)."""
        # Should be valid JSON
        with open(gemini_golden_path, encoding="utf-8") as f:
            content = f.read()

        # Should parse as single JSON object
        data = json.loads(content)
        assert isinstance(data, dict), "Should be a JSON object, not array"

        # Should have top-level keys, not be a flat array
        assert "sessionId" in data, "Should have sessionId at top level"
        assert "messages" in data, "Should have messages array"

    def test_tool_calls_embedded_in_messages(self, gemini_golden_path: Path):
        """Verify tool calls are embedded in gemini messages (not separate records)."""
        session = load_gemini_session(gemini_golden_path)

        # Find a gemini message with toolCalls
        for message in session.get("messages", []):
            if message.get("type") == "gemini" and message.get("toolCalls"):
                tool_call = message["toolCalls"][0]

                # Verify tool call structure
                assert "id" in tool_call, "Tool call should have id"
                assert "name" in tool_call, "Tool call should have name"
                assert "args" in tool_call, "Tool call should have args"
                assert "result" in tool_call, "Tool call should have embedded result"
                assert "status" in tool_call, "Tool call should have status"
                return

        pytest.fail("No gemini message with toolCalls found")

    def test_thoughts_structure(self, gemini_golden_path: Path):
        """Verify thoughts have correct structure."""
        session = load_gemini_session(gemini_golden_path)

        for message in session.get("messages", []):
            if message.get("type") == "gemini" and message.get("thoughts"):
                thought = message["thoughts"][0]

                # Verify thought structure
                assert "subject" in thought, "Thought should have subject"
                assert "description" in thought, "Thought should have description"
                assert "timestamp" in thought, "Thought should have timestamp"
                return

        pytest.fail("No gemini message with thoughts found")
