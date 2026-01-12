"""Parity tests for CLI handler registration.

These tests assert that handlers exist for CLI verbs defined in the specs.
They are expected to fail until the missing handlers are implemented.
"""

from agent_history.cli.orchestrator import CommandOrchestrator


def test_required_handlers_are_registered():
    """All spec-defined verbs should have handlers registered."""
    orchestrator = CommandOrchestrator()
    dispatcher = orchestrator.dispatcher

    required = [
        ("session", "show"),
        ("ws", "show"),
        ("ws", "export"),
        ("ws", "stats"),
        ("home", "show"),
        ("home", "export"),
        ("home", "stats"),
        ("project", "add"),
        ("project", "remove"),
        ("project", "export"),
    ]

    missing = [pair for pair in required if dispatcher.get_handler(*pair) is None]

    assert not missing, f"Missing handlers: {missing}"
