"""Helper utilities for gap-focused tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_json_output(result: Any) -> Any:
    output = (getattr(result, "stdout", "") or "").strip()
    assert output, f"Expected JSON output, got empty stdout:\nstderr: {result.stderr}"
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        pass

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for candidate in reversed(lines):
        if candidate.startswith(("{", "[")):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    raise AssertionError(f"Expected JSON output, got:\n{output}")


def assert_exported_to_dir(result: Any, output_dir: Path) -> None:
    payload = load_json_output(result)
    assert payload.get("exported", 0) > 0, "Expected at least one exported session"
    reported_dir = payload.get("output_dir")
    assert reported_dir, "Expected export_result to include output_dir"
    assert Path(reported_dir) == output_dir, "Expected output_dir to match export result"


def ensure_config_env(env: Dict[str, str], config_dir: Path) -> Dict[str, str]:
    config_dir.mkdir(parents=True, exist_ok=True)
    updated = env.copy()
    updated["AGENT_HISTORY_CONFIG_DIR"] = str(config_dir)
    return updated
