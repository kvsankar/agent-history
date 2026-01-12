from __future__ import annotations

import json
from pathlib import Path

from tests.helpers.module_loader import load_agent_history


def test_unified_export_writes_header(tmp_path: Path):
    """Unified NDJSON export should prepend header with schema_version 2.0."""
    ah = load_agent_history()
    records = [{"timestamp": "2025-01-01T00:00:00Z", "role": "user", "content": "hi"}]
    out = tmp_path / "out.ndjson"

    ah.write_unified_ndjson(records, out, quiet=True, header=ah._build_unified_header("claude"))  # type: ignore[attr-defined]

    lines = out.read_text().splitlines()
    header = json.loads(lines[0])
    assert header["type"] == "header"
    assert header["schema_version"] == "2.0"
    assert header["agent_types"] == ["claude-code"]
