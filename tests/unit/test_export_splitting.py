from __future__ import annotations

from pathlib import Path

from agent_history.export.markdown import generate_part_markdown
from agent_history.export.splitting import generate_markdown_parts


def _short_messages(count: int) -> list[dict[str, str]]:
    return [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "timestamp": f"2025-01-01T10:{index:02d}:00Z",
            "content": f"Message {index}",
        }
        for index in range(count)
    ]


def test_split_does_not_fragment_markdown_shorter_than_target() -> None:
    """--split N should not split when the rendered markdown is under N lines."""
    messages = _short_messages(30)
    source = Path("session.jsonl")
    full_markdown = generate_part_markdown(
        messages,
        source,
        minimal=False,
        part_num=1,
        total_parts=1,
        start_idx=0,
        end_idx=len(messages),
        markdown_level=4,
    )
    target_lines = len(full_markdown.splitlines()) + 1

    assert (
        generate_markdown_parts(
            messages,
            source,
            minimal=False,
            split_lines=target_lines,
            markdown_level=4,
        )
        is None
    )
