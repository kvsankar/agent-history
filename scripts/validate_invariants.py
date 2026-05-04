#!/usr/bin/env python3
"""
Validate mathematical invariants in stats database.
"""

import sqlite3
import sys
from pathlib import Path


def get_metrics_db_path():
    """Get metrics database path."""
    return Path.home() / ".agent-history" / "metrics.db"


def check_user_assistant_sum(conn):
    """Check if user + assistant = total messages."""
    cursor = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN type = 'user' THEN 1 ELSE 0 END) as user_count,
            SUM(CASE WHEN type IN ('assistant', 'gemini') THEN 1 ELSE 0 END) as assistant_count
        FROM messages
        WHERE type IN ('user', 'assistant', 'gemini')
    """)
    row = cursor.fetchone()
    total, user, assistant = row[0], row[1], row[2]

    passed = user + assistant == total
    print("Invariant: user + assistant = total messages")
    print(f"  {user} + {assistant} = {total}")
    print(f"  Result: {'PASS ✓' if passed else 'FAIL ✗'}")
    return passed


def check_grouped_sessions_sum(conn):
    """Check if sum of grouped sessions equals total."""
    total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    grouped = (
        conn.execute("""
        SELECT SUM(cnt) FROM (
            SELECT COUNT(*) as cnt
            FROM sessions
            GROUP BY workspace
        )
    """).fetchone()[0]
        or 0
    )

    passed = grouped == total
    print("\nInvariant: sum of workspace-grouped sessions = total")
    print(f"  Grouped: {grouped}, Total: {total}")
    print(f"  Result: {'PASS ✓' if passed else 'FAIL ✗'}")
    return passed


def check_grouped_tokens_sum(conn):
    """Check if sum of grouped tokens equals total."""
    cursor = conn.execute("""
        SELECT
            COALESCE(SUM(input_tokens), 0) as total_input,
            COALESCE(SUM(output_tokens), 0) as total_output
        FROM messages
    """)
    row = cursor.fetchone()
    total_input, total_output = row[0], row[1]

    cursor = conn.execute("""
        SELECT
            COALESCE(SUM(input_sum), 0) as grouped_input,
            COALESCE(SUM(output_sum), 0) as grouped_output
        FROM (
            SELECT
                SUM(input_tokens) as input_sum,
                SUM(output_tokens) as output_sum
            FROM messages
            GROUP BY model
        )
    """)
    row = cursor.fetchone()
    grouped_input, grouped_output = row[0], row[1]

    input_passed = grouped_input == total_input
    output_passed = grouped_output == total_output

    print("\nInvariant: sum of model-grouped tokens = total")
    print(f"  Input: Grouped={grouped_input}, Total={total_input} {'✓' if input_passed else '✗'}")
    print(
        f"  Output: Grouped={grouped_output}, Total={total_output} {'✓' if output_passed else '✗'}"
    )
    print(f"  Result: {'PASS ✓' if input_passed and output_passed else 'FAIL ✗'}")
    return input_passed and output_passed


def check_non_negative_values(conn):
    """Check all counts are non-negative."""
    checks = [
        ("messages.input_tokens", "SELECT COUNT(*) FROM messages WHERE input_tokens < 0"),
        ("messages.output_tokens", "SELECT COUNT(*) FROM messages WHERE output_tokens < 0"),
        ("sessions.message_count", "SELECT COUNT(*) FROM sessions WHERE message_count < 0"),
    ]

    print("\nInvariant: all counts are non-negative")
    all_passed = True
    for name, query in checks:
        negative_count = conn.execute(query).fetchone()[0]
        passed = negative_count == 0
        all_passed = all_passed and passed
        print(f"  {name}: {negative_count} negative values {'✓' if passed else '✗'}")

    print(f"  Result: {'PASS ✓' if all_passed else 'FAIL ✗'}")
    return all_passed


def check_session_ids_unique(conn):
    """Check session IDs are unique."""
    cursor = conn.execute("""
        SELECT
            COUNT(*) as total_sessions,
            COUNT(DISTINCT session_id) as unique_sessions
        FROM sessions
    """)
    row = cursor.fetchone()
    total, unique = row[0], row[1]

    passed = total == unique
    print("\nInvariant: session IDs are unique")
    print(f"  Total: {total}, Unique: {unique}")
    print(f"  Result: {'PASS ✓' if passed else 'FAIL ✗'}")
    return passed


def main():
    """Main validation function."""
    print("=== Agent-History Stats Invariants Validation ===\n")

    db_path = get_metrics_db_path()

    if not db_path.exists():
        print(f"Error: Metrics database not found at {db_path}")
        print("Run 'agent-history session stats --sync --aw' first")
        return 1

    conn = sqlite3.connect(str(db_path))

    results = []
    results.append(check_user_assistant_sum(conn))
    results.append(check_grouped_sessions_sum(conn))
    results.append(check_grouped_tokens_sum(conn))
    results.append(check_non_negative_values(conn))
    results.append(check_session_ids_unique(conn))

    conn.close()

    print(f"\n{'='*50}")
    passed = sum(results)
    total = len(results)
    print(f"Overall: {passed}/{total} invariants passed")

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
