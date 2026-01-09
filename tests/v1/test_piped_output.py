"""Tests for piped output auto-detection."""

import subprocess


def test_ws_list_piped_outputs_tsv():
    """Test that ws list auto-switches to TSV when piped."""
    # When piped, output should be TSV (no column alignment padding)
    result = subprocess.run(
        ["sh", "-c", "python3 agent-history ws list | cat"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    if result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        # Should be tab-separated, not space-padded
        assert "\t" in lines[0]


def test_session_list_piped_outputs_tsv():
    """Test that session list auto-switches to TSV when piped."""
    result = subprocess.run(
        ["sh", "-c", "python3 agent-history session list --aw | head -5"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    if result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        # Should be tab-separated
        if len(lines) > 0:
            assert "\t" in lines[0] or "SESSION" in lines[0]


def test_home_list_piped_outputs_tsv():
    """Test that home list auto-switches to TSV when piped."""
    result = subprocess.run(
        ["sh", "-c", "python3 agent-history home list | cat"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    if result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        # Should be tab-separated
        assert "\t" in lines[0]
