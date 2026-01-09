from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_project_show_rejects_format_flag(tmp_path: Path):
    """project show should reject --format flag (show commands don't support formats)."""
    script = Path(__file__).parents[2] / "agent-history"
    proc = subprocess.run(
        [sys.executable, str(script), "project", "show", "dummy", "--format", "json"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    # Should fail with argument parsing error
    assert proc.returncode != 0
    assert "unrecognized arguments" in proc.stderr.lower() or "error" in proc.stderr.lower()
