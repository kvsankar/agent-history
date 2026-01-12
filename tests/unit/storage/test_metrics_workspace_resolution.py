"""Parity tests for metrics DB workspace resolution."""

import json
from pathlib import Path

from tests.helpers.session_builders import CodexSessionBuilder, GeminiSessionBuilder


def test_codex_metrics_workspace_uses_cwd(tmp_path: Path):
    """Codex metrics should store workspace from session_meta.cwd."""
    from agent_history.storage.metrics import init_metrics_db, sync_sessions_to_db

    codex_dir = tmp_path / ".codex" / "sessions"
    builder = CodexSessionBuilder(session_id="codex-parity-001", cwd="/home/testuser/codex")
    builder.add_user_message("hi")
    builder.add_assistant_message("ok")
    session_file = builder.write_to(codex_dir)

    conn = init_metrics_db(db_path=tmp_path / "metrics.db")
    try:
        sync_sessions_to_db(conn, codex_dir, agent="codex", force=True)
        row = conn.execute(
            "SELECT workspace FROM sessions WHERE file_path = ?",
            (str(session_file),),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "Expected codex session to be synced"
    assert row[0] == builder.cwd, "Expected workspace to match session_meta.cwd"


def test_gemini_metrics_workspace_uses_hash_index(tmp_path: Path, monkeypatch):
    """Gemini metrics should store resolved workspace from hash index."""
    from agent_history.storage.metrics import init_metrics_db, sync_sessions_to_db

    gemini_dir = tmp_path / ".gemini" / "tmp"
    project_hash = "b" * 64
    builder = GeminiSessionBuilder(session_id="gemini-parity-001", project_hash=project_hash)
    builder.add_user_message("hi")
    builder.add_gemini_message("ok")
    session_file = builder.write_to(gemini_dir)

    # Seed hash index mapping
    config_dir = tmp_path / ".agent-history"
    config_dir.mkdir(parents=True, exist_ok=True)
    index_file = config_dir / "gemini_index.json"
    index_file.write_text(
        json.dumps({"hashes": {project_hash: "/home/testuser/gemini"}}, indent=2),
        encoding="utf-8",
    )

    # Point lookup to our temp config dir
    monkeypatch.setenv("AGENT_HISTORY_CONFIG_DIR", str(config_dir))

    conn = init_metrics_db(db_path=tmp_path / "metrics.db")
    try:
        sync_sessions_to_db(conn, gemini_dir, agent="gemini", force=True)
        row = conn.execute(
            "SELECT workspace FROM sessions WHERE file_path = ?",
            (str(session_file),),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "Expected gemini session to be synced"
    assert row[0] == "/home/testuser/gemini", "Expected workspace to use hash index mapping"
