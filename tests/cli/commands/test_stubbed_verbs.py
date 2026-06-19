"""Tests for resource verbs that should be implemented."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.helpers.cli import assert_cli_success, run_cli_subprocess
from tests.helpers.gap_helpers import ensure_config_env
from tests.helpers.workspace_paths import encode_workspace_path

pytestmark = pytest.mark.scope


class TestStubbedVerbs:
    """Resource verbs should return real data, not "not implemented"."""

    def test_session_show_returns_details(self, current_workspace_setup: dict[str, Any]) -> None:
        session_id = current_workspace_setup["sessions"][0]
        claude_dir = Path(current_workspace_setup["env"]["CLAUDE_PROJECTS_DIR"])
        encoded_ws = encode_workspace_path(current_workspace_setup["workspace_path"])
        session_path = claude_dir / encoded_ws / f"{session_id}.jsonl"
        result = run_cli_subprocess(
            ["session", "show", str(session_path)],
            env=current_workspace_setup["env"],
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(result, "session show should succeed with details")

    def test_ws_show_returns_details(self, current_workspace_setup: dict[str, Any]) -> None:
        result = run_cli_subprocess(
            ["ws", "show", current_workspace_setup["workspace_path"]],
            env=current_workspace_setup["env"],
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(result, "ws show should succeed with details")

    def test_ws_export_writes_files(
        self, current_workspace_setup: dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "ws-export"
        result = run_cli_subprocess(
            [
                "ws",
                "export",
                current_workspace_setup["workspace_path"],
                str(output_dir),
            ],
            env=current_workspace_setup["env"],
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(result, "ws export should succeed")
        assert list(output_dir.rglob("*.md")), "Expected markdown exports for ws export"

    def test_ws_stats_returns_summary(self, current_workspace_setup: dict[str, Any]) -> None:
        result = run_cli_subprocess(
            [
                "ws",
                "stats",
                current_workspace_setup["workspace_path"],
                "--format",
                "json",
            ],
            env=current_workspace_setup["env"],
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(result, "ws stats should succeed")

    def test_home_show_returns_details(self, multi_home_setup: dict[str, Any]) -> None:
        result = run_cli_subprocess(
            ["home", "show", "local"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "home show should succeed with details")

    def test_home_export_writes_files(
        self, multi_home_setup: dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "home-export"
        result = run_cli_subprocess(
            ["home", "export", "local", str(output_dir)],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "home export should succeed")
        assert list(output_dir.rglob("*.md")), "Expected markdown exports for home export"

    def test_home_stats_returns_summary(self, multi_home_setup: dict[str, Any]) -> None:
        result = run_cli_subprocess(
            ["home", "stats", "local", "--format", "json"],
            env=multi_home_setup["env"],
        )

        assert_cli_success(result, "home stats should succeed")

    def test_project_add_creates_config(
        self, current_workspace_setup: dict[str, Any], tmp_path: Path
    ) -> None:
        env = ensure_config_env(current_workspace_setup["env"], tmp_path / ".agent-history")
        result = run_cli_subprocess(
            [
                "project",
                "add",
                "gap-project",
                current_workspace_setup["workspace_path"],
            ],
            env=env,
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(result, "project add should succeed")
        config_path = Path(env["AGENT_HISTORY_CONFIG_DIR"]) / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        project_def = config.get("projects", {}).get("gap-project", {})
        assert current_workspace_setup["workspace_path"] in project_def.get(
            "local", []
        ), "Expected project to be added"

    def test_project_add_glob_dry_run_does_not_update_config(
        self, multi_workspace_home: dict[str, Any]
    ) -> None:
        result = run_cli_subprocess(
            ["project", "add", "workspace-family", "--glob", "*", "--dry-run"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "project add --dry-run should succeed")
        assert "/home/user/project-alpha" in result.stdout
        assert "/home/user/project/beta" in result.stdout

        config_path = Path(multi_workspace_home["env"]["AGENT_HISTORY_CONFIG_DIR"]) / "config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            assert "workspace-family" not in config.get("projects", {})

    def test_project_add_glob_snapshots_resolved_workspaces(
        self, multi_workspace_home: dict[str, Any]
    ) -> None:
        result = run_cli_subprocess(
            ["project", "add", "workspace-family", "--glob", "*"],
            env=multi_workspace_home["env"],
        )

        assert_cli_success(result, "project add --glob should succeed")

        config_path = Path(multi_workspace_home["env"]["AGENT_HISTORY_CONFIG_DIR"]) / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        project_def = config.get("projects", {}).get("workspace-family", {})
        assert "/home/user/project-alpha" in project_def.get("local", [])
        assert "/home/user/project/beta" in project_def.get("local", [])

    def test_project_add_glob_no_match_reports_clear_error(
        self, multi_workspace_home: dict[str, Any]
    ) -> None:
        result = run_cli_subprocess(
            [
                "project",
                "add",
                "workspace-family",
                "--glob",
                "*does-not-match*",
            ],
            env=multi_workspace_home["env"],
        )

        assert result.returncode != 0
        assert "No matching workspaces found." in result.stdout
        assert "{'error':" not in result.stdout

    def test_project_add_dedupes_encoded_and_decoded_members(
        self, current_workspace_setup: dict[str, Any], tmp_path: Path
    ) -> None:
        config_dir = tmp_path / ".agent-history"
        env = ensure_config_env(current_workspace_setup["env"], config_dir)
        encoded = encode_workspace_path(current_workspace_setup["workspace_path"])
        config_path = config_dir / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "projects": {"gap-project": {"local": [encoded]}},
                    "homes": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = run_cli_subprocess(
            ["project", "add", "gap-project", current_workspace_setup["workspace_path"]],
            env=env,
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(result, "project add should treat encoded/path aliases as existing")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        project_members = config.get("projects", {}).get("gap-project", {}).get("local", [])
        assert project_members == [current_workspace_setup["workspace_path"]]

    def test_project_remove_updates_config(
        self, current_workspace_setup: dict[str, Any], tmp_path: Path
    ) -> None:
        config_dir = tmp_path / ".agent-history"
        env = ensure_config_env(current_workspace_setup["env"], config_dir)
        config_path = config_dir / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "projects": {
                        "gap-project": {"local": [current_workspace_setup["workspace_path"]]}
                    },
                    "homes": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = run_cli_subprocess(
            ["project", "remove", "gap-project", current_workspace_setup["workspace_path"]],
            env=env,
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(result, "project remove should succeed")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        assert current_workspace_setup["workspace_path"] not in config.get("projects", {}).get(
            "gap-project", {}
        ).get("local", []), "Expected workspace to be removed from project"

    def test_tag_add_list_remove_updates_project_tags(
        self, current_workspace_setup: dict[str, Any], tmp_path: Path
    ) -> None:
        config_dir = tmp_path / ".agent-history"
        env = ensure_config_env(current_workspace_setup["env"], config_dir)
        config_path = config_dir / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "projects": {
                        "gap-project": {"local": [current_workspace_setup["workspace_path"]]}
                    },
                    "homes": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        add_result = run_cli_subprocess(
            ["tag", "add", "--project", "gap-project", "Work Stuff", "client_a"],
            env=env,
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(add_result, "tag add should succeed")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        assert config["project_tags"]["gap-project"] == ["work-stuff", "client_a"]

        list_result = run_cli_subprocess(
            ["tag", "list", "--format", "json"],
            env=env,
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(list_result, "tag list should succeed")
        rows = json.loads(list_result.stdout)
        assert rows == [{"project": "gap-project", "tags": ["work-stuff", "client_a"]}]

        remove_result = run_cli_subprocess(
            ["tag", "remove", "--project", "gap-project", "work-stuff"],
            env=env,
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(remove_result, "tag remove should succeed")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        assert config["project_tags"]["gap-project"] == ["client_a"]

    def test_project_list_json_includes_tags(
        self, current_workspace_setup: dict[str, Any], tmp_path: Path
    ) -> None:
        config_dir = tmp_path / ".agent-history"
        env = ensure_config_env(current_workspace_setup["env"], config_dir)
        config_path = config_dir / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "projects": {
                        "gap-project": {"local": [current_workspace_setup["workspace_path"]]}
                    },
                    "project_tags": {"gap-project": ["work", "client"]},
                    "homes": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = run_cli_subprocess(
            ["project", "list", "--format", "json"],
            env=env,
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(result, "project list should include tags")
        rows = json.loads(result.stdout)
        assert rows[0]["tags"] == ["work", "client"]

        show_result = run_cli_subprocess(
            ["project", "show", "gap-project", "--format", "json"],
            env=env,
            cwd=current_workspace_setup["workspace_dir"],
        )

        assert_cli_success(show_result, "project show should include tags")
        details = json.loads(show_result.stdout)
        assert details["tags"] == ["work", "client"]

    def test_project_export_writes_files(
        self, project_config_setup: dict[str, Any], tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "project-export"
        result = run_cli_subprocess(
            ["project", "export", "myproject", str(output_dir)],
            env=project_config_setup["env"],
        )

        assert_cli_success(result, "project export should succeed")
        assert list(output_dir.rglob("*.md")), "Expected markdown exports for project export"
