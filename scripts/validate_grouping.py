#!/usr/bin/env python3
"""
Validate grouping consistency across all dimensions.
"""

import sqlite3
import sys
from pathlib import Path


def get_metrics_db_path():
    """Get metrics database path."""
    return Path.home() / ".agent-history" / "metrics.db"


def check_grouping_sum(conn, dimension, column):
    """Check if sum of grouped value equals total."""
    total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    grouped = (
        conn.execute(f"""
        SELECT SUM(cnt) FROM (
            SELECT COUNT(*) as cnt
            FROM sessions
            GROUP BY {column}
        )
    """).fetchone()[0]
        or 0
    )

    passed = grouped == total
    print(f"  {dimension}: Total={total}, Grouped={grouped} {'✓' if passed else '✗'}")
    return passed


def main():
    """Main validation function."""
    print("=== Agent-History Stats Grouping Validation ===\n")

    db_path = get_metrics_db_path()

    if not db_path.exists():
        print(f"Error: Metrics database not found at {db_path}")
        print("Run 'agent-history session stats --sync --aw' first")
        return 1

    conn = sqlite3.connect(str(db_path))

    print("Checking grouping consistency (sessions):")
    results = []

    groupings = [
        ("workspace", "workspace"),
        ("agent", "agent"),
        ("source/home", "source"),
        ("day", "DATE(start_time)"),
    ]

    for name, column in groupings:
        try:
            results.append(check_grouping_sum(conn, name, column))
        except sqlite3.OperationalError as e:
            print(f"  {name}: SKIP (column not found: {e})")

    conn.close()

    print(f"\nOverall: {sum(results)}/{len(results)} groupings passed")

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
