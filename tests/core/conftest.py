"""V1-specific pytest fixtures."""

import shutil
from pathlib import Path
from typing import Any, Dict

import pytest


@pytest.fixture
def claude_golden_path(v1_fixtures_dir: Path) -> Path:
    """Return path to Claude golden fixture."""
    return v1_fixtures_dir / "claude_golden.jsonl"


@pytest.fixture
def codex_golden_path(v1_fixtures_dir: Path) -> Path:
    """Return path to Codex golden fixture."""
    return v1_fixtures_dir / "codex_golden.jsonl"


@pytest.fixture
def gemini_golden_path(v1_fixtures_dir: Path) -> Path:
    """Return path to Gemini golden fixture."""
    return v1_fixtures_dir / "gemini_golden.json"


@pytest.fixture
def setup_golden_fixtures(isolated_home: Dict[str, Any], v1_fixtures_dir: Path) -> Dict[str, Path]:
    """Copy golden fixtures to isolated home and return session file paths.

    Sets up the V1 golden fixtures in the correct directory structure:
    - Claude: .claude/projects/-home-testuser-golden-project/golden-claude-001.jsonl
    - Codex: .codex/sessions/2025/01/04/rollout-golden-codex-001.jsonl
    - Gemini: .gemini/tmp/abc123.../chats/session-golden-gemini-001.json

    Returns:
        Dict mapping agent names to session file paths
    """
    paths = {}

    # Claude: copy to workspace directory
    claude_ws = isolated_home["claude_dir"] / "-home-testuser-golden-project"
    claude_ws.mkdir(parents=True, exist_ok=True)
    claude_session = claude_ws / "golden-claude-001.jsonl"
    shutil.copy(v1_fixtures_dir / "claude_golden.jsonl", claude_session)
    paths["claude"] = claude_session

    # Codex: copy to date-based directory
    codex_date_dir = isolated_home["codex_dir"] / "2025" / "01" / "04"
    codex_date_dir.mkdir(parents=True, exist_ok=True)
    codex_session = codex_date_dir / "rollout-golden-codex-001.jsonl"
    shutil.copy(v1_fixtures_dir / "codex_golden.jsonl", codex_session)
    paths["codex"] = codex_session

    # Gemini: copy to hash-based directory
    gemini_hash = "abc123def456789012345678901234567890123456789012345678901234"
    gemini_chat_dir = isolated_home["gemini_dir"] / gemini_hash / "chats"
    gemini_chat_dir.mkdir(parents=True, exist_ok=True)
    gemini_session = gemini_chat_dir / "session-2025-01-05T14-00-golden-gemini-001.json"
    shutil.copy(v1_fixtures_dir / "gemini_golden.json", gemini_session)
    paths["gemini"] = gemini_session

    return paths


@pytest.fixture
def golden_totals(expected_values: Dict[str, Any]) -> Dict[str, Any]:
    """Return expected totals from golden fixtures."""
    return expected_values["totals"]


@pytest.fixture
def claude_expected(expected_values: Dict[str, Any]) -> Dict[str, Any]:
    """Return expected values for Claude golden fixture."""
    return expected_values["claude_golden"]


@pytest.fixture
def codex_expected(expected_values: Dict[str, Any]) -> Dict[str, Any]:
    """Return expected values for Codex golden fixture."""
    return expected_values["codex_golden"]


@pytest.fixture
def gemini_expected(expected_values: Dict[str, Any]) -> Dict[str, Any]:
    """Return expected values for Gemini golden fixture."""
    return expected_values["gemini_golden"]
