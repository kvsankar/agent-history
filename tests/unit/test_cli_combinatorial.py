"""Combinatorial CLI argument tests using Hypothesis.

This module tests various combinations of command-line arguments
to find edge cases and unexpected interactions between flags.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

# Path to the CLI script
CLI_PATH = Path(__file__).parent.parent.parent / "agent-history"


def run_cli_in_temp(args: list, timeout: int = None) -> subprocess.CompletedProcess:
    """Run the CLI with given arguments in a temp directory."""
    # Use longer timeout on Windows due to WSL scanning operations
    if timeout is None:
        timeout = 30 if sys.platform == "win32" else 5

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        # Set up isolated environment
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        env["USERPROFILE"] = str(tmp_path)  # Windows uses USERPROFILE
        # Skip WSL and Windows scanning in tests to avoid timeouts
        env["CLAUDE_SKIP_WSL_SCAN"] = "1"
        env["CLAUDE_SKIP_WINDOWS_SCAN"] = "1"

        # Create required directories
        (tmp_path / ".claude" / "projects").mkdir(parents=True)
        (tmp_path / ".agent-history").mkdir(parents=True)
        (tmp_path / ".codex" / "sessions").mkdir(parents=True)
        (tmp_path / ".gemini").mkdir(parents=True)

        cmd = [sys.executable, str(CLI_PATH), *args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(tmp_path),
            check=False,
        )


# ============================================================================
# Strategy definitions for CLI arguments
# ============================================================================

# Common values
workspace_patterns = st.sampled_from(["*", "myproject", "test", "nonexistent-ws-12345", ""])
agent_choices = st.sampled_from(["auto", "claude", "codex", "gemini"])
date_strings = st.sampled_from(
    [
        "2025-01-01",
        "2025-12-31",
        "2024-06-15",
        "invalid-date",
        "2025/01/01",
        "",  # Include some invalid formats
    ]
)


# ============================================================================
# lsw command tests
# ============================================================================


class TestLswCombinations:
    """Test lsw command with various flag combinations."""

    @given(
        pattern=workspace_patterns,
        use_ah=st.booleans(),
        use_local=st.booleans(),
        agent=st.one_of(st.none(), agent_choices),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_lsw_flag_combinations(self, pattern, use_ah, use_local, agent):
        """Test lsw with various flag combinations."""
        args = ["lsw"]
        if pattern:
            args.append(pattern)
        if use_ah:
            args.append("--ah")
        if use_local:
            args.append("--local")
        if agent:
            args.extend(["--agent", agent])

        result = run_cli_in_temp(args)

        # Should not crash - exit code 0 or 1 (no workspaces) are acceptable
        assert result.returncode in (
            0,
            1,
        ), f"Unexpected exit code {result.returncode}: {result.stderr}"
        # Should not have Python tracebacks
        assert "Traceback" not in result.stderr, f"Crashed with: {result.stderr}"

    @given(
        pattern=workspace_patterns,
        use_wsl=st.booleans(),
        use_windows=st.booleans(),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_lsw_wsl_windows_flags(self, pattern, use_wsl, use_windows):
        """Test that --wsl and --windows are handled gracefully."""
        args = ["lsw"]
        if pattern:
            args.append(pattern)
        if use_wsl:
            args.append("--wsl")
        if use_windows:
            args.append("--windows")

        result = run_cli_in_temp(args)

        # Should handle gracefully - even if WSL/Windows not available
        assert result.returncode in (0, 1), f"Unexpected crash: {result.stderr}"
        assert "Traceback" not in result.stderr


# ============================================================================
# lss command tests
# ============================================================================


class TestLssCombinations:
    """Test lss command with various flag combinations."""

    @given(
        workspace=workspace_patterns,
        use_ah=st.booleans(),
        use_aw=st.booleans(),
        use_this=st.booleans(),
        agent=st.one_of(st.none(), agent_choices),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_lss_scope_combinations(self, workspace, use_ah, use_aw, use_this, agent):
        """Test lss with scope flag combinations."""
        args = ["lss"]
        if workspace:
            args.append(workspace)
        if use_ah:
            args.append("--ah")
        if use_aw:
            args.append("--aw")
        if use_this:
            args.append("--this")
        if agent:
            args.extend(["--agent", agent])

        result = run_cli_in_temp(args)

        assert result.returncode in (0, 1), f"Unexpected exit code: {result.stderr}"
        assert "Traceback" not in result.stderr

    @given(
        since=date_strings,
        until=date_strings,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_lss_date_combinations(self, since, until):
        """Test lss with date filter combinations."""
        args = ["lss", "*"]  # Use wildcard to match any workspace
        if since:
            args.extend(["--since", since])
        if until:
            args.extend(["--until", until])

        result = run_cli_in_temp(args)

        # Invalid dates should produce error messages, not crashes
        assert "Traceback" not in result.stderr
        # Exit code 0, 1 (no sessions), or 1 (invalid date error) are acceptable
        assert result.returncode in (0, 1)


# ============================================================================
# export command tests
# ============================================================================


class TestExportCombinations:
    """Test export command with various flag combinations."""

    @given(
        target=workspace_patterns,
        use_ah=st.booleans(),
        use_aw=st.booleans(),
        use_minimal=st.booleans(),
        use_flat=st.booleans(),
        use_force=st.booleans(),
        agent=st.one_of(st.none(), agent_choices),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_export_flag_combinations(
        self, target, use_ah, use_aw, use_minimal, use_flat, use_force, agent
    ):
        """Test export with various flag combinations."""
        # Skip --ah in unit tests (causes SSH timeouts); tested in Docker E2E
        assume(not use_ah)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            env = os.environ.copy()
            env["HOME"] = str(tmp_path)
            env["USERPROFILE"] = str(tmp_path)
            env["CLAUDE_SKIP_WSL_SCAN"] = "1"

            (tmp_path / ".claude" / "projects").mkdir(parents=True)
            (tmp_path / ".agent-history").mkdir(parents=True)
            (tmp_path / ".codex" / "sessions").mkdir(parents=True)
            (tmp_path / ".gemini").mkdir(parents=True)
            output_dir = tmp_path / "output"

            args = ["export"]
            if target:
                args.append(target)
            args.extend(["-o", str(output_dir)])

            if use_ah:
                args.append("--ah")
            if use_aw:
                args.append("--aw")
            if use_minimal:
                args.append("--minimal")
            if use_flat:
                args.append("--flat")
            if use_force:
                args.append("--force")
            if agent:
                args.extend(["--agent", agent])

            cmd = [sys.executable, str(CLI_PATH), *args]
            timeout = 30 if sys.platform == "win32" else 10
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(tmp_path),
                check=False,
            )

            assert "Traceback" not in result.stderr
            assert result.returncode in (0, 1)

    @given(
        split_value=st.one_of(
            st.none(),
            st.integers(min_value=100, max_value=10000),
        ),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_export_split_values(self, split_value):
        """Test export with various --split values."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            env = os.environ.copy()
            env["HOME"] = str(tmp_path)
            env["USERPROFILE"] = str(tmp_path)
            env["CLAUDE_SKIP_WSL_SCAN"] = "1"

            (tmp_path / ".claude" / "projects").mkdir(parents=True)
            (tmp_path / ".agent-history").mkdir(parents=True)
            output_dir = tmp_path / "output"

            args = ["export", "*", "-o", str(output_dir)]
            if split_value is not None:
                args.extend(["--split", str(split_value)])

            cmd = [sys.executable, str(CLI_PATH), *args]
            timeout = 30 if sys.platform == "win32" else 10
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(tmp_path),
                check=False,
            )

            assert "Traceback" not in result.stderr
            assert result.returncode in (0, 1, 2)  # 2 for argparse errors


# ============================================================================
# stats command tests
# ============================================================================


class TestStatsCombinations:
    """Test stats command with various flag combinations."""

    @given(
        workspace=workspace_patterns,
        use_sync=st.booleans(),
        use_ah=st.booleans(),
        use_aw=st.booleans(),
        view=st.sampled_from([None, "tools", "models", "by-workspace", "by-day", "time"]),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_stats_flag_combinations(self, workspace, use_sync, use_ah, use_aw, view):
        """Test stats with various flag combinations."""
        # Skip --ah in unit tests (causes SSH timeouts); tested in Docker E2E
        assume(not use_ah)

        args = ["stats"]
        if workspace:
            args.append(workspace)
        if use_sync:
            args.append("--sync")
        if use_ah:
            args.append("--ah")
        if use_aw:
            args.append("--aw")
        if view:
            args.append(f"--{view}")

        result = run_cli_in_temp(args)

        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)

    @given(
        use_tools=st.booleans(),
        use_models=st.booleans(),
        use_by_workspace=st.booleans(),
        use_by_day=st.booleans(),
        use_time=st.booleans(),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_stats_multiple_views(
        self, use_tools, use_models, use_by_workspace, use_by_day, use_time
    ):
        """Test stats with multiple view flags."""
        args = ["stats"]
        if use_tools:
            args.append("--tools")
        if use_models:
            args.append("--models")
        if use_by_workspace:
            args.append("--by-workspace")
        if use_by_day:
            args.append("--by-day")
        if use_time:
            args.append("--time")

        result = run_cli_in_temp(args)

        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)


# ============================================================================
# alias command tests
# ============================================================================


class TestAliasCombinations:
    """Test alias subcommands with various combinations."""

    @given(
        alias_name=st.sampled_from(["myalias", "test-alias", "a", "alias_123"]),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_alias_create_show_delete(self, alias_name):
        """Test alias create/show/delete lifecycle."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            env = os.environ.copy()
            env["HOME"] = str(tmp_path)
            # Disable coverage subprocess tracking to avoid coverage atexit errors
            env.pop("COVERAGE_PROCESS_START", None)

            (tmp_path / ".claude" / "projects").mkdir(parents=True)
            (tmp_path / ".agent-history").mkdir(parents=True)

            # Create
            cmd = [sys.executable, str(CLI_PATH), "alias", "create", alias_name]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5, env=env, check=False
            )
            assert "Traceback" not in result.stderr or "coverage" in result.stderr.lower()

            # Show
            cmd = [sys.executable, str(CLI_PATH), "alias", "show", alias_name]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5, env=env, check=False
            )
            assert "Traceback" not in result.stderr or "coverage" in result.stderr.lower()

            # Delete
            cmd = [sys.executable, str(CLI_PATH), "alias", "delete", alias_name]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5, env=env, check=False
            )
            assert "Traceback" not in result.stderr or "coverage" in result.stderr.lower()

    def test_alias_list_flags(self):
        """Test alias list basic invocation."""
        args = ["alias", "list"]
        result = run_cli_in_temp(args)

        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)


# ============================================================================
# Cross-command flag consistency tests
# ============================================================================


class TestCrossCommandConsistency:
    """Test that similar flags work consistently across commands."""

    @given(
        command=st.sampled_from(["lsw", "lss", "export"]),
        agent=agent_choices,
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_agent_flag_all_commands(self, command, agent):
        """Test --agent flag works on all commands that support it."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            env = os.environ.copy()
            env["HOME"] = str(tmp_path)
            env["USERPROFILE"] = str(tmp_path)
            env["CLAUDE_SKIP_WSL_SCAN"] = "1"

            (tmp_path / ".claude" / "projects").mkdir(parents=True)
            (tmp_path / ".agent-history").mkdir(parents=True)
            (tmp_path / ".codex" / "sessions").mkdir(parents=True)
            (tmp_path / ".gemini").mkdir(parents=True)
            output_dir = tmp_path / "output"

            if command == "lsw":
                args = ["lsw", "*", "--agent", agent]
            elif command == "lss":
                args = ["lss", "*", "--agent", agent]
            else:  # export
                args = ["export", "*", "-o", str(output_dir), "--agent", agent]

            cmd = [sys.executable, str(CLI_PATH), *args]
            timeout = 30 if sys.platform == "win32" else 10
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(tmp_path),
                check=False,
            )

            assert "Traceback" not in result.stderr
            assert result.returncode in (0, 1)

    @given(
        command=st.sampled_from(["lss", "export"]),
        use_ah=st.booleans(),
        use_aw=st.booleans(),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_ah_aw_orthogonality(self, command, use_ah, use_aw):
        """Test --ah and --aw are orthogonal (can be combined)."""
        # Skip --ah in unit tests (causes SSH timeouts); tested in Docker E2E
        assume(not use_ah)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            env = os.environ.copy()
            env["HOME"] = str(tmp_path)
            env["USERPROFILE"] = str(tmp_path)
            env["CLAUDE_SKIP_WSL_SCAN"] = "1"

            (tmp_path / ".claude" / "projects").mkdir(parents=True)
            (tmp_path / ".agent-history").mkdir(parents=True)
            output_dir = tmp_path / "output"

            if command == "lss":
                args = ["lss", "*"]
            else:  # export
                args = ["export", "*", "-o", str(output_dir)]

            if use_ah:
                args.append("--ah")
            if use_aw:
                args.append("--aw")

            cmd = [sys.executable, str(CLI_PATH), *args]
            timeout = 30 if sys.platform == "win32" else 10
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(tmp_path),
                check=False,
            )

            assert "Traceback" not in result.stderr
            assert result.returncode in (0, 1)


# ============================================================================
# Edge case tests
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @given(
        pattern=st.text(
            alphabet=st.characters(blacklist_categories=["Cs"], blacklist_characters="\x00\n\r"),
            min_size=0,
            max_size=50,
        ),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_arbitrary_workspace_pattern(self, pattern):
        """Test with arbitrary text as workspace pattern."""
        # Skip patterns that could be interpreted as flags
        assume(not pattern.startswith("-"))

        result = run_cli_in_temp(["lsw", pattern])

        assert "Traceback" not in result.stderr

    @given(num_patterns=st.integers(min_value=0, max_value=5))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_multiple_workspace_patterns(self, num_patterns):
        """Test with multiple workspace patterns."""
        patterns = [f"pattern{i}" for i in range(num_patterns)]
        args = ["lsw", *patterns]

        result = run_cli_in_temp(args)

        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)


# ============================================================================
# gemini-index command tests
# ============================================================================


class TestGeminiIndexCombinations:
    """Test gemini-index command combinations."""

    @given(use_add=st.booleans())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_gemini_index_flags(self, use_add):
        """Test gemini-index with flags."""
        args = ["gemini-index"]
        if use_add:
            args.append("--add")

        result = run_cli_in_temp(args)

        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)


# ============================================================================
# lsh command tests
# ============================================================================


class TestLshCombinations:
    """Test lsh (list homes) command combinations."""

    @given(
        use_local=st.booleans(),
        use_wsl=st.booleans(),
        use_windows=st.booleans(),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_lsh_flag_combinations(self, use_local, use_wsl, use_windows):
        """Test lsh with flag combinations."""
        args = ["lsh"]
        if use_local:
            args.append("--local")
        if use_wsl:
            args.append("--wsl")
        if use_windows:
            args.append("--windows")

        result = run_cli_in_temp(args)

        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
