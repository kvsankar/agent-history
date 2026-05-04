"""CLI stats output behavior vs metrics DB expectations."""

import json

from tests.helpers.cli import run_cli_subprocess


def test_cli_stats_reports_token_totals(
    stats_test_home,
    setup_all_stats_fixtures,
    all_stats_expected,
):
    """CLI stats should surface token totals from the synced metrics DB."""
    result = run_cli_subprocess(
        ["session", "stats", "--sync", "--aw", "--format", "json"],
        env=stats_test_home["env"],
        cwd=stats_test_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip(), "Expected JSON stats output"

    stats = json.loads(result.stdout)
    tokens = stats.get("tokens") or {}

    assert tokens.get("input") == all_stats_expected["input_tokens"], "Input tokens mismatch"
    assert tokens.get("output") == all_stats_expected["output_tokens"], "Output tokens mismatch"
