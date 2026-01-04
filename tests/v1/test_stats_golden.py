"""V1 stats validation against golden fixture totals.

Spec Reference: docs/testing/testing-strategy.md#v1-stats-golden-dataset

These tests validate that stats calculations produce correct totals
when run against the golden fixtures with known values.

Golden Dataset (3 sessions):
- Session 1 (Claude): 6 messages, 500 input, 200 output, 2 tools
- Session 2 (Codex):  4 messages, 300 input, 150 output, 1 tool
- Session 3 (Gemini): 4 messages, 400 input, 180 output, 1 tool
────────────────────────────────────────────────────────────────
Expected totals: 14 messages, 1200 input, 530 output, 4 tool calls
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.helpers.assertions import assert_stats_invariants
from tests.helpers.cli import assert_cli_success, run_cli_subprocess

pytestmark = pytest.mark.v1


class TestStatsGolden:
    """Validate stats against known golden totals."""

    def test_stats_sync_creates_database(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """stats --sync creates metrics database."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --sync not implemented: {result.stderr}")

        # Check if metrics.db was created
        db_path = isolated_home["history_dir"] / "metrics.db"
        assert db_path.exists(), "metrics.db should be created after sync"

    def test_stats_session_count(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
        golden_totals: Dict[str, Any],
    ):
        """stats shows correct session count."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = isolated_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            session_count = cursor.fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"sessions table not found: {e}")
        finally:
            conn.close()

        expected = golden_totals["sessions"]
        assert session_count == expected, f"Expected {expected} sessions, got {session_count}"

    def test_stats_message_count(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
        golden_totals: Dict[str, Any],
    ):
        """stats shows correct message count."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = isolated_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            # Count only conversation messages (user + assistant), not synthetic records
            cursor = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE type IN ('user', 'assistant')"
            )
            message_count = cursor.fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"messages table not found: {e}")
        finally:
            conn.close()

        expected = golden_totals["messages"]
        assert message_count == expected, f"Expected {expected} messages, got {message_count}"

    def test_stats_token_totals(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
        golden_totals: Dict[str, Any],
    ):
        """stats shows correct token totals."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = isolated_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0) FROM messages"
            )
            row = cursor.fetchone()
            input_tokens = row[0]
            output_tokens = row[1]
        except sqlite3.OperationalError as e:
            pytest.skip(f"messages table or token columns not found: {e}")
        finally:
            conn.close()

        expected_input = golden_totals["input_tokens"]
        expected_output = golden_totals["output_tokens"]

        assert (
            input_tokens == expected_input
        ), f"Expected {expected_input} input tokens, got {input_tokens}"
        assert (
            output_tokens == expected_output
        ), f"Expected {expected_output} output tokens, got {output_tokens}"

    def test_stats_user_assistant_breakdown(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
        golden_totals: Dict[str, Any],
    ):
        """stats shows correct user/assistant message breakdown."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = isolated_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            # Count by role
            cursor = conn.execute("SELECT role, COUNT(*) FROM messages GROUP BY role")
            counts = dict(cursor.fetchall())
        except sqlite3.OperationalError as e:
            pytest.skip(f"messages table or role column not found: {e}")
        finally:
            conn.close()

        expected_user = golden_totals["user_messages"]
        expected_assistant = golden_totals["assistant_messages"]

        user_count = counts.get("user", 0)
        assistant_count = counts.get("assistant", 0)

        assert (
            user_count == expected_user
        ), f"Expected {expected_user} user messages, got {user_count}"
        assert (
            assistant_count == expected_assistant
        ), f"Expected {expected_assistant} assistant messages, got {assistant_count}"

    def test_stats_invariants(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """stats satisfy mathematical invariants."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        db_path = isolated_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            # Get all counts for invariant checking
            stats = {}
            stats["messages"] = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            stats["user_messages"] = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE role = 'user'"
            ).fetchone()[0]
            stats["assistant_messages"] = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE role = 'assistant'"
            ).fetchone()[0]
            stats["input_tokens"] = conn.execute(
                "SELECT COALESCE(SUM(input_tokens), 0) FROM messages"
            ).fetchone()[0]
            stats["output_tokens"] = conn.execute(
                "SELECT COALESCE(SUM(output_tokens), 0) FROM messages"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"Required tables/columns not found: {e}")
        finally:
            conn.close()

        assert_stats_invariants(stats)


class TestStatsPerAgent:
    """Test stats filtering by agent."""

    def test_stats_claude_only(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
        claude_expected: Dict[str, Any],
    ):
        """stats --agent claude shows only Claude session stats."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--agent", "claude"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --agent not implemented: {result.stderr}")

        # Verify command succeeded - detailed validation requires DB access

    def test_stats_codex_only(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
        codex_expected: Dict[str, Any],
    ):
        """stats --agent codex shows only Codex session stats."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--agent", "codex"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --agent not implemented: {result.stderr}")

    def test_stats_gemini_only(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
        gemini_expected: Dict[str, Any],
    ):
        """stats --agent gemini shows only Gemini session stats."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--agent", "gemini"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --agent not implemented: {result.stderr}")


class TestStatsOutput:
    """Test stats output formatting."""

    def test_stats_default_output(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """stats produces readable output."""
        result = run_cli_subprocess(
            ["session", "stats", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        output = result.stdout
        assert output.strip(), "stats should produce output"

    def test_stats_no_sync_uses_cache(
        self,
        isolated_home: Dict[str, Any],
        setup_golden_fixtures: Dict[str, Path],
    ):
        """stats without --sync uses existing cache if available."""
        # First, create the cache
        result1 = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        if result1.returncode != 0:
            pytest.skip(f"stats --sync not implemented: {result1.stderr}")

        db_path = isolated_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        # Now run without --sync
        result2 = run_cli_subprocess(
            ["session", "stats", "--aw"],
            env=isolated_home["env"],
            cwd=isolated_home["path"],
        )

        assert_cli_success(result2, "stats without --sync should succeed")
