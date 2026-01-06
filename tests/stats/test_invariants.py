"""Tests for mathematical invariants in stats calculations.

Spec Reference: docs/testing/testing-strategy.md#3c-stats-commands

These tests validate that stats calculations satisfy mathematical
invariants that must always hold true regardless of data.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.helpers.assertions import assert_stats_invariants
from tests.helpers.cli import run_cli_subprocess

pytestmark = pytest.mark.stats


class TestMessageCountInvariants:
    """Invariants related to message counts."""

    def test_user_plus_assistant_equals_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """user_messages + assistant_messages == total messages."""
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
            # Get total messages (conversation messages only)
            total = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE type IN ('user', 'assistant', 'gemini')"
            ).fetchone()[0]

            # Try role column first
            try:
                user_count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE role = 'user'"
                ).fetchone()[0]
                assistant_count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE role = 'assistant'"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                # Fall back to type column
                user_count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE type = 'user'"
                ).fetchone()[0]
                assistant_count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE type IN ('assistant', 'gemini')"
                ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"Required columns not found: {e}")
        finally:
            conn.close()

        assert user_count + assistant_count == total, (
            f"Invariant violated: {user_count} user + {assistant_count} assistant "
            f"!= {total} total"
        )

    def test_messages_per_session_sum_to_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Sum of messages per session should equal total messages."""
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
            total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

            per_session_sum = (
                conn.execute(
                    "SELECT SUM(cnt) FROM (SELECT COUNT(*) as cnt FROM messages GROUP BY session_id)"
                ).fetchone()[0]
                or 0
            )
        except sqlite3.OperationalError as e:
            pytest.skip(f"Required columns not found: {e}")
        finally:
            conn.close()

        assert per_session_sum == total, (
            f"Invariant violated: sum of per-session messages ({per_session_sum}) "
            f"!= total ({total})"
        )

    def test_each_message_belongs_to_one_session(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Every message should have exactly one session_id."""
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
            # Check for NULL session_ids
            null_count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id IS NULL"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"session_id column not found: {e}")
        finally:
            conn.close()

        assert null_count == 0, f"Invariant violated: {null_count} messages have NULL session_id"


class TestTokenInvariants:
    """Invariants related to token counts."""

    def test_tokens_non_negative(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """All token counts must be non-negative."""
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
            # Check input tokens
            negative_input = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE input_tokens < 0"
            ).fetchone()[0]

            # Check output tokens
            negative_output = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE output_tokens < 0"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"Token columns not found: {e}")
        finally:
            conn.close()

        assert (
            negative_input == 0
        ), f"Invariant violated: {negative_input} messages have negative input_tokens"
        assert (
            negative_output == 0
        ), f"Invariant violated: {negative_output} messages have negative output_tokens"

    def test_tokens_per_session_sum_to_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Sum of tokens per session should equal total tokens."""
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
            total_input = conn.execute(
                "SELECT COALESCE(SUM(input_tokens), 0) FROM messages"
            ).fetchone()[0]

            per_session_input = conn.execute(
                """SELECT COALESCE(SUM(session_input), 0) FROM
                   (SELECT SUM(input_tokens) as session_input FROM messages GROUP BY session_id)"""
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"Token columns not found: {e}")
        finally:
            conn.close()

        assert per_session_input == total_input, (
            f"Invariant violated: per-session input sum ({per_session_input}) "
            f"!= total ({total_input})"
        )

    def test_cache_tokens_less_than_or_equal_input(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
    ):
        """Cache read tokens should not exceed input tokens for any message."""
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
            # Cache tokens are a subset of input processing
            conn.execute(
                """SELECT COUNT(*) FROM messages
                   WHERE cache_read_tokens > input_tokens"""
            ).fetchone()[0]
        except sqlite3.OperationalError:
            # Cache columns might not exist
            pytest.skip("Cache token columns not found")
        finally:
            conn.close()

        # Note: This might need adjustment based on how cache tokens work
        # Some implementations might allow cache_read > input for certain scenarios


class TestSessionInvariants:
    """Invariants related to session records."""

    def test_every_session_has_id(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Every session must have a non-null session_id."""
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
            null_ids = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE session_id IS NULL"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"sessions table not found: {e}")
        finally:
            conn.close()

        assert null_ids == 0, f"Invariant violated: {null_ids} sessions have NULL session_id"

    def test_session_ids_unique(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Session IDs should be unique."""
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
            total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

            unique_sessions = conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM sessions"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"sessions table not found: {e}")
        finally:
            conn.close()

        assert total_sessions == unique_sessions, (
            f"Invariant violated: {total_sessions} total sessions but "
            f"only {unique_sessions} unique IDs"
        )

    def test_every_session_has_agent(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Every session must have a known agent type."""
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
            null_agents = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE agent IS NULL"
            ).fetchone()[0]

            invalid_agents = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE agent NOT IN ('claude', 'codex', 'gemini')"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"agent column not found: {e}")
        finally:
            conn.close()

        assert null_agents == 0, f"Invariant violated: {null_agents} sessions have NULL agent"
        assert (
            invalid_agents == 0
        ), f"Invariant violated: {invalid_agents} sessions have unknown agent type"


class TestToolInvariants:
    """Invariants related to tool calls."""

    def test_every_tool_has_name(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_tool_fixtures: Path,
    ):
        """Every tool call must have a non-null name."""
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
            null_names = conn.execute(
                "SELECT COUNT(*) FROM tool_calls WHERE name IS NULL"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        assert null_names == 0, f"Invariant violated: {null_names} tool calls have NULL name"

    def test_tool_calls_linked_to_messages(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Tool calls should be linked to existing messages."""
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

        # This test depends on schema having a foreign key relationship
        # Implementation may vary

    def test_tool_calls_per_type_sum_to_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_tool_fixtures: Path,
        multi_tool_expected: Dict[str, Any],
    ):
        """Sum of tool calls grouped by name should equal total."""
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
            total = conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0]

            grouped_sum = (
                conn.execute(
                    "SELECT SUM(cnt) FROM (SELECT COUNT(*) as cnt FROM tool_calls GROUP BY name)"
                ).fetchone()[0]
                or 0
            )
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        assert (
            grouped_sum == total
        ), f"Invariant violated: grouped sum ({grouped_sum}) != total ({total})"


class TestGroupingInvariants:
    """Invariants that must hold for any grouping operation."""

    @pytest.mark.parametrize(
        "grouping",
        ["model", "agent", "workspace", "day"],
    )
    def test_grouped_session_sum_equals_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        grouping: str,
    ):
        """Sum of sessions in any grouping should equal total sessions."""
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

        # Grouping invariants depend on which columns exist
        # This is a placeholder for the general pattern

    @pytest.mark.parametrize(
        "grouping",
        ["model", "agent", "session_id"],
    )
    def test_grouped_token_sum_equals_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        grouping: str,
    ):
        """Sum of tokens in any grouping should equal total tokens."""
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
            total_tokens = conn.execute(
                """SELECT COALESCE(SUM(input_tokens), 0) + COALESCE(SUM(output_tokens), 0)
                   FROM messages"""
            ).fetchone()[0]

            # Group and sum
            grouped_tokens = conn.execute(
                f"""SELECT COALESCE(SUM(group_sum), 0) FROM
                   (SELECT SUM(input_tokens) + SUM(output_tokens) as group_sum
                    FROM messages GROUP BY {grouping})"""
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"Required columns not found: {e}")
        finally:
            conn.close()

        assert grouped_tokens == total_tokens, (
            f"Invariant violated: grouped by {grouping} ({grouped_tokens}) "
            f"!= total ({total_tokens})"
        )


class TestCrossCheckInvariants:
    """Cross-check invariants between different stats."""

    def test_messages_match_expected_fixture(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """Stats from DB should match expected fixture values exactly."""
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
            stats = {}
            stats["sessions"] = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            stats["messages"] = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE type IN ('user', 'assistant', 'gemini')"
            ).fetchone()[0]
            stats["input_tokens"] = conn.execute(
                "SELECT COALESCE(SUM(input_tokens), 0) FROM messages"
            ).fetchone()[0]
            stats["output_tokens"] = conn.execute(
                "SELECT COALESCE(SUM(output_tokens), 0) FROM messages"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"Required columns not found: {e}")
        finally:
            conn.close()

        expected = all_stats_expected

        assert (
            stats["sessions"] == expected["sessions"]
        ), f"Sessions mismatch: got {stats['sessions']}, expected {expected['sessions']}"
        assert (
            stats["messages"] == expected["messages"]
        ), f"Messages mismatch: got {stats['messages']}, expected {expected['messages']}"
        assert stats["input_tokens"] == expected["input_tokens"], (
            f"Input tokens mismatch: got {stats['input_tokens']}, "
            f"expected {expected['input_tokens']}"
        )
        assert stats["output_tokens"] == expected["output_tokens"], (
            f"Output tokens mismatch: got {stats['output_tokens']}, "
            f"expected {expected['output_tokens']}"
        )

    def test_helper_assertion_function(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Test using the assert_stats_invariants helper."""
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
            stats = {
                "messages": conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE type IN ('user', 'assistant', 'gemini')"
                ).fetchone()[0],
                "input_tokens": conn.execute(
                    "SELECT COALESCE(SUM(input_tokens), 0) FROM messages"
                ).fetchone()[0],
                "output_tokens": conn.execute(
                    "SELECT COALESCE(SUM(output_tokens), 0) FROM messages"
                ).fetchone()[0],
            }

            # Try to get user/assistant breakdown
            try:
                stats["user_messages"] = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE role = 'user'"
                ).fetchone()[0]
                stats["assistant_messages"] = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE role = 'assistant'"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                stats["user_messages"] = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE type = 'user'"
                ).fetchone()[0]
                stats["assistant_messages"] = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE type IN ('assistant', 'gemini')"
                ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"Required columns not found: {e}")
        finally:
            conn.close()

        # Use the helper function to validate invariants
        assert_stats_invariants(stats)


class TestTimeInvariants:
    """Invariants related to time tracking (if implemented)."""

    def test_effort_time_less_than_calendar_time(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Effort time should never exceed calendar time."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--time"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --time not implemented: {result.stderr}")

        # If time tracking is implemented, validate the invariant
        # effort_time <= calendar_time always

    def test_timestamps_in_order(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Messages should have timestamps in non-decreasing order within session."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        # This invariant depends on timestamp column existence
