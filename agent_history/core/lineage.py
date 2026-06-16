"""Normalize parent/child session lineage across agent backends."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_history.types import SessionDict
from agent_history.utils.platform import AGENT_CLAUDE, AGENT_CODEX, AGENT_GEMINI, AGENT_PI

LineageRecord = dict[str, Any]

_CLAUDE_NOTIFICATION_TAGS = (
    "task-id",
    "tool-use-id",
    "status",
    "summary",
    "result",
    "output-file",
    "usage",
)


def build_timeline_lineage(
    sessions: list[SessionDict], *, include_related: bool = False
) -> list[LineageRecord]:
    """Build normalized lineage records for an export/session scope.

    The returned model is intentionally backend-neutral so the HTML timeline can
    consume it without parsing concrete JSONL details itself.
    """
    records: list[LineageRecord] = []
    codex_invocations: dict[str, dict[str, Any]] = {}
    claude_notifications: dict[tuple[str, str], dict[str, Any]] = {}
    seen_files: set[Path] = set()

    for session in sessions:
        session_file = Path(session["file"])
        if session_file in seen_files:
            continue
        seen_files.add(session_file)

        agent = str(session.get("agent", ""))
        if agent == AGENT_CODEX:
            record, invocations = extract_codex_lineage(session_file)
            if record:
                records.append(_with_session_context(record, session))
            codex_invocations.update(invocations)
        elif agent == AGENT_CLAUDE:
            claude_records, notifications = extract_claude_lineage(session_file)
            records.extend(_with_session_context(record, session) for record in claude_records)
            claude_notifications.update(notifications)
            if include_related:
                for child_file in _discover_claude_nested_subagents(session_file):
                    if child_file in seen_files:
                        continue
                    seen_files.add(child_file)
                    child_records, _ = extract_claude_lineage(child_file)
                    records.extend(
                        _with_session_context(
                            record,
                            {
                                **session,
                                "file": child_file,
                                "filename": child_file.name,
                                "modified": datetime.fromtimestamp(child_file.stat().st_mtime),
                            },
                        )
                        for record in child_records
                    )
        elif agent == AGENT_GEMINI:
            records.extend(
                _with_session_context(record, session)
                for record in extract_gemini_lineage(session_file)
            )
        elif agent == AGENT_PI:
            records.extend(
                _with_session_context(record, session)
                for record in extract_pi_lineage(session_file)
            )
        else:
            record = _main_record_for_session(session_file, agent)
            records.append(_with_session_context(record, session))

    _attach_codex_invocations(records, codex_invocations)
    _attach_claude_notifications(records, claude_notifications)
    _mark_unjoined_subagents(records)
    _append_subagent_completion_events(records)
    return sorted(records, key=_lineage_sort_key)


def extract_codex_lineage(
    jsonl_file: Path,
) -> tuple[LineageRecord | None, dict[str, dict[str, Any]]]:
    """Extract one Codex session lineage record plus parent spawn invocations."""
    parts, invocations = _collect_codex_lineage_parts(jsonl_file)
    session_meta = parts.get("session_meta") or {}
    session_id = session_meta.get("id")
    if not session_id:
        return None, invocations
    return _codex_lineage_record(jsonl_file, parts), invocations


def _collect_codex_lineage_parts(
    jsonl_file: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    from agent_history.backends.codex import _codex_open_text

    parts: dict[str, Any] = {
        "session_meta": {},
        "first_ts": None,
        "last_ts": None,
        "task_complete": None,
    }
    pending_spawn_calls: dict[str, dict[str, Any]] = {}
    invocations_by_agent_id: dict[str, dict[str, Any]] = {}

    try:
        with _codex_open_text(jsonl_file) as handle:
            for raw_line in handle:
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                timestamp = entry.get("timestamp")
                parts["first_ts"] = parts["first_ts"] or timestamp
                parts["last_ts"] = timestamp or parts["last_ts"]
                entry_type = entry.get("type")
                payload = entry.get("payload") or {}
                if entry_type == "session_meta":
                    parts["session_meta"] = payload
                elif entry_type == "response_item":
                    _collect_codex_invocation(
                        jsonl_file,
                        timestamp,
                        payload,
                        pending_spawn_calls,
                        invocations_by_agent_id,
                    )
                elif entry_type == "event_msg" and payload.get("type") == "task_complete":
                    parts["task_complete"] = {"timestamp": timestamp, **payload}
    except OSError:
        return parts, invocations_by_agent_id

    return parts, invocations_by_agent_id


def _collect_codex_invocation(
    jsonl_file: Path,
    timestamp: str | None,
    payload: dict[str, Any],
    pending_spawn_calls: dict[str, dict[str, Any]],
    invocations_by_agent_id: dict[str, dict[str, Any]],
) -> None:
    payload_type = payload.get("type")
    if payload_type == "function_call" and payload.get("name") == "spawn_agent":
        pending_spawn_calls[payload.get("call_id", "")] = _codex_spawn_invocation(
            jsonl_file, timestamp, payload
        )
    elif payload_type == "function_call_output":
        invocation = pending_spawn_calls.get(payload.get("call_id", ""))
        if completed := _codex_completed_spawn_invocation(jsonl_file, payload, invocation):
            invocations_by_agent_id[completed["agent_id"]] = completed


def _codex_spawn_invocation(
    jsonl_file: Path,
    timestamp: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "invocation_tool_call_id": payload.get("call_id"),
        "invocation_ts": timestamp,
        "invocation_name": "spawn_agent",
        "invocation_args": _loads_json_object(payload.get("arguments")),
        "evidence": [_evidence(jsonl_file, "response_item.function_call", "spawn_agent")],
    }


def _codex_completed_spawn_invocation(
    jsonl_file: Path,
    payload: dict[str, Any],
    invocation: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not invocation:
        return None
    output = _loads_json_object(payload.get("output"))
    agent_id = output.get("agent_id")
    if not agent_id:
        return None
    call_id = payload.get("call_id")
    return {
        **invocation,
        "agent_id": str(agent_id),
        "agent_name": output.get("nickname")
        or invocation.get("invocation_args", {}).get("agent_type"),
        "merge_message_id": payload.get("id") or call_id,
        "evidence": [
            *invocation["evidence"],
            _evidence(jsonl_file, "response_item.function_call_output", "agent_id"),
        ],
    }


def _codex_lineage_record(jsonl_file: Path, parts: dict[str, Any]) -> LineageRecord:
    session_meta = parts["session_meta"]
    session_id = session_meta.get("id")
    task_complete = parts.get("task_complete") or {}
    source = session_meta.get("source") if isinstance(session_meta.get("source"), dict) else {}
    subagent_source = source.get("subagent")
    if not isinstance(subagent_source, dict):
        subagent_source = {}
    spawn = subagent_source.get("thread_spawn")
    if not isinstance(spawn, dict):
        spawn = {}
    parent_session_id = (
        session_meta.get("parent_thread_id")
        or spawn.get("parent_thread_id")
        or session_meta.get("forked_from_id")
    )
    is_subagent = session_meta.get("thread_source") == "subagent" or bool(spawn)
    record: LineageRecord = {
        "agent": AGENT_CODEX,
        "kind": "subagent" if is_subagent else "main",
        "session_id": session_id,
        "parent_session_id": parent_session_id,
        "agent_id": session_id if is_subagent else None,
        "agent_name": session_meta.get("agent_nickname") or session_meta.get("agent_role"),
        "agent_role": session_meta.get("agent_role"),
        "start_ts": session_meta.get("timestamp") or parts.get("first_ts"),
        "end_ts": task_complete.get("timestamp") or parts.get("last_ts"),
        "status": "completed" if task_complete else None,
        "duration_ms": task_complete.get("duration_ms"),
        "last_agent_message": task_complete.get("last_agent_message"),
        "confidence": "confirmed",
        "evidence": [_evidence(jsonl_file, "session_meta", "payload")],
        "source_file": str(jsonl_file),
    }
    if task_complete:
        record["evidence"].append(_evidence(jsonl_file, "event_msg.task_complete", "payload"))
    return _drop_none(record)


def extract_claude_lineage(
    jsonl_file: Path,
) -> tuple[list[LineageRecord], dict[tuple[str, str], dict[str, Any]]]:
    """Extract Claude session/child lineage and parent task notifications."""
    state, notifications = _collect_claude_lineage_parts(jsonl_file)
    if not state:
        return [], notifications
    return [_claude_lineage_record(jsonl_file, state)], notifications


def _collect_claude_lineage_parts(
    jsonl_file: Path,
) -> tuple[dict[str, Any], dict[tuple[str, str], dict[str, Any]]]:
    state: dict[str, Any] = {
        "first_ts": None,
        "last_ts": None,
        "session_id": None,
        "agent_id": None,
        "is_sidechain": False,
    }
    notifications: dict[tuple[str, str], dict[str, Any]] = {}

    try:
        with open(jsonl_file, encoding="utf-8") as handle:
            for raw_line in handle:
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                _update_claude_lineage_state(state, entry)
                _collect_claude_notifications(state, entry, jsonl_file, notifications)
    except OSError:
        return {}, notifications

    return state, notifications


def _update_claude_lineage_state(state: dict[str, Any], entry: dict[str, Any]) -> None:
    timestamp = entry.get("timestamp")
    state["first_ts"] = state["first_ts"] or timestamp
    state["last_ts"] = timestamp or state["last_ts"]
    state["session_id"] = state["session_id"] or entry.get("sessionId")
    state["agent_id"] = state["agent_id"] or entry.get("agentId")
    state["is_sidechain"] = state["is_sidechain"] or bool(entry.get("isSidechain"))


def _collect_claude_notifications(
    state: dict[str, Any],
    entry: dict[str, Any],
    jsonl_file: Path,
    notifications: dict[tuple[str, str], dict[str, Any]],
) -> None:
    session_id = state.get("session_id")
    if not session_id:
        return
    for notification in _claude_notifications_from_entry(entry, jsonl_file):
        task_id = notification.get("task_id")
        if task_id:
            notifications[(str(session_id), str(task_id))] = notification


def _claude_lineage_record(jsonl_file: Path, state: dict[str, Any]) -> LineageRecord:
    session_id = state.get("session_id") or _session_id_from_claude_path(jsonl_file)
    task_id = _task_id_from_claude_path(jsonl_file)
    agent_id = state.get("agent_id")
    if not agent_id and task_id:
        agent_id = task_id
    is_subagent = (
        bool(state.get("is_sidechain")) or bool(task_id) or jsonl_file.name.startswith("agent-")
    )

    record: LineageRecord = {
        "agent": AGENT_CLAUDE,
        "kind": "subagent" if is_subagent else "main",
        "session_id": f"{session_id}:{agent_id}" if is_subagent and agent_id else session_id,
        "parent_session_id": session_id if is_subagent else None,
        "agent_id": agent_id,
        "agent_name": None,
        "start_ts": state.get("first_ts"),
        "end_ts": state.get("last_ts"),
        "status": None,
        "confidence": "confirmed",
        "evidence": [_evidence(jsonl_file, "jsonl", "sessionId/agentId/isSidechain")],
        "source_file": str(jsonl_file),
    }
    return _drop_none(record)


def extract_gemini_lineage(json_file: Path) -> list[LineageRecord]:
    """Extract Gemini main session and parent-side subagent tool spans."""
    if json_file.name.endswith(".jsonl"):
        return _extract_gemini_jsonl_lineage(json_file)
    try:
        with open(json_file, encoding="utf-8") as handle:
            data = json.load(handle) if json_file.suffix == ".json" else None
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, dict):
        return []

    session_id = data.get("sessionId") or data.get("id") or json_file.stem
    records: list[LineageRecord] = [
        _drop_none(
            {
                "agent": AGENT_GEMINI,
                "kind": "main",
                "session_id": session_id,
                "start_ts": data.get("startTime"),
                "end_ts": data.get("lastUpdated"),
                "confidence": "confirmed",
                "evidence": [_evidence(json_file, "session", "sessionId")],
                "source_file": str(json_file),
            }
        )
    ]
    records.extend(_gemini_subagent_records(json_file, session_id, data.get("messages", [])))
    return records


def _extract_gemini_jsonl_lineage(jsonl_file: Path) -> list[LineageRecord]:
    session_meta: dict[str, Any] = {}
    messages: list[dict[str, Any]] = []
    first_ts = None
    last_ts = None
    try:
        with open(jsonl_file, encoding="utf-8") as handle:
            for raw_line in handle:
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                timestamp = entry.get("timestamp")
                first_ts = first_ts or timestamp
                last_ts = timestamp or last_ts
                _collect_gemini_jsonl_record(entry, session_meta, messages)
    except OSError:
        return []

    session_id = session_meta.get("sessionId") or session_meta.get("id") or jsonl_file.stem
    nested_parent_id = _gemini_nested_jsonl_parent_session_id(jsonl_file)
    is_nested_child = nested_parent_id is not None
    records = [
        _drop_none(
            {
                "agent": AGENT_GEMINI,
                "kind": "subagent" if is_nested_child else "main",
                "session_id": session_id,
                "parent_session_id": nested_parent_id,
                "agent_id": (
                    session_meta.get("agentId") or session_meta.get("agent_id") or jsonl_file.stem
                    if is_nested_child
                    else None
                ),
                "agent_name": session_meta.get("agentName") or session_meta.get("agent_name"),
                "start_ts": session_meta.get("startTime") or first_ts,
                "end_ts": session_meta.get("lastUpdated") or last_ts,
                "confidence": "confirmed",
                "evidence": [_evidence(jsonl_file, "session", "sessionId")],
                "source_file": str(jsonl_file),
            }
        )
    ]
    records.extend(_gemini_subagent_records(jsonl_file, session_id, messages))
    return records


def _collect_gemini_jsonl_record(
    entry: dict[str, Any],
    session_meta: dict[str, Any],
    messages: list[dict[str, Any]],
) -> None:
    if "$rewindTo" in entry:
        _rewind_gemini_messages(messages, entry.get("$rewindTo"))
        return
    if "$set" in entry:
        _apply_gemini_set_record(session_meta, messages, entry.get("$set"))
        return

    record_type = entry.get("type") or entry.get("role")
    if record_type == "$set":
        _apply_gemini_set_record(session_meta, messages, entry.get("value") or entry.get("updates"))
    elif record_type in (
        "user",
        "gemini",
        "model",
        "assistant",
        "info",
        "error",
        "warning",
    ) or entry.get("toolCalls"):
        messages.append(entry)
    elif record_type in (None, "metadata", "session"):
        session_meta.update({key: value for key, value in entry.items() if key != "messages"})


def _rewind_gemini_messages(messages: list[dict[str, Any]], target_id: Any) -> None:
    for index, message in enumerate(messages):
        if message.get("id") == target_id:
            del messages[index + 1 :]
            return


def _apply_gemini_set_record(
    session_meta: dict[str, Any],
    messages: list[dict[str, Any]],
    updates: Any,
) -> None:
    if not isinstance(updates, dict):
        return
    if isinstance(updates.get("messages"), list):
        messages.clear()
        messages.extend(updates["messages"])
    session_meta.update({key: value for key, value in updates.items() if key != "messages"})


def _gemini_subagent_records(
    json_file: Path,
    session_id: str,
    messages: list[dict[str, Any]],
) -> list[LineageRecord]:
    records: list[LineageRecord] = []
    for message_index, message in enumerate(messages):
        for tool_call in message.get("toolCalls", []) or []:
            if _is_gemini_subagent_tool(tool_call):
                records.append(
                    _gemini_subagent_record(
                        json_file, session_id, message_index, message, tool_call
                    )
                )
    return records


def _gemini_subagent_record(
    json_file: Path,
    session_id: str,
    message_index: int,
    message: dict[str, Any],
    tool_call: dict[str, Any],
) -> LineageRecord:
    tool_id = str(tool_call.get("id") or "")
    return _drop_none(
        {
            "agent": AGENT_GEMINI,
            "kind": "subagent",
            "session_id": f"{session_id}:{tool_id}" if tool_id else None,
            "parent_session_id": session_id,
            "agent_id": tool_id,
            "agent_name": tool_call.get("displayName") or tool_call.get("name"),
            "invocation_tool_call_id": tool_id,
            "invocation_message_id": message.get("id") or str(message_index),
            "start_ts": tool_call.get("timestamp") or message.get("timestamp"),
            "end_ts": tool_call.get("timestamp") or message.get("timestamp"),
            "status": tool_call.get("status"),
            "last_agent_message": tool_call.get("resultDisplay"),
            "confidence": "confirmed",
            "evidence": [_evidence(json_file, "messages.toolCalls", tool_id)],
            "source_file": str(json_file),
        }
    )


def extract_pi_lineage(jsonl_file: Path) -> list[LineageRecord]:
    """Extract Pi main session plus branch-lineage marker when present."""
    first_ts = None
    last_ts = None
    session_id = None
    child_ids_by_parent: dict[str, set[str]] = {}
    has_explicit_branch = False
    subagent_records: list[LineageRecord] = []
    pending_subagent_calls: dict[str, dict[str, Any]] = {}

    try:
        with open(jsonl_file, encoding="utf-8") as handle:
            for raw_line in handle:
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                timestamp = entry.get("timestamp")
                first_ts = first_ts or timestamp
                last_ts = timestamp or last_ts
                if entry.get("type") in ("session", "tree"):
                    session_id = session_id or entry.get("id")
                parent_id = entry.get("parentId") or entry.get("parent_id")
                entry_id = entry.get("id")
                if parent_id and entry_id:
                    child_ids_by_parent.setdefault(str(parent_id), set()).add(str(entry_id))
                if entry.get("type") == "branch_summary":
                    has_explicit_branch = True
                children = entry.get("children")
                if isinstance(children, list) and len(children) > 1:
                    has_explicit_branch = True
                _collect_pi_subagent_lineage(
                    jsonl_file,
                    entry,
                    pending_subagent_calls,
                    subagent_records,
                    session_id,
                    timestamp,
                )
    except OSError:
        return []

    record = _drop_none(
        {
            "agent": AGENT_PI,
            "kind": "main",
            "session_id": session_id or jsonl_file.stem,
            "start_ts": first_ts,
            "end_ts": last_ts,
            "confidence": "confirmed",
            "evidence": [_evidence(jsonl_file, "session", "id")],
            "source_file": str(jsonl_file),
        }
    )
    records = [record, *subagent_records]
    has_branch_links = has_explicit_branch or any(
        len(children) > 1 for children in child_ids_by_parent.values()
    )
    if has_branch_links:
        records.append(
            _drop_none(
                {
                    "agent": AGENT_PI,
                    "kind": "branch",
                    "session_id": f"{record['session_id']}:branches",
                    "parent_session_id": record["session_id"],
                    "start_ts": first_ts,
                    "end_ts": last_ts,
                    "confidence": "confirmed",
                    "evidence": [_evidence(jsonl_file, "message", "id/parentId")],
                    "source_file": str(jsonl_file),
                }
            )
        )
    return records


def _attach_codex_invocations(
    records: list[LineageRecord], invocations_by_agent_id: dict[str, dict[str, Any]]
) -> None:
    for record in records:
        if record.get("agent") != AGENT_CODEX or record.get("kind") != "subagent":
            continue
        invocation = invocations_by_agent_id.get(str(record.get("agent_id")))
        if not invocation:
            continue
        record.setdefault("agent_name", invocation.get("agent_name"))
        for key in (
            "invocation_tool_call_id",
            "invocation_ts",
            "invocation_name",
            "merge_message_id",
        ):
            if invocation.get(key) is not None:
                record[key] = invocation[key]
        record["evidence"] = [*record.get("evidence", []), *invocation.get("evidence", [])]
        record["join_status"] = "joined"


def _attach_claude_notifications(
    records: list[LineageRecord],
    notifications: dict[tuple[str, str], dict[str, Any]],
) -> None:
    for record in records:
        if record.get("agent") != AGENT_CLAUDE or record.get("kind") != "subagent":
            continue
        parent_session_id = record.get("parent_session_id")
        agent_id = record.get("agent_id")
        if not parent_session_id or not agent_id:
            continue
        notification = notifications.get((str(parent_session_id), str(agent_id)))
        if not notification:
            continue
        record["invocation_tool_call_id"] = notification.get("tool_use_id")
        record["status"] = notification.get("status")
        record["last_agent_message"] = notification.get("result") or notification.get("summary")
        record["merge_message_id"] = notification.get("notification_uuid")
        if duration_ms := notification.get("duration_ms"):
            record["duration_ms"] = duration_ms
        record["evidence"] = [*record.get("evidence", []), *notification.get("evidence", [])]
        record["join_status"] = "joined"


def _mark_unjoined_subagents(records: list[LineageRecord]) -> None:
    for record in records:
        if (
            record.get("kind") == "subagent"
            and record.get("parent_session_id")
            and not record.get("join_status")
        ):
            record["join_status"] = "unjoined"


def _append_subagent_completion_events(records: list[LineageRecord]) -> None:
    events = [
        event for record in records if (event := _subagent_completion_event(record)) is not None
    ]
    records.extend(events)


def _subagent_completion_event(record: LineageRecord) -> LineageRecord | None:
    if record.get("kind") != "subagent":
        return None
    parent_session_id = record.get("parent_session_id")
    child_session_id = record.get("session_id")
    status = record.get("status")
    if not parent_session_id or not child_session_id or not status:
        return None

    timestamp = record.get("end_ts") or record.get("start_ts")
    event: LineageRecord = {
        "kind": "event",
        "event_type": "subagent.completed",
        "event_id": f"{parent_session_id}:subagent.completed:{child_session_id}",
        "synthetic": True,
        "parent_session_id": parent_session_id,
        "child_session_id": child_session_id,
        "child_agent_id": record.get("agent_id"),
        "agent": record.get("agent"),
        "agent_name": record.get("agent_name"),
        "invocation_message_id": record.get("invocation_message_id"),
        "invocation_tool_call_id": record.get("invocation_tool_call_id"),
        "merge_message_id": record.get("merge_message_id"),
        "timestamp": timestamp,
        "start_ts": timestamp,
        "status": status,
        "duration_ms": record.get("duration_ms"),
        "summary": record.get("last_agent_message"),
        "confidence": record.get("confidence", "confirmed"),
        "evidence": record.get("evidence", []),
    }
    return _drop_none(event)


def _claude_notifications_from_entry(
    entry: dict[str, Any], jsonl_file: Path
) -> list[dict[str, Any]]:
    texts: list[str] = []
    if entry.get("type") == "queue-operation" and isinstance(entry.get("content"), str):
        texts.append(entry["content"])
    if isinstance(entry.get("message"), dict):
        content = entry["message"].get("content")
        if isinstance(content, str):
            texts.append(content)
    if isinstance(entry.get("attachment"), dict):
        prompt = entry["attachment"].get("prompt")
        if isinstance(prompt, str):
            texts.append(prompt)

    notifications = []
    for text in texts:
        if "<task-notification>" not in text:
            continue
        parsed = {
            _tag_to_key(tag): _extract_xml_tag(text, tag) for tag in _CLAUDE_NOTIFICATION_TAGS
        }
        parsed = {key: value for key, value in parsed.items() if value is not None}
        usage = parsed.get("usage")
        if usage and (duration := _extract_xml_tag(usage, "duration_ms")):
            parsed["duration_ms"] = _coerce_int(duration)
        parsed["notification_uuid"] = entry.get("uuid")
        parsed["evidence"] = [_evidence(jsonl_file, "task-notification", "task-id")]
        notifications.append(parsed)
    return notifications


def _discover_claude_nested_subagents(session_file: Path) -> list[Path]:
    if session_file.name.startswith("agent-") or "subagents" in session_file.parts:
        return []
    nested_dir = session_file.with_suffix("") / "subagents"
    if not nested_dir.is_dir():
        return []
    return sorted(
        path for path in nested_dir.glob("agent-*.jsonl") if _is_claude_task_subagent_file(path)
    )


def _is_gemini_subagent_tool(tool_call: dict[str, Any]) -> bool:
    name = str(tool_call.get("name") or "").lower()
    display = str(tool_call.get("displayName") or "").lower()
    result_display = str(tool_call.get("resultDisplay") or "").lower()
    return (
        display.endswith(" agent") or "subagent" in result_display or name.endswith("_investigator")
    )


def _gemini_nested_jsonl_parent_session_id(jsonl_file: Path) -> str | None:
    parent = jsonl_file.parent
    if parent.parent.name != "chats":
        return None
    return parent.name


def _collect_pi_subagent_lineage(
    jsonl_file: Path,
    entry: dict[str, Any],
    pending_calls: dict[str, dict[str, Any]],
    records: list[LineageRecord],
    session_id: str | None,
    timestamp: Any,
) -> None:
    message = entry.get("message") if isinstance(entry.get("message"), dict) else entry
    raw_role = message.get("role")
    if raw_role == "assistant":
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "toolCall":
                    continue
                if invocation := _pi_subagent_invocation(jsonl_file, block, session_id, timestamp):
                    pending_calls[str(invocation["invocation_tool_call_id"])] = invocation
    elif raw_role == "toolResult":
        call_id = message.get("toolCallId")
        invocation = pending_calls.pop(str(call_id), None)
        if invocation:
            records.append(
                _pi_completed_subagent_record(jsonl_file, message, invocation, timestamp)
            )


def _pi_subagent_invocation(
    jsonl_file: Path,
    tool_call: dict[str, Any],
    session_id: str | None,
    timestamp: Any,
) -> dict[str, Any] | None:
    name = str(tool_call.get("name") or "")
    if name not in {"subagent", "sub_agent", "pi-subagent", "pi_subagent"}:
        return None
    args = tool_call.get("arguments") or tool_call.get("input") or {}
    if not isinstance(args, dict):
        return None
    child_id = _pi_child_identity(args)
    if not child_id:
        return None
    call_id = tool_call.get("id")
    if not call_id:
        return None
    return {
        "agent": AGENT_PI,
        "kind": "subagent",
        "session_id": child_id,
        "parent_session_id": session_id,
        "agent_id": child_id,
        "agent_name": args.get("agent_name") or args.get("agentName") or args.get("name") or name,
        "invocation_tool_call_id": call_id,
        "invocation_name": name,
        "invocation_args": args,
        "start_ts": timestamp,
        "confidence": "confirmed",
        "evidence": [_evidence(jsonl_file, "message.toolCall", name)],
        "source_file": str(jsonl_file),
        "join_status": "joined",
    }


def _pi_completed_subagent_record(
    jsonl_file: Path,
    message: dict[str, Any],
    invocation: dict[str, Any],
    timestamp: Any,
) -> LineageRecord:
    return _drop_none(
        {
            **invocation,
            "end_ts": timestamp or invocation.get("start_ts"),
            "status": "error" if message.get("isError") else "completed",
            "last_agent_message": _pi_result_content(message.get("content")),
            "merge_message_id": message.get("id") or message.get("toolCallId"),
            "evidence": [
                *invocation.get("evidence", []),
                _evidence(jsonl_file, "message.toolResult", "toolCallId"),
            ],
        }
    )


def _pi_child_identity(args: dict[str, Any]) -> str | None:
    for key in (
        "session_id",
        "sessionId",
        "child_session_id",
        "childSessionId",
        "thread_id",
        "threadId",
        "agent_id",
        "agentId",
    ):
        if args.get(key):
            return str(args[key])
    return None


def _pi_result_content(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _is_claude_task_subagent_file(path: Path) -> bool:
    return path.name.startswith("agent-") and not path.name.startswith("agent-acompact-")


def _main_record_for_session(jsonl_file: Path, agent: str) -> LineageRecord:
    return {
        "agent": agent,
        "kind": "main",
        "session_id": jsonl_file.stem,
        "confidence": "weak",
        "evidence": [_evidence(jsonl_file, "file", "stem")],
        "source_file": str(jsonl_file),
    }


def _with_session_context(record: LineageRecord, session: SessionDict) -> LineageRecord:
    enriched = {
        "workspace": session.get("workspace"),
        "workspace_readable": session.get("workspace_readable"),
        "home": session.get("home"),
        **record,
    }
    if not enriched.get("start_ts") and session.get("modified"):
        enriched["start_ts"] = _datetime_to_iso(session["modified"])
    return enriched


def _lineage_sort_key(record: LineageRecord) -> tuple[str, str, str]:
    return (
        str(record.get("start_ts") or ""),
        str(record.get("parent_session_id") or record.get("session_id") or ""),
        str(record.get("session_id") or ""),
    )


def _session_id_from_claude_path(jsonl_file: Path) -> str | None:
    parts = jsonl_file.parts
    if len(parts) >= 3 and parts[-2] == "subagents":
        return parts[-3]
    if not jsonl_file.name.startswith("agent-"):
        return jsonl_file.stem
    return None


def _task_id_from_claude_path(jsonl_file: Path) -> str | None:
    if not jsonl_file.name.startswith("agent-"):
        return None
    return jsonl_file.stem.removeprefix("agent-")


def _loads_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _extract_xml_tag(text: str, tag: str) -> str | None:
    match = re.search(rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", text, re.DOTALL)
    return match.group(1).strip() if match else None


def _tag_to_key(tag: str) -> str:
    return tag.replace("-", "_")


def _coerce_int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _datetime_to_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return value.isoformat()
    return None


def _evidence(jsonl_file: Path, record_type: str, field_path: str) -> dict[str, str]:
    return {
        "source_file": str(jsonl_file),
        "record_type": record_type,
        "field_path": field_path,
    }


def _drop_none(record: LineageRecord) -> LineageRecord:
    return {key: value for key, value in record.items() if value is not None}
