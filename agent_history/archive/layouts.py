"""Which files to archive for each agent, and where they go in the archive.

Each agent has an allowlist of glob patterns relative to its root folder. A credential
denylist applies to every file whatever the configuration says. Archived paths mirror the
source's home directory, so ``.claude/history.jsonl`` is stored at
``sources/<source>/files/.claude/history.jsonl.zst``.
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Pattern

if TYPE_CHECKING:
    from agent_history.archive.config import SourceConfig, SourcePart

ARCHIVE_SUFFIX = ".zst"
OTHER_AGENT = "other"

# Matched against file names only, everywhere. Never archived.
CREDENTIAL_DENYLIST = (
    "auth.json",
    "*oauth*",
    "*.pem",
    "*.key",
    ".credentials.json",
    "credentials*",
    "google_accounts.json",
)

# Matched against file names only, in every layout.
COMMON_EXCLUDES = ("*.tmp", "*.part", "*-wal", "*-shm", "*-journal")


@dataclass(frozen=True)
class DatabaseRule:
    """A SQLite database to archive as a snapshot or by exporting new log rows."""

    pattern: str
    mode: str  # "snapshot" or "log"
    blank_columns: tuple[str, ...] = ()  # "table.column"
    log_table: str | None = None
    log_key: str | None = None
    # Returns (session_id, cwd, git_branch, first_time, last_time, message_count) per session.
    sessions_sql: str | None = None


@dataclass(frozen=True)
class AgentLayout:
    """Where one agent keeps the files worth archiving."""

    name: str
    roots: dict[str, tuple[str, ...]]  # platform (or "*") -> home-relative roots
    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    databases: tuple[DatabaseRule, ...] = ()
    backend: str | None = None  # cagelens backend id that reads this agent's sessions
    sessions: tuple[str, ...] = ()  # session file patterns, relative to the root

    def roots_for(self, platform: str) -> tuple[str, ...]:
        return self.roots.get(platform) or self.roots.get("*", ())


@dataclass(frozen=True)
class SelectedFile:
    """A source file chosen for archiving."""

    rel_path: str  # home-relative, "/"-separated
    path: Path
    agent: str
    database: DatabaseRule | None = None


_VSCODE_USER_DIRS = {
    "windows": ("AppData/Roaming/Code/User", "AppData/Roaming/Code - Insiders/User"),
    "darwin": (
        "Library/Application Support/Code/User",
        "Library/Application Support/Code - Insiders/User",
    ),
    "linux": (".config/Code/User", ".config/Code - Insiders/User", ".vscode-server/data/User"),
}

LAYOUTS: tuple[AgentLayout, ...] = (
    AgentLayout(
        name="claude",
        roots={"*": (".claude",)},
        include=(
            "projects/**",
            "sessions/**",
            "history.jsonl",
            "todos/**",
            "plans/**",
            "tasks/**",
            "file-history/**",
            "usage-data/**",
        ),
        backend="claude",
        sessions=("projects/*/*.jsonl", "projects/*/*/subagents/*.jsonl"),
    ),
    AgentLayout(
        name="codex",
        roots={"*": (".codex",)},
        include=("sessions/**", "archived_sessions/**", "history.jsonl", "session_index.jsonl"),
        databases=(
            DatabaseRule(
                "state_*.sqlite",
                "snapshot",
                sessions_sql="SELECT id, cwd, NULL, created_at, updated_at, NULL FROM threads",
            ),
            DatabaseRule("memories_*.sqlite", "snapshot"),
            DatabaseRule("goals_*.sqlite", "snapshot"),
            DatabaseRule("queue_*.sqlite", "snapshot"),
            DatabaseRule("logs_*.sqlite", "log", log_table="logs", log_key="id"),
        ),
        backend="codex",
        sessions=(
            "sessions/**/rollout-*.jsonl",
            "sessions/**/rollout-*.jsonl.zst",
            "archived_sessions/**/rollout-*.jsonl",
            "archived_sessions/**/rollout-*.jsonl.zst",
        ),
    ),
    AgentLayout(
        name="gemini",
        roots={"*": (".gemini",)},
        include=("history/**", "tmp/**", "antigravity/**"),
        exclude=("tmp/*/tool-outputs/**", "tmp/bin/**"),
        backend="gemini",
        sessions=("tmp/*/chats/*.json", "tmp/*/chats/*.jsonl"),
    ),
    AgentLayout(
        name="pi",
        roots={"*": (".pi/agent",)},
        include=("sessions/**",),
        backend="pi",
        sessions=("sessions/**/*.jsonl",),
    ),
    AgentLayout(
        name="copilot-cli",
        roots={"*": (".copilot",)},
        include=("session-state/**", "chats/**", "history-session-state/**"),
        databases=(
            DatabaseRule(
                "session-store.db",
                "snapshot",
                sessions_sql=(
                    "SELECT s.id, s.cwd, s.branch, s.created_at, s.updated_at, "
                    "(SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) FROM sessions s"
                ),
            ),
            DatabaseRule(
                "data.db",
                "snapshot",
                blank_columns=("accounts.access_token", "settings.github_access_token"),
            ),
            DatabaseRule(
                "data.db.pre-update-backup-*",
                "snapshot",
                blank_columns=("accounts.access_token", "settings.github_access_token"),
            ),
        ),
        backend="copilot-cli",
        sessions=("session-state/*/events.jsonl",),
    ),
    AgentLayout(
        name="copilot-vscode",
        roots=_VSCODE_USER_DIRS,
        include=("workspaceStorage/*/GitHub.copilot-chat/**", "workspaceStorage/*/chatSessions/**"),
        backend="copilot-vscode",
        sessions=("workspaceStorage/*/GitHub.copilot-chat/transcripts/*.jsonl",),
    ),
    AgentLayout(
        name="cagelens",
        roots={"*": (".agent-history", ".cagelens")},
        include=("**",),
        exclude=("remote-cache/**", "web-cache/**", "archive-state/**", "*.db"),
    ),
)

AGENT_NAMES = tuple(layout.name for layout in LAYOUTS)
_LAYOUTS_BY_NAME = {layout.name: layout for layout in LAYOUTS}


def archive_file_path(source: str, rel_path: str) -> str:
    """Archive-relative path of a source file's compressed copy."""
    return f"sources/{source}/files/{rel_path}{ARCHIVE_SUFFIX}"


def original_path(source: str, archived: str) -> str:
    """Inverse of :func:`archive_file_path`."""
    prefix = f"sources/{source}/files/"
    if not archived.startswith(prefix) or not archived.endswith(ARCHIVE_SUFFIX):
        raise ValueError(f"Not an archived file of {source}: {archived}")
    return archived[len(prefix) : -len(ARCHIVE_SUFFIX)]


@dataclass(frozen=True)
class SessionTarget:
    """How to read sessions out of an archived file."""

    backend: str
    database: DatabaseRule | None = None


def session_target(rel_path: str, platform: str) -> SessionTarget | None:
    """The backend that reads sessions from a home-relative path, if it holds any."""
    for layout in LAYOUTS:
        if layout.backend is None:
            continue
        for root in layout.roots_for(platform):
            if not rel_path.startswith(root + "/"):
                continue
            inner = rel_path[len(root) + 1 :]
            if _matches_any(inner, layout.sessions):
                return SessionTarget(layout.backend)
            for rule in layout.databases:
                if rule.sessions_sql and _compiled(rule.pattern).match(inner):
                    return SessionTarget(layout.backend, rule)
    return None


def iter_source_files(source: SourceConfig) -> Iterator[SelectedFile]:
    """Yield every file of a source that should be archived, each path once."""
    seen = set()
    for part in source.parts:
        for item in _iter_part(part, source.platform):
            if item.rel_path not in seen:
                seen.add(item.rel_path)
                yield item


def _iter_part(part: SourcePart, platform: str) -> Iterator[SelectedFile]:
    agents = part.agents or AGENT_NAMES
    for name in agents:
        layout = _LAYOUTS_BY_NAME[name]
        for abs_root, rel_root in _agent_roots(part, layout, platform):
            yield from _iter_agent_root(part, layout, abs_root, rel_root)
    if part.home is not None and part.include:
        yield from _iter_config_includes(part, platform)


def _agent_roots(part: SourcePart, layout: AgentLayout, platform: str) -> list[tuple[Path, str]]:
    defaults = layout.roots_for(platform)
    if layout.name in part.roots:
        return [(part.roots[layout.name], defaults[0])] if defaults else []
    if part.home is None:
        return []
    return [(part.home / rel_root, rel_root) for rel_root in defaults]


def _iter_agent_root(
    part: SourcePart, layout: AgentLayout, abs_root: Path, rel_root: str
) -> Iterator[SelectedFile]:
    patterns = list(layout.include) + [rule.pattern for rule in layout.databases]
    for inner in _walk_matching(abs_root, patterns):
        if _matches_any(inner, layout.exclude) or not _name_allowed(inner):
            continue
        rel_path = f"{rel_root}/{inner}"
        if _matches_any(rel_path, part.exclude):
            continue
        database = next(
            (rule for rule in layout.databases if _compiled(rule.pattern).match(inner)), None
        )
        yield SelectedFile(rel_path, abs_root / inner, layout.name, database)


def _iter_config_includes(part: SourcePart, platform: str) -> Iterator[SelectedFile]:
    home = part.home
    if home is None:
        return
    for rel_path in _walk_matching(home, list(part.include)):
        if not _name_allowed(rel_path) or _matches_any(rel_path, part.exclude):
            continue
        yield SelectedFile(rel_path, home / rel_path, _agent_for(rel_path, platform))


def _agent_for(rel_path: str, platform: str) -> str:
    for layout in LAYOUTS:
        for root in layout.roots_for(platform):
            if rel_path.startswith(root + "/"):
                return layout.name
    return OTHER_AGENT


def _name_allowed(rel_path: str) -> bool:
    name = rel_path.rsplit("/", 1)[-1]
    lowered = name.lower()
    if any(fnmatch.fnmatchcase(lowered, pattern) for pattern in CREDENTIAL_DENYLIST):
        return False
    return not any(fnmatch.fnmatchcase(name, pattern) for pattern in COMMON_EXCLUDES)


def _walk_matching(root: Path, patterns: list[str]) -> Iterator[str]:
    """Yield "/"-separated paths under ``root`` that match any pattern, without symlinks."""
    found = set()
    for pattern in patterns:
        regex = _compiled(pattern)
        prefix = _static_prefix(pattern)
        start = root / prefix if prefix else root
        for rel_path in _walk_files(root, start):
            if rel_path not in found and regex.match(rel_path):
                found.add(rel_path)
                yield rel_path


def _walk_files(root: Path, start: Path) -> Iterator[str]:
    if start.is_symlink():
        return
    if start.is_file():
        yield start.relative_to(root).as_posix()
        return
    if not start.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not os.path.islink(os.path.join(dirpath, d)))
        base = Path(dirpath)
        for filename in sorted(filenames):
            path = base / filename
            if not path.is_symlink():
                yield path.relative_to(root).as_posix()


def _static_prefix(pattern: str) -> str:
    segments = []
    for segment in pattern.split("/"):
        if any(ch in segment for ch in "*?["):
            break
        segments.append(segment)
    return "/".join(segments)


def _matches_any(rel_path: str, patterns) -> bool:
    return any(_compiled(pattern).match(rel_path) for pattern in patterns)


@lru_cache(maxsize=None)
def _compiled(pattern: str) -> Pattern[str]:
    """Compile a glob where ``**`` spans folders and ``*``/``?`` stay within one."""
    parts = []
    segments = pattern.split("/")
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            parts.append(".*" if last else "(?:[^/]*/)*")
            continue
        regex = "".join(
            "[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch) for ch in segment
        )
        parts.append(regex if last else regex + "/")
    return re.compile("".join(parts) + r"\Z", re.DOTALL)
