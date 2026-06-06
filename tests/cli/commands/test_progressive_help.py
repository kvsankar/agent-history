"""Progressive CLI help tests."""

from tests.helpers.cli import assert_cli_success, run_cli_subprocess


def test_top_level_help_points_to_next_help_and_common_commands() -> None:
    result = run_cli_subprocess(["--help"])

    assert_cli_success(result, "top-level help should succeed")
    assert "Progressive help:" in result.stdout
    assert "Common commands:" in result.stdout
    assert "Scope shortcuts:" in result.stdout
    assert "cagelens ws --help" in result.stdout
    assert "cagelens session --help" in result.stdout
    assert "cagelens ws                     List all local workspaces with counts" in result.stdout


def test_workspace_help_explains_default_output_and_next_help() -> None:
    result = run_cli_subprocess(["ws", "--help"])

    assert_cli_success(result, "workspace help should succeed")
    assert "Default behavior:" in result.stdout
    assert "cagelens ws lists all workspaces in the selected homes." in result.stdout
    assert "Output columns: HOME, WORKSPACE, SESSIONS, STATUS, MODIFIED." in result.stdout
    assert "Next help:" in result.stdout
    assert "cagelens ws list --help" in result.stdout


def test_session_list_help_explains_scope_and_columns() -> None:
    result = run_cli_subprocess(["session", "list", "--help"])

    assert_cli_success(result, "session list help should succeed")
    assert "Default behavior:" in result.stdout
    assert "current workspace or auto-detected project" in result.stdout
    assert "Output columns: AGENT, HOME, WORKSPACE, FILE, MESSAGES, MODIFIED." in result.stdout
    assert "cagelens session list --aw --format json" in result.stdout
