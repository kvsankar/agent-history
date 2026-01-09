"""Tests for home list format support."""

import json
import subprocess


def test_home_list_table_format():
    """Test home list with table format."""
    result = subprocess.run(
        ["python3", "agent-history", "home", "list", "--format", "table"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "HOME" in result.stdout
    assert "PATH" in result.stdout or "TYPE" in result.stdout


def test_home_list_tsv_format():
    """Test home list with TSV format."""
    result = subprocess.run(
        ["python3", "agent-history", "home", "list", "--format", "tsv"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    lines = result.stdout.strip().split("\n")
    assert len(lines) >= 1  # At least header
    # Header should be tab-separated
    assert "\t" in lines[0]


def test_home_list_json_format():
    """Test home list with JSON format."""
    result = subprocess.run(
        ["python3", "agent-history", "home", "list", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    # Should be valid JSON
    data = json.loads(result.stdout)
    assert isinstance(data, list)


def test_home_list_default_format_is_table():
    """Test that default format is table when on TTY."""
    result = subprocess.run(
        ["python3", "agent-history", "home", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    # Should have column headers
    assert "HOME" in result.stdout or "TYPE" in result.stdout
