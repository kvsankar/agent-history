"""Stats test fixtures with known expected values.

Spec Reference: docs/testing/testing-strategy.md#3c-stats-commands

These fixtures create sessions with precisely controlled token counts,
tool usage, and message counts for validating stats calculations.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List

import pytest

# ---------------------------------------------------------------------------
# Expected Values - Pre-computed totals for validation
# ---------------------------------------------------------------------------

# Claude session with known values
CLAUDE_STATS_EXPECTED = {
    "session_id": "stats-claude-001",
    "agent": "claude",
    "workspace": "-home-testuser-stats-project",
    "messages": 6,  # 3 user (including 2 tool_results) + 3 assistant
    "user_messages": 3,
    "assistant_messages": 3,
    "input_tokens": 500,
    "output_tokens": 200,
    "cache_creation_tokens": 30,
    "cache_read_tokens": 130,
    "tool_calls": {"Read": 1, "Edit": 1},
    "model": "claude-sonnet-4-20250514",
}

# Codex session with known values
# The stats implementation sums output_tokens + reasoning_output_tokens as total output
# This matches user expectation that "output" = all generated tokens
CODEX_STATS_EXPECTED = {
    "session_id": "stats-codex-001",
    "agent": "codex",
    "workspace": "/home/testuser/codex-project",
    "messages": 4,  # 2 user + 2 assistant
    "user_messages": 2,
    "assistant_messages": 2,
    "input_tokens": 300,
    "output_tokens": 150,  # 135 base + 15 reasoning (total output)
    "base_output_tokens": 135,  # Excluding reasoning
    "cached_input_tokens": 120,
    "reasoning_output_tokens": 15,
    "tool_calls": {"shell": 1},
    "model": "gpt-4.5-turbo",
}

# Gemini session with known values
GEMINI_STATS_EXPECTED = {
    "session_id": "stats-gemini-001",
    "agent": "gemini",
    "workspace": "stats123def456789012345678901234567890123456789012345678901234",
    "messages": 4,  # 2 user + 2 assistant (gemini)
    "user_messages": 2,
    "assistant_messages": 2,
    "input_tokens": 400,
    "output_tokens": 180,
    "cached_tokens": 50,
    "thought_tokens": 35,
    "tool_tokens": 10,
    "tool_calls": {"read_file": 1},
    "model": "gemini-2.5-pro",
}

# Combined totals for all 3 sessions
# Claude: 500 in, 200 out; Codex: 300 in, 150 out; Gemini: 400 in, 180 out
ALL_STATS_EXPECTED = {
    "sessions": 3,
    "messages": 14,
    "user_messages": 7,
    "assistant_messages": 7,
    "input_tokens": 1200,  # 500 + 300 + 400
    "output_tokens": 530,  # 200 + 150 + 180
    "tool_calls_total": 4,
    "tools": {"Read": 1, "Edit": 1, "shell": 1, "read_file": 1},
}


# ---------------------------------------------------------------------------
# Multi-session fixtures for grouping tests
# ---------------------------------------------------------------------------

# Multiple Claude sessions with different models
# Note: These are PER-MESSAGE token values used by the fixture builder
# Totals are computed: opus=1 msg, sonnet=2 msgs (fixture adds pair when messages==4)
CLAUDE_MULTI_MODEL_EXPECTED = {
    "sessions": [
        {
            "session_id": "multi-claude-opus",
            "model": "claude-opus-4-20250514",
            "messages": 2,
            "user_messages": 1,
            "assistant_messages": 1,
            "input_tokens": 200,  # Per message
            "output_tokens": 100,  # Per message
            "total_input": 200,  # 1 assistant * 200
            "total_output": 100,  # 1 assistant * 100
        },
        {
            "session_id": "multi-claude-sonnet",
            "model": "claude-sonnet-4-20250514",
            "messages": 4,
            "user_messages": 2,
            "assistant_messages": 2,
            "input_tokens": 400,  # Per message
            "output_tokens": 150,  # First message (second is -25)
            "total_input": 800,  # 2 assistants * 400
            "total_output": 275,  # 150 + 125
        },
    ],
    "by_model": {
        "claude-opus-4-20250514": {"messages": 2, "input_tokens": 200, "output_tokens": 100},
        "claude-sonnet-4-20250514": {"messages": 4, "input_tokens": 800, "output_tokens": 275},
    },
    "totals": {
        "sessions": 2,
        "messages": 6,
        "input_tokens": 1000,  # 200 + 800
        "output_tokens": 375,  # 100 + 275
    },
}

# Sessions across multiple days
MULTI_DAY_EXPECTED = {
    "sessions": [
        {"session_id": "day1-session", "date": "2025-01-03", "messages": 4},
        {"session_id": "day2-session", "date": "2025-01-04", "messages": 6},
        {"session_id": "day3-session", "date": "2025-01-05", "messages": 2},
    ],
    "by_day": {
        "2025-01-03": {"sessions": 1, "messages": 4},
        "2025-01-04": {"sessions": 1, "messages": 6},
        "2025-01-05": {"sessions": 1, "messages": 2},
    },
    "totals": {"sessions": 3, "messages": 12},
}

# Sessions with multiple tool types
MULTI_TOOL_EXPECTED = {
    "tool_calls": {
        "Read": 3,
        "Edit": 2,
        "Bash": 4,
        "Grep": 1,
        "Write": 1,
    },
    "tool_calls_total": 11,
}


# ---------------------------------------------------------------------------
# Session Builders for Stats Tests
# ---------------------------------------------------------------------------


def build_claude_stats_session(
    session_id: str,
    workspace: str,
    messages: List[Dict[str, Any]],
    model: str = "claude-sonnet-4-20250514",
) -> List[Dict[str, Any]]:
    """Build Claude session records with precise control over stats."""
    records = []
    parent_uuid = None
    base_time = datetime(2025, 1, 3, 10, 0, 0)

    for i, msg_spec in enumerate(messages):
        msg_uuid = f"u{i+1}-{session_id}"
        timestamp = (base_time + timedelta(seconds=i * 5)).isoformat() + "Z"

        if msg_spec["role"] == "user":
            record = {
                "type": "user",
                "uuid": msg_uuid,
                "parentUuid": parent_uuid,
                "sessionId": session_id,
                "timestamp": timestamp,
                "cwd": f"/home/testuser/{workspace.lstrip('-').replace('-', '/')}",
                "message": {
                    "role": "user",
                    "content": msg_spec.get("content", "Test message"),
                },
            }
            # Handle tool_result messages
            if "tool_result" in msg_spec:
                record["message"]["content"] = [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg_spec["tool_result"]["tool_use_id"],
                        "content": msg_spec["tool_result"].get("content", "Result"),
                    }
                ]
            records.append(record)

        elif msg_spec["role"] == "assistant":
            content_blocks = []
            if msg_spec.get("thinking"):
                content_blocks.append({"type": "thinking", "thinking": msg_spec["thinking"]})
            content_blocks.append({"type": "text", "text": msg_spec.get("content", "Response")})
            if msg_spec.get("tool_use"):
                for tool in msg_spec["tool_use"]:
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool["id"],
                            "name": tool["name"],
                            "input": tool.get("input", {}),
                        }
                    )

            record = {
                "type": "assistant",
                "uuid": msg_uuid,
                "parentUuid": parent_uuid,
                "sessionId": session_id,
                "timestamp": timestamp,
                "requestId": f"req_{i+1:03d}",
                "message": {
                    "id": f"msg_{i+1:03d}",
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": content_blocks,
                    "stop_reason": "tool_use" if msg_spec.get("tool_use") else "end_turn",
                    "usage": {
                        "input_tokens": msg_spec.get("input_tokens", 0),
                        "output_tokens": msg_spec.get("output_tokens", 0),
                        "cache_creation_input_tokens": msg_spec.get("cache_creation", 0),
                        "cache_read_input_tokens": msg_spec.get("cache_read", 0),
                    },
                },
            }
            records.append(record)

        parent_uuid = msg_uuid

    return records


def build_codex_stats_session(
    session_id: str,
    cwd: str,
    messages: List[Dict[str, Any]],
    model: str = "gpt-4.5-turbo",
    token_usage: Dict[str, int] = None,
) -> List[Dict[str, Any]]:
    """Build Codex session records with precise control over stats."""
    records = []
    base_time = datetime(2025, 1, 4, 9, 0, 0)

    # Session metadata
    records.append(
        {
            "timestamp": base_time.isoformat() + "Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "timestamp": base_time.isoformat() + "Z",
                "cwd": cwd,
                "originator": "codex_cli_rs",
                "cli_version": "0.77.0",
                "source": "cli",
                "model_provider": "openai",
                "git": {"commit_hash": "abc123", "branch": "main"},
            },
        }
    )

    # Turn context
    records.append(
        {
            "timestamp": (base_time + timedelta(seconds=1)).isoformat() + "Z",
            "type": "turn_context",
            "payload": {
                "cwd": cwd,
                "approval_policy": "on-request",
                "model": model,
                "effort": "high",
            },
        }
    )

    # Messages
    for i, msg_spec in enumerate(messages):
        timestamp = (base_time + timedelta(seconds=i + 2)).isoformat() + "Z"

        if msg_spec["role"] == "user":
            records.append(
                {
                    "timestamp": timestamp,
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": msg_spec.get("content", "Test")}
                        ],
                    },
                }
            )

        elif msg_spec["role"] == "assistant":
            # Optional reasoning
            if msg_spec.get("reasoning"):
                records.append(
                    {
                        "timestamp": timestamp,
                        "type": "response_item",
                        "payload": {
                            "type": "reasoning",
                            "summary": [{"type": "summary_text", "text": msg_spec["reasoning"]}],
                            "content": None,
                            "encrypted_content": None,
                        },
                    }
                )

            records.append(
                {
                    "timestamp": timestamp,
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": msg_spec.get("content", "Response")}
                        ],
                    },
                }
            )

            # Function calls
            if msg_spec.get("function_call"):
                call = msg_spec["function_call"]
                records.append(
                    {
                        "timestamp": timestamp,
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "name": call["name"],
                            "arguments": json.dumps(call.get("arguments", {})),
                            "call_id": call["call_id"],
                        },
                    }
                )

            # Function outputs
            if msg_spec.get("function_output"):
                output = msg_spec["function_output"]
                records.append(
                    {
                        "timestamp": timestamp,
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "call_id": output["call_id"],
                            "output": output["output"],
                        },
                    }
                )

    # Token count at end
    if token_usage:
        records.append(
            {
                "timestamp": (base_time + timedelta(seconds=len(messages) + 3)).isoformat() + "Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": token_usage.get("input", 0),
                            "cached_input_tokens": token_usage.get("cached", 0),
                            "output_tokens": token_usage.get("output", 0),
                            "reasoning_output_tokens": token_usage.get("reasoning", 0),
                            "total_tokens": token_usage.get("input", 0)
                            + token_usage.get("output", 0),
                        },
                        "last_token_usage": {},
                        "model_context_window": 128000,
                    },
                },
            }
        )

    return records


def build_gemini_stats_session(
    session_id: str,
    project_hash: str,
    messages: List[Dict[str, Any]],
    model: str = "gemini-2.5-pro",
) -> Dict[str, Any]:
    """Build Gemini session data with precise control over stats."""
    base_time = datetime(2025, 1, 5, 14, 0, 0)
    msg_list = []

    for i, msg_spec in enumerate(messages):
        timestamp = (base_time + timedelta(seconds=i * 10)).isoformat() + "Z"
        msg_id = f"msg-g{i+1}"

        if msg_spec["role"] == "user":
            msg_list.append(
                {
                    "id": msg_id,
                    "timestamp": timestamp,
                    "type": "user",
                    "content": msg_spec.get("content", "Test message"),
                }
            )

        elif msg_spec["role"] == "assistant":
            msg = {
                "id": msg_id,
                "timestamp": timestamp,
                "type": "gemini",
                "content": msg_spec.get("content", "Response"),
                "model": model,
                "tokens": {
                    "input": msg_spec.get("input_tokens", 0),
                    "output": msg_spec.get("output_tokens", 0),
                    "cached": msg_spec.get("cached", 0),
                    "thoughts": msg_spec.get("thought_tokens", 0),
                    "tool": msg_spec.get("tool_tokens", 0),
                    "total": msg_spec.get("input_tokens", 0) + msg_spec.get("output_tokens", 0),
                },
            }

            if msg_spec.get("thoughts"):
                msg["thoughts"] = msg_spec["thoughts"]

            if msg_spec.get("tool_calls"):
                msg["toolCalls"] = msg_spec["tool_calls"]

            msg_list.append(msg)

    return {
        "sessionId": session_id,
        "projectHash": project_hash,
        "startTime": msg_list[0]["timestamp"] if msg_list else None,
        "lastUpdated": msg_list[-1]["timestamp"] if msg_list else None,
        "messages": msg_list,
    }


# ---------------------------------------------------------------------------
# Pytest Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def claude_stats_expected() -> Dict[str, Any]:
    """Expected values for Claude stats session."""
    return CLAUDE_STATS_EXPECTED.copy()


@pytest.fixture
def codex_stats_expected() -> Dict[str, Any]:
    """Expected values for Codex stats session."""
    return CODEX_STATS_EXPECTED.copy()


@pytest.fixture
def gemini_stats_expected() -> Dict[str, Any]:
    """Expected values for Gemini stats session."""
    return GEMINI_STATS_EXPECTED.copy()


@pytest.fixture
def all_stats_expected() -> Dict[str, Any]:
    """Expected totals for all sessions combined."""
    return ALL_STATS_EXPECTED.copy()


@pytest.fixture
def multi_model_expected() -> Dict[str, Any]:
    """Expected values for multi-model grouping tests."""
    return CLAUDE_MULTI_MODEL_EXPECTED.copy()


@pytest.fixture
def multi_day_expected() -> Dict[str, Any]:
    """Expected values for multi-day grouping tests."""
    return MULTI_DAY_EXPECTED.copy()


@pytest.fixture
def multi_tool_expected() -> Dict[str, Any]:
    """Expected values for multi-tool grouping tests."""
    return MULTI_TOOL_EXPECTED.copy()


@pytest.fixture
def stats_test_home(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create isolated home for stats tests with controlled fixtures.

    Creates the standard agent directory structure and populates it
    with sessions having known stats values.
    """
    # Create agent directories
    claude_dir = tmp_path / ".claude" / "projects"
    codex_dir = tmp_path / ".codex" / "sessions"
    gemini_dir = tmp_path / ".gemini" / "tmp"
    history_dir = tmp_path / ".agent-history"

    claude_dir.mkdir(parents=True)
    codex_dir.mkdir(parents=True)
    gemini_dir.mkdir(parents=True)
    history_dir.mkdir(parents=True)

    # Build environment
    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(claude_dir)
    env["CODEX_SESSIONS_DIR"] = str(codex_dir)
    env["GEMINI_SESSIONS_DIR"] = str(gemini_dir)
    env["HOME"] = str(tmp_path)
    env["AGENT_HISTORY_HOME"] = str(tmp_path)

    yield {
        "path": tmp_path,
        "env": env,
        "claude_dir": claude_dir,
        "codex_dir": codex_dir,
        "gemini_dir": gemini_dir,
        "history_dir": history_dir,
    }


@pytest.fixture
def setup_claude_stats_fixture(stats_test_home: Dict[str, Any]) -> Path:
    """Create Claude session with known stats values."""
    claude_dir = stats_test_home["claude_dir"]
    exp = CLAUDE_STATS_EXPECTED

    # Build messages with precise token counts
    messages = [
        {"role": "user", "content": "Read the config file"},
        {
            "role": "assistant",
            "content": "I'll read the config file for you.",
            "input_tokens": 100,
            "output_tokens": 40,
            "cache_creation": 0,
            "cache_read": 0,
            "tool_use": [
                {"id": "toolu_001", "name": "Read", "input": {"file_path": "config.json"}}
            ],
        },
        {"role": "user", "tool_result": {"tool_use_id": "toolu_001", "content": '{"debug": true}'}},
        {
            "role": "assistant",
            "content": "Let me update the config.",
            "thinking": "User wants me to modify the config.",
            "input_tokens": 150,
            "output_tokens": 60,
            "cache_creation": 10,
            "cache_read": 50,
            "tool_use": [
                {"id": "toolu_002", "name": "Edit", "input": {"file_path": "config.json"}}
            ],
        },
        {"role": "user", "tool_result": {"tool_use_id": "toolu_002", "content": "File updated"}},
        {
            "role": "assistant",
            "content": "Done! I've updated the config.",
            "input_tokens": 250,
            "output_tokens": 100,
            "cache_creation": 20,
            "cache_read": 80,
        },
    ]

    records = build_claude_stats_session(
        session_id=exp["session_id"],
        workspace=exp["workspace"],
        messages=messages,
        model=exp["model"],
    )

    # Write session file
    ws_dir = claude_dir / exp["workspace"]
    ws_dir.mkdir(parents=True, exist_ok=True)
    session_file = ws_dir / f"{exp['session_id']}.jsonl"

    with open(session_file, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    return session_file


@pytest.fixture
def setup_codex_stats_fixture(stats_test_home: Dict[str, Any]) -> Path:
    """Create Codex session with known stats values."""
    codex_dir = stats_test_home["codex_dir"]
    exp = CODEX_STATS_EXPECTED

    messages = [
        {"role": "user", "content": "List the files"},
        {
            "role": "assistant",
            "content": "I'll list the files for you.",
            "reasoning": "Preparing to list directory",
            "function_call": {
                "name": "shell",
                "arguments": {"command": "ls -la"},
                "call_id": "call_001",
            },
            "function_output": {"call_id": "call_001", "output": "README.md\npackage.json"},
        },
        {"role": "user", "content": "Thanks!"},
        {"role": "assistant", "content": "You're welcome!"},
    ]

    records = build_codex_stats_session(
        session_id=exp["session_id"],
        cwd=exp["workspace"],
        messages=messages,
        model=exp["model"],
        token_usage={
            "input": exp["input_tokens"],
            "output": exp["base_output_tokens"],  # 135, implementation adds reasoning
            "cached": exp["cached_input_tokens"],
            "reasoning": exp["reasoning_output_tokens"],
        },
    )

    # Write session file
    date_dir = codex_dir / "2025" / "01" / "04"
    date_dir.mkdir(parents=True, exist_ok=True)
    session_file = date_dir / f"rollout-{exp['session_id']}.jsonl"

    with open(session_file, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    return session_file


@pytest.fixture
def setup_gemini_stats_fixture(stats_test_home: Dict[str, Any]) -> Path:
    """Create Gemini session with known stats values."""
    gemini_dir = stats_test_home["gemini_dir"]
    exp = GEMINI_STATS_EXPECTED

    messages = [
        {"role": "user", "content": "Read the package.json file"},
        {
            "role": "assistant",
            "content": "I'll read the package.json file for you.",
            "input_tokens": 150,
            "output_tokens": 60,
            "cached": 0,
            "thought_tokens": 20,
            "tool_tokens": 10,
            "thoughts": [{"subject": "File Reading", "description": "Reading package.json"}],
            "tool_calls": [
                {
                    "id": "read_file-001",
                    "name": "read_file",
                    "args": {"file_path": "package.json"},
                    "result": [
                        {
                            "functionResponse": {
                                "id": "read_file-001",
                                "name": "read_file",
                                "response": {"output": '{"name": "test"}'},
                            }
                        }
                    ],
                    "status": "success",
                }
            ],
        },
        {"role": "user", "content": "What's the project name?"},
        {
            "role": "assistant",
            "content": "The project name is 'test'.",
            "input_tokens": 250,
            "output_tokens": 120,
            "cached": 50,
            "thought_tokens": 15,
            "tool_tokens": 0,
            "thoughts": [{"subject": "Answering", "description": "Extracting project name"}],
        },
    ]

    session_data = build_gemini_stats_session(
        session_id=exp["session_id"],
        project_hash=exp["workspace"],
        messages=messages,
        model=exp["model"],
    )

    # Write session file
    chat_dir = gemini_dir / exp["workspace"] / "chats"
    chat_dir.mkdir(parents=True, exist_ok=True)
    session_file = chat_dir / f"session-{exp['session_id']}.json"

    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2)

    return session_file


@pytest.fixture
def setup_all_stats_fixtures(
    setup_claude_stats_fixture: Path,
    setup_codex_stats_fixture: Path,
    setup_gemini_stats_fixture: Path,
) -> Dict[str, Path]:
    """Set up all three agent fixtures for combined stats tests."""
    return {
        "claude": setup_claude_stats_fixture,
        "codex": setup_codex_stats_fixture,
        "gemini": setup_gemini_stats_fixture,
    }


@pytest.fixture
def setup_multi_model_fixtures(stats_test_home: Dict[str, Any]) -> List[Path]:
    """Create multiple Claude sessions with different models."""
    claude_dir = stats_test_home["claude_dir"]
    session_files = []

    for session_spec in CLAUDE_MULTI_MODEL_EXPECTED["sessions"]:
        messages = [
            {"role": "user", "content": "Test message"},
            {
                "role": "assistant",
                "content": "Test response",
                "input_tokens": session_spec["input_tokens"],
                "output_tokens": session_spec["output_tokens"],
            },
        ]

        # Add extra message pair for sonnet
        if session_spec["messages"] == 4:  # noqa: PLR2004
            messages.extend(
                [
                    {"role": "user", "content": "Another message"},
                    {
                        "role": "assistant",
                        "content": "Another response",
                        "input_tokens": session_spec["input_tokens"],
                        "output_tokens": session_spec["output_tokens"] - 25,
                    },
                ]
            )

        records = build_claude_stats_session(
            session_id=session_spec["session_id"],
            workspace="-home-testuser-multi-model",
            messages=messages,
            model=session_spec["model"],
        )

        ws_dir = claude_dir / "-home-testuser-multi-model"
        ws_dir.mkdir(parents=True, exist_ok=True)
        session_file = ws_dir / f"{session_spec['session_id']}.jsonl"

        with open(session_file, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        session_files.append(session_file)

    return session_files


@pytest.fixture
def setup_multi_day_fixtures(stats_test_home: Dict[str, Any]) -> List[Path]:
    """Create sessions across multiple days."""
    claude_dir = stats_test_home["claude_dir"]
    session_files = []

    for session_spec in MULTI_DAY_EXPECTED["sessions"]:
        # Build message list based on count
        messages = []
        for i in range(session_spec["messages"] // 2):
            messages.extend(
                [
                    {"role": "user", "content": f"Message {i+1}"},
                    {
                        "role": "assistant",
                        "content": f"Response {i+1}",
                        "input_tokens": 50,
                        "output_tokens": 25,
                    },
                ]
            )

        records = build_claude_stats_session(
            session_id=session_spec["session_id"],
            workspace="-home-testuser-multi-day",
            messages=messages,
        )

        # Adjust timestamps for the correct date
        date = datetime.strptime(session_spec["date"], "%Y-%m-%d")
        for i, record in enumerate(records):
            record["timestamp"] = (date + timedelta(seconds=i * 5)).isoformat() + "Z"

        ws_dir = claude_dir / "-home-testuser-multi-day"
        ws_dir.mkdir(parents=True, exist_ok=True)
        session_file = ws_dir / f"{session_spec['session_id']}.jsonl"

        with open(session_file, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        session_files.append(session_file)

    return session_files


@pytest.fixture
def setup_multi_tool_fixtures(stats_test_home: Dict[str, Any]) -> Path:
    """Create session with multiple tool types."""
    claude_dir = stats_test_home["claude_dir"]
    tool_counts = MULTI_TOOL_EXPECTED["tool_calls"]

    messages = [{"role": "user", "content": "Perform various operations"}]

    # Build assistant messages with tool calls
    tool_id_counter = 1
    for tool_name, count in tool_counts.items():
        tools = []
        for _ in range(count):
            tools.append(
                {
                    "id": f"toolu_{tool_id_counter:03d}",
                    "name": tool_name,
                    "input": {"param": "value"},
                }
            )
            tool_id_counter += 1

        messages.append(
            {
                "role": "assistant",
                "content": f"Using {tool_name}",
                "input_tokens": 100,
                "output_tokens": 50,
                "tool_use": tools,
            }
        )

        # Add tool results
        for tool in tools:
            messages.append(
                {"role": "user", "tool_result": {"tool_use_id": tool["id"], "content": "Success"}}
            )

    # Final response
    messages.append(
        {
            "role": "assistant",
            "content": "All operations complete.",
            "input_tokens": 100,
            "output_tokens": 50,
        }
    )

    records = build_claude_stats_session(
        session_id="multi-tool-session",
        workspace="-home-testuser-multi-tool",
        messages=messages,
    )

    ws_dir = claude_dir / "-home-testuser-multi-tool"
    ws_dir.mkdir(parents=True, exist_ok=True)
    session_file = ws_dir / "multi-tool-session.jsonl"

    with open(session_file, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    return session_file


@pytest.fixture
def setup_workspace_fixtures(stats_test_home: Dict[str, Any]) -> Dict[str, List[Path]]:
    """Create sessions in multiple workspaces for grouping tests."""
    claude_dir = stats_test_home["claude_dir"]
    workspaces = {
        "-home-testuser-workspace-alpha": [],
        "-home-testuser-workspace-beta": [],
        "-home-testuser-workspace-gamma": [],
    }

    session_counter = 1
    for workspace, session_list in workspaces.items():
        # Create 2 sessions per workspace
        for i in range(2):
            messages = [
                {"role": "user", "content": f"Message in {workspace}"},
                {
                    "role": "assistant",
                    "content": f"Response in {workspace}",
                    "input_tokens": 100,
                    "output_tokens": 50,
                },
            ]

            records = build_claude_stats_session(
                session_id=f"ws-session-{session_counter:03d}",
                workspace=workspace,
                messages=messages,
            )

            ws_dir = claude_dir / workspace
            ws_dir.mkdir(parents=True, exist_ok=True)
            session_file = ws_dir / f"ws-session-{session_counter:03d}.jsonl"

            with open(session_file, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record) + "\n")

            session_list.append(session_file)
            session_counter += 1

    return workspaces
