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


def test_stats_help_points_to_monthly_time_rollups() -> None:
    result = run_cli_subprocess(["stats", "--help"])

    assert_cli_success(result, "stats help should succeed")
    assert "Stats modes:" in result.stdout
    assert "cagelens stats rollup --metric time --by month" in result.stdout
    assert "cagelens stats rollup --metric time --by project,month" in result.stdout
    assert "Summary flags such as --time expand the dashboard." in result.stdout


def test_stats_rollup_help_explains_time_metric_and_month_dimension() -> None:
    result = run_cli_subprocess(["stats", "rollup", "--help"])

    assert_cli_success(result, "stats rollup help should succeed")
    assert "Rollup examples:" in result.stdout
    assert "cagelens stats rollup --metric time --by month" in result.stdout
    assert "project/proj, month" in result.stdout
    assert "cagelens stats rollup --metric tokens --by ws,month" in result.stdout
    assert "cagelens stats rollup --metric tokens --by ws,month --raw --no-total" in result.stdout
    assert "Not needed for rollups; use --metric time" in result.stdout


def test_export_help_prefers_output_flag_and_exact_workspace_matching() -> None:
    result = run_cli_subprocess(["session", "export", "--help"])

    assert_cli_success(result, "session export help should succeed")
    assert "Prefer -o DIR for export destination." in result.stdout
    assert "Positional workspace/target arguments" in result.stdout
    assert 'cagelens session export --glob "*auth*" -o ./exports' in result.stdout


def test_project_add_help_explains_exact_vs_glob_matching() -> None:
    result = run_cli_subprocess(["project", "add", "--help"])

    assert_cli_success(result, "project add help should succeed")
    assert "Positional workspace arguments are exact paths or IDs." in result.stdout
    assert 'cagelens project add myproj --glob "*auth*" --dry-run' in result.stdout


def test_gemini_index_help_shows_add_examples() -> None:
    result = run_cli_subprocess(["gemini-index", "--help"])

    assert_cli_success(result, "gemini-index help should succeed")
    assert "cagelens gemini-index --add" in result.stdout
    assert "cagelens gemini-index --add ~/projects/myapp" in result.stdout


def test_reset_help_explains_targets_and_raw_files() -> None:
    result = run_cli_subprocess(["reset", "--help"])

    assert_cli_success(result, "reset help should succeed")
    assert "Targets:" in result.stdout
    assert "Raw agent session files are not changed." in result.stdout
    assert "cagelens reset db -y" in result.stdout
