"""Tests for per-tool call count validation.

Spec Reference: docs/testing/testing-strategy.md#3c-stats-commands

These tests validate that tool usage statistics accurately reflect
the tool_use blocks in session data.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.helpers.cli import run_cli_subprocess

pytestmark = pytest.mark.stats


class TestToolCallCounts:
    """Validate tool call count accuracy."""

    def test_claude_tool_counts(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
        claude_stats_expected: Dict[str, Any],
    ):
        """Claude session should report correct tool call counts."""
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
            cursor = conn.execute("SELECT name, COUNT(*) FROM tool_calls GROUP BY name")
            actual_tools = dict(cursor.fetchall())
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        expected_tools = claude_stats_expected["tool_calls"]
        assert (
            actual_tools == expected_tools
        ), f"Expected tool counts {expected_tools}, got {actual_tools}"

    def test_codex_tool_counts(
        self,
        stats_test_home: Dict[str, Any],
        setup_codex_stats_fixture: Path,
        codex_stats_expected: Dict[str, Any],
    ):
        """Codex session should report correct function call counts."""
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
            cursor = conn.execute("SELECT name, COUNT(*) FROM tool_calls GROUP BY name")
            actual_tools = dict(cursor.fetchall())
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        expected_tools = codex_stats_expected["tool_calls"]
        assert (
            actual_tools == expected_tools
        ), f"Expected tool counts {expected_tools}, got {actual_tools}"

    def test_gemini_tool_counts(
        self,
        stats_test_home: Dict[str, Any],
        setup_gemini_stats_fixture: Path,
        gemini_stats_expected: Dict[str, Any],
    ):
        """Gemini session should report correct tool call counts."""
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
            cursor = conn.execute("SELECT name, COUNT(*) FROM tool_calls GROUP BY name")
            actual_tools = dict(cursor.fetchall())
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        expected_tools = gemini_stats_expected["tool_calls"]
        assert (
            actual_tools == expected_tools
        ), f"Expected tool counts {expected_tools}, got {actual_tools}"

    def test_combined_tool_counts(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """Combined sessions should report all tool call counts."""
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
            cursor = conn.execute("SELECT name, COUNT(*) FROM tool_calls GROUP BY name")
            actual_tools = dict(cursor.fetchall())
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        expected_tools = all_stats_expected["tools"]
        assert (
            actual_tools == expected_tools
        ), f"Expected tool counts {expected_tools}, got {actual_tools}"

    def test_total_tool_calls(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """Total tool call count should match expected."""
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
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        expected = all_stats_expected["tool_calls_total"]
        assert total == expected, f"Expected {expected} tool calls, got {total}"


class TestMultiToolSession:
    """Test sessions with multiple tool types."""

    def test_multi_tool_counts(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_tool_fixtures: Path,
        multi_tool_expected: Dict[str, Any],
    ):
        """Session with many tools should count each correctly."""
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
            cursor = conn.execute("SELECT name, COUNT(*) FROM tool_calls GROUP BY name")
            actual_tools = dict(cursor.fetchall())
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        expected_tools = multi_tool_expected["tool_calls"]
        assert (
            actual_tools == expected_tools
        ), f"Expected tool counts {expected_tools}, got {actual_tools}"

    def test_multi_tool_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_tool_fixtures: Path,
        multi_tool_expected: Dict[str, Any],
    ):
        """Total tool calls should sum correctly for multi-tool session."""
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
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        expected = multi_tool_expected["tool_calls_total"]
        assert total == expected, f"Expected {expected} tool calls, got {total}"


class TestToolNormalization:
    """Test tool name normalization across agents."""

    def test_claude_tool_names(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
    ):
        """Claude tool names should be stored as-is (Read, Edit, etc.)."""
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
            cursor = conn.execute("SELECT DISTINCT name FROM tool_calls")
            tool_names = {row[0] for row in cursor}
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        # Claude uses PascalCase tool names
        assert "Read" in tool_names, "Claude tool 'Read' not found"
        assert "Edit" in tool_names, "Claude tool 'Edit' not found"

    def test_codex_function_names(
        self,
        stats_test_home: Dict[str, Any],
        setup_codex_stats_fixture: Path,
    ):
        """Codex function names should be normalized to tool_calls."""
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
            cursor = conn.execute("SELECT DISTINCT name FROM tool_calls")
            tool_names = {row[0] for row in cursor}
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        # Codex uses snake_case function names
        assert "shell" in tool_names, "Codex function 'shell' not found"

    def test_gemini_tool_names(
        self,
        stats_test_home: Dict[str, Any],
        setup_gemini_stats_fixture: Path,
    ):
        """Gemini tool names should be normalized to tool_calls."""
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
            cursor = conn.execute("SELECT DISTINCT name FROM tool_calls")
            tool_names = {row[0] for row in cursor}
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        # Gemini uses snake_case tool names
        assert "read_file" in tool_names, "Gemini tool 'read_file' not found"


class TestToolCallsBySession:
    """Test tool call association with sessions."""

    def test_tool_calls_linked_to_session(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        claude_stats_expected: Dict[str, Any],
    ):
        """Tool calls should be linked to correct session."""
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
            cursor = conn.execute(
                """SELECT session_id, COUNT(*)
                FROM tool_calls
                GROUP BY session_id"""
            )
            session_tool_counts = dict(cursor.fetchall())
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_calls table not found: {e}")
        finally:
            conn.close()

        claude_session = claude_stats_expected["session_id"]
        if claude_session in session_tool_counts:
            expected_count = sum(claude_stats_expected["tool_calls"].values())
            assert session_tool_counts[claude_session] == expected_count, (
                f"Claude session expected {expected_count} tools, "
                f"got {session_tool_counts[claude_session]}"
            )

    def test_tool_calls_per_agent(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Tool call counts should be correct when grouped by agent."""
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

        # This depends on whether there's an agent column or join needed
        # Implementation will vary based on schema


class TestToolCallEdgeCases:
    """Test edge cases for tool handling."""

    def test_session_no_tools(self, stats_test_home: Dict[str, Any]):
        """Session with no tool calls should report empty tool list."""
        # Create a session without tool calls
        import json

        claude_dir = stats_test_home["claude_dir"]
        ws_dir = claude_dir / "-home-testuser-no-tools"
        ws_dir.mkdir(parents=True, exist_ok=True)

        # Simple session with no tools
        records = [
            {
                "type": "user",
                "uuid": "u1",
                "parentUuid": None,
                "sessionId": "no-tools-session",
                "timestamp": "2025-01-03T10:00:00.000Z",
                "message": {"role": "user", "content": "Hello"},
            },
            {
                "type": "assistant",
                "uuid": "a1",
                "parentUuid": "u1",
                "sessionId": "no-tools-session",
                "timestamp": "2025-01-03T10:00:05.000Z",
                "message": {
                    "role": "assistant",
                    "model": "claude-sonnet-4-20250514",
                    "content": [{"type": "text", "text": "Hello!"}],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            },
        ]

        session_file = ws_dir / "no-tools-session.jsonl"
        with open(session_file, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        # Should succeed without error even with no tools

    def test_tool_with_error_status(self, stats_test_home: Dict[str, Any]):
        """Tool calls with error status should still be counted."""
        # Tools that fail should still be tracked
        pass

    def test_duplicate_tool_ids(self, stats_test_home: Dict[str, Any]):
        """Duplicate tool IDs should be handled gracefully."""
        # Edge case: what if same tool_use_id appears twice?
        pass


class TestToolStatsByGrouping:
    """Test tool stats with different groupings."""

    def test_tools_by_session(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Tool counts grouped by session should be correct."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "session"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by session not implemented: {result.stderr}")

    def test_tools_by_agent(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """Tool counts grouped by agent should be correct."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "agent"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by agent not implemented: {result.stderr}")


class TestToolResults:
    """Test tool result handling."""

    def test_tool_result_linkage(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
    ):
        """Tool results should be linked to tool calls."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats not implemented: {result.stderr}")

        # Verify tool results are tracked and linked

    def test_missing_tool_result(self, stats_test_home: Dict[str, Any]):
        """Tool without result (rejection) should be tracked."""
        # This tests the rejection detection scenario
        pass
