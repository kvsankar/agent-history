"""WSL edge-case helper tests (ported from legacy)."""

from pathlib import Path

import pytest

from tests.helpers.module_loader import load_agent_history

pytestmark = pytest.mark.v1

module = load_agent_history()

is_wsl = module.is_running_in_wsl()
skip_unless_wsl = pytest.mark.skipif(not is_wsl, reason="WSL-only test")


def test_looks_like_windows_drive_basic():
    assert module._looks_like_windows_drive("C:/Users/test")  # noqa: SLF001
    assert module._looks_like_windows_drive("D:\\Projects")  # noqa: SLF001
    assert not module._looks_like_windows_drive("/home/user")  # noqa: SLF001


def test_strip_wsl_unc_prefix_variants():
    assert module._strip_wsl_unc_prefix("//wsl.localhost/Ubuntu/home/user") == "/home/user"  # noqa: SLF001
    assert module._strip_wsl_unc_prefix("//wsl$/Ubuntu/home/user") == "/home/user"  # noqa: SLF001
    assert module._strip_wsl_unc_prefix("/home/user") == "/home/user"  # noqa: SLF001


def test_is_windows_encoded_path_detection():
    assert module._is_windows_encoded_path("C--Users-test-project")  # noqa: SLF001
    assert not module._is_windows_encoded_path("-home-user-project")  # noqa: SLF001


def test_is_wsl_unc_path_detection():
    assert module._is_wsl_unc_path(Path("//wsl.localhost/Ubuntu/home"))  # noqa: SLF001
    assert not module._is_wsl_unc_path(Path("/home/user"))  # noqa: SLF001


def test_projects_dir_from_wsl_unc():
    unc_path = "//wsl.localhost/Ubuntu/home/user/.claude/projects"
    result = module._projects_dir_from_wsl_unc(unc_path)  # noqa: SLF001
    assert isinstance(result, Path)


def test_normalize_windows_path_formatting():
    # Should normalize without raising; content depends on host
    normalized = module._normalize_windows_path("C--Users-test-project", verify_local=False)  # noqa: SLF001
    assert "Users" in normalized or "users" in normalized


@skip_unless_wsl
def test_get_windows_users_with_claude_returns_list():
    users = module.get_windows_users_with_claude()
    assert isinstance(users, list)


@skip_unless_wsl
def test_get_windows_home_from_wsl_safe():
    # May return None if no Windows home is available; just ensure no crash.
    home = module.get_windows_home_from_wsl()
    assert home is None or home.exists()
