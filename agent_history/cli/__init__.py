"""CLI components for agent-history.

This package provides command line interface components:
- CLIParser: Argument parsing and CommandRequest building
- CommandOrchestrator: Full pipeline coordination
- main: Entry point function
"""

from agent_history.cli.orchestrator import CommandOrchestrator, main
from agent_history.cli.parser import CLIParser

__all__ = [
    "CLIParser",
    "CommandOrchestrator",
    "main",
]
