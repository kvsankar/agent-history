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

    def test_get_access_token_from_credentials_file_exists(self, tmp_path):
        """Test token retrieval from credentials file."""
        # Create credentials file
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('{"claudeAiOauth": {"accessToken": "test-token-123"}}')

        with patch.object(Path, "home", return_value=tmp_path):
            result = agent_history.get_access_token_from_credentials_file()

        assert result == "test-token-123"

    def test_get_access_token_from_credentials_file_missing(self, tmp_path):
        """Test returns None when credentials file doesn't exist."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = agent_history.get_access_token_from_credentials_file()

        assert result is None

    def test_get_access_token_from_credentials_file_invalid_json(self, tmp_path):
        """Test returns None for invalid JSON in credentials file."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text("not valid json")

        with patch.object(Path, "home", return_value=tmp_path):
            result = agent_history.get_access_token_from_credentials_file()

        assert result is None

    def test_get_access_token_uses_both_sources(self, tmp_path, monkeypatch):
        """Test get_access_token checks both keychain and credentials file."""
        monkeypatch.setattr(sys, "platform", "linux")  # Keychain won't work

        # Create credentials file with token
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('{"claudeAiOauth": {"accessToken": "file-token"}}')

        with patch.object(Path, "home", return_value=tmp_path):
            result = agent_history.get_access_token()

        assert result == "file-token"

    def test_resolve_web_credentials_missing_token_non_macos(self, tmp_path, monkeypatch):
        """Test that missing token on non-macOS raises appropriate error."""
        monkeypatch.setattr(sys, "platform", "linux")

        # Ensure no credentials file exists
        with patch.object(Path, "home", return_value=tmp_path):
            with pytest.raises(agent_history.WebSessionsError) as exc_info:
                agent_history.resolve_web_credentials(token=None, org_uuid="some-uuid")

        assert "access token" in str(exc_info.value).lower()
        assert ".credentials.json" in str(exc_info.value)

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

    def test_get_web_session_workspace_from_sources(self):
        """Test workspace extraction from session_context.sources."""
        session = {
            "session_context": {
                "sources": [{"type": "git_repository", "url": "https://github.com/owner/repo"}]
            }
        }
        result = agent_history.get_web_session_workspace(session)
        assert result == "owner/repo"

    def test_get_web_session_workspace_from_outcomes(self):
        """Test workspace extraction from session_context.outcomes."""
        session = {
            "session_context": {
                "outcomes": [{"git_info": {"repo": "owner/repo", "type": "github"}}]
            }
        }
        result = agent_history.get_web_session_workspace(session)
        assert result == "owner/repo"

    def test_get_web_session_workspace_from_cwd(self):
        """Test workspace extraction falls back to cwd."""
        session = {"session_context": {"cwd": "/home/user/project"}}
        result = agent_history.get_web_session_workspace(session)
        assert result == "/home/user/project"

    def test_get_web_session_workspace_empty(self):
        """Test workspace extraction returns None when no context."""
        session = {}
        result = agent_history.get_web_session_workspace(session)
        assert result is None

    def test_get_web_session_workspace_json_string(self):
        """Test workspace extraction handles JSON string context."""
        import json

        session = {
            "session_context": json.dumps(
                {"sources": [{"type": "git_repository", "url": "https://github.com/a/b"}]}
            )
        }
        result = agent_history.get_web_session_workspace(session)
        assert result == "a/b"

    def test_get_web_session_workspace_with_github_map(self):
        """Test workspace resolves to local path when github_map provided."""
        session = {
            "session_context": {
                "sources": [{"type": "git_repository", "url": "https://github.com/owner/repo"}]
            }
        }
        github_map = {"owner/repo": "home/user/projects/repo"}
        result = agent_history.get_web_session_workspace(session, github_map)
        assert result == "home/user/projects/repo"

    def test_get_web_session_workspace_no_match_in_map(self):
        """Test workspace returns repo when no match in github_map."""
        session = {
            "session_context": {
                "sources": [{"type": "git_repository", "url": "https://github.com/owner/repo"}]
            }
        }
        github_map = {"other/repo": "home/user/other"}
        result = agent_history.get_web_session_workspace(session, github_map)
        assert result == "owner/repo"

    def test_extract_github_repo_https(self):
        """Test extraction from HTTPS URL."""
        assert (
            agent_history.extract_github_repo_from_git_url("https://github.com/owner/repo")
            == "owner/repo"
        )
        assert (
            agent_history.extract_github_repo_from_git_url("https://github.com/owner/repo.git")
            == "owner/repo"
        )

    def test_extract_github_repo_ssh(self):
        """Test extraction from SSH URL."""
        assert (
            agent_history.extract_github_repo_from_git_url("git@github.com:owner/repo.git")
            == "owner/repo"
        )

    def test_extract_github_repo_ssh_alias(self):
        """Test extraction from SSH alias URL."""
        assert (
            agent_history.extract_github_repo_from_git_url("github-alias:owner/repo.git")
            == "owner/repo"
        )
        assert (
            agent_history.extract_github_repo_from_git_url(
                "git@github-kvsankar:kvsankar/skyfield-ts.git"
            )
            == "kvsankar/skyfield-ts"
        )

    def test_extract_github_repo_non_github(self):
        """Test returns None for non-GitHub URLs."""
        assert (
            agent_history.extract_github_repo_from_git_url("git@gitlab.com:owner/repo.git") is None
        )
        assert (
            agent_history.extract_github_repo_from_git_url("git@essence:Essence-10/BP-v1.git")
            is None
        )


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


class TestWorkspaceURI:
    """Tests for workspace URI generation and parsing."""

    # ==================== make_workspace_uri tests ====================

    def test_make_workspace_uri_local_path(self):
        """Test local path URI generation."""
        result = agent_history.make_workspace_uri(location="local", path="/home/user/project")
        assert result == "/home/user/project"

    def test_make_workspace_uri_local_with_github(self):
        """Test local path with GitHub correlation."""
        result = agent_history.make_workspace_uri(
            location="local", path="/home/user/project", github_repo="owner/repo"
        )
        assert result == "/home/user/project@github.com/owner/repo"

    def test_make_workspace_uri_remote(self):
        """Test remote SSH URI generation."""
        result = agent_history.make_workspace_uri(
            location="remote", host="user@vm01", path="/home/user/project"
        )
        assert result == "user@vm01:/home/user/project"

    def test_make_workspace_uri_remote_with_github(self):
        """Test remote SSH URI with GitHub correlation."""
        result = agent_history.make_workspace_uri(
            location="remote",
            host="user@vm01",
            path="/home/user/project",
            github_repo="owner/repo",
        )
        assert result == "user@vm01:/home/user/project@github.com/owner/repo"

    def test_make_workspace_uri_wsl(self):
        """Test WSL URI generation."""
        result = agent_history.make_workspace_uri(
            location="wsl", host="Ubuntu", path="/home/user/project"
        )
        assert result == "wsl:Ubuntu:/home/user/project"

    def test_make_workspace_uri_wsl_without_host(self):
        """Test WSL URI without distro name."""
        result = agent_history.make_workspace_uri(location="wsl", path="/home/user/project")
        assert result == "wsl:/home/user/project"

    def test_make_workspace_uri_windows(self):
        """Test Windows URI generation with username."""
        result = agent_history.make_workspace_uri(
            location="windows", host="alice", path="C:\\Users\\alice\\project"
        )
        assert result == "windows:alice:C:\\Users\\alice\\project"

    def test_make_workspace_uri_windows_path_only(self):
        """Test Windows URI with path only."""
        result = agent_history.make_workspace_uri(
            location="windows", path="C:\\Users\\alice\\project"
        )
        assert result == "C:\\Users\\alice\\project"

    def test_make_workspace_uri_web_session(self):
        """Test web session URI generation."""
        result = agent_history.make_workspace_uri(location="web", session_id="session_xyz")
        assert result == "claude.ai/session/session_xyz"

    def test_make_workspace_uri_web_with_github(self):
        """Test web session URI with GitHub correlation."""
        result = agent_history.make_workspace_uri(
            location="web", session_id="session_xyz", github_repo="owner/repo"
        )
        assert result == "claude.ai/session/session_xyz@github.com/owner/repo"

    def test_make_workspace_uri_web_no_session(self):
        """Test web session URI without session ID."""
        result = agent_history.make_workspace_uri(location="web")
        assert result == "claude.ai"

    def test_make_workspace_uri_gemini_unmapped(self):
        """Test Gemini unmapped hash URI generation."""
        result = agent_history.make_workspace_uri(location="gemini", gemini_hash="321784d9")
        assert result == "urn:gemini:321784d9"

    def test_make_workspace_uri_gemini_with_path(self):
        """Test Gemini URI with mapped path."""
        result = agent_history.make_workspace_uri(
            location="gemini", path="/home/user/project", gemini_hash="321784d9"
        )
        assert result == "/home/user/project@gemini:321784d9"

    # ==================== parse_workspace_uri tests ====================

    def test_parse_workspace_uri_local_path(self):
        """Test parsing local path URI."""
        result = agent_history.parse_workspace_uri("/home/user/project")
        assert result.location == "local"
        assert result.path == "/home/user/project"
        assert result.github_repo is None

    def test_parse_workspace_uri_local_with_github(self):
        """Test parsing local path with GitHub suffix."""
        result = agent_history.parse_workspace_uri("/home/user/project@github.com/owner/repo")
        assert result.location == "local"
        assert result.path == "/home/user/project"
        assert result.github_repo == "owner/repo"

    def test_parse_workspace_uri_remote_ssh(self):
        """Test parsing remote SSH format."""
        result = agent_history.parse_workspace_uri("user@vm01:/home/user/project")
        assert result.location == "remote"
        assert result.host == "user@vm01"
        assert result.path == "/home/user/project"

    def test_parse_workspace_uri_remote_with_github(self):
        """Test parsing remote SSH with GitHub suffix."""
        result = agent_history.parse_workspace_uri(
            "user@vm01:/home/user/project@github.com/owner/repo"
        )
        assert result.location == "remote"
        assert result.host == "user@vm01"
        assert result.path == "/home/user/project"
        assert result.github_repo == "owner/repo"

    def test_parse_workspace_uri_wsl(self):
        """Test parsing WSL URI."""
        result = agent_history.parse_workspace_uri("wsl:Ubuntu:/home/user/project")
        assert result.location == "wsl"
        assert result.host == "Ubuntu"
        assert result.path == "/home/user/project"

    def test_parse_workspace_uri_wsl_without_host(self):
        """Test parsing WSL URI without distro."""
        result = agent_history.parse_workspace_uri("wsl:/home/user/project")
        assert result.location == "wsl"
        assert result.host is None
        assert result.path == "/home/user/project"

    def test_parse_workspace_uri_windows_prefixed(self):
        """Test parsing Windows prefixed URI."""
        result = agent_history.parse_workspace_uri("windows:alice:C:\\Users\\alice\\project")
        assert result.location == "windows"
        assert result.host == "alice"
        assert result.path == "C:\\Users\\alice\\project"

    def test_parse_workspace_uri_windows_drive_path(self):
        """Test parsing Windows drive path directly."""
        result = agent_history.parse_workspace_uri("C:\\Users\\alice\\project")
        assert result.location == "windows"
        assert result.path == "C:\\Users\\alice\\project"
        assert result.host is None

    def test_parse_workspace_uri_web_session(self):
        """Test parsing web session URI."""
        result = agent_history.parse_workspace_uri("claude.ai/session/session_xyz")
        assert result.location == "web"
        assert result.session_id == "session_xyz"

    def test_parse_workspace_uri_web_with_github(self):
        """Test parsing web session with GitHub suffix."""
        result = agent_history.parse_workspace_uri(
            "claude.ai/session/session_xyz@github.com/owner/repo"
        )
        assert result.location == "web"
        assert result.session_id == "session_xyz"
        assert result.github_repo == "owner/repo"

    def test_parse_workspace_uri_gemini_urn(self):
        """Test parsing Gemini URN format."""
        result = agent_history.parse_workspace_uri("urn:gemini:321784d9")
        assert result.location == "gemini"
        assert result.gemini_hash == "321784d9"

    def test_parse_workspace_uri_gemini_with_path(self):
        """Test parsing path with Gemini hash suffix."""
        result = agent_history.parse_workspace_uri("/home/user/project@gemini:321784d9")
        assert result.location == "local"
        assert result.path == "/home/user/project"
        assert result.gemini_hash == "321784d9"

    def test_parse_workspace_uri_combined_suffixes(self):
        """Test parsing URI with both GitHub and Gemini suffixes."""
        result = agent_history.parse_workspace_uri(
            "/home/user/project@github.com/owner/repo@gemini:321784d9"
        )
        assert result.location == "local"
        assert result.path == "/home/user/project"
        assert result.github_repo == "owner/repo"
        assert result.gemini_hash == "321784d9"

    # ==================== Round-trip tests ====================

    def test_roundtrip_local(self):
        """Test round-trip for local path."""
        original = agent_history.make_workspace_uri(location="local", path="/home/user/project")
        parsed = agent_history.parse_workspace_uri(original)
        assert parsed.location == "local"
        assert parsed.path == "/home/user/project"

    def test_roundtrip_remote(self):
        """Test round-trip for remote SSH."""
        original = agent_history.make_workspace_uri(
            location="remote", host="user@vm01", path="/home/user/project"
        )
        parsed = agent_history.parse_workspace_uri(original)
        assert parsed.location == "remote"
        assert parsed.host == "user@vm01"
        assert parsed.path == "/home/user/project"

    def test_roundtrip_web_with_github(self):
        """Test round-trip for web session with GitHub."""
        original = agent_history.make_workspace_uri(
            location="web", session_id="abc123", github_repo="owner/repo"
        )
        parsed = agent_history.parse_workspace_uri(original)
        assert parsed.location == "web"
        assert parsed.session_id == "abc123"
        assert parsed.github_repo == "owner/repo"

    def test_roundtrip_wsl(self):
        """Test round-trip for WSL path."""
        original = agent_history.make_workspace_uri(
            location="wsl", host="Ubuntu", path="/home/user/project"
        )
        parsed = agent_history.parse_workspace_uri(original)
        assert parsed.location == "wsl"
        assert parsed.host == "Ubuntu"
        assert parsed.path == "/home/user/project"


class TestWorkspaceURIFromSource:
    """Tests for workspace_uri_from_source function."""

    def test_local_source(self):
        """Test URI generation for local source."""
        uri = agent_history.workspace_uri_from_source("Local", "/home/user/project")
        assert uri == "/home/user/project"

    def test_local_wsl_source(self):
        """Test URI generation for local WSL source."""
        uri = agent_history.workspace_uri_from_source("Local (WSL)", "/home/user/project")
        assert uri == "/home/user/project"

    def test_windows_source(self):
        """Test URI generation for Windows source."""
        uri = agent_history.workspace_uri_from_source(
            "Windows (kvsan)", "C:\\Users\\kvsan\\project"
        )
        assert uri == "windows:kvsan:C:\\Users\\kvsan\\project"

    def test_windows_source_mnt_path(self):
        """Test URI generation for Windows source with /mnt/c path."""
        uri = agent_history.workspace_uri_from_source(
            "Windows (kvsan)", "/mnt/c/Users/kvsan/project"
        )
        assert uri == "windows:kvsan:/mnt/c/Users/kvsan/project"

    def test_wsl_source(self):
        """Test URI generation for WSL source."""
        uri = agent_history.workspace_uri_from_source("WSL (Ubuntu)", "/home/user/project")
        assert uri == "wsl:Ubuntu:/home/user/project"

    def test_remote_source_colon(self):
        """Test URI generation for remote source with colon format."""
        uri = agent_history.workspace_uri_from_source("Remote: vm01", "/home/user/project")
        assert uri == "vm01:/home/user/project"

    def test_remote_source_parens(self):
        """Test URI generation for remote source with parentheses."""
        uri = agent_history.workspace_uri_from_source("Remote (vm01)", "/home/user/project")
        assert uri == "vm01:/home/user/project"

    def test_gemini_hash(self):
        """Test URI generation for Gemini hash workspace."""
        uri = agent_history.workspace_uri_from_source("Local", "[hash:321784d9]")
        assert uri == "urn:gemini:321784d9"

    def test_web_source(self):
        """Test URI generation for web source."""
        uri = agent_history.workspace_uri_from_source(
            "Web", "session_abc", github_repo="owner/repo"
        )
        assert uri == "claude.ai/session/session_abc@github.com/owner/repo"

    def test_with_github_repo(self):
        """Test URI generation with GitHub repo correlation."""
        uri = agent_history.workspace_uri_from_source(
            "Local", "/home/user/project", github_repo="owner/repo"
        )
        assert uri == "/home/user/project@github.com/owner/repo"
