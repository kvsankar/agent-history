"""Read agent transcripts without stopping at a line that cannot be used.

Transcripts are written by other programs and can hold a byte that is not
UTF-8, a byte order mark, a line that is not JSON, JSON nested too deeply to
parse, or JSON that is not an object. The readers decode bad bytes as U+FFFD
and skip lines that are not JSON objects, so one such line costs that line,
not the file. A value of the wrong type inside a line is coerced with the
``as_*`` helpers, or ignored when it cannot be.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO

TRANSCRIPT_ENCODING = "utf-8-sig"
TRANSCRIPT_ERRORS = "replace"


def open_transcript(path: Path) -> TextIO:
    """Open a plain transcript file as text, decoding bad bytes as U+FFFD."""
    return open(path, encoding=TRANSCRIPT_ENCODING, errors=TRANSCRIPT_ERRORS)


def json_objects(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """The lines that parse as JSON objects; the others are skipped.

    A line nested more deeply than the decoder's recursion limit is skipped
    like a line that is not JSON.
    """
    for line in lines:
        try:
            entry = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(entry, dict):
            yield entry


def dict_field(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    """``mapping[key]`` when it is an object, else an empty dict."""
    value = mapping.get(key)
    return value if isinstance(value, dict) else {}


def as_count(value: Any) -> int:
    """A token count: a number, or text holding one, as an int; anything else is 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return 0
    if isinstance(value, float):
        return int(value) if math.isfinite(value) else 0
    return 0


def as_timestamp(value: Any) -> str | None:
    """A timestamp as the transcripts write it (text), or None for any other value.

    Values of other types are ignored rather than guessed at, so they are
    never compared with text timestamps.
    """
    return value if isinstance(value, str) and value else None


def as_text(value: Any) -> str | None:
    """A value as SQLite text: None stays None, text is kept, others become JSON.

    IDs, model names and tool names are text in the transcripts; a list or
    object found in their place is stored in its JSON form.
    """
    if value is None or isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError, RecursionError):
        return str(value)


def id_key(value: Any) -> str | None:
    """The text form of an ID for use as a dict key, or None when it is empty."""
    if value is None or value == "":
        return None
    return as_text(value)
