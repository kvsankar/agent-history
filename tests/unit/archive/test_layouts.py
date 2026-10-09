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


@pytest.mark.parametrize(
    "rel_path",
    [
        ".claude/projects/-home-alex-shop/s1/subagents/agent-acompact-1.jsonl",
        ".claude/projects/-home-alex-shop/s1/subagents/workflows/wf_1/agent-acompact-2.jsonl",
    ],
)
def test_a_claude_compaction_transcript_is_not_read_for_sessions(rel_path):
    assert session_target(rel_path, "linux") is None


def test_a_claude_compaction_transcript_is_still_archived(tmp_path):
    rel = ".claude/projects/-home-alex-shop/s1/subagents/agent-acompact-1.jsonl"
    _touch(tmp_path, rel)

    assert rel in _selected(_source(tmp_path))


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

    assert set(_selected(_source(tmp_path))) == set()


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


def test_mcp_configurations_are_never_selected(tmp_path):
    _touch(tmp_path, ".gemini/antigravity/mcp_config.json")
    _touch(tmp_path, ".gemini/antigravity/conversations/c1.pb")
    _touch(tmp_path, ".copilot/mcp-config.json")
    _touch(tmp_path, ".config/Code/User/mcp.json")

    selected = _selected(_source(tmp_path))

    assert set(selected) == {".gemini/antigravity/conversations/c1.pb"}


def test_config_exclude_narrows_the_layouts(tmp_path):
    _touch(tmp_path, ".claude/projects/p/a.jsonl")
    _touch(tmp_path, ".claude/projects/q/b.jsonl")
    source = _source(tmp_path, exclude=[".claude/projects/q/**"])

    assert set(_selected(source)) == {".claude/projects/p/a.jsonl"}


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


@pytest.mark.skipif(
    os.name == "nt", reason="creating symlinks needs Developer Mode or administrator rights"
)
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


def test_default_layouts_keep_project_folders_named_like_credentials(tmp_path):
    # Claude names a project folder after its working folder, which can be any name.
    _touch(tmp_path, ".claude/projects/-home-alex-code-oauth-proxy/s.jsonl")
    _touch(tmp_path, ".claude/projects/-home-alex-code-credentials-api/s.jsonl")

    assert set(_selected(_source(tmp_path))) == {
        ".claude/projects/-home-alex-code-oauth-proxy/s.jsonl",
        ".claude/projects/-home-alex-code-credentials-api/s.jsonl",
    }


def _sqlite(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    return path


# Files in every Linux agent folder: some the layouts select, some they leave out.
_IN_AGENT_FOLDERS = (
    ".claude/projects/p/a.jsonl",
    ".claude/projects/-home-alex-oauth-proxy/s.jsonl",
    ".claude/settings.json",
    ".claude/plugins/x/notes.md",
    ".codex/hooks.json",
    ".codex/skills/oauth/SKILL.md",
    ".gemini/tmp/abc/chats/session-1.json",
    ".gemini/tmp/abc/tool-outputs/out.json",
    ".pi/agent/settings.json",
    ".pi/settings.json",
    ".copilot/session-state/abc/events.jsonl",
    ".copilot/command-history-state.json",
    ".config/Code/User/settings.json",
    ".config/Code/User/workspaceStorage/w/chatSessions/c.json",
    ".vscode-server/data/User/globalStorage/x.json",
    ".cagelens/config.json",
    ".cagelens/codex_index.json",
    ".agent-history/aliases.json",
)
_DATABASES_IN_AGENT_FOLDERS = (
    ".codex/state_5.sqlite",
    ".codex/logs_2.sqlite",
    ".codex/thread_history_1.sqlite",
    ".copilot/data.db",
    ".copilot/repo-metadata-cache.db",
    ".cagelens/metrics.db",
)
_OUTSIDE_AGENT_FOLDERS = (
    "notes/n.json",
    ".config/tool/settings.json",
    ".vscode-server/extensions/e/package.json",
    # Other tools' settings and credentials, which no layout selects.
    ".claude.json",
    ".env",
    ".ssh/id_x",
    ".docker/config.json",
)


def _fill_home(home: Path) -> None:
    for rel in _IN_AGENT_FOLDERS + _OUTSIDE_AGENT_FOLDERS:
        _touch(home, rel)
    for rel in _DATABASES_IN_AGENT_FOLDERS:
        _sqlite(home, rel)
    _sqlite(home, "tools/app/state.sqlite")


def test_the_default_layouts_select_only_agent_files_in_a_full_home(tmp_path):
    _fill_home(tmp_path)

    items = list(iter_source_files(_source(tmp_path)))

    selected = {item.rel_path: item for item in items}
    assert len(items) == len(selected)  # each path once
    assert set(selected) == {
        ".claude/projects/p/a.jsonl",
        ".claude/projects/-home-alex-oauth-proxy/s.jsonl",
        ".gemini/tmp/abc/chats/session-1.json",
        ".copilot/session-state/abc/events.jsonl",
        ".config/Code/User/workspaceStorage/w/chatSessions/c.json",
        ".cagelens/config.json",
        ".agent-history/aliases.json",
        ".codex/state_5.sqlite",
        ".codex/logs_2.sqlite",
        ".copilot/data.db",
    }
    assert selected[".copilot/data.db"].agent == "copilot-cli"
    assert "accounts.access_token" in selected[".copilot/data.db"].database.blank_columns
    assert selected[".codex/logs_2.sqlite"].database.mode == "log"


def test_a_roots_override_inside_the_home_replaces_the_agent_folder(tmp_path):
    copy = tmp_path / "old" / "claude-copy"
    _touch(copy, "projects/p/a.jsonl")
    _touch(copy, "settings.json")
    _touch(tmp_path, "old/notes.md")
    _touch(tmp_path, ".claude/projects/p/home.jsonl")
    source = _source(tmp_path, roots={"claude": str(copy)})

    selected = _selected(source)

    assert set(selected) == {".claude/projects/p/a.jsonl"}
    assert selected[".claude/projects/p/a.jsonl"].path == copy / "projects/p/a.jsonl"
