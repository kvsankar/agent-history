"""Metrics DB workspace resolution behavior tests."""

import json
from pathlib import Path

from tests.helpers.session_builders import CodexSessionBuilder, GeminiSessionBuilder


def test_codex_metrics_workspace_uses_cwd(tmp_path: Path):
    """Codex metrics should store workspace from session_meta.cwd."""
    from agent_history.storage.metrics import init_metrics_db, sync_sessions_to_db

    codex_dir = tmp_path / ".codex" / "sessions"
    builder = CodexSessionBuilder(session_id="codex-metrics-001", cwd="/home/testuser/codex")
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
    builder = GeminiSessionBuilder(session_id="gemini-metrics-001", project_hash=project_hash)
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


def test_metrics_sync_uses_registered_backend_capabilities(tmp_path: Path):
    """Stats sync should not need storage-layer edits for a registered backend."""
    from agent_history.backends.registry import AgentBackend, register_backend, unregister_backend
    from agent_history.storage.metrics import init_metrics_db, sync_sessions_to_db

    sessions_dir = tmp_path / "fake-sessions"
    sessions_dir.mkdir()
    session_file = sessions_dir / "fake-session.jsonl"
    session_file.write_text('{"role":"user","content":"hello"}\n', encoding="utf-8")

    backend = AgentBackend(
        id="fake-stats",
        label="Fake Stats Agent",
        get_session_dir=lambda resolver, context: sessions_dir,
        scan_sessions=lambda root: [
            {
                "agent": "fake-stats",
                "workspace": "/tmp/fake-stats-workspace",
                "workspace_readable": "/tmp/fake-stats-workspace",
                "file": root / "fake-session.jsonl",
                "filename": "fake-session.jsonl",
            }
        ],
        list_workspaces=lambda root, home: ["/tmp/fake-stats-workspace"],
        read_messages=lambda path: [{"role": "user", "content": "hello"}],
        count_messages=lambda path: 1,
        render_markdown=lambda path, minimal, messages, level: "# Fake Stats\n",
        message_to_unified=lambda msg: {
            "timestamp": msg.get("timestamp", ""),
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
        },
        extract_stats=lambda path: (
            {
                "session_id": "fake-stats-session",
                "message_count": 1,
                "user_messages": 1,
                "assistant_messages": 0,
                "input_tokens": 7,
                "output_tokens": 0,
                "cache_creation_tokens": 0,
                "cache_read_tokens": 0,
                "first_timestamp": "2026-01-01T00:00:00Z",
                "last_timestamp": "2026-01-01T00:00:00Z",
                "cwd": "/tmp/fake-stats-workspace-from-meta",
            },
            [
                {
                    "uuid": "fake-message",
                    "session_id": "fake-stats-session",
                    "type": "user",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "input_tokens": 7,
                }
            ],
            [],
        ),
        resolve_stats_workspace=lambda path, session_info, workspace: session_info["cwd"],
    )

    register_backend(backend)
    conn = init_metrics_db(db_path=tmp_path / "metrics.db")
    try:
        stats = sync_sessions_to_db(conn, sessions_dir, agent="fake-stats", force=True)
        row = conn.execute(
            """
            SELECT workspace, agent, message_count, input_tokens
            FROM sessions
            WHERE file_path = ?
            """,
            (str(session_file),),
        ).fetchone()
    finally:
        conn.close()
        unregister_backend("fake-stats")

    assert stats == {"synced": 1, "skipped": 0, "errors": 0}
    assert row is not None
    assert row["workspace"] == "/tmp/fake-stats-workspace-from-meta"
    assert row["agent"] == "fake-stats"
    assert row["message_count"] == 1
    assert row["input_tokens"] == 7
