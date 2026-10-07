"""Tests for piped output auto-detection."""

import shlex
import subprocess
import sys

from tests.helpers.cli import run_cli_subprocess


def _run_piped(args_str: str) -> subprocess.CompletedProcess:
    """Run CLI command through a pipe, in an isolated home, to test auto-format detection."""
    split_args = shlex.split(args_str, posix=sys.platform != "win32")
    return run_cli_subprocess(split_args)


def test_ws_list_piped_outputs_tsv():
    """Test that ws list auto-switches to TSV when piped."""
    # When piped, output should be TSV (no column alignment padding)
    result = _run_piped("ws list")
    assert result.returncode == 0
    if result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        # Should be tab-separated, not space-padded
        assert "\t" in lines[0]


def test_session_list_piped_outputs_tsv():
    """Test that session list auto-switches to TSV when piped."""
    result = _run_piped("session list --aw")
    assert result.returncode == 0
    if result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        # Should be tab-separated
        if len(lines) > 0:
            assert "\t" in lines[0] or "SESSION" in lines[0]


def test_home_list_piped_outputs_tsv():
    """Test that home list auto-switches to TSV when piped."""
    result = _run_piped("home list")
    assert result.returncode == 0
    if result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        # Should be tab-separated
        assert "\t" in lines[0]
