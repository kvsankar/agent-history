"""Advanced web session credential and workspace tests."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers.module_loader import load_agent_history

pytestmark = pytest.mark.v1


def _patch_home(module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Force Path.home() to tmp_path for the module under test."""
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path)


def test_resolve_web_credentials_missing_token_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """If no token is available, resolve_web_credentials should error."""
    module = load_agent_history()
    _patch_home(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, "get_access_token", lambda: None)
    with pytest.raises(module.WebSessionsError):
        module.resolve_web_credentials(token=None, org_uuid="some-uuid")


def test_resolve_web_credentials_missing_org_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """If org UUID is missing, resolve_web_credentials should error."""
    module = load_agent_history()
    _patch_home(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, "get_access_token", lambda: "tok")
    monkeypatch.setattr(module, "get_org_uuid_from_claude_config", lambda: None)
    with pytest.raises(module.WebSessionsError):
        module.resolve_web_credentials(token=None, org_uuid=None)


def test_get_access_token_from_keychain_success(monkeypatch: pytest.MonkeyPatch):
    """Keychain lookup on macOS should return token when JSON is valid."""
    module = load_agent_history()
    monkeypatch.setattr(sys, "platform", "darwin")
    mock_result = MagicMock(returncode=0, stdout='{"claudeAiOauth": {"accessToken": "keychain-token"}}')
    with patch("subprocess.run", return_value=mock_result):
        assert module.get_access_token_from_keychain() == "keychain-token"


def test_get_access_token_from_keychain_invalid_json(monkeypatch: pytest.MonkeyPatch):
    """Invalid JSON from keychain should return None."""
    module = load_agent_history()
    monkeypatch.setattr(sys, "platform", "darwin")
    mock_result = MagicMock(returncode=0, stdout="not json")
    with patch("subprocess.run", return_value=mock_result):
        assert module.get_access_token_from_keychain() is None


def test_get_access_token_from_keychain_subprocess_error(monkeypatch: pytest.MonkeyPatch):
    """Subprocess errors should return None."""
    module = load_agent_history()
    monkeypatch.setattr(sys, "platform", "darwin")
    with patch("subprocess.run", side_effect=module.subprocess.SubprocessError("fail")):
        assert module.get_access_token_from_keychain() is None


def test_get_access_token_from_keychain_missing_binary(monkeypatch: pytest.MonkeyPatch):
    """Missing security binary should return None."""
    module = load_agent_history()
    monkeypatch.setattr(sys, "platform", "darwin")
    with patch("subprocess.run", side_effect=FileNotFoundError("security not found")):
        assert module.get_access_token_from_keychain() is None


def test_get_web_session_workspace_prefers_repo_string_when_no_map(monkeypatch: pytest.MonkeyPatch):
    """When no map is provided, workspace should fall back to repo string."""
    module = load_agent_history()
    session = {
        "session_context": {
            "sources": [{"type": "git_repository", "url": "https://github.com/owner/repo.git"}]
        }
    }
    assert module.get_web_session_workspace(session) == "owner/repo"


def test_get_web_session_workspace_invalid_session_context(monkeypatch: pytest.MonkeyPatch):
    """Graceful handling when session_context is non-JSON string."""
    module = load_agent_history()
    session = {"session_context": "not-json"}
    assert module.get_web_session_workspace(session) is None
