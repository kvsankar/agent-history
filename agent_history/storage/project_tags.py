"""Project tag helpers.

Tags are project metadata stored separately from project workspace definitions so
the existing project schema remains a pure home-to-workspace map.
"""

from __future__ import annotations

import re
from typing import Any

PROJECT_TAGS_KEY = "project_tags"
UNTAGGED_TAG = "untagged"


def normalize_tag(tag: Any) -> str:
    """Return a stable lowercase tag slug.

    Whitespace and unsupported punctuation collapse to ``-``. Underscore,
    period, and hyphen are preserved because they are common shell-friendly
    separators.
    """
    normalized = re.sub(r"[^a-z0-9._-]+", "-", str(tag).strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        raise ValueError("Tag must not be empty")
    return normalized


def normalize_tags(tags: list[Any] | tuple[Any, ...] | set[Any]) -> list[str]:
    """Normalize tags while preserving first-seen order."""
    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = normalize_tag(tag)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def project_tag_map(config: dict[str, Any]) -> dict[str, list[str]]:
    """Return normalized project tag mapping from config."""
    raw = config.get(PROJECT_TAGS_KEY) or {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, list[str]] = {}
    for project, tags in raw.items():
        if isinstance(tags, str):
            values: list[Any] = [tags]
        elif isinstance(tags, (list, tuple, set)):
            values = list(tags)
        else:
            values = []
        normalized = normalize_tags(values)
        if normalized:
            result[str(project)] = normalized
    return result


def project_tags_for(config: dict[str, Any], project: str) -> list[str]:
    """Return normalized tags for one project."""
    return project_tag_map(config).get(project, [])


def projects_for_tags(config: dict[str, Any], tags: list[Any]) -> list[str]:
    """Return configured project names that have at least one requested tag."""
    requested = set(normalize_tags(tags))
    if not requested:
        return []
    mapping = project_tag_map(config)
    projects = config.get("projects") or {}
    names = [str(name) for name in projects.keys()]
    return [name for name in names if requested.intersection(mapping.get(name, []))]


def set_project_tags(config: dict[str, Any], project: str, tags: list[Any]) -> list[str]:
    """Replace tags for a project and return the normalized list."""
    normalized = normalize_tags(tags)
    tag_map = project_tag_map(config)
    if normalized:
        tag_map[project] = normalized
    else:
        tag_map.pop(project, None)
    config[PROJECT_TAGS_KEY] = tag_map
    return normalized


def add_project_tags(
    config: dict[str, Any], project: str, tags: list[Any]
) -> tuple[list[str], list[str], list[str]]:
    """Add tags to a project.

    Returns ``(updated_tags, added_tags, existing_tags)``.
    """
    existing = project_tags_for(config, project)
    incoming = normalize_tags(tags)
    seen = set(existing)
    added: list[str] = []
    already_present: list[str] = []
    for tag in incoming:
        if tag in seen:
            already_present.append(tag)
            continue
        seen.add(tag)
        added.append(tag)
    updated = [*existing, *added]
    set_project_tags(config, project, updated)
    return updated, added, already_present


def remove_project_tags(
    config: dict[str, Any], project: str, tags: list[Any]
) -> tuple[list[str], list[str], list[str]]:
    """Remove tags from a project.

    Returns ``(updated_tags, removed_tags, missing_tags)``.
    """
    existing = project_tags_for(config, project)
    remove_set = set(normalize_tags(tags))
    removed = [tag for tag in existing if tag in remove_set]
    missing = [tag for tag in remove_set if tag not in existing]
    updated = [tag for tag in existing if tag not in remove_set]
    set_project_tags(config, project, updated)
    return updated, removed, missing
