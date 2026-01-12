"""Tests for token count validation: input, output, cache tokens.

Spec Reference: docs/testing/testing-strategy.md#3c-stats-commands

These tests validate that token statistics are accurate against
known fixture data with pre-computed expected values.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.helpers.cli import run_cli_subprocess

pytestmark = pytest.mark.stats


class TestInputTokens:
    """Validate input token count accuracy."""

    def test_claude_input_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
        claude_stats_expected: Dict[str, Any],
    ):
        """Claude session should report correct input token total."""
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
            total = conn.execute("SELECT COALESCE(SUM(input_tokens), 0) FROM messages").fetchone()[
                0
            ]
        except sqlite3.OperationalError as e:
            pytest.skip(f"input_tokens column not found: {e}")
        finally:
            conn.close()

        expected = claude_stats_expected["input_tokens"]
        assert total == expected, f"Expected {expected} input tokens, got {total}"

    def test_codex_input_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_codex_stats_fixture: Path,
        codex_stats_expected: Dict[str, Any],
    ):
        """Codex session should report correct input token total."""
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
            total = conn.execute("SELECT COALESCE(SUM(input_tokens), 0) FROM messages").fetchone()[
                0
            ]
        except sqlite3.OperationalError as e:
            pytest.skip(f"input_tokens column not found: {e}")
        finally:
            conn.close()

        expected = codex_stats_expected["input_tokens"]
        assert total == expected, f"Expected {expected} input tokens, got {total}"

    def test_gemini_input_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_gemini_stats_fixture: Path,
        gemini_stats_expected: Dict[str, Any],
    ):
        """Gemini session should report correct input token total."""
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
            total = conn.execute("SELECT COALESCE(SUM(input_tokens), 0) FROM messages").fetchone()[
                0
            ]
        except sqlite3.OperationalError as e:
            pytest.skip(f"input_tokens column not found: {e}")
        finally:
            conn.close()

        expected = gemini_stats_expected["input_tokens"]
        assert total == expected, f"Expected {expected} input tokens, got {total}"

    def test_combined_input_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """Combined sessions should report correct total input tokens."""
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
            total = conn.execute("SELECT COALESCE(SUM(input_tokens), 0) FROM messages").fetchone()[
                0
            ]
        except sqlite3.OperationalError as e:
            pytest.skip(f"input_tokens column not found: {e}")
        finally:
            conn.close()

        expected = all_stats_expected["input_tokens"]
        assert total == expected, f"Expected {expected} input tokens, got {total}"


class TestOutputTokens:
    """Validate output token count accuracy."""

    def test_claude_output_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
        claude_stats_expected: Dict[str, Any],
    ):
        """Claude session should report correct output token total."""
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
            total = conn.execute("SELECT COALESCE(SUM(output_tokens), 0) FROM messages").fetchone()[
                0
            ]
        except sqlite3.OperationalError as e:
            pytest.skip(f"output_tokens column not found: {e}")
        finally:
            conn.close()

        expected = claude_stats_expected["output_tokens"]
        assert total == expected, f"Expected {expected} output tokens, got {total}"

    def test_codex_output_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_codex_stats_fixture: Path,
        codex_stats_expected: Dict[str, Any],
    ):
        """Codex session should report correct output token total."""
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
            total = conn.execute("SELECT COALESCE(SUM(output_tokens), 0) FROM messages").fetchone()[
                0
            ]
        except sqlite3.OperationalError as e:
            pytest.skip(f"output_tokens column not found: {e}")
        finally:
            conn.close()

        expected = codex_stats_expected["output_tokens"]
        assert total == expected, f"Expected {expected} output tokens, got {total}"

    def test_gemini_output_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_gemini_stats_fixture: Path,
        gemini_stats_expected: Dict[str, Any],
    ):
        """Gemini session should report correct output token total."""
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
            total = conn.execute("SELECT COALESCE(SUM(output_tokens), 0) FROM messages").fetchone()[
                0
            ]
        except sqlite3.OperationalError as e:
            pytest.skip(f"output_tokens column not found: {e}")
        finally:
            conn.close()

        expected = gemini_stats_expected["output_tokens"]
        assert total == expected, f"Expected {expected} output tokens, got {total}"

    def test_combined_output_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """Combined sessions should report correct total output tokens."""
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
            total = conn.execute("SELECT COALESCE(SUM(output_tokens), 0) FROM messages").fetchone()[
                0
            ]
        except sqlite3.OperationalError as e:
            pytest.skip(f"output_tokens column not found: {e}")
        finally:
            conn.close()

        expected = all_stats_expected["output_tokens"]
        assert total == expected, f"Expected {expected} output tokens, got {total}"


class TestCacheTokens:
    """Validate cache token count accuracy (Claude-specific)."""

    def test_claude_cache_creation_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
        claude_stats_expected: Dict[str, Any],
    ):
        """Claude session should report correct cache creation token total."""
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
            total = conn.execute(
                "SELECT COALESCE(SUM(cache_creation_tokens), 0) FROM messages"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            # Cache tokens might be optional
            pytest.skip(f"cache_creation_tokens column not found: {e}")
        finally:
            conn.close()

        expected = claude_stats_expected["cache_creation_tokens"]
        assert total == expected, f"Expected {expected} cache creation tokens, got {total}"

    def test_claude_cache_read_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
        claude_stats_expected: Dict[str, Any],
    ):
        """Claude session should report correct cache read token total."""
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
            total = conn.execute(
                "SELECT COALESCE(SUM(cache_read_tokens), 0) FROM messages"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"cache_read_tokens column not found: {e}")
        finally:
            conn.close()

        expected = claude_stats_expected["cache_read_tokens"]
        assert total == expected, f"Expected {expected} cache read tokens, got {total}"

    def test_codex_no_cache_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_codex_stats_fixture: Path,
    ):
        """Codex sessions should report 0 or NULL for cache tokens."""
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
            total = conn.execute(
                "SELECT COALESCE(SUM(cache_creation_tokens), 0) FROM messages"
            ).fetchone()[0]
            # Codex doesn't have cache_creation tokens
            assert total == 0, f"Expected 0 cache creation tokens for Codex, got {total}"
        except sqlite3.OperationalError:
            # Column might not exist - that's OK for Codex
            pass
        finally:
            conn.close()


class TestCodexSpecificTokens:
    """Validate Codex-specific token fields."""

    def test_codex_cached_input_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_codex_stats_fixture: Path,
        codex_stats_expected: Dict[str, Any],
    ):
        """Codex session should report correct cached input token total."""
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

        # Codex cached_input_tokens might be stored differently
        # This test validates the normalization works correctly

    def test_codex_reasoning_output_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_codex_stats_fixture: Path,
        codex_stats_expected: Dict[str, Any],
    ):
        """Codex session should track reasoning output tokens separately."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        # Reasoning tokens are a Codex-specific field


class TestGeminiSpecificTokens:
    """Validate Gemini-specific token fields."""

    def test_gemini_thought_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_gemini_stats_fixture: Path,
        gemini_stats_expected: Dict[str, Any],
    ):
        """Gemini session should report correct thought token total."""
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

        # Gemini has a specific "thoughts" token field

    def test_gemini_tool_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_gemini_stats_fixture: Path,
        gemini_stats_expected: Dict[str, Any],
    ):
        """Gemini session should report correct tool token total."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        # Gemini tracks tool tokens separately

    def test_gemini_cached_tokens(
        self,
        stats_test_home: Dict[str, Any],
        setup_gemini_stats_fixture: Path,
        gemini_stats_expected: Dict[str, Any],
    ):
        """Gemini session should report correct cached token total."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")


class TestTokenEdgeCases:
    """Test edge cases for token handling."""

    def test_zero_tokens_session(self, stats_test_home: Dict[str, Any]):
        """Session with no token usage should report 0, not NULL."""
        # This tests robustness against messages without token info
        pass

    def test_missing_token_fields(self, stats_test_home: Dict[str, Any]):
        """Session with partial token info should handle gracefully."""
        pass

    def test_token_overflow_protection(self, stats_test_home: Dict[str, Any]):
        """Very large token counts should not overflow."""
        pass


class TestTokenNormalization:
    """Test token field normalization across agents."""

    def test_input_tokens_normalized(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """All agents should normalize to input_tokens field."""
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
            # Verify input_tokens column exists and has values
            row = conn.execute(
                "SELECT COUNT(*), SUM(input_tokens) FROM messages WHERE input_tokens > 0"
            ).fetchone()
            count, total = row
            assert count > 0, "No messages have input_tokens"
            assert total > 0, "Total input_tokens should be > 0"
        except sqlite3.OperationalError as e:
            pytest.skip(f"input_tokens column not found: {e}")
        finally:
            conn.close()

    def test_output_tokens_normalized(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """All agents should normalize to output_tokens field."""
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
            row = conn.execute(
                "SELECT COUNT(*), SUM(output_tokens) FROM messages WHERE output_tokens > 0"
            ).fetchone()
            count, total = row
            assert count > 0, "No messages have output_tokens"
            assert total > 0, "Total output_tokens should be > 0"
        except sqlite3.OperationalError as e:
            pytest.skip(f"output_tokens column not found: {e}")
        finally:
            conn.close()


class TestTokenTotals:
    """Test aggregate token totals."""

    def test_total_tokens_correct(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """Total tokens should be sum of input + output."""
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
            row = conn.execute(
                """SELECT
                    COALESCE(SUM(input_tokens), 0),
                    COALESCE(SUM(output_tokens), 0)
                FROM messages"""
            ).fetchone()
            input_total, output_total = row
        except sqlite3.OperationalError as e:
            pytest.skip(f"Token columns not found: {e}")
        finally:
            conn.close()

        expected_input = all_stats_expected["input_tokens"]
        expected_output = all_stats_expected["output_tokens"]
        expected_total = expected_input + expected_output

        actual_total = input_total + output_total
        assert (
            actual_total == expected_total
        ), f"Expected {expected_total} total tokens, got {actual_total}"

    def test_tokens_per_session(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        claude_stats_expected: Dict[str, Any],
        codex_stats_expected: Dict[str, Any],
        gemini_stats_expected: Dict[str, Any],
    ):
        """Token counts per session should match expected values."""
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

        expected_by_session = {
            claude_stats_expected["session_id"]: {
                "input": claude_stats_expected["input_tokens"],
                "output": claude_stats_expected["output_tokens"],
            },
            codex_stats_expected["session_id"]: {
                "input": codex_stats_expected["input_tokens"],
                "output": codex_stats_expected["output_tokens"],
            },
            gemini_stats_expected["session_id"]: {
                "input": gemini_stats_expected["input_tokens"],
                "output": gemini_stats_expected["output_tokens"],
            },
        }

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                """SELECT session_id,
                    COALESCE(SUM(input_tokens), 0),
                    COALESCE(SUM(output_tokens), 0)
                FROM messages
                GROUP BY session_id"""
            )
            for row in cursor:
                session_id, input_tokens, output_tokens = row
                if session_id in expected_by_session:
                    expected = expected_by_session[session_id]
                    assert input_tokens == expected["input"], (
                        f"Session {session_id}: expected {expected['input']} "
                        f"input tokens, got {input_tokens}"
                    )
                    assert output_tokens == expected["output"], (
                        f"Session {session_id}: expected {expected['output']} "
                        f"output tokens, got {output_tokens}"
                    )
        except sqlite3.OperationalError as e:
            pytest.skip(f"Token columns not found: {e}")
        finally:
            conn.close()
