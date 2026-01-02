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
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    stdout_path = Path(result.stdout.strip()) if result.stdout.strip() else None
    md_candidates = list(outdir.glob("*.md"))
    if stdout_path and stdout_path.exists():
        md_candidates.append(stdout_path)
    assert (
        md_candidates
    ), f"no markdown output created; stdout={result.stdout} stderr={result.stderr}"


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
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "not found" in (result.stderr or result.stdout).lower()


def test_cli_export_with_source_flag(tmp_path):
    """Test that --source flag copies source JSONL alongside markdown."""
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
        "--source",
        "--force",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    # Check that both .md and .jsonl files were created
    md_files = list(outdir.glob("*.md"))
    jsonl_files = list(outdir.glob("*.jsonl"))

    assert md_files, f"no markdown output created; stdout={result.stdout}"
    assert jsonl_files, f"no jsonl copy created; stdout={result.stdout}"

    # Verify the JSONL content matches original
    original_content = jsonl.read_text(encoding="utf-8")
    copied_content = jsonl_files[0].read_text(encoding="utf-8")
    assert original_content == copied_content, "JSONL content mismatch"


def test_cli_export_source_flag_with_workspace(tmp_path, monkeypatch):
    """Test --source flag with workspace pattern export."""
    # Create a mock projects directory structure
    projects_dir = tmp_path / ".claude" / "projects" / "-test-workspace"
    projects_dir.mkdir(parents=True)
    jsonl = projects_dir / "abc123.jsonl"
    _write_session(jsonl)

    outdir = tmp_path / "out"

    # Patch home directory (HOME for Unix, USERPROFILE for Windows)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    cmd = [
        sys.executable,
        "agent-history",
        "export",
        "test-workspace",
        "-o",
        str(outdir),
        "--source",
        "--force",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    # Find all output files recursively
    md_files = list(outdir.rglob("*.md"))
    jsonl_files = list(outdir.rglob("*.jsonl"))

    assert md_files, f"no markdown output; stdout={result.stdout} stderr={result.stderr}"
    assert jsonl_files, f"no jsonl copy; stdout={result.stdout} stderr={result.stderr}"
