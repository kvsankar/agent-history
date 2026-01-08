from __future__ import annotations

import subprocess
from pathlib import Path


def test_project_show_accepts_format_flag(tmp_path: Path):
    """project show should accept --format json from CLI parser."""
    script = Path(__file__).parents[2] / "agent-history"
    proc = subprocess.run(
        ["python3", str(script), "project", "show", "dummy", "--format", "json"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    # Should fail with not found, not with arg parsing error
    assert "not found" in proc.stderr.lower()
