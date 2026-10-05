"""Tests for per-agent file selection."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agent_history.archive.config import parse_config
from agent_history.archive.errors import ArchiveError
from agent_history.archive.layouts import (
    archive_file_path,
    iter_source_files,
    original_path,
    session_target,
)


@pytest.mark.parametrize(
    "rel_path",
    [
        ".claude/projects/-home-alex-shop/s1.jsonl",
        ".claude/projects/-home-alex-shop/s1/subagents/agent-a1.jsonl",
        ".claude/projects/-home-alex-shop/s1/subagents/workflows/wf_1/agent-a2.jsonl",
    ],
)
def test_claude_session_files_are_read_for_sessions(rel_path):
    target = session_target(rel_path, "linux")

    assert target is not None
    assert (target.backend, target.workspace) == ("claude", "-home-alex-shop")


def test_a_claude_workflow_journal_is_not_read_for_sessions():
    rel = ".claude/projects/-home-alex-shop/s1/subagents/workflows/wf_1/journal.jsonl"

    assert session_target(rel, "linux") is None


def _touch(root: Path, rel: str, text: str = "x") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _source(home: Path, platform: str = "linux", **extra):
    entry = {"name": "src", "kind": "live", "platform": platform, "home": str(home)}
    entry.update(extra)
    config = parse_config({"archive": {"destination": "/dest"}, "sources": [entry]})
    return config.sources[0]


def _selected(source) -> dict:
    return {item.rel_path: item for item in iter_source_files(source)}


def test_selects_session_files_and_skips_settings(tmp_path):
    _touch(tmp_path, ".claude/projects/-home-alex-shop/a1.jsonl")
    _touch(tmp_path, ".claude/history.jsonl")
    _touch(tmp_path, ".claude/settings.json")
    _touch(tmp_path, ".claude/plugins/cache/x.js")
    _touch(tmp_path, ".codex/sessions/2026/10/02/rollout-1.jsonl")
    _touch(tmp_path, ".codex/config.toml")
    _touch(tmp_path, ".pi/agent/sessions/--home-alex--/s.jsonl")
    _touch(tmp_path, ".copilot/session-state/abc/events.jsonl")

    selected = _selected(_source(tmp_path))

    assert set(selected) == {
        ".claude/projects/-home-alex-shop/a1.jsonl",
        ".claude/history.jsonl",
        ".codex/sessions/2026/10/02/rollout-1.jsonl",
        ".pi/agent/sessions/--home-alex--/s.jsonl",
        ".copilot/session-state/abc/events.jsonl",
    }
    assert selected[".claude/history.jsonl"].agent == "claude"
    assert selected[".claude/history.jsonl"].path == tmp_path / ".claude" / "history.jsonl"


def test_layout_exclusions_apply(tmp_path):
    _touch(tmp_path, ".gemini/tmp/abc/chats/session-1.json")
    _touch(tmp_path, ".gemini/tmp/abc/tool-outputs/out.txt")
    _touch(tmp_path, ".gemini/tmp/bin/rg")
    _touch(tmp_path, ".claude/projects/p/a.jsonl.tmp")
    _touch(tmp_path, ".copilot/data.db-wal")

    assert set(_selected(_source(tmp_path))) == {".gemini/tmp/abc/chats/session-1.json"}


def test_credential_files_are_never_selected(tmp_path):
    _touch(tmp_path, ".claude/projects/p/auth.json")
    _touch(tmp_path, ".claude/projects/p/my-oauth-token.json")
    _touch(tmp_path, ".claude/projects/p/server.pem")
    _touch(tmp_path, ".codex/auth.json")
    source = _source(tmp_path, include=[".codex/auth.json", ".claude/projects/**"])

    assert set(_selected(source)) == set()


@pytest.mark.parametrize(
    "name",
    [
        "id_rsa",
        "id_rsa.pub",
        "id_ed25519",
        "id_ecdsa",
        "id_dsa",
        "id_ed25519_sk",
        ".netrc",
        "_netrc",
        ".git-credentials",
        ".pgpass",
        ".npmrc",
        ".pypirc",
        "client.p12",
        "client.PFX",
        "server.pem",
        "putty.ppk",
        "Extension Cookies",
        "Safe Browsing Cookies",
        "cookies.txt",
        "ws.token",
        "ws.release.token",
        "abc123.tokens.json",
        # MCP server configurations carry API keys in env or headers.
        "mcp_config.json",
        "mcp-config.json",
        ".mcp.json",
        "mcp.json",
        "MCP_Config.json",
        "remote-mcp-server-config.json",
        "mcp_config.json.bak",
    ],
)
def test_more_credential_files_are_never_selected(tmp_path, name):
    _touch(tmp_path, f".claude/projects/p/{name}")
    _touch(tmp_path, ".claude/projects/p/id_map.json")

    assert set(_selected(_source(tmp_path))) == {".claude/projects/p/id_map.json"}


def test_mcp_configurations_are_never_selected_by_layouts_or_includes(tmp_path):
    _touch(tmp_path, ".gemini/antigravity/mcp_config.json")
    _touch(tmp_path, ".gemini/antigravity/conversations/c1.pb")
    _touch(tmp_path, ".copilot/mcp-config.json")
    _touch(tmp_path, ".claude/plugins/x/.mcp.json")
    _touch(tmp_path, ".config/Code/User/mcp.json")
    _touch(tmp_path, "notes/n.md")
    include = [".copilot/**", ".claude/plugins/**", ".config/**", "notes/**"]

    selected = _selected(_source(tmp_path, include=include))

    assert set(selected) == {".gemini/antigravity/conversations/c1.pb", "notes/n.md"}


def test_config_include_and_exclude(tmp_path):
    _touch(tmp_path, "notes/agent-log.md")
    _touch(tmp_path, ".claude/projects/p/a.jsonl")
    _touch(tmp_path, ".claude/projects/q/b.jsonl")
    source = _source(tmp_path, include=["notes/*.md"], exclude=[".claude/projects/q/**"])

    assert set(_selected(source)) == {"notes/agent-log.md", ".claude/projects/p/a.jsonl"}


def test_agents_filter_limits_selection(tmp_path):
    _touch(tmp_path, ".claude/history.jsonl")
    _touch(tmp_path, ".codex/history.jsonl")

    assert set(_selected(_source(tmp_path, agents=["codex"]))) == {".codex/history.jsonl"}


def test_vscode_chats_use_the_source_platform(tmp_path):
    storage = "AppData/Roaming/Code/User/workspaceStorage/ws1"
    _touch(tmp_path, f"{storage}/GitHub.copilot-chat/transcripts/t.jsonl")
    _touch(tmp_path, f"{storage}/chatSessions/c.json")
    _touch(tmp_path, f"{storage}/state.vscdb")
    _touch(tmp_path, ".config/Code/User/workspaceStorage/ws2/chatSessions/linux.json")

    selected = _selected(_source(tmp_path, platform="windows"))

    assert set(selected) == {
        f"{storage}/GitHub.copilot-chat/transcripts/t.jsonl",
        f"{storage}/chatSessions/c.json",
    }
    assert {item.agent for item in selected.values()} == {"copilot-vscode"}


def test_roots_override_maps_to_home_relative_paths(tmp_path):
    old = tmp_path / "raw" / "laptop" / "claude"
    _touch(old, "projects/p/a.jsonl")
    _touch(old, "history.jsonl")
    entry = {"name": "src", "kind": "live", "platform": "linux", "roots": {"claude": str(old)}}
    source = parse_config({"archive": {"destination": "/d"}, "sources": [entry]}).sources[0]

    selected = _selected(source)

    assert set(selected) == {".claude/projects/p/a.jsonl", ".claude/history.jsonl"}
    assert selected[".claude/history.jsonl"].path == old / "history.jsonl"


def test_copilot_chat_index_databases_are_skipped(tmp_path):
    chat = ".config/Code/User/workspaceStorage/ws1/GitHub.copilot-chat"
    _touch(tmp_path, f"{chat}/transcripts/t.jsonl")
    _touch(tmp_path, f"{chat}/memory-tool/notes.md")
    _touch(tmp_path, f"{chat}/codebase-external.sqlite")
    _touch(tmp_path, f"{chat}/local-index.1.db")
    _touch(tmp_path, f"{chat}/sub/workspace-chunks.sqlite3")

    assert set(_selected(_source(tmp_path, agents=["copilot-vscode"]))) == {
        f"{chat}/transcripts/t.jsonl",
        f"{chat}/memory-tool/notes.md",
    }


def _merged_source(home: Path, old: Path):
    """A source whose second entry includes another home's ``.claude`` folder, ``old``."""
    assert old.name == ".claude"
    entries = [
        {"name": "src", "kind": "live", "platform": "linux", "home": str(home)},
        {
            "name": "src",
            "kind": "live",
            "platform": "linux",
            "home": str(old.parent),
            "agents": [],
            "include": [".claude/**"],
        },
    ]
    return parse_config({"archive": {"destination": "/d"}, "sources": entries}).sources[0]


def _set_mtime(path: Path, stamp: int) -> None:
    os.utime(path, (stamp, stamp))


def test_merged_parts_with_a_differing_copy_report_it(tmp_path):
    home, old = tmp_path / "home", tmp_path / "old" / ".claude"
    _touch(home, ".claude/projects/p/a.jsonl", "live\n")
    _touch(old, "projects/p/a.jsonl", "older and longer\n")
    _touch(old, "projects/p/only-old.jsonl")

    items = list(iter_source_files(_merged_source(home, old)))

    paths = [(item.rel_path, item.path, item.error is not None) for item in items]
    assert sorted(paths) == [
        (".claude/projects/p/a.jsonl", home / ".claude/projects/p/a.jsonl", False),
        (".claude/projects/p/a.jsonl", old / "projects/p/a.jsonl", True),
        (".claude/projects/p/only-old.jsonl", old / "projects/p/only-old.jsonl", False),
    ]
    (error,) = [item.error for item in items if item.error]
    assert str(old / "projects/p/a.jsonl") in error


def test_merged_parts_with_the_same_content_are_not_reported(tmp_path):
    home, old = tmp_path / "home", tmp_path / "old" / ".claude"
    _touch(home, ".claude/history.jsonl", "same\n")
    _touch(old, "history.jsonl", "same\n")
    _touch(home, ".claude/projects/p/a.jsonl", "same size, other time\n")
    _touch(old, "projects/p/a.jsonl", "same size, other time\n")
    _set_mtime(home / ".claude/history.jsonl", 1_790_000_000)
    _set_mtime(old / "history.jsonl", 1_790_000_000)
    _set_mtime(old / "projects/p/a.jsonl", 1_780_000_000)

    items = list(iter_source_files(_merged_source(home, old)))

    assert [item.error for item in items] == [None, None]
    assert {item.path for item in items} == {
        home / ".claude/history.jsonl",
        home / ".claude/projects/p/a.jsonl",
    }


def test_merged_parts_with_same_size_and_other_content_report_it(tmp_path):
    home, old = tmp_path / "home", tmp_path / "old" / ".claude"
    _touch(home, ".claude/history.jsonl", "aaaa\n")
    _touch(old, "history.jsonl", "bbbb\n")
    _set_mtime(home / ".claude/history.jsonl", 1_790_000_000)
    _set_mtime(old / "history.jsonl", 1_780_000_000)

    items = list(iter_source_files(_merged_source(home, old)))

    assert [item.error is not None for item in items] == [False, True]


def test_databases_are_marked(tmp_path):
    _touch(tmp_path, ".codex/state_5.sqlite")
    _touch(tmp_path, ".codex/logs_2.sqlite")
    _touch(tmp_path, ".codex/thread_history_1.sqlite")
    _touch(tmp_path, ".copilot/session-store.db")
    _touch(tmp_path, ".copilot/repo-metadata-cache.db")

    selected = _selected(_source(tmp_path))

    assert set(selected) == {
        ".codex/state_5.sqlite",
        ".codex/logs_2.sqlite",
        ".copilot/session-store.db",
    }
    assert selected[".codex/state_5.sqlite"].database.mode == "snapshot"
    assert selected[".codex/logs_2.sqlite"].database.mode == "log"
    assert selected[".codex/logs_2.sqlite"].database.log_table == "logs"


def test_symlinks_are_not_followed(tmp_path):
    outside = tmp_path / "outside"
    _touch(outside, "secret.jsonl")
    projects = tmp_path / "home" / ".claude" / "projects"
    projects.mkdir(parents=True)
    (projects / "linked").symlink_to(outside, target_is_directory=True)

    assert set(_selected(_source(tmp_path / "home"))) == set()


_segment = st.text(
    alphabet=st.characters(blacklist_characters="/\\\x00", blacklist_categories=("Cs",)),
    min_size=1,
    max_size=12,
).filter(lambda s: s not in {".", ".."})


@given(st.lists(_segment, min_size=1, max_size=5))
def test_archive_path_round_trip(segments):
    rel = "/".join(segments)

    archived = archive_file_path("laptop", rel)

    assert archived == f"sources/laptop/files/{rel}.zst"
    assert original_path("laptop", archived) == rel


def test_walk_descends_only_where_patterns_can_match(tmp_path, monkeypatch):
    from agent_history.archive import layouts

    _touch(tmp_path, ".codex/state_5.sqlite")
    _touch(tmp_path, ".codex/.tmp/plugins/deep/tree/file.txt")
    _touch(tmp_path, ".codex/sessions/2026/10/02/rollout-1.jsonl")
    visited = []
    real_scandir = layouts.os.scandir

    def recording(path):
        visited.append(Path(path).as_posix())
        return real_scandir(path)

    monkeypatch.setattr(layouts.os, "scandir", recording)

    selected = _selected(_source(tmp_path, agents=["codex"]))

    assert set(selected) == {".codex/state_5.sqlite", ".codex/sessions/2026/10/02/rollout-1.jsonl"}
    skipped = (tmp_path / ".codex/.tmp").as_posix()
    assert visited
    assert not [path for path in visited if path == skipped or path.startswith(skipped + "/")]


def test_cagelens_keeps_configuration_not_caches(tmp_path):
    _touch(tmp_path, ".cagelens/config.json")
    _touch(tmp_path, ".cagelens/aliases.backup.20251216_104723.json")
    _touch(tmp_path, ".cagelens/project_tags.json")
    _touch(tmp_path, ".cagelens/remote_u1_codex/s.jsonl")
    _touch(tmp_path, ".cagelens/remote-cache/h/claude/x.jsonl")
    _touch(tmp_path, ".cagelens/metrics.db")
    _touch(tmp_path, ".agent-history/config.json")

    assert set(_selected(_source(tmp_path, agents=["cagelens"]))) == {
        ".cagelens/config.json",
        ".cagelens/aliases.backup.20251216_104723.json",
        ".cagelens/project_tags.json",
        ".agent-history/config.json",
    }


def test_browser_profiles_are_never_archived(tmp_path):
    base = ".copilot/session-state/abc/files"
    _touch(tmp_path, f"{base}/chrome-profile/Local State")
    _touch(tmp_path, f"{base}/chrome-profile/Default/Network/Cookies")
    _touch(tmp_path, f"{base}/chrome-profile/Default/Preferences")
    _touch(tmp_path, f"{base}/firefox/cookies.sqlite")
    _touch(tmp_path, f"{base}/firefox/prefs.js")
    _touch(tmp_path, f"{base}/stray/Login Data")
    _touch(tmp_path, f"{base}/screenshot.png")
    _touch(tmp_path, ".copilot/session-state/abc/inuse.41364.lock")

    assert set(_selected(_source(tmp_path))) == {f"{base}/screenshot.png"}


@pytest.mark.parametrize(
    "markers",
    [
        ["Login Data"],
        ["Cookies"],
        ["Network/Cookies"],
        ["Preferences", "Secure Preferences"],
        ["Web Data"],
    ],
)
def test_a_lone_browser_profile_folder_is_skipped(tmp_path, markers):
    base = ".copilot/session-state/abc/files"
    for marker in markers:
        _touch(tmp_path, f"{base}/Default/{marker}")
    _touch(tmp_path, f"{base}/Default/History")
    _touch(tmp_path, f"{base}/Default/Sessions/Session_1")
    _touch(tmp_path, f"{base}/notes.md")

    assert set(_selected(_source(tmp_path))) == {f"{base}/notes.md"}


def test_a_folder_with_only_preferences_is_not_a_profile(tmp_path):
    base = ".copilot/session-state/abc/files"
    _touch(tmp_path, f"{base}/tool/Preferences")
    _touch(tmp_path, f"{base}/tool/Network/settings.json")

    assert set(_selected(_source(tmp_path))) == {
        f"{base}/tool/Preferences",
        f"{base}/tool/Network/settings.json",
    }


def _refuse_folder(monkeypatch, folder: Path):
    """Make listing ``folder`` fail as it does for an unreadable folder."""
    from agent_history.archive import layouts

    real_scandir = layouts.os.scandir

    def scandir(path):
        if not isinstance(path, int) and Path(path) == folder:
            raise PermissionError(13, "Permission denied", str(path))
        return real_scandir(path)

    monkeypatch.setattr(layouts.os, "scandir", scandir)


def test_unreadable_folder_is_an_error_item_and_the_walk_goes_on(tmp_path, monkeypatch):
    _touch(tmp_path, ".claude/projects/p/a.jsonl")
    _touch(tmp_path, ".claude/projects/q/b.jsonl")
    _touch(tmp_path, ".claude/history.jsonl")
    _refuse_folder(monkeypatch, tmp_path / ".claude" / "projects" / "p")

    selected = _selected(_source(tmp_path))

    assert set(selected) == {
        ".claude/projects/p",
        ".claude/projects/q/b.jsonl",
        ".claude/history.jsonl",
    }
    assert "Permission denied" in selected[".claude/projects/p"].error
    assert selected[".claude/history.jsonl"].error is None


def test_unreadable_agent_root_is_an_error_item(tmp_path, monkeypatch):
    _touch(tmp_path, ".claude/history.jsonl")
    _touch(tmp_path, ".codex/history.jsonl")
    _refuse_folder(monkeypatch, tmp_path / ".claude")

    selected = _selected(_source(tmp_path))

    assert set(selected) == {".claude", ".codex/history.jsonl"}
    assert selected[".claude"].error


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permissions that apply to the user running the tests",
)
def test_folder_without_permissions_does_not_abort_the_walk(tmp_path):
    _touch(tmp_path, ".claude/projects/p/a.jsonl")
    _touch(tmp_path, ".claude/history.jsonl")
    locked = tmp_path / ".claude" / "projects" / "p"
    locked.chmod(0)
    try:
        selected = _selected(_source(tmp_path))
    finally:
        locked.chmod(0o755)

    assert set(selected) == {".claude/projects/p", ".claude/history.jsonl"}
    assert selected[".claude/projects/p"].error


def test_missing_home_fails(tmp_path):
    source = _source(tmp_path / "unmounted")

    with pytest.raises(ArchiveError, match="unmounted"):
        _selected(source)


def test_missing_configured_root_fails(tmp_path):
    _touch(tmp_path, "home/.codex/history.jsonl")
    entry = {"name": "src", "kind": "live", "platform": "linux", "home": str(tmp_path / "home")}
    entry["agents"] = ["codex"]
    old = {"name": "src", "kind": "live", "platform": "linux"}
    old["roots"] = {"claude": str(tmp_path / "gone")}
    source = parse_config({"archive": {"destination": "/d"}, "sources": [entry, old]}).sources[0]

    with pytest.raises(ArchiveError, match="gone"):
        _selected(source)


def test_missing_default_agent_folders_are_skipped(tmp_path):
    _touch(tmp_path, ".codex/history.jsonl")  # no .claude, .gemini, ... at all

    assert set(_selected(_source(tmp_path))) == {".codex/history.jsonl"}


def test_copilot_session_databases_are_snapshots(tmp_path):
    _touch(tmp_path, ".copilot/session-state/abc/session.db")

    selected = _selected(_source(tmp_path))

    assert selected[".copilot/session-state/abc/session.db"].database.mode == "snapshot"


def test_includes_under_an_agent_folder_keep_its_database_rules(tmp_path):
    _touch(tmp_path, ".copilot/data.db")
    _touch(tmp_path, ".codex/state_5.sqlite")
    _touch(tmp_path, ".codex/logs_2.sqlite")
    _touch(tmp_path, ".codex/config.toml")
    source = _source(tmp_path, agents=["claude"], include=[".copilot/**", ".codex/**"])

    selected = _selected(source)

    assert set(selected) == {
        ".copilot/data.db",
        ".codex/state_5.sqlite",
        ".codex/logs_2.sqlite",
        ".codex/config.toml",
    }
    data_db = selected[".copilot/data.db"]
    assert data_db.agent == "copilot-cli"
    assert data_db.database is not None
    assert "accounts.access_token" in data_db.database.blank_columns
    assert selected[".codex/state_5.sqlite"].database.mode == "snapshot"
    assert selected[".codex/logs_2.sqlite"].database.mode == "log"
    assert selected[".codex/config.toml"].database is None


def test_includes_under_an_agent_folder_keep_its_exclusions(tmp_path):
    chat = ".config/Code/User/workspaceStorage/ws1/GitHub.copilot-chat"
    _touch(tmp_path, ".gemini/tmp/abc/chats/session-1.json")
    _touch(tmp_path, ".gemini/tmp/abc/tool-outputs/out.txt")
    _touch(tmp_path, ".gemini/tmp/bin/rg")
    _touch(tmp_path, f"{chat}/transcripts/t.jsonl")
    _touch(tmp_path, f"{chat}/codebase-external.sqlite")
    _touch(tmp_path, ".copilot/data.db-wal")
    source = _source(
        tmp_path, agents=["claude"], include=[".gemini/**", ".config/**", ".copilot/**"]
    )

    assert set(_selected(source)) == {
        ".gemini/tmp/abc/chats/session-1.json",
        f"{chat}/transcripts/t.jsonl",
    }


def test_includes_never_select_files_inside_credential_folders(tmp_path):
    _touch(tmp_path, ".copilot/mcp-oauth-config/abc123.json")
    _touch(tmp_path, ".copilot/mcp-oauth-config/abc123.tokens.json")
    _touch(tmp_path, ".copilot/run/ws.token")
    _touch(tmp_path, ".copilot/run/ws.release.token")
    _touch(tmp_path, ".config/tool/credentials/default.json")
    _touch(tmp_path, ".copilot/session-state/abc/events.jsonl")
    source = _source(tmp_path, agents=["cagelens"], include=[".copilot/**", ".config/**"])

    assert set(_selected(source)) == {".copilot/session-state/abc/events.jsonl"}


def test_unreadable_credential_folder_under_an_include_is_not_an_error(tmp_path, monkeypatch):
    from agent_history.archive import layouts

    _touch(tmp_path, ".copilot/mcp-oauth-config/abc123.json")
    _touch(tmp_path, ".copilot/chats/c.json")
    locked = tmp_path / ".copilot" / "mcp-oauth-config"
    real_scandir = layouts.os.scandir

    def scandir(path):
        if Path(path) == locked:
            raise PermissionError(13, "Permission denied", str(path))
        return real_scandir(path)

    monkeypatch.setattr(layouts.os, "scandir", scandir)
    source = _source(tmp_path, agents=["cagelens"], include=[".copilot/**"])

    assert set(_selected(source)) == {".copilot/chats/c.json"}


def test_default_layouts_keep_project_folders_named_like_credentials(tmp_path):
    # Claude names a project folder after its working folder, which can be any name.
    _touch(tmp_path, ".claude/projects/-home-alex-code-oauth-proxy/s.jsonl")
    _touch(tmp_path, ".claude/projects/-home-alex-code-credentials-api/s.jsonl")

    assert set(_selected(_source(tmp_path))) == {
        ".claude/projects/-home-alex-code-oauth-proxy/s.jsonl",
        ".claude/projects/-home-alex-code-credentials-api/s.jsonl",
    }


def test_an_entry_with_no_agents_selects_only_its_includes(tmp_path):
    _touch(tmp_path, "data/.claude/history.jsonl")
    _touch(tmp_path, "data/notes/n.md")
    entry = {"name": "src", "kind": "live", "platform": "linux", "home": str(tmp_path / "data")}
    entry.update(agents=[], include=["notes/**"])
    source = parse_config({"archive": {"destination": "/d"}, "sources": [entry]}).sources[0]

    assert set(_selected(source)) == {"notes/n.md"}


def _sqlite(root: Path, rel: str, wal: bool = False) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    return path


def test_includes_follow_the_databases_that_layouts_leave_out(tmp_path):
    _sqlite(tmp_path, ".codex/thread_history_1.sqlite")
    _sqlite(tmp_path, ".copilot/repo-metadata-cache.db")
    _sqlite(tmp_path, ".cagelens/metrics.db")
    _sqlite(tmp_path, ".cagelens/backups/metrics.db.20260108-175254")
    _touch(tmp_path, ".cagelens/codex_index.json")
    _touch(tmp_path, ".cagelens/remote_u1_codex/s.jsonl")
    _touch(tmp_path, ".cagelens/remote-cache/h/claude/x.jsonl")
    _touch(tmp_path, ".cagelens/archive-work/staging/f.zst")
    _touch(tmp_path, ".cagelens/config.json")
    _touch(tmp_path, ".codex/history.jsonl")
    _touch(tmp_path, ".copilot/chats/c.json")
    include = [".codex/**", ".copilot/**", ".cagelens/**"]

    selected = _selected(_source(tmp_path, agents=[], include=include))

    assert set(selected) == {
        ".cagelens/config.json",
        ".codex/history.jsonl",
        ".copilot/chats/c.json",
    }


def test_includes_snapshot_any_sqlite_database_no_rule_names(tmp_path):
    _sqlite(tmp_path, ".codex/sqlite/codex-dev.db", wal=True)
    _sqlite(tmp_path, ".copilot/store/index.bin")
    _sqlite(tmp_path, "tools/app/state.sqlite")
    _touch(tmp_path, ".codex/sqlite/notes.db", "not a database")
    _touch(tmp_path, "tools/app/plain.txt", "text")
    include = [".codex/**", ".copilot/**", "tools/**"]

    selected = _selected(_source(tmp_path, agents=[], include=include))

    assert set(selected) == {
        ".codex/sqlite/codex-dev.db",
        ".copilot/store/index.bin",
        "tools/app/state.sqlite",
        ".codex/sqlite/notes.db",
        "tools/app/plain.txt",
    }
    for rel in (".codex/sqlite/codex-dev.db", ".copilot/store/index.bin", "tools/app/state.sqlite"):
        rule = selected[rel].database
        assert rule is not None, rel
        assert (rule.mode, rule.blank_columns) == ("snapshot", ())
    assert selected[".codex/sqlite/notes.db"].database is None
    assert selected["tools/app/plain.txt"].database is None


def test_includes_leave_out_agent_configuration_that_holds_tokens(tmp_path):
    left_out = [
        ".codex/config.toml.bak-20260928-150907",
        ".codex/config.toml~",
        ".codex/.config.toml.un~",
        ".codex/backups/removal-20260827/config.toml",
        ".codex/computer-use/config.json",
        ".codex/log/codex-login.log",
        ".copilot/config.json",
        ".copilot/settings.json",
        ".copilot/logs/process-1790254081843-19836.log",
        ".copilot/logs/extensions/canvas-1790254081843-10532.log",
        ".pi/agent/models.json",
        ".pi/agent/models.json.bak-20260623-140738",
        ".claude/daemon-auth-status.json",
        ".claude/daemon-auth-cooldown",
        "tools/app/auth-status.json",
        "tools/app/login.log",
    ]
    kept = [
        ".codex/hooks.json",
        ".codex/backups/removal-20260827/hooks.json",
        ".copilot/command-history-state.json",
        ".pi/agent/settings.json",
        ".claude/settings.json",
        ".claude/daemon.status.json",
        "tools/app/app.log",
    ]
    for rel in left_out + kept:
        _touch(tmp_path, rel)
    include = [".codex/**", ".copilot/**", ".pi/**", ".claude/**", "tools/**"]

    assert set(_selected(_source(tmp_path, agents=[], include=include))) == set(kept)


def test_includes_inside_agent_folders_follow_the_layouts_folder_rules(tmp_path):
    # Claude names a project folder after its working folder, which can be any name.
    _touch(tmp_path, ".claude/projects/-home-alex-oauth-proxy/s1.jsonl")
    _touch(tmp_path, ".claude/projects/-home-alex-credentials-api/s2.jsonl")
    _touch(tmp_path, ".codex/skills/oauth/SKILL.md")
    # Credential folders that a layout names stay out.
    _touch(tmp_path, ".copilot/mcp-oauth-config/abc123.json")
    _touch(tmp_path, ".codex/mcp-oauth-locks/server-1")
    # Outside agent folders, folder names are still checked.
    _touch(tmp_path, "tools/oauth-proxy/notes.md")
    _touch(tmp_path, "tools/app/notes.md")
    include = [".claude/**", ".codex/**", ".copilot/**", "tools/**"]

    assert set(_selected(_source(tmp_path, agents=[], include=include))) == {
        ".claude/projects/-home-alex-oauth-proxy/s1.jsonl",
        ".claude/projects/-home-alex-credentials-api/s2.jsonl",
        ".codex/skills/oauth/SKILL.md",
        "tools/app/notes.md",
    }


def test_an_include_snapshots_a_database_whose_rows_are_only_in_its_wal(tmp_path):
    # A new WAL database can be empty on disk until its first checkpoint.
    _touch(tmp_path, "tools/app/state.db", "")
    (tmp_path / "tools/app/state.db-wal").write_bytes(b"\x37\x7f\x06\x82" + b"\0" * 28)

    selected = _selected(_source(tmp_path, agents=[], include=["tools/**"]))

    assert set(selected) == {"tools/app/state.db"}
    assert selected["tools/app/state.db"].database.mode == "snapshot"
