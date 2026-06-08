from __future__ import annotations

import pytest

from agent_history.cli.parser import CLIParser


def test_stats_aliases_expand_to_group_by_dimensions() -> None:
    request = CLIParser().parse(
        [
            "session",
            "stats",
            "--models",
            "--tools",
            "--by-day",
            "--by-workspace",
            "--by",
            "home,agent",
            "--top-ws",
            "all",
            "--human",
        ]
    )

    assert request.verb_args["by"] == [
        "home",
        "agent",
        "model",
        "tool",
        "day",
        "workspace",
    ]
    assert request.verb_args["top_ws"] == "all"
    assert request.output_args.human_readable is True
    assert request.verb_args["human"] is True


def test_stats_top_ws_rejects_non_positive_values() -> None:
    with pytest.raises(SystemExit):
        CLIParser().parse(["session", "stats", "--top-ws", "0"])


def test_top_level_stats_defaults_to_summary() -> None:
    request = CLIParser().parse(["stats"])

    assert request.resource == "stats"
    assert request.verb == "summary"
    assert request.verb_args["stats_mode"] == "summary"
    assert request.verb_args["sync"] is False


def test_top_level_stats_accepts_bare_exact_workspace() -> None:
    request = CLIParser().parse(["stats", "auth", "--by", "workspace"])

    assert request.resource == "stats"
    assert request.verb == "summary"
    assert request.scope_args.patterns == ["auth"]
    assert request.scope_args.name_patterns == []
    assert request.verb_args["by"] == ["workspace"]


def test_top_level_stats_parses_glob_and_regex_workspace_scope() -> None:
    request = CLIParser().parse(
        ["stats", "--glob", "*auth*", "--regex", r"(^|/)api($|/)", "--by", "workspace"]
    )

    assert request.resource == "stats"
    assert request.verb == "summary"
    assert request.scope_args.patterns == []
    assert request.scope_args.glob_patterns == ["*auth*"]
    assert request.scope_args.regex_patterns == [r"(^|/)api($|/)"]
    assert request.verb_args["by"] == ["workspace"]


def test_top_level_stats_rollup_parses_metrics_dimensions_and_limit() -> None:
    request = CLIParser().parse(
        ["stats", "rollup", "--metric", "time", "--by", "project,month", "--top", "5"]
    )

    assert request.resource == "stats"
    assert request.verb == "rollup"
    assert request.verb_args["stats_mode"] == "rollup"
    assert request.verb_args["metric"] == "time"
    assert request.verb_args["by"] == ["project", "month"]
    assert request.verb_args["top"] == 5


def test_top_level_stats_rollup_rejects_non_positive_top() -> None:
    with pytest.raises(SystemExit):
        CLIParser().parse(["stats", "rollup", "--top", "0"])


def test_top_level_stats_help_stays_on_parent_parser(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        CLIParser().parse(["stats", "--help"])

    output = capsys.readouterr().out
    assert exc_info.value.code == 0
    assert "usage: cagelens stats" in output
    assert "rollup" in output
