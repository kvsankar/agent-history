"""Remote Codex listing commands must work in shells whose echo expands escapes.

Codex writes its system instructions into the session_meta line, so that line
holds JSON escapes such as ``\\n`` after the cwd. dash (``/bin/sh`` on Debian
and Ubuntu) and zsh (the macOS login shell) expand those escapes in ``echo``,
which split the extracted cwd over many lines and matched no workspace.
"""

import json
import os
import shutil
import subprocess

import pytest

from agent_history.backends.registry import get_backend

SHELLS = [shell for shell in ("dash", "zsh", "bash") if shutil.which(shell)]


def _write_session(home, cwd):
    day_dir = home / ".codex" / "sessions" / "2026" / "07" / "19"
    day_dir.mkdir(parents=True)
    meta = {
        "timestamp": "2026-07-19T00:00:00Z",
        "type": "session_meta",
        "payload": {
            "id": "s-1",
            "cwd": cwd,
            "base_instructions": {"text": '# Heading\n\nSome text with \\t and "quotes".\n'},
        },
    }
    session = day_dir / "rollout-2026-07-19T00-00-00-s-1.jsonl"
    # Codex writes compact JSON with no space after the colon.
    session.write_text(json.dumps(meta, separators=(",", ":")) + "\n", encoding="utf-8")
    return session


def _run(shell, command, home):
    env = dict(os.environ, HOME=str(home))
    result = subprocess.run(
        [shell, "-c", command], capture_output=True, text=True, env=env, check=False
    )
    return result.stdout


@pytest.mark.parametrize("shell", SHELLS)
def test_remote_codex_session_listing_matches_the_workspace(tmp_path, shell):
    session = _write_session(tmp_path, "/Users/test/project")
    command = get_backend("codex").remote_list_sessions_command("/Users/test/project")

    lines = [line for line in _run(shell, command, tmp_path).splitlines() if line]

    assert len(lines) == 1
    path, _size, _mtime, _count, workspace = lines[0].split("|")
    assert path == str(session)
    assert workspace == "/Users/test/project"


@pytest.mark.parametrize("shell", SHELLS)
def test_remote_codex_workspace_listing_prints_only_the_cwd(tmp_path, shell):
    _write_session(tmp_path, "/Users/test/project")
    command = get_backend("codex").remote_list_workspaces_command()

    lines = [line for line in _run(shell, command, tmp_path).splitlines() if line]

    assert lines == ["/Users/test/project"]
