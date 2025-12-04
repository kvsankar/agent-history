#!/usr/bin/env python3
"""Update the README help snippet from the actual CLI output."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READ_ME = ROOT / "README.md"
START_MARKER = "<!-- help-snippet:start -->"
END_MARKER = "<!-- help-snippet:end -->"


def render_help_output() -> str:
    """Return the current `claude-history --help` output as a fenced block."""
    try:
        result = subprocess.run(
            [sys.executable, "claude-history", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise SystemExit(
            f"Failed to run `claude-history --help` (exit {exc.returncode}):\n{exc.stderr}"
        ) from exc

    help_text = result.stdout.strip()
    return f"{START_MARKER}\n```\n{help_text}\n```\n{END_MARKER}"


def update_readme_block(new_block: str) -> None:
    """Replace the help snippet block in README.md with new content."""
    text = READ_ME.read_text()
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start == -1 or end == -1:
        raise SystemExit(f"Could not find help markers {START_MARKER} / {END_MARKER} in {READ_ME}")

    end += len(END_MARKER)
    updated = text[:start] + new_block + text[end:]
    if updated == text:
        return
    READ_ME.write_text(updated)


def main() -> None:
    new_block = render_help_output()
    update_readme_block(new_block)


if __name__ == "__main__":
    main()
