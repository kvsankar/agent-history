"""Utility command handlers for install/reset/fetch."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, ClassVar

from agent_history.adapters.remote import SSHRemoteClient
from agent_history.core.workspaces import build_scope_metadata
from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope
from agent_history.storage.config import get_config_dir
from agent_history.storage.metrics import get_metrics_db_path


class InstallHandler(VerbHandler):
    """Handler for 'install' utility command."""

    SKILL_NAME = "cagelens"
    AGENT_SKILL_DIRS: ClassVar[dict[str, Path]] = {
        "claude": Path("~/.claude/skills/cagelens"),
        "codex": Path("~/.codex/skills/cagelens"),
        "gemini": Path("~/.gemini/skills/cagelens"),
        "pi": Path("~/.pi/agent/skills/cagelens"),
    }

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        warnings = []
        dry_run = verb_args.get("dry_run", False)
        actions = self._build_install_plan(verb_args, warnings)

        if not dry_run:
            actions = [self._execute_install_action(action) for action in actions]

        return CommandResult(
            success=True,
            data={
                "action": "install",
                "status": "planned" if dry_run else "ok",
                "bin_dir": verb_args.get("bin_dir"),
                "skill_dir": verb_args.get("skill_dir"),
                "skip_cli": verb_args.get("skip_cli", False),
                "skip_skill": verb_args.get("skip_skill", False),
                "skip_settings": verb_args.get("skip_settings", False),
                "dry_run": dry_run,
                "installed": actions,
            },
            data_type="install_result",
            metadata={
                "message": "Install plan" if dry_run else "Install completed",
                "workspace_display_map": {},
            },
            warnings=warnings,
        )

    def _build_install_plan(
        self, verb_args: dict[str, Any], warnings: list[str]
    ) -> list[dict[str, str]]:
        actions = []
        if not verb_args.get("skip_cli", False):
            actions.append(self._plan_cli(verb_args.get("bin_dir")))
        if not verb_args.get("skip_skill", False):
            actions.extend(self._plan_skills(verb_args, warnings))
        actions.append(self._plan_settings(verb_args))
        return actions

    def _plan_cli(self, bin_dir: str | None) -> dict[str, str]:
        target_dir = Path(bin_dir or "~/.local/bin").expanduser()
        target = target_dir / "cagelens"
        return {
            "component": "cli",
            "agent": "",
            "status": "planned",
            "path": str(target),
            "message": "install cagelens CLI wrapper",
        }

    def _plan_skills(self, verb_args: dict[str, Any], warnings: list[str]) -> list[dict[str, str]]:
        skill_dir = verb_args.get("skill_dir")
        if skill_dir:
            return [self._plan_skill_package("custom", Path(skill_dir).expanduser())]

        agent = verb_args.get("agent")
        agents = [agent] if agent and agent != "auto" else list(self.AGENT_SKILL_DIRS)
        actions = []
        for target_agent in agents:
            target_template = self.AGENT_SKILL_DIRS.get(target_agent)
            if target_template is None:
                warnings.append(f"Install skipped for unsupported agent: {target_agent}")
                continue
            target_dir = self._resolve_agent_skill_dir(target_agent, target_template)
            actions.append(self._plan_skill_package(target_agent, target_dir))
        return actions

    def _plan_skill_package(self, agent: str, target_dir: Path) -> dict[str, str]:
        return {
            "component": "skill",
            "agent": agent,
            "status": "planned",
            "path": str(target_dir),
            "message": f"install {self.SKILL_NAME} skill package",
        }

    def _plan_settings(self, verb_args: dict[str, Any]) -> dict[str, str]:
        if verb_args.get("skip_settings", False):
            return {
                "component": "settings",
                "agent": "",
                "status": "skipped",
                "path": "",
                "message": "legacy agent settings step skipped",
            }
        return {
            "component": "settings",
            "agent": "",
            "status": "noop",
            "path": "",
            "message": "no agent settings update is required",
        }

    def _execute_install_action(self, action: dict[str, str]) -> dict[str, str]:
        if action["component"] == "cli" and action["status"] == "planned":
            return self._install_cli(Path(action["path"]))
        if action["component"] == "skill" and action["status"] == "planned":
            return self._install_skill_package(action["agent"], Path(action["path"]))
        return action

    def _install_cli(self, target: Path) -> dict[str, str]:
        target_dir = target.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        source = self._find_cli_source()
        shutil.copy2(source, target)
        target.chmod(target.stat().st_mode | 0o755)
        return {
            "component": "cli",
            "agent": "",
            "status": "installed",
            "path": str(target),
            "message": "installed cagelens CLI wrapper",
        }

    def _install_skill_package(self, agent: str, target_dir: Path) -> dict[str, str]:
        target_dir.mkdir(parents=True, exist_ok=True)
        skill_md = self._find_skill_source()
        cli_source = self._find_cli_source()

        shutil.copy2(skill_md, target_dir / "SKILL.md")
        cli_target = target_dir / "cagelens"
        shutil.copy2(cli_source, cli_target)
        cli_target.chmod(cli_target.stat().st_mode | 0o755)

        return {
            "component": "skill",
            "agent": agent,
            "status": "installed",
            "path": str(target_dir),
            "message": f"installed {self.SKILL_NAME} skill package",
        }

    def _resolve_agent_skill_dir(self, agent: str, target_template: Path) -> Path:
        if agent == "codex":
            codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
            return codex_home / "skills" / self.SKILL_NAME
        return target_template.expanduser()

    def _find_skill_source(self) -> Path:
        for candidate in self._source_root_candidates():
            skill_md = candidate / "SKILL.md"
            if skill_md.is_file():
                return skill_md
        raise FileNotFoundError("Could not find SKILL.md to install")

    def _find_cli_source(self) -> Path:
        argv0 = Path(sys.argv[0]).expanduser()
        candidates = []
        if argv0.is_file():
            candidates.append(argv0)
        candidates.extend(candidate / "cagelens" for candidate in self._source_root_candidates())
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise FileNotFoundError("Could not find cagelens CLI wrapper to install")

    def _source_root_candidates(self) -> list[Path]:
        return [
            Path.cwd(),
            Path(__file__).resolve().parents[2],
            Path(sys.argv[0]).expanduser().resolve().parent,
        ]


class ResetHandler(VerbHandler):
    """Handler for 'reset' utility command."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        force = verb_args.get("yes", False)
        if not force and sys.stdin.isatty():
            try:
                response = input("Reset stored data? [y/N] ").strip().lower()
            except EOFError:
                response = ""
            if response not in ("y", "yes"):
                return CommandResult(
                    success=False,
                    data={"status": "aborted"},
                    data_type="reset_result",
                    errors=["Reset aborted"],
                )
        elif not force:
            return CommandResult(
                success=False,
                data={"status": "aborted"},
                data_type="reset_result",
                errors=["Reset requires confirmation (-y)"],
            )

        reset_db = verb_args.get("reset_db", False)
        reset_config = verb_args.get("reset_config", False)
        reset_cache = verb_args.get("reset_cache", False)

        removed = []
        if reset_db:
            db_path = get_metrics_db_path()
            if db_path.exists():
                db_path.unlink()
                removed.append(str(db_path))

        if reset_config:
            config_dir = get_config_dir()
            config_file = config_dir / "config.json"
            if config_file.exists():
                config_file.unlink()
                removed.append(str(config_file))
            for extra in ("gemini_index.json", "gemini_hash_index.json", "codex_index.json"):
                extra_path = config_dir / extra
                if extra_path.exists():
                    extra_path.unlink()
                    removed.append(str(extra_path))

        if reset_cache:
            for cache_name in ("remote-cache", "web-cache"):
                cache_dir = get_config_dir() / cache_name
                if cache_dir.exists():
                    shutil.rmtree(cache_dir)
                    removed.append(str(cache_dir))

        return CommandResult(
            success=True,
            data={"status": "ok", "removed": removed},
            data_type="reset_result",
            metadata={"workspace_display_map": {}},
        )


class FetchHandler(VerbHandler):
    """Handler for 'fetch' utility command."""

    def execute(
        self, scope: ConcreteScope, verb_args: dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        client = SSHRemoteClient()
        fetched = 0
        skipped = 0
        errors = 0

        for record in scope:
            if not record.home.startswith("remote:"):
                continue
            remote_host = record.home[7:]
            for session in record.sessions:
                file_value = session.get("file")
                if file_value and Path(str(file_value)).exists():
                    skipped += 1
                    continue
                try:
                    local = client.ensure_local_copy(remote_host, record.workspace, session)
                    if local:
                        fetched += 1
                    else:
                        errors += 1
                except Exception:
                    errors += 1

        metadata = build_scope_metadata(scope)
        return CommandResult(
            success=errors == 0,
            data={"fetched": fetched, "skipped": skipped, "errors": errors},
            data_type="fetch_result",
            metadata=metadata,
        )
