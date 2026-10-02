"""Tests for per-agent file selection."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from agent_history.archive.config import parse_config
from agent_history.archive.layouts import (
    archive_file_path,
    iter_source_files,
    original_path,
)


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
