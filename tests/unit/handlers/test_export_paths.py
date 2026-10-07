"""Export path handling tests."""

from pathlib import Path

from agent_history.cli.constants import (
    EXPORT_LAYOUT_FLAT,
    EXPORT_LAYOUT_SQUASHED,
    EXPORT_LAYOUT_TREE,
)
from agent_history.handlers.export import SessionExportHandler


def test_workspace_hash_sanitized_for_output(tmp_path: Path) -> None:
    handler = SessionExportHandler()
    ws_path = handler._get_workspace_output_path(tmp_path, "[hash:4391478e]", flat=False)

    assert ws_path.name == "[hash_4391478e]"
    assert ws_path.exists()


def test_windows_workspace_path_split_into_segments(tmp_path: Path) -> None:
    handler = SessionExportHandler()
    ws_path = handler._get_workspace_output_path(
        tmp_path,
        r"C:\\Users\\Alice\\Proj",
        flat=False,
        layout=EXPORT_LAYOUT_TREE,
    )

    assert ws_path == tmp_path / "C" / "Users" / "Alice" / "Proj"
    assert ws_path.exists()


def test_squashed_workspace_path_uses_claude_style_name(tmp_path: Path) -> None:
    handler = SessionExportHandler()
    ws_path = handler._get_workspace_output_path(
        tmp_path,
        "/home/Alice/My Project",
        layout=EXPORT_LAYOUT_SQUASHED,
    )

    assert ws_path == tmp_path / "-home-Alice-My Project"
    assert ws_path.exists()


def test_squashed_workspace_path_decodes_existing_claude_name(tmp_path: Path) -> None:
    handler = SessionExportHandler()
    ws_path = handler._get_workspace_output_path(
        tmp_path,
        "-home-Alice-My Project",
        layout=EXPORT_LAYOUT_SQUASHED,
    )

    assert ws_path == tmp_path / "-home-Alice-My Project"
    assert ws_path.exists()


def test_layout_flat_writes_to_output_root(tmp_path: Path) -> None:
    handler = SessionExportHandler()
    ws_path = handler._get_workspace_output_path(
        tmp_path,
        "/home/Alice/My Project",
        layout=EXPORT_LAYOUT_FLAT,
    )

    assert ws_path == tmp_path
