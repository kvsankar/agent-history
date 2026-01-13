"""Tests for home list format support."""

import json

from tests.helpers.cli import run_cli_subprocess


def test_home_list_table_format():
    """Test home list with table format."""
    result = run_cli_subprocess(["home", "list", "--format", "table"])
    assert result.returncode == 0
    assert "HOME" in result.stdout
    assert "PATH" in result.stdout or "TYPE" in result.stdout


def test_home_list_tsv_format():
    """Test home list with TSV format."""
    result = run_cli_subprocess(["home", "list", "--format", "tsv"])
    assert result.returncode == 0
    lines = result.stdout.strip().split("\n")
    assert len(lines) >= 1  # At least header
    # Header should be tab-separated
    assert "\t" in lines[0]
    assert "SESSIONS" not in lines[0]


def test_home_list_tsv_format_with_counts():
    """Test home list TSV output with session counts."""
    result = run_cli_subprocess(["home", "list", "--format", "tsv", "--counts"])
    assert result.returncode == 0
    lines = result.stdout.strip().split("\n")
    assert len(lines) >= 1  # At least header
    assert "SESSIONS" in lines[0]


def test_home_list_json_format():
    """Test home list with JSON format."""
    result = run_cli_subprocess(["home", "list", "--format", "json"])
    assert result.returncode == 0
    # Should be valid JSON
    data = json.loads(result.stdout)
    assert isinstance(data, list)


def test_home_list_default_format_is_table():
    """Test that default format is table when on TTY."""
    result = run_cli_subprocess(["home", "list"])
    assert result.returncode == 0
    # Should have column headers
    assert "HOME" in result.stdout or "TYPE" in result.stdout
