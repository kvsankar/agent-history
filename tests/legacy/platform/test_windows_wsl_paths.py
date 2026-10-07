"""Windows and WSL path normalization helpers."""

import pytest

from tests.helpers.module_loader import load_agent_history

pytestmark = pytest.mark.v1


def test_convert_windows_path_to_encoded() -> None:
    """Windows paths should encode drive and separators correctly."""
    module = load_agent_history()
    assert (
        module._convert_windows_path_to_encoded("C:\\Users\\test\\project")
        == "C--Users-test-project"
    )
    assert module._convert_windows_path_to_encoded("D:/Projects/my-app") == "D--Projects-my-app"


def test_strip_wsl_unc_prefix() -> None:
    """UNC-style WSL paths should be normalized to POSIX paths."""
    module = load_agent_history()
    assert module._strip_wsl_unc_prefix("//wsl.localhost/Ubuntu/home/user") == "/home/user"
    assert module._strip_wsl_unc_prefix("//wsl$/Ubuntu/home/user") == "/home/user"
