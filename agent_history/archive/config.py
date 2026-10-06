"""Loading and validating the archive configuration file.

The configuration names the archive destination and the sources to collect. Entries in
``sources`` that share a name merge into one source; each entry becomes one *part*. Two
parts of one source may not cover the same agent, because its files would map to the
same archive paths. Include patterns may not reach inside an agent's folder, which only
its layout reads.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from agent_history.archive.errors import ArchiveConfigError
from agent_history.archive.layouts import AGENT_NAMES, agent_folder_of, agent_folders

DEFAULT_COMPRESSION_LEVEL = 19
SOURCE_KINDS = ("live", "imported", "restored")
PLATFORMS = ("linux", "darwin", "windows")
_SOURCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TOP_KEYS = {"archive", "sources"}
_ARCHIVE_KEYS = {"destination", "compression_level", "min_interval_hours", "health_url", "workers"}
_SOURCE_KEYS = {"name", "kind", "platform", "note", "home", "roots", "agents", "include", "exclude"}


@dataclass(frozen=True)
class SourcePart:
    """One configuration entry of a source: a home and/or per-agent root overrides."""

    home: Path | None
    roots: dict[str, Path] = field(default_factory=dict)
    agents: tuple[str, ...] | None = None  # None: every agent; (): none, only includes
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
    _reject_unknown(data, _TOP_KEYS, "the configuration")
    archive = data.get("archive") or {}
    _reject_unknown(archive, _ARCHIVE_KEYS, "archive")
    destination = archive.get("destination")
    if not isinstance(destination, str) or not destination.strip():
        raise ArchiveConfigError("archive.destination is required")
    return ArchiveConfig(
        destination=destination,
        compression_level=_compression_level(archive),
        min_interval_hours=_min_interval(archive),
        health_url=_health_url(archive),
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


def _health_url(archive: dict[str, Any]) -> str | None:
    url = archive.get("health_url") or None
    if url is None:
        return None
    message = f"archive.health_url must be an http:// or https:// URL: {url!r}"
    if not isinstance(url, str):
        raise ArchiveConfigError(message)
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises ValueError for a port that is not a number
    except ValueError as exc:
        raise ArchiveConfigError(message) from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ArchiveConfigError(message)
    return url


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
    for source in merged.values():
        _reject_overlapping_parts(source)
        _reject_includes_in_agent_folders(source)
    return tuple(merged.values())


def _reject_overlapping_parts(source: SourceConfig) -> None:
    """Refuse two parts that cover one agent: their files would share archive paths.

    Include patterns can still overlap; the collector reports such files at run time.
    """
    first_part: dict[str, int] = {}
    for number, part in enumerate(source.parts, start=1):
        for agent in _covered_agents(part):
            if agent in first_part:
                raise ArchiveConfigError(
                    f"Source {source.name}: entries {first_part[agent]} and {number} both "
                    f"cover agent {agent}, so their files would share archive paths. Give the "
                    'other copy its own source name, for example with kind "imported".'
                )
            first_part[agent] = number


def _reject_includes_in_agent_folders(source: SourceConfig) -> None:
    """Refuse an include whose fixed leading part lies inside an agent folder.

    Agent folders are read only through their layouts. An include that starts with a
    wildcard can still match inside one; the walk skips those files.
    """
    overrides = [root for part in source.parts for root in part.roots.values()]
    for part in source.parts:
        if not part.include:
            continue
        folders = agent_folders(source.platform, part.home, overrides)
        for pattern in part.include:
            folder = agent_folder_of(_fixed_part(pattern), folders, source.platform)
            if folder is not None:
                raise ArchiveConfigError(
                    f"Source {source.name}: include pattern {pattern!r} reaches inside the "
                    f"agent folder {folder or part.home}. Agent folders are archived through "
                    "their layouts only; include patterns are for files elsewhere in the home."
                )


def _fixed_part(pattern: str) -> str:
    """The folders and name at the start of a pattern, up to its first wildcard."""
    fixed = []
    for segment in pattern.replace("\\", "/").split("/"):
        if "*" in segment or "?" in segment:
            break
        if segment not in ("", "."):
            fixed.append(segment)
    return "/".join(fixed)


def _covered_agents(part: SourcePart) -> tuple[str, ...]:
    """The agents whose folders a part reads, from its home or its root overrides."""
    agents = AGENT_NAMES if part.agents is None else part.agents
    return tuple(agent for agent in agents if part.home is not None or agent in part.roots)


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
    include = _patterns(entry, "include", name)
    exclude = _patterns(entry, "exclude", name)
    for pattern in include + exclude:
        parts = pattern.replace("\\", "/").split("/")
        if pattern.startswith(("/", "\\")) or ".." in parts or ":" in parts[0]:
            raise ArchiveConfigError(
                f"Source {name}: patterns must stay inside the home: {pattern}"
            )
    agents = entry.get("agents")
    return SourcePart(
        home=Path(home).expanduser() if home else None,
        roots={agent: Path(root).expanduser() for agent, root in roots.items()},
        agents=None if agents is None else tuple(agents),
        include=include,
        exclude=exclude,
    )


def _patterns(entry: dict[str, Any], key: str, name: str) -> tuple[str, ...]:
    """The ``include`` or ``exclude`` patterns of an entry: a list of strings, or absent.

    A single string is refused rather than read as a list of its characters.
    """
    value = entry.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ArchiveConfigError(
            f'Source {name}: {key} must be a list of glob patterns, such as ["notes/**"]; '
            f"got {json.dumps(value)}"
        )
    return tuple(value)
