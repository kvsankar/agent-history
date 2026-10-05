"""Read agent transcripts without stopping at a line that cannot be used.

Transcripts are written by other programs and can hold a byte that is not
UTF-8, a byte order mark, a line that is not JSON, or JSON that is not an
object. The readers decode bad bytes as U+FFFD and skip lines that are not
JSON objects, so one such line costs that line, not the file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO

TRANSCRIPT_ENCODING = "utf-8-sig"
TRANSCRIPT_ERRORS = "replace"


def open_transcript(path: Path) -> TextIO:
    """Open a plain transcript file as text, decoding bad bytes as U+FFFD."""
    return open(path, encoding=TRANSCRIPT_ENCODING, errors=TRANSCRIPT_ERRORS)


def json_objects(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """The lines that parse as JSON objects; the others are skipped."""
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            yield entry


def dict_field(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    """``mapping[key]`` when it is an object, else an empty dict."""
    value = mapping.get(key)
    return value if isinstance(value, dict) else {}
