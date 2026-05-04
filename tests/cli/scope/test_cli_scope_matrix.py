"""Scope matrix parsing for bounded CLI combinations."""

from __future__ import annotations

import pytest

from agent_history.cli.parser import CLIParser


HOME_SCOPES = [
    ("implicit", []),
    ("home_local", ["--home", "local"]),
    ("home_wsl", ["--home", "wsl:Ubuntu"]),
    ("home_windows", ["--home", "windows"]),
    ("web_flag", ["--web"]),
    ("remote_1", ["-r", "user@host1"]),
    ("remote_2", ["-r", "user@host1", "-r", "user@host2"]),
    ("remote_3", ["-r", "user@host1", "-r", "user@host2", "-r", "user@host3"]),
    ("local_plus_remote", ["--local", "-r", "user@host1"]),
    ("all_homes", ["--ah"]),
    ("all_homes_no_remote", ["--ah", "--no-remote"]),
]

WORKSPACE_SCOPES = [
    ("implicit", []),
    ("all_workspaces", ["--aw"]),
    ("path_1", ["/home/user/project-alpha"]),
    ("name_1", ["-n", "project"]),
    ("project_1", ["--project", "alpha"]),
    ("this_only", ["--this"]),
]

VERB_SUFFIX = {
    "list": [],
    "export": ["-o", "./out"],
    "stats": [],
}


@pytest.mark.parametrize("verb", ["list", "export", "stats"])
@pytest.mark.parametrize("home_name,home_args", HOME_SCOPES)
@pytest.mark.parametrize("ws_name,ws_args", WORKSPACE_SCOPES)
def test_session_scope_matrix_parses(verb, home_name, home_args, ws_name, ws_args) -> None:
    parser = CLIParser()
    args = ["session", verb, *home_args, *ws_args, *VERB_SUFFIX[verb]]
    request = parser.parse(args)

    assert request.resource == "session"
    assert request.verb == verb
