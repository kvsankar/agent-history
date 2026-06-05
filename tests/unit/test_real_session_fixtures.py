"""Tests for sanitized sessions captured from real agent CLIs."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "real_sessions"


def test_real_claude_fixture_parses_and_preserves_usage() -> None:
    from agent_history.backends.claude import claude_message_to_unified, read_jsonl_messages

    messages = read_jsonl_messages(FIXTURES / "claude" / "session-01.jsonl")

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assistant = messages[1]
    assert assistant["content"] == "[REDACTED_ASSISTANT_TEXT]"
    assert assistant["model"] == "claude-opus-4-7"

    unified = claude_message_to_unified(assistant)

    assert unified["tokens"] == {"input": 6, "output": 16, "cached": 3057}


def test_real_codex_fixture_parses_session_meta_and_messages() -> None:
    from agent_history.backends.codex import codex_message_to_unified, codex_read_jsonl_messages

    messages, meta = codex_read_jsonl_messages(FIXTURES / "codex" / "session-01.jsonl")

    assert meta is not None
    assert meta["cwd"] == "/tmp/agent-history-real-agent/codex/workspace"
    assert meta["cli_version"] == "0.135.0"
    assert meta["base_instructions"]["text"] == "[REDACTED_BASE_INSTRUCTIONS]"
    assert [message["role"] for message in messages] == [
        "developer",
        "user",
        "user",
        "assistant",
    ]
    assert messages[-1]["content"] == "[REDACTED_ASSISTANT_TEXT]"

    unified = codex_message_to_unified(messages[-1])

    assert unified["role"] == "assistant"
    assert unified["content"] == "[REDACTED_ASSISTANT_TEXT]"


def test_real_gemini_json_fixture_parses_thoughts_tokens_and_model() -> None:
    from agent_history.backends.gemini import _gemini_message_to_unified, gemini_read_json_messages

    messages, meta = gemini_read_json_messages(FIXTURES / "gemini" / "session-01.json")

    assert meta is not None
    assert meta["sessionId"] == "dcbe78d3-ea75-4786-929e-d6cff0fc00ed"
    assert meta["projectHash"] == "d30f91067027d10192e4aed3e7b03fecf08089dd3370f047f14f38b1845c8042"
    assert [message["role"] for message in messages] == ["user", "assistant"]

    assistant = messages[1]
    assert assistant["content"] == "[REDACTED_ASSISTANT_TEXT]"
    assert assistant["thoughts"][0]["description"] == "[REDACTED_THOUGHT]"
    assert assistant["tokens"]["thoughts"] == 28
    assert assistant["model"] == "gemini-2.5-flash"

    unified = _gemini_message_to_unified(assistant)

    assert unified["tokens"] == {"input": 4383, "output": 8}


def test_real_pi_fixture_parses_tree_context_and_openai_codex_message() -> None:
    from agent_history.backends.pi import pi_message_to_unified, pi_read_jsonl_messages

    messages, meta = pi_read_jsonl_messages(FIXTURES / "pi" / "session-01.jsonl")

    assert meta is not None
    assert meta["version"] == 3
    assert meta["cwd"] == "/tmp/agent-history-real-agent/pi/workspace"
    assert [message["raw_role"] for message in messages] == [
        "session_info",
        "model_change",
        "thinking_level_change",
        "user",
        "assistant",
    ]

    assistant = messages[-1]
    assert assistant["content"] == "[REDACTED_ASSISTANT_TEXT]"
    assert assistant["model"] == "gpt-5.5"
    assert assistant["tokens"]["input"] == 433
    assert assistant["raw_payload"]["provider"] == "openai-codex"

    unified = pi_message_to_unified(assistant)

    assert unified["role"] == "assistant"
    assert unified["tokens"] == {"input": 433, "output": 9, "cache_write": 0, "cache_read": 0}
