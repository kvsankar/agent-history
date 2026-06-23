"""Environment variable helpers for cagelens compatibility aliases."""

from __future__ import annotations

import os


def get_env(primary: str, legacy: str | None = None, default: str | None = None) -> str | None:
    """Return a primary env var value, falling back to one legacy name."""
    value = os.environ.get(primary)
    if value is not None:
        return value
    if legacy is not None:
        value = os.environ.get(legacy)
        if value is not None:
            return value
    return default


def has_env(primary: str, legacy: str | None = None) -> bool:
    """Return True when a primary or legacy env var is set to a non-empty value."""
    return bool(get_env(primary, legacy))


def get_bool_env(primary: str, legacy: str | None = None) -> bool:
    """Return True for common truthy env var values."""
    value = get_env(primary, legacy, "")
    return str(value).lower() in {"1", "true", "yes", "on"}
