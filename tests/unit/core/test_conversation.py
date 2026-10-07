from __future__ import annotations

from agent_history.core.conversation import analyze_conversation_graph


def test_conversation_graph_ignores_parented_messages_without_uuid() -> None:
    """Malformed records should not crash fork analysis."""
    messages = [
        {"uuid": "root", "parentUuid": None, "role": "user"},
        {"parentUuid": "root", "role": "assistant"},
        {"uuid": "child", "parentUuid": "root", "role": "assistant"},
    ]

    graph = analyze_conversation_graph(messages)

    assert graph.is_linear
    assert graph.uuid_to_children == {"root": ["child"]}
