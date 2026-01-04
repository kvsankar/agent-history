"""Root pytest fixtures for all tests."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import patch

import pytest

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
