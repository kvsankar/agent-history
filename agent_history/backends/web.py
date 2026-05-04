"""Claude.ai web sessions backend for agent-history.

This module handles authentication discovery, session listing, and
session retrieval from the Claude web API. It also provides helpers
to map web sessions to local workspaces when GitHub metadata is present.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from agent_history.storage.config import get_config_dir
from agent_history.utils.paths import normalize_workspace_name

WEB_API_BASE_URL = "https://api.anthropic.com/v1"
WEB_API_VERSION = "2023-06-01"


class WebSessionsError(RuntimeError):
    """Error accessing Claude web sessions."""


def get_access_token_from_keychain() -> Optional[str]:
    """Get Claude web access token from macOS Keychain."""
    if sys.platform != "darwin":
        return None

    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                os.environ.get("USER", ""),
                "-s",
                "Claude Code-credentials",
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    try:
        creds = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return None

    return creds.get("claudeAiOauth", {}).get("accessToken")


def get_access_token_from_credentials_file() -> Optional[str]:
    """Get Claude web access token from ~/.claude/.credentials.json."""
    creds_path = Path.home() / ".claude" / ".credentials.json"
    if not creds_path.exists():
        return None

    try:
        with open(creds_path, encoding="utf-8") as handle:
            creds = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    return creds.get("claudeAiOauth", {}).get("accessToken")


def get_access_token() -> Optional[str]:
    """Resolve Claude web access token from available sources."""
    token = get_access_token_from_keychain()
    if token:
        return token
    return get_access_token_from_credentials_file()


def get_org_uuid_from_claude_config() -> Optional[str]:
    """Get Claude organization UUID from ~/.claude.json."""
    config_path = Path.home() / ".claude.json"
    if not config_path.exists():
        return None

    try:
        with open(config_path, encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    return config.get("oauthAccount", {}).get("organizationUuid")


def resolve_web_credentials(
    token: Optional[str] = None, org_uuid: Optional[str] = None
) -> tuple[str, str]:
    """Resolve web API credentials or raise if missing."""
    if token is None:
        token = get_access_token()
    if not token:
        raise WebSessionsError(
            "Missing Claude web access token. "
            "Log in with Claude Code to populate ~/.claude/.credentials.json."
        )

    if org_uuid is None:
        org_uuid = get_org_uuid_from_claude_config()
    if not org_uuid:
        raise WebSessionsError(
            "Missing Claude organization UUID. "
            "Provide ~/.claude.json or use --org-uuid."
        )

    return token, org_uuid


def _make_web_api_request(endpoint: str, token: str, org_uuid: str, timeout: int = 30) -> dict:
    """Make an authenticated Claude web API request."""
    url = f"{WEB_API_BASE_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-version": WEB_API_VERSION,
        "Content-Type": "application/json",
        "x-organization-uuid": org_uuid,
    }
    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise WebSessionsError(f"API error {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise WebSessionsError(f"Network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise WebSessionsError(f"Invalid JSON response: {exc}") from exc


def fetch_web_sessions(token: str, org_uuid: str) -> list[dict]:
    """Fetch list of web sessions from the Claude API."""
    data = _make_web_api_request("/sessions", token, org_uuid)
    return data.get("data", [])


def fetch_web_session(token: str, org_uuid: str, session_id: str) -> dict:
    """Fetch a specific web session (loglines included)."""
    return _make_web_api_request(
        f"/session_ingress/session/{session_id}", token, org_uuid, timeout=60
    )


def web_session_to_jsonl(session_data: dict) -> str:
    """Convert web session loglines to JSONL string."""
    lines = []
    for entry in session_data.get("loglines", []):
        if entry.get("type") not in ("user", "assistant"):
            continue
        lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines)


def get_web_cache_dir() -> Path:
    """Return cache directory for web session JSONL files."""
    return get_config_dir() / "web-cache"


def ensure_web_session_cache(
    session_id: str, token: str, org_uuid: str, force: bool = False
) -> Path:
    """Ensure a local JSONL cache exists for a web session."""
    cache_dir = get_web_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = cache_dir / f"{session_id}.jsonl"
    if jsonl_path.exists() and not force:
        return jsonl_path

    session_data = fetch_web_session(token, org_uuid, session_id)
    jsonl_path.write_text(web_session_to_jsonl(session_data), encoding="utf-8")
    return jsonl_path


def extract_github_repo_from_git_url(url: str) -> Optional[str]:
    """Extract owner/repo from git remote URL if hosted on GitHub."""
    if not url:
        return None

    if "github.com/" in url:
        repo = url.split("github.com/")[-1]
        return repo.rstrip("/").removesuffix(".git")

    if ":" in url and "/" in url.split(":")[-1]:
        host_part = url.split(":")[0]
        if "github" in host_part.lower():
            repo_part = url.split(":")[-1]
            return repo_part.removesuffix(".git")

    return None


def get_web_session_github_repo(session: dict) -> Optional[str]:
    """Extract GitHub repo (owner/repo) from a web session summary."""
    ctx = session.get("session_context", {})
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except (json.JSONDecodeError, TypeError):
            return None

    sources = ctx.get("sources", [])
    for src in sources:
        if src.get("type") == "git_repository":
            repo = extract_github_repo_from_git_url(src.get("url", ""))
            if repo:
                return repo

    outcomes = ctx.get("outcomes", [])
    for outcome in outcomes:
        git_info = outcome.get("git_info", {})
        if git_info.get("repo"):
            return git_info.get("repo")

    return None


def build_github_to_workspace_map(projects_dir: Optional[Path]) -> dict[str, str]:
    """Build a map of GitHub repos to local workspace paths."""
    repo_map: dict[str, str] = {}
    if not projects_dir or not projects_dir.exists():
        return repo_map

    for workspace_dir in projects_dir.iterdir():
        if not workspace_dir.is_dir():
            continue
        if workspace_dir.name.startswith(("remote_", "wsl_", "windows_")):
            continue

        workspace_path = normalize_workspace_name(workspace_dir.name)
        actual_path = Path(workspace_path)
        if not actual_path.is_absolute():
            actual_path = Path("/") / workspace_path.lstrip("/")

        git_dir = actual_path / ".git"
        if not git_dir.exists():
            continue

        try:
            result = subprocess.run(
                ["git", "-C", str(actual_path), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue

        if result.returncode != 0:
            continue

        repo = extract_github_repo_from_git_url(result.stdout.strip())
        if repo:
            repo_map[repo] = workspace_path

    return repo_map


def get_web_session_workspace(session: dict, github_map: Optional[dict] = None) -> Optional[str]:
    """Resolve a workspace identifier for a web session."""
    github_repo = get_web_session_github_repo(session)
    if github_repo:
        if github_map and github_repo in github_map:
            return github_map[github_repo]
        return github_repo

    ctx = session.get("session_context", {})
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except (json.JSONDecodeError, TypeError):
            return None

    cwd = ctx.get("cwd")
    if cwd:
        return cwd

    return None

