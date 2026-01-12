"""Web session credential and workspace resolution tests.

Spec Reference: docs/specs/agent-history-spec.md#web-session-access
"""

import json
from pathlib import Path

import pytest

from tests.helpers.module_loader import load_agent_history

pytestmark = pytest.mark.v1


def _patch_home(module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Force Path.home() to tmp_path for the module under test."""
    monkeypatch.setattr(module.Path, "home", lambda: tmp_path)


def test_access_token_from_credentials_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """File-based credentials should be read from ~/.claude/.credentials.json."""
    module = load_agent_history()
    _patch_home(module, tmp_path, monkeypatch)

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    creds_file = claude_dir / ".credentials.json"
    creds_file.write_text('{"claudeAiOauth": {"accessToken": "token-123"}}', encoding="utf-8")

    assert module.get_access_token_from_credentials_file() == "token-123"


def test_get_access_token_falls_back_to_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """get_access_token should fall back to file when keychain is unavailable."""
    module = load_agent_history()
    _patch_home(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, "get_access_token_from_keychain", lambda: None)

    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    creds_file = claude_dir / ".credentials.json"
    creds_file.write_text('{"claudeAiOauth": {"accessToken": "file-token"}}', encoding="utf-8")

    assert module.get_access_token() == "file-token"


def test_get_org_uuid_from_claude_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Organization UUID should be read from ~/.claude.json when present."""
    module = load_agent_history()
    _patch_home(module, tmp_path, monkeypatch)

    config_file = tmp_path / ".claude.json"
    config_file.write_text(
        json.dumps({"oauthAccount": {"organizationUuid": "org-uuid-123"}}),
        encoding="utf-8",
    )

    assert module.get_org_uuid_from_claude_config() == "org-uuid-123"


def test_web_session_workspace_prefers_github_map() -> None:
    """GitHub repo mapping should resolve to local workspace when available."""
    module = load_agent_history()
    session = {
        "session_context": {
            "sources": [
                {"type": "git_repository", "url": "https://github.com/owner/repo.git"},
            ]
        }
    }
    github_map = {"owner/repo": "/home/user/projects/repo"}

    workspace = module.get_web_session_workspace(session, github_map)
    assert workspace == "/home/user/projects/repo"


def test_web_session_workspace_falls_back_to_cwd() -> None:
    """When no repo is present, workspace falls back to session_context.cwd."""
    module = load_agent_history()
    session = {"session_context": json.dumps({"cwd": "/home/user/fallback"})}

    workspace = module.get_web_session_workspace(session)
    assert workspace == "/home/user/fallback"
