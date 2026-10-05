"""Which files to archive for each agent, and where they go in the archive.

Each agent has an allowlist of glob patterns relative to its root folder. A credential
denylist applies to every file whatever the configuration says, and to every folder a
configuration include passes through. Archived paths mirror the
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

# Matched against every file name, and against the folder names of files that a
# configuration include selects. Never archived. Folder names in the default layouts are
# not checked: a Claude project folder is named after any working folder, such as one
# called "oauth-proxy", and the layouts never select a credential folder.
CREDENTIAL_DENYLIST = (
    "auth.json",
    "*oauth*",
    "*.token",
    "*tokens.json",
    "*.pem",
    "*.key",
    ".credentials.json",
    "credentials*",
    "google_accounts.json",
    # MCP server configurations, which carry API keys in env or headers.
    "*mcp*config*",
    "mcp.json*",
    ".mcp.json*",
    # Sign-in status and logs, such as Claude's daemon-auth-status.json and Codex's
    # codex-login.log.
    "*auth-status*",
    "*login*.log",
    # SSH and other private keys and certificate stores.
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "*.ppk",
    "*.p12",
    "*.pfx",
    # Files that hold passwords or tokens for other tools.
    ".netrc",
    "_netrc",
    ".git-credentials",
    ".pgpass",
    ".npmrc",
    ".pypirc",
    # Browser credential stores (also caught by skipping whole profiles, below).
    "*cookies",
    "cookies.txt",
    "cookies.sqlite*",
    "login data*",
    "web data*",
    "local state",
    "key4.db",
    "logins.json",
)

# A folder holding any of these is a browser profile: cookies, saved logins and caches,
# never session content. Such folders are not descended into. "Local State" marks the
# top folder of a Chromium user-data directory; the others mark one profile folder (such
# as "Default"), which can also be found on its own. Compared case-insensitively.
BROWSER_PROFILE_MARKERS = (
    "Local State",
    "Login Data",
    "Cookies",
    "Web Data",
    "cookies.sqlite",
    "logins.json",
    "key4.db",
)
# A Chromium profile keeps both of these; either alone is too common a name.
BROWSER_PROFILE_MARKER_PAIR = ("Preferences", "Secure Preferences")
# Newer Chromium versions keep cookies in this subfolder of a profile.
BROWSER_PROFILE_COOKIES = ("Network", "Cookies")

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
    # The folder, relative to the root, whose subfolders name each session's workspace
    # (Claude's projects/<workspace>/), when the agent keeps sessions that way.
    workspace_folder: str | None = None

    def roots_for(self, platform: str) -> tuple[str, ...]:
        return self.roots.get(platform) or self.roots.get("*", ())


# The rule for a SQLite database that a configuration include selects and no layout rule
# names: a snapshot with credential-named columns blanked, never a raw copy.
GENERIC_SNAPSHOT = DatabaseRule("*", "snapshot")
_SQLITE_HEADER = b"SQLite format 3\x00"


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
        # The background daemon's sign-in state.
        exclude=("daemon-auth-*",),
        backend="claude",
        sessions=(
            "projects/*/*.jsonl",
            "projects/*/*/subagents/*.jsonl",
            # Sub-agents of a workflow; the folder's journal.jsonl holds no session.
            "projects/*/*/subagents/workflows/*/agent-*.jsonl",
        ),
        workspace_folder="projects",
    ),
    AgentLayout(
        name="codex",
        roots={"*": (".codex",)},
        include=("sessions/**", "archived_sessions/**", "history.jsonl", "session_index.jsonl"),
        exclude=(
            # Built from the rollout files, recording how far into each one it has read.
            "thread_history_*.sqlite",
            # Copies of config.toml, which can hold MCP server keys and bearer tokens:
            # backups, editor backups and undo files.
            "config.toml?*",
            ".config.toml.*",
            "backups/**/config.toml*",
            "computer-use/config.json",
        ),
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
        workspace_folder="tmp",
    ),
    AgentLayout(
        name="pi",
        roots={"*": (".pi/agent",)},
        include=("sessions/**",),
        # Custom model providers keep their API keys in models.json.
        exclude=("models.json", "models.json.*"),
        backend="pi",
        sessions=("sessions/**/*.jsonl",),
    ),
    AgentLayout(
        name="copilot-cli",
        roots={"*": (".copilot",)},
        include=("session-state/**", "chats/**", "history-session-state/**"),
        exclude=(
            # A cache of repository details that Copilot rebuilds.
            "repo-metadata-cache.db",
            # Settings that can hold signed-in users' tokens, and logs that can record
            # request headers.
            "config.json",
            "settings.json",
            "logs/**",
        ),
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
        # SQLite files here are indexes of the workspace's files (path, size, time and
        # hash per file) that Copilot rebuilds; they hold no chat content.
        exclude=(
            "workspaceStorage/*/GitHub.copilot-chat/**/*.sqlite",
            "workspaceStorage/*/GitHub.copilot-chat/**/*.sqlite3",
            "workspaceStorage/*/GitHub.copilot-chat/**/*.db",
        ),
        backend="copilot-vscode",
        sessions=("workspaceStorage/*/GitHub.copilot-chat/transcripts/*.jsonl",),
    ),
    AgentLayout(
        name="cagelens",
        roots={"*": (".agent-history", ".cagelens")},
        include=("config.json", "aliases*.json", "project_tags*"),
        # Caches, which hold copies of other machines' sessions or data rebuilt from
        # sessions, and the collector's own work folder.
        exclude=(
            "remote_*/**",
            "remote-cache/**",
            "**/metrics.db*",
            "*_index.json",
            "archive-work/**",
        ),
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
    # The workspace that the file's path names, for agents with a workspace_folder.
    workspace: str | None = None


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
                return SessionTarget(layout.backend, workspace=_path_workspace(layout, inner))
            for rule in layout.databases:
                if rule.sessions_sql and _compiled(rule.pattern).match(inner):
                    return SessionTarget(layout.backend, rule)
    return None


def _path_workspace(layout: AgentLayout, inner: str) -> str | None:
    """The workspace folder that a root-relative path lies in, if the layout has one."""
    if layout.workspace_folder is None or not inner.startswith(layout.workspace_folder + "/"):
        return None
    rest = inner[len(layout.workspace_folder) + 1 :].split("/")
    return rest[0] if len(rest) > 1 else None


def iter_source_files(source: SourceConfig) -> Iterator[SelectedFile]:
    """Yield every file of a source that should be archived, each path once.

    A configured home or agent root that is missing or cannot be read raises
    :class:`ArchiveError`, because walking it would make every file look deleted. A
    folder inside it that cannot be read is yielded as an item with ``error`` set, whose
    ``rel_path`` is the folder; the walk goes on with the other folders.

    Parts of one source never cover the same agent (the configuration refuses that),
    but their include patterns can still map two different files to one archive path.
    Then the first part's file is archived. If the other file's content differs, it is
    yielded as an item with ``error`` set, so the run reports it instead of dropping it.
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
        agents = AGENT_NAMES if part.agents is None else part.agents
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
    agents = AGENT_NAMES if part.agents is None else part.agents
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
        yield SelectedFile(rel_path, abs_root / found, layout.name, _database_rule(layout, found))


def _database_rule(layout: AgentLayout, inner: str) -> DatabaseRule | None:
    return next((rule for rule in layout.databases if _compiled(rule.pattern).match(inner)), None)


def _iter_config_includes(part: SourcePart, platform: str) -> Iterator[SelectedFile]:
    """Files matched by the configuration's own include patterns.

    A file inside an agent's folder gets that agent's rules, as if the layout had
    selected it: its exclusions apply and a database is snapshotted, blanked or exported
    by rows. Any other SQLite database, inside an agent's folder or not, is snapshotted
    with :data:`GENERIC_SNAPSHOT`. So an include can add files to an agent folder but
    never copy a database raw or bring back what the layout leaves out.
    """
    home = part.home
    if home is None:
        return
    for found in _walk_matching(home, list(part.include)):
        rel_path = found.rel_path if isinstance(found, _Unreadable) else found
        layout, inner = _layout_for(rel_path, platform)
        layout_exclude = layout.exclude if layout is not None else ()
        agent = layout.name if layout is not None else OTHER_AGENT
        if isinstance(found, _Unreadable):
            if _folders_allowed(rel_path + "/") and not _excludes_folder(
                inner, layout_exclude, rel_path, part.exclude
            ):
                yield SelectedFile(rel_path, home / rel_path, agent, error=found.message)
            continue
        if not _name_allowed(found) or not _folders_allowed(found):
            continue
        if _matches_any(found, part.exclude) or _matches_any(inner, layout_exclude):
            continue
        rule = _database_rule(layout, inner) if layout is not None else None
        if rule is None and _is_sqlite_database(home / found):
            rule = GENERIC_SNAPSHOT
        yield SelectedFile(found, home / found, agent, rule)


def _is_sqlite_database(path: Path) -> bool:
    """Whether a file is a SQLite database, judged by its header, not its name.

    A WAL database can be empty on disk until its first checkpoint, with every row in
    its ``-wal`` file; an empty file with a non-empty ``-wal`` file beside it counts too.
    """
    header = _read_header(path)
    if header == _SQLITE_HEADER:
        return True
    if header != b"":  # not empty, or not readable: the collector reports the latter
        return False
    try:
        return os.lstat(f"{path}-wal").st_size > 0
    except OSError:
        return False


def _read_header(path: Path) -> bytes | None:
    """The first bytes of a file, as many as a SQLite header has; None if unreadable."""
    try:
        with open(path, "rb") as handle:
            return handle.read(len(_SQLITE_HEADER))
    except OSError:
        return None


def _excludes_folder(inner: str, layout_exclude, rel_path: str, part_exclude) -> bool:
    """Whether exclusions drop everything inside a folder, so it need not be read."""
    return _matches_any(inner + "/", layout_exclude) or _matches_any(rel_path + "/", part_exclude)


def _layout_for(rel_path: str, platform: str) -> tuple[AgentLayout | None, str]:
    """The layout whose folder holds a home-relative path, and the path inside it."""
    for layout in LAYOUTS:
        for root in layout.roots_for(platform):
            if rel_path.startswith(root + "/"):
                return layout, rel_path[len(root) + 1 :]
    return None, rel_path


def _name_allowed(rel_path: str) -> bool:
    name = rel_path.rsplit("/", 1)[-1]
    if _is_credential_name(name):
        return False
    return not any(fnmatch.fnmatchcase(name, pattern) for pattern in COMMON_EXCLUDES)


def _folders_allowed(rel_path: str) -> bool:
    """Whether no folder on ``rel_path`` (every segment but the last) is a credential name."""
    return not any(_is_credential_name(folder) for folder in rel_path.split("/")[:-1])


def _is_credential_name(name: str) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatchcase(lowered, pattern) for pattern in CREDENTIAL_DENYLIST)


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
    names = {entry.name.lower(): entry for entry in entries}
    if any(marker.lower() in names for marker in BROWSER_PROFILE_MARKERS):
        return True
    if all(marker.lower() in names for marker in BROWSER_PROFILE_MARKER_PAIR):
        return True
    folder, cookies = BROWSER_PROFILE_COOKIES
    network = names.get(folder.lower())
    if network is None or _entry_kind(network) != "dir":
        return False
    try:
        with os.scandir(network.path) as inner:
            return any(entry.name.lower() == cookies.lower() for entry in inner)
    except OSError:
        return False  # the walk reports the folder when it tries to read it


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
