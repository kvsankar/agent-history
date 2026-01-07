"""Conversation fork analysis coverage using forked fixture."""

from pathlib import Path

import pytest

from tests.helpers.module_loader import load_agent_history

pytestmark = pytest.mark.v1


def test_fork_detection_and_summary_from_fixture() -> None:
    """Forked conversations should produce fork points and summaries."""
    module = load_agent_history()
    fixture = Path(__file__).parent.parent / "fixtures" / "forks" / "claude_forked_session.jsonl"

    messages = module.read_jsonl_messages(fixture)
    graph = module.analyze_conversation_graph(messages)

    assert not graph.is_linear
    assert graph.fork_points == ["fa1-fork"]
    assert len(graph.branches) == 1
    assert len(graph.branches[0]["branches"]) == 2

    summary = module.generate_graph_summary(graph)
    assert summary, "Forked conversations should emit a summary block"
    assert "Conversation Structure" in "\n".join(summary)
