"""HTML rendering for session export."""

from __future__ import annotations

import json
import re
from html import escape, unescape
from pathlib import Path
from typing import Any

from agent_history.backends.registry import get_backend
from agent_history.types import MessageDict

HTML_RENDERER_VERSION = 2
HTML_LIGHT_HIGHLIGHT_STYLE = "default"
HTML_DARK_HIGHLIGHT_STYLE = "github-dark"
HTML_TRIM_CHARS = 3000
HTML_TABLE_MIN_LINES = 2

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
        '<button class="theme-control" type="button" data-theme-toggle '
        'aria-pressed="false">Dark mode</button>',
        '<main class="page">',
        '<header class="export-header">',
        f"<h1>{escape(title)}</h1>",
    ]

    if not minimal:
        body.extend(_render_metadata(display_name, agent_type, messages))
    body.extend(
        [
            '<div class="page-controls" role="group" aria-label="Disclosure controls">',
            '<button class="utility-control" type="button" data-expand-all>Expand all</button>',
            '<button class="utility-control" type="button" data-collapse-all>Collapse all</button>',
            "</div>",
            "</header>",
            '<section class="turns" aria-label="Conversation turns">',
        ]
    )

    for turn_index, turn in enumerate(turns, 1):
        body.extend(_render_turn(turn, turn_index, len(turns), agent_type, minimal))

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
    turn: list[MessageDict],
    turn_index: int,
    total_turns: int,
    agent_type: str,
    minimal: bool,
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
        '<div class="turn-heading">',
        f"<h2>Turn {turn_index}</h2>",
        _render_turn_nav(turn_index, total_turns),
        "</div>",
        f'<div class="turn-meta"><span class="turn-summary">{escape(summary)}</span></div>',
        "</header>",
    ]
    for message_index, msg in enumerate(turn, 1):
        lines.extend(_render_message(msg, turn_index, message_index, agent_type, minimal))
    lines.append("</article>")
    return lines


def _render_turn_nav(turn_index: int, total_turns: int) -> str:
    previous_turn = turn_index - 1 if turn_index > 1 else None
    next_turn = turn_index + 1 if turn_index < total_turns else None
    return (
        '<div class="turn-nav">'
        + _render_turn_nav_button(previous_turn, "<", "Previous")
        + _render_turn_nav_button(next_turn, ">", "Next")
        + "</div>"
    )


def _render_turn_nav_button(target_turn: Any, label: str, direction: str) -> str:
    if target_turn is None:
        return (
            f'<button class="turn-nav-button" type="button" '
            f'aria-label="{escape(direction, quote=True)} turn" disabled>'
            f"{escape(label)}</button>"
        )
    return (
        f'<button class="turn-nav-button" type="button" data-scroll-turn="{target_turn}" '
        f'aria-label="{escape(direction, quote=True)} turn">{escape(label)}</button>'
    )


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
    return ['<div class="message-body">', _render_markdown(content), "</div>"]


def _render_tool_panel(content: str, origin: str) -> list[str]:
    title = "Tool input" if origin == "tool_call" else "Tool output"
    return [_render_code_or_diff(content, title)]


def _render_code_or_diff(content: str, title: str) -> str:
    fence_match = _CODE_FENCE_RE.search(content)
    text = fence_match.group("body") if fence_match else content
    language = _normalize_language(fence_match.group("label") if fence_match else "")

    if _looks_like_diff(text):
        return _render_diff_panel(title, text)

    panel_title = "JSON" if language == "json" else title
    return _render_code_panel(
        panel_title,
        text.strip(),
        language=language,
        raw_toggle=bool(language),
    )


def _highlight_code(text: str, language: str = "", style: str = "") -> str:
    try:
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import TextLexer, get_lexer_by_name
    except ImportError:
        return escape(text)

    try:
        lexer = get_lexer_by_name(language) if language else TextLexer()
    except Exception:
        lexer = TextLexer()
    try:
        formatter = HtmlFormatter(
            nowrap=True,
            noclasses=True,
            style=style or HTML_LIGHT_HIGHLIGHT_STYLE,
        )
        return highlight(text, lexer, formatter).rstrip("\n")
    except Exception:
        return escape(text)


def _render_pre(
    text: str,
    class_name: str = "",
    trim: bool = False,
    language: str = "",
    highlighted: bool = False,
    paired_highlight: bool = False,
) -> str:
    text = "" if text is None else str(text)

    def class_attr(value: str) -> str:
        return f' class="{escape(value, quote=True)}"' if value else ""

    def render_text(value: str, style: str = "") -> str:
        return _highlight_code(value, language, style) if highlighted else escape(value)

    def render_pre(value: str, extra_attrs: str = "") -> str:
        if highlighted and paired_highlight:
            light_class = " ".join(part for part in (class_name, "code-theme-light") if part)
            dark_class = " ".join(part for part in (class_name, "code-theme-dark") if part)
            return "\n".join(
                [
                    f"<pre{class_attr(light_class)}{extra_attrs}>"
                    f"{render_text(value, HTML_LIGHT_HIGHLIGHT_STYLE)}</pre>",
                    f"<pre{class_attr(dark_class)}{extra_attrs}>"
                    f"{render_text(value, HTML_DARK_HIGHLIGHT_STYLE)}</pre>",
                ]
            )
        return f"<pre{class_attr(class_name)}{extra_attrs}>{render_text(value)}</pre>"

    if not trim or len(text) <= HTML_TRIM_CHARS:
        return render_pre(text)

    short_text = text[:HTML_TRIM_CHARS].rstrip() + "\n... [truncated]"
    return "\n".join(
        [
            '<div class="trim-panel" data-trim-panel data-expanded="false">',
            render_pre(short_text, " data-trim-short"),
            render_pre(text, " data-trim-full hidden"),
            '<button class="trim-toggle" type="button" data-trim-toggle>Show more</button>',
            "</div>",
        ]
    )


def _render_view_toggle(rendered_label: str = "Rendered", raw_label: str = "Raw") -> str:
    return "\n".join(
        [
            '<span class="view-toggle" role="group" aria-label="Text view">',
            f'<button type="button" data-view-toggle="rendered" aria-pressed="true">'
            f"{escape(rendered_label)}</button>",
            f'<button type="button" data-view-toggle="raw" aria-pressed="false">'
            f"{escape(raw_label)}</button>",
            "</span>",
        ]
    )


def _render_code_title(
    title: str,
    raw_toggle: bool = False,
    rendered_label: str = "Rendered",
) -> str:
    if not raw_toggle:
        return f'<div class="code-title">{escape(title)}</div>'
    return "\n".join(
        [
            '<div class="code-title">',
            f'<span class="code-title-label">{escape(title)}</span>',
            _render_view_toggle(rendered_label, "Raw"),
            "</div>",
        ]
    )


def _render_code_panel(
    title: str,
    text: str,
    class_name: str = "",
    trim: bool = True,
    panel_class: str = "",
    language: str = "",
    raw_toggle: bool = False,
) -> str:
    pre_class = " ".join(part for part in ("code-text", class_name) if part)
    section_class = " ".join(part for part in ("code-panel", panel_class) if part)
    rendered_pre = _render_pre(
        text,
        pre_class,
        trim=trim,
        language=language,
        highlighted=bool(language),
        paired_highlight=bool(language),
    )
    if raw_toggle:
        body = "\n".join(
            [
                '<div data-view-content="rendered">',
                rendered_pre,
                "</div>",
                '<div data-view-content="raw" hidden>',
                _render_pre(
                    text, " ".join(part for part in (pre_class, "raw-text") if part), trim=trim
                ),
                "</div>",
            ]
        )
    else:
        body = rendered_pre
    data_panel = " data-view-panel" if raw_toggle else ""
    return "\n".join(
        [
            f'<section class="{escape(section_class, quote=True)}"{data_panel}>',
            _render_code_title(title, raw_toggle=raw_toggle, rendered_label="Highlighted"),
            '<div class="code-body">',
            body,
            "</div>",
            "</section>",
        ]
    )


def _looks_like_diff(text: str) -> bool:
    lines = text.splitlines()
    if any(line.startswith("diff --git ") for line in lines):
        return True
    if any(line.startswith("@@") for line in lines):
        return True
    has_add = any(line.startswith("+") and not line.startswith("+++") for line in lines)
    has_del = any(line.startswith("-") and not line.startswith("---") for line in lines)
    return has_add and has_del and any(line.startswith(("---", "+++", "@@")) for line in lines)


def _diff_line_class(line: str) -> str:
    if line.startswith("@@"):
        return "diff-line-hunk"
    if line.startswith(("---", "+++", "diff --git", "index ")):
        return "diff-line-meta"
    if line.startswith("+"):
        return "diff-line-add"
    if line.startswith("-"):
        return "diff-line-del"
    return "diff-line-context"


def _render_diff_lines(text: str) -> str:
    rows = []
    for raw_line in str(text or "").splitlines() or [""]:
        line_class = _diff_line_class(raw_line)
        is_change_line = line_class in {"diff-line-add", "diff-line-del"}
        marker = raw_line[:1] if is_change_line else ""
        content = raw_line[1:] if is_change_line else raw_line
        rows.append(
            "\n".join(
                [
                    f'<span class="diff-line {line_class}">',
                    f'<span class="diff-marker">{escape(marker)}</span>',
                    f'<span class="diff-content">{escape(content)}</span>',
                    "</span>",
                ]
            )
        )
    return '<div class="diff-view">' + "\n".join(rows) + "</div>"


def _render_diff_panel(title: str, text: str, trim: bool = True) -> str:
    text = "" if text is None else str(text)
    if trim and len(text) > HTML_TRIM_CHARS:
        short_text = text[:HTML_TRIM_CHARS].rstrip() + "\n... [truncated]"
        body = "\n".join(
            [
                '<div class="trim-panel" data-trim-panel data-expanded="false">',
                f"<div data-trim-short>{_render_diff_lines(short_text)}</div>",
                f"<div data-trim-full hidden>{_render_diff_lines(text)}</div>",
                '<button class="trim-toggle" type="button" data-trim-toggle>Show more</button>',
                "</div>",
            ]
        )
    else:
        body = _render_diff_lines(text)
    return "\n".join(
        [
            '<section class="code-panel diff-panel" data-view-panel>',
            _render_code_title(title, raw_toggle=True, rendered_label="Diff"),
            '<div class="code-body">',
            '<div data-view-content="rendered">',
            body,
            "</div>",
            '<div data-view-content="raw" hidden>',
            _render_pre(text, "code-text raw-text", trim=trim),
            "</div>",
            "</div>",
            "</section>",
        ]
    )


def _safe_link_url(url: str) -> str:
    stripped = str(url).strip()
    if stripped.startswith(("#", "/", "./", "../")):
        return stripped
    if re.match(r"^(https?|mailto):", stripped, flags=re.IGNORECASE):
        return stripped
    return "#"


def _inline_markdown(text: str) -> str:
    escaped = escape(text)

    def link_repl(match: re.Match) -> str:
        label = match.group(1)
        url = _safe_link_url(unescape(match.group(2)))
        return f'<a href="{escape(url, quote=True)}">{label}</a>'

    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    return escaped


def _render_paragraph(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines).strip()
    return f"<p>{_inline_markdown(text)}</p>" if text else ""


def _render_list(items: list[str], ordered: bool) -> str:
    tag = "ol" if ordered else "ul"
    rendered_items = "\n".join(f"<li>{_inline_markdown(item.strip())}</li>" for item in items)
    return f"<{tag}>\n{rendered_items}\n</{tag}>"


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _render_table(table_lines: list[str]) -> str:
    if len(table_lines) < HTML_TABLE_MIN_LINES:
        return _render_paragraph(table_lines)
    headers = _split_table_row(table_lines[0])
    rows = [_split_table_row(line) for line in table_lines[2:]]
    column_count = len(headers)

    def normalize(row: list[str]) -> list[str]:
        return (row + [""] * column_count)[:column_count]

    header_html = "".join(f"<th>{_inline_markdown(cell)}</th>" for cell in normalize(headers))
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_inline_markdown(cell)}</td>" for cell in normalize(row))
        body_rows.append(f"<tr>{cells}</tr>")
    return "\n".join(
        [
            "<table>",
            f"<thead><tr>{header_html}</tr></thead>",
            "<tbody>",
            "\n".join(body_rows),
            "</tbody>",
            "</table>",
        ]
    )


def _render_rendered_raw_panel(
    rendered_html: str,
    raw_text: str,
    rendered_label: str = "Formatted",
) -> str:
    return "\n".join(
        [
            '<div class="rendered-raw-panel markdown-raw-panel" data-view-panel>',
            '<div class="rendered-raw-toolbar">',
            _render_view_toggle(rendered_label, "Raw"),
            "</div>",
            '<div data-view-content="rendered">',
            rendered_html,
            "</div>",
            '<div data-view-content="raw" hidden>',
            _render_pre(raw_text, "message-text raw-text", trim=True),
            "</div>",
            "</div>",
        ]
    )


class _MarkdownRenderState:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.paragraph: list[str] = []
        self.list_items: list[str] = []
        self.list_ordered = False
        self.table_lines: list[str] = []
        self.in_fence = False
        self.fence_lang = ""
        self.fence_lines: list[str] = []

    def flush_paragraph(self) -> None:
        rendered = _render_paragraph(self.paragraph)
        if rendered:
            self.parts.append(rendered)
        self.paragraph = []

    def flush_list(self) -> None:
        if self.list_items:
            self.parts.append(_render_list(self.list_items, self.list_ordered))
        self.list_items = []

    def flush_table(self) -> None:
        if self.table_lines:
            self.parts.append(_render_table(self.table_lines))
        self.table_lines = []

    def flush_all(self) -> None:
        self.flush_paragraph()
        self.flush_list()
        self.flush_table()

    def append_fence_block(self) -> None:
        language = _normalize_language(self.fence_lang)
        self.parts.append(
            _render_code_panel(
                f"Code{f' ({language})' if language else ''}",
                "\n".join(self.fence_lines),
                language=language,
                raw_toggle=bool(language),
            )
        )
        self.in_fence = False
        self.fence_lang = ""
        self.fence_lines = []


def _handle_markdown_fence(state: _MarkdownRenderState, line: str) -> bool:
    fence_match = re.match(r"^```([A-Za-z0-9_+.-]*)\s*$", line)
    if not fence_match:
        return False
    if state.in_fence:
        state.append_fence_block()
    else:
        state.flush_all()
        state.in_fence = True
        state.fence_lang = fence_match.group(1)
    return True


def _handle_markdown_table(
    state: _MarkdownRenderState,
    lines: list[str],
    index: int,
    line: str,
) -> bool:
    if "|" in line and state.table_lines:
        state.table_lines.append(line)
        return True
    next_index = index + 1
    if "|" in line and next_index < len(lines) and _is_table_separator(lines[next_index]):
        state.flush_paragraph()
        state.flush_list()
        state.table_lines.append(line)
        return True
    if state.table_lines and (_is_table_separator(line) or "|" in line):
        state.table_lines.append(line)
        return True
    if state.table_lines:
        state.flush_table()
    return False


def _handle_markdown_heading(state: _MarkdownRenderState, line: str) -> bool:
    heading = re.match(r"^(#{1,3})\s+(.+)$", line)
    if not heading:
        return False
    state.flush_all()
    level = len(heading.group(1))
    state.parts.append(f"<h{level}>{_inline_markdown(heading.group(2).strip())}</h{level}>")
    return True


def _handle_markdown_list(state: _MarkdownRenderState, line: str) -> bool:
    bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
    numbered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
    if not (bullet or numbered):
        return False
    state.flush_paragraph()
    state.flush_table()
    ordered = bool(numbered)
    item = (numbered or bullet).group(1)
    if state.list_items and ordered != state.list_ordered:
        state.flush_list()
    state.list_ordered = ordered
    state.list_items.append(item)
    return True


def _consume_markdown_line(
    state: _MarkdownRenderState,
    lines: list[str],
    index: int,
    line: str,
) -> None:
    if _handle_markdown_fence(state, line):
        return
    if state.in_fence:
        state.fence_lines.append(line)
        return
    if not line.strip():
        state.flush_all()
        return
    if _handle_markdown_table(state, lines, index, line):
        return
    if _handle_markdown_heading(state, line):
        return
    if _handle_markdown_list(state, line):
        return
    state.flush_list()
    state.flush_table()
    state.paragraph.append(line)


def _render_markdown(text: str) -> str:
    lines = str(text).splitlines()
    state = _MarkdownRenderState()
    for index, line in enumerate(lines):
        _consume_markdown_line(state, lines, index, line)

    if state.in_fence:
        state.append_fence_block()
    state.flush_all()
    rendered = '<div class="markdown-body">' + "\n".join(state.parts) + "</div>"
    return _render_rendered_raw_panel(rendered, text)


def _normalize_language(label: str) -> str:
    language = str(label or "").strip().lower()
    aliases = {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "sh": "bash",
        "shell": "bash",
        "yml": "yaml",
        "md": "markdown",
    }
    return aliases.get(language, language)


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
  color-scheme: light;
  --bg: #f7f8fb;
  --panel: #ffffff;
  --panel-muted: #f1f4f8;
  --ink: #18212f;
  --muted: #5c6778;
  --line: #d9e0ea;
  --accent: #3158d4;
  --accent-soft: #e8edff;
  --tool: #fff7e6;
  --tool-border: #f2ddb2;
  --raw-soft: #f8f9fb;
  --inline-code-bg: rgba(255, 255, 255, 0.65);
  --code-bg: #f7f9fc;
  --code-title-bg: #f1f4f8;
  --code-title-text: #5c6778;
  --diff-add-bg: #dafbe1;
  --diff-add-border: #aceebb;
  --diff-add-text: #116329;
  --diff-del-bg: #ffebe9;
  --diff-del-border: #ffcecb;
  --diff-del-text: #82071e;
  --diff-hunk-bg: #ddf4ff;
  --diff-hunk-text: #0550ae;
  --diff-meta-bg: #f6f8fa;
  --diff-meta-text: #57606a;
}
html[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0d1117;
  --panel: #161b22;
  --panel-muted: #21262d;
  --ink: #e6edf3;
  --muted: #8b949e;
  --line: #30363d;
  --accent: #79c0ff;
  --accent-soft: #13233a;
  --tool: #2b2111;
  --tool-border: #7c5b1f;
  --raw-soft: #1c2128;
  --inline-code-bg: rgba(110, 118, 129, 0.25);
  --code-bg: #0d1117;
  --code-title-bg: #161b22;
  --code-title-text: #c9d1d9;
  --diff-add-bg: rgba(46, 160, 67, 0.18);
  --diff-add-border: rgba(46, 160, 67, 0.42);
  --diff-add-text: #aff5b4;
  --diff-del-bg: rgba(248, 81, 73, 0.16);
  --diff-del-border: rgba(248, 81, 73, 0.42);
  --diff-del-text: #ffdcd7;
  --diff-hunk-bg: rgba(56, 139, 253, 0.16);
  --diff-hunk-text: #a5d6ff;
  --diff-meta-bg: #161b22;
  --diff-meta-text: #8b949e;
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
.theme-control {
  position: fixed;
  top: 12px;
  right: 16px;
  z-index: 30;
  min-width: 112px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--panel);
  color: var(--ink);
  padding: 7px 11px;
  font: inherit;
  font-size: 13px;
  box-shadow: 0 6px 18px rgba(18, 25, 38, 0.16);
  cursor: pointer;
}
html[data-theme="dark"] .theme-control {
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
}
.page-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}
.utility-control {
  border: 1px dashed var(--line);
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  padding: 6px 9px;
}
.utility-control:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.metadata { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; margin: 0; color: var(--muted); }
.metadata dt { font-weight: 700; color: var(--ink); }
.metadata dd { margin: 0; overflow-wrap: anywhere; }
.turn {
  margin: 0 0 28px;
  border-top: 1px solid var(--line);
  padding-top: 20px;
  scroll-margin-top: 84px;
}
.turn-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}
.turn-heading { display: flex; align-items: center; gap: 10px; }
.turn-header h2 { margin: 0; font-size: 20px; }
.turn-meta { color: var(--muted); font-size: 12px; text-align: right; }
.turn-summary { color: var(--muted); }
.turn-nav { display: inline-flex; gap: 4px; }
.turn-nav-button {
  width: 28px;
  height: 28px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  line-height: 1;
}
.turn-nav-button:hover:not(:disabled) {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
}
.turn-nav-button:disabled { cursor: default; opacity: 0.35; }
.message {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  margin: 10px 0;
  padding: 14px;
}
.message-action { background: var(--tool); border-color: var(--tool-border); }
.message-header { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.message-header h3 { font-size: 15px; margin: 0; }
.message-header time { color: var(--muted); font-size: 12px; white-space: nowrap; }
.message-body.empty { color: var(--muted); font-style: italic; }
.markdown-body { font-size: 14px; }
.markdown-body > *:first-child { margin-top: 0; }
.markdown-body > *:last-child { margin-bottom: 0; }
.markdown-body h1, .markdown-body h2, .markdown-body h3 {
  letter-spacing: 0;
  margin: 14px 0 8px;
}
.markdown-body h1 { font-size: 20px; }
.markdown-body h2 { font-size: 17px; }
.markdown-body h3 { font-size: 15px; }
.markdown-body p { margin: 8px 0; overflow-wrap: anywhere; }
.markdown-body ul, .markdown-body ol { margin: 8px 0 8px 22px; padding: 0; }
.markdown-body table {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
}
.markdown-body th, .markdown-body td {
  border: 1px solid var(--line);
  padding: 6px 8px;
  text-align: left;
  vertical-align: top;
}
.markdown-body th { background: var(--panel-muted); font-weight: 700; }
.markdown-body tr:nth-child(even) td { background: var(--raw-soft); }
.markdown-body code {
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 1px 4px;
  background: var(--inline-code-bg);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 0.92em;
}
.rendered-raw-panel { position: relative; }
.rendered-raw-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.code-panel {
  margin-top: 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
  background: var(--code-bg);
}
.code-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--line);
  background: var(--code-title-bg);
  color: var(--code-title-text);
  font-size: 12px;
  font-weight: 700;
}
.code-title-label {
  color: var(--muted);
  text-transform: uppercase;
}
.view-toggle {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--panel);
  overflow: hidden;
  font-size: 11px;
  font-weight: 600;
}
.view-toggle button {
  border: 0;
  border-left: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  padding: 2px 7px;
}
.view-toggle button:first-child { border-left: 0; }
.view-toggle button[aria-pressed="true"] {
  background: var(--accent-soft);
  color: var(--accent);
}
.code-body { padding: 10px; }
.code-text, .message-text, pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.code-text, .message-text, .code-panel pre {
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 13px;
}
pre {
  margin: 0;
  padding: 12px;
  background: var(--code-bg);
  color: var(--ink);
  overflow: auto;
}
code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; }
.code-theme-dark { display: none; }
html[data-theme="dark"] .code-theme-light { display: none; }
html[data-theme="dark"] .code-theme-dark { display: block; }
.raw-text { background: var(--raw-soft); }
.trim-toggle {
  margin-top: 8px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  color: var(--accent);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  padding: 5px 8px;
}
.diff-panel .code-body { padding: 0; }
.diff-view {
  margin: 0;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  line-height: 1.45;
}
.diff-line {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  min-width: max-content;
  border-left: 3px solid transparent;
}
.diff-marker {
  padding: 1px 8px;
  user-select: none;
  text-align: center;
  color: var(--muted);
}
.diff-content { padding: 1px 12px 1px 4px; white-space: pre; }
.diff-line-add { background: var(--diff-add-bg); border-left-color: var(--diff-add-border); }
.diff-line-add .diff-marker, .diff-line-add .diff-content { color: var(--diff-add-text); }
.diff-line-del { background: var(--diff-del-bg); border-left-color: var(--diff-del-border); }
.diff-line-del .diff-marker, .diff-line-del .diff-content { color: var(--diff-del-text); }
.diff-line-hunk { background: var(--diff-hunk-bg); }
.diff-line-hunk .diff-content { color: var(--diff-hunk-text); font-weight: 600; }
.diff-line-meta { background: var(--diff-meta-bg); }
.diff-line-meta .diff-content { color: var(--diff-meta-text); font-weight: 600; }
.raw-payload { margin-top: 10px; color: var(--muted); }
.raw-payload summary { cursor: pointer; }
[hidden] { display: none !important; }
@media (max-width: 640px) {
  .page { padding: 20px 12px 40px; }
  .turn-header, .message-header { display: block; }
  .turn-heading { margin-bottom: 6px; }
  .turn-meta { text-align: left; }
  .message-header time { display: block; margin-top: 4px; }
  .theme-control { position: static; margin: 12px; }
}
"""


_SCRIPT = """
(function () {
  var themeOrder = ["light", "dark"];

  function systemTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function readTheme() {
    var stored = "";
    try {
      stored = window.localStorage ? window.localStorage.getItem("cagelensTheme") : "";
    } catch (error) {
      stored = "";
    }
    return themeOrder.indexOf(stored) >= 0 ? stored : systemTheme();
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.textContent = theme === "dark" ? "Light mode" : "Dark mode";
      button.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    });
  }

  document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      var nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      try {
        if (window.localStorage) {
          window.localStorage.setItem("cagelensTheme", nextTheme);
        }
      } catch (error) {
        // Ignore storage failures; theme still applies for this page view.
      }
      applyTheme(nextTheme);
    });
  });

  document.querySelectorAll("[data-scroll-turn]").forEach(function (button) {
    button.addEventListener("click", function () {
      var target = document.getElementById("turn-" + button.getAttribute("data-scroll-turn"));
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });

  var expandAll = document.querySelector("[data-expand-all]");
  if (expandAll) {
    expandAll.addEventListener("click", function () {
      document.querySelectorAll("details").forEach(function (details) {
        details.open = true;
      });
    });
  }

  var collapseAll = document.querySelector("[data-collapse-all]");
  if (collapseAll) {
    collapseAll.addEventListener("click", function () {
      document.querySelectorAll("details").forEach(function (details) {
        details.open = false;
      });
    });
  }

  document.querySelectorAll("[data-trim-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      var panel = button.closest("[data-trim-panel]");
      if (!panel) {
        return;
      }
      var expanded = panel.getAttribute("data-expanded") === "true";
      panel.setAttribute("data-expanded", expanded ? "false" : "true");
      panel.querySelectorAll("[data-trim-short]").forEach(function (el) {
        el.hidden = !expanded;
      });
      panel.querySelectorAll("[data-trim-full]").forEach(function (el) {
        el.hidden = expanded;
      });
      button.textContent = expanded ? "Show more" : "Show less";
    });
  });

  document.querySelectorAll("[data-view-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      var panel = button.closest("[data-view-panel]");
      if (!panel) {
        return;
      }
      var mode = button.getAttribute("data-view-toggle");
      panel.querySelectorAll("[data-view-content]").forEach(function (el) {
        el.hidden = el.getAttribute("data-view-content") !== mode;
      });
      panel.querySelectorAll("[data-view-toggle]").forEach(function (modeButton) {
        modeButton.setAttribute(
          "aria-pressed",
          modeButton.getAttribute("data-view-toggle") === mode ? "true" : "false"
        );
      });
    });
  });

  applyTheme(readTheme());
})();
"""
