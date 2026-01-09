#!/usr/bin/env python3
"""
Validate stats accuracy by comparing database values with actual JSONL file content.
"""

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path


def get_claude_projects_dir():
    """Get Claude projects directory."""
    return Path.home() / ".claude" / "projects"


def get_metrics_db_path():
    """Get metrics database path."""
    return Path.home() / ".agent-history" / "metrics.db"


def count_sessions_from_files(projects_dir):
    """Count sessions by scanning JSONL files."""
    return len(list(projects_dir.glob("**/*.jsonl")))


def count_messages_from_files(projects_dir):
    """Count messages by parsing JSONL files."""
    counts = {"total": 0, "user": 0, "assistant": 0}

    for jsonl_file in projects_dir.glob("**/*.jsonl"):
        try:
            with open(jsonl_file) as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    msg_type = entry.get("type")
                    if msg_type == "user":
                        counts["user"] += 1
                        counts["total"] += 1
                    elif msg_type == "assistant":
                        counts["assistant"] += 1
                        counts["total"] += 1
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Error reading {jsonl_file}: {e}")

    return counts


def count_tokens_from_files(projects_dir):
    """Count tokens by parsing JSONL files."""
    tokens = {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0}

    for jsonl_file in projects_dir.glob("**/*.jsonl"):
        try:
            with open(jsonl_file) as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if entry.get("type") == "assistant":
                        usage = entry.get("usage", {})
                        tokens["input"] += usage.get("input_tokens", 0)
                        tokens["output"] += usage.get("output_tokens", 0)
                        tokens["cache_creation"] += usage.get("cache_creation_input_tokens", 0)
                        tokens["cache_read"] += usage.get("cache_read_input_tokens", 0)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Error reading {jsonl_file}: {e}")

    return tokens


def count_tools_from_files(projects_dir):
    """Count tool uses by parsing JSONL files."""
    tools = Counter()

    for jsonl_file in projects_dir.glob("**/*.jsonl"):
        try:
            with open(jsonl_file) as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if entry.get("type") == "assistant":
                        content = entry.get("content", [])
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                tools[block.get("name")] += 1
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Error reading {jsonl_file}: {e}")

    return tools


def get_db_stats(db_path):
    """Get stats from database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    stats = {}

    # Session counts
    stats["sessions"] = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    # Message counts
    cursor = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN type = 'user' THEN 1 ELSE 0 END) as user,
            SUM(CASE WHEN type IN ('assistant', 'gemini') THEN 1 ELSE 0 END) as assistant
        FROM messages
        WHERE type IN ('user', 'assistant', 'gemini')
    """)
    row = cursor.fetchone()
    stats["messages"] = {"total": row["total"], "user": row["user"], "assistant": row["assistant"]}

    # Token counts
    cursor = conn.execute("""
        SELECT
            COALESCE(SUM(input_tokens), 0) as input,
            COALESCE(SUM(output_tokens), 0) as output,
            COALESCE(SUM(cache_creation_tokens), 0) as cache_creation,
            COALESCE(SUM(cache_read_tokens), 0) as cache_read
        FROM messages
    """)
    row = cursor.fetchone()
    stats["tokens"] = {
        "input": row["input"],
        "output": row["output"],
        "cache_creation": row["cache_creation"],
        "cache_read": row["cache_read"],
    }

    # Tool counts
    cursor = conn.execute("SELECT tool_name, COUNT(*) as count FROM tool_uses GROUP BY tool_name")
    stats["tools"] = {row["tool_name"]: row["count"] for row in cursor}

    conn.close()
    return stats


def main():
    """Main validation function."""
    print("=== Agent-History Stats Validation ===\n")

    projects_dir = get_claude_projects_dir()
    db_path = get_metrics_db_path()

    if not db_path.exists():
        print(f"Error: Metrics database not found at {db_path}")
        print("Run 'agent-history session stats --sync --aw' first")
        return 1

    print("Counting from JSONL files...")
    file_sessions = count_sessions_from_files(projects_dir)
    file_messages = count_messages_from_files(projects_dir)
    file_tokens = count_tokens_from_files(projects_dir)
    file_tools = count_tools_from_files(projects_dir)

    print("Querying database...")
    db_stats = get_db_stats(db_path)

    print("\n=== RESULTS ===\n")

    # Session validation
    print("Sessions:")
    print(f"  Files: {file_sessions}")
    print(f"  DB:    {db_stats['sessions']}")
    print(f"  Match: {'✓' if file_sessions == db_stats['sessions'] else '✗'}")

    # Message validation
    print("\nMessages:")
    for key in ["total", "user", "assistant"]:
        file_val = file_messages[key]
        db_val = db_stats["messages"][key]
        match = "✓" if file_val == db_val else "✗"
        print(f"  {key.capitalize()}: Files={file_val}, DB={db_val} {match}")

    # Token validation
    print("\nTokens:")
    for key in ["input", "output", "cache_creation", "cache_read"]:
        file_val = file_tokens[key]
        db_val = db_stats["tokens"][key]
        match = "✓" if file_val == db_val else "✗"
        print(f"  {key}: Files={file_val}, DB={db_val} {match}")

    # Tool validation
    print("\nTools:")
    all_tools = set(file_tools.keys()) | set(db_stats["tools"].keys())
    for tool in sorted(all_tools):
        file_val = file_tools.get(tool, 0)
        db_val = db_stats["tools"].get(tool, 0)
        match = "✓" if file_val == db_val else "✗"
        print(f"  {tool}: Files={file_val}, DB={db_val} {match}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
