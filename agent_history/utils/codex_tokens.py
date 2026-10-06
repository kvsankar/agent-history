"""Per-response token usage from Codex token_count events.

Codex writes a token_count event after each model response. Its
``total_token_usage`` is a running total for the thread, and
``last_token_usage`` is the usage of the latest response. Summing running
totals overcounts, and so does taking the last running total of a spawned
sub-agent, whose totals start from its parent's. Codex also repeats an event
unchanged when only rate limits change. Its output count already includes
the reasoning tokens, and its input count includes the cached tokens.

A forked sub-agent's file starts with a replay of its parent's history,
token_count events included. Entries numbered below the session's
``subagent_history_start_ordinal`` are that replay; their usage belongs to
the parent and is not counted again.
"""

from typing import Any, Dict, Optional

_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")


def is_replayed(entry: Dict[str, Any], history_start: Optional[int]) -> bool:
    """Return True if an entry is part of a forked sub-agent's replayed history."""
    ordinal = entry.get("ordinal")
    return isinstance(history_start, int) and isinstance(ordinal, int) and ordinal < history_start


class CodexTokenCounter:
    """Turn a stream of token_count events into per-response usage."""

    def __init__(self) -> None:
        self._previous_total: Optional[Dict[str, Any]] = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0

    def add(self, info: Dict[str, Any], replayed: bool = False) -> Optional[Dict[str, int]]:
        """Record one event's ``info``; return that response's usage, or None.

        None means the event adds nothing: it has no running total, it
        repeats the previous one, or it is replayed parent history, whose
        running total only becomes the baseline for the next event.
        """
        total = info.get("total_token_usage")
        if not total:
            return None
        if replayed:
            self._previous_total = total
            return None
        if total == self._previous_total:
            return None

        last = info.get("last_token_usage")
        if last:
            usage = {field: last.get(field, 0) or 0 for field in _FIELDS}
        else:
            previous = self._previous_total or {}
            usage = {
                field: max((total.get(field, 0) or 0) - (previous.get(field, 0) or 0), 0)
                for field in _FIELDS
            }
        self._previous_total = total

        delta = {
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "cache_read_tokens": usage["cached_input_tokens"],
        }
        self.input_tokens += delta["input_tokens"]
        self.output_tokens += delta["output_tokens"]
        self.cache_read_tokens += delta["cache_read_tokens"]
        return delta
