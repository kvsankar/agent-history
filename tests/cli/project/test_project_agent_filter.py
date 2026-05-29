"""Project command agent-filter behavior."""

from __future__ import annotations

import json

from tests.helpers.cli import run_cli_subprocess
from tests.helpers.gap_helpers import load_json_output
from tests.helpers.session_builders import ClaudeSessionBuilder, CodexSessionBuilder


def _write_mixed_agent_project(isolated_home, project_name: str = "filterproj") -> str:
    workspace = "/home/user/projects/filter-target"
    encoded_workspace = "-home-user-projects-filter-target"

    claude = ClaudeSessionBuilder(workspace=encoded_workspace, session_id="claude-filter-session")
    claude.add_user_message("Hello Claude")
    claude.add_assistant_message("Claude response")
    claude.write_to(isolated_home["claude_dir"])

    codex = CodexSessionBuilder(session_id="codex-filter-session", cwd=workspace)
    codex.add_user_message("Hello Codex")
    codex.add_assistant_message("Codex response")
    codex.write_to(isolated_home["codex_dir"])

    config_file = isolated_home["history_dir"] / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "version": 2,
                "homes": [],
                "sources": [],
                "projects": {project_name: {"local": [workspace]}},
            }
        ),
        encoding="utf-8",
    )
    return project_name


def test_project_export_accepts_agent_filter(isolated_home):
    project_name = _write_mixed_agent_project(isolated_home)
    output_dir = isolated_home["path"] / "project-agent-export"

    result = run_cli_subprocess(
        ["project", "export", project_name, "--agent", "codex", "--force", "-o", str(output_dir)],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    md_files = sorted(output_dir.rglob("*.md"))
    assert len(md_files) == 1
    content = md_files[0].read_text(encoding="utf-8")
    assert "# Codex Conversation" in content
    assert "Codex response" in content
    assert "Claude response" not in content


def test_project_stats_accepts_agent_filter(isolated_home):
    project_name = _write_mixed_agent_project(isolated_home)

    result = run_cli_subprocess(
        ["project", "stats", project_name, "--agent", "codex", "--sync", "--format", "json"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    data = load_json_output(result)
    assert data["total_sessions"] == 1
    assert data["by_agent"]["codex"]["sessions"] == 1
    assert "claude" not in data["by_agent"]
