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


def test_install_help_is_agent_skill_generic(tmp_path: Path) -> None:
    result = run_cli_subprocess(["install", "--help"], env={"HOME": str(tmp_path)})

    assert_cli_success(result, "install help should succeed")
    assert "Install the CLI wrapper and agent skill packages." in result.stdout
    assert "Custom agent skill install directory" in result.stdout
    assert "Skip agent skill install" in result.stdout
    assert "Skip agent settings update" in result.stdout
    assert "--agent {auto,claude,codex,gemini,pi}" in result.stdout
    assert "Claude skill" not in result.stdout
    assert "Claude settings" not in result.stdout


def test_install_creates_selected_agent_skill_package(tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path), "CODEX_HOME": str(tmp_path / ".codex-custom")}
    result = run_cli_subprocess(
        ["install", "--skip-cli", "--skip-settings", "--agent", "codex"],
        env=env,
    )

    assert_cli_success(result, "install should create selected agent skill package")
    target = tmp_path / ".codex-custom" / "skills" / "cagelens"
    assert (target / "SKILL.md").is_file()
    assert (target / "cagelens").is_file()
    assert not (tmp_path / ".claude" / "skills" / "cagelens").exists()
    assert not (tmp_path / ".gemini" / "skills" / "cagelens").exists()
    assert not (tmp_path / ".pi" / "agent" / "skills" / "cagelens").exists()


def test_install_creates_all_agent_skill_packages_by_default(tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path), "CODEX_HOME": str(tmp_path / ".codex-custom")}
    result = run_cli_subprocess(["install", "--skip-cli", "--skip-settings"], env=env)

    assert_cli_success(result, "install should create all agent skill packages")
    for target in [
        tmp_path / ".claude" / "skills" / "cagelens",
        tmp_path / ".codex-custom" / "skills" / "cagelens",
        tmp_path / ".gemini" / "skills" / "cagelens",
        tmp_path / ".pi" / "agent" / "skills" / "cagelens",
    ]:
        assert (target / "SKILL.md").is_file()
        assert (target / "cagelens").is_file()


def test_install_custom_skill_dir_overrides_agent_targets(tmp_path: Path) -> None:
    custom = tmp_path / "custom-skill"
    result = run_cli_subprocess(
        ["install", "--skip-cli", "--skip-settings", "--skill-dir", str(custom)],
        env={"HOME": str(tmp_path)},
    )

    assert_cli_success(result, "install should honor custom skill directory")
    assert (custom / "SKILL.md").is_file()
    assert (custom / "cagelens").is_file()
    assert not (tmp_path / ".claude" / "skills" / "cagelens").exists()


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
