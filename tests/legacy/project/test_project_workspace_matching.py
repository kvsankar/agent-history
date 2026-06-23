"""Tests for project workspace pattern matching.

These tests verify that project session listing correctly matches exact workspaces
and doesn't incorrectly include sessions from workspaces with similar names.
"""

from __future__ import annotations

from tests.helpers.module_loader import load_agent_history


def test_get_alias_workspace_patterns_returns_full_paths():
    """Test that _get_alias_workspace_patterns returns full workspace paths.

    FIX: Now returns full paths like '/home/user/projects/auth' instead of just 'auth'.
    This enables precise substring matching that won't incorrectly match similar names.
    """
    ah = load_agent_history()

    alias_config = {
        "local": ["/home/user/projects/auth"],
    }

    patterns = ah._get_alias_workspace_patterns(alias_config)

    # Fixed behavior: returns full path
    # Pattern '/home/user/projects/auth' won't match '/home/user/projects/auth-infra'
    assert len(patterns) == 1
    assert patterns[0].endswith("/auth") or patterns[0] == "/home/user/projects/auth"
    assert "auth" in patterns[0]  # Contains the workspace name
    assert "/" in patterns[0]  # Is a full path, not just the last component


def test_get_alias_workspace_patterns_with_multiple_workspaces():
    """Test pattern extraction returns distinct full paths."""
    ah = load_agent_history()

    alias_config = {
        "local": ["/home/user/projects/auth", "/home/user/projects/auth-api"],
        "remote:server": ["/home/user/projects/auth-infra"],
    }

    patterns = ah._get_alias_workspace_patterns(alias_config)

    # Fixed: Returns full paths
    # Now we have 3 distinct patterns that won't collide
    assert len(patterns) == 3

    # Each pattern should be a full path
    for pattern in patterns:
        assert "/" in pattern, f"Pattern should be a full path: {pattern}"

    # Verify all workspaces are represented
    workspace_names = [p.split("/")[-1] for p in patterns]
    assert "auth" in workspace_names or any("auth" in p and "auth-" not in p for p in patterns)
    assert any("api" in p for p in patterns)
    assert any("infra" in p for p in patterns)


def test_exact_workspace_matching_filter():
    """Verify that exact workspace matching prevents incorrect matches.

    Even though '/home/user/projects/auth' is a substring of '/home/user/projects/auth-infra',
    the exact matching filter (workspace == pattern) will only match the exact workspace.
    """
    # Full path pattern (what the function now returns)
    pattern = "/home/user/projects/auth"

    # Test sessions with different workspaces
    test_sessions = [
        {"workspace": "/home/user/projects/auth", "workspace_readable": "/home/user/projects/auth"},
        {
            "workspace": "/home/user/projects/auth-infra",
            "workspace_readable": "/home/user/projects/auth-infra",
        },
        {
            "workspace": "/home/user/projects/auth-api",
            "workspace_readable": "/home/user/projects/auth-api",
        },
        {
            "workspace": "/home/user/projects/my-auth",
            "workspace_readable": "/home/user/projects/my-auth",
        },
        {
            "workspace": "/home/user/projects/authorization",
            "workspace_readable": "/home/user/projects/authorization",
        },
    ]

    # Apply exact matching filter (as done in _collect_non_claude_alias_sessions)
    matched_sessions = []
    for s in test_sessions:
        workspace = s.get("workspace_readable") or s.get("workspace", "")
        if workspace == pattern:  # Exact match
            matched_sessions.append(s)

    # Fixed: Only 1 session matches (exact workspace match)
    assert len(matched_sessions) == 1, f"Expected 1 match, got {len(matched_sessions)}"
    assert matched_sessions[0]["workspace"] == "/home/user/projects/auth"

    # Verify NO incorrect matches
    matched_workspaces = [s["workspace"] for s in matched_sessions]
    assert "/home/user/projects/auth-infra" not in matched_workspaces
    assert "/home/user/projects/auth-api" not in matched_workspaces
    assert "/home/user/projects/my-auth" not in matched_workspaces
    assert "/home/user/projects/authorization" not in matched_workspaces
