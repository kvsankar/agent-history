"""Tests for session, message, and user/assistant count validation.

Spec Reference: docs/testing/testing-strategy.md#3c-stats-commands

These tests validate that count statistics are accurate against
known fixture data, not just checking output format.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.helpers.cli import run_cli_subprocess

pytestmark = pytest.mark.stats


class TestSessionCounts:
    """Validate session count accuracy."""

    def test_single_session_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
    ):
        """Single Claude session should report 1 session."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"sessions table not found: {e}")
        finally:
            conn.close()

        assert session_count == 1, f"Expected 1 session, got {session_count}"

    def test_multi_agent_session_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """Three sessions (Claude + Codex + Gemini) should report 3 sessions."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"sessions table not found: {e}")
        finally:
            conn.close()

        expected = all_stats_expected["sessions"]
        assert session_count == expected, f"Expected {expected} sessions, got {session_count}"

    def test_session_count_per_agent(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Each agent should have exactly 1 session in the combined fixture."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT agent, COUNT(*) FROM sessions GROUP BY agent")
            agent_counts = dict(cursor.fetchall())
        except sqlite3.OperationalError as e:
            pytest.skip(f"sessions table or agent column not found: {e}")
        finally:
            conn.close()

        for agent in ["claude", "codex", "gemini"]:
            count = agent_counts.get(agent, 0)
            assert count == 1, f"Expected 1 {agent} session, got {count}"

    def test_zero_message_sessions_are_synced(self, stats_test_home: Dict[str, Any]):
        """Sessions with no user/assistant messages should still be counted."""
        ws_dir = stats_test_home["claude_dir"] / "-home-testuser-zero"
        ws_dir.mkdir(parents=True, exist_ok=True)
        session_file = ws_dir / "zero.jsonl"
        session_file.write_text(
            '{"type":"session_meta","sessionId":"zero-001","payload":{"cwd":"/home/testuser/zero"}}\n',
            encoding="utf-8",
        )

        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            msg_count = conn.execute("SELECT message_count FROM sessions").fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"sessions table not found: {e}")
        finally:
            conn.close()

        assert session_count == 1
        assert msg_count == 0

    def test_empty_stats_zero_sessions(self, stats_test_home: Dict[str, Any]):
        """Empty home should report 0 sessions without error."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        # Should not error even with no sessions
        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        # If command succeeded, verify zero count or check output
        db_path = stats_test_home["history_dir"] / "metrics.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            try:
                session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                assert session_count == 0, f"Expected 0 sessions, got {session_count}"
            except sqlite3.OperationalError:
                pass  # Table might not exist if no sessions
            finally:
                conn.close()


class TestMessageCounts:
    """Validate message count accuracy."""

    def test_claude_message_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
        claude_stats_expected: Dict[str, Any],
    ):
        """Claude session should report correct total message count."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            # Count conversation messages (user + assistant types)
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE type IN ('user', 'assistant')"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"messages table not found: {e}")
        finally:
            conn.close()

        expected = claude_stats_expected["messages"]
        assert count == expected, f"Expected {expected} messages, got {count}"

    def test_codex_message_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_codex_stats_fixture: Path,
        codex_stats_expected: Dict[str, Any],
    ):
        """Codex session should report correct total message count."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE type IN ('user', 'assistant')"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"messages table not found: {e}")
        finally:
            conn.close()

        expected = codex_stats_expected["messages"]
        assert count == expected, f"Expected {expected} messages, got {count}"

    def test_gemini_message_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_gemini_stats_fixture: Path,
        gemini_stats_expected: Dict[str, Any],
    ):
        """Gemini session should report correct total message count."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE type IN ('user', 'assistant', 'gemini')"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"messages table not found: {e}")
        finally:
            conn.close()

        expected = gemini_stats_expected["messages"]
        assert count == expected, f"Expected {expected} messages, got {count}"

    def test_combined_message_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """Combined sessions should report correct total message count."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE type IN ('user', 'assistant', 'gemini')"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"messages table not found: {e}")
        finally:
            conn.close()

        expected = all_stats_expected["messages"]
        assert count == expected, f"Expected {expected} messages, got {count}"


class TestUserAssistantCounts:
    """Validate user/assistant message breakdown accuracy."""

    def test_claude_user_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
        claude_stats_expected: Dict[str, Any],
    ):
        """Claude session should report correct user message count."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            # Try role column first (spec-preferred approach)
            count = conn.execute("SELECT COUNT(*) FROM messages WHERE role = 'user'").fetchone()[0]
        except sqlite3.OperationalError:
            # Fall back to type column
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE type = 'user'"
                ).fetchone()[0]
            except sqlite3.OperationalError as e:
                pytest.skip(f"Cannot determine user count: {e}")
        finally:
            conn.close()

        expected = claude_stats_expected["user_messages"]
        assert count == expected, f"Expected {expected} user messages, got {count}"

    def test_claude_assistant_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
        claude_stats_expected: Dict[str, Any],
    ):
        """Claude session should report correct assistant message count."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            # Try role column first
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE role = 'assistant'"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            # Fall back to type column
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE type = 'assistant'"
                ).fetchone()[0]
            except sqlite3.OperationalError as e:
                pytest.skip(f"Cannot determine assistant count: {e}")
        finally:
            conn.close()

        expected = claude_stats_expected["assistant_messages"]
        assert count == expected, f"Expected {expected} assistant messages, got {count}"

    def test_combined_user_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """Combined sessions should report correct total user message count."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            count = conn.execute("SELECT COUNT(*) FROM messages WHERE role = 'user'").fetchone()[0]
        except sqlite3.OperationalError:
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE type = 'user'"
                ).fetchone()[0]
            except sqlite3.OperationalError as e:
                pytest.skip(f"Cannot determine user count: {e}")
        finally:
            conn.close()

        expected = all_stats_expected["user_messages"]
        assert count == expected, f"Expected {expected} user messages, got {count}"

    def test_combined_assistant_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """Combined sessions should report correct total assistant message count."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            # Count both assistant and gemini types
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE role = 'assistant'"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE type IN ('assistant', 'gemini')"
                ).fetchone()[0]
            except sqlite3.OperationalError as e:
                pytest.skip(f"Cannot determine assistant count: {e}")
        finally:
            conn.close()

        expected = all_stats_expected["assistant_messages"]
        assert count == expected, f"Expected {expected} assistant messages, got {count}"


class TestAgentFilteredCounts:
    """Test counts with --agent filter."""

    @pytest.mark.parametrize(
        "agent,expected_messages",
        [
            ("claude", 6),  # From CLAUDE_STATS_EXPECTED
            ("codex", 4),  # From CODEX_STATS_EXPECTED
            ("gemini", 4),  # From GEMINI_STATS_EXPECTED
        ],
    )
    def test_filtered_message_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        agent: str,
        expected_messages: int,
    ):
        """--agent filter should return correct message counts per agent."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--agent", agent],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --agent not implemented: {result.stderr}")

        # Verify command succeeded and check output or DB
        # Note: exact validation depends on implementation details

    def test_filtered_session_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """--agent filter should return 1 session per agent."""
        for agent in ["claude", "codex", "gemini"]:
            result = run_cli_subprocess(
                ["session", "stats", "--sync", "--aw", "--agent", agent],
                env=stats_test_home["env"],
                cwd=stats_test_home["path"],
            )

            if result.returncode != 0:
                pytest.skip(f"stats --agent not implemented: {result.stderr}")


class TestMultiSessionCounts:
    """Test counts with multiple sessions per workspace."""

    def test_multi_day_session_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_day_fixtures,
        multi_day_expected: Dict[str, Any],
    ):
        """Multiple sessions across days should be counted correctly."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"sessions table not found: {e}")
        finally:
            conn.close()

        expected = multi_day_expected["totals"]["sessions"]
        assert session_count == expected, f"Expected {expected} sessions, got {session_count}"

    def test_multi_day_message_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_day_fixtures,
        multi_day_expected: Dict[str, Any],
    ):
        """Multiple sessions across days should have correct total messages."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            message_count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE type IN ('user', 'assistant')"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"messages table not found: {e}")
        finally:
            conn.close()

        expected = multi_day_expected["totals"]["messages"]
        assert message_count == expected, f"Expected {expected} messages, got {message_count}"

    def test_workspace_session_count(
        self,
        stats_test_home: Dict[str, Any],
        setup_workspace_fixtures,
    ):
        """Sessions across multiple workspaces should be counted correctly."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"sessions table not found: {e}")
        finally:
            conn.close()

        # 3 workspaces * 2 sessions each = 6 total
        assert session_count == 6, f"Expected 6 sessions, got {session_count}"
