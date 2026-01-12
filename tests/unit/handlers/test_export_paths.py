"""Export path handling tests."""

from pathlib import Path

from agent_history.handlers.export import SessionExportHandler


def test_workspace_hash_sanitized_for_output(tmp_path: Path) -> None:
    handler = SessionExportHandler()
    ws_path = handler._get_workspace_output_path(tmp_path, "[hash:4391478e]", flat=False)

    assert ws_path.name == "[hash_4391478e]"
    assert ws_path.exists()


def test_windows_workspace_path_split_into_segments(tmp_path: Path) -> None:
    handler = SessionExportHandler()
    ws_path = handler._get_workspace_output_path(tmp_path, r"C:\\Users\\Alice\\Proj", flat=False)

    assert ws_path == tmp_path / "C" / "Users" / "Alice" / "Proj"
    assert ws_path.exists()
