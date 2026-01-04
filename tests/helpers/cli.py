"""CLI runner helpers for V1 tests."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Click is optional - only needed for run_cli_click()
try:
    from click.testing import CliRunner, Result

    HAS_CLICK = True
except ImportError:
    HAS_CLICK = False
    CliRunner = None  # type: ignore
    Result = None  # type: ignore


def get_script_path() -> Path:
    """Find the agent-history script path."""
    candidates = [
        Path.cwd() / "agent-history",
        Path.cwd() / "claude-history",
        Path(__file__).parent.parent.parent / "agent-history",
        Path(__file__).parent.parent.parent / "claude-history",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find agent-history script")


def run_cli_subprocess(
    args: List[str],
    env: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    """Run CLI via subprocess (E2E testing).

    Args:
        args: Command-line arguments
        env: Environment variables override
        timeout: Command timeout in seconds
        cwd: Working directory

    Returns:
        CompletedProcess with stdout, stderr, returncode
    """
    script_path = get_script_path()
    cmd = [sys.executable, str(script_path), *args]

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=run_env,
        timeout=timeout,
        cwd=cwd,
        check=False,
    )


def run_cli_click(
    runner: CliRunner,
    args: List[str],
    env: Optional[Dict[str, str]] = None,
    catch_exceptions: bool = False,
) -> Result:
    """Run CLI via Click CliRunner (unit testing).

    Args:
        runner: Click CliRunner instance
        args: Command-line arguments
        env: Environment variables override
        catch_exceptions: Whether to catch exceptions

    Returns:
        Click Result object
    """
    # Import CLI lazily to avoid import issues
    # The agent-history script defines the CLI entry point
    import importlib.util

    script_path = get_script_path()
    spec = importlib.util.spec_from_file_location("agent_history", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Find the CLI entry point (usually named 'cli' or 'main')
    cli = getattr(module, "cli", None) or getattr(module, "main", None)
    if cli is None:
        raise AttributeError("Could not find CLI entry point in agent-history script")

    return runner.invoke(
        cli,
        args,
        env=env,
        catch_exceptions=catch_exceptions,
    )


def assert_cli_success(result: Any, message: str = "") -> None:
    """Assert CLI command succeeded.

    Works with both subprocess.CompletedProcess and click.testing.Result.
    """
    if hasattr(result, "returncode"):
        # subprocess.CompletedProcess
        assert result.returncode == 0, f"{message}\nstderr: {result.stderr}"
    else:
        # click.testing.Result
        assert (
            result.exit_code == 0
        ), f"{message}\noutput: {result.output}\nexception: {result.exception}"


def assert_cli_output_contains(result: Any, expected: str, message: str = "") -> None:
    """Assert CLI output contains expected string."""
    if hasattr(result, "stdout"):
        output = result.stdout
    else:
        output = result.output
    assert expected in output, f"{message}\nExpected '{expected}' in output:\n{output}"


def assert_cli_output_not_contains(result: Any, unexpected: str, message: str = "") -> None:
    """Assert CLI output does not contain unexpected string."""
    if hasattr(result, "stdout"):
        output = result.stdout
    else:
        output = result.output
    assert (
        unexpected not in output
    ), f"{message}\nUnexpected '{unexpected}' found in output:\n{output}"
