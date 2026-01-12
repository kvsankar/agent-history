"""Markdown export fork summary coverage."""

from agent_history.backends.claude import read_jsonl_messages
from agent_history.export.markdown import parse_jsonl_to_markdown
from tests.helpers.paths import fixtures_dir


def test_markdown_includes_fork_summary() -> None:
    fixture = fixtures_dir() / "forks" / "claude_forked_session.jsonl"
    messages = read_jsonl_messages(fixture)
    markdown = parse_jsonl_to_markdown(fixture, minimal=False, messages=messages)

    assert "Conversation Structure" in markdown
    assert '<a name="msg-fa1-fork"></a>' in markdown
    assert "(#msg-" in markdown
