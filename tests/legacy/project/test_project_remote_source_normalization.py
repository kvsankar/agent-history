from __future__ import annotations

from tests.helpers.module_loader import load_agent_history


def test_remote_alias_matches_hostname():
    """@project pattern should match remote sources even if alias includes user@host."""
    ah = load_agent_history()
    conds, params = ah._expand_alias_to_conditions(  # type: ignore[attr-defined]
        "proj",
        {"proj": {"remote:sankar@ubuntuvm01": ["-home-user-proj"]}},
    )
    # Expect workspace condition with both user@host and host-only sources
    assert "(s.workspace = ? AND s.source IN (?,?))" in conds[0]
    assert params[0] == "user-proj"
    assert "remote:sankar@ubuntuvm01" in params
    assert "remote:ubuntuvm01" in params
