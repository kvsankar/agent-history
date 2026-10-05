"""Which files to archive for each agent, and where they go in the archive.

Each agent has an allowlist of glob patterns relative to its root folder. A credential
denylist applies to every file whatever the configuration says. Archived paths mirror the
source's home directory, so ``.claude/history.jsonl`` is stored at
``sources/<source>/files/.claude/history.jsonl.zst``.
"""

from __future__ import annotations

import filecmp
import fnmatch
import os
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, NamedTuple, Pattern

from agent_history.archive.errors import ArchiveError

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
    # Browser credential stores (also caught by skipping whole profiles, below).
    "cookies",
    "cookies.sqlite*",
    "login data*",
    "web data*",
    "local state",
    "key4.db",
    "logins.json",
)

# A folder holding any of these is a browser profile: cookies, saved logins and caches,
# never session content. Such folders are not descended into.
BROWSER_PROFILE_MARKERS = ("Local State", "cookies.sqlite", "logins.json", "key4.db")

# Matched against file names only, in every layout.
COMMON_EXCLUDES = ("*.tmp", "*.part", "*-wal", "*-shm", "*-journal", "*.lock")


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
    """A source file chosen for archiving, or a path that could not be read."""

    rel_path: str  # home-relative, "/"-separated
    path: Path
    agent: str
    database: DatabaseRule | None = None
    # Set when this path could not be read; nothing at or below it can be judged deleted.
    error: str | None = None


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
            DatabaseRule("session-state/*/session.db", "snapshot"),
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
        include=("config.json", "aliases*.json", "project_tags*"),
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
    """Yield every file of a source that should be archived, each path once.

    A configured home or agent root that is missing or cannot be read raises
    :class:`ArchiveError`, because walking it would make every file look deleted. A
    folder inside it that cannot be read is yielded as an item with ``error`` set, whose
    ``rel_path`` is the folder; the walk goes on with the other folders.

    When parts of a merged source map two different files to one archive path, the
    first part's file is archived. If the other file's content differs, it is yielded
    as an item with ``error`` set, so the run reports it instead of dropping it.
    """
    _check_configured_folders(source)
    seen: dict[str, SelectedFile] = {}
    for part in source.parts:
        for item in _iter_part(part, source.platform):
            first = seen.get(item.rel_path)
            if first is None:
                seen[item.rel_path] = item
                yield item
            elif first.error is None and item.error is None and first.path != item.path:
                problem = _collision(first, item)
                if problem:
                    yield replace(item, error=problem)


def _collision(first: SelectedFile, other: SelectedFile) -> str | None:
    """Why ``other`` cannot share ``first``'s archive path, or None if they are the same.

    Files of the same size and modification time count as the same, as in change
    detection; files of the same size are otherwise compared byte by byte.
    """
    try:
        a, b = os.stat(first.path), os.stat(other.path)
        if a.st_size == b.st_size and (
            a.st_mtime_ns == b.st_mtime_ns or filecmp.cmp(first.path, other.path, shallow=False)
        ):
            return None
    except OSError as exc:
        return f"cannot compare {other.path} with {first.path}: {exc}"
    return (
        f"{other.path} differs from {first.path}, which another entry of this source maps "
        "to the same archive path; it is not archived. Give its folder its own source name."
    )


def is_within(rel_path: str, folders) -> bool:
    """Whether ``rel_path`` is one of ``folders`` or lies inside one of them."""
    return any(not f or rel_path == f or rel_path.startswith(f + "/") for f in folders)


def _check_configured_folders(source: SourceConfig) -> None:
    for part in source.parts:
        agents = part.agents or AGENT_NAMES
        folders = [part.home] if part.home is not None else []
        folders += [root for agent, root in part.roots.items() if agent in agents]
        for folder in folders:
            try:
                with os.scandir(folder):
                    pass
            except OSError as exc:
                raise ArchiveError(
                    f"Source {source.name}: cannot read {folder}: {exc.strerror or exc}"
                ) from exc


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
    for found in _walk_matching(abs_root, patterns):
        if isinstance(found, _Unreadable):
            rel_path = f"{rel_root}/{found.rel_path}" if found.rel_path else rel_root
            if not _excludes_folder(found.rel_path, layout.exclude, rel_path, part.exclude):
                yield SelectedFile(
                    rel_path, abs_root / found.rel_path, layout.name, error=found.message
                )
            continue
        if _matches_any(found, layout.exclude) or not _name_allowed(found):
            continue
        rel_path = f"{rel_root}/{found}"
        if _matches_any(rel_path, part.exclude):
            continue
        database = next(
            (rule for rule in layout.databases if _compiled(rule.pattern).match(found)), None
        )
        yield SelectedFile(rel_path, abs_root / found, layout.name, database)


def _iter_config_includes(part: SourcePart, platform: str) -> Iterator[SelectedFile]:
    home = part.home
    if home is None:
        return
    for found in _walk_matching(home, list(part.include)):
        if isinstance(found, _Unreadable):
            if not _excludes_folder(found.rel_path, (), found.rel_path, part.exclude):
                agent = _agent_for(found.rel_path, platform)
                yield SelectedFile(
                    found.rel_path, home / found.rel_path, agent, error=found.message
                )
            continue
        if not _name_allowed(found) or _matches_any(found, part.exclude):
            continue
        yield SelectedFile(found, home / found, _agent_for(found, platform))


def _excludes_folder(inner: str, layout_exclude, rel_path: str, part_exclude) -> bool:
    """Whether exclusions drop everything inside a folder, so it need not be read."""
    return _matches_any(inner + "/", layout_exclude) or _matches_any(rel_path + "/", part_exclude)


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


class _Unreadable(NamedTuple):
    """A folder or entry under the walk root that could not be read."""

    rel_path: str  # "/"-separated, relative to the walk root; "" for the root itself
    message: str


def _walk_matching(root: Path, patterns: list[str]) -> Iterator[str | _Unreadable]:
    """Yield "/"-separated paths under ``root`` that match any pattern, without symlinks.

    Each pattern is followed segment by segment, so a pattern only descends into folders
    it can match; only a ``**`` segment walks a whole subtree. A folder that cannot be
    read is yielded once as :class:`_Unreadable`; a folder that does not exist is empty.
    """
    found = set()
    for pattern in patterns:
        regex = _compiled(pattern)
        for item in _walk_segments(root, "", pattern.split("/"), top=True):
            if isinstance(item, _Unreadable):
                if item.rel_path not in found:
                    found.add(item.rel_path)
                    yield item
            elif item not in found and regex.match(item):
                found.add(item)
                yield item


def _walk_segments(
    root: Path, rel_dir: str, segments: list[str], top: bool = False
) -> Iterator[str | _Unreadable]:
    """Walk ``rel_dir`` for ``segments``; folders below the top are checked for profiles."""
    entries = _scan(root, rel_dir)
    if isinstance(entries, _Unreadable):
        yield entries
        return
    if not top and _is_browser_profile(entries):
        return
    segment, rest = segments[0], segments[1:]
    if segment == "**":
        rest = segments
    matcher = None if segment == "**" else _compiled(segment)
    for entry in entries:
        if matcher is not None and not matcher.match(entry.name):
            continue
        rel_path = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
        kind = _entry_kind(entry)
        if kind == "error":
            yield _Unreadable(rel_path, f"cannot read {entry.path}")
        elif kind == "dir" and rest:
            yield from _walk_segments(root, rel_path, rest)
        elif kind == "file" and (not rest or segment == "**"):
            yield rel_path


def _entry_kind(entry: os.DirEntry) -> str:
    """ "dir", "file", "other" (symbolic links too, which are never followed) or "error"."""
    try:
        if entry.is_symlink():
            return "other"
        if entry.is_dir(follow_symlinks=False):
            return "dir"
        return "file" if entry.is_file(follow_symlinks=False) else "other"
    except OSError:
        return "error"


def _is_browser_profile(entries: list[os.DirEntry]) -> bool:
    names = {entry.name.lower() for entry in entries}
    return any(marker.lower() in names for marker in BROWSER_PROFILE_MARKERS)


def _scan(root: Path, rel_dir: str) -> list[os.DirEntry] | _Unreadable:
    folder = root / rel_dir if rel_dir else root
    try:
        with os.scandir(folder) as entries:
            return sorted(entries, key=lambda entry: entry.name)
    except (FileNotFoundError, NotADirectoryError):
        return []  # the agent has no such folder, or it was deleted during the walk
    except OSError as exc:
        return _Unreadable(rel_dir, str(exc))


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
