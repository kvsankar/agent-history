"""CLI runner helpers for V1 tests."""

import os
import subprocess
import sys
import tempfile
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
    """Find the agent-history CLI script path.

    By default, returns the new agent-history wrapper (v2 module).
    Set AGENT_HISTORY_TEST_SCRIPT=v1 to use the old ah.py script instead.

    This allows running the same test suite against both implementations:
        # Test against new agent-history module (default)
        uv run pytest tests/core/

        # Test against old ah.py script
        AGENT_HISTORY_TEST_SCRIPT=v1 uv run pytest tests/core/
    """
    use_old_script = os.environ.get("AGENT_HISTORY_TEST_SCRIPT", "").lower() in (
        "v1",
        "old",
        "ah.py",
    )

    if use_old_script:
        # Use the old monolithic script
        candidates = [
            Path.cwd() / "ah.py",
            Path(__file__).parent.parent.parent / "ah.py",
        ]
        script_name = "ah.py"
    else:
        # Use the new v2 wrapper (default)
        candidates = [
            Path.cwd() / "agent-history",
            Path.cwd() / "claude-history",
            Path(__file__).parent.parent.parent / "agent-history",
            Path(__file__).parent.parent.parent / "claude-history",
        ]
        script_name = "agent-history"

    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find {script_name} script")


def get_module_path() -> Path:
    """Find the old monolithic script (ah.py) for module import tests.

    The v1 module tests need the old script which has internal functions
    like is_running_in_wsl(), _looks_like_windows_drive(), etc.
    """
    candidates = [
        Path.cwd() / "ah.py",
        Path(__file__).parent.parent.parent / "ah.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find ah.py (old monolithic script)")


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

    temp_dir = None
    try:
        run_env = os.environ.copy()
        if env is None:
            # Default to an isolated home to avoid probing the real filesystem during tests.
            temp_dir = tempfile.TemporaryDirectory(prefix="agent-history-test-")
            root = Path(temp_dir.name)
            claude_dir = root / ".claude" / "projects"
            codex_dir = root / ".codex" / "sessions"
            gemini_dir = root / ".gemini" / "tmp"
            history_dir = root / ".agent-history"
            for path in (claude_dir, codex_dir, gemini_dir, history_dir):
                path.mkdir(parents=True, exist_ok=True)

            run_env.update(
                {
                    "HOME": str(root),
                    "CLAUDE_PROJECTS_DIR": str(claude_dir),
                    "CODEX_SESSIONS_DIR": str(codex_dir),
                    "GEMINI_SESSIONS_DIR": str(gemini_dir),
                    "AGENT_HISTORY_CONFIG_DIR": str(history_dir),
                }
            )
            if sys.platform == "win32":
                run_env["USERPROFILE"] = str(root)
        else:
            run_env.update(env)

        run_env.setdefault("AGENT_HISTORY_TEST_MODE", "1")

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=run_env,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


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
