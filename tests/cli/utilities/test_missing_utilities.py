"""Tests for required top-level utility commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.cli import assert_cli_success, run_cli_subprocess

pytestmark = pytest.mark.scope


@pytest.mark.parametrize(
    "args",
    [
        ["install", "--help"],
        ["reset", "--help"],
        ["fetch", "--help"],
    ],
)
def test_utility_commands_exist(args: list[str], tmp_path: Path) -> None:
    result = run_cli_subprocess(
        args,
        env={"HOME": str(tmp_path)},
    )

    assert_cli_success(result, f"Utility command should exist: {' '.join(args)}")


def test_reset_help_uses_positional_target_shape(tmp_path: Path) -> None:
    result = run_cli_subprocess(["reset", "--help"], env={"HOME": str(tmp_path)})

    assert_cli_success(result, "reset help should succeed")
    assert "{all,db,config,cache}" in result.stdout
    assert "Reset target (default: all)" in result.stdout
    assert "--db" not in result.stdout
    assert "--config" not in result.stdout
    assert "--settings" not in result.stdout


@pytest.mark.parametrize("target", ["all", "db", "config", "cache"])
def test_reset_target_help_is_available(target: str, tmp_path: Path) -> None:
    result = run_cli_subprocess(["reset", target, "--help"], env={"HOME": str(tmp_path)})

    assert_cli_success(result, f"reset {target} --help should succeed")
    assert "usage: cagelens reset" in result.stdout
    assert "{all,db,config,cache}" in result.stdout


def test_fetch_help_is_remote_cache_focused(tmp_path: Path) -> None:
    result = run_cli_subprocess(["fetch", "--help"], env={"HOME": str(tmp_path)})

    assert_cli_success(result, "fetch help should succeed")
    assert "Fetch SSH remote sessions into the local cagelens cache." in result.stdout
    assert "It does not fetch local, WSL, Windows, or Claude web sessions." in result.stdout
    assert "-r HOST, --remote HOST" in result.stdout
    assert "--all-remotes" in result.stdout
    assert "--wsl" not in result.stdout
    assert "--windows" not in result.stdout
    assert "--web" not in result.stdout
    assert "--local" not in result.stdout
