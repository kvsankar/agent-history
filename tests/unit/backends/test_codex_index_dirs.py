"""The Codex workspace index tracks each sessions folder separately.

The index used one "last scanned" date for every folder. After the local
folder was scanned, a second folder such as Windows' ~/.codex/sessions was
only scanned for today's date, so its older sessions were never indexed and
every listing reopened each of their files.
"""

import json

from agent_history.backends import codex


def _rollout(sessions_dir, day, name, cwd):
    folder = sessions_dir / day
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"rollout-{name}.jsonl"
    path.write_text(
        json.dumps(
            {
                "type": "session_meta",
                "timestamp": "2026-03-01T00:00:00Z",
                "payload": {"id": name, "cwd": cwd},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_a_second_sessions_folder_is_fully_indexed(tmp_path, monkeypatch):
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / "config"))
    local = tmp_path / "local" / "sessions"
    windows = tmp_path / "windows" / "sessions"
    _rollout(local, "2026/03/01", "a", "/home/user/a")
    old = _rollout(windows, "2026/03/02", "b", "/mnt/c/projects/b")

    codex.codex_ensure_index_updated(local)
    sessions_map = codex.codex_ensure_index_updated(windows)

    assert str(old) in sessions_map
    assert sessions_map[str(old)]


def test_files_found_while_scanning_are_added_to_the_index(tmp_path, monkeypatch):
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / "config"))
    windows = tmp_path / "windows" / "sessions"
    path = _rollout(windows, "2026/03/02", "b", "/mnt/c/projects/b")

    codex.codex_scan_sessions(sessions_dir=windows, skip_message_count=True)

    assert str(path) in codex.codex_load_index()["sessions"]


def test_stale_check_only_touches_the_folder_being_scanned(tmp_path, monkeypatch):
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / "config"))
    local = tmp_path / "local" / "sessions"
    windows = tmp_path / "windows" / "sessions"
    _rollout(local, "2026/03/01", "a", "/home/user/a")
    _rollout(windows, "2026/03/02", "b", "/mnt/c/projects/b")
    codex.codex_ensure_index_updated(local)
    codex.codex_ensure_index_updated(windows)

    checked = []
    real_exists = codex.Path.exists

    def spy(self, *args, **kwargs):
        checked.append(str(self))
        return real_exists(self, *args, **kwargs)

    monkeypatch.setattr(codex.Path, "exists", spy)
    codex.codex_ensure_index_updated(local)

    assert not [path for path in checked if str(windows) in path]


def test_one_process_checks_a_folder_for_stale_entries_once(tmp_path, monkeypatch):
    """Listing calls the index once per workspace; re-checking every file each time
    made Windows listings take tens of minutes over /mnt/c."""
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / "config"))
    windows = tmp_path / "windows" / "sessions"
    _rollout(windows, "2026/03/02", "b", "/mnt/c/projects/b")
    codex.codex_ensure_index_updated(windows)

    calls = []
    real = codex._remove_stale_entries
    monkeypatch.setattr(
        codex, "_remove_stale_entries", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    first = codex.codex_ensure_index_updated(windows)
    second = codex.codex_ensure_index_updated(windows)

    assert len(calls) <= 1
    assert first == second


def test_windows_workspaces_match_their_canonical_keys():
    """Scope resolution looks workspaces up by their canonical key (/mnt/c/...),
    while Codex on native Windows records C:\\... paths, so no Codex session
    was found for any workspace."""
    assert codex._matches_workspace_pattern("C:\\Users\\alex", "/mnt/c/Users/alex")
    assert codex._matches_workspace_pattern(
        "C:\\alex\\projects\\ledger", "/mnt/c/alex/projects/ledger"
    )
    assert not codex._matches_workspace_pattern("C:\\alex\\projects\\ledger", "/mnt/c/other")


def test_scan_finds_windows_sessions_by_canonical_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CAGELENS_CONFIG_DIR", str(tmp_path / "config"))
    sessions_dir = tmp_path / "sessions"
    _rollout(sessions_dir, "2026/03/02", "w", "C:\\alex\\projects\\ledger")

    found = codex.codex_scan_sessions(
        pattern="/mnt/c/alex/projects/ledger", sessions_dir=sessions_dir, skip_message_count=True
    )

    assert len(found) == 1
