"""Utility to load the agent-history script as a Python module for unit tests."""

import importlib.machinery
import importlib.util
from types import ModuleType

from .cli import get_module_path


def load_agent_history() -> ModuleType:
    """Import the old monolithic agent-history script (ah.py) as a module.

    This is used by v1 unit tests that need access to internal functions
    like is_running_in_wsl(), _looks_like_windows_drive(), etc.
    """
    script_path = get_module_path()
    loader = importlib.machinery.SourceFileLoader("agent_history", str(script_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise ImportError("Unable to build import spec for ah.py")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
