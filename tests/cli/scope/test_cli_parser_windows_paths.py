"""Tests for CLI parser handling of Windows-style paths."""

from agent_history.cli.parser import CLIParser


def test_session_show_keeps_windows_path() -> None:
    parser = CLIParser()
    session_path = r"C:\Users\Alice\proj\session-001.jsonl"
    request = parser.parse(["session", "show", session_path])

    assert request.verb_args.get("session_id") == session_path
    assert request.scope_args.patterns == []
    assert request.scope_args.name_patterns == []


def test_session_list_windows_path_stays_positional() -> None:
    parser = CLIParser()
    workspace_path = r"C:\Users\Alice\proj"
    request = parser.parse(["session", "list", workspace_path])

    assert request.scope_args.patterns == [workspace_path]
    assert request.scope_args.name_patterns == []


def test_ws_list_windows_path_stays_positional() -> None:
    parser = CLIParser()
    workspace_path = r"C:\Users\Alice\proj"
    request = parser.parse(["ws", "list", workspace_path])

    assert request.scope_args.patterns == [workspace_path]
    assert request.scope_args.name_patterns == []
