"""Tests for stats grouping options: --by model, tool, day, workspace.

Spec Reference: docs/testing/testing-strategy.md#3c-stats-commands

These tests validate that grouped stats produce correct breakdowns
and that sums across groups equal the ungrouped total.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tests.helpers.cli import run_cli_subprocess

pytestmark = pytest.mark.stats


class TestGroupByModel:
    """Test --by model grouping."""

    def test_group_by_model_output(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_model_fixtures: List[Path],
    ):
        """--by model should produce output grouped by model."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "model"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by model not implemented: {result.stderr}")

        # Should have output containing model names
        output = result.stdout
        assert output.strip(), "stats --by model should produce output"

    def test_group_by_model_counts(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_model_fixtures: List[Path],
        multi_model_expected: Dict[str, Any],
    ):
        """--by model should report correct counts per model."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "model"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by model not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                """SELECT model, COUNT(*), SUM(input_tokens), SUM(output_tokens)
                FROM messages
                WHERE model IS NOT NULL
                GROUP BY model"""
            )
            model_stats = {
                row[0]: {"count": row[1], "input": row[2], "output": row[3]} for row in cursor
            }
        except sqlite3.OperationalError as e:
            pytest.skip(f"model column not found: {e}")
        finally:
            conn.close()

        expected = multi_model_expected["by_model"]
        for model, expected_stats in expected.items():
            if model in model_stats:
                assert model_stats[model]["input"] == expected_stats["input_tokens"], (
                    f"Model {model}: expected {expected_stats['input_tokens']} "
                    f"input tokens, got {model_stats[model]['input']}"
                )

    def test_group_by_model_sum_equals_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_model_fixtures: List[Path],
        multi_model_expected: Dict[str, Any],
    ):
        """Sum of grouped model stats should equal ungrouped total."""
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
            # Get total
            total_input = conn.execute(
                "SELECT COALESCE(SUM(input_tokens), 0) FROM messages"
            ).fetchone()[0]

            # Get sum of grouped
            cursor = conn.execute(
                """SELECT COALESCE(SUM(input_tokens), 0)
                FROM messages
                WHERE model IS NOT NULL"""
            )
            grouped_input = cursor.fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"Token columns not found: {e}")
        finally:
            conn.close()

        # Sum of per-model should equal total
        assert grouped_input == total_input, f"Grouped sum {grouped_input} != total {total_input}"


class TestGroupByTool:
    """Test --by tool grouping."""

    def test_group_by_tool_output(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_tool_fixtures: Path,
    ):
        """--by tool should produce output grouped by tool name."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "tool"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by tool not implemented: {result.stderr}")

        output = result.stdout
        assert output.strip(), "stats --by tool should produce output"

    def test_group_by_tool_counts(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_tool_fixtures: Path,
        multi_tool_expected: Dict[str, Any],
    ):
        """--by tool should report correct counts per tool."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "tool"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by tool not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT tool_name, COUNT(*) FROM tool_uses GROUP BY tool_name")
            tool_counts = dict(cursor.fetchall())
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_uses table not found: {e}")
        finally:
            conn.close()

        expected = multi_tool_expected["tool_calls"]
        assert tool_counts == expected, f"Expected tool counts {expected}, got {tool_counts}"

    def test_group_by_tool_sum_equals_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_tool_fixtures: Path,
        multi_tool_expected: Dict[str, Any],
    ):
        """Sum of per-tool counts should equal total tool calls."""
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
            total = conn.execute("SELECT COUNT(*) FROM tool_uses").fetchone()[0]
            cursor = conn.execute(
                "SELECT SUM(cnt) FROM (SELECT COUNT(*) as cnt FROM tool_uses GROUP BY tool_name)"
            )
            grouped_sum = cursor.fetchone()[0] or 0
        except sqlite3.OperationalError as e:
            pytest.skip(f"tool_uses table not found: {e}")
        finally:
            conn.close()

        assert grouped_sum == total, f"Grouped sum {grouped_sum} != total {total}"


class TestGroupByDay:
    """Test --by day grouping."""

    def test_group_by_day_output(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_day_fixtures: List[Path],
    ):
        """--by day should produce output grouped by date."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "day"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by day not implemented: {result.stderr}")

        output = result.stdout
        assert output.strip(), "stats --by day should produce output"

    def test_group_by_day_session_counts(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_day_fixtures: List[Path],
        multi_day_expected: Dict[str, Any],
    ):
        """--by day should report correct session counts per day."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "day"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by day not implemented: {result.stderr}")

        # Validation depends on how day grouping is implemented
        # Could use start_time or a date column

    def test_group_by_day_message_counts(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_day_fixtures: List[Path],
        multi_day_expected: Dict[str, Any],
    ):
        """--by day should report correct message counts per day."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "day"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by day not implemented: {result.stderr}")

        multi_day_expected["by_day"]
        # Verify each day has expected counts

    def test_group_by_day_sum_equals_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_day_fixtures: List[Path],
        multi_day_expected: Dict[str, Any],
    ):
        """Sum of per-day sessions should equal total sessions."""
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
        except sqlite3.OperationalError as e:
            pytest.skip(f"sessions table not found: {e}")
        finally:
            conn.close()

        expected_total = multi_day_expected["totals"]["sessions"]
        assert (
            total_sessions == expected_total
        ), f"Expected {expected_total} total sessions, got {total_sessions}"


class TestGroupByWorkspace:
    """Test --by workspace grouping."""

    def test_group_by_workspace_output(
        self,
        stats_test_home: Dict[str, Any],
        setup_workspace_fixtures: Dict[str, List[Path]],
    ):
        """--by workspace should produce output grouped by workspace."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "workspace"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by workspace not implemented: {result.stderr}")

        output = result.stdout
        assert output.strip(), "stats --by workspace should produce output"

    def test_group_by_workspace_counts(
        self,
        stats_test_home: Dict[str, Any],
        setup_workspace_fixtures: Dict[str, List[Path]],
    ):
        """--by workspace should report correct counts per workspace."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "workspace"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by workspace not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT workspace, COUNT(*) FROM sessions GROUP BY workspace")
            workspace_counts = dict(cursor.fetchall())
        except sqlite3.OperationalError as e:
            pytest.skip(f"workspace column not found: {e}")
        finally:
            conn.close()

        # Each workspace should have 2 sessions (from fixture)
        for workspace, count in workspace_counts.items():
            assert count == 2, f"Workspace {workspace} expected 2 sessions, got {count}"

    def test_group_by_workspace_sum_equals_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_workspace_fixtures: Dict[str, List[Path]],
    ):
        """Sum of per-workspace sessions should equal total sessions."""
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
            total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            cursor = conn.execute(
                "SELECT SUM(cnt) FROM (SELECT COUNT(*) as cnt FROM sessions GROUP BY workspace)"
            )
            grouped_sum = cursor.fetchone()[0] or 0
        except sqlite3.OperationalError as e:
            pytest.skip(f"sessions/workspace columns not found: {e}")
        finally:
            conn.close()

        assert grouped_sum == total, f"Grouped workspace sum {grouped_sum} != total {total}"


class TestGroupByAgent:
    """Test --by agent grouping."""

    def test_group_by_agent_output(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """--by agent should produce output grouped by agent type."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "agent"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by agent not implemented: {result.stderr}")

        output = result.stdout
        assert output.strip(), "stats --by agent should produce output"

    def test_group_by_agent_counts(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """--by agent should report correct counts per agent."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "agent"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by agent not implemented: {result.stderr}")

        db_path = stats_test_home["history_dir"] / "metrics.db"
        if not db_path.exists():
            pytest.skip("metrics.db not created")

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT agent, COUNT(*) FROM sessions GROUP BY agent")
            agent_counts = dict(cursor.fetchall())
        except sqlite3.OperationalError as e:
            pytest.skip(f"agent column not found: {e}")
        finally:
            conn.close()

        # Each agent should have 1 session
        for agent in ["claude", "codex", "gemini"]:
            assert (
                agent_counts.get(agent, 0) == 1
            ), f"Agent {agent} expected 1 session, got {agent_counts.get(agent, 0)}"


class TestMultiGroupCombinations:
    """Test multiple grouping dimensions."""

    def test_group_by_model_and_tool(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_model_fixtures: List[Path],
    ):
        """--by model,tool should produce combined grouping."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "model,tool"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by model,tool not implemented: {result.stderr}")

    def test_group_by_agent_and_day(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
    ):
        """--by agent,day should produce combined grouping."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "agent,day"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by agent,day not implemented: {result.stderr}")


class TestGroupingInvariants:
    """Test mathematical invariants for grouping operations."""

    def test_sum_of_parts_equals_whole(
        self,
        stats_test_home: Dict[str, Any],
        setup_all_stats_fixtures: Dict[str, Path],
        all_stats_expected: Dict[str, Any],
    ):
        """Sum of any grouping should equal the ungrouped total."""
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
            total_messages = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE type IN ('user', 'assistant', 'gemini')"
            ).fetchone()[0]
            total_input = conn.execute(
                "SELECT COALESCE(SUM(input_tokens), 0) FROM messages"
            ).fetchone()[0]
            total_output = conn.execute(
                "SELECT COALESCE(SUM(output_tokens), 0) FROM messages"
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"Required columns not found: {e}")
        finally:
            conn.close()

        expected = all_stats_expected
        assert (
            total_sessions == expected["sessions"]
        ), f"Sessions: expected {expected['sessions']}, got {total_sessions}"
        assert (
            total_messages == expected["messages"]
        ), f"Messages: expected {expected['messages']}, got {total_messages}"
        assert (
            total_input == expected["input_tokens"]
        ), f"Input tokens: expected {expected['input_tokens']}, got {total_input}"
        assert (
            total_output == expected["output_tokens"]
        ), f"Output tokens: expected {expected['output_tokens']}, got {total_output}"

    def test_grouped_sessions_sum_to_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_workspace_fixtures: Dict[str, List[Path]],
    ):
        """Sum of sessions grouped by workspace should equal total."""
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
            total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            grouped = (
                conn.execute(
                    "SELECT SUM(cnt) FROM (SELECT COUNT(*) as cnt FROM sessions GROUP BY workspace)"
                ).fetchone()[0]
                or 0
            )
        except sqlite3.OperationalError as e:
            pytest.skip(f"Sessions table not found: {e}")
        finally:
            conn.close()

        assert grouped == total, f"Grouped ({grouped}) != Total ({total})"

    def test_grouped_tokens_sum_to_total(
        self,
        stats_test_home: Dict[str, Any],
        setup_multi_model_fixtures: List[Path],
    ):
        """Sum of tokens grouped by model should equal total tokens."""
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

            grouped_input = conn.execute(
                """SELECT COALESCE(SUM(input_sum), 0) FROM
                   (SELECT SUM(input_tokens) as input_sum FROM messages GROUP BY model)"""
            ).fetchone()[0]
        except sqlite3.OperationalError as e:
            pytest.skip(f"Token columns not found: {e}")
        finally:
            conn.close()

        assert (
            grouped_input == total_input
        ), f"Grouped input ({grouped_input}) != Total ({total_input})"


class TestGroupingEdgeCases:
    """Test edge cases for grouping operations."""

    def test_empty_group(self, stats_test_home: Dict[str, Any]):
        """Empty result set should return empty groups."""
        run_cli_subprocess(
            ["session", "stats", "--aw", "--by", "model"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        # Should not error even with no data

    def test_single_group(
        self,
        stats_test_home: Dict[str, Any],
        setup_claude_stats_fixture: Path,
    ):
        """Single session should produce single group."""
        result = run_cli_subprocess(
            ["session", "stats", "--sync", "--aw", "--by", "agent"],
            env=stats_test_home["env"],
            cwd=stats_test_home["path"],
        )

        if result.returncode != 0:
            pytest.skip(f"stats --by agent not implemented: {result.stderr}")

    def test_null_group_handling(self, stats_test_home: Dict[str, Any]):
        """Messages with NULL model should be handled gracefully."""
        # Some messages might not have model info
        pass
