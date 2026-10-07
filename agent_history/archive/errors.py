"""Exceptions raised by the session archive."""

from __future__ import annotations


class ArchiveError(Exception):
    """Base class for archive errors."""


class ArchiveConfigError(ArchiveError):
    """The archive configuration is missing or invalid."""
