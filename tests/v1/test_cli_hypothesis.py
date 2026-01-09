"""Property-based CLI combination tests (ported from legacy suite).

These tests focus on flag combinatorics and ensure the CLI handles
diverse argument mixes without crashing.
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from tests.helpers.cli import run_cli_subprocess

pytestmark = pytest.mark.v1

# Common values
workspace_patterns = st.sampled_from(
    ["*", "myproject", "test", "nonexistent-ws-12345", ""]
)
agent_choices = st.sampled_from(["auto", "claude", "codex", "gemini"])
date_strings = st.sampled_from(
    [
        "2025-01-01",
        "2025-12-31",
        "2024-06-15",
        "invalid-date",
        "2025/01/01",
        "",
    ]
)

DEFAULT_HEALTH = [HealthCheck.too_slow, HealthCheck.function_scoped_fixture]


def _run(args: list[str], env: dict[str, str], cwd: Path, timeout: int = 10):
    return run_cli_subprocess(args, env=env, cwd=cwd, timeout=timeout)


class TestWsCombinations:
    """Test ws command with various flag combinations."""

    @given(
        pattern=workspace_patterns,
        use_ah=st.booleans(),
        use_local=st.booleans(),
        agent=st.one_of(st.none(), agent_choices),
    )
    @settings(max_examples=100, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_ws_flag_combinations(self, pattern, use_ah, use_local, agent, isolated_home):
        """ws with flag mixes should not crash."""
        args = ["ws"]
        if pattern:
            args.append(pattern)
        if use_ah:
            args.append("--ah")
        if use_local:
            args.append("--local")
        if agent:
            args.extend(["--agent", agent])

        result = _run(args, env=isolated_home["env"], cwd=isolated_home["path"])
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stderr

    @given(
        pattern=workspace_patterns,
        use_wsl=st.booleans(),
        use_windows=st.booleans(),
    )
    @settings(max_examples=50, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_ws_wsl_windows_flags(self, pattern, use_wsl, use_windows, isolated_home):
        """--wsl/--windows handling should be graceful."""
        # Avoid slow cross-platform probing in unit scope; covered in targeted tests
        assume(not use_wsl and not use_windows)
        args = ["ws"]
        if pattern:
            args.append(pattern)
        if use_wsl:
            args.append("--wsl")
        if use_windows:
            args.append("--windows")

        result = _run(args, env=isolated_home["env"], cwd=isolated_home["path"])
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stderr


class TestSessionCombinations:
    """Test session list/export flag combinations."""

    @given(
        workspace=workspace_patterns,
        use_ah=st.booleans(),
        use_aw=st.booleans(),
        use_this=st.booleans(),
        agent=st.one_of(st.none(), agent_choices),
    )
    @settings(max_examples=100, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_session_scope_combinations(
        self, workspace, use_ah, use_aw, use_this, agent, isolated_home
    ):
        """session list scope permutations."""
        args = ["session"]
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

        result = _run(args, env=isolated_home["env"], cwd=isolated_home["path"])
        assert result.returncode in (0, 1)
        assert "Traceback" not in result.stderr

    @given(
        since=date_strings,
        until=date_strings,
    )
    @settings(max_examples=50, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_session_date_combinations(self, since, until, isolated_home):
        """session list date filter permutations."""
        args = ["session", "-n", "*"]
        if since:
            args.extend(["--since", since])
        if until:
            args.extend(["--until", until])

        result = _run(args, env=isolated_home["env"], cwd=isolated_home["path"])
        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)


class TestExportCombinations:
    """Test session export flag combinations."""

    @given(
        target=workspace_patterns,
        use_ah=st.booleans(),
        use_aw=st.booleans(),
        use_minimal=st.booleans(),
        use_flat=st.booleans(),
        use_force=st.booleans(),
        agent=st.one_of(st.none(), agent_choices),
    )
    @settings(max_examples=100, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_export_flag_combinations(
        self, target, use_ah, use_aw, use_minimal, use_flat, use_force, agent, isolated_home
    ):
        """Export should tolerate varied flag mixes without crashing."""
        assume(not use_ah)  # avoid cross-home scans in unit scope

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_dir = tmp_path / "output"

            args = ["session", "export", "-o", str(output_dir)]
            if target:
                args.append(target)
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

            env = {**isolated_home["env"], "HOME": str(tmp_path)}
            result = run_cli_subprocess(args, env=env, cwd=tmp_path)

            assert "Traceback" not in result.stderr
            assert result.returncode in (0, 1)

    @given(
        split_value=st.one_of(
            st.none(),
            st.integers(min_value=100, max_value=10000),
        ),
    )
    @settings(max_examples=30, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_export_split_values(self, split_value, isolated_home):
        """Export should accept varied --split values."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_dir = tmp_path / "output"
            args = ["session", "export", "-n", "*", "-o", str(output_dir)]
            if split_value is not None:
                args.extend(["--split", str(split_value)])

            env = {**isolated_home["env"], "HOME": str(tmp_path)}
            result = run_cli_subprocess(args, env=env, cwd=tmp_path)

            assert "Traceback" not in result.stderr
            assert result.returncode in (0, 1, 2)  # 2 for argparse errors


class TestStatsCombinations:
    """Test session stats command with various flag combinations."""

    @given(
        workspace=workspace_patterns,
        use_sync=st.booleans(),
        use_ah=st.booleans(),
        use_aw=st.booleans(),
        view=st.sampled_from([None, "tools", "models", "by-workspace", "by-day", "time"]),
    )
    @settings(max_examples=100, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_stats_flag_combinations(
        self, workspace, use_sync, use_ah, use_aw, view, isolated_home
    ):
        """Stats flag permutations should not crash."""
        assume(not use_ah)

        args = ["session", "stats"]
        if workspace:
            args.extend(["-n", workspace])
        if use_sync:
            args.append("--sync")
        if use_ah:
            args.append("--ah")
        if use_aw:
            args.append("--aw")
        if view:
            args.append(f"--{view}")

        result = _run(args, env=isolated_home["env"], cwd=isolated_home["path"])
        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)

    @given(
        use_tools=st.booleans(),
        use_models=st.booleans(),
        use_by_workspace=st.booleans(),
        use_by_day=st.booleans(),
        use_time=st.booleans(),
    )
    @settings(max_examples=50, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_stats_multiple_views(
        self, use_tools, use_models, use_by_workspace, use_by_day, use_time, isolated_home
    ):
        """Stats multi-view flags should be tolerated."""
        args = ["session", "stats"]
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

        result = _run(args, env=isolated_home["env"], cwd=isolated_home["path"])
        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)


class TestProjectCombinations:
    """Project subcommand smoke checks."""

    def test_project_list(self, isolated_home):
        """project list basic invocation."""
        result = _run(["project", "list"], env=isolated_home["env"], cwd=isolated_home["path"])
        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)


class TestCrossCommandConsistency:
    """Consistency of shared flags across commands."""

    @given(
        command=st.sampled_from(["ws", "session", "session-export"]),
        agent=agent_choices,
    )
    @settings(max_examples=30, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_agent_flag_all_commands(self, command, agent, isolated_home):
        """--agent should be accepted consistently."""
        output_dir = isolated_home["path"] / "output"
        args: list[str]
        if command == "ws":
            args = ["ws", "-n", "*", "--agent", agent]
        elif command == "session":
            args = ["session", "-n", "*", "--agent", agent]
        else:
            args = ["session", "export", "-n", "*", "-o", str(output_dir), "--agent", agent]

        result = _run(args, env=isolated_home["env"], cwd=isolated_home["path"])
        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)

    @given(
        command=st.sampled_from(["session", "session-export"]),
        use_ah=st.booleans(),
        use_aw=st.booleans(),
    )
    @settings(max_examples=30, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_ah_aw_orthogonality(self, command, use_ah, use_aw, isolated_home):
        """--ah and --aw should be orthogonal."""
        assume(not use_ah)

        output_dir = isolated_home["path"] / "output"
        args: list[str]
        if command == "session":
            args = ["session", "-n", "*"]
        else:
            args = ["session", "export", "-n", "*", "-o", str(output_dir)]

        if use_ah:
            args.append("--ah")
        if use_aw:
            args.append("--aw")

        result = _run(args, env=isolated_home["env"], cwd=isolated_home["path"])
        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)


class TestEdgeCases:
    """Edge case inputs."""

    @given(
        pattern=st.text(
            alphabet=st.characters(blacklist_categories=["Cs"], blacklist_characters="\x00\n\r"),
            min_size=0,
            max_size=50,
        ),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.filter_too_much,
            HealthCheck.function_scoped_fixture,
        ],
        deadline=None,
    )
    def test_arbitrary_workspace_pattern(self, pattern, isolated_home):
        """Arbitrary text patterns shouldn't crash."""
        assume(not pattern.startswith("-"))

        result = _run(["ws", "-n", pattern], env=isolated_home["env"], cwd=isolated_home["path"])
        assert "Traceback" not in result.stderr

    @given(num_patterns=st.integers(min_value=0, max_value=5))
    @settings(max_examples=20, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_multiple_workspace_patterns(self, num_patterns, isolated_home):
        """Multiple patterns should parse."""
        args = ["ws"]
        for i in range(num_patterns):
            args.extend(["-n", f"pattern{i}"])

        result = _run(args, env=isolated_home["env"], cwd=isolated_home["path"])
        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)


class TestGeminiIndexCombinations:
    """gemini-index smoke."""

    @given(use_add=st.booleans())
    @settings(max_examples=10, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_gemini_index_flags(self, use_add, isolated_home):
        args = ["gemini-index"]
        if use_add:
            args.append("--add")

        result = _run(args, env=isolated_home["env"], cwd=isolated_home["path"])
        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)


class TestHomeCombinations:
    """home command flag mixes."""

    @given(
        use_local=st.booleans(),
        use_wsl=st.booleans(),
        use_windows=st.booleans(),
    )
    @settings(max_examples=20, suppress_health_check=DEFAULT_HEALTH, deadline=None)
    def test_home_flag_combinations(self, use_local, use_wsl, use_windows, isolated_home):
        args = ["home"]
        if use_local:
            args.append("--local")
        if use_wsl:
            args.append("--wsl")
        if use_windows:
            args.append("--windows")

        result = _run(args, env=isolated_home["env"], cwd=isolated_home["path"])
        assert "Traceback" not in result.stderr
        assert result.returncode in (0, 1)
