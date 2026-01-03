#!/usr/bin/env python3
"""
Focused unit tests for agent-history helpers and CLI parsing (v2 CLI).
"""

import importlib.machinery
import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

# Load the agent-history script as a module (single-file CLI)
root_path = Path(__file__).resolve()
root_search = [root_path.parent, *root_path.parents]
module_path = None
for name in ["agent-history", "claude-history"]:
    for base in root_search:
        candidate = base / name
        if candidate.exists():
            module_path = candidate
            break
    if module_path:
        break
if module_path is None:
    raise FileNotFoundError("Could not locate 'agent-history' or 'claude-history'")
loader = importlib.machinery.SourceFileLoader("claude_history", str(module_path))
spec = importlib.util.spec_from_loader("claude_history", loader)
ch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ch)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / ".agent-history"
        config_dir.mkdir(parents=True)
        yield config_dir


# ============================================================================
# Parser sanity
# ============================================================================


def test_parser_ws_command():
    parser = ch._create_argument_parser()
    args = parser.parse_args(["ws"])
    assert args.command == "ws"
    assert getattr(args, "ws_verb", None) == "list"


def test_parser_session_list_and_export():
    parser = ch._create_argument_parser()
    list_args = parser.parse_args(["session"])
    assert list_args.command == "session"
    assert getattr(list_args, "session_verb", None) == "list"

    export_args = parser.parse_args(["session", "export", "-n", "proj", "-o", "/tmp/out"])
    assert export_args.command == "session"
    assert getattr(export_args, "session_verb", None) == "export"
    assert export_args.output_override == "/tmp/out"


def test_parser_project_add_and_stats():
    parser = ch._create_argument_parser()
    add_args = parser.parse_args(["project", "add", "myproj", "/tmp/work"])
    assert add_args.command == "project"
    assert add_args.project_command == "add"
    assert add_args.name == "myproj"

    stats_args = parser.parse_args(["project", "stats", "myproj"])
    assert stats_args.project_command == "stats"
    assert stats_args.name == "myproj"


def test_parser_home_export():
    parser = ch._create_argument_parser()
    args = parser.parse_args(["home", "export", "local", "-o", "/tmp/out"])
    assert args.command == "home"
    assert args.home_verb == "export"
    assert args.output_override == "/tmp/out"


# ============================================================================
# Pattern matching helpers
# ============================================================================


def test_matches_any_pattern_exact_prefix_equal():
    workspace = "/home/user/project"
    assert ch.matches_any_pattern(workspace, ["= /home/user/project".replace(" ", "")])
    assert not ch.matches_any_pattern(workspace, ["=other"])


def test_matches_workspace_pattern_exact_and_readable(monkeypatch):
    # pattern startswith '=' should match either raw or readable value
    workspace = "-home-user-proj"

    def fake_readable(_: str) -> str:
        return "/home/user/proj"

    assert ch._matches_workspace_pattern(
        workspace, "= -home-user-proj".replace(" ", ""), fake_readable
    )
    assert ch._matches_workspace_pattern(workspace, "=/home/user/proj", fake_readable)
    assert not ch._matches_workspace_pattern(workspace, "=other", fake_readable)


# ============================================================================
# Alias/Projects config helpers
# ============================================================================


def test_load_empty_aliases(temp_config_dir, monkeypatch):
    monkeypatch.setattr(ch, "get_aliases_dir", lambda: temp_config_dir)
    monkeypatch.setattr(ch, "get_config_dir", lambda: temp_config_dir)
    monkeypatch.setattr(ch, "get_projects_file", lambda: temp_config_dir / "projects.json")
    aliases = ch.load_aliases()
    assert aliases == {"version": 2, "projects": {}}


def test_save_and_load_aliases(temp_config_dir, monkeypatch):
    monkeypatch.setattr(ch, "get_aliases_dir", lambda: temp_config_dir)
    monkeypatch.setattr(ch, "get_config_dir", lambda: temp_config_dir)
    projects_file = temp_config_dir / "projects.json"
    monkeypatch.setattr(ch, "get_projects_file", lambda: projects_file)

    data = {"version": 2, "projects": {"p": {"local": ["-home-user-proj"]}}}
    assert ch.save_aliases(data)
    loaded = ch.load_aliases()
    assert loaded["projects"]["p"]["local"] == ["-home-user-proj"]


def test_alias_import_replace_creates_backup(monkeypatch, temp_config_dir, tmp_path):
    monkeypatch.setattr(ch, "get_aliases_dir", lambda: temp_config_dir)
    monkeypatch.setattr(ch, "get_config_dir", lambda: temp_config_dir)
    projects_file = temp_config_dir / "projects.json"
    projects_file.write_text(json.dumps({"version": 1, "projects": {"old": {"local": ["ws1"]}}}))

    import_file = tmp_path / "import.json"
    new_aliases = {"version": 1, "projects": {"new": {"local": ["ws2"]}}}
    import_file.write_text(json.dumps(new_aliases))

    args = SimpleNamespace(file=str(import_file), replace=True)
    ch.cmd_project_config_import(args)

    backups = list(temp_config_dir.glob("projects.backup.*.json"))
    assert backups, "Expected backup before replace"
    loaded = json.loads(projects_file.read_text())
    assert "new" in loaded.get("projects", {})
