"""Repeatable --home handling."""

from agent_history.scope.context import ResolutionContext, ScopeArgs
from agent_history.scope.resolver import ScopeResolver
from agent_history.scope.types import HomeSpecConcrete


def test_multiple_home_names_should_not_drop_extra_values():
    """Repeatable --home values should not be collapsed to the first entry."""
    context = ResolutionContext()
    resolver = ScopeResolver(context)

    args = ScopeArgs(home_names=["local", "remote:vm01"], all_workspaces=True)
    home_spec = resolver._build_home_spec(args)

    assert not isinstance(
        home_spec, HomeSpecConcrete
    ), "Expected multiple homes to be preserved"
