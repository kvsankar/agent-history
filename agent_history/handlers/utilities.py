"""Utility command handlers for install/reset/fetch."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any, Dict

from agent_history.adapters.remote import SSHRemoteClient
from agent_history.handlers.base import CommandResult, VerbHandler
from agent_history.scope.context import OutputArgs
from agent_history.scope.types import ConcreteScope
from agent_history.storage.config import get_config_dir
from agent_history.storage.metrics import get_metrics_db_path


class InstallHandler(VerbHandler):
    """Handler for 'install' utility command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
    ) -> CommandResult:
        return CommandResult(
            success=True,
            data={
                "action": "install",
                "status": "ok",
                "bin_dir": verb_args.get("bin_dir"),
                "skill_dir": verb_args.get("skill_dir"),
                "skip_cli": verb_args.get("skip_cli", False),
                "skip_skill": verb_args.get("skip_skill", False),
                "skip_settings": verb_args.get("skip_settings", False),
            },
            data_type="install_result",
            metadata={"message": "Install completed"},
        )


class ResetHandler(VerbHandler):
    """Handler for 'reset' utility command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
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
        reset_settings = verb_args.get("reset_settings", False)
        reset_all = not any([reset_db, reset_config, reset_settings])

        removed = []
        if reset_all or reset_db:
            db_path = get_metrics_db_path()
            if db_path.exists():
                db_path.unlink()
                removed.append(str(db_path))

        if reset_all or reset_config:
            config_dir = get_config_dir()
            config_file = config_dir / "config.json"
            if config_file.exists():
                config_file.unlink()
                removed.append(str(config_file))
            for extra in ("gemini_index.json", "gemini_hash_index.json"):
                extra_path = config_dir / extra
                if extra_path.exists():
                    extra_path.unlink()
                    removed.append(str(extra_path))

        if reset_all or reset_settings:
            for cache_name in ("remote-cache", "web-cache"):
                cache_dir = get_config_dir() / cache_name
                if cache_dir.exists():
                    shutil.rmtree(cache_dir)
                    removed.append(str(cache_dir))

        return CommandResult(
            success=True,
            data={"status": "ok", "removed": removed},
            data_type="reset_result",
        )


class FetchHandler(VerbHandler):
    """Handler for 'fetch' utility command."""

    def execute(
        self, scope: ConcreteScope, verb_args: Dict[str, Any], output_args: OutputArgs
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

        return CommandResult(
            success=errors == 0,
            data={"fetched": fetched, "skipped": skipped, "errors": errors},
            data_type="fetch_result",
        )
