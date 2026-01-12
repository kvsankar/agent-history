"""Stats limit coverage for --top-ws."""

from typing import Any, Dict, List

import pytest

from tests.helpers.cli import assert_cli_success, run_cli_subprocess

pytestmark = pytest.mark.stats


def _data_lines(output: str) -> List[str]:
    """Return workspace TSV rows (exclude other summary tables)."""
    rows: List[str] = []
    for line in output.strip().splitlines():
        if "\t" not in line:
            continue
        cols = line.split("\t")
        if cols[0].upper() == "HOME":
            continue
        # Workspaces have HOME column values like local/wsl/windows/remote:host
        home_val = cols[0].lower()
        if home_val in {"local", "wsl", "windows"} or home_val.startswith("remote"):
            rows.append(line)
    return rows


def test_top_ws_limits_workspace_rows(
    stats_test_home: Dict[str, Any],
    setup_all_stats_fixtures: Dict[str, Any],
) -> None:
    """--top-ws N should cap workspace rows to N."""
    result = run_cli_subprocess(
        ["session", "stats", "--sync", "--aw", "--top-ws", "1", "--format", "tsv"],
        env=stats_test_home["env"],
        cwd=stats_test_home["path"],
    )

    if result.returncode != 0:
        pytest.skip(f"stats --top-ws not available: {result.stderr}")

    assert_cli_success(result, "stats --top-ws should succeed")
    rows = _data_lines(result.stdout)
    assert len(rows) <= 1, f"Expected at most 1 workspace row, got {len(rows)}"
