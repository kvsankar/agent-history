from __future__ import annotations

from datetime import datetime

from tests.helpers.module_loader import load_agent_history


def test_session_list_columns_single_home(capsys):
    """session list output uses spec columns with size and modified date."""
    ah = load_agent_history()
    sessions = [
        {
            "filename": "session-1.jsonl",
            "size_kb": 12.3,
            "message_count": 7,
            "modified": datetime(2025, 1, 3, 18, 15),
        }
    ]

    ah.print_sessions_output(sessions, "Local", workspaces_only=False, output_format="tsv")
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0] == "SESSION\tMESSAGES\tSIZE\tMODIFIED"
    assert out[1] == "session-1.jsonl\t7\t12.3 KB\t2025-01-03 18:15"


def test_session_list_columns_multi_home(capsys):
    """multi-home session list includes HOME/WORKSPACE/SESSION/SIZE/MODIFIED."""
    ah = load_agent_history()
    sessions_local = [
        {
            "workspace": "/home/user/proj",
            "workspace_readable": "/home/user/proj",
            "filename": "sess-a.jsonl",
            "size_kb": 5.0,
            "message_count": 2,
            "modified": datetime(2025, 1, 2, 10, 30),
        }
    ]
    sessions_remote = [
        {
            "workspace": "/srv/app",
            "workspace_readable": "/srv/app",
            "filename": "sess-b.jsonl",
            "size_kb": 8.4,
            "message_count": 3,
            "modified": datetime(2025, 1, 1, 9, 0),
        }
    ]

    ah._print_all_homes_results(  # type: ignore[attr-defined]
        [("Local", sessions_local), ("Remote (vm01)", sessions_remote)],
        workspaces_only=False,
        output_format="tsv",
    )
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0] == "HOME\tWORKSPACE\tSESSION\tMESSAGES\tSIZE\tMODIFIED"
    assert out[1] == "local\t/home/user/proj\tsess-a.jsonl\t2\t5.0 KB\t2025-01-02 10:30"
    assert out[2] == "remote:vm01\t/srv/app\tsess-b.jsonl\t3\t8.4 KB\t2025-01-01 09:00"
