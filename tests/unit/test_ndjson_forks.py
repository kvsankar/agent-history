"""NDJSON export includes fork metadata for Claude sessions."""

from agent_history.backends.claude import read_jsonl_messages
from agent_history.core.ndjson import build_ndjson_records
from tests.helpers.paths import fixtures_dir


def test_ndjson_session_record_includes_forks() -> None:
    fixture = fixtures_dir() / "forks" / "claude_forked_session.jsonl"
    messages = read_jsonl_messages(fixture)

    records = build_ndjson_records("claude", messages, {"filename": "forked.jsonl"})
    session_record = next(record for record in records if record.get("type") == "session")

    forks = session_record.get("forks")
    assert forks, "Expected fork metadata in session record"
    assert "fa1-fork" in forks.get("fork_points", [])
