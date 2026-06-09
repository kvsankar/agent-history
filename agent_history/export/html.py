"""HTML rendering for session export."""

from __future__ import annotations

import json
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from agent_history.backends.registry import get_backend
from agent_history.types import MessageDict

HTML_RENDERER_VERSION = 1
HTML_TIMELINE_RENDERER_VERSION = 1

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
        f'<meta name="cagelens-renderer" content="{HTML_RENDERER_VERSION}">',
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


def assign_timeline_tracks(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign compact non-overlapping track indexes to timeline sessions."""
    sorted_sessions = sorted(
        (dict(session) for session in sessions),
        key=lambda session: (
            int(session.get("start_ms", 0)),
            int(session.get("end_ms", 0)),
            str(session.get("id", "")),
        ),
    )
    track_ends: list[int] = []
    for session in sorted_sessions:
        start_ms = int(session.get("start_ms", 0))
        end_ms = max(start_ms, int(session.get("end_ms", start_ms)))
        session["end_ms"] = end_ms

        track_index = None
        for index, track_end in enumerate(track_ends):
            if track_end <= start_ms:
                track_index = index
                track_ends[index] = end_ms
                break
        if track_index is None:
            track_index = len(track_ends)
            track_ends.append(end_ms)
        session["track_index"] = track_index
    return sorted_sessions


def render_html_timeline_export(
    sessions: list[dict[str, Any]],
    title: str = "Cagelens Timeline Export",
) -> str:
    """Render a self-contained HTML timeline index for exported sessions."""
    sessions = assign_timeline_tracks(sessions)
    if sessions:
        start_ms = min(int(session["start_ms"]) for session in sessions)
        end_ms = max(int(session["end_ms"]) for session in sessions)
    else:
        now_ms = int(datetime.now().timestamp() * 1000)
        start_ms = now_ms
        end_ms = now_ms
    if end_ms <= start_ms:
        end_ms = start_ms + 60_000

    agents = sorted({str(session.get("agent") or "unknown") for session in sessions})
    workspaces = sorted({str(session.get("workspace_display") or "") for session in sessions})
    track_count = max((int(session.get("track_index", 0)) for session in sessions), default=-1) + 1
    timeline_data = {
        "sessions": sessions,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "agents": agents,
        "workspaces": workspaces,
    }
    timeline_json = (
        json.dumps(timeline_data, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )

    body = [
        "<!doctype html>",
        '<html lang="en" data-theme="light">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(title)}</title>",
        f'<meta name="cagelens-timeline-renderer" content="{HTML_TIMELINE_RENDERER_VERSION}">',
        f"<style>{_TIMELINE_CSS}</style>",
        "</head>",
        "<body>",
        '<main class="timeline-page">',
        '<header class="timeline-header">',
        f"<h1>{escape(title)}</h1>",
        '<dl class="timeline-summary">',
        f"<dt>Sessions</dt><dd>{len(sessions)}</dd>",
        f"<dt>Tracks</dt><dd>{track_count}</dd>",
        f"<dt>Agents</dt><dd>{escape(', '.join(agents) if agents else 'none')}</dd>",
        "</dl>",
        "</header>",
        '<section class="timeline-controls" aria-label="Timeline controls">',
        '<div class="control-row">',
        '<button type="button" data-fit>Fit</button>',
        '<button type="button" data-zoom="in">Zoom in</button>',
        '<button type="button" data-zoom="out">Zoom out</button>',
        '<label class="search-label">Search <input type="search" data-search placeholder="Session, workspace, prompt"></label>',
        "</div>",
        '<div class="control-row agent-filters" aria-label="Agent filters">',
    ]
    for agent in agents:
        token = _safe_class_token(agent)
        body.append(
            '<label class="agent-filter">'
            f'<input type="checkbox" data-agent-filter="{escape(agent, quote=True)}" checked>'
            f'<span class="agent-dot agent-{token}"></span>'
            f"{escape(agent)}</label>"
        )
    body.extend(
        [
            "</div>",
            '<label class="pan-label">Position <input type="range" min="0" max="1000" value="0" data-pan></label>',
            "</section>",
            '<section class="timeline-shell" aria-label="Session timeline">',
            '<div class="timeline-ticks" data-ticks></div>',
            f'<div class="timeline-tracks" data-track-count="{track_count}">',
        ]
    )
    for track_index in range(track_count):
        body.append(f'<div class="timeline-track" data-track="{track_index}">')
        for session in sessions:
            if int(session.get("track_index", 0)) != track_index:
                continue
            body.append(_render_timeline_bar(session))
        body.append("</div>")
    body.extend(
        [
            "</div>",
            "</section>",
            '<section class="session-detail" aria-live="polite">',
            '<div class="detail-empty" data-detail-empty>Select a session to view the conversation.</div>',
            '<div class="detail-card" data-detail-card hidden>',
            "<header>",
            "<h2 data-detail-title></h2>",
            '<a data-detail-link target="_blank" rel="noreferrer">Open full conversation</a>',
            "</header>",
            '<dl class="detail-meta" data-detail-meta></dl>',
            '<iframe title="Selected session conversation" data-detail-frame hidden></iframe>',
            "</div>",
            "</section>",
            "</main>",
            '<script type="application/json" id="timeline-data">',
            timeline_json,
            "</script>",
            f"<script>{_TIMELINE_SCRIPT}</script>",
            "</body>",
            "</html>",
            "",
        ]
    )
    return "\n".join(body)


def _render_timeline_bar(session: dict[str, Any]) -> str:
    agent = str(session.get("agent") or "unknown")
    classes = [
        "session-bar",
        f"agent-{_safe_class_token(agent)}",
    ]
    if session.get("is_subagent"):
        classes.append("session-subagent")
    label = "{} - {} - {}".format(
        session.get("agent") or "unknown",
        session.get("title") or session.get("id") or "session",
        session.get("duration_label") or "",
    )
    attrs = {
        "type": "button",
        "class": " ".join(classes),
        "data-session-id": str(session.get("id") or ""),
        "data-agent": agent,
        "data-workspace": str(session.get("workspace_display") or ""),
        "data-title": str(session.get("title") or ""),
        "data-start-ms": str(session.get("start_ms") or 0),
        "data-end-ms": str(session.get("end_ms") or 0),
        "aria-label": label,
    }
    attr_text = " ".join(f'{key}="{escape(value, quote=True)}"' for key, value in attrs.items())
    title = escape(str(session.get("title") or session.get("id") or "session"))
    return f"<button {attr_text}><span>{title}</span></button>"


def _safe_class_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")
    return token or "unknown"


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


_TIMELINE_CSS = """
:root {
  color-scheme: light dark;
  --bg: #f6f7f8;
  --panel: #ffffff;
  --ink: #182025;
  --muted: #5c6970;
  --line: #d6dde1;
  --track: #edf1f3;
  --focus: #111827;
  --claude: #2563eb;
  --codex: #16803c;
  --gemini: #b35c00;
  --pi: #7c3aed;
  --unknown: #64748b;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #101416;
    --panel: #181f23;
    --ink: #eef3f5;
    --muted: #a6b0b6;
    --line: #303a40;
    --track: #11181c;
    --focus: #f8fafc;
    --claude: #60a5fa;
    --codex: #4ade80;
    --gemini: #f59e0b;
    --pi: #a78bfa;
    --unknown: #94a3b8;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
button, input { font: inherit; }
.timeline-page { max-width: 1280px; margin: 0 auto; padding: 28px 18px 48px; }
.timeline-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: end;
  border-bottom: 1px solid var(--line);
  padding-bottom: 16px;
}
h1 { margin: 0; font-size: 28px; line-height: 1.2; letter-spacing: 0; }
h2 { margin: 0; font-size: 18px; letter-spacing: 0; }
.timeline-summary, .detail-meta {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 3px 10px;
  margin: 0;
}
.timeline-summary dt, .detail-meta dt { color: var(--ink); font-weight: 700; }
.timeline-summary dd, .detail-meta dd { color: var(--muted); margin: 0; overflow-wrap: anywhere; }
.timeline-controls {
  display: grid;
  gap: 10px;
  margin: 18px 0;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}
.control-row { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; }
.timeline-controls button {
  border: 1px solid var(--line);
  border-radius: 6px;
  background: transparent;
  color: var(--ink);
  cursor: pointer;
  padding: 5px 10px;
}
.search-label { display: flex; align-items: center; gap: 8px; min-width: min(100%, 360px); }
.search-label input { min-width: 0; width: 280px; max-width: 100%; }
.pan-label { display: grid; grid-template-columns: max-content minmax(160px, 1fr); gap: 10px; align-items: center; }
.agent-filter { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); }
.agent-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--unknown); display: inline-block; }
.agent-claude { --agent: var(--claude); }
.agent-codex { --agent: var(--codex); }
.agent-gemini { --agent: var(--gemini); }
.agent-pi { --agent: var(--pi); }
.agent-unknown { --agent: var(--unknown); }
.agent-dot.agent-claude, .agent-dot.agent-codex, .agent-dot.agent-gemini, .agent-dot.agent-pi, .agent-dot.agent-unknown {
  background: var(--agent);
}
.timeline-shell {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  overflow-x: auto;
}
.timeline-ticks {
  position: relative;
  min-width: 900px;
  height: 36px;
  border-bottom: 1px solid var(--line);
}
.timeline-tick {
  position: absolute;
  top: 0;
  bottom: 0;
  border-left: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
  padding-left: 5px;
  white-space: nowrap;
}
.timeline-tracks {
  position: relative;
  min-width: 900px;
  padding: 8px 0;
}
.timeline-track {
  position: relative;
  height: 34px;
  margin: 0 8px 5px;
  border-radius: 6px;
  background: var(--track);
}
.session-bar {
  position: absolute;
  top: 5px;
  height: 24px;
  min-width: 8px;
  border: 0;
  border-radius: 5px;
  background: var(--agent, var(--unknown));
  color: #ffffff;
  cursor: pointer;
  overflow: hidden;
  padding: 0 7px;
  text-align: left;
  white-space: nowrap;
}
.session-bar span { display: block; overflow: hidden; text-overflow: ellipsis; }
.session-bar[hidden] { display: none; }
.session-bar:focus-visible, .session-bar[aria-selected="true"] {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
  z-index: 2;
}
.session-subagent {
  background-image: repeating-linear-gradient(
    135deg,
    rgba(255,255,255,.24) 0,
    rgba(255,255,255,.24) 5px,
    rgba(0,0,0,.08) 5px,
    rgba(0,0,0,.08) 10px
  );
}
.session-detail { margin-top: 20px; }
.detail-empty, .detail-card {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  padding: 14px;
}
.detail-card header {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}
.detail-card a { color: var(--ink); }
.detail-card iframe {
  width: 100%;
  height: 70vh;
  margin-top: 14px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
}
@media (max-width: 720px) {
  .timeline-page { padding: 18px 10px 36px; }
  .timeline-header { grid-template-columns: 1fr; }
  .search-label, .pan-label { width: 100%; }
  .search-label input { width: 100%; }
}
"""


_TIMELINE_SCRIPT = """
const dataElement = document.getElementById('timeline-data');
const data = dataElement ? JSON.parse(dataElement.textContent || '{}') : {};
const sessions = data.sessions || [];
const fullStart = Number(data.start_ms || Date.now());
const fullEnd = Number(data.end_ms || fullStart + 60000);
let viewStart = fullStart;
let viewEnd = fullEnd;
let selectedId = null;

const bars = Array.from(document.querySelectorAll('.session-bar'));
const pan = document.querySelector('[data-pan]');
const search = document.querySelector('[data-search]');
const ticks = document.querySelector('[data-ticks]');
const detailEmpty = document.querySelector('[data-detail-empty]');
const detailCard = document.querySelector('[data-detail-card]');
const detailTitle = document.querySelector('[data-detail-title]');
const detailLink = document.querySelector('[data-detail-link]');
const detailMeta = document.querySelector('[data-detail-meta]');
const detailFrame = document.querySelector('[data-detail-frame]');

function sessionById(id) {
  return sessions.find((session) => String(session.id) === String(id));
}

function formatTime(ms) {
  const duration = viewEnd - viewStart;
  const date = new Date(ms);
  if (duration < 60 * 60 * 1000) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
  if (duration < 48 * 60 * 60 * 1000) {
    return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  if (duration < 90 * 24 * 60 * 60 * 1000) {
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }
  return date.toLocaleDateString([], { year: 'numeric', month: 'short' });
}

function renderTicks() {
  if (!ticks) return;
  ticks.textContent = '';
  const count = 6;
  for (let index = 0; index <= count; index += 1) {
    const position = index / count;
    const tick = document.createElement('span');
    tick.className = 'timeline-tick';
    tick.style.left = `${position * 100}%`;
    tick.textContent = formatTime(viewStart + ((viewEnd - viewStart) * position));
    ticks.appendChild(tick);
  }
}

function activeAgents() {
  return new Set(
    Array.from(document.querySelectorAll('[data-agent-filter]'))
      .filter((input) => input.checked)
      .map((input) => input.dataset.agentFilter)
  );
}

function updatePositions() {
  const span = Math.max(1, viewEnd - viewStart);
  const query = (search && search.value ? search.value : '').toLowerCase();
  const agents = activeAgents();
  bars.forEach((bar) => {
    const start = Number(bar.dataset.startMs || 0);
    const end = Math.max(start + 1, Number(bar.dataset.endMs || start + 1));
    const text = `${bar.dataset.title || ''} ${bar.dataset.workspace || ''} ${bar.dataset.sessionId || ''}`.toLowerCase();
    const filtered = !agents.has(bar.dataset.agent) || (query && !text.includes(query));
    const outside = end < viewStart || start > viewEnd;
    bar.hidden = Boolean(filtered || outside);
    const left = ((start - viewStart) / span) * 100;
    const right = ((end - viewStart) / span) * 100;
    bar.style.left = `${Math.max(0, Math.min(100, left))}%`;
    bar.style.width = `${Math.max(0.8, Math.min(100, right) - Math.max(0, left))}%`;
  });
  renderTicks();
}

function setView(start, end) {
  const fullSpan = Math.max(1, fullEnd - fullStart);
  const minSpan = Math.max(60000, fullSpan / 1000);
  let span = Math.max(minSpan, end - start);
  if (span > fullSpan) span = fullSpan;
  if (start < fullStart) start = fullStart;
  if (start + span > fullEnd) start = fullEnd - span;
  viewStart = start;
  viewEnd = start + span;
  if (pan) {
    const maxOffset = Math.max(1, fullSpan - span);
    pan.value = String(Math.round(((viewStart - fullStart) / maxOffset) * 1000));
  }
  updatePositions();
}

function selectSession(id) {
  selectedId = id;
  const session = sessionById(id);
  bars.forEach((bar) => {
    bar.setAttribute('aria-selected', String(bar.dataset.sessionId === String(id)));
  });
  if (!session || !detailCard || !detailEmpty) return;
  detailEmpty.hidden = true;
  detailCard.hidden = false;
  detailTitle.textContent = session.title || session.id || 'Session';
  detailLink.href = session.html_file;
  detailLink.textContent = 'Open full conversation';
  detailMeta.textContent = '';
  [
    ['Agent', session.agent],
    ['Workspace', session.workspace_display],
    ['Started', session.start],
    ['Ended', session.end],
    ['Duration', session.duration_label],
    ['Messages', session.message_count],
  ].forEach(([key, value]) => {
    const dt = document.createElement('dt');
    const dd = document.createElement('dd');
    dt.textContent = key;
    dd.textContent = value == null ? '' : String(value);
    detailMeta.append(dt, dd);
  });
  if (detailFrame) {
    detailFrame.src = session.html_file;
    detailFrame.hidden = false;
  }
}

document.querySelectorAll('[data-fit]').forEach((button) => {
  button.addEventListener('click', () => setView(fullStart, fullEnd));
});
document.querySelectorAll('[data-zoom]').forEach((button) => {
  button.addEventListener('click', () => {
    const factor = button.dataset.zoom === 'in' ? 0.5 : 2;
    const center = viewStart + ((viewEnd - viewStart) / 2);
    const span = (viewEnd - viewStart) * factor;
    setView(center - (span / 2), center + (span / 2));
  });
});
if (pan) {
  pan.addEventListener('input', () => {
    const span = viewEnd - viewStart;
    const fullSpan = fullEnd - fullStart;
    const maxOffset = Math.max(0, fullSpan - span);
    setView(fullStart + ((Number(pan.value) / 1000) * maxOffset), fullStart + ((Number(pan.value) / 1000) * maxOffset) + span);
  });
}
document.querySelectorAll('[data-agent-filter]').forEach((input) => {
  input.addEventListener('change', updatePositions);
});
if (search) search.addEventListener('input', updatePositions);
bars.forEach((bar) => {
  bar.addEventListener('click', () => selectSession(bar.dataset.sessionId));
});
setView(fullStart, fullEnd);
if (sessions.length === 1) selectSession(sessions[0].id);
"""
