"""Behavior tests for export output across agents and NDJSON schema."""

import json
from pathlib import Path

from tests.helpers.cli import run_cli_subprocess
from tests.helpers.gap_helpers import load_json_output
from tests.helpers.session_builders import ClaudeSessionBuilder


def _find_single_output_file(output_dir: Path, suffix: str) -> Path:
    matches = [path for path in output_dir.glob(f"**/*{suffix}") if path.name != "index.md"]
    assert matches, f"Expected export output with suffix {suffix}"
    return matches[0]


def _write_claude_session(root: Path, workspace: str = "-home-user-export-target") -> Path:
    builder = ClaudeSessionBuilder(workspace=workspace, session_id="export-session")
    tool = builder.make_tool_use("Bash", {"command": "echo ok"})
    builder.add_user_message("Hello")
    builder.add_assistant_message("Running it", tools=[tool])
    builder.add_tool_result(tool["id"], "ok")
    return builder.write_to(root)


def _write_pi_session(root: Path) -> Path:
    session_file = root / "--home-user-pi-project--" / "session.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {"type": "session", "id": "pi-session", "cwd": "/home/user/pi-project"},
        {
            "type": "message",
            "id": "u1",
            "timestamp": 1700000000000,
            "message": {"role": "user", "content": "Hello Pi"},
        },
        {
            "type": "message",
            "id": "a1",
            "parentId": "u1",
            "timestamp": 1700000001000,
            "message": {"role": "assistant", "content": "Pi response"},
        },
    ]
    session_file.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n",
        encoding="utf-8",
    )
    return session_file


def test_session_export_default_output_dir_is_hidden_agent_history_exports(isolated_home):
    _write_claude_session(isolated_home["claude_dir"])

    result = run_cli_subprocess(
        ["session", "export", "export-target", "--force"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    output_dir = isolated_home["path"] / ".agent-history" / "exports"
    assert list(output_dir.rglob("*.md")), "Expected markdown under default export directory"


def test_session_export_to_stdout_requires_single_session_file(isolated_home):
    session_file = _write_claude_session(isolated_home["claude_dir"])

    result = run_cli_subprocess(
        ["session", "export", str(session_file), "-o", "-", "--markdown-level", "1"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "# Claude Conversation" in result.stdout
    assert "**Markdown detail level:** 1" in result.stdout
    assert "## Turn 1" in result.stdout
    assert not (isolated_home["path"] / "-").exists()


def test_session_export_markdown_level_1_writes_compact_turns(isolated_home):
    _write_claude_session(isolated_home["claude_dir"])
    output_dir = isolated_home["path"] / "level_export"

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "export-target",
            "--markdown-level",
            "1",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    content = _find_single_output_file(output_dir, ".md").read_text(encoding="utf-8")
    assert "**Markdown detail level:** 1" in content
    assert "## Turn 1" in content
    assert "### Tool Call" not in content


def test_export_rejects_html_until_package_renderer_exists(isolated_home):
    _write_claude_session(isolated_home["claude_dir"])

    result = run_cli_subprocess(
        ["session", "export", "export-target", "--format", "html"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode != 0
    assert "HTML export has not been ported" in result.stderr


def test_pi_agent_sessions_list_and_export_via_registry(isolated_home):
    pi_dir = isolated_home["path"] / ".pi" / "agent" / "sessions"
    _write_pi_session(pi_dir)
    env = dict(isolated_home["env"])
    env["PI_SESSIONS_DIR"] = str(pi_dir)

    list_result = run_cli_subprocess(
        ["session", "list", "--agent", "pi", "--aw", "--format", "json"],
        env=env,
        cwd=isolated_home["path"],
    )

    assert list_result.returncode == 0, f"stderr: {list_result.stderr}"
    sessions = load_json_output(list_result)
    assert len(sessions) == 1
    assert sessions[0]["agent"] == "pi"

    output_dir = isolated_home["path"] / "pi-export"
    export_result = run_cli_subprocess(
        ["session", "export", "--agent", "pi", "--aw", "-o", str(output_dir), "--force"],
        env=env,
        cwd=isolated_home["path"],
    )

    assert export_result.returncode == 0, f"stderr: {export_result.stderr}"
    content = _find_single_output_file(output_dir, ".md").read_text(encoding="utf-8")
    assert "# Pi Conversation" in content
    assert "Pi response" in content


def test_codex_markdown_export_uses_codex_header(isolated_home, setup_golden_fixtures):
    output_dir = isolated_home["path"] / "exports"
    output_dir.mkdir()

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "--agent",
            "codex",
            "--aw",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"

    output_file = _find_single_output_file(output_dir, ".md")
    contents = output_file.read_text(encoding="utf-8")
    assert contents.startswith("# Codex Conversation"), "Expected Codex export header"


def test_gemini_markdown_export_uses_gemini_header(isolated_home, setup_golden_fixtures):
    output_dir = isolated_home["path"] / "exports"
    output_dir.mkdir()

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "--agent",
            "gemini",
            "--aw",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"

    output_file = _find_single_output_file(output_dir, ".md")
    contents = output_file.read_text(encoding="utf-8")
    assert contents.startswith("# Gemini Conversation"), "Expected Gemini export header"


def test_ndjson_export_writes_header_and_session_record(isolated_home, setup_golden_fixtures):
    output_dir = isolated_home["path"] / "exports"
    output_dir.mkdir()

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "--json",
            "--aw",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"

    output_file = _find_single_output_file(output_dir, ".ndjson")
    lines = [line for line in output_file.read_text(encoding="utf-8").splitlines() if line]
    assert lines, "Expected NDJSON output"

    first = json.loads(lines[0])
    assert first.get("type") == "header", "Expected header as first NDJSON line"

    session_lines = [
        json.loads(line) for line in lines if json.loads(line).get("type") == "session"
    ]
    assert session_lines, "Expected at least one session record"
