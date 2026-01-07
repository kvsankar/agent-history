"""Root pytest fixtures for all tests."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Pytest CLI Options
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    """Add custom CLI options."""
    parser.addoption(
        "--docker",
        action="store_true",
        default=False,
        help="Run Docker E2E tests (starts containers and runs tests inside Docker)",
    )


def pytest_configure(config):
    """Store docker flag in config for access by fixtures."""
    config.addinivalue_line("markers", "e2e_docker: marks tests as Docker E2E tests")

    # If --docker flag is passed and we're not inside Docker, run tests in Docker
    if config.getoption("--docker", default=False):
        if not (
            os.environ.get("NODE_ALPHA") is not None
            or os.environ.get("NODE_BETA") is not None
            or Path("/.dockerenv").exists()
        ):
            # We're on the host, need to run inside Docker
            _run_docker_tests_and_exit(config)


def _run_docker_tests_and_exit(config):
    """Run Docker E2E tests inside the Docker container and exit.

    This is called when --docker is passed from the host.
    """
    docker_dir = Path(__file__).parent.parent / "docker"

    print("=" * 60)
    print("Running Docker E2E tests inside container...")
    print("=" * 60)

    try:
        # Build containers
        print("\n[1/4] Building Docker containers...")
        result = subprocess.run(
            ["docker", "compose", "build"],
            cwd=docker_dir,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            print("ERROR: Docker build failed")
            sys.exit(1)

        # Start SSH nodes
        print("\n[2/4] Starting SSH nodes...")
        result = subprocess.run(
            ["docker", "compose", "up", "-d", "node-alpha", "node-beta"],
            cwd=docker_dir,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            print("ERROR: Failed to start Docker containers")
            sys.exit(1)

        # Wait for SSH to be ready
        print("\n[3/4] Waiting for SSH nodes...")
        time.sleep(5)

        # Run tests inside Docker
        print("\n[4/4] Running tests inside Docker container...")
        print("-" * 60)

        # Pass through any extra pytest args
        extra_args = []
        if config.option.verbose:
            extra_args.append("-v")
        if hasattr(config.option, "tb") and config.option.tb:
            extra_args.extend(["--tb", config.option.tb])

        result = subprocess.run(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "test-runner",
                "pytest",
                "tests/e2e_docker/",
                *extra_args,
            ],
            cwd=docker_dir,
            check=False,
        )

        print("-" * 60)
        exit_code = result.returncode

    finally:
        # Cleanup
        print("\nCleaning up Docker containers...")
        subprocess.run(
            ["docker", "compose", "down", "-v"],
            cwd=docker_dir,
            capture_output=True,
            timeout=60,
            check=False,
        )

    # Use os._exit to avoid pytest's exception handling
    os._exit(exit_code)


# ---------------------------------------------------------------------------
# Docker Infrastructure
# ---------------------------------------------------------------------------


def _get_docker_compose_dir() -> Path:
    """Get path to docker/ directory."""
    return Path(__file__).parent.parent / "docker"


def _is_docker_running() -> bool:
    """Check if Docker daemon is running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _start_docker_containers() -> bool:
    """Start Docker containers for E2E tests.

    Returns:
        True if containers started successfully
    """
    docker_dir = _get_docker_compose_dir()

    # Build containers
    result = subprocess.run(
        ["docker", "compose", "build"],
        cwd=docker_dir,
        capture_output=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        print(f"Docker build failed: {result.stderr.decode()}")
        return False

    # Start SSH nodes
    result = subprocess.run(
        ["docker", "compose", "up", "-d", "node-alpha", "node-beta"],
        cwd=docker_dir,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        print(f"Docker start failed: {result.stderr.decode()}")
        return False

    # Wait for SSH to be ready
    time.sleep(3)

    # Verify connectivity
    for attempt in range(5):
        result = subprocess.run(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "test-runner",
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=5",
                "alice@node-alpha",
                "echo",
                "ready",
            ],
            cwd=docker_dir,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0:
            return True
        time.sleep(2)

    return False


def _stop_docker_containers():
    """Stop Docker containers."""
    docker_dir = _get_docker_compose_dir()
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=docker_dir,
        capture_output=True,
        timeout=60,
        check=False,
    )


@pytest.fixture(scope="session")
def docker_containers(request):
    """Session-scoped fixture to manage Docker containers.

    Only starts containers if --docker flag is passed.
    """
    if not request.config.getoption("--docker"):
        yield None
        return

    if not _is_docker_running():
        pytest.skip("Docker daemon not running")

    print("\nStarting Docker containers for E2E tests...")
    if not _start_docker_containers():
        pytest.fail("Failed to start Docker containers")

    yield {
        "node_alpha": "node-alpha",
        "node_beta": "node-beta",
        "alpha_users": ["alice", "bob"],
        "beta_users": ["charlie", "dave"],
        "docker_dir": _get_docker_compose_dir(),
    }

    print("\nStopping Docker containers...")
    _stop_docker_containers()


def pytest_collection_modifyitems(config, items):
    """Skip e2e_docker tests unless --docker flag is passed or inside Docker."""
    if config.getoption("--docker"):
        # --docker passed, don't skip
        return

    # Check if we're inside Docker
    if (
        os.environ.get("NODE_ALPHA") is not None
        or os.environ.get("NODE_BETA") is not None
        or Path("/.dockerenv").exists()
    ):
        # Inside Docker, don't skip
        return

    # Skip all e2e_docker tests
    skip_docker = pytest.mark.skip(
        reason="Docker E2E tests require --docker flag or running inside Docker"
    )
    for item in items:
        if "e2e_docker" in item.nodeid:
            item.add_marker(skip_docker)


# ---------------------------------------------------------------------------
# Platform Detection
# ---------------------------------------------------------------------------


def get_platform() -> str:
    """Detect current platform."""
    if sys.platform == "win32":
        return "windows"
    try:
        if "microsoft" in os.uname().release.lower():
            return "wsl"
    except AttributeError:
        pass
    return "linux"


CURRENT_PLATFORM = get_platform()


# ---------------------------------------------------------------------------
# Session-Scoped Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_home(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path, None, None]:
    """Create an isolated test home directory for the entire test session.

    Creates the standard agent directory structure:
    - .claude/projects/
    - .codex/sessions/
    - .gemini/tmp/
    - .agent-history/

    Yields:
        Path to the test home directory
    """
    home = tmp_path_factory.mktemp("test_home")

    # Create agent directories
    (home / ".claude" / "projects").mkdir(parents=True)
    (home / ".codex" / "sessions").mkdir(parents=True)
    (home / ".gemini" / "tmp").mkdir(parents=True)
    (home / ".agent-history").mkdir(parents=True)

    yield home


@pytest.fixture(scope="session")
def v1_fixtures_dir() -> Path:
    """Return path to V1 golden fixtures directory."""
    return Path(__file__).parent / "fixtures" / "v1"


@pytest.fixture(scope="session")
def expected_values(v1_fixtures_dir: Path) -> Dict[str, Any]:
    """Load expected values from golden fixtures."""
    expected_file = v1_fixtures_dir / "expected_values.json"
    if not expected_file.exists():
        pytest.skip("expected_values.json not found")
    with open(expected_file, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Function-Scoped Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_home(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create function-scoped isolated home with environment overrides.

    Yields:
        Dict with 'path' and 'env' keys for use with CLI tests
    """
    # Create agent directories
    claude_dir = tmp_path / ".claude" / "projects"
    codex_dir = tmp_path / ".codex" / "sessions"
    gemini_dir = tmp_path / ".gemini" / "tmp"
    history_dir = tmp_path / ".agent-history"

    claude_dir.mkdir(parents=True)
    codex_dir.mkdir(parents=True)
    gemini_dir.mkdir(parents=True)
    history_dir.mkdir(parents=True)

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(claude_dir)
    env["CODEX_SESSIONS_DIR"] = str(codex_dir)
    env["GEMINI_SESSIONS_DIR"] = str(gemini_dir)
    env["HOME"] = str(tmp_path)
    # Ensure config/metrics live alongside this isolated home, regardless of external overrides.
    env["AGENT_HISTORY_CONFIG_DIR"] = str(history_dir)
    if sys.platform == "win32":
        env["USERPROFILE"] = str(tmp_path)

    yield {
        "path": tmp_path,
        "env": env,
        "claude_dir": claude_dir,
        "codex_dir": codex_dir,
        "gemini_dir": gemini_dir,
        "history_dir": history_dir,
    }


@pytest.fixture
def cross_env_homes(tmp_path: Path) -> Generator[Dict[str, Path], None, None]:
    """Create isolated homes for cross-environment testing.

    Creates three separate home directories simulating:
    - local: Current platform home
    - wsl: WSL home (for Windows tests)
    - windows: Windows home (for WSL tests)

    Yields:
        Dict mapping home names to paths
    """
    homes = {}
    for name in ["local", "wsl", "windows"]:
        home = tmp_path / name
        (home / ".claude" / "projects").mkdir(parents=True)
        (home / ".codex" / "sessions").mkdir(parents=True)
        (home / ".gemini" / "tmp").mkdir(parents=True)
        (home / ".agent-history").mkdir(parents=True)
        homes[name] = home

    with patch.dict(
        os.environ,
        {
            "AGENT_HISTORY_HOME": str(homes["local"]),
            "AGENT_HISTORY_HOME_WSL": str(homes["wsl"]),
            "AGENT_HISTORY_HOME_WINDOWS": str(homes["windows"]),
        },
    ):
        yield homes


@pytest.fixture
def metrics_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Create an isolated metrics database path.

    Yields:
        Path to the metrics.db file (may not exist until sync)
    """
    db_path = tmp_path / "metrics.db"
    yield db_path
    # Cleanup handled by tmp_path


# ---------------------------------------------------------------------------
# CLI Runner Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_runner():
    """Create Click CLI test runner.

    Returns:
        CliRunner instance configured for testing, or None if click not available
    """
    try:
        from click.testing import CliRunner

        return CliRunner(mix_stderr=False)
    except ImportError:
        pytest.skip("click not available - install with: pip install click")
