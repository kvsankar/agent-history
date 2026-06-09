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
    ("name_1", ["--glob", "*project*"]),
    ("project_1", ["--project", "alpha"]),
    ("this_only", ["--this"]),
]

VERB_SUFFIX = {
    "list": [],
    "export": ["-o", "./out"],
    "stats": [],
}


def test_bare_parser_prints_help_without_defaulting_to_session_list(capsys) -> None:
    parser = CLIParser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse([])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "usage: cagelens" in output
    assert "COMMAND" in output


@pytest.mark.parametrize("verb", ["list", "export", "stats"])
@pytest.mark.parametrize("home_name,home_args", HOME_SCOPES)
@pytest.mark.parametrize("ws_name,ws_args", WORKSPACE_SCOPES)
def test_session_scope_matrix_parses(verb, home_name, home_args, ws_name, ws_args) -> None:
    parser = CLIParser()
    args = ["session", verb, *home_args, *ws_args, *VERB_SUFFIX[verb]]
    request = parser.parse(args)

    assert request.resource == "session"
    assert request.verb == verb


def test_parent_scope_flags_survive_subcommand_defaults() -> None:
    """Flags before a subcommand should not be overwritten by subparser defaults."""
    parser = CLIParser()

    request = parser.parse(
        [
            "session",
            "--windows",
            "--aw",
            "--agent",
            "codex",
            "--format",
            "json",
            "list",
        ]
    )

    assert request.scope_args.home_type == "windows"
    assert request.scope_args.all_workspaces is True
    assert request.scope_args.agent == "codex"
    assert request.output_args.format == "json"


def test_combined_home_type_flags_are_preserved_as_multiple_homes() -> None:
    """Combined category flags should not collapse to the first flag."""
    parser = CLIParser()

    request = parser.parse(["session", "list", "--wsl", "--windows", "--aw"])

    assert request.scope_args.home_type is None
    assert request.scope_args.home_names == ["wsl", "windows"]


def test_local_can_combine_with_explicit_remote_scope() -> None:
    """--local is documented as combinable with -r/--home."""
    parser = CLIParser()

    request = parser.parse(["session", "list", "--local", "-r", "user@host", "--aw"])

    assert request.scope_args.home_type is None
    assert request.scope_args.home_names == ["remote:user@host", "local"]


def test_home_parent_filter_flags_survive_subcommand_defaults() -> None:
    parser = CLIParser()

    request = parser.parse(["home", "--windows", "list", "--format", "json"])

    assert request.verb_args["windows"] is True
    assert request.output_args.format == "json"
