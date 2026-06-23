"""Behavior tests for CLI flags that should alter behavior."""

import json
from pathlib import Path

from tests.helpers.cli import run_cli_subprocess
from tests.helpers.session_builders import ClaudeSessionBuilder


def test_session_list_counts_flag_populates_message_count(
    isolated_home, setup_golden_fixtures
):
    """--counts should populate message_count values in session list output."""
    result = run_cli_subprocess(
        ["session", "list", "--counts", "--aw", "--format", "json"],
        env=isolated_home["env"],
        cwd=isolated_home["path"],
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip(), "Expected JSON session list output"

    sessions = json.loads(result.stdout)
    assert any(s.get("message_count", 0) > 0 for s in sessions), "Expected counts > 0"


def test_export_jobs_uses_thread_pool(monkeypatch, tmp_path: Path):
    """--jobs should enable parallel export execution."""
    from agent_history.handlers.export import SessionExportHandler
    from agent_history.scope.context import OutputArgs
    from agent_history.scope.types import ConcreteRecord
    from agent_history.utils.platform import AGENT_CLAUDE

    builder = ClaudeSessionBuilder(workspace="-home-testuser-project")
    builder.add_user_message("hello")
    session_file = builder.write_to(tmp_path)

    scope = [
        ConcreteRecord(
            home="local",
            workspace="/home/testuser/project",
            sessions=[
                {
                    "file": session_file,
                    "filename": session_file.name,
                    "agent": AGENT_CLAUDE,
                    "workspace": "-home-testuser-project",
                }
            ],
        )
    ]

    used_pool = {"called": False}

    class DummyPool:
        def __init__(self, *args, **kwargs):
            used_pool["called"] = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            class FakeFuture:
                def __init__(self, result):
                    self._result = result
                def result(self):
                    return self._result
            return FakeFuture(fn(*args, **kwargs))

    monkeypatch.setattr(
        "agent_history.handlers.export.ThreadPoolExecutor",
        DummyPool,
        raising=False,
    )

    handler = SessionExportHandler()
    output_dir = tmp_path / "exports"
    handler.execute(
        scope,
        {"output_dir": output_dir, "jobs": 2, "force": True},
        OutputArgs(),
    )

    assert used_pool["called"], "Expected export to use ThreadPoolExecutor when jobs > 1"
