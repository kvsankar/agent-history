"""Gemini E2E integration tests.

Tests end-to-end flows for Gemini CLI session handling:
- lsw/lss with --agent gemini
- export with --agent gemini
- stats sync and display for Gemini sessions
- Mixed agent filtering (auto/claude/codex/gemini)
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


def make_gemini_session(base_path: Path, project_hash: str, session_id: str, messages: list = None):
    """Create a Gemini session file in ~/.gemini/tmp/<hash>/chats/ structure.

    Args:
        base_path: Base path for .gemini directory (simulated home)
        project_hash: SHA-256 hash of project path
        session_id: Session identifier for filename
        messages: Optional list of message dicts to include
    """
    chat_dir = base_path / ".gemini" / "tmp" / project_hash / "chats"
    chat_dir.mkdir(parents=True, exist_ok=True)

    default_messages = messages or [
        {
            "type": "user",
            "content": "Hello Gemini",
            "timestamp": "2025-01-15T10:00:00.000Z",
        },
        {
            "type": "gemini",
            "content": "Hello! How can I help you today?",
            "timestamp": "2025-01-15T10:00:05.000Z",
            "model": "gemini-2.5-flash",
            "thoughts": [
                {
                    "subject": "Greeting",
                    "description": "Processing user greeting",
                    "timestamp": "2025-01-15T10:00:04.000Z",
                }
            ],
            "tokens": {"input": 10, "output": 20, "total": 30},
        },
    ]

    session_data = {
        "sessionId": session_id,
        "projectHash": project_hash,
        "startTime": "2025-01-15T10:00:00.000Z",
        "lastUpdated": "2025-01-15T10:00:05.000Z",
        "summary": "Test session",
        "messages": default_messages,
    }

    session_file = chat_dir / f"session-{session_id}.json"
    with session_file.open("w", encoding="utf-8") as f:
        json.dump(session_data, f)

    return session_file


def make_claude_session(
    base_path: Path, workspace_name: str, session_id: str, messages: list = None
):
    """Create a Claude session file in ~/.claude/projects/ structure."""
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

    Uses environment variable overrides to point the CLI at test fixtures.
    """
    # Create directories for all agents
    claude_dir = tmp_path / ".claude" / "projects"
    codex_dir = tmp_path / ".codex" / "sessions"
    gemini_dir = tmp_path / ".gemini" / "tmp"
    claude_dir.mkdir(parents=True, exist_ok=True)
    codex_dir.mkdir(parents=True, exist_ok=True)
    gemini_dir.mkdir(parents=True, exist_ok=True)

    # Create .claude-history for metrics DB
    history_dir = tmp_path / ".claude-history"
    history_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    # Use environment variable overrides for all agent types
    env["CLAUDE_PROJECTS_DIR"] = str(claude_dir)
    env["CODEX_SESSIONS_DIR"] = str(codex_dir)
    env["GEMINI_SESSIONS_DIR"] = str(gemini_dir)
    # Set HOME for the metrics DB location (~/.claude-history/)
    if sys.platform == "win32":
        env["USERPROFILE"] = str(tmp_path)
    else:
        env["HOME"] = str(tmp_path)

    return env


# ============================================================================
# Gemini List Tests (lsw/lss --agent gemini)
# ============================================================================


class TestGeminiList:
    """E2E tests for listing Gemini sessions."""

    def test_lss_agent_gemini_lists_gemini_sessions(self, tmp_path: Path):
        """lss --agent gemini should list only Gemini sessions."""
        make_gemini_session(tmp_path, "hash123abc", "session-1")
        make_gemini_session(tmp_path, "hash456def", "session-2")

        env = setup_env(tmp_path)

        result = run_cli(["--agent", "gemini", "lss", "--local", "--aw"], env=env)
        assert result.returncode == 0, f"Expected success, got: {result.stderr}"
        assert result.stdout.strip(), "Should have session output"

    def test_lss_agent_gemini_excludes_claude_sessions(self, tmp_path: Path):
        """lss --agent gemini should not list Claude sessions."""
        make_gemini_session(tmp_path, "hash123abc", "gemini-only")
        make_claude_session(tmp_path, "-home-user-claude-project", "claude-uuid-123")

        env = setup_env(tmp_path)

        result = run_cli(["--agent", "gemini", "lss", "--local", "--aw"], env=env)
        assert result.returncode == 0, f"Expected success: {result.stderr}"
        # Should not include Claude workspace in output
        assert "claude-project" not in result.stdout.lower()
        # Should have Gemini output
        assert result.stdout.strip(), "Should list Gemini sessions"

    def test_lss_agent_claude_excludes_gemini_sessions(self, tmp_path: Path):
        """lss --agent claude should not list Gemini sessions."""
        make_gemini_session(tmp_path, "hash123abc", "gemini-only")
        make_claude_session(tmp_path, "-home-user-claude-project", "claude-uuid-123")

        env = setup_env(tmp_path)

        result = run_cli(["--agent", "claude", "lss", "--local", "--aw"], env=env)
        assert result.returncode == 0, f"Expected success: {result.stderr}"
        # Should include Claude workspace
        assert "claude" in result.stdout.lower(), "Should list Claude sessions"
        # Should not include Gemini session identifiers
        assert "hash123" not in result.stdout.lower()


# ============================================================================
# Gemini Export Tests
# ============================================================================


class TestGeminiExport:
    """E2E tests for exporting Gemini sessions to Markdown."""

    def test_export_agent_gemini_produces_markdown(self, tmp_path: Path):
        """export --agent gemini should produce Gemini-formatted Markdown."""
        make_gemini_session(tmp_path, "hash123abc", "export-test-session")
        outdir = tmp_path / "output"
        outdir.mkdir()

        env = setup_env(tmp_path)

        result = run_cli(
            ["--agent", "gemini", "export", "--local", "-o", str(outdir), "--force", "--aw"],
            env=env,
        )
        assert result.returncode == 0, f"Export failed: {result.stderr}"

        # Must produce markdown output
        md_files = list(outdir.rglob("*.md"))
        assert len(md_files) >= 1, f"Should produce at least one markdown file, got: {md_files}"

        # Verify Gemini markdown structure - title must indicate Gemini
        content = md_files[0].read_text()
        assert "# Gemini Conversation" in content, f"Missing Gemini title in: {content[:500]}"

    def test_export_gemini_markdown_structure(self, tmp_path: Path):
        """Verify Gemini export has correct markdown structure with thoughts."""
        # Create session with reasoning thoughts
        messages = [
            {
                "type": "user",
                "content": "Explain Python decorators",
                "timestamp": "2025-01-15T10:00:00.000Z",
            },
            {
                "type": "gemini",
                "content": "Python decorators are functions that modify the behavior of other functions.",
                "timestamp": "2025-01-15T10:00:10.000Z",
                "model": "gemini-2.5-pro",
                "thoughts": [
                    {
                        "subject": "Understanding Request",
                        "description": "User wants explanation of decorators",
                        "timestamp": "2025-01-15T10:00:05.000Z",
                    },
                    {
                        "subject": "Formulating Response",
                        "description": "Preparing clear explanation with examples",
                        "timestamp": "2025-01-15T10:00:08.000Z",
                    },
                ],
                "tokens": {"input": 50, "output": 100, "total": 150},
            },
        ]
        make_gemini_session(tmp_path, "hash789ghi", "thoughts-test", messages)
        outdir = tmp_path / "output"
        outdir.mkdir()

        env = setup_env(tmp_path)

        result = run_cli(
            ["--agent", "gemini", "export", "--local", "-o", str(outdir), "--force", "--aw"],
            env=env,
        )
        assert result.returncode == 0, f"Export failed: {result.stderr}"

        md_files = list(outdir.rglob("*.md"))
        assert len(md_files) >= 1
        content = md_files[0].read_text()

        # Verify thoughts are included
        assert "Reasoning" in content, "Should include Reasoning section"
        assert "Understanding Request" in content, "Should include thought subjects"


# ============================================================================
# Gemini Stats Tests
# ============================================================================


class TestGeminiStats:
    """E2E tests for Gemini stats sync and display."""

    def test_stats_sync_includes_gemini_sessions(self, tmp_path: Path):
        """stats --sync should include Gemini sessions in database."""
        make_gemini_session(tmp_path, "hash123abc", "stats-test-1")
        make_gemini_session(tmp_path, "hash456def", "stats-test-2")

        env = setup_env(tmp_path)

        # Sync sessions to database
        result = run_cli(["stats", "--sync", "--aw"], env=env)
        assert result.returncode == 0, f"Sync failed: {result.stderr}"

        # Verify sessions are in database
        db_path = tmp_path / ".claude-history" / "metrics.db"
        assert db_path.exists(), "Metrics DB should be created"

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT agent, workspace FROM sessions").fetchall()
        conn.close()

        gemini_rows = [r for r in rows if r["agent"] == "gemini"]
        assert len(gemini_rows) >= 2, f"Should have at least 2 Gemini sessions, got: {gemini_rows}"

    def test_stats_sync_stores_token_data(self, tmp_path: Path):
        """stats --sync should store per-message token data for Gemini."""
        # Create session with known token values
        messages = [
            {
                "type": "user",
                "content": "Hello",
                "timestamp": "2025-01-15T10:00:00.000Z",
            },
            {
                "type": "gemini",
                "content": "Hi there!",
                "timestamp": "2025-01-15T10:00:05.000Z",
                "model": "gemini-2.5-flash",
                "tokens": {"input": 100, "output": 50, "total": 150},
            },
        ]
        make_gemini_session(tmp_path, "hashtoken123", "token-test", messages)

        env = setup_env(tmp_path)

        result = run_cli(["stats", "--sync", "--aw"], env=env)
        assert result.returncode == 0, f"Sync failed: {result.stderr}"

        # Verify token data is in messages table
        db_path = tmp_path / ".claude-history" / "metrics.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT input_tokens, output_tokens FROM messages WHERE type = 'assistant'"
        ).fetchall()
        conn.close()

        assert len(rows) >= 1, "Should have at least one assistant message"
        # Verify tokens were stored (at least one message has our values)
        token_found = any(r["input_tokens"] == 100 and r["output_tokens"] == 50 for r in rows)
        assert token_found, f"Token data not found in messages: {[dict(r) for r in rows]}"


# ============================================================================
# Mixed Agent Tests
# ============================================================================


class TestMixedAgentsGemini:
    """E2E tests for mixed agent filtering including Gemini."""

    def test_agent_auto_includes_gemini(self, tmp_path: Path):
        """--agent auto should include Gemini sessions when present."""
        make_gemini_session(tmp_path, "hash123abc", "gemini-session")
        make_claude_session(tmp_path, "-home-user-myproject", "claude-session")

        env = setup_env(tmp_path)

        result = run_cli(["--agent", "auto", "lss", "--local", "--aw"], env=env)
        assert result.returncode == 0, f"Expected success: {result.stderr}"
        # Should have both in output
        assert result.stdout.strip(), "Should have session output"

    def test_stats_sync_all_agents(self, tmp_path: Path):
        """stats --sync should sync all agent types."""
        make_gemini_session(tmp_path, "hash123abc", "gemini-sync")
        make_claude_session(tmp_path, "-home-user-myproject", "claude-sync")

        env = setup_env(tmp_path)

        result = run_cli(["stats", "--sync", "--aw"], env=env)
        assert result.returncode == 0, f"Sync failed: {result.stderr}"

        # Verify both agents are in database
        db_path = tmp_path / ".claude-history" / "metrics.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT DISTINCT agent FROM sessions").fetchall()
        conn.close()

        agents = {r["agent"] for r in rows}
        assert "gemini" in agents, f"Gemini should be in agents: {agents}"
        assert "claude" in agents, f"Claude should be in agents: {agents}"


# ============================================================================
# Gemini Workspace Tests
# ============================================================================


class TestGeminiWorkspaces:
    """E2E tests for Gemini workspace handling."""

    def test_gemini_sessions_have_workspace(self, tmp_path: Path):
        """Gemini sessions should have workspace field (from project hash)."""
        make_gemini_session(tmp_path, "abc123def456", "workspace-test")

        env = setup_env(tmp_path)

        result = run_cli(["--agent", "gemini", "lss", "--local", "--aw"], env=env)
        assert result.returncode == 0
        # Workspace should show truncated hash
        assert "[hash:" in result.stdout or "abc123" in result.stdout.lower()

    def test_lsw_agent_gemini_lists_workspaces(self, tmp_path: Path):
        """lsw --agent gemini should list Gemini workspaces (project hashes)."""
        make_gemini_session(tmp_path, "hash111aaa", "session-a")
        make_gemini_session(tmp_path, "hash222bbb", "session-b")

        env = setup_env(tmp_path)

        result = run_cli(["--agent", "gemini", "lsw", "--local"], env=env)
        assert result.returncode == 0
        # Should list workspace hashes
        assert result.stdout.strip(), "Should have workspace output"
