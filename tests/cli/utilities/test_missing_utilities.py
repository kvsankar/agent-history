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
