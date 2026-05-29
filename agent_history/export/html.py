"""HTML rendering for session export."""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any

from agent_history.backends.registry import get_backend
from agent_history.types import MessageDict

HTML_RENDERER_VERSION = 1

_TOOL_HEADING_RE = re.compile(r"\*\*\[(?:Tool Use|Tool): ([^\]]+)\]\*\*")
_CODE_FENCE_RE = re.compile(r"```(?P<label>[A-Za-z0-9_+.-]*)\n(?P<body>.*?)\n```", re.DOTALL)


def render_html_export(
    jsonl_file: Path,
    agent_type: str,
    messages: list[MessageDict],
    minimal: bool = False,
    display_file: str | None = None,
) -> str:
    """Render a session as a self-contained HTML document."""
    backend = get_backend(agent_type)
    agent_title = (
        backend.markdown_title if backend and backend.markdown_title else agent_type.title()
    )
    title = f"{agent_title} Conversation"
    display_name = display_file or jsonl_file.name
    turns = _group_messages_into_turns(messages)

    body = [
        "<!doctype html>",
        '<html lang="en" data-theme="light">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(title)} - {escape(display_name)}</title>",
        f'<meta name="agent-history-renderer" content="{HTML_RENDERER_VERSION}">',
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        '<main class="page">',
        '<header class="export-header">',
        f"<h1>{escape(title)}</h1>",
    ]

    if not minimal:
        body.extend(_render_metadata(display_name, agent_type, messages))
    body.extend(["</header>", '<section class="turns" aria-label="Conversation turns">'])

    for turn_index, turn in enumerate(turns, 1):
        body.extend(_render_turn(turn, turn_index, agent_type, minimal))

    body.extend(
        [
            "</section>",
            "</main>",
            f"<script>{_SCRIPT}</script>",
            "</body>",
            "</html>",
            "",
        ]
    )
    return "\n".join(body)


def _render_metadata(display_name: str, agent_type: str, messages: list[MessageDict]) -> list[str]:
    rows = [
        ("File", display_name),
        ("Agent", agent_type),
        ("Messages", str(len(messages))),
    ]
    if messages and messages[0].get("timestamp"):
        rows.append(("Started", str(messages[0]["timestamp"])))
    if len(messages) > 1 and messages[-1].get("timestamp"):
        rows.append(("Ended", str(messages[-1]["timestamp"])))

    lines = ['<dl class="metadata">']
    for key, value in rows:
        lines.append(f"<dt>{escape(key)}</dt><dd>{escape(value)}</dd>")
    lines.append("</dl>")
    return lines


def _starts_new_turn(msg: MessageDict) -> bool:
    return _semantic_origin(msg) == "human"


def _group_messages_into_turns(messages: list[MessageDict]) -> list[list[MessageDict]]:
    turns: list[list[MessageDict]] = []
    current: list[MessageDict] = []
    for msg in messages:
        if _starts_new_turn(msg) and current:
            turns.append(current)
            current = []
        current.append(msg)
    if current:
        turns.append(current)
    return turns


def _render_turn(
    turn: list[MessageDict], turn_index: int, agent_type: str, minimal: bool
) -> list[str]:
    action_count = sum(1 for msg in turn if _semantic_origin(msg) in {"tool_call", "tool_result"})
    assistant_count = sum(1 for msg in turn if _semantic_origin(msg) == "assistant")
    summary = f"{len(turn)} messages"
    if action_count or assistant_count:
        details = []
        if assistant_count:
            details.append(f"{assistant_count} assistant")
        if action_count:
            details.append(f"{action_count} action")
        summary = ", ".join(details)

    lines = [
        f'<article class="turn" id="turn-{turn_index}" data-turn="{turn_index}">',
        '<header class="turn-header">',
        f"<h2>Turn {turn_index}</h2>",
        f'<span class="turn-summary">{escape(summary)}</span>',
        "</header>",
    ]
    for message_index, msg in enumerate(turn, 1):
        lines.extend(_render_message(msg, turn_index, message_index, agent_type, minimal))
    lines.append("</article>")
    return lines


def _render_message(
    msg: MessageDict,
    turn_index: int,
    message_index: int,
    agent_type: str,
    minimal: bool,
) -> list[str]:
    origin = _semantic_origin(msg)
    role = str(msg.get("role") or "unknown").lower()
    label = _message_label(msg, origin)
    classes = ["message", f"message-{origin.replace('_', '-')}"]
    if origin in {"tool_call", "tool_result"}:
        classes.append("message-action")

    timestamp = str(msg.get("timestamp") or "")
    content = str(msg.get("content") or "")
    raw_payload = _raw_payload(msg)

    lines = [
        '<section class="{}" data-agent="{}" data-role="{}" data-origin="{}" '
        'data-turn="{}" data-message="{}">'.format(
            " ".join(classes),
            escape(agent_type, quote=True),
            escape(role, quote=True),
            escape(origin, quote=True),
            turn_index,
            message_index,
        ),
        '<header class="message-header">',
        f"<h3>{escape(label)}</h3>",
    ]
    if timestamp and not minimal:
        lines.append(f'<time datetime="{escape(timestamp, quote=True)}">{escape(timestamp)}</time>')
    lines.extend(["</header>", *_render_content_panel(msg, content, origin)])
    if raw_payload and not minimal:
        lines.extend(_render_raw_panel(raw_payload))
    lines.append("</section>")
    return lines


def _message_label(msg: MessageDict, origin: str) -> str:
    if origin == "tool_call":
        tool_name = _tool_name(msg)
        return f"Tool call: {tool_name}" if tool_name else "Tool call"
    if origin == "tool_result":
        tool_name = msg.get("tool_name")
        return f"Tool result: {tool_name}" if tool_name else "Tool result"
    if origin == "internal_context":
        return "Internal context"
    role = str(msg.get("role") or "unknown").lower()
    return "User" if role == "user" else "Assistant" if role == "assistant" else role.title()


def _semantic_origin(msg: MessageDict) -> str:
    if msg.get("is_tool_call"):
        return "tool_call"
    if msg.get("is_tool_result"):
        return "tool_result"
    if msg.get("is_internal_context"):
        return "internal_context"
    role = str(msg.get("role") or "").lower()
    content = str(msg.get("content") or "")
    if role == "user" and "**[Tool Result" in content:
        return "tool_result"
    if role == "assistant" and _TOOL_HEADING_RE.search(content):
        return "tool_call"
    if role == "user":
        return "human"
    if role == "assistant":
        return "assistant"
    if role == "tool":
        return "tool_result"
    return "system"


def _tool_name(msg: MessageDict) -> str | None:
    if msg.get("tool_name"):
        return str(msg["tool_name"])
    for call in msg.get("tool_calls") or []:
        if isinstance(call, dict):
            name = call.get("name") or call.get("displayName")
            if name:
                return str(name)
    match = _TOOL_HEADING_RE.search(str(msg.get("content") or ""))
    if match:
        return match.group(1)
    return None


def _render_content_panel(msg: MessageDict, content: str, origin: str) -> list[str]:
    if not content and msg.get("tool_calls"):
        content = "\n\n".join(_format_structured_tool_call(call) for call in msg["tool_calls"])
    if not content:
        return ['<div class="message-body empty">No visible content</div>']

    if origin in {"tool_call", "tool_result"}:
        return _render_tool_panel(content, origin)
    return ['<div class="message-body">', _render_text_blocks(content), "</div>"]


def _render_tool_panel(content: str, origin: str) -> list[str]:
    title = "Tool input" if origin == "tool_call" else "Tool output"
    rendered, raw = _render_code_or_diff(content, title)
    return [
        '<section class="code-panel" data-view-panel>',
        '<div class="code-title">',
        f'<span class="code-title-label">{escape(title)}</span>',
        '<button class="view-toggle" type="button" data-view-toggle="raw" '
        'aria-pressed="false">Raw</button>',
        "</div>",
        '<div data-view-content="rendered">',
        rendered,
        "</div>",
        '<pre class="raw-code" data-view-content="raw" hidden><code>',
        raw,
        "</code></pre>",
        "</section>",
    ]


def _render_code_or_diff(content: str, title: str) -> tuple[str, str]:
    raw = escape(content)
    fence_match = _CODE_FENCE_RE.search(content)
    text = fence_match.group("body") if fence_match else content
    language = fence_match.group("label") if fence_match else ""

    if _looks_like_diff(text):
        return _render_diff(text), raw

    panel_title = "JSON" if language == "json" else title
    rendered = (
        '<section class="code-block">'
        f'<span class="code-block-title">{escape(panel_title)}</span>'
        f"<pre><code>{escape(text.strip())}</code></pre>"
        "</section>"
    )
    return rendered, raw


def _render_diff(text: str) -> str:
    lines = [
        '<section class="diff-panel">',
        '<span class="code-block-title">Diff</span>',
        '<pre class="diff">',
    ]
    for line in text.splitlines():
        if line.startswith("@@"):
            class_name = "diff-line-hunk"
        elif line.startswith("+") and not line.startswith("+++"):
            class_name = "diff-line-add"
        elif line.startswith("-") and not line.startswith("---"):
            class_name = "diff-line-del"
        elif line.startswith(("diff --git", "index ", "---", "+++")):
            class_name = "diff-line-meta"
        else:
            class_name = "diff-line-context"
        marker = line[:1] if line[:1] in {"+", "-", "@"} else " "
        content = line[1:] if marker in {"+", "-"} else line
        lines.append(
            f'<span class="diff-line {class_name}">'
            f'<span class="diff-marker">{escape(marker)}</span>'
            f'<span class="diff-content">{escape(content)}</span>'
            "</span>"
        )
    lines.extend(["</pre>", "</section>"])
    return "\n".join(lines)


def _looks_like_diff(text: str) -> bool:
    lines = text.splitlines()
    if any(line.startswith("diff --git ") for line in lines):
        return True
    has_add = any(line.startswith("+") and not line.startswith("+++") for line in lines)
    has_del = any(line.startswith("-") and not line.startswith("---") for line in lines)
    return has_add and has_del and any(line.startswith(("---", "+++", "@@")) for line in lines)


def _render_text_blocks(content: str) -> str:
    parts: list[str] = []
    position = 0
    for match in _CODE_FENCE_RE.finditer(content):
        before = content[position : match.start()].strip()
        if before:
            parts.append(_paragraphs(before))
        label = match.group("label") or "text"
        code = match.group("body")
        parts.append(
            '<section class="code-block">'
            f'<span class="code-block-title">Code ({escape(label)})</span>'
            f"<pre><code>{escape(code)}</code></pre>"
            "</section>"
        )
        position = match.end()
    remaining = content[position:].strip()
    if remaining:
        parts.append(_paragraphs(remaining))
    return "\n".join(parts) if parts else ""


def _paragraphs(text: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    return "\n".join(f"<p>{escape(part).replace(chr(10), '<br>')}</p>" for part in paragraphs)


def _format_structured_tool_call(call: dict[str, Any]) -> str:
    name = call.get("displayName") or call.get("name") or "unknown"
    args = call.get("args") or call.get("arguments") or call.get("input") or {}
    return f"**[Tool: {name}]**\n```json\n{json.dumps(args, indent=2, ensure_ascii=False)}\n```"


def _raw_payload(msg: MessageDict) -> str:
    return json.dumps(msg, indent=2, ensure_ascii=False, default=str)


def _render_raw_panel(raw_payload: str) -> list[str]:
    return [
        '<details class="raw-payload">',
        "<summary>Raw message</summary>",
        f"<pre><code>{escape(raw_payload)}</code></pre>",
        "</details>",
    ]


_CSS = """
:root {
  color-scheme: light dark;
  --bg: #f7f7f4;
  --panel: #ffffff;
  --ink: #1d2528;
  --muted: #5b676b;
  --line: #d7dddf;
  --accent: #0b6f70;
  --tool: #f4f0e8;
  --code: #111827;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111416;
    --panel: #191f22;
    --ink: #eef2f3;
    --muted: #a7b0b4;
    --line: #30383c;
    --tool: #252119;
    --code: #080b0f;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 14px/1.55 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.page { max-width: 1120px; margin: 0 auto; padding: 32px 20px 56px; }
.export-header { border-bottom: 1px solid var(--line); margin-bottom: 24px; padding-bottom: 18px; }
h1 { font-size: 28px; line-height: 1.2; margin: 0 0 14px; letter-spacing: 0; }
h2, h3 { letter-spacing: 0; }
.metadata { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; margin: 0; color: var(--muted); }
.metadata dt { font-weight: 700; color: var(--ink); }
.metadata dd { margin: 0; overflow-wrap: anywhere; }
.turn { margin: 0 0 28px; border-top: 1px solid var(--line); padding-top: 20px; }
.turn-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.turn-header h2 { margin: 0; font-size: 20px; }
.turn-summary { color: var(--muted); }
.message {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  margin: 10px 0;
  padding: 14px;
}
.message-action { background: var(--tool); }
.message-header { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.message-header h3 { font-size: 15px; margin: 0; }
.message-header time { color: var(--muted); font-size: 12px; white-space: nowrap; }
.message-body p { margin: 0 0 10px; overflow-wrap: anywhere; }
.message-body p:last-child { margin-bottom: 0; }
.message-body.empty { color: var(--muted); font-style: italic; }
.code-panel, .code-block, .diff-panel { margin: 0; }
.code-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.code-title-label, .code-block-title {
  display: inline-block;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}
.view-toggle {
  appearance: none;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: transparent;
  color: var(--ink);
  cursor: pointer;
  font: inherit;
  padding: 2px 8px;
}
pre {
  margin: 6px 0 0;
  padding: 12px;
  border-radius: 6px;
  background: var(--code);
  color: #e5e7eb;
  overflow: auto;
  white-space: pre-wrap;
}
code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; }
.diff { background: #101820; }
.diff-line { display: block; min-height: 1.4em; }
.diff-marker { display: inline-block; width: 1.5em; color: #aeb8bf; }
.diff-line-add .diff-content, .diff-line-add .diff-marker { color: #7ee787; }
.diff-line-del .diff-content, .diff-line-del .diff-marker { color: #ff8182; }
.diff-line-meta .diff-content, .diff-line-hunk .diff-content { color: #79c0ff; }
.raw-payload { margin-top: 10px; color: var(--muted); }
.raw-payload summary { cursor: pointer; }
@media (max-width: 640px) {
  .page { padding: 20px 12px 40px; }
  .turn-header, .message-header { display: block; }
  .message-header time { display: block; margin-top: 4px; }
}
"""


_SCRIPT = """
document.querySelectorAll('[data-view-toggle="raw"]').forEach((button) => {
  button.addEventListener('click', () => {
    const panel = button.closest('[data-view-panel]');
    if (!panel) return;
    const raw = panel.querySelector('[data-view-content="raw"]');
    const rendered = panel.querySelector('[data-view-content="rendered"]');
    if (!raw || !rendered) return;
    const showRaw = raw.hasAttribute('hidden');
    raw.toggleAttribute('hidden', !showRaw);
    rendered.toggleAttribute('hidden', showRaw);
    button.setAttribute('aria-pressed', String(showRaw));
  });
});
"""
