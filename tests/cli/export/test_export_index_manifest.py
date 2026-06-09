"""Tests index.md manifest generation for multi-home exports."""

from pathlib import Path
from typing import Any, Dict

import pytest

from tests.helpers.cli import assert_cli_success, run_cli_subprocess
from tests.helpers.session_builders import ClaudeSessionBuilder

pytestmark = pytest.mark.v1


def test_export_all_homes_generates_manifest(
    isolated_home: Dict[str, Any], setup_golden_fixtures: Dict[str, Path]
) -> None:
    """session export --ah should write index.md with workspace and session totals."""
    output_dir = isolated_home["path"] / "exports_index"
    output_dir.mkdir()

    env = dict(isolated_home["env"])
    # Skip WSL/Windows/remote validation in the test environment.
    env["AGENT_HISTORY_HOME"] = str(isolated_home["path"])

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "--ah",
            "--aw",
            "--no-wsl",
            "--no-windows",
            "--no-remote",
            "-o",
            str(output_dir),
            "--force",
        ],
        env=env,
        cwd=isolated_home["path"],
    )
    assert_cli_success(result, "session export --ah should succeed")

    index_file = output_dir / "index.md"
    assert index_file.exists(), "index.md manifest should be generated for multi-home export"

    md_files = [p for p in output_dir.glob("**/*.md") if p.name != "index.md"]
    assert md_files, "export should create markdown files"

    workspace_counts: Dict[str, int] = {}
    for md_file in md_files:
        # Export-all should organize sessions under workspace subdirectories.
        assert md_file.parent != output_dir, "sessions should be grouped by workspace"
        workspace = str(md_file.parent.relative_to(output_dir))
        workspace_counts[workspace] = workspace_counts.get(workspace, 0) + 1

    content = index_file.read_text(encoding="utf-8")
    lines = content.splitlines()

    assert f"**Total Workspaces:** {len(workspace_counts)}" in content
    assert f"**Total Sessions:** {len(md_files)}" in content
    assert any(
        line.startswith("- **") for line in lines
    ), "Sources section should list session counts"
    assert any(
        line.startswith("### ") for line in lines
    ), "Workspace section should include headings"

    for workspace, count in workspace_counts.items():
        assert (
            f"### {workspace} ({count} sessions)" in content
        ), f"Workspace {workspace} should be summarized in index.md"


@pytest.mark.parametrize(
    ("format_args", "suffix"),
    [
        (["--format", "html"], ".html"),
        (["--json"], ".ndjson"),
    ],
)
def test_export_manifest_counts_non_markdown_sessions(
    isolated_home: Dict[str, Any],
    format_args: list[str],
    suffix: str,
) -> None:
    for workspace, session_id in [
        ("-home-user-html-manifest-one", "html-manifest-one"),
        ("-home-user-html-manifest-two", "html-manifest-two"),
    ]:
        builder = ClaudeSessionBuilder(workspace=workspace, session_id=session_id)
        builder.add_user_message(f"Hello {session_id}")
        builder.add_assistant_message("Done")
        builder.write_to(isolated_home["claude_dir"])

    output_dir = isolated_home["path"] / "exports_html_index"

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "--aw",
            *format_args,
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )
    assert_cli_success(result, "All-workspace export should succeed")

    exported_files = list(output_dir.rglob(f"*{suffix}"))
    assert len(exported_files) == 2

    content = (output_dir / "index.md").read_text(encoding="utf-8")
    assert "**Total Workspaces:** 2" in content
    assert "**Total Sessions:** 2" in content
    assert "### -home-user-html-manifest-one (1 sessions)" in content
    assert "### -home-user-html-manifest-two (1 sessions)" in content
