"""Path helpers for tests."""

from pathlib import Path


def repo_root() -> Path:
    """Return repository root path."""
    return Path(__file__).resolve().parents[2]


def fixtures_dir() -> Path:
    """Return path to tests fixtures directory."""
    return repo_root() / "tests" / "fixtures"
