"""Tests for HTML timeline export rendering."""

from __future__ import annotations

import json

from agent_history.export.html import assign_timeline_tracks, render_html_timeline_export


def test_assign_timeline_tracks_separates_overlapping_sessions() -> None:
    sessions = [
        {"id": "a", "start_ms": 0, "end_ms": 100},
        {"id": "b", "start_ms": 50, "end_ms": 120},
        {"id": "c", "start_ms": 120, "end_ms": 140},
    ]

    laid_out = assign_timeline_tracks(sessions)
    by_id = {session["id"]: session for session in laid_out}

    assert by_id["a"]["track_index"] == 0
    assert by_id["b"]["track_index"] == 1
    assert by_id["c"]["track_index"] == 0


def test_render_html_timeline_export_writes_json_and_session_bars() -> None:
    html = render_html_timeline_export(
        [
            {
                "id": "session-1",
                "title": "Unsafe <prompt>",
                "agent": "codex",
                "workspace_display": "/repo",
                "html_file": "sessions/session-1.html",
                "start": "2026-06-09T10:00:00Z",
                "end": "2026-06-09T10:05:00Z",
                "start_ms": 1000,
                "end_ms": 301000,
                "duration_label": "5m",
                "message_count": 4,
            }
        ]
    )

    assert html.startswith("<!doctype html>")
    assert 'data-session-id="session-1"' in html
    assert "Unsafe &lt;prompt&gt;" in html
    start = html.index('<script type="application/json" id="timeline-data">')
    start = html.index("\n", start) + 1
    end = html.index("\n</script>", start)
    data = json.loads(html[start:end])

    assert data["sessions"][0]["title"] == "Unsafe <prompt>"
    assert data["sessions"][0]["html_file"] == "sessions/session-1.html"
