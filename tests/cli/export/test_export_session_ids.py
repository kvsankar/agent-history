"""Session export by explicit session IDs."""

from pathlib import Path

from tests.helpers.cli import run_cli_subprocess


def test_session_export_by_single_id(current_workspace_setup, tmp_path: Path) -> None:
    output_dir = tmp_path / "exports_by_id"
    output_dir.mkdir()

    session_id = current_workspace_setup["sessions"][0]
    result = run_cli_subprocess(
        ["session", "export", "--session", session_id, "-o", str(output_dir), "--force"],
        env=current_workspace_setup["env"],
        cwd=current_workspace_setup["workspace_dir"],
    )

    assert result.returncode == 0, result.stderr
    md_files = list(output_dir.rglob("*.md"))
    assert len(md_files) == 1, "Expected a single exported session"


def test_session_export_by_multiple_ids(current_workspace_setup, tmp_path: Path) -> None:
    output_dir = tmp_path / "exports_by_ids"
    output_dir.mkdir()

    session_ids = current_workspace_setup["sessions"]
    joined = ",".join(session_ids)
    result = run_cli_subprocess(
        ["session", "export", "--session", joined, "-o", str(output_dir), "--force"],
        env=current_workspace_setup["env"],
        cwd=current_workspace_setup["workspace_dir"],
    )

    assert result.returncode == 0, result.stderr
    md_files = list(output_dir.rglob("*.md"))
    assert len(md_files) == len(session_ids), "Expected exports for each session ID"


def test_session_export_missing_id_fails(current_workspace_setup, tmp_path: Path) -> None:
    output_dir = tmp_path / "exports_missing_id"
    output_dir.mkdir()

    result = run_cli_subprocess(
        ["session", "export", "--session", "missing-session-id", "-o", str(output_dir)],
        env=current_workspace_setup["env"],
        cwd=current_workspace_setup["workspace_dir"],
    )

    assert result.returncode == 1, "Expected failure for missing session ID"
    assert not list(output_dir.rglob("*.md")), "No exports expected for missing session ID"
