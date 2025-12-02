#!/usr/bin/env python3
"""
Automated tests for claude-history.

Run with: python -m pytest test_claude_history.py -v
Or simply: pytest test_claude_history.py -v

These tests focus on:
1. Pure functions that don't depend on filesystem/subprocess
2. Functions that can use temp directories for isolation
3. Data transformation and parsing logic
"""

import importlib.machinery

# Import the module under test
# Since claude-history is a single file without .py extension, we need to import it specially
import importlib.util
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

module_path = Path(__file__).parent / "claude-history"
loader = importlib.machinery.SourceFileLoader("claude_history", str(module_path))
spec = importlib.util.spec_from_loader("claude_history", loader)
ch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ch)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_jsonl_content():
    """Sample JSONL content for testing."""
    return [
        {
            "type": "user",
            "message": {"role": "user", "content": "Hello Claude"},
            "timestamp": "2025-11-20T10:30:45.123Z",
            "uuid": "user-uuid-1",
            "sessionId": "session-123",
        },
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "Hello! How can I help?"}]},
            "timestamp": "2025-11-20T10:30:50.456Z",
            "uuid": "assistant-uuid-1",
            "parentUuid": "user-uuid-1",
            "sessionId": "session-123",
        },
    ]


@pytest.fixture
def temp_projects_dir(sample_jsonl_content):
    """Create a temporary Claude projects directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        projects_dir = Path(tmpdir) / ".claude" / "projects"

        # Create a workspace with sessions
        workspace = projects_dir / "-home-user-myproject"
        workspace.mkdir(parents=True)

        # Create a session file
        session_file = workspace / "abc123-def456.jsonl"
        with open(session_file, "w", encoding="utf-8") as f:
            for msg in sample_jsonl_content:
                f.write(json.dumps(msg) + "\n")

        # Create another workspace
        workspace2 = projects_dir / "-home-user-another-project"
        workspace2.mkdir(parents=True)
        session_file2 = workspace2 / "xyz789.jsonl"
        with open(session_file2, "w", encoding="utf-8") as f:
            for msg in sample_jsonl_content:
                f.write(json.dumps(msg) + "\n")

        yield projects_dir


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / ".claude-history"
        config_dir.mkdir(parents=True)
        yield config_dir


# ============================================================================
# Pure Function Tests
# ============================================================================


class TestDateParsing:
    """Tests for parse_date_string and date validation."""

    def test_parse_valid_date(self):
        """Valid ISO date should parse correctly."""
        result = ch.parse_date_string("2025-11-20")
        assert result == datetime(2025, 11, 20)

    def test_parse_invalid_date_format(self):
        """Invalid format should return None."""
        # The function returns None for invalid formats rather than raising
        result = ch.parse_date_string("20-11-2025")
        assert result is None

    def test_parse_invalid_date_values(self):
        """Invalid date values should return None."""
        # The function returns None for invalid dates rather than raising
        result = ch.parse_date_string("2025-13-45")  # Invalid month/day
        assert result is None

    def test_parse_and_validate_dates_valid_range(self):
        """Valid date range should parse correctly."""
        since, until = ch.parse_and_validate_dates("2025-01-01", "2025-12-31")
        assert since == datetime(2025, 1, 1)
        assert until == datetime(2025, 12, 31)

    def test_parse_and_validate_dates_since_only(self):
        """Since-only should work."""
        since, until = ch.parse_and_validate_dates("2025-01-01", None)
        assert since == datetime(2025, 1, 1)
        assert until is None

    def test_parse_and_validate_dates_until_only(self):
        """Until-only should work."""
        since, until = ch.parse_and_validate_dates(None, "2025-12-31")
        assert since is None
        assert until == datetime(2025, 12, 31)

    def test_parse_and_validate_dates_none(self):
        """Both None should return (None, None)."""
        since, until = ch.parse_and_validate_dates(None, None)
        assert since is None
        assert until is None


class TestWindowsPathDetection:
    """Tests for _is_windows_encoded_path."""

    def test_windows_path_detected(self):
        """Windows-style paths should be detected."""
        assert ch._is_windows_encoded_path("C--Users-test") is True
        assert ch._is_windows_encoded_path("D--projects-myapp") is True

    def test_unix_path_not_detected(self):
        """Unix-style paths should not be detected as Windows."""
        assert ch._is_windows_encoded_path("-home-user-project") is False
        assert ch._is_windows_encoded_path("home-user") is False

    def test_short_strings(self):
        """Short strings should not be detected as Windows paths."""
        assert ch._is_windows_encoded_path("C-") is False
        assert ch._is_windows_encoded_path("C") is False
        assert ch._is_windows_encoded_path("") is False


class TestPathNormalization:
    """Tests for path normalization (without filesystem verification)."""

    def test_unix_path_simple(self):
        """Simple Unix path normalization without verification."""
        result = ch.normalize_workspace_name("-home-user-project", verify_local=False)
        assert result == "/home/user/project"

    def test_unix_path_no_leading_dash(self):
        """Unix path without leading dash."""
        result = ch.normalize_workspace_name("home-user-project", verify_local=False)
        assert result == "/home/user/project"

    def test_windows_path_simple(self):
        """Simple Windows path normalization without verification."""
        result = ch.normalize_workspace_name("C--Users-test-project", verify_local=False)
        assert result == "/C/Users/test/project"

    def test_windows_path_different_drive(self):
        """Windows path with different drive letter."""
        result = ch.normalize_workspace_name("D--work-myapp", verify_local=False)
        assert result == "/D/work/myapp"


class TestSourceTagGeneration:
    """Tests for get_source_tag."""

    def test_local_no_tag(self):
        """Local (None) should return empty string."""
        assert ch.get_source_tag(None) == ""

    def test_wsl_tag(self):
        """WSL source should get wsl_ prefix."""
        # The function extracts distro name after wsl:// and lowercases it
        result = ch.get_source_tag("wsl://Ubuntu")
        assert result.startswith("wsl_")
        assert "ubuntu" in result.lower()

    def test_windows_tag(self):
        """Windows source should get windows_ prefix."""
        assert ch.get_source_tag("windows://username") == "windows_username_"

    def test_ssh_remote_tag(self):
        """SSH remote should get remote_ prefix."""
        result = ch.get_source_tag("user@hostname")
        assert result.startswith("remote_")
        assert "hostname" in result


class TestWorkspaceNameFromPath:
    """Tests for get_workspace_name_from_path."""

    def test_simple_workspace(self):
        """Simple workspace path extraction."""
        result = ch.get_workspace_name_from_path("-home-user-myproject")
        # Should return last component
        assert "myproject" in result

    def test_windows_workspace(self):
        """Windows workspace path extraction."""
        result = ch.get_workspace_name_from_path("C--Users-test-project")
        assert "project" in result


class TestNativeWorkspaceDetection:
    """Tests for is_native_workspace."""

    def test_native_unix_workspace(self):
        """Native Unix workspace should return True."""
        assert ch.is_native_workspace("-home-user-project") is True

    def test_native_windows_workspace(self):
        """Native Windows workspace should return True."""
        assert ch.is_native_workspace("C--Users-test") is True

    def test_remote_cached_workspace(self):
        """Remote cached workspace should return False."""
        assert ch.is_native_workspace("remote_hostname_home-user") is False

    def test_wsl_cached_workspace(self):
        """WSL cached workspace should return False."""
        assert ch.is_native_workspace("wsl_Ubuntu_home-user") is False


class TestContentExtraction:
    """Tests for extract_content."""

    def test_extract_simple_text(self):
        """Simple text content extraction from assistant message."""
        # extract_content expects a message_obj dict with "content" key
        message_obj = {"content": [{"type": "text", "text": "Hello world"}]}
        result = ch.extract_content(message_obj)
        assert "Hello world" in result

    def test_extract_tool_use(self):
        """Tool use content extraction."""
        message_obj = {
            "content": [
                {"type": "text", "text": "Let me help"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
            ]
        }
        result = ch.extract_content(message_obj)
        assert "Let me help" in result
        assert "Bash" in result

    def test_extract_string_content(self):
        """String content (user messages)."""
        # User messages have simple string content
        message_obj = {"content": "Hello from user"}
        result = ch.extract_content(message_obj)
        assert result == "Hello from user"


class TestBase64Decoding:
    """Tests for decode_content."""

    def test_decode_valid_base64(self):
        """Valid base64 should decode correctly."""
        import base64

        original = "Hello World"
        encoded = base64.b64encode(original.encode()).decode()
        result = ch.decode_content(encoded)
        assert result == original

    def test_decode_invalid_base64(self):
        """Invalid base64 should return error message."""
        invalid = "not-valid-base64!!!"
        result = ch.decode_content(invalid)
        # The function returns an error message for invalid base64
        assert "Error" in result or result == invalid


# ============================================================================
# JSONL Reading Tests
# ============================================================================


class TestJSONLReading:
    """Tests for read_jsonl_messages."""

    def test_read_valid_jsonl(self, temp_projects_dir):
        """Should read and parse valid JSONL file."""
        session_file = temp_projects_dir / "-home-user-myproject" / "abc123-def456.jsonl"
        messages = ch.read_jsonl_messages(session_file)

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_read_extracts_timestamps(self, temp_projects_dir):
        """Should extract timestamps from messages."""
        session_file = temp_projects_dir / "-home-user-myproject" / "abc123-def456.jsonl"
        messages = ch.read_jsonl_messages(session_file)

        assert "timestamp" in messages[0]
        assert messages[0]["timestamp"] == "2025-11-20T10:30:45.123Z"

    def test_read_handles_missing_file(self, temp_projects_dir):
        """Should raise FileNotFoundError for missing file."""
        missing_file = temp_projects_dir / "nonexistent.jsonl"
        # The function raises FileNotFoundError for missing files
        with pytest.raises(FileNotFoundError):
            ch.read_jsonl_messages(missing_file)

    def test_read_handles_empty_file(self, temp_projects_dir):
        """Should return empty list for empty file."""
        empty_file = temp_projects_dir / "-home-user-myproject" / "empty.jsonl"
        empty_file.touch()
        messages = ch.read_jsonl_messages(empty_file)
        assert messages == []


# ============================================================================
# Workspace Session Tests
# ============================================================================


class TestWorkspaceSessions:
    """Tests for get_workspace_sessions."""

    def test_get_sessions_by_pattern(self, temp_projects_dir):
        """Should find sessions matching pattern."""
        sessions = ch.get_workspace_sessions("myproject", projects_dir=temp_projects_dir, quiet=True)

        assert len(sessions) == 1
        assert "myproject" in sessions[0]["workspace"]

    def test_get_sessions_empty_pattern(self, temp_projects_dir):
        """Empty pattern should match all workspaces."""
        sessions = ch.get_workspace_sessions("", projects_dir=temp_projects_dir, quiet=True)

        # Should find sessions from both workspaces
        assert len(sessions) >= 2

    def test_get_sessions_no_match(self, temp_projects_dir):
        """Non-matching pattern should return empty list."""
        sessions = ch.get_workspace_sessions("nonexistent-workspace-xyz", projects_dir=temp_projects_dir, quiet=True)

        assert sessions == []

    def test_sessions_include_file_info(self, temp_projects_dir):
        """Sessions should include file path and metadata."""
        sessions = ch.get_workspace_sessions("myproject", projects_dir=temp_projects_dir, quiet=True)

        assert len(sessions) == 1
        session = sessions[0]
        assert "file" in session
        assert "workspace" in session
        # The field is named "message_count" not "messages"
        assert "message_count" in session
        assert session["message_count"] == 2


# ============================================================================
# ExportConfig Tests
# ============================================================================


class TestExportConfig:
    """Tests for ExportConfig dataclass."""

    def test_create_with_defaults(self):
        """Should create with default values."""
        config = ch.ExportConfig(output_dir="/tmp/test", patterns=["myproject"])

        assert config.output_dir == "/tmp/test"
        assert config.patterns == ["myproject"]
        assert config.since is None
        assert config.until is None
        assert config.force is False
        assert config.minimal is False
        assert config.split is None
        assert config.flat is False
        assert config.remote is None
        assert config.lenient is False

    def test_workspace_property(self):
        """Workspace property should return first pattern."""
        config = ch.ExportConfig(output_dir="/tmp", patterns=["proj1", "proj2"])
        assert config.workspace == "proj1"

    def test_workspace_property_empty(self):
        """Workspace property should return empty string for empty patterns."""
        config = ch.ExportConfig(output_dir="/tmp", patterns=[])
        assert config.workspace == ""

    def test_from_args(self):
        """Should create config from args object."""

        class MockArgs:
            output_dir = "/tmp/export"
            patterns = ["test"]
            since = "2025-01-01"
            until = None
            force = True
            minimal = False
            split = 500
            flat = True
            remote = None
            lenient = False

        config = ch.ExportConfig.from_args(MockArgs())

        assert config.output_dir == "/tmp/export"
        assert config.patterns == ["test"]
        assert config.since == "2025-01-01"
        assert config.force is True
        assert config.split == 500
        assert config.flat is True

    def test_from_args_with_overrides(self):
        """Should apply overrides when creating from args."""

        class MockArgs:
            output_dir = "/tmp/default"
            patterns = ["default"]
            since = None
            until = None
            force = False
            minimal = False
            split = None
            flat = False
            remote = None
            lenient = False

        config = ch.ExportConfig.from_args(MockArgs(), output_dir="/tmp/override", patterns=["override"], force=True)

        assert config.output_dir == "/tmp/override"
        assert config.patterns == ["override"]
        assert config.force is True


# ============================================================================
# Markdown Generation Tests
# ============================================================================


class TestMarkdownGeneration:
    """Tests for parse_jsonl_to_markdown."""

    def test_generates_markdown_header(self, temp_projects_dir):
        """Should generate markdown with header."""
        session_file = temp_projects_dir / "-home-user-myproject" / "abc123-def456.jsonl"
        markdown = ch.parse_jsonl_to_markdown(session_file)

        assert "# Claude Conversation" in markdown
        assert "**Messages:** 2" in markdown

    def test_includes_message_content(self, temp_projects_dir):
        """Should include message content."""
        session_file = temp_projects_dir / "-home-user-myproject" / "abc123-def456.jsonl"
        markdown = ch.parse_jsonl_to_markdown(session_file)

        assert "Hello Claude" in markdown
        assert "Hello! How can I help?" in markdown

    def test_minimal_mode_excludes_metadata(self, temp_projects_dir):
        """Minimal mode should exclude metadata sections."""
        session_file = temp_projects_dir / "-home-user-myproject" / "abc123-def456.jsonl"

        full_md = ch.parse_jsonl_to_markdown(session_file, minimal=False)
        minimal_md = ch.parse_jsonl_to_markdown(session_file, minimal=True)

        # Full should have metadata, minimal should not
        assert "### Metadata" in full_md
        assert "### Metadata" not in minimal_md

    def test_accepts_preread_messages(self, temp_projects_dir):
        """Should accept pre-read messages to avoid re-reading file."""
        session_file = temp_projects_dir / "-home-user-myproject" / "abc123-def456.jsonl"
        messages = ch.read_jsonl_messages(session_file)

        # Pass pre-read messages
        markdown = ch.parse_jsonl_to_markdown(session_file, messages=messages)

        assert "Hello Claude" in markdown
        assert "**Messages:** 2" in markdown


# ============================================================================
# Alias/Config Storage Tests
# ============================================================================


class TestAliasStorage:
    """Tests for alias loading and saving."""

    def test_load_empty_aliases(self, temp_config_dir):
        """Should return default structure for missing file."""
        with patch.object(ch, "get_aliases_file", return_value=temp_config_dir / "aliases.json"):
            aliases = ch.load_aliases()
            assert aliases == {"version": 1, "aliases": {}}

    def test_save_and_load_aliases(self, temp_config_dir):
        """Should save and load aliases correctly."""
        aliases_file = temp_config_dir / "aliases.json"

        with patch.object(ch, "get_aliases_dir", return_value=temp_config_dir):
            with patch.object(ch, "get_aliases_file", return_value=aliases_file):
                # Save
                test_data = {"version": 1, "aliases": {"myproject": {"local": ["-home-user-myproject"]}}}
                result = ch.save_aliases(test_data)
                assert result is True

                # Load
                loaded = ch.load_aliases()
                assert loaded["aliases"]["myproject"]["local"] == ["-home-user-myproject"]


class TestConfigStorage:
    """Tests for config loading and saving."""

    def test_load_empty_config(self, temp_config_dir):
        """Should return default structure for missing file."""
        with patch.object(ch, "get_config_file", return_value=temp_config_dir / "config.json"):
            config = ch.load_config()
            assert config == {"version": 1, "sources": []}

    def test_save_and_load_config(self, temp_config_dir):
        """Should save and load config correctly."""
        config_file = temp_config_dir / "config.json"

        with patch.object(ch, "get_config_dir", return_value=temp_config_dir):
            with patch.object(ch, "get_config_file", return_value=config_file):
                # Save
                test_data = {"version": 1, "sources": ["user@host1", "user@host2"]}
                result = ch.save_config(test_data)
                assert result is True

                # Load
                loaded = ch.load_config()
                assert loaded["sources"] == ["user@host1", "user@host2"]


# ============================================================================
# Security Validation Tests
# ============================================================================


class TestSecurityValidation:
    """Tests for security-related validation functions."""

    def test_validate_remote_host_valid(self):
        """Valid remote hosts should pass."""
        assert ch.validate_remote_host("user@hostname") is True
        assert ch.validate_remote_host("user@server.example.com") is True
        assert ch.validate_remote_host("user123@host-name") is True

    def test_validate_remote_host_invalid(self):
        """Invalid remote hosts should fail."""
        assert ch.validate_remote_host("") is False
        assert ch.validate_remote_host("user@host; rm -rf /") is False
        assert ch.validate_remote_host("$(whoami)@host") is False
        assert ch.validate_remote_host("user@host`id`") is False

    def test_validate_workspace_name_valid(self):
        """Valid workspace names should pass."""
        assert ch.validate_workspace_name("-home-user-project") is True
        assert ch.validate_workspace_name("C--Users-test") is True
        assert ch.validate_workspace_name("my-project-123") is True

    def test_validate_workspace_name_invalid(self):
        """Invalid workspace names should fail."""
        assert ch.validate_workspace_name("") is False
        assert ch.validate_workspace_name("../../../etc/passwd") is False
        assert ch.validate_workspace_name("workspace; rm -rf /") is False


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
