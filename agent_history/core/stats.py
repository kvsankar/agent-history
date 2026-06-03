"""Pure statistics computation helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from agent_history.scope.types import ConcreteRecord, ConcreteScope


def compute_stats(scope: ConcreteScope, group_by: str | None, include_time: bool) -> dict[str, Any]:
    """Compute aggregate statistics from a resolved scope."""
    stats: dict[str, Any] = {
        "sessions": 0,
        "main_sessions": 0,
        "agent_sessions": 0,
        "messages": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "tokens": {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_creation": 0,
        },
        "by_agent": defaultdict(lambda: {"sessions": 0, "messages": 0}),
        "by_model": defaultdict(lambda: {"messages": 0, "tokens": 0}),
        "by_tool": defaultdict(lambda: {"uses": 0, "errors": 0}),
        "by_home": defaultdict(lambda: {"sessions": 0, "messages": 0}),
        "by_workspace": defaultdict(lambda: {"sessions": 0, "messages": 0}),
    }

    if group_by == "day":
        stats["by_day"] = defaultdict(lambda: {"sessions": 0, "messages": 0})

    for record in scope:
        for session in record.sessions:
            _add_session_stats(stats, session, record)

    stats["by_agent"] = _sort_by_count(dict(stats["by_agent"]), "sessions")
    stats["by_model"] = _sort_by_count(dict(stats["by_model"]), "messages")
    stats["by_tool"] = _sort_by_count(dict(stats["by_tool"]), "uses")
    stats["by_home"] = _sort_by_count(dict(stats["by_home"]), "sessions")
    stats["by_workspace"] = _sort_by_count(dict(stats["by_workspace"]), "sessions")

    if "by_day" in stats:
        stats["by_day"] = _sort_by_date(dict(stats["by_day"]))

    if include_time:
        stats["time_stats"] = _compute_time_stats(scope)

    return stats


def overlay_metrics(stats: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    """Overlay metrics database values onto computed stats."""
    for key in ("messages", "user_messages", "assistant_messages"):
        if key in metrics:
            stats[key] = metrics[key]

    tokens = stats.get("tokens", {})
    tokens["input"] = metrics.get("input_tokens", tokens.get("input", 0))
    tokens["output"] = metrics.get("output_tokens", tokens.get("output", 0))
    tokens["cache_creation"] = metrics.get("cache_creation_tokens", tokens.get("cache_creation", 0))
    tokens["cache_read"] = metrics.get("cache_read_tokens", tokens.get("cache_read", 0))
    stats["tokens"] = tokens

    if "by_tool" in metrics:
        stats["by_tool"] = metrics["by_tool"]

    if "by_model" in metrics:
        stats["by_model"] = metrics["by_model"]

    for breakdown_key in ("by_agent", "by_home", "by_workspace"):
        if breakdown_key not in metrics:
            continue
        current = stats.get(breakdown_key, {})
        scoped = metrics[breakdown_key]
        merged: dict[str, Any] = {}
        for name, values in current.items():
            merged[name] = dict(values)
            if name in scoped:
                merged[name]["messages"] = scoped[name].get(
                    "messages", merged[name].get("messages", 0)
                )
        for name, values in scoped.items():
            if name not in merged:
                merged[name] = dict(values)
        stats[breakdown_key] = merged

    if "time_stats" in metrics:
        stats["time_stats"] = metrics["time_stats"]

    return stats


def apply_top_limit(stats: dict[str, Any], top_limit: int) -> dict[str, Any]:
    """Apply top limit to breakdown dictionaries."""
    breakdown_keys = ["by_agent", "by_model", "by_tool", "by_home", "by_workspace", "by_day"]

    for key in breakdown_keys:
        if key in stats and isinstance(stats[key], dict):
            items = list(stats[key].items())[:top_limit]
            stats[key] = dict(items)

    return stats


def _add_session_stats(
    stats: dict[str, Any], session: dict[str, Any], record: ConcreteRecord
) -> None:
    stats["sessions"] += 1
    is_agent_session = session.get("is_agent", False)
    if is_agent_session:
        stats["agent_sessions"] += 1
    else:
        stats["main_sessions"] += 1

    message_count = session.get("message_count", 0)
    user_messages = session.get("user_messages", 0)
    assistant_messages = session.get("assistant_messages", 0)

    stats["messages"] += message_count
    stats["user_messages"] += user_messages
    stats["assistant_messages"] += assistant_messages

    tokens = _session_tokens(session)
    _add_token_stats(stats, tokens)

    agent = session.get("agent", "unknown")
    stats["by_agent"][agent]["sessions"] += 1
    stats["by_agent"][agent]["messages"] += message_count

    model = session.get("model") or session.get("primary_model")
    if model:
        stats["by_model"][model]["messages"] += message_count
        stats["by_model"][model]["tokens"] += tokens["output"]

    _add_tool_stats(stats, session.get("tool_uses", []))

    stats["by_home"][record.home]["sessions"] += 1
    stats["by_home"][record.home]["messages"] += message_count

    workspace_key = record.workspace_key or record.workspace
    stats["by_workspace"][workspace_key]["sessions"] += 1
    stats["by_workspace"][workspace_key]["messages"] += message_count

    if "by_day" in stats:
        _add_day_stats(stats, session, message_count)


def _session_tokens(session: dict[str, Any]) -> dict[str, int]:
    tokens = session.get("tokens", {})
    if isinstance(tokens, dict) and tokens:
        return {
            "input": tokens.get("input", 0),
            "output": tokens.get("output", 0),
            "cache_read": tokens.get("cache_read", 0),
            "cache_creation": tokens.get("cache_creation", 0),
        }
    return {
        "input": session.get("input_tokens", 0) or 0,
        "output": session.get("output_tokens", 0) or 0,
        "cache_read": session.get("cache_read_tokens", 0) or 0,
        "cache_creation": session.get("cache_creation_tokens", 0) or 0,
    }


def _add_token_stats(stats: dict[str, Any], tokens: dict[str, int]) -> None:
    stats["tokens"]["input"] += tokens["input"]
    stats["tokens"]["output"] += tokens["output"]
    stats["tokens"]["cache_read"] += tokens["cache_read"]
    stats["tokens"]["cache_creation"] += tokens["cache_creation"]


def _add_tool_stats(stats: dict[str, Any], tool_uses: Any) -> None:
    if isinstance(tool_uses, list):
        for tool_use in tool_uses:
            tool_name = tool_use.get("name") or tool_use.get("tool_name", "unknown")
            stats["by_tool"][tool_name]["uses"] += 1
            if tool_use.get("is_error") or tool_use.get("error"):
                stats["by_tool"][tool_name]["errors"] += 1
    elif isinstance(tool_uses, dict):
        for tool_name, count in tool_uses.items():
            stats["by_tool"][tool_name]["uses"] += count


def _add_day_stats(stats: dict[str, Any], session: dict[str, Any], message_count: int) -> None:
    day_key = _extract_day_key(session)
    if day_key:
        stats["by_day"][day_key]["sessions"] += 1
        stats["by_day"][day_key]["messages"] += message_count


def _extract_day_key(session: dict[str, Any]) -> str | None:
    for field in ["modified", "created", "start_time", "timestamp"]:
        value = session.get(field)
        if value:
            if isinstance(value, datetime):
                return value.strftime("%Y-%m-%d")
            if isinstance(value, str):
                if "T" in value:
                    return value.split("T")[0]
                if len(value) >= 10 and value[4] == "-" and value[7] == "-":
                    return value[:10]
    return None


def _compute_time_stats(scope: ConcreteScope) -> dict[str, Any]:
    time_stats: dict[str, Any] = {
        "total_duration_seconds": 0,
        "sessions_with_time": 0,
        "by_day": defaultdict(float),
    }

    for record in scope:
        for session in record.sessions:
            duration = session.get("duration_seconds") or session.get("duration")
            if duration:
                try:
                    duration_float = float(duration)
                    time_stats["total_duration_seconds"] += duration_float
                    time_stats["sessions_with_time"] += 1

                    day_key = _extract_day_key(session)
                    if day_key:
                        time_stats["by_day"][day_key] += duration_float
                except (ValueError, TypeError):
                    pass

    if time_stats["sessions_with_time"] > 0:
        time_stats["average_duration_seconds"] = (
            time_stats["total_duration_seconds"] / time_stats["sessions_with_time"]
        )
    else:
        time_stats["average_duration_seconds"] = 0

    time_stats["by_day"] = dict(time_stats["by_day"])

    return time_stats


def _sort_by_count(
    breakdown: dict[str, dict[str, Any]], count_key: str
) -> dict[str, dict[str, Any]]:
    sorted_items = sorted(breakdown.items(), key=lambda x: x[1].get(count_key, 0), reverse=True)
    return dict(sorted_items)


def _sort_by_date(breakdown: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    sorted_items = sorted(breakdown.items(), key=lambda x: x[0])
    return dict(sorted_items)
