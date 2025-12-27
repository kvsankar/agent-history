"""Unit tests for conversation graph analysis and isMeta metadata."""

import importlib.util
import json
from pathlib import Path

# Load agent-history as a module
spec = importlib.util.spec_from_loader("agent_history", loader=None)
agent_history = importlib.util.module_from_spec(spec)
with open(Path(__file__).parent.parent.parent / "agent-history") as f:
    code = f.read()
exec(compile(code, "agent-history", "exec"), agent_history.__dict__)


class TestConversationGraphAnalysis:
    """Tests for conversation graph analysis."""

    def test_analyze_linear_conversation(self):
        """Test analysis of a linear conversation (no forks)."""
        messages = [
            {"uuid": "a", "parentUuid": None, "role": "user"},
            {"uuid": "b", "parentUuid": "a", "role": "assistant"},
            {"uuid": "c", "parentUuid": "b", "role": "user"},
            {"uuid": "d", "parentUuid": "c", "role": "assistant"},
        ]

        graph = agent_history.analyze_conversation_graph(messages)

        assert graph.is_linear
        assert len(graph.fork_points) == 0
        assert len(graph.branches) == 0

    def test_analyze_forked_conversation(self):
        """Test analysis of a conversation with forks."""
        messages = [
            {"uuid": "a", "parentUuid": None, "role": "user", "timestamp": "2025-01-01T00:00:00Z"},
            {
                "uuid": "b",
                "parentUuid": "a",
                "role": "assistant",
                "timestamp": "2025-01-01T00:01:00Z",
            },
            # Fork: two messages with same parent
            {"uuid": "c1", "parentUuid": "b", "role": "user", "timestamp": "2025-01-01T00:02:00Z"},
            {"uuid": "c2", "parentUuid": "b", "role": "user", "timestamp": "2025-01-01T00:03:00Z"},
        ]

        graph = agent_history.analyze_conversation_graph(messages)

        assert not graph.is_linear
        assert len(graph.fork_points) == 1
        assert "b" in graph.fork_points
        assert len(graph.branches) == 1
        assert len(graph.branches[0]["branches"]) == 2

    def test_analyze_multiple_forks(self):
        """Test analysis with multiple fork points."""
        messages = [
            {"uuid": "a", "parentUuid": None, "role": "user"},
            {"uuid": "b", "parentUuid": "a", "role": "assistant"},
            {"uuid": "c1", "parentUuid": "b", "role": "user"},
            {"uuid": "c2", "parentUuid": "b", "role": "user"},  # Fork 1
            {"uuid": "d", "parentUuid": "c1", "role": "assistant"},
            {"uuid": "e1", "parentUuid": "d", "role": "user"},
            {"uuid": "e2", "parentUuid": "d", "role": "user"},  # Fork 2
        ]

        graph = agent_history.analyze_conversation_graph(messages)

        assert not graph.is_linear
        assert len(graph.fork_points) == 2
        assert "b" in graph.fork_points
        assert "d" in graph.fork_points

    def test_uuid_to_msg_mapping(self):
        """Test that uuid_to_msg correctly maps UUIDs to messages."""
        messages = [
            {"uuid": "a", "role": "user", "content": "hello"},
            {"uuid": "b", "role": "assistant", "content": "hi"},
        ]

        graph = agent_history.analyze_conversation_graph(messages)

        assert "a" in graph.uuid_to_msg
        assert "b" in graph.uuid_to_msg
        assert graph.uuid_to_msg["a"]["content"] == "hello"


class TestGraphSummaryGeneration:
    """Tests for generating graph summary markdown."""

    def test_generate_summary_linear(self):
        """Test that linear conversations produce no summary."""
        messages = [
            {"uuid": "a", "parentUuid": None, "role": "user"},
            {"uuid": "b", "parentUuid": "a", "role": "assistant"},
        ]

        graph = agent_history.analyze_conversation_graph(messages)
        summary = agent_history.generate_graph_summary(graph)

        assert summary == []

    def test_generate_summary_forked(self):
        """Test that forked conversations produce summary."""
        messages = [
            {"uuid": "a", "parentUuid": None, "role": "user", "timestamp": "2025-01-01T00:00:00Z"},
            {
                "uuid": "b",
                "parentUuid": "a",
                "role": "assistant",
                "timestamp": "2025-01-01T00:01:00Z",
            },
            {"uuid": "c1", "parentUuid": "b", "role": "user", "timestamp": "2025-01-01T00:02:00Z"},
            {"uuid": "c2", "parentUuid": "b", "role": "user", "timestamp": "2025-01-01T00:03:00Z"},
        ]

        graph = agent_history.analyze_conversation_graph(messages)
        summary = agent_history.generate_graph_summary(graph)

        assert len(summary) > 0
        summary_text = "\n".join(summary)
        assert "Conversation Structure" in summary_text
        assert "fork point" in summary_text.lower()
        assert "Branch" in summary_text


class TestMermaidGraphGeneration:
    """Tests for Mermaid diagram generation."""

    def test_mermaid_linear_returns_empty(self):
        """Test that linear conversations return empty diagram."""
        messages = [
            {"uuid": "a", "parentUuid": None, "role": "user"},
            {"uuid": "b", "parentUuid": "a", "role": "assistant"},
        ]

        graph = agent_history.analyze_conversation_graph(messages)
        mermaid = agent_history.generate_mermaid_graph(graph)

        assert mermaid == []

    def test_mermaid_forked_contains_mermaid_block(self):
        """Test that forked conversations produce Mermaid diagram."""
        messages = [
            {"uuid": "abcdef", "parentUuid": None, "role": "user"},
            {"uuid": "bcdefg", "parentUuid": "abcdef", "role": "assistant"},
            {"uuid": "cdefgh", "parentUuid": "bcdefg", "role": "user"},
            {"uuid": "defghi", "parentUuid": "bcdefg", "role": "user"},  # Fork
        ]

        graph = agent_history.analyze_conversation_graph(messages)
        mermaid = agent_history.generate_mermaid_graph(graph)

        assert len(mermaid) > 0
        mermaid_text = "\n".join(mermaid)
        assert "```mermaid" in mermaid_text
        assert "graph TD" in mermaid_text
        assert "```" in mermaid_text


class TestIsMetaMetadata:
    """Tests for isMeta field handling."""

    def test_build_message_dict_includes_is_meta(self):
        """Test that _build_message_dict includes isMeta field."""
        entry = {
            "type": "user",
            "isMeta": True,
            "uuid": "test-uuid",
        }
        message_obj = {"role": "user", "content": "test"}

        result = agent_history._build_message_dict(
            entry, message_obj, "user", "test content", "2025-01-01T00:00:00Z"
        )

        assert "isMeta" in result
        assert result["isMeta"] is True

    def test_is_meta_false(self):
        """Test isMeta when explicitly False."""
        entry = {
            "type": "user",
            "isMeta": False,
            "uuid": "test-uuid",
        }
        message_obj = {"role": "user", "content": "test"}

        result = agent_history._build_message_dict(
            entry, message_obj, "user", "test content", "2025-01-01T00:00:00Z"
        )

        assert result["isMeta"] is False

    def test_is_meta_not_present(self):
        """Test isMeta when not present in entry."""
        entry = {
            "type": "user",
            "uuid": "test-uuid",
        }
        message_obj = {"role": "user", "content": "test"}

        result = agent_history._build_message_dict(
            entry, message_obj, "user", "test content", "2025-01-01T00:00:00Z"
        )

        assert "isMeta" in result
        assert result["isMeta"] is None


class TestMarkdownIntegration:
    """Integration tests for markdown generation with graph and metadata."""

    def test_parse_jsonl_includes_graph_for_forked(self, tmp_path):
        """Test that forked conversations include graph summary in markdown."""
        jsonl_file = tmp_path / "test.jsonl"
        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Hello"},
                "uuid": "a",
                "parentUuid": None,
                "timestamp": "2025-01-01T00:00:00Z",
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]},
                "uuid": "b",
                "parentUuid": "a",
                "timestamp": "2025-01-01T00:01:00Z",
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "Fork 1"},
                "uuid": "c1",
                "parentUuid": "b",
                "timestamp": "2025-01-01T00:02:00Z",
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "Fork 2"},
                "uuid": "c2",
                "parentUuid": "b",
                "timestamp": "2025-01-01T00:03:00Z",
            },
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        markdown = agent_history.parse_jsonl_to_markdown(jsonl_file)

        assert "Conversation Structure" in markdown
        assert "fork point" in markdown.lower()

    def test_parse_jsonl_no_graph_for_linear(self, tmp_path):
        """Test that linear conversations don't include graph summary."""
        jsonl_file = tmp_path / "test.jsonl"
        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Hello"},
                "uuid": "a",
                "parentUuid": None,
                "timestamp": "2025-01-01T00:00:00Z",
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]},
                "uuid": "b",
                "parentUuid": "a",
                "timestamp": "2025-01-01T00:01:00Z",
            },
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        markdown = agent_history.parse_jsonl_to_markdown(jsonl_file)

        assert "Conversation Structure" not in markdown

    def test_parse_jsonl_no_graph_in_minimal_mode(self, tmp_path):
        """Test that graph is not included in minimal mode."""
        jsonl_file = tmp_path / "test.jsonl"
        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Hello"},
                "uuid": "a",
                "parentUuid": None,
                "timestamp": "2025-01-01T00:00:00Z",
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]},
                "uuid": "b",
                "parentUuid": "a",
                "timestamp": "2025-01-01T00:01:00Z",
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "Fork 1"},
                "uuid": "c1",
                "parentUuid": "b",
                "timestamp": "2025-01-01T00:02:00Z",
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "Fork 2"},
                "uuid": "c2",
                "parentUuid": "b",
                "timestamp": "2025-01-01T00:03:00Z",
            },
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        markdown = agent_history.parse_jsonl_to_markdown(jsonl_file, minimal=True)

        assert "Conversation Structure" not in markdown

    def test_is_meta_in_metadata_section(self, tmp_path):
        """Test that isMeta appears in metadata section."""
        jsonl_file = tmp_path / "test.jsonl"
        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Hello"},
                "uuid": "a",
                "isMeta": True,
                "timestamp": "2025-01-01T00:00:00Z",
            },
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        markdown = agent_history.parse_jsonl_to_markdown(jsonl_file)

        assert "Is Meta" in markdown
        assert "`True`" in markdown
