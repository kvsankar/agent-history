"""HTML rendering for session export."""

from __future__ import annotations

import json
import re
from html import escape, unescape
from pathlib import Path
from typing import Any

from agent_history.backends.registry import get_backend
from agent_history.types import MessageDict

HTML_RENDERER_VERSION = 3
HTML_AGENT_GRAPH_ENABLED = False
HTML_LIGHT_HIGHLIGHT_STYLE = "default"
HTML_DARK_HIGHLIGHT_STYLE = "github-dark"
HTML_TRIM_CHARS = 3000
HTML_TABLE_MIN_LINES = 2
HTML_DEFAULT_LEVEL = 1
HTML_MAX_LEVEL = 4
HTML_ACTION_LEVEL = 2
HTML_FULL_IO_LEVEL = 3
HTML_TRACE_LEVEL = 4
HTML_SNIPPET_LINES = 8
HTML_SNIPPET_CHARS = 900
AGENT_GRAPH_ROW_HEIGHT = 32
AGENT_GRAPH_TOP = 18
AGENT_GRAPH_TRACK_GAP = 18
AGENT_GRAPH_MAIN_X = 18
AGENT_GRAPH_SUBAGENT_SPAN = 24

_TOOL_HEADING_RE = re.compile(r"\*\*\[(?:Tool Use|Tool): ([^\]]+)\]\*\*")
_CODE_FENCE_RE = re.compile(r"```(?P<label>[A-Za-z0-9_+.-]*)\n(?P<body>.*?)\n```", re.DOTALL)
_TOOL_LINE_NUMBER_RE = re.compile(r"^\s*\d+\s*[→↠⇒➜]\s?(?P<body>.*)$")


def render_html_export(
    jsonl_file: Path,
    agent_type: str,
    messages: list[MessageDict],
    minimal: bool = False,
    display_file: str | None = None,
    html_level: int = HTML_DEFAULT_LEVEL,
    lineage_records: list[dict[str, Any]] | None = None,
    lineage_hrefs: dict[str, str] | None = None,
) -> str:
    """Render a session as a self-contained HTML document."""
    initial_level = _normalize_html_level(html_level)
    backend = get_backend(agent_type)
    agent_title = (
        backend.markdown_title if backend and backend.markdown_title else agent_type.title()
    )
    title = f"{agent_title} Conversation"
    display_name = display_file or jsonl_file.name
    turns = _group_messages_into_turns(messages)
    agent_graph_state = "visible" if HTML_AGENT_GRAPH_ENABLED else "hidden"

    body = [
        "<!doctype html>",
        f'<html lang="en" data-theme="light" data-level="{initial_level}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(title)} - {escape(display_name)}</title>",
        f'<meta name="cagelens-renderer" content="{HTML_RENDERER_VERSION}">',
        f"<style>{_CSS}</style>",
        "</head>",
        f'<body data-agent-graph="{agent_graph_state}">',
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
            _render_level_controls(initial_level),
            '<button class="utility-control" type="button" data-expand-all>Expand all</button>',
            '<button class="utility-control" type="button" data-collapse-all>Collapse all</button>',
        ]
    )
    if HTML_AGENT_GRAPH_ENABLED:
        body.append(
            '<button class="graph-toggle-pill" type="button" data-agent-graph-toggle '
            'aria-pressed="false">Hide graph</button>'
        )
    body.extend(
        [
            "</div>",
            "</header>",
            '<div class="export-layout">',
        ]
    )
    if HTML_AGENT_GRAPH_ENABLED:
        body.append(
            _render_agent_graph(
                turns,
                agent_title,
                jsonl_file=jsonl_file,
                lineage_records=lineage_records,
                lineage_hrefs=lineage_hrefs,
            )
        )
    body.append('<section class="turns" aria-label="Conversation turns">')

    for turn_index, turn in enumerate(turns, 1):
        body.extend(
            _render_turn(
                turn,
                turn_index,
                len(turns),
                agent_type,
                minimal,
                initial_level,
            )
        )

    body.extend(
        [
            "</section>",
            "</div>",
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


def _normalize_html_level(value: int) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        level = HTML_DEFAULT_LEVEL
    return max(1, min(HTML_MAX_LEVEL, level))


def _html_level_attrs(min_level: int, initial_level: int) -> str:
    attrs = [f'data-level="{min_level}"']
    if initial_level < min_level:
        attrs.append("hidden")
    return " ".join(attrs)


def _render_level_controls(initial_level: int) -> str:
    labels = {
        1: "Conversation",
        2: "Actions",
        3: "Full I/O",
        4: "Trace",
    }
    buttons = []
    for level in range(1, HTML_MAX_LEVEL + 1):
        buttons.append(
            f'<button class="level-control" type="button" data-level-button="{level}" '
            f'aria-pressed="{str(initial_level == level).lower()}">{escape(labels[level])}</button>'
        )
    return (
        '<div class="level-controls" role="group" aria-label="Detail level">'
        + "\n".join(buttons)
        + "</div>"
    )


def _render_agent_graph(
    turns: list[list[MessageDict]],
    agent_title: str,
    *,
    jsonl_file: Path,
    lineage_records: list[dict[str, Any]] | None = None,
    lineage_hrefs: dict[str, str] | None = None,
) -> str:
    graph = _build_agent_graph_model(turns, jsonl_file, lineage_records or [], lineage_hrefs or {})
    width = graph["width"]
    height = graph["height"]
    lines = [
        '<aside class="agent-graph" data-agent-graph aria-label="Agent graph">',
        '<div class="agent-graph-header">',
        "<h2>Agent Graph</h2>",
        f'<span class="agent-graph-agent">{escape(agent_title)}</span>',
        "</div>",
        (
            f'<svg class="agent-graph-svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" '
            'role="img" aria-label="Agent turn graph">'
        ),
    ]
    lines.extend(_render_agent_graph_tracks(graph))
    lines.extend(_render_agent_graph_main_nodes(graph))
    lines.extend(_render_agent_graph_subagent_nodes(graph))
    lines.extend(["</svg>", "</aside>"])
    return "\n".join(lines)


def _build_agent_graph_model(
    turns: list[list[MessageDict]],
    jsonl_file: Path,
    lineage_records: list[dict[str, Any]],
    lineage_hrefs: dict[str, str],
) -> dict[str, Any]:
    source_file = str(jsonl_file)
    current_record = _lineage_record_for_source(lineage_records, source_file)
    current_session_id = (
        str(current_record.get("session_id"))
        if current_record and current_record.get("session_id")
        else _session_id_from_messages(turns)
    )
    lineage_children = [
        record
        for record in lineage_records
        if record.get("kind") == "subagent"
        and current_session_id
        and str(record.get("parent_session_id") or "") == current_session_id
    ]
    children_by_call_id = {
        str(record["invocation_tool_call_id"]): record
        for record in lineage_children
        if record.get("invocation_tool_call_id")
    }
    lanes = _agent_graph_lanes_for_turn_events(turns, children_by_call_id, lineage_hrefs)
    matched_ids = {lane["record"].get("session_id") for lane in lanes if lane.get("record")}
    for child in lineage_children:
        if child.get("session_id") in matched_ids:
            continue
        lanes.append(
            {
                "turn_index": 1,
                "tool_id": str(child.get("invocation_tool_call_id") or ""),
                "title": _lineage_title(child, "Sub-agent"),
                "result": _lineage_result(child),
                "record": child,
                "href": _lineage_href(child, lineage_hrefs),
            }
        )
    track_count = max(1, len(lanes) + 1)
    width = AGENT_GRAPH_MAIN_X + (track_count - 1) * AGENT_GRAPH_TRACK_GAP + 18
    height = max(128, AGENT_GRAPH_TOP + max(1, len(turns)) * AGENT_GRAPH_ROW_HEIGHT + 24)
    return {
        "turns": turns,
        "lanes": lanes,
        "track_count": track_count,
        "width": width,
        "height": height,
    }


def _agent_graph_lanes_for_turn_events(
    turns: list[list[MessageDict]],
    children_by_call_id: dict[str, dict[str, Any]],
    lineage_hrefs: dict[str, str],
) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    for turn_index, turn in enumerate(turns, 1):
        for event in _subagent_events_for_turn(turn):
            child = children_by_call_id.get(event.get("tool_id", ""))
            if not _should_render_subagent_graph_event(event, child):
                continue
            lane = {
                **event,
                "turn_index": turn_index,
                "record": child,
                "href": _lineage_href(child, lineage_hrefs) if child else "",
            }
            if child:
                lane["title"] = _lineage_title(child, event.get("title", "Sub-agent"))
                lane["result"] = _lineage_result(child) or event.get("result", "")
            lanes.append(lane)
    return lanes


def _should_render_subagent_graph_event(
    event: dict[str, str], child: dict[str, Any] | None
) -> bool:
    if child:
        return True
    if str(event.get("title") or "").strip().lower() != "spawn_agent":
        return True
    result = str(event.get("result") or "").lower()
    return "agent_id" in result or "failed" in result or "error" in result


def _render_agent_graph_tracks(graph: dict[str, Any]) -> list[str]:
    lines = ['<g class="agent-graph-tracks" aria-hidden="true">']
    bottom = graph["height"] - 18
    for track_index in range(graph["track_count"]):
        x = _agent_graph_track_x(track_index)
        track_class = "agent-graph-main-track" if track_index == 0 else "agent-graph-sub-track"
        lines.append(f'<line class="{track_class}" x1="{x}" y1="24" x2="{x}" y2="{bottom}" />')
    lines.append("</g>")
    return lines


def _render_agent_graph_main_nodes(graph: dict[str, Any]) -> list[str]:
    lines = ['<g class="agent-graph-main-nodes">']
    for turn_index, turn in enumerate(graph["turns"], 1):
        y = _agent_graph_turn_y(turn_index)
        lines.extend(
            [
                f'<a class="agent-graph-turn-link" href="#turn-{turn_index}" '
                f'data-scroll-turn="{turn_index}">',
                f"<title>Turn {turn_index}: {escape(_turn_action_summary(turn))}</title>",
                f'<circle class="agent-graph-main-node" cx="{AGENT_GRAPH_MAIN_X}" cy="{y}" r="6" />',
                "</a>",
            ]
        )
    lines.append("</g>")
    return lines


def _render_agent_graph_subagent_nodes(graph: dict[str, Any]) -> list[str]:
    lines = ['<g class="agent-graph-subagent-nodes">']
    for lane_index, lane in enumerate(graph["lanes"], 1):
        parent_x = AGENT_GRAPH_MAIN_X
        x = _agent_graph_track_x(lane_index)
        start_y = _agent_graph_turn_y(int(lane.get("turn_index") or 1))
        end_y = min(graph["height"] - 28, start_y + AGENT_GRAPH_SUBAGENT_SPAN)
        turn_index = int(lane.get("turn_index") or 1)
        href = str(lane.get("href") or f"#turn-{turn_index}")
        click_attrs = (
            "" if lane.get("href") else f' data-scroll-turn="{turn_index}" data-open-turn-actions'
        )
        tooltip = _agent_graph_lane_tooltip(lane)
        lines.extend(
            [
                '<g class="agent-graph-branch-edge" aria-hidden="true">',
                (
                    f'<path d="M {parent_x + 7} {start_y} C {parent_x + 10} {start_y}, '
                    f'{x - 10} {start_y}, {x - 5} {start_y}" />'
                ),
                f'<line x1="{x}" y1="{start_y}" x2="{x}" y2="{end_y}" />',
                "</g>",
                f'<a class="agent-graph-subagent-link" href="{escape(href, quote=True)}"{click_attrs}>',
                f"<title>{escape(tooltip)}</title>",
                f'<circle class="agent-graph-subagent-node" cx="{x}" cy="{start_y}" r="6" />',
                f'<circle class="agent-graph-merge-node" cx="{x}" cy="{end_y}" r="4" />',
                "</a>",
            ]
        )
    lines.append("</g>")
    return lines


def _agent_graph_track_x(track_index: int) -> int:
    return AGENT_GRAPH_MAIN_X + track_index * AGENT_GRAPH_TRACK_GAP


def _agent_graph_turn_y(turn_index: int) -> int:
    return AGENT_GRAPH_TOP + (turn_index - 1) * AGENT_GRAPH_ROW_HEIGHT


def _agent_graph_lane_tooltip(lane: dict[str, Any]) -> str:
    parts = [str(lane.get("title") or "Sub-agent")]
    if lane.get("result"):
        parts.append(str(lane["result"]))
    parts.append("Open sub-agent transcript" if lane.get("href") else "Open parent turn actions")
    return " - ".join(parts)


def _lineage_record_for_source(
    lineage_records: list[dict[str, Any]], source_file: str
) -> dict[str, Any] | None:
    for record in lineage_records:
        if str(record.get("source_file") or "") == source_file:
            return record
    return None


def _session_id_from_messages(turns: list[list[MessageDict]]) -> str:
    for turn in turns:
        for msg in turn:
            if msg.get("session_id"):
                return str(msg["session_id"])
    return ""


def _lineage_href(record: dict[str, Any] | None, lineage_hrefs: dict[str, str]) -> str:
    if not record:
        return ""
    source_file = str(record.get("source_file") or "")
    return lineage_hrefs.get(source_file, "")


def _lineage_title(record: dict[str, Any], fallback: str) -> str:
    for key in ("agent_name", "agent_role", "agent_id", "session_id"):
        if record.get(key):
            return str(record[key])
    return fallback


def _lineage_result(record: dict[str, Any]) -> str:
    if record.get("status"):
        return str(record["status"])
    if record.get("last_agent_message"):
        return str(record["last_agent_message"])
    return ""


def _subagent_events_for_turn(turn: list[MessageDict]) -> list[dict[str, str]]:
    results_by_tool_id = {
        tool_id: result
        for msg in turn
        if _semantic_origin(msg) == "tool_result"
        for tool_id, result in [_tool_result_summary(msg)]
        if tool_id
    }
    events: list[dict[str, str]] = []
    for msg in turn:
        structured_events = _subagent_events_from_structured_calls(msg, results_by_tool_id)
        if structured_events:
            events.extend(structured_events)
            continue
        content = str(msg.get("content") or "")
        block_events = _subagent_events_from_tool_blocks(content, results_by_tool_id)
        if block_events:
            events.extend(block_events)
            continue
        if _semantic_origin(msg) != "tool_call":
            continue
        tool_name = _tool_name(msg) or ""
        if not _is_subagent_tool_name(tool_name):
            continue
        tool_id = _tool_id_from_content(content)
        title = _subagent_title_from_content(content) or tool_name or "Sub-agent"
        events.append(_subagent_event(tool_id, title, results_by_tool_id.get(tool_id, "")))
    return events


def _subagent_events_from_structured_calls(
    msg: MessageDict, results_by_tool_id: dict[str, str]
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for call in msg.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        tool_name = str(call.get("name") or call.get("displayName") or "")
        if not _is_subagent_tool_name(tool_name):
            continue
        tool_id = str(call.get("id") or call.get("call_id") or call.get("callId") or "")
        title = _subagent_title_from_tool_call(call) or tool_name or "Sub-agent"
        events.append(_subagent_event(tool_id, title, results_by_tool_id.get(tool_id, "")))
    return events


def _subagent_events_from_tool_blocks(
    content: str, results_by_tool_id: dict[str, str]
) -> list[dict[str, str]]:
    matches = list(_TOOL_HEADING_RE.finditer(content))
    if len(matches) < 2:
        return []
    events: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        tool_name = match.group(1)
        if not _is_subagent_tool_name(tool_name):
            continue
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        block = content[start:end]
        tool_id = _tool_id_from_content(block)
        title = _subagent_title_from_content(block) or tool_name or "Sub-agent"
        events.append(_subagent_event(tool_id, title, results_by_tool_id.get(tool_id, "")))
    return events


def _subagent_event(tool_id: str, title: str, result: str) -> dict[str, str]:
    return {
        "tool_id": tool_id,
        "title": title,
        "result": result,
    }


def _subagent_title_from_tool_call(call: dict[str, Any]) -> str | None:
    args = call.get("input") or call.get("arguments") or {}
    if isinstance(args, str):
        try:
            loaded = json.loads(args)
        except json.JSONDecodeError:
            loaded = {}
        args = loaded if isinstance(loaded, dict) else {}
    if not isinstance(args, dict):
        return None
    for key in ("description", "subagent_type", "agent_type", "prompt"):
        value = args.get(key)
        if value:
            return _truncate_graph_text(str(value))
    return None


def _tool_result_summary(msg: MessageDict) -> tuple[str, str]:
    content = str(msg.get("content") or "")
    tool_id = _tool_id_from_content(content)
    body = content
    fence_match = re.search(r"```\n(?P<body>.*?)\n```", content, re.DOTALL)
    if fence_match:
        body = fence_match.group("body")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    summary = next(
        (
            line
            for line in lines
            if not line.startswith("**[Tool Result") and not line.startswith("Tool Use ID:")
        ),
        "",
    )
    return tool_id, _truncate_graph_text(summary)


def _subagent_title_from_content(content: str) -> str | None:
    data = _json_input_from_tool_content(content)
    for key in ("description", "subagent_type", "agent_type", "prompt"):
        value = data.get(key)
        if value:
            return _truncate_graph_text(str(value))
    return None


def _json_input_from_tool_content(content: str) -> dict[str, Any]:
    match = re.search(r"Input:\s*```json\n(?P<body>.*?)\n```", content, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group("body"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _tool_id_from_content(content: str) -> str:
    match = re.search(r"(?:Tool (?:ID|Use ID)|Call ID): `([^`]+)`", content)
    return match.group(1) if match else ""


def _is_subagent_tool_name(tool_name: str) -> bool:
    normalized = tool_name.strip().lower()
    return normalized in {"task", "subagent", "sub_agent", "spawn_agent"}


def _truncate_graph_text(value: str, limit: int = 96) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _starts_new_turn(msg: MessageDict) -> bool:
    return _semantic_origin(msg) in {"human", "parent_agent"}


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
    initial_level: int,
) -> list[str]:
    conversation_messages = _conversation_messages_for_turn(turn)
    action_messages = [
        msg
        for msg in turn
        if _message_detail_level(msg, turn) == HTML_ACTION_LEVEL
        or _semantic_origin(msg) in {"subagent_event", "tool_call", "tool_result"}
    ]
    summary = _turn_action_summary(turn)

    lines = [
        f'<article class="turn" id="turn-{turn_index}" data-turn="{turn_index}">',
        '<header class="turn-header">',
        '<div class="turn-heading">',
        f"<h2>Turn {turn_index}</h2>",
        _render_turn_nav(turn_index, total_turns),
        _render_turn_level_controls(),
        "</div>",
        f'<div class="turn-meta"><span class="turn-summary">{escape(summary)}</span></div>',
        "</header>",
        '<section class="turn-conversation">',
    ]
    for message_index, msg in enumerate(conversation_messages, 1):
        lines.extend(
            _render_message(
                msg,
                turn_index,
                message_index,
                agent_type,
                minimal,
                initial_level,
                min_level=HTML_DEFAULT_LEVEL,
                include_details=False,
            )
        )
    if not conversation_messages:
        lines.append(
            f'<p class="empty" {_html_level_attrs(HTML_TRACE_LEVEL, initial_level)}>'
            "No conversation text in this turn.</p>"
        )
    lines.append("</section>")
    if action_messages:
        open_attr = " open" if initial_level >= HTML_ACTION_LEVEL else ""
        lines.extend(
            [
                f'<details class="turn-actions" {_html_level_attrs(HTML_ACTION_LEVEL, initial_level)} '
                f'data-open-level="{HTML_ACTION_LEVEL}"{open_attr}>',
                f"<summary>Actions: {escape(_turn_action_summary(turn))}</summary>",
            ]
        )
        for message_index, msg in enumerate(action_messages, 1):
            lines.extend(
                _render_message(
                    msg,
                    turn_index,
                    message_index,
                    agent_type,
                    minimal,
                    initial_level,
                    min_level=HTML_ACTION_LEVEL,
                    include_details=True,
                )
            )
        lines.append("</details>")
    if turn and not minimal:
        open_attr = " open" if initial_level >= HTML_TRACE_LEVEL else ""
        lines.extend(
            [
                f'<details class="turn-trace" {_html_level_attrs(HTML_TRACE_LEVEL, initial_level)} '
                f'data-open-level="{HTML_TRACE_LEVEL}"{open_attr}>',
                "<summary>Full trace</summary>",
            ]
        )
        for message_index, msg in enumerate(turn, 1):
            lines.extend(
                _render_message(
                    msg,
                    turn_index,
                    message_index,
                    agent_type,
                    minimal,
                    initial_level,
                    min_level=HTML_TRACE_LEVEL,
                    include_details=True,
                    trace_label=True,
                )
            )
        lines.append("</details>")
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


def _render_turn_level_controls() -> str:
    controls = [
        (HTML_ACTION_LEVEL, "Actions"),
        (HTML_FULL_IO_LEVEL, "Full I/O"),
        (HTML_TRACE_LEVEL, "Trace"),
    ]
    buttons = [
        f'<button class="turn-level-button" type="button" data-turn-level-button="{level}" '
        f'aria-pressed="false">{escape(label)}</button>'
        for level, label in controls
    ]
    return (
        '<div class="turn-level-controls" role="group" aria-label="Turn detail level">'
        + "\n".join(buttons)
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


def _conversation_messages_for_turn(turn: list[MessageDict]) -> list[MessageDict]:
    final_assistant = _final_assistant_message(turn)
    messages: list[MessageDict] = []
    for msg in turn:
        origin = _semantic_origin(msg)
        if origin in {"human", "parent_agent"} or msg is final_assistant:
            messages.append(msg)
    return messages


def _final_assistant_message(turn: list[MessageDict]) -> MessageDict | None:
    for msg in reversed(turn):
        if _semantic_origin(msg) == "assistant" and str(msg.get("content") or "").strip():
            return msg
    return None


def _message_detail_level(msg: MessageDict, turn: list[MessageDict]) -> int:
    origin = _semantic_origin(msg)
    if origin in {"human", "parent_agent"} or msg is _final_assistant_message(turn):
        return HTML_DEFAULT_LEVEL
    if origin in {"assistant", "subagent_event", "tool_call", "tool_result"}:
        return HTML_ACTION_LEVEL
    return HTML_TRACE_LEVEL


def _turn_action_summary(turn: list[MessageDict]) -> str:
    subagent_events = sum(1 for msg in turn if _semantic_origin(msg) == "subagent_event")
    tool_calls = sum(1 for msg in turn if _semantic_origin(msg) == "tool_call")
    tool_results = sum(1 for msg in turn if _semantic_origin(msg) == "tool_result")
    assistant_notes = sum(
        1
        for msg in turn
        if _semantic_origin(msg) == "assistant" and msg is not _final_assistant_message(turn)
    )
    parts = []
    if subagent_events:
        parts.append(f"{subagent_events} sub-agent event{'s' if subagent_events != 1 else ''}")
    if tool_calls:
        parts.append(f"{tool_calls} tool call{'s' if tool_calls != 1 else ''}")
    if tool_results:
        parts.append(f"{tool_results} tool result{'s' if tool_results != 1 else ''}")
    if assistant_notes:
        parts.append(f"{assistant_notes} assistant note{'s' if assistant_notes != 1 else ''}")
    return ", ".join(parts) if parts else "No recorded actions"


def _render_message(
    msg: MessageDict,
    turn_index: int,
    message_index: int,
    agent_type: str,
    minimal: bool,
    initial_level: int,
    min_level: int = HTML_DEFAULT_LEVEL,
    include_details: bool = True,
    trace_label: bool = False,
) -> list[str]:
    origin = _semantic_origin(msg)
    role = str(msg.get("role") or "unknown").lower()
    label = f"Raw {_message_label(msg, origin)}" if trace_label else _message_label(msg, origin)
    classes = ["message", f"message-{origin.replace('_', '-')}"]
    if origin in {"subagent_event", "tool_call", "tool_result"}:
        classes.append("message-action")

    timestamp = str(msg.get("timestamp") or "")
    content = str(msg.get("content") or "")
    raw_payload = _raw_payload(msg)

    lines = [
        '<section class="{}" {} data-agent="{}" data-role="{}" data-origin="{}" '
        'data-turn="{}" data-message="{}">'.format(
            " ".join(classes),
            _html_level_attrs(min_level, initial_level),
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
    lines.append("</header>")
    if include_details and min_level == HTML_ACTION_LEVEL:
        lines.extend(_render_action_content_panel(msg, content, origin, initial_level))
    else:
        lines.extend(_render_content_panel(msg, content, origin))
    if raw_payload and not minimal and trace_label:
        lines.extend(_render_raw_panel(raw_payload))
    lines.append("</section>")
    return lines


def _message_label(msg: MessageDict, origin: str) -> str:
    if origin == "parent_agent":
        return "Parent agent"
    if origin == "subagent_event":
        status = str(msg.get("subagent_status") or "notification").replace("_", " ")
        return f"Sub-agent {status}"
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
    if msg.get("is_subagent_notification"):
        return "subagent_event"
    if msg.get("is_parent_agent_message"):
        return "parent_agent"
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


def _render_action_content_panel(
    msg: MessageDict,
    content: str,
    origin: str,
    initial_level: int,
) -> list[str]:
    if not content and msg.get("tool_calls"):
        content = "\n\n".join(_format_structured_tool_call(call) for call in msg["tool_calls"])
    if not content:
        return ['<div class="message-body empty">No visible content</div>']

    if origin == "assistant":
        return [
            '<div class="message-body action-brief">',
            _render_markdown(_conversation_snippet(content)),
            "</div>",
        ]

    snippet = _conversation_snippet(content)
    full_label = "Full output" if origin == "tool_result" else "Full input"
    return [
        '<div class="message-body action-brief">',
        _render_code_or_diff(snippet, "Snippet", raw_toggle=False),
        "</div>",
        _render_full_io_details(content, full_label, initial_level),
    ]


def _render_tool_panel(content: str, origin: str) -> list[str]:
    title = "Tool input" if origin == "tool_call" else "Tool output"
    return [_render_code_or_diff(content, title)]


def _render_code_or_diff(content: str, title: str, raw_toggle: bool | None = None) -> str:
    fence_match = _CODE_FENCE_RE.search(content)
    raw_text = fence_match.group("body") if fence_match else content
    text = _strip_tool_line_numbers(raw_text)
    explicit_language = _normalize_language(fence_match.group("label") if fence_match else "")
    language = explicit_language or _infer_code_language(title, text)

    if _looks_like_diff(text):
        return _render_diff_panel(title, text, raw_text=raw_text)

    panel_title = "JSON" if language == "json" else title
    return _render_code_panel(
        panel_title,
        text.strip(),
        language=language,
        raw_toggle=bool(language) if raw_toggle is None else raw_toggle,
        raw_text=raw_text.strip("\n"),
    )


def _conversation_snippet(text: str) -> str:
    lines = str(text or "").splitlines()
    snippet = "\n".join(lines[:HTML_SNIPPET_LINES])
    if len(snippet) > HTML_SNIPPET_CHARS:
        snippet = snippet[:HTML_SNIPPET_CHARS].rstrip()
    clipped = len(lines) > HTML_SNIPPET_LINES or len(str(text or "")) > len(snippet)
    return f"{snippet}\n... [truncated]" if clipped else snippet


def _render_full_io_details(content: str, label: str, initial_level: int) -> str:
    open_attr = " open" if initial_level >= HTML_FULL_IO_LEVEL else ""
    return "\n".join(
        [
            f'<details class="full-io" {_html_level_attrs(HTML_FULL_IO_LEVEL, initial_level)} '
            f'data-open-level="{HTML_FULL_IO_LEVEL}"{open_attr}>',
            f"<summary>{escape(label)}</summary>",
            _render_code_or_diff(content, label),
            "</details>",
        ]
    )


def _strip_tool_line_numbers(text: str) -> str:
    lines = str(text or "").splitlines()
    if not lines:
        return str(text or "")
    stripped_lines: list[str] = []
    stripped_count = 0
    for line in lines:
        match = _TOOL_LINE_NUMBER_RE.match(line)
        if match:
            stripped_count += 1
            stripped_lines.append(match.group("body"))
        else:
            stripped_lines.append(line)
    return "\n".join(stripped_lines) if stripped_count else str(text or "")


def _infer_code_language(title: str, text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped:
        return ""
    if _looks_like_json(stripped):
        return "json"
    if _looks_like_markdown(stripped):
        return "markdown"
    title_lower = str(title or "").lower()
    if "markdown" in title_lower:
        return "markdown"
    return ""


def _looks_like_json(text: str) -> bool:
    if not text.startswith(("{", "[")):
        return False
    try:
        json.loads(text)
    except (TypeError, ValueError):
        return False
    return True


def _looks_like_markdown(text: str) -> bool:
    lines = str(text or "").splitlines()
    if any(re.match(r"^#{1,6}\s+\S+", line) for line in lines):
        return True
    if any(line.startswith("```") for line in lines):
        return True
    if any(re.search(r"\*\*[^*]+\*\*", line) for line in lines):
        return True
    if any(
        "|" in line and index + 1 < len(lines) and _is_table_separator(lines[index + 1])
        for index, line in enumerate(lines)
    ):
        return True
    return False


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


def _render_copy_button() -> str:
    return '<button class="copy-button" type="button" data-copy-button>Copy</button>'


def _render_copy_source(text: str, view: str = "rendered") -> str:
    return (
        f'<pre class="copy-source" data-copy-content="{escape(view, quote=True)}" hidden>'
        f"{escape(str(text or ''))}</pre>"
    )


def _render_code_title(
    title: str,
    raw_toggle: bool = False,
    rendered_label: str = "Rendered",
) -> str:
    controls = [_render_copy_button()]
    if raw_toggle:
        controls.insert(0, _render_view_toggle(rendered_label, "Raw"))
    controls_html = '<span class="code-title-controls">' + "\n".join(controls) + "</span>"
    if not raw_toggle:
        return "\n".join(
            [
                '<div class="code-title">',
                f'<span class="code-title-label">{escape(title)}</span>',
                controls_html,
                "</div>",
            ]
        )
    return "\n".join(
        [
            '<div class="code-title">',
            f'<span class="code-title-label">{escape(title)}</span>',
            controls_html,
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
    raw_text: str | None = None,
) -> str:
    raw_text = text if raw_text is None else raw_text
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
                    raw_text, " ".join(part for part in (pre_class, "raw-text") if part), trim=trim
                ),
                "</div>",
            ]
        )
    else:
        body = rendered_pre
    data_panel = " data-view-panel" if raw_toggle else ""
    return "\n".join(
        [
            f'<section class="{escape(section_class, quote=True)}"{data_panel} data-copy-scope>',
            _render_code_title(title, raw_toggle=raw_toggle, rendered_label="Highlighted"),
            _render_copy_source(text, "rendered"),
            _render_copy_source(raw_text, "raw"),
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


def _render_diff_panel(
    title: str,
    text: str,
    trim: bool = True,
    raw_text: str | None = None,
) -> str:
    text = "" if text is None else str(text)
    raw_text = text if raw_text is None else str(raw_text)
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
            '<section class="code-panel diff-panel" data-view-panel data-copy-scope>',
            _render_code_title(title, raw_toggle=True, rendered_label="Diff"),
            _render_copy_source(text, "rendered"),
            _render_copy_source(raw_text, "raw"),
            '<div class="code-body">',
            '<div data-view-content="rendered">',
            body,
            "</div>",
            '<div data-view-content="raw" hidden>',
            _render_pre(raw_text, "code-text raw-text", trim=trim),
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
            '<div class="rendered-raw-panel markdown-raw-panel" data-view-panel data-copy-scope>',
            _render_copy_source(raw_text, "rendered"),
            _render_copy_source(raw_text, "raw"),
            '<div class="rendered-raw-toolbar">',
            _render_view_toggle(rendered_label, "Raw"),
            _render_copy_button(),
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
        '<details class="raw-payload" data-copy-scope>',
        "<summary>Raw message</summary>",
        '<div class="raw-payload-controls">',
        _render_copy_button(),
        "</div>",
        _render_copy_source(raw_payload, "rendered"),
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
  --user-bg: #f0f7ff;
  --user-border: #cfe4ff;
  --user-title: #24527a;
  --assistant-bg: #f3fbf6;
  --assistant-border: #cfe9d9;
  --assistant-title: #2f6548;
  --parent-agent-bg: #f7f2ff;
  --parent-agent-border: #ddd0f3;
  --parent-agent-title: #6b4ca4;
  --subagent-event-bg: #fff7ed;
  --subagent-event-border: #fed7aa;
  --subagent-event-title: #9a4c00;
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
  --user-bg: #111d2b;
  --user-border: #294866;
  --user-title: #9cccff;
  --assistant-bg: #11241c;
  --assistant-border: #2b5a41;
  --assistant-title: #a6e3ba;
  --parent-agent-bg: #20172f;
  --parent-agent-border: #4b3b6f;
  --parent-agent-title: #d7c4ff;
  --subagent-event-bg: #2a1d10;
  --subagent-event-border: #7a4d1f;
  --subagent-event-title: #ffd7a3;
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
.level-controls {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  background: var(--panel);
}
.level-control {
  border: 0;
  border-left: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  padding: 6px 10px;
}
.level-control:first-child { border-left: 0; }
.level-control[aria-pressed="true"] {
  background: var(--accent-soft);
  color: var(--accent);
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
.graph-toggle-pill {
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--panel);
  color: var(--accent);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  padding: 6px 10px;
}
.graph-toggle-pill[aria-pressed="true"] {
  background: var(--accent-soft);
}
.metadata { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; margin: 0; color: var(--muted); }
.metadata dt { font-weight: 700; color: var(--ink); }
.metadata dd { margin: 0; overflow-wrap: anywhere; }
.export-layout {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: 28px;
  align-items: start;
}
body[data-agent-graph="hidden"] .export-layout {
  grid-template-columns: minmax(0, 1fr);
}
body[data-agent-graph="hidden"] .agent-graph {
  display: none;
}
.agent-graph {
  position: sticky;
  top: 18px;
  max-height: calc(100vh - 36px);
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  padding: 14px;
}
.agent-graph-header {
  margin-bottom: 12px;
}
.agent-graph-header h2 {
  margin: 0;
  font-size: 16px;
}
.agent-graph-agent {
  display: block;
  margin-top: 2px;
  color: var(--muted);
  font-size: 12px;
}
.agent-graph-svg {
  display: block;
  width: auto;
  max-width: none;
  min-width: 260px;
  height: auto;
  overflow: visible;
}
.agent-graph-svg a {
  cursor: pointer;
  text-decoration: none;
}
.agent-graph-main-track,
.agent-graph-sub-track {
  stroke: var(--line);
  stroke-width: 2;
  stroke-linecap: round;
}
.agent-graph-sub-track {
  stroke-dasharray: 3 6;
}
.agent-graph-branch-edge path,
.agent-graph-branch-edge line {
  fill: none;
  stroke: var(--accent);
  stroke-width: 2;
  stroke-linecap: round;
}
.agent-graph-main-node,
.agent-graph-subagent-node,
.agent-graph-merge-node {
  fill: var(--panel);
  stroke: var(--accent);
  stroke-width: 2;
}
.agent-graph-subagent-node {
  fill: var(--accent-soft);
}
.agent-graph-merge-node {
  stroke: var(--muted);
}
.agent-graph-turn-link:hover .agent-graph-main-node,
.agent-graph-subagent-link:hover .agent-graph-subagent-node,
.agent-graph-subagent-link[aria-current="true"] .agent-graph-subagent-node {
  fill: var(--accent);
  stroke: var(--accent);
}
.turn {
  margin: 0 0 28px;
  border-top: 1px solid var(--line);
  padding-top: 20px;
  scroll-margin-top: 84px;
}
.turn[data-graph-selected="true"] {
  animation: cagelens-turn-highlight 1200ms ease-out;
}
@keyframes cagelens-turn-highlight {
  0% { background: var(--accent-soft); }
  100% { background: transparent; }
}
.turn-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}
.turn-heading {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.turn-header h2 { margin: 0; font-size: 20px; }
.turn-meta { color: var(--muted); font-size: 12px; text-align: right; }
.turn-summary { color: var(--muted); }
.turn-actions, .turn-trace, .full-io {
  margin-top: 10px;
}
.turn-actions > summary, .turn-trace > summary, .full-io > summary {
  cursor: pointer;
  color: var(--muted);
  font-weight: 700;
}
.turn-nav { display: inline-flex; gap: 4px; }
.turn-level-controls {
  display: inline-flex;
  align-items: center;
  gap: 0;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--panel);
  overflow: hidden;
}
.turn-level-button {
  border: 0;
  border-left: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 7px;
}
.turn-level-button:first-child { border-left: 0; }
.turn-level-button[aria-pressed="true"] {
  background: var(--accent-soft);
  color: var(--accent);
}
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
.message-human { background: var(--user-bg); border-color: var(--user-border); }
.message-assistant { background: var(--assistant-bg); border-color: var(--assistant-border); }
.message-parent-agent { background: var(--parent-agent-bg); border-color: var(--parent-agent-border); }
.message-subagent-event { background: var(--subagent-event-bg); border-color: var(--subagent-event-border); }
.message-human .message-header h3 { color: var(--user-title); }
.message-assistant .message-header h3 { color: var(--assistant-title); }
.message-parent-agent .message-header h3 { color: var(--parent-agent-title); }
.message-subagent-event .message-header h3 { color: var(--subagent-event-title); }
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
  align-items: center;
  gap: 8px;
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
.code-title-controls {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
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
.copy-button {
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel);
  color: var(--accent);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
}
.copy-button:hover {
  background: var(--accent-soft);
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
.raw-payload-controls {
  display: flex;
  justify-content: flex-end;
  margin: 8px 0;
}
[hidden] { display: none !important; }
@media (max-width: 640px) {
  .page { padding: 20px 12px 40px; }
  .export-layout { display: block; }
  .agent-graph {
    position: static;
    max-height: 220px;
    margin-bottom: 18px;
  }
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

  function readAgentGraphState() {
    var stored = "";
    try {
      stored = window.localStorage ? window.localStorage.getItem("cagelensAgentGraph") : "";
    } catch (error) {
      stored = "";
    }
    return stored === "hidden" ? "hidden" : "visible";
  }

  function applyAgentGraphState(state) {
    if (!document.querySelector(".agent-graph") && !document.querySelector("[data-agent-graph-toggle]")) {
      return;
    }
    var safeState = state === "hidden" ? "hidden" : "visible";
    if (document.body) {
      document.body.setAttribute("data-agent-graph", safeState);
    }
    document.querySelectorAll("[data-agent-graph-toggle]").forEach(function (button) {
      var hidden = safeState === "hidden";
      button.textContent = hidden ? "Show graph" : "Hide graph";
      button.setAttribute("aria-pressed", hidden ? "true" : "false");
    });
  }

  document.querySelectorAll("[data-agent-graph-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      var current = document.body
        ? document.body.getAttribute("data-agent-graph")
        : "visible";
      var nextState = current === "hidden" ? "visible" : "hidden";
      try {
        if (window.localStorage) {
          window.localStorage.setItem("cagelensAgentGraph", nextState);
        }
      } catch (error) {
        // Ignore storage failures; graph visibility still applies for this page view.
      }
      applyAgentGraphState(nextState);
    });
  });

  function applyLevel(level) {
    var safeLevel = Math.max(1, Math.min(4, parseInt(level, 10) || 1));
    document.documentElement.dataset.level = String(safeLevel);
    document.querySelectorAll("[data-level]").forEach(function (el) {
      applyElementLevel(el, safeLevel);
    });
    document.querySelectorAll("[data-level-button]").forEach(function (button) {
      button.setAttribute(
        "aria-pressed",
        button.getAttribute("data-level-button") === String(safeLevel) ? "true" : "false"
      );
    });
    document.querySelectorAll(".turn[data-turn-local-level]").forEach(function (turn) {
      applyTurnLevel(turn, parseInt(turn.getAttribute("data-turn-local-level"), 10) || safeLevel);
    });
  }

  function applyElementLevel(el, level) {
    var minLevel = parseInt(el.getAttribute("data-level"), 10) || 1;
    el.hidden = level < minLevel;
    if (el.tagName === "DETAILS" && el.hasAttribute("data-open-level")) {
      var openLevel = parseInt(el.getAttribute("data-open-level"), 10) || minLevel;
      el.open = level >= openLevel;
    }
  }

  function applyTurnLevel(turn, level) {
    if (!turn) {
      return;
    }
    applyTurnContentLevel(turn, level);
    turn.querySelectorAll("[data-turn-level-button]").forEach(function (button) {
      button.setAttribute(
        "aria-pressed",
        button.getAttribute("data-turn-level-button") === String(level) ? "true" : "false"
      );
    });
  }

  function applyTurnContentLevel(turn, level) {
    turn.querySelectorAll("[data-level]").forEach(function (el) {
      applyElementLevel(el, level);
    });
  }

  function clearTurnLevel(turn) {
    if (!turn) {
      return;
    }
    turn.removeAttribute("data-turn-local-level");
    turn.querySelectorAll("[data-turn-level-button]").forEach(function (button) {
      button.setAttribute("aria-pressed", "false");
    });
    applyTurnContentLevel(turn, parseInt(document.documentElement.dataset.level, 10) || 1);
  }

  document.querySelectorAll("[data-level-button]").forEach(function (button) {
    button.addEventListener("click", function () {
      applyLevel(button.getAttribute("data-level-button"));
    });
  });

  document.querySelectorAll("[data-turn-level-button]").forEach(function (button) {
    button.addEventListener("click", function () {
      var turn = button.closest(".turn");
      if (!turn) {
        return;
      }
      var level = parseInt(button.getAttribute("data-turn-level-button"), 10) || 1;
      var current = parseInt(turn.getAttribute("data-turn-local-level"), 10) || 0;
      if (current === level) {
        clearTurnLevel(turn);
        return;
      }
      turn.setAttribute("data-turn-local-level", String(level));
      applyTurnLevel(turn, level);
    });
  });

  document.querySelectorAll("[data-scroll-turn]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      var target = document.getElementById("turn-" + button.getAttribute("data-scroll-turn"));
      if (target) {
        var isAnchor = button.tagName && button.tagName.toUpperCase() === "A";
        if (button.hasAttribute("data-open-turn-actions")) {
          document.querySelectorAll(".agent-graph-subagent-link[aria-current]").forEach(function (branch) {
            branch.removeAttribute("aria-current");
          });
          button.setAttribute("aria-current", "true");
          document.querySelectorAll(".turn[data-graph-selected]").forEach(function (turn) {
            turn.removeAttribute("data-graph-selected");
          });
          target.setAttribute("data-graph-selected", "true");
          setTimeout(function () {
            target.removeAttribute("data-graph-selected");
          }, 1400);
          target.setAttribute("data-turn-local-level", "2");
          applyTurnLevel(target, 2);
          var actions = target.querySelector(".turn-actions");
          if (actions) {
            actions.open = true;
          }
        }
        if (isAnchor) {
          event.preventDefault();
        }
        target.scrollIntoView({ behavior: "auto", block: "start" });
        if (window.history && isAnchor) {
          window.history.replaceState(null, "", button.getAttribute("href"));
        }
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

  function activeCopyMode(scope) {
    if (!scope) {
      return "rendered";
    }
    var active = scope.querySelector("[data-view-toggle][aria-pressed='true']");
    return active ? active.getAttribute("data-view-toggle") : "rendered";
  }

  function fallbackCopy(text) {
    var textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand("copy");
    } finally {
      document.body.removeChild(textarea);
    }
  }

  function setCopied(button) {
    var original = button.textContent;
    button.textContent = "Copied";
    window.setTimeout(function () {
      button.textContent = original || "Copy";
    }, 1200);
  }

  document.querySelectorAll("[data-copy-button]").forEach(function (button) {
    button.addEventListener("click", function () {
      var scope = button.closest("[data-copy-scope]");
      var mode = activeCopyMode(scope);
      var source = scope
        ? scope.querySelector("[data-copy-content='" + mode + "']")
          || scope.querySelector("[data-copy-content]")
        : null;
      var text = source ? source.textContent : "";
      if (!text) {
        return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          setCopied(button);
        }, function () {
          fallbackCopy(text);
          setCopied(button);
        });
      } else {
        fallbackCopy(text);
        setCopied(button);
      }
    });
  });

  applyTheme(readTheme());
  applyAgentGraphState(readAgentGraphState());
  applyLevel(document.documentElement.dataset.level || "1");
})();
"""
