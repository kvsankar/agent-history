"""Loading and validating the archive configuration file.

The configuration names the archive destination and the sources to collect. Entries in
``sources`` that share a name merge into one source; each entry becomes one *part*.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_history.archive.errors import ArchiveConfigError
from agent_history.archive.layouts import AGENT_NAMES

DEFAULT_COMPRESSION_LEVEL = 19
SOURCE_KINDS = ("live", "imported", "restored")
PLATFORMS = ("linux", "darwin", "windows")
_SOURCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ARCHIVE_KEYS = {"destination", "compression_level", "min_interval_hours", "health_url", "workers"}
_SOURCE_KEYS = {"name", "kind", "platform", "note", "home", "roots", "agents", "include", "exclude"}


@dataclass(frozen=True)
class SourcePart:
    """One configuration entry of a source: a home and/or per-agent root overrides."""

    home: Path | None
    roots: dict[str, Path] = field(default_factory=dict)
    agents: tuple[str, ...] | None = None
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceConfig:
    """A named source, merged from every entry with that name."""

    name: str
    kind: str
    platform: str
    note: str
    parts: tuple[SourcePart, ...]


@dataclass(frozen=True)
class ArchiveConfig:
    """The whole archive configuration."""

    destination: str
    compression_level: int
    min_interval_hours: float
    health_url: str | None
    sources: tuple[SourceConfig, ...]
    workers: int = 1

    def source(self, name: str) -> SourceConfig:
        for source in self.sources:
            if source.name == name:
                return source
        raise ArchiveConfigError(f"Unknown source: {name}")


def load_config(path: Path) -> ArchiveConfig:
    """Read and validate a JSON configuration file."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ArchiveConfigError(f"Archive configuration not found: {path}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArchiveConfigError(f"Archive configuration is not valid JSON: {exc}") from exc
    return parse_config(data)


def parse_config(data: dict[str, Any]) -> ArchiveConfig:
    """Validate configuration data already loaded from JSON."""
    if not isinstance(data, dict):
        raise ArchiveConfigError("Archive configuration must be a JSON object")
    archive = data.get("archive") or {}
    _reject_unknown(archive, _ARCHIVE_KEYS, "archive")
    destination = archive.get("destination")
    if not isinstance(destination, str) or not destination.strip():
        raise ArchiveConfigError("archive.destination is required")
    return ArchiveConfig(
        destination=destination,
        compression_level=_compression_level(archive),
        min_interval_hours=_min_interval(archive),
        health_url=archive.get("health_url") or None,
        sources=_merge_sources(data.get("sources") or []),
        workers=_workers(archive),
    )


def _reject_unknown(section: dict[str, Any], allowed: set, where: str) -> None:
    unknown = sorted(set(section) - allowed)
    if unknown:
        raise ArchiveConfigError(f"Unknown setting in {where}: {', '.join(unknown)}")


def _workers(archive: dict[str, Any]) -> int:
    value = archive.get("workers", min(4, os.cpu_count() or 1))
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 64:
        raise ArchiveConfigError("archive.workers must be an integer from 1 to 64")
    return value


def _compression_level(archive: dict[str, Any]) -> int:
    level = archive.get("compression_level", DEFAULT_COMPRESSION_LEVEL)
    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 19:
        raise ArchiveConfigError("archive.compression_level must be an integer from 1 to 19")
    return level


def _min_interval(archive: dict[str, Any]) -> float:
    value = archive.get("min_interval_hours", 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ArchiveConfigError("archive.min_interval_hours must be a number >= 0")
    return float(value)


def _merge_sources(entries: list[dict[str, Any]]) -> tuple[SourceConfig, ...]:
    merged: dict[str, SourceConfig] = {}
    for entry in entries:
        _reject_unknown(entry, _SOURCE_KEYS, f"source {entry.get('name')!r}")
        name, kind, platform, note = _source_identity(entry)
        part = _source_part(entry, name)
        existing = merged.get(name)
        if existing is None:
            merged[name] = SourceConfig(name, kind, platform, note, (part,))
            continue
        if (existing.kind, existing.platform) != (kind, platform):
            raise ArchiveConfigError(f"Entries for source {name} disagree on kind or platform")
        merged[name] = SourceConfig(
            name, kind, platform, existing.note or note, (*existing.parts, part)
        )
    return tuple(merged.values())


def _source_identity(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    name = entry.get("name")
    if not isinstance(name, str) or not _SOURCE_NAME.match(name):
        raise ArchiveConfigError(f"Invalid source name: {name!r}")
    kind = entry.get("kind")
    if kind not in SOURCE_KINDS:
        raise ArchiveConfigError(f"Source {name}: kind must be one of {', '.join(SOURCE_KINDS)}")
    platform = entry.get("platform")
    if platform not in PLATFORMS:
        raise ArchiveConfigError(f"Source {name}: platform must be one of {', '.join(PLATFORMS)}")
    return name, kind, platform, str(entry.get("note") or "")


def _source_part(entry: dict[str, Any], name: str) -> SourcePart:
    home = entry.get("home")
    roots = entry.get("roots") or {}
    if not home and not roots:
        raise ArchiveConfigError(f"Source {name}: give a home or roots")
    for agent in list(roots) + list(entry.get("agents") or []):
        if agent not in AGENT_NAMES:
            raise ArchiveConfigError(f"Source {name}: unknown agent {agent}")
    for pattern in list(entry.get("include") or ()) + list(entry.get("exclude") or ()):
        parts = pattern.replace("\\", "/").split("/")
        if pattern.startswith(("/", "\\")) or ".." in parts or ":" in parts[0]:
            raise ArchiveConfigError(
                f"Source {name}: patterns must stay inside the home: {pattern}"
            )
    agents = entry.get("agents")
    return SourcePart(
        home=Path(home).expanduser() if home else None,
        roots={agent: Path(root).expanduser() for agent, root in roots.items()},
        agents=tuple(agents) if agents else None,
        include=tuple(entry.get("include") or ()),
        exclude=tuple(entry.get("exclude") or ()),
    )
