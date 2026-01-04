"""Session factory helpers for creating synthetic test data."""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class ClaudeSessionBuilder:
    """Builder for Claude Code session files."""

    def __init__(
        self,
        workspace: str = "-home-testuser-project",
        session_id: Optional[str] = None,
    ):
        self.workspace = workspace
        self.session_id = session_id or str(uuid.uuid4())
        self.messages: List[Dict[str, Any]] = []
        self._parent_uuid: Optional[str] = None
        self._timestamp = datetime(2025, 1, 3, 10, 0, 0)
        self._tool_counter = 1

    def add_user_message(self, content: str) -> "ClaudeSessionBuilder":
        """Add a user message."""
        msg_uuid = str(uuid.uuid4())
        self.messages.append(
            {
                "type": "user",
                "uuid": msg_uuid,
                "parentUuid": self._parent_uuid,
                "sessionId": self.session_id,
                "timestamp": self._timestamp.isoformat() + "Z",
                "cwd": f"/home/testuser/{self.workspace.replace('-', '/')}",
                "message": {"role": "user", "content": content},
            }
        )
        self._parent_uuid = msg_uuid
        self._timestamp += timedelta(seconds=5)
        return self

    def add_tool_result(self, tool_use_id: str, content: str) -> "ClaudeSessionBuilder":
        """Add a tool result as a user message."""
        msg_uuid = str(uuid.uuid4())
        self.messages.append(
            {
                "type": "user",
                "uuid": msg_uuid,
                "parentUuid": self._parent_uuid,
                "sessionId": self.session_id,
                "timestamp": self._timestamp.isoformat() + "Z",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
                    ],
                },
            }
        )
        self._parent_uuid = msg_uuid
        self._timestamp += timedelta(seconds=1)
        return self

    def add_assistant_message(
        self,
        content: str,
        input_tokens: int = 100,
        output_tokens: int = 50,
        tools: Optional[List[Dict[str, Any]]] = None,
        thinking: Optional[str] = None,
    ) -> "ClaudeSessionBuilder":
        """Add an assistant message with optional tool use and thinking."""
        msg_uuid = str(uuid.uuid4())
        content_blocks = []

        if thinking:
            content_blocks.append({"type": "thinking", "thinking": thinking})

        content_blocks.append({"type": "text", "text": content})

        if tools:
            content_blocks.extend(tools)

        self.messages.append(
            {
                "type": "assistant",
                "uuid": msg_uuid,
                "parentUuid": self._parent_uuid,
                "sessionId": self.session_id,
                "timestamp": self._timestamp.isoformat() + "Z",
                "requestId": f"req_{msg_uuid[:8]}",
                "message": {
                    "id": f"msg_{msg_uuid[:8]}",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-4-20250514",
                    "content": content_blocks,
                    "stop_reason": "tool_use" if tools else "end_turn",
                    "usage": {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                    },
                },
            }
        )
        self._parent_uuid = msg_uuid
        self._timestamp += timedelta(seconds=10)
        return self

    def make_tool_use(self, name: str, input_args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a tool_use content block."""
        tool_id = f"toolu_{self._tool_counter:03d}"
        self._tool_counter += 1
        return {
            "type": "tool_use",
            "id": tool_id,
            "name": name,
            "input": input_args,
        }

    def build(self) -> List[Dict[str, Any]]:
        """Return the message list."""
        return self.messages

    def write_to(self, directory: Path) -> Path:
        """Write session to JSONL file in directory."""
        ws_dir = directory / self.workspace
        ws_dir.mkdir(parents=True, exist_ok=True)
        session_file = ws_dir / f"{self.session_id}.jsonl"

        with open(session_file, "w", encoding="utf-8") as f:
            for msg in self.messages:
                f.write(json.dumps(msg) + "\n")

        return session_file


class CodexSessionBuilder:
    """Builder for Codex CLI session files."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        cwd: str = "/home/testuser/codex-project",
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.cwd = cwd
        self.records: List[Dict[str, Any]] = []
        self._timestamp = datetime(2025, 1, 4, 9, 0, 0)
        self._call_counter = 1
        self._init_session()

    def _init_session(self) -> None:
        """Add session metadata records."""
        self.records.append(
            {
                "timestamp": self._timestamp.isoformat() + "Z",
                "type": "session_meta",
                "payload": {
                    "id": self.session_id,
                    "timestamp": self._timestamp.isoformat() + "Z",
                    "cwd": self.cwd,
                    "originator": "codex_cli_rs",
                    "cli_version": "0.77.0",
                    "source": "cli",
                    "model_provider": "openai",
                    "git": {"commit_hash": "abc123", "branch": "main"},
                },
            }
        )
        self._timestamp += timedelta(seconds=1)
        self.records.append(
            {
                "timestamp": self._timestamp.isoformat() + "Z",
                "type": "turn_context",
                "payload": {
                    "cwd": self.cwd,
                    "approval_policy": "on-request",
                    "model": "gpt-4.5-turbo",
                    "effort": "high",
                },
            }
        )
        self._timestamp += timedelta(seconds=1)

    def add_user_message(self, content: str) -> "CodexSessionBuilder":
        """Add a user message."""
        self.records.append(
            {
                "timestamp": self._timestamp.isoformat() + "Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": content}],
                },
            }
        )
        self._timestamp += timedelta(seconds=3)
        return self

    def add_assistant_message(self, content: str) -> "CodexSessionBuilder":
        """Add an assistant message."""
        self.records.append(
            {
                "timestamp": self._timestamp.isoformat() + "Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": content}],
                },
            }
        )
        self._timestamp += timedelta(seconds=5)
        return self

    def add_reasoning(self, summary: str) -> "CodexSessionBuilder":
        """Add a reasoning block."""
        self.records.append(
            {
                "timestamp": self._timestamp.isoformat() + "Z",
                "type": "response_item",
                "payload": {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": summary}],
                    "content": None,
                    "encrypted_content": None,
                },
            }
        )
        self._timestamp += timedelta(seconds=2)
        return self

    def add_function_call(self, name: str, arguments: Dict[str, Any]) -> "CodexSessionBuilder":
        """Add a function call."""
        call_id = f"call_{self._call_counter:03d}"
        self._call_counter += 1
        self.records.append(
            {
                "timestamp": self._timestamp.isoformat() + "Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": name,
                    "arguments": json.dumps(arguments),
                    "call_id": call_id,
                },
            }
        )
        self._timestamp += timedelta(seconds=1)
        return self

    def add_function_output(self, call_id: str, output: str) -> "CodexSessionBuilder":
        """Add a function call output."""
        self.records.append(
            {
                "timestamp": self._timestamp.isoformat() + "Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
                },
            }
        )
        self._timestamp += timedelta(seconds=1)
        return self

    def add_token_count(
        self,
        input_tokens: int,
        output_tokens: int,
        cached: int = 0,
        reasoning: int = 0,
    ) -> "CodexSessionBuilder":
        """Add token count event."""
        self.records.append(
            {
                "timestamp": self._timestamp.isoformat() + "Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": input_tokens,
                            "cached_input_tokens": cached,
                            "output_tokens": output_tokens,
                            "reasoning_output_tokens": reasoning,
                            "total_tokens": input_tokens + output_tokens,
                        },
                        "last_token_usage": {
                            "input_tokens": input_tokens // 2,
                            "cached_input_tokens": cached // 2,
                            "output_tokens": output_tokens // 2,
                            "reasoning_output_tokens": reasoning // 2,
                            "total_tokens": (input_tokens + output_tokens) // 2,
                        },
                        "model_context_window": 128000,
                    },
                },
            }
        )
        return self

    def build(self) -> List[Dict[str, Any]]:
        """Return the records list."""
        return self.records

    def write_to(self, directory: Path, date_str: str = "2025-01-04") -> Path:
        """Write session to JSONL file in date-based directory."""
        year, month, day = date_str.split("-")
        date_dir = directory / year / month / day
        date_dir.mkdir(parents=True, exist_ok=True)
        session_file = date_dir / f"rollout-{self.session_id}.jsonl"

        with open(session_file, "w", encoding="utf-8") as f:
            for record in self.records:
                f.write(json.dumps(record) + "\n")

        return session_file


class GeminiSessionBuilder:
    """Builder for Gemini CLI session files."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        project_hash: Optional[str] = None,
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.project_hash = project_hash or "a" * 64
        self.messages: List[Dict[str, Any]] = []
        self._timestamp = datetime(2025, 1, 5, 14, 0, 0)
        self._msg_counter = 1
        self._tool_counter = 1

    def add_user_message(self, content: str) -> "GeminiSessionBuilder":
        """Add a user message."""
        self.messages.append(
            {
                "id": f"msg-g{self._msg_counter}",
                "timestamp": self._timestamp.isoformat() + "Z",
                "type": "user",
                "content": content,
            }
        )
        self._msg_counter += 1
        self._timestamp += timedelta(seconds=5)
        return self

    def add_gemini_message(
        self,
        content: str,
        model: str = "gemini-2.5-pro",
        input_tokens: int = 100,
        output_tokens: int = 50,
        thoughts: Optional[List[Dict[str, str]]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> "GeminiSessionBuilder":
        """Add a Gemini response message."""
        msg = {
            "id": f"msg-g{self._msg_counter}",
            "timestamp": self._timestamp.isoformat() + "Z",
            "type": "gemini",
            "content": content,
            "model": model,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "cached": 0,
                "thoughts": 0,
                "tool": 0,
                "total": input_tokens + output_tokens,
            },
        }

        if thoughts:
            msg["thoughts"] = thoughts

        if tool_calls:
            msg["toolCalls"] = tool_calls

        self.messages.append(msg)
        self._msg_counter += 1
        self._timestamp += timedelta(seconds=10)
        return self

    def make_thought(self, subject: str, description: str) -> Dict[str, str]:
        """Create a thought entry."""
        return {
            "subject": subject,
            "description": description,
            "timestamp": self._timestamp.isoformat() + "Z",
        }

    def make_tool_call(
        self,
        name: str,
        args: Dict[str, Any],
        result: Any,
        status: str = "success",
    ) -> Dict[str, Any]:
        """Create a tool call entry with result."""
        tool_id = f"{name}-{self._tool_counter:03d}"
        self._tool_counter += 1
        return {
            "id": tool_id,
            "name": name,
            "args": args,
            "result": [
                {"functionResponse": {"id": tool_id, "name": name, "response": {"output": result}}}
            ],
            "status": status,
            "timestamp": self._timestamp.isoformat() + "Z",
            "displayName": name.replace("_", " ").title(),
        }

    def build(self) -> Dict[str, Any]:
        """Return the session data."""
        return {
            "sessionId": self.session_id,
            "projectHash": self.project_hash,
            "startTime": self.messages[0]["timestamp"] if self.messages else None,
            "lastUpdated": self.messages[-1]["timestamp"] if self.messages else None,
            "messages": self.messages,
        }

    def write_to(self, directory: Path) -> Path:
        """Write session to JSON file in hash-based directory."""
        chat_dir = directory / self.project_hash / "chats"
        chat_dir.mkdir(parents=True, exist_ok=True)
        session_file = chat_dir / f"session-{self.session_id}.json"

        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(self.build(), f, indent=2)

        return session_file
