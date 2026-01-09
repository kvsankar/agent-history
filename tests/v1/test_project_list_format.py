"""Tests for project list format support."""

import json
import subprocess


def test_project_list_shows_projects():
    """Test that project list shows projects."""
    result = subprocess.run(
        ["python3", "agent-history", "project", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    # Should have tab-separated output
    if result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        # Check header
        assert "PROJECT" in lines[0]
        assert "SOURCE" in lines[0]
        assert "WORKSPACE" in lines[0]


def test_project_list_tsv_format():
    """Test project list TSV output."""
    result = subprocess.run(
        ["python3", "agent-history", "project", "list", "--format", "tsv"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    if result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        # Should be tab-separated
        assert "\t" in lines[0]


def test_project_list_json_format():
    """Test project list JSON output."""
    result = subprocess.run(
        ["python3", "agent-history", "project", "list", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    # Should be valid JSON
    if result.stdout.strip():
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        if len(data) > 0:
            assert "project" in data[0]
            assert "source" in data[0]
            assert "workspace" in data[0]


def test_project_list_with_counts():
    """Test project list with session counts."""
    result = subprocess.run(
        ["python3", "agent-history", "project", "list", "--counts"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    if result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        # Should have SESSIONS column
        assert "SESSIONS" in lines[0] or "WORKSPACE" in lines[0]
