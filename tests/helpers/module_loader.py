"""Utility to load the agent-history script as a Python module for unit tests."""

import importlib.machinery
import importlib.util
from types import ModuleType

from .cli import get_script_path


def load_agent_history() -> ModuleType:
    """Import the agent-history CLI script as a module."""
    script_path = get_script_path()
    loader = importlib.machinery.SourceFileLoader("agent_history", str(script_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise ImportError("Unable to build import spec for agent-history")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
