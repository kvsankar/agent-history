"""Helpers for workspace encoding and fixture creation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Dict, Any


def encode_workspace_path(path: str) -> str:
    """Encode a path as a Claude workspace directory name."""
    path = path.replace("\\", "/").rstrip("/")

    windows_drive_match = re.match(r"^[A-Za-z]:", path)
    if windows_drive_match:
        drive = windows_drive_match.group(0)[0].upper()
        remainder = path[len(windows_drive_match.group(0)) :].lstrip("/").replace("/", "-")
        return f"{drive}--{remainder}"

    wsl_prefix = "/mnt/"
    if path.startswith(wsl_prefix) and len(path) > len(wsl_prefix):
        drive_letter = path[len(wsl_prefix)]
        if drive_letter.isalpha():
            drive = drive_letter.upper()
            remainder = path[len(wsl_prefix) + 1 :].lstrip("/").replace("/", "-")
            return f"{drive}--{remainder}"
        return f"{drive}--{remainder}"

    encoded = path.replace("/", "-")
    if not encoded.startswith("-"):
        encoded = "-" + encoded
    return encoded


def create_workspace_fixture(base_path: Path, workspace_path: str, num_sessions: int = 1) -> str:
    """Create a Claude workspace with sessions at the given path."""
    encoded = encode_workspace_path(workspace_path)

    claude_dir = base_path / ".claude" / "projects" / encoded
    claude_dir.mkdir(parents=True, exist_ok=True)

    for i in range(num_sessions):
        session_file = claude_dir / f"session-{i:03d}.jsonl"
        session_data: List[Dict[str, Any]] = [
            {
                "type": "user",
                "message": {"role": "user", "content": "test"},
                "timestamp": "2025-01-01T10:00:00Z",
                "sessionId": f"sess-{i}",
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
                "timestamp": "2025-01-01T10:00:01Z",
                "sessionId": f"sess-{i}",
            },
        ]
        with open(session_file, "w", encoding="utf-8") as f:
            for entry in session_data:
                f.write(json.dumps(entry) + "\n")

    return encoded
