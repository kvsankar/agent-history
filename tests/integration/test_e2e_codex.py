"""Codex E2E integration tests.

Tests end-to-end flows for Codex CLI session handling:
- lsw/lss with --agent codex
- export with --agent codex
- stats sync and display for Codex sessions
- Mixed agent filtering (auto/claude/codex)
"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def run_cli(args, env=None, timeout=25):
    """Run agent-history CLI command."""
    script_path = Path.cwd() / "agent-history"
    if not script_path.exists():
        script_path = Path.cwd() / "claude-history"
    cmd = [sys.executable, str(script_path), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
        timeout=timeout,
        check=False,
    )


def make_codex_session(
    base_path: Path, date_str: str, session_id: str, messages: list = None, cwd: str = None
):
    """Create a Codex session file in ~/.codex/sessions/YYYY/MM/DD/ structure.

    Args:
        base_path: Base path for .codex directory (simulated home)
        date_str: Date in YYYY-MM-DD format
        session_id: Unique session identifier
        messages: Optional list of message dicts to include
        cwd: Optional working directory path (default: /home/user/codex-project)
    """
    year, month, day = date_str.split("-")
    session_dir = base_path / ".codex" / "sessions" / year / month / day
    session_dir.mkdir(parents=True, exist_ok=True)

    # Default session with realistic Codex format
    rows = [
        {
            "timestamp": f"{date_str}T10:00:00.000Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "cwd": cwd or "/home/user/codex-project",
                "cli_version": "0.5.0",
                "source": "cli",
            },
        },
        {
            "timestamp": f"{date_str}T10:00:01.000Z",
            "type": "turn_context",
            "payload": {"model": "o4-mini"},
        },
    ]

    if messages:
        for msg in messages:
            rows.append(msg)
    else:
        # Default user/assistant exchange
        rows.extend(
            [
                {
                    "timestamp": f"{date_str}T10:00:02.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "Hello Codex"}],
                    },
                },
                {
                    "timestamp": f"{date_str}T10:00:03.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Hello! How can I help?"}],
                    },
                },
            ]
        )

    session_file = session_dir / f"rollout-{session_id}.jsonl"
    with session_file.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    return session_file


def make_claude_session(
    base_path: Path, workspace_name: str, session_id: str, messages: list = None
):
    """Create a Claude session file in ~/.claude/projects/ structure.

    Args:
        base_path: Base path for .claude directory (simulated home)
        workspace_name: Encoded workspace name (e.g., "-home-user-myproject")
        session_id: UUID for the session file
        messages: Optional list of message dicts to include
    """
    workspace_dir = base_path / ".claude" / "projects" / workspace_name
    workspace_dir.mkdir(parents=True, exist_ok=True)

    rows = messages or [
        {
            "type": "user",
            "timestamp": "2025-01-15T10:00:00Z",
            "message": {"role": "user", "content": "Hello Claude"},
        },
        {
            "type": "assistant",
            "timestamp": "2025-01-15T10:00:01Z",
            "model": "claude-3-5-sonnet",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello! How can I help?"}],
            },
        },
    ]

    session_file = workspace_dir / f"{session_id}.jsonl"
    with session_file.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    return session_file


def setup_env(tmp_path: Path):
    """Set up environment variables for testing.

    Uses CLAUDE_PROJECTS_DIR and CODEX_SESSIONS_DIR environment variables
    to point the CLI at our test fixtures, avoiding the need to modify HOME.
    """
    # Create both directories - CLI requires them to exist
    claude_dir = tmp_path / ".claude" / "projects"
    codex_dir = tmp_path / ".codex" / "sessions"
    claude_dir.mkdir(parents=True, exist_ok=True)
    codex_dir.mkdir(parents=True, exist_ok=True)

    # Create .claude-history for metrics DB
    history_dir = tmp_path / ".claude-history"
    history_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    # Use environment variable overrides for both agent types
    env["CLAUDE_PROJECTS_DIR"] = str(claude_dir)
    env["CODEX_SESSIONS_DIR"] = str(codex_dir)
    # Set HOME for the metrics DB location (~/.claude-history/)
    if sys.platform == "win32":
        env["USERPROFILE"] = str(tmp_path)
    else:
        env["HOME"] = str(tmp_path)

    return env


# ============================================================================
# Codex List Tests (lsw/lss --agent codex)
# ============================================================================


class TestCodexList:
    """E2E tests for listing Codex sessions."""

    def test_lss_agent_codex_lists_codex_sessions(self, tmp_path: Path):
        """lss --agent codex should list only Codex sessions."""
        make_codex_session(tmp_path, "2025-01-15", "codex-session-1")
        make_codex_session(tmp_path, "2025-01-16", "codex-session-2")

        env = setup_env(tmp_path)

        # Use --aw to list all workspaces (Codex doesn't have workspace patterns)
        result = run_cli(["--agent", "codex", "lss", "--local", "--aw"], env=env)
        # Must succeed - fixtures are aligned with HOME
        assert result.returncode == 0, f"Expected success, got: {result.stderr}"
        # Should list our sessions (output contains session info)
        assert result.stdout.strip(), "Should have session output"

    def test_lss_agent_codex_excludes_claude_sessions(self, tmp_path: Path):
        """lss --agent codex should not list Claude sessions."""
        # Create both Codex and Claude sessions
        make_codex_session(tmp_path, "2025-01-15", "codex-only")
        make_claude_session(tmp_path, "-home-user-claude-project", "claude-uuid-123")

        env = setup_env(tmp_path)

        result = run_cli(["--agent", "codex", "lss", "--local", "--aw"], env=env)
        # Must succeed
        assert result.returncode == 0, f"Expected success: {result.stderr}"
        # Should not include Claude workspace in output
        assert "claude-project" not in result.stdout.lower()
        # Should have Codex output
        assert result.stdout.strip(), "Should list Codex sessions"

    def test_lss_agent_claude_excludes_codex_sessions(self, tmp_path: Path):
        """lss --agent claude should not list Codex sessions."""
        make_codex_session(tmp_path, "2025-01-15", "codex-only")
        make_claude_session(tmp_path, "-home-user-claude-project", "claude-uuid-123")

        env = setup_env(tmp_path)

        result = run_cli(["--agent", "claude", "lss", "--local", "--aw"], env=env)
        # Must succeed
        assert result.returncode == 0, f"Expected success: {result.stderr}"
        # Should include Claude workspace
        assert "claude" in result.stdout.lower(), "Should list Claude sessions"
        # Should not include Codex session identifiers
        assert "codex-only" not in result.stdout.lower()


# ============================================================================
# Codex Export Tests
# ============================================================================


class TestCodexExport:
    """E2E tests for exporting Codex sessions to Markdown."""

    def test_export_agent_codex_produces_markdown(self, tmp_path: Path):
        """export --agent codex should produce Codex-formatted Markdown."""
        make_codex_session(tmp_path, "2025-01-15", "export-test-session")
        outdir = tmp_path / "output"
        outdir.mkdir()

        env = setup_env(tmp_path)

        result = run_cli(
            ["--agent", "codex", "export", "--local", "-o", str(outdir), "--force", "--aw"],
            env=env,
        )
        # Must succeed - fixtures are aligned with HOME
        assert result.returncode == 0, f"Export failed: {result.stderr}"

        # Must produce markdown output
        md_files = list(outdir.rglob("*.md"))
        assert len(md_files) >= 1, f"Should produce at least one markdown file, got: {md_files}"

        # Verify Codex markdown structure - title must indicate Codex
        content = md_files[0].read_text()
        assert "# Codex Conversation" in content, f"Missing Codex title in: {content[:500]}"

    def test_export_codex_markdown_structure(self, tmp_path: Path):
        """Verify Codex export has correct markdown structure with tool calls."""
        # Create session with tool call
        messages = [
            {
                "timestamp": "2025-01-15T10:00:02.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Run ls command"}],
                },
            },
            {
                "timestamp": "2025-01-15T10:00:03.000Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": '{"command": "ls -la"}',
                    "call_id": "call-123",
                },
            },
            {
                "timestamp": "2025-01-15T10:00:04.000Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-123",
                    "output": "total 0\ndrwxr-xr-x 2 user user 40 Jan 15 10:00 .",
                },
            },
        ]
        make_codex_session(tmp_path, "2025-01-15", "tool-test", messages)
        outdir = tmp_path / "output"
        outdir.mkdir()

        env = setup_env(tmp_path)

        result = run_cli(
            ["--agent", "codex", "export", "--local", "-o", str(outdir), "--force", "--aw"],
            env=env,
        )

        # Must succeed
        assert result.returncode == 0, f"Export failed: {result.stderr}"

        # Must produce markdown
        md_files = list(outdir.rglob("*.md"))
        assert len(md_files) >= 1, "Should produce markdown file"

        content = md_files[0].read_text()

        # Verify structural elements
        assert "# Codex Conversation" in content, "Missing Codex title"
        # User messages use format: "## User (Message N)"
        assert "User" in content, "Missing user message"
        assert "Message 1" in content, "Missing message numbering"
        # Verify tool call is rendered
        assert "shell" in content, f"Missing tool call 'shell' in: {content}"
        # Verify tool output is rendered
        assert "drwxr-xr-x" in content, f"Missing tool output in: {content}"

    def test_export_codex_metadata_headers(self, tmp_path: Path):
        """Verify Codex export includes session metadata headers."""
        make_codex_session(tmp_path, "2025-01-15", "metadata-test")
        outdir = tmp_path / "output"
        outdir.mkdir()

        env = setup_env(tmp_path)

        result = run_cli(
            ["--agent", "codex", "export", "--local", "-o", str(outdir), "--force", "--aw"],
            env=env,
        )

        assert result.returncode == 0, f"Export failed: {result.stderr}"

        md_files = list(outdir.rglob("*.md"))
        assert len(md_files) >= 1, "Should produce markdown file"

        content = md_files[0].read_text()

        # Verify session metadata is present (from session_meta payload)
        assert "## Session Metadata" in content, f"Missing metadata section: {content[:500]}"
        assert "Session ID:" in content, f"Missing session ID: {content[:500]}"
        assert "Working Directory:" in content, f"Missing working directory: {content[:500]}"
        assert "CLI Version:" in content, f"Missing CLI version: {content[:500]}"
        # Verify our fixture values
        assert "metadata-test" in content, "Should have session ID from fixture"
        assert "/home/user/codex-project" in content, "Should have cwd from fixture"


# ============================================================================
# Codex Stats Tests
# ============================================================================


class TestCodexStats:
    """E2E tests for Codex stats sync and display."""

    def test_stats_sync_includes_codex_sessions(self, tmp_path: Path):
        """stats --sync should scan and include Codex sessions."""
        make_codex_session(tmp_path, "2025-01-15", "stats-test-1")
        make_codex_session(tmp_path, "2025-01-16", "stats-test-2")

        env = setup_env(tmp_path)

        # Use stats --sync --aw to sync all workspaces
        result = run_cli(["stats", "--sync", "--aw"], env=env)
        assert result.returncode == 0, f"Stats sync failed: {result.stderr}"

        # Database must exist after sync
        db_path = tmp_path / ".claude-history" / "metrics.db"
        assert db_path.exists(), f"Database should exist at {db_path}"

        # Verify Codex sessions are in database
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT agent, COUNT(*) FROM sessions GROUP BY agent")
        agents = dict(cursor.fetchall())
        conn.close()

        # Must have Codex sessions
        assert "codex" in agents, f"Should have codex sessions, got: {agents}"
        assert (
            agents["codex"] >= 2
        ), f"Should have at least 2 Codex sessions, got: {agents['codex']}"

    def test_stats_display_codex_sessions(self, tmp_path: Path):
        """stats should display Codex session metrics."""
        make_codex_session(tmp_path, "2025-01-15", "display-test")

        env = setup_env(tmp_path)

        # Sync first with --aw
        sync_result = run_cli(["stats", "--sync", "--aw"], env=env)
        assert sync_result.returncode == 0, f"Sync failed: {sync_result.stderr}"

        # Display stats for all workspaces
        result = run_cli(["stats", "--aw"], env=env)
        assert result.returncode == 0, f"Stats display failed: {result.stderr}"
        # Should show session count
        assert result.stdout.strip(), "Should have stats output"

    def test_stats_codex_session_schema(self, tmp_path: Path):
        """stats should have proper schema for Codex sessions."""
        make_codex_session(tmp_path, "2025-01-15", "schema-test")

        env = setup_env(tmp_path)

        result = run_cli(["stats", "--sync", "--aw"], env=env)
        assert result.returncode == 0, f"Sync failed: {result.stderr}"

        # Database must exist
        db_path = tmp_path / ".claude-history" / "metrics.db"
        assert db_path.exists(), "Database should exist"

        conn = sqlite3.connect(db_path)

        # Check schema has expected columns for agent support
        cursor = conn.execute("PRAGMA table_info(sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "agent" in columns, "Sessions table should have agent column"
        assert "workspace" in columns, "Sessions table should have workspace column"
        assert "session_id" in columns, "Sessions table should have session_id column"

        # Verify Codex sessions were synced with proper agent tagging
        cursor = conn.execute(
            "SELECT agent, session_id, workspace FROM sessions WHERE agent = 'codex'"
        )
        rows = cursor.fetchall()
        conn.close()

        # Should have synced Codex sessions
        assert len(rows) >= 1, "Should have Codex sessions in DB"
        # Verify agent is set correctly
        assert all(row[0] == "codex" for row in rows), "All rows should have agent=codex"

    def test_stats_codex_workspace_extraction(self, tmp_path: Path):
        """stats should extract workspace from Codex session_meta cwd."""
        make_codex_session(tmp_path, "2025-01-15", "workspace-extract-test")

        env = setup_env(tmp_path)

        result = run_cli(["stats", "--sync", "--aw"], env=env)
        assert result.returncode == 0, f"Sync failed: {result.stderr}"

        db_path = tmp_path / ".claude-history" / "metrics.db"
        assert db_path.exists(), "Database should exist"

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT workspace FROM sessions WHERE agent = 'codex'")
        workspaces = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Should have workspace from session_meta.cwd
        assert len(workspaces) >= 1, "Should have Codex sessions"
        # Default fixture uses "/home/user/codex-project" as cwd
        assert any(
            "codex-project" in w for w in workspaces
        ), f"Should have workspace, got: {workspaces}"


# ============================================================================
# Mixed Agent Tests
# ============================================================================


class TestMixedAgents:
    """E2E tests for mixed Claude/Codex filtering."""

    def test_agent_auto_includes_both(self, tmp_path: Path):
        """--agent auto should include both Claude and Codex sessions."""
        make_codex_session(tmp_path, "2025-01-15", "codex-mixed")
        make_claude_session(tmp_path, "-home-user-claude-mixed", "claude-uuid-mixed")

        env = setup_env(tmp_path)

        # Use lss --local --aw to list all workspaces
        result = run_cli(["lss", "--local", "--aw"], env=env)
        # Must succeed
        assert result.returncode == 0, f"Expected success: {result.stderr}"
        # Should have output from both
        assert result.stdout.strip(), "Should list sessions"

    def test_stats_sync_both_agents(self, tmp_path: Path):
        """stats --sync with auto should sync both Claude and Codex."""
        make_codex_session(tmp_path, "2025-01-15", "codex-sync")
        make_claude_session(tmp_path, "-home-user-claude-sync", "claude-uuid-sync")

        env = setup_env(tmp_path)

        result = run_cli(["stats", "--sync", "--aw"], env=env)
        assert result.returncode == 0, f"Sync failed: {result.stderr}"

        # Database must exist
        db_path = tmp_path / ".claude-history" / "metrics.db"
        assert db_path.exists(), "Database should exist"

        # Check both agents in database
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT DISTINCT agent FROM sessions")
        agents = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Must have both agent types
        assert "codex" in agents, f"Should have codex sessions, got: {agents}"
        assert "claude" in agents, f"Should have claude sessions, got: {agents}"

    def test_export_filters_by_agent_codex_only(self, tmp_path: Path):
        """export --agent codex should only export Codex sessions."""
        make_codex_session(tmp_path, "2025-01-15", "codex-filter")
        make_claude_session(tmp_path, "-home-user-claude-filter", "claude-uuid-filter")

        outdir = tmp_path / "output"
        outdir.mkdir()

        env = setup_env(tmp_path)

        # Export only Codex
        result = run_cli(
            ["--agent", "codex", "export", "--local", "-o", str(outdir), "--force", "--aw"],
            env=env,
        )
        # Must succeed
        assert result.returncode == 0, f"Export failed: {result.stderr}"

        # Should have markdown files
        md_files = list(outdir.rglob("*.md"))
        assert len(md_files) >= 1, "Should produce markdown"

        # All files should be Codex format
        for md_file in md_files:
            content = md_file.read_text()
            assert "# Codex Conversation" in content, f"Should be Codex format: {md_file}"
            assert "# Claude Conversation" not in content, f"Should not be Claude format: {md_file}"

    def test_export_filters_by_agent_claude_only(self, tmp_path: Path):
        """export --agent claude should only export Claude sessions."""
        make_codex_session(tmp_path, "2025-01-15", "codex-filter2")
        make_claude_session(tmp_path, "-home-user-claude-filter2", "claude-uuid-filter2")

        outdir = tmp_path / "output"
        outdir.mkdir()

        env = setup_env(tmp_path)

        # Export only Claude
        result = run_cli(
            ["--agent", "claude", "export", "--local", "-o", str(outdir), "--force", "--aw"],
            env=env,
        )
        # Must succeed
        assert result.returncode == 0, f"Export failed: {result.stderr}"

        # Should have markdown files
        md_files = list(outdir.rglob("*.md"))
        assert len(md_files) >= 1, "Should produce markdown"

        # All files should be Claude format
        for md_file in md_files:
            content = md_file.read_text()
            assert "# Claude Conversation" in content, f"Should be Claude format: {md_file}"
            assert "# Codex Conversation" not in content, f"Should not be Codex format: {md_file}"


# ============================================================================
# Codex Workspace Tests
# ============================================================================


class TestCodexWorkspaces:
    """E2E tests for Codex workspace handling."""

    def test_codex_sessions_have_workspace(self, tmp_path: Path):
        """Codex sessions should have meaningful workspace names."""
        make_codex_session(tmp_path, "2025-01-15", "workspace-test")

        env = setup_env(tmp_path)

        # --agent must come before the subcommand (it's a global argument)
        result = run_cli(["--agent", "codex", "stats", "--sync"], env=env)
        assert result.returncode == 0, f"Sync failed: {result.stderr}"

        # Database must exist
        db_path = tmp_path / ".claude-history" / "metrics.db"
        assert db_path.exists(), "Database should exist"

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT workspace FROM sessions WHERE agent = 'codex'")
        workspaces = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Must have Codex sessions with workspaces
        assert len(workspaces) >= 1, "Should have Codex sessions"
        assert all(w for w in workspaces), f"All sessions should have workspace: {workspaces}"

    def test_lsw_agent_codex_lists_workspaces(self, tmp_path: Path):
        """lsw --agent codex should list Codex workspaces."""
        make_codex_session(tmp_path, "2025-01-15", "lsw-test")

        env = setup_env(tmp_path)

        result = run_cli(["--agent", "codex", "lsw", "--local"], env=env)
        # Must succeed
        assert result.returncode == 0, f"lsw failed: {result.stderr}"
        # Should have workspace output
        assert result.stdout.strip(), "Should list workspaces"


# ============================================================================
# Codex Index Fallback Tests
# ============================================================================


class TestCodexIndexFallback:
    """Tests for Codex index fallback when workspace entries are empty or stale."""

    def _create_codex_index(self, tmp_path: Path, sessions: dict) -> None:
        """Create a Codex session index file.

        Args:
            sessions: Dict mapping file paths to workspace names
        """
        config_dir = tmp_path / ".claude-history"
        config_dir.mkdir(parents=True, exist_ok=True)
        index_file = config_dir / "codex_session_index.json"
        index_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "last_scan_date": "2025-01-01",
                    "sessions": sessions,
                }
            )
        )

    def test_empty_index_entry_triggers_fallback(self, tmp_path: Path):
        """Session with empty workspace in index should fallback to file read."""
        # Create a Codex session
        make_codex_session(
            tmp_path, "2025-01-15", "fallback-test", cwd="/home/user/fallback-project"
        )

        # Create index with empty workspace for this session
        sessions_dir = tmp_path / ".codex" / "sessions"
        session_files = list(sessions_dir.glob("*/*/*/rollout-*.jsonl"))
        assert len(session_files) == 1, "Should have one session file"

        # Index with empty workspace
        self._create_codex_index(tmp_path, {str(session_files[0]): ""})

        env = setup_env(tmp_path)

        # lss should still find the session (fallback to file read)
        result = run_cli(["--agent", "codex", "lss", "--local", "--aw"], env=env)
        assert result.returncode == 0, f"lss failed: {result.stderr}"
        # Should show the workspace from file content
        assert "fallback" in result.stdout.lower() or "project" in result.stdout.lower()

    def test_lsw_with_empty_index_entry(self, tmp_path: Path):
        """lsw should list workspace even if index has empty entry."""
        make_codex_session(tmp_path, "2025-01-20", "empty-index-test", cwd="/home/user/my-project")

        # Create index with empty workspace
        sessions_dir = tmp_path / ".codex" / "sessions"
        session_files = list(sessions_dir.glob("*/*/*/rollout-*.jsonl"))
        self._create_codex_index(tmp_path, {str(session_files[0]): ""})

        env = setup_env(tmp_path)

        result = run_cli(["--agent", "codex", "lsw", "--local"], env=env)
        assert result.returncode == 0, f"lsw failed: {result.stderr}"
        # Should have workspace output (from fallback read)
        assert result.stdout.strip(), "Should list workspaces even with empty index"

    def test_pattern_filter_with_fallback_workspace(self, tmp_path: Path):
        """Pattern filtering should work after fallback to file read."""
        make_codex_session(tmp_path, "2025-01-25", "pattern-test", cwd="/home/user/react-app")

        # Create index with empty workspace
        sessions_dir = tmp_path / ".codex" / "sessions"
        session_files = list(sessions_dir.glob("*/*/*/rollout-*.jsonl"))
        self._create_codex_index(tmp_path, {str(session_files[0]): ""})

        env = setup_env(tmp_path)

        # Filter by "react" should match after fallback
        result = run_cli(["--agent", "codex", "lss", "react", "--local"], env=env)
        assert result.returncode == 0

        # Filter by non-matching pattern should not match
        result2 = run_cli(["--agent", "codex", "lss", "nonexistent", "--local"], env=env)
        # Returns 1 when no sessions found (which is expected behavior)
        assert result2.returncode in (0, 1)
        assert "pattern-test" not in result2.stdout
