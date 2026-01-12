"""WorkspaceRef normalization tests."""

from agent_history.utils.workspace_ref import build_workspace_ref


def test_encoded_workspace_ref_decodes() -> None:
    ref = build_workspace_ref("-home-user-project")
    assert ref.key == "/home/user/project"
    assert ref.display == "/home/user/project"
    assert ref.kind.value == "encoded"


def test_cached_workspace_ref_decodes() -> None:
    ref = build_workspace_ref("remote_vm01_-home-user-project")
    assert ref.key == "/home/user/project"
    assert ref.display == "/home/user/project"
    assert ref.kind.value == "cached"


def test_hash_workspace_ref_uses_raw_key() -> None:
    raw = "a1b2c3d4e5f67890a1b2c3d4e5f67890"
    ref = build_workspace_ref(raw)
    assert ref.key == raw
    assert ref.display == "[hash:a1b2c3d4]"
    assert ref.kind.value == "hash"


def test_windows_path_workspace_ref_normalizes() -> None:
    ref = build_workspace_ref(r"C:\\Users\\Alice\\Proj")
    assert ref.key == "C:/Users/Alice/Proj"
    assert ref.display == "C:/Users/Alice/Proj"
    assert ref.kind.value == "path"


def test_readable_path_overrides_raw_hash() -> None:
    raw = "abcdefabcdefabcdefabcdefabcdefab"
    ref = build_workspace_ref(raw, readable="/home/user/project")
    assert ref.key == "/home/user/project"
    assert ref.display == "/home/user/project"
    assert ref.kind.value == "hash"
