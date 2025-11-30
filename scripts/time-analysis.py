#!/usr/bin/env python3
"""
Time Tracking Analysis Script

Compares two approaches to measuring time spent in Claude Code sessions:
1. Simple: Sum of (last_timestamp - first_timestamp) per file
2. Work-period: Detect gaps, sum only active work periods

Run from project root:
    python3 scripts/time-analysis.py [workspace-pattern]
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

# Gap threshold for work period detection (seconds)
GAP_THRESHOLD = 30 * 60  # 30 minutes


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp to datetime."""
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))


def get_file_timestamps(jsonl_file: Path) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    """
    Extract session_id and all (timestamp, type) pairs from a JSONL file.
    Only includes user/assistant messages (they always have timestamps).
    """
    session_id = None
    timestamps = []

    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                rec = json.loads(line)
                if not session_id and rec.get('sessionId'):
                    session_id = rec['sessionId']
                if rec.get('timestamp') and rec.get('type') in ('user', 'assistant'):
                    timestamps.append((rec['timestamp'], rec['type']))
            except (json.JSONDecodeError, KeyError):
                continue

    return session_id, timestamps


def simple_duration(timestamps: List[Tuple[str, str]]) -> float:
    """
    Simple approach: max_timestamp - min_timestamp.
    Returns duration in seconds.

    Note: We use min/max instead of first/last because timestamps
    in JSONL files are not always in chronological order (due to
    context restoration, summary expansion, etc.)
    """
    if len(timestamps) < 2:
        return 0.0

    parsed = [parse_timestamp(t[0]) for t in timestamps]
    return (max(parsed) - min(parsed)).total_seconds()


def work_period_duration(timestamps: List[Tuple[str, str]], gap_threshold: float = GAP_THRESHOLD) -> Tuple[float, int]:
    """
    Work-period approach: Sum only active periods, excluding gaps.
    Returns (total_seconds, num_work_periods).

    Note: Timestamps are sorted first since JSONL files may have
    out-of-order timestamps due to context restoration.
    """
    if len(timestamps) < 2:
        return 0.0, 1 if timestamps else 0

    # Sort timestamps chronologically
    sorted_ts = sorted(timestamps, key=lambda x: x[0])

    total_duration = 0.0
    num_periods = 1
    period_start = parse_timestamp(sorted_ts[0][0])
    prev_ts = period_start

    for ts_str, _ in sorted_ts[1:]:
        ts = parse_timestamp(ts_str)
        gap = (ts - prev_ts).total_seconds()

        if gap > gap_threshold:
            # End current period, start new one
            total_duration += (prev_ts - period_start).total_seconds()
            period_start = ts
            num_periods += 1

        prev_ts = ts

    # Add final period
    total_duration += (prev_ts - period_start).total_seconds()

    return total_duration, num_periods


def format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    elif seconds < 86400:
        return f"{seconds/3600:.1f}h"
    else:
        return f"{seconds/86400:.1f}d"


def analyze_workspace(ws_dir: Path) -> Dict:
    """Analyze all sessions in a workspace."""
    # Group files by session ID
    sessions = defaultdict(list)

    for jsonl_file in ws_dir.glob('*.jsonl'):
        session_id, timestamps = get_file_timestamps(jsonl_file)

        if session_id and timestamps:
            is_agent = jsonl_file.name.startswith('agent-')
            sessions[session_id].append({
                'file': jsonl_file.name,
                'is_agent': is_agent,
                'timestamps': timestamps,
                'first_ts': timestamps[0][0],
                'last_ts': timestamps[-1][0],
            })

    results = []

    for session_id, files in sessions.items():
        main_files = [f for f in files if not f['is_agent']]
        agent_files = [f for f in files if f['is_agent']]

        if not main_files:
            continue  # Skip orphan agents

        main = main_files[0]

        # Simple approach: sum per-file durations
        simple_main = simple_duration(main['timestamps'])
        simple_agents = sum(simple_duration(a['timestamps']) for a in agent_files)
        simple_total = simple_main + simple_agents

        # Work-period approach for main file
        wp_main, wp_periods = work_period_duration(main['timestamps'])
        wp_agents = sum(work_period_duration(a['timestamps'])[0] for a in agent_files)
        wp_total = wp_main + wp_agents

        # Calendar time: span from earliest to latest across all files
        all_timestamps = []
        for f in files:
            all_timestamps.extend([t[0] for t in f['timestamps']])
        all_timestamps.sort()
        calendar_time = (parse_timestamp(all_timestamps[-1]) - parse_timestamp(all_timestamps[0])).total_seconds()

        # Check for concurrent agents
        concurrent_agents = 0
        if len(agent_files) >= 2:
            agent_times = [(parse_timestamp(a['first_ts']), parse_timestamp(a['last_ts'])) for a in agent_files]
            for i, (s1, e1) in enumerate(agent_times):
                for s2, e2 in agent_times[i+1:]:
                    if s2 < e1:  # Overlap
                        concurrent_agents += 1

        results.append({
            'session_id': session_id[:8],
            'main_msgs': len(main['timestamps']),
            'num_agents': len(agent_files),
            'concurrent_agents': concurrent_agents,
            'calendar_time': calendar_time,
            'simple_total': simple_total,
            'work_period_total': wp_total,
            'work_periods': wp_periods,
            'gap_time': simple_main - wp_main,  # Time spent in gaps (main only)
        })

    return results


def main():
    projects_dir = Path.home() / '.claude' / 'projects'

    if not projects_dir.exists():
        print(f"Error: {projects_dir} not found", file=sys.stderr)
        sys.exit(1)

    # Optional workspace filter
    pattern = sys.argv[1] if len(sys.argv) > 1 else None

    all_results = []

    for ws_dir in projects_dir.iterdir():
        if not ws_dir.is_dir():
            continue
        if pattern and pattern not in ws_dir.name:
            continue

        results = analyze_workspace(ws_dir)
        for r in results:
            r['workspace'] = ws_dir.name[-30:]
        all_results.extend(results)

    if not all_results:
        print("No sessions found")
        return

    # Sort by calendar time descending
    all_results.sort(key=lambda x: x['calendar_time'], reverse=True)

    # Print header
    print("=" * 100)
    print("TIME TRACKING ANALYSIS")
    print(f"Gap threshold: {GAP_THRESHOLD/60:.0f} minutes")
    print("=" * 100)
    print()

    # Print per-session results
    print(f"{'Session':<10} {'Msgs':>6} {'Agents':>6} {'Calendar':>10} {'Simple':>10} {'WorkPeriod':>10} {'Periods':>8} {'GapTime':>10}")
    print("-" * 100)

    total_calendar = 0
    total_simple = 0
    total_wp = 0
    total_gap = 0

    for r in all_results[:30]:  # Top 30
        print(f"{r['session_id']:<10} "
              f"{r['main_msgs']:>6} "
              f"{r['num_agents']:>6} "
              f"{format_duration(r['calendar_time']):>10} "
              f"{format_duration(r['simple_total']):>10} "
              f"{format_duration(r['work_period_total']):>10} "
              f"{r['work_periods']:>8} "
              f"{format_duration(r['gap_time']):>10}")

        total_calendar += r['calendar_time']
        total_simple += r['simple_total']
        total_wp += r['work_period_total']
        total_gap += r['gap_time']

    if len(all_results) > 30:
        print(f"... and {len(all_results) - 30} more sessions")
        for r in all_results[30:]:
            total_calendar += r['calendar_time']
            total_simple += r['simple_total']
            total_wp += r['work_period_total']
            total_gap += r['gap_time']

    print("-" * 100)
    print(f"{'TOTAL':<10} "
          f"{'':>6} "
          f"{'':>6} "
          f"{format_duration(total_calendar):>10} "
          f"{format_duration(total_simple):>10} "
          f"{format_duration(total_wp):>10} "
          f"{'':>8} "
          f"{format_duration(total_gap):>10}")

    # Summary statistics
    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print()
    print(f"Total sessions analyzed: {len(all_results)}")
    print()
    print(f"Calendar Time (wall clock):     {format_duration(total_calendar):>12}")
    print(f"Simple Effort (per-file sum):   {format_duration(total_simple):>12}")
    print(f"Work Period Effort (gap-aware): {format_duration(total_wp):>12}")
    print(f"Time in gaps (excluded):        {format_duration(total_gap):>12}")
    print()

    if total_simple > 0:
        ratio = total_wp / total_simple * 100
        print(f"Work Period / Simple ratio: {ratio:.1f}%")
        print(f"  (Lower = more time spent in gaps between work periods)")

    if total_calendar > 0:
        print()
        print(f"Simple / Calendar ratio: {total_simple / total_calendar * 100:.1f}%")
        print(f"WorkPeriod / Calendar ratio: {total_wp / total_calendar * 100:.1f}%")

    # Sessions with most gap time
    print()
    print("=" * 100)
    print("SESSIONS WITH MOST GAP TIME")
    print("=" * 100)
    print()

    by_gap = sorted(all_results, key=lambda x: x['gap_time'], reverse=True)[:10]
    for r in by_gap:
        if r['gap_time'] > 0:
            gap_pct = r['gap_time'] / r['simple_total'] * 100 if r['simple_total'] > 0 else 0
            print(f"  {r['session_id']}: {format_duration(r['gap_time'])} gap time "
                  f"({gap_pct:.0f}% of simple duration), {r['work_periods']} work periods")


if __name__ == '__main__':
    main()
