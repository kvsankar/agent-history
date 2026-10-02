"""Behavior tests for export output across agents and NDJSON schema."""

import json
import os
from pathlib import Path

from agent_history.export.html import render_html_export
from tests.helpers.cli import run_cli_subprocess
from tests.helpers.gap_helpers import load_json_output
from tests.helpers.session_builders import ClaudeSessionBuilder, CodexSessionBuilder


def _find_single_output_file(output_dir: Path, suffix: str) -> Path:
    matches = [path for path in output_dir.glob(f"**/*{suffix}") if path.name != "index.md"]
    assert matches, f"Expected export output with suffix {suffix}"
    return matches[0]


def _write_claude_session(root: Path, workspace: str = "-home-user-export-target") -> Path:
    builder = ClaudeSessionBuilder(workspace=workspace, session_id="export-session")
    tool = builder.make_tool_use("Bash", {"command": "echo ok"})
    builder.add_user_message("Hello")
    builder.add_assistant_message("Running it\n\n```python\nprint('ok')\n```", tools=[tool])
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


def _write_copilot_cli_session(root: Path) -> Path:
    session_dir = root / "copilot-cli-session"
    events_file = session_dir / "events.jsonl"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "workspace.yaml").write_text(
        "cwd: /home/user/copilot-cli-project\n",
        encoding="utf-8",
    )
    events = [
        {
            "id": "u1",
            "timestamp": "2026-06-18T14:00:00.000Z",
            "type": "user.message",
            "data": {"content": "Hello Copilot CLI"},
        },
        {
            "id": "a1",
            "parentId": "u1",
            "timestamp": "2026-06-18T14:00:01.000Z",
            "type": "assistant.message",
            "data": {"content": "Copilot CLI response", "model": "gpt-5"},
        },
    ]
    events_file.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )
    return events_file


def _write_copilot_vscode_session(root: Path) -> Path:
    workspace_dir = root / "hash123"
    transcript = workspace_dir / "GitHub.copilot-chat" / "transcripts" / "chat-1.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "workspace.json").write_text(
        json.dumps({"folder": "file:///home/user/copilot-vscode-project"}),
        encoding="utf-8",
    )
    events = [
        {
            "id": "u1",
            "timestamp": "2026-06-18T14:00:00.000Z",
            "type": "user.message",
            "data": {"content": "Hello VS Code Copilot"},
        },
        {
            "id": "a1",
            "parentId": "u1",
            "timestamp": "2026-06-18T14:00:01.000Z",
            "type": "assistant.message",
            "data": {"content": "VS Code Copilot response", "model": "gpt-5"},
        },
    ]
    transcript.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )
    return transcript


def test_session_export_default_output_dir_is_cagelens_exports(isolated_home):
    _write_claude_session(isolated_home["claude_dir"])

    result = run_cli_subprocess(
        ["session", "export", "/home/user/export-target", "--force"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    output_dir = isolated_home["path"] / ".cagelens" / "exports"
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
            "/home/user/export-target",
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


def test_session_export_html_writes_turns_actions_and_raw_view(isolated_home):
    builder = ClaudeSessionBuilder(workspace="-home-user-export-target", session_id="html-session")
    tool = builder.make_tool_use("Bash", {"command": "printf '<b>unsafe</b>'"})
    task_tool = builder.make_tool_use(
        "Task",
        {
            "description": "Review HTML export behavior",
            "prompt": "Inspect graph controls",
            "subagent_type": "reviewer",
        },
    )
    builder.add_user_message("Show <script>alert(1)</script>")
    builder.add_assistant_message("Running it", tools=[tool, task_tool])
    builder.add_tool_result(
        tool["id"], "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n-old\n+new"
    )
    builder.add_tool_result(
        task_tool["id"],
        "Sub-agent found the graph should expose invocation and merge details.",
    )
    builder.add_assistant_message("Done")
    builder.write_to(isolated_home["claude_dir"])
    output_dir = isolated_home["path"] / "html-export"

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "/home/user/export-target",
            "--format",
            "html",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    output = _find_single_output_file(output_dir, ".html")
    html = output.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert '<html lang="en" data-theme="light" data-level="1">' in html
    assert '<body data-agent-graph="hidden">' in html
    assert "Turn 1" in html
    assert "Show &lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert 'class="message message-human"' in html
    assert 'class="message message-assistant"' in html
    assert (
        ".message-human { background: var(--user-bg); border-color: var(--user-border); }" in html
    )
    assert (
        ".message-assistant { background: var(--assistant-bg); "
        "border-color: var(--assistant-border); }"
    ) in html
    assert "Tool call: Bash" in html
    assert 'data-origin="tool_call"' in html
    assert 'data-origin="tool_result"' in html
    assert 'data-level-button="1" aria-pressed="true">Conversation</button>' in html
    assert 'data-level-button="2" aria-pressed="false">Actions</button>' in html
    assert 'data-turn-level-button="2" aria-pressed="false">Actions</button>' in html
    assert 'data-turn-level-button="3" aria-pressed="false">Full I/O</button>' in html
    assert 'data-turn-level-button="4" aria-pressed="false">Trace</button>' in html
    assert "data-turn-local-level" in html
    assert '<details class="turn-actions" data-level="2" hidden data-open-level="2">' in html
    assert '<details class="full-io" data-level="3" hidden data-open-level="3">' in html
    assert '<details class="turn-trace" data-level="4" hidden data-open-level="4">' in html
    assert 'data-theme-toggle aria-pressed="false">Dark mode</button>' in html
    assert 'data-agent-graph-toggle aria-pressed="false">Hide graph</button>' not in html
    assert 'class="export-layout"' in html
    assert '<aside class="agent-graph" data-agent-graph aria-label="Agent graph">' not in html
    assert 'class="agent-graph-svg"' not in html
    assert 'class="agent-graph-main-track"' not in html
    assert 'class="agent-graph-sub-track"' not in html
    assert 'class="agent-graph-subagent-link"' not in html
    assert "data-open-turn-actions>" not in html
    assert "Review HTML export behavior" in html
    assert "Sub-agent found the graph should expose invocation and merge details." in html
    assert 'target.scrollIntoView({ behavior: "auto", block: "start" })' in html
    assert 'body[data-agent-graph="hidden"] .agent-graph' in html
    assert 'class="turn-nav-button"' in html
    assert 'data-view-toggle="rendered" aria-pressed="true">Formatted</button>' in html
    assert 'data-view-toggle="raw" aria-pressed="false"' in html
    assert 'class="markdown-body"' in html
    assert 'class="code-text code-theme-light"' in html
    assert 'class="code-text code-theme-dark"' in html
    assert 'class="diff-view"' in html
    assert '<span class="diff-line diff-line-add">' in html
    assert "Raw message" in html


def test_session_export_html_level_three_opens_actions_and_full_io(isolated_home):
    builder = ClaudeSessionBuilder(workspace="-home-user-export-target", session_id="html-level")
    tool = builder.make_tool_use("Bash", {"command": "echo ok"})
    builder.add_user_message("Run the command")
    builder.add_assistant_message("Running it", tools=[tool])
    builder.add_tool_result(tool["id"], "ok")
    builder.write_to(isolated_home["claude_dir"])
    output_dir = isolated_home["path"] / "html-level-export"

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "/home/user/export-target",
            "--format",
            "html",
            "--html-level",
            "3",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    html = _find_single_output_file(output_dir, ".html").read_text(encoding="utf-8")
    assert '<html lang="en" data-theme="light" data-level="3">' in html
    assert 'data-level-button="3" aria-pressed="true">Full I/O</button>' in html
    assert '<details class="turn-actions" data-level="2" data-open-level="2" open>' in html
    assert '<details class="full-io" data-level="3" data-open-level="3" open>' in html
    assert '<details class="turn-trace" data-level="4" hidden data-open-level="4">' in html


def test_html_export_omits_agent_graph_when_lineage_is_available(tmp_path: Path):
    parent = tmp_path / "rollout-parent.jsonl"
    child = tmp_path / "rollout-child.jsonl"
    messages = [
        {
            "role": "user",
            "content": "Review the export graph.",
            "timestamp": "2026-06-09T10:00:00Z",
            "session_id": "parent-thread",
        },
        {
            "role": "assistant",
            "content": (
                "**[Tool Use: spawn_agent]**\n\n"
                "Call ID: `call-child`\n\n"
                'Input:\n```json\n{"agent_type":"approvals_reviewer"}\n```'
            ),
            "timestamp": "2026-06-09T10:00:01Z",
            "is_tool_call": True,
            "tool_name": "spawn_agent",
            "tool_call_id": "call-child",
            "session_id": "parent-thread",
        },
        {
            "role": "system",
            "content": "Call ID: `call-child`\n\nChild completed.",
            "timestamp": "2026-06-09T10:00:02Z",
            "is_tool_result": True,
            "tool_call_id": "call-child",
            "session_id": "parent-thread",
        },
        {
            "role": "assistant",
            "content": "Done.",
            "timestamp": "2026-06-09T10:00:03Z",
            "session_id": "parent-thread",
        },
    ]

    html = render_html_export(
        parent,
        "codex",
        messages,
        lineage_records=[
            {
                "kind": "main",
                "session_id": "parent-thread",
                "source_file": str(parent),
            },
            {
                "kind": "subagent",
                "session_id": "child-thread",
                "parent_session_id": "parent-thread",
                "invocation_tool_call_id": "call-child",
                "agent_name": "approvals_reviewer",
                "status": "completed",
                "source_file": str(child),
            },
        ],
        lineage_hrefs={str(child): "rollout-child.html"},
    )

    assert '<body data-agent-graph="hidden">' in html
    assert 'data-agent-graph-toggle aria-pressed="false">Hide graph</button>' not in html
    assert 'class="agent-graph-subagent-link" href="rollout-child.html">' not in html
    assert "Open sub-agent transcript" not in html
    assert 'class="agent-graph-subagent-label"' not in html
    assert 'class="agent-graph-turn-label"' not in html


def test_html_export_includes_codex_related_subagent_page(isolated_home, tmp_path: Path):
    workspace = "/home/testuser/codex-project"
    parent = CodexSessionBuilder(session_id="parent-thread", cwd=workspace)
    parent.add_user_message("Review this change.")
    parent.add_function_call("spawn_agent", {"agent_type": "approvals_reviewer"})
    parent.add_function_output(
        "call_001",
        json.dumps({"agent_id": "child-thread", "nickname": "approvals_reviewer"}),
    )
    parent.add_assistant_message("The child reviewer is done.")
    parent_file = parent.write_to(isolated_home["codex_dir"], date_str="2026-01-02")

    child = CodexSessionBuilder(session_id="child-thread", cwd=workspace)
    child.records[0]["payload"].update(
        {
            "thread_source": "subagent",
            "forked_from_id": "parent-thread",
            "agent_nickname": "approvals_reviewer",
            "source": {
                "subagent": {
                    "thread_spawn": {
                        "parent_thread_id": "parent-thread",
                        "instruction": "Review this change.",
                    }
                }
            },
        }
    )
    child.add_user_message("Review this change.")
    child.add_assistant_message("No issues found.")
    child_file = child.write_to(isolated_home["codex_dir"], date_str="2026-01-02")

    os.utime(parent_file, (1767312000, 1767312000))
    os.utime(child_file, (1735689600, 1735689600))

    output_dir = tmp_path / "html-export"
    result = run_cli_subprocess(
        [
            "--agent",
            "codex",
            "session",
            "export",
            workspace,
            "--format",
            "html",
            "--since",
            "2026-01-01",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    html_files = sorted(output_dir.rglob("*.html"))
    assert len(html_files) == 2
    parent_html_file = next(path for path in html_files if "parent-thread" in path.name)
    child_html_file = next(path for path in html_files if "child-thread" in path.name)
    parent_html = parent_html_file.read_text(encoding="utf-8")
    assert '<body data-agent-graph="hidden">' in parent_html
    assert child_html_file.name not in parent_html
    assert "Open sub-agent transcript" not in parent_html
    assert "data-open-turn-actions>" not in parent_html


def test_html_export_labels_subagent_events_and_parent_agent_prompts(tmp_path: Path):
    html = render_html_export(
        tmp_path / "rollout-child.jsonl",
        "codex",
        [
            {
                "role": "user",
                "content": "Inspect this area.",
                "timestamp": "2026-06-09T10:00:00Z",
                "is_parent_agent_message": True,
            },
            {
                "role": "system",
                "content": "**Sub-agent completed**\nAgent path: `agent-1`\n\nReviewed it.",
                "timestamp": "2026-06-09T10:00:01Z",
                "is_subagent_notification": True,
                "subagent_status": "completed",
            },
            {
                "role": "assistant",
                "content": "I reviewed the area.",
                "timestamp": "2026-06-09T10:00:02Z",
            },
        ],
    )

    assert "<h3>Parent agent</h3>" in html
    assert "<h3>Sub-agent completed</h3>" in html
    assert "1 sub-agent event" in html
    assert 'class="message message-parent-agent"' in html
    assert 'class="message message-subagent-event message-action"' in html
    assert "<h3>User</h3>" not in html
    assert "&lt;subagent_notification&gt;" not in html


def test_session_export_html_highlights_numbered_markdown_tool_output(isolated_home):
    builder = ClaudeSessionBuilder(
        workspace="-home-user-export-target",
        session_id="html-markdown-tool-output",
    )
    tool = builder.make_tool_use("Read", {"file_path": "TESTING.md"})
    builder.add_user_message("Show the test doc")
    builder.add_assistant_message("Reading it", tools=[tool])
    builder.add_tool_result(
        tool["id"],
        "     1→# claude-history Regression Test Cases\n"
        "     2→\n"
        "     3→This document lists all test combinations.\n"
        "     4→\n"
        "     5→**Important Notes:**\n"
        "     6→- Replace `<user>` with test username",
    )
    builder.write_to(isolated_home["claude_dir"])
    output_dir = isolated_home["path"] / "html-markdown-output-export"

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "/home/user/export-target",
            "--format",
            "html",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    html = _find_single_output_file(output_dir, ".html").read_text(encoding="utf-8")
    assert "data-copy-button" in html
    assert 'data-copy-content="rendered" hidden># claude-history Regression Test Cases' in html
    assert 'data-copy-content="raw" hidden>     1→# claude-history' in html
    assert 'class="code-text code-theme-light"' in html
    assert 'class="code-text code-theme-dark"' in html
    assert 'data-view-toggle="rendered" aria-pressed="true">Highlighted</button>' in html


def test_session_export_html_skips_claude_snapshot_only_files(isolated_home):
    _write_claude_session(isolated_home["claude_dir"])
    workspace_dir = isolated_home["claude_dir"] / "-home-user-export-target"
    snapshot_file = workspace_dir / "snapshot-only.jsonl"
    snapshot_file.write_text(
        json.dumps(
            {
                "type": "file-history-snapshot",
                "messageId": "snapshot-message",
                "snapshot": {"trackedFileBackups": {}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = isolated_home["path"] / "html-snapshot-export"

    result = run_cli_subprocess(
        [
            "session",
            "export",
            "/home/user/export-target",
            "--format",
            "html",
            "--force",
            "-o",
            str(output_dir),
        ],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    html_files = [path for path in output_dir.glob("**/*.html") if path.name != "index.html"]

    assert html_files, "Expected the real conversation to be exported"
    assert not (output_dir / "home" / "user" / "export-target" / "snapshot-only.html").exists()
    assert all("<dt>Messages</dt><dd>0</dd>" not in path.read_text() for path in html_files)


def test_session_export_html_to_stdout_uses_file_target(isolated_home):
    session_file = _write_claude_session(isolated_home["claude_dir"])

    result = run_cli_subprocess(
        ["session", "export", str(session_file), "--format", "html", "-o", "-"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.startswith("<!doctype html>")
    assert "Claude Conversation" in result.stdout
    assert "Turn 1" in result.stdout
    assert not (isolated_home["path"] / "-").exists()


def test_project_export_preserves_non_claude_absolute_workspace_path(isolated_home):
    workspace = "/home/user/projects/examples-sandbox/codex-examples"
    builder = CodexSessionBuilder(session_id="codex-project-session", cwd=workspace)
    builder.add_user_message("Hello Codex project")
    builder.add_assistant_message("Codex project response")
    builder.write_to(isolated_home["codex_dir"])
    config_file = isolated_home["history_dir"] / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "version": 2,
                "homes": [],
                "sources": [],
                "projects": {"codexproj": {"local": [workspace]}},
            }
        ),
        encoding="utf-8",
    )
    output_dir = isolated_home["path"] / "project-export"

    result = run_cli_subprocess(
        ["project", "export", "codexproj", "--layout", "tree", "--force", "-o", str(output_dir)],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    output_file = _find_single_output_file(output_dir, ".md")
    assert "examples-sandbox/codex-examples" in output_file.as_posix()
    content = output_file.read_text(encoding="utf-8")
    assert "# Codex Conversation" in content
    assert "Codex project response" in content


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


def test_copilot_cli_sessions_list_and_export_via_registry(isolated_home):
    copilot_dir = isolated_home["path"] / ".copilot" / "session-state"
    _write_copilot_cli_session(copilot_dir)
    env = dict(isolated_home["env"])
    env["COPILOT_CLI_SESSIONS_DIR"] = str(copilot_dir)

    list_result = run_cli_subprocess(
        ["session", "list", "--agent", "copilot-cli", "--aw", "--format", "json"],
        env=env,
        cwd=isolated_home["path"],
    )

    assert list_result.returncode == 0, f"stderr: {list_result.stderr}"
    sessions = load_json_output(list_result)
    assert len(sessions) == 1
    assert sessions[0]["agent"] == "copilot-cli"
    assert sessions[0]["workspace"] == "/home/user/copilot-cli-project"

    output_dir = isolated_home["path"] / "copilot-cli-export"
    export_result = run_cli_subprocess(
        [
            "session",
            "export",
            "--agent",
            "copilot-cli",
            "--aw",
            "-o",
            str(output_dir),
            "--force",
        ],
        env=env,
        cwd=isolated_home["path"],
    )

    assert export_result.returncode == 0, f"stderr: {export_result.stderr}"
    content = _find_single_output_file(output_dir, ".md").read_text(encoding="utf-8")
    assert "# Copilot CLI Conversation" in content
    assert "Copilot CLI response" in content


def test_copilot_vscode_sessions_list_and_export_via_registry(isolated_home):
    storage_dir = isolated_home["path"] / "workspaceStorage"
    _write_copilot_vscode_session(storage_dir)
    env = dict(isolated_home["env"])
    env["COPILOT_VSCODE_WORKSPACE_STORAGE_DIR"] = str(storage_dir)

    list_result = run_cli_subprocess(
        ["session", "list", "--agent", "copilot-vscode", "--aw", "--format", "json"],
        env=env,
        cwd=isolated_home["path"],
    )

    assert list_result.returncode == 0, f"stderr: {list_result.stderr}"
    sessions = load_json_output(list_result)
    assert len(sessions) == 1
    assert sessions[0]["agent"] == "copilot-vscode"
    assert sessions[0]["workspace"] == "/home/user/copilot-vscode-project"

    output_dir = isolated_home["path"] / "copilot-vscode-export"
    export_result = run_cli_subprocess(
        [
            "session",
            "export",
            "--agent",
            "copilot-vscode",
            "--aw",
            "-o",
            str(output_dir),
            "--force",
        ],
        env=env,
        cwd=isolated_home["path"],
    )

    assert export_result.returncode == 0, f"stderr: {export_result.stderr}"
    content = _find_single_output_file(output_dir, ".md").read_text(encoding="utf-8")
    assert "# VS Code Copilot Conversation" in content
    assert "VS Code Copilot response" in content


def test_copilot_vscode_windows_workspace_sessions_export_from_workspace_scope(isolated_home):
    storage_dir = isolated_home["path"] / "windows" / "workspaceStorage"
    workspace_dir = storage_dir / "e9d2bd165be5e72d21f6e6f3c2699e13"
    transcript = (
        workspace_dir
        / "GitHub.copilot-chat"
        / "transcripts"
        / "b52a58a1-7877-4746-85a3-88bd963f1fea.jsonl"
    )
    transcript.parent.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "workspace.json").write_text(
        json.dumps({"folder": "file:///d%3A/stellantis/pre/todo-priority"}),
        encoding="utf-8",
    )
    transcript.write_text(
        "\n".join(
            json.dumps(event)
            for event in [
                {
                    "id": "u1",
                    "timestamp": "2026-06-18T14:00:00.000Z",
                    "type": "user.message",
                    "data": {"content": "Hello Windows VS Code Copilot"},
                },
                {
                    "id": "a1",
                    "parentId": "u1",
                    "timestamp": "2026-06-18T14:00:01.000Z",
                    "type": "assistant.message",
                    "data": {"content": "Windows VS Code Copilot response", "model": "gpt-5"},
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = dict(isolated_home["env"])
    env["COPILOT_VSCODE_WINDOWS_WORKSPACE_STORAGE_DIR"] = str(storage_dir)

    ws_result = run_cli_subprocess(
        [
            "ws",
            "list",
            "--home",
            "windows",
            "--agent",
            "copilot-vscode",
            "--format",
            "json",
        ],
        env=env,
        cwd=isolated_home["path"],
    )
    assert ws_result.returncode == 0, f"stderr: {ws_result.stderr}"
    workspaces = load_json_output(ws_result)
    assert workspaces[0]["workspace"] == "/mnt/d/stellantis/pre/todo-priority"
    assert workspaces[0]["session_count"] == 1

    list_result = run_cli_subprocess(
        [
            "session",
            "list",
            "/mnt/d/stellantis/pre/todo-priority",
            "--home",
            "windows",
            "--agent",
            "copilot-vscode",
            "--format",
            "json",
        ],
        env=env,
        cwd=isolated_home["path"],
    )
    assert list_result.returncode == 0, f"stderr: {list_result.stderr}"
    sessions = load_json_output(list_result)
    assert len(sessions) == 1
    assert sessions[0]["workspace_key"] == "/mnt/d/stellantis/pre/todo-priority"

    empty_list_result = run_cli_subprocess(
        [
            "session",
            "list",
            "/mnt/d/stellantis/pre/no-such-project",
            "--home",
            "windows",
            "--agent",
            "copilot-vscode",
            "--format",
            "json",
        ],
        env=env,
        cwd=isolated_home["path"],
    )
    assert empty_list_result.returncode == 0, f"stderr: {empty_list_result.stderr}"
    assert load_json_output(empty_list_result) == []

    output_dir = isolated_home["path"] / "copilot-vscode-windows-export"
    export_result = run_cli_subprocess(
        [
            "ws",
            "export",
            "/mnt/d/stellantis/pre/todo-priority",
            "--home",
            "windows",
            "--agent",
            "copilot-vscode",
            "--format",
            "html",
            "-o",
            str(output_dir),
            "--force",
        ],
        env=env,
        cwd=isolated_home["path"],
    )
    assert export_result.returncode == 0, f"stderr: {export_result.stderr}"
    payload = load_json_output(export_result)
    assert payload["exported"] == 1
    content = _find_single_output_file(output_dir, ".html").read_text(encoding="utf-8")
    assert "Windows VS Code Copilot response" in content


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
