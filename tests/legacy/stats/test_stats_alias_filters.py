from __future__ import annotations

from tests.helpers.module_loader import load_agent_history


def test_expand_alias_to_conditions_includes_source(monkeypatch):
    """Alias expansion should constrain both workspace and source."""
    ah = load_agent_history()
    aliases = {
        "projects": {
            "proj": {
                "local": ["-home-user-proj"],
                "remote:vm": ["-home-user-proj"],
                "windows:user": ["C--Users-user-proj"],
                "wsl:Ubuntu": ["-home-user-proj"],
            }
        }
    }
    conds, params = ah._expand_alias_to_conditions("proj", aliases["projects"])  # type: ignore[attr-defined]
    assert any("source =" in c or "source LIKE" in c for c in conds)
    # Ensure params are paired workspace+source in order
    assert len(conds) == len(params) // 2 or len(conds) == len(params) // 2 + 1
