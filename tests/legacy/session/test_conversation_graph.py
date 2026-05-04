"""Conversation fork analysis coverage using forked fixture."""

import pytest

from tests.helpers.module_loader import load_agent_history
from tests.helpers.paths import fixtures_dir

pytestmark = pytest.mark.v1


def test_fork_detection_and_summary_from_fixture() -> None:
    """Forked conversations should produce fork points and summaries."""
    module = load_agent_history()
    fixture = fixtures_dir() / "forks" / "claude_forked_session.jsonl"

    messages = module.read_jsonl_messages(fixture)
    graph = module.analyze_conversation_graph(messages)

    assert not graph.is_linear
    assert graph.fork_points == ["fa1-fork"]
    assert len(graph.branches) == 1
    assert len(graph.branches[0]["branches"]) == 2

    summary = module.generate_graph_summary(graph)
    assert summary, "Forked conversations should emit a summary block"
    assert "Conversation Structure" in "\n".join(summary)


def test_linear_conversation_has_no_branches() -> None:
    """Linear conversations should not report forks or branches."""
    module = load_agent_history()
    messages = [
        {"uuid": "a", "parentUuid": None, "role": "user"},
        {"uuid": "b", "parentUuid": "a", "role": "assistant"},
        {"uuid": "c", "parentUuid": "b", "role": "user"},
    ]
    graph = module.analyze_conversation_graph(messages)

    assert graph.is_linear
    assert graph.fork_points == []
    assert graph.branches == []


def test_mermaid_generation_for_forked_graph() -> None:
    """Forked conversations should produce a Mermaid diagram block."""
    module = load_agent_history()
    messages = [
        {"uuid": "root", "parentUuid": None, "role": "user"},
        {"uuid": "child", "parentUuid": "root", "role": "assistant"},
        {"uuid": "fork1", "parentUuid": "child", "role": "user"},
        {"uuid": "fork2", "parentUuid": "child", "role": "user"},
    ]
    graph = module.analyze_conversation_graph(messages)
    mermaid = module.generate_mermaid_graph(graph)

    assert mermaid, "Mermaid output expected for forked graph"
    mermaid_text = "\n".join(mermaid)
    assert "```mermaid" in mermaid_text
    assert "graph TD" in mermaid_text


def test_is_meta_preserved_in_build_message_dict() -> None:
    """_build_message_dict should preserve isMeta field when present."""
    module = load_agent_history()
    entry = {"type": "user", "isMeta": True, "uuid": "meta-uuid"}
    message_obj = {"role": "user", "content": "test"}

    result = module._build_message_dict(  # type: ignore[attr-defined]
        entry, message_obj, "user", "test content", "2025-01-01T00:00:00Z"
    )
    assert result.get("isMeta") is True


def test_is_meta_defaults_to_absent() -> None:
    """isMeta should be present as None when not provided."""
    module = load_agent_history()
    entry = {"type": "user", "uuid": "meta-uuid"}
    message_obj = {"role": "user", "content": "test"}

    result = module._build_message_dict(  # type: ignore[attr-defined]
        entry, message_obj, "user", "test content", "2025-01-01T00:00:00Z"
    )
    assert "isMeta" in result
    assert result["isMeta"] is None
