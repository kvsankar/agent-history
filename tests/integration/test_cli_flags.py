import json
import subprocess
import sys
from pathlib import Path


def _write_session(path: Path) -> None:
    messages = [
        {
            "type": "user",
            "message": {"role": "user", "content": "Hello"},
            "timestamp": "2025-01-01T00:00:00Z",
            "uuid": "u1",
            "sessionId": "s1",
        },
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]},
            "timestamp": "2025-01-01T00:01:00Z",
            "uuid": "a1",
            "sessionId": "s1",
        },
    ]
    path.write_text("\n".join(json.dumps(m) for m in messages), encoding="utf-8")


def test_cli_export_with_flags(tmp_path):
    jsonl = tmp_path / "session.jsonl"
    outdir = tmp_path / "out"
    _write_session(jsonl)

    cmd = [
        sys.executable,
        "agent-history",
        "export",
        str(jsonl),
        "-o",
        str(outdir),
        "--minimal",
        "--flat",
        "--split",
        "1",
        "--force",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    stdout_path = Path(result.stdout.strip()) if result.stdout.strip() else None
    md_candidates = list(outdir.glob("*.md"))
    if stdout_path and stdout_path.exists():
        md_candidates.append(stdout_path)
    assert md_candidates, f"no markdown output created; stdout={result.stdout} stderr={result.stderr}"


def test_cli_export_missing_file_returns_error(tmp_path):
    outdir = tmp_path / "out"
    cmd = [
        sys.executable,
        "agent-history",
        "export",
        str(tmp_path / "missing.jsonl"),
        "-o",
        str(outdir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode != 0
    assert "not found" in (result.stderr or result.stdout).lower()
