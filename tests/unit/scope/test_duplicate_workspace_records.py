"""Two workspace names for the same folder must not list its sessions twice.

On native Windows the Claude folder name and Codex's recorded path for
C:\\Users\\alex both resolve to the workspace /mnt/c/Users/alex, and each
record collected the same Codex sessions.
"""

from agent_history.scope.resolver import dedupe_session_records
from agent_history.scope.types import ConcreteRecord


def _record(workspace, files, home="local"):
    return ConcreteRecord(
        home=home, workspace=workspace, sessions=[{"file": f, "agent": "codex"} for f in files]
    )


def test_sessions_listed_under_the_same_workspace_twice_are_kept_once():
    scope = [
        _record("/mnt/c/Users/alex", ["a", "b"]),
        _record("/mnt/c/Users/alex", ["a", "b", "c"]),
    ]

    result = dedupe_session_records(scope)

    assert sorted(s["file"] for r in result for s in r.sessions) == ["a", "b", "c"]


def test_other_workspaces_and_homes_are_untouched():
    scope = [
        _record("/mnt/c/Users/alex", ["a"]),
        _record("/mnt/c/Users/alex/.ssh", ["a"]),
        _record("/mnt/c/Users/alex", ["a"], home="windows:alex"),
    ]

    result = dedupe_session_records(scope)

    assert [len(r.sessions) for r in result] == [1, 1, 1]
