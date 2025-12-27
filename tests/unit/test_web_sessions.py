"""Unit tests for web sessions functionality."""

import importlib.util
import json

# Import functions from agent-history
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load agent-history as a module
spec = importlib.util.spec_from_loader("agent_history", loader=None)
agent_history = importlib.util.module_from_spec(spec)
with open(Path(__file__).parent.parent.parent / "agent-history") as f:
    code = f.read()
exec(compile(code, "agent-history", "exec"), agent_history.__dict__)


class TestWebCredentials:
    """Tests for credential resolution."""

    def test_get_org_uuid_from_claude_config_exists(self, tmp_path, monkeypatch):
        """Test reading org UUID from ~/.claude.json when it exists."""
        config_file = tmp_path / ".claude.json"
        config_file.write_text(json.dumps({"oauthAccount": {"organizationUuid": "test-org-uuid"}}))
        monkeypatch.setenv("HOME", str(tmp_path))

        # Patch Path.home() to return tmp_path
        with patch.object(Path, "home", return_value=tmp_path):
            result = agent_history.get_org_uuid_from_claude_config()

        assert result == "test-org-uuid"

    def test_get_org_uuid_from_claude_config_missing(self, tmp_path, monkeypatch):
        """Test reading org UUID when ~/.claude.json doesn't exist."""
        monkeypatch.setenv("HOME", str(tmp_path))

        with patch.object(Path, "home", return_value=tmp_path):
            result = agent_history.get_org_uuid_from_claude_config()

        assert result is None

    def test_get_org_uuid_from_claude_config_invalid_json(self, tmp_path, monkeypatch):
        """Test reading org UUID from invalid JSON file."""
        config_file = tmp_path / ".claude.json"
        config_file.write_text("not valid json")
        monkeypatch.setenv("HOME", str(tmp_path))

        with patch.object(Path, "home", return_value=tmp_path):
            result = agent_history.get_org_uuid_from_claude_config()

        assert result is None

    def test_get_access_token_from_keychain_non_macos(self, monkeypatch):
        """Test keychain access returns None on non-macOS."""
        monkeypatch.setattr(sys, "platform", "linux")
        result = agent_history.get_access_token_from_keychain()
        assert result is None

    def test_resolve_web_credentials_missing_token_non_macos(self, monkeypatch):
        """Test that missing token on non-macOS raises appropriate error."""
        monkeypatch.setattr(sys, "platform", "linux")

        with pytest.raises(agent_history.WebSessionsError) as exc_info:
            agent_history.resolve_web_credentials(token=None, org_uuid="some-uuid")

        assert "non-macOS" in str(exc_info.value)
        assert "--token" in str(exc_info.value)

    def test_resolve_web_credentials_missing_org_uuid(self, tmp_path, monkeypatch):
        """Test that missing org UUID raises appropriate error."""
        monkeypatch.setenv("HOME", str(tmp_path))

        with patch.object(Path, "home", return_value=tmp_path):
            with pytest.raises(agent_history.WebSessionsError) as exc_info:
                agent_history.resolve_web_credentials(token="some-token", org_uuid=None)

        assert "organization UUID" in str(exc_info.value)

    def test_resolve_web_credentials_both_provided(self):
        """Test that provided credentials are returned as-is."""
        token, org_uuid = agent_history.resolve_web_credentials(token="my-token", org_uuid="my-org")

        assert token == "my-token"
        assert org_uuid == "my-org"


class TestWebSessionConversion:
    """Tests for web session data conversion."""

    def test_web_session_to_jsonl_basic(self):
        """Test converting basic web session to JSONL."""
        session_data = {
            "loglines": [
                {"type": "user", "message": {"content": "Hello"}},
                {"type": "assistant", "message": {"content": "Hi there!"}},
            ]
        }

        result = agent_history.web_session_to_jsonl(session_data)
        lines = result.strip().split("\n")

        assert len(lines) == 2
        assert json.loads(lines[0])["type"] == "user"
        assert json.loads(lines[1])["type"] == "assistant"

    def test_web_session_to_jsonl_filters_non_messages(self):
        """Test that non-user/assistant entries are filtered out."""
        session_data = {
            "loglines": [
                {"type": "system", "data": "something"},
                {"type": "user", "message": {"content": "Hello"}},
                {"type": "tool_use", "data": "something"},
                {"type": "assistant", "message": {"content": "Hi!"}},
            ]
        }

        result = agent_history.web_session_to_jsonl(session_data)
        lines = result.strip().split("\n")

        assert len(lines) == 2
        assert all(json.loads(line)["type"] in ("user", "assistant") for line in lines)

    def test_web_session_to_jsonl_empty(self):
        """Test converting empty session."""
        session_data = {"loglines": []}

        result = agent_history.web_session_to_jsonl(session_data)

        assert result == ""

    def test_web_session_to_jsonl_unicode(self):
        """Test that Unicode characters are preserved."""
        session_data = {
            "loglines": [
                {"type": "user", "message": {"content": "Hello 世界 🌍"}},
            ]
        }

        result = agent_history.web_session_to_jsonl(session_data)
        parsed = json.loads(result)

        assert "世界" in parsed["message"]["content"]
        assert "🌍" in parsed["message"]["content"]


class TestWebAPIRequest:
    """Tests for web API request handling."""

    def test_make_web_api_request_success(self):
        """Test successful API request."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": [{"id": "123"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = agent_history._make_web_api_request("/sessions", "token", "org-uuid")

        assert result == {"data": [{"id": "123"}]}

    def test_make_web_api_request_http_error(self):
        """Test handling of HTTP errors."""
        import urllib.error

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError("url", 401, "Unauthorized", {}, None),
        ):
            with pytest.raises(agent_history.WebSessionsError) as exc_info:
                agent_history._make_web_api_request("/sessions", "bad-token", "org")

        assert "401" in str(exc_info.value)

    def test_make_web_api_request_network_error(self):
        """Test handling of network errors."""
        import urllib.error

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            with pytest.raises(agent_history.WebSessionsError) as exc_info:
                agent_history._make_web_api_request("/sessions", "token", "org")

        assert "Network error" in str(exc_info.value)


class TestFetchWebSessions:
    """Tests for fetching web sessions."""

    def test_fetch_web_sessions_returns_data(self):
        """Test that fetch_web_sessions returns session list."""
        with patch.object(
            agent_history,
            "_make_web_api_request",
            return_value={"data": [{"id": "1"}, {"id": "2"}]},
        ):
            result = agent_history.fetch_web_sessions("token", "org")

        assert len(result) == 2
        assert result[0]["id"] == "1"

    def test_fetch_web_session_single(self):
        """Test fetching a single web session."""
        mock_session = {
            "uuid": "abc123",
            "loglines": [{"type": "user", "message": {"content": "Test"}}],
        }

        with patch.object(agent_history, "_make_web_api_request", return_value=mock_session):
            result = agent_history.fetch_web_session("token", "org", "abc123")

        assert result["uuid"] == "abc123"
        assert len(result["loglines"]) == 1
