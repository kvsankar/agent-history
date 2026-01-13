"""Datetime comparison helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def modified_key(value: Any) -> float:
    """Return a comparable key for datetime sorting/comparisons."""
    if isinstance(value, datetime):
        try:
            return value.timestamp()
        except (OSError, ValueError, OverflowError):
            return 0.0
    return 0.0
