"""Gemini index support checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers.cli import assert_cli_success, run_cli_subprocess
from tests.helpers.gap_helpers import ensure_config_env, load_json_output


pytestmark = pytest.mark.scope


def test_gemini_index_rebuild_is_implemented(tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path)}
    env = ensure_config_env(env, tmp_path / ".agent-history")
    result = run_cli_subprocess(
        ["gemini-index", "--rebuild"],
        env=env,
    )

    assert_cli_success(result, "gemini-index --rebuild should succeed")
    payload = load_json_output(result)
    assert payload.get("status") != "not implemented", "Expected rebuild to be implemented"
