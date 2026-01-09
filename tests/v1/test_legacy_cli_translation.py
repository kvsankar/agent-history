"""Tests for legacy CLI argument translation to the new noun-verb form."""

from tests.legacy.legacy_cli import translate_legacy_args


def test_export_maps_to_session_export():
    args = translate_legacy_args(["export", "proj", "-o", "/tmp/out"])
    assert args == ["session", "export", "proj", "-o", "/tmp/out"]


def test_stats_maps_to_session_stats():
    args = translate_legacy_args(["stats", "--aw"])
    assert args == ["session", "stats", "--aw"]


def test_lss_defaults_to_claude_and_legacy_format():
    args = translate_legacy_args(["lss", "foo"])
    assert args == ["--agent", "claude", "session", "--legacy-format", "foo"]


def test_lss_respects_explicit_agent():
    args = translate_legacy_args(["--agent", "codex", "lss", "foo"])
    assert args == ["--agent", "codex", "session", "--legacy-format", "foo"]


def test_lsw_defaults_to_claude():
    args = translate_legacy_args(["lsw", "--aw"])
    assert args == ["--agent", "claude", "ws", "--aw"]


def test_lsw_respects_explicit_agent():
    args = translate_legacy_args(["--agent", "gemini", "lsw"])
    assert args == ["--agent", "gemini", "ws"]


def test_out_flag_maps_to_output():
    args = translate_legacy_args(["export", "--out", "/tmp/out"])
    assert args == ["session", "export", "-o", "/tmp/out"]


def test_passthrough_for_other_commands():
    args = translate_legacy_args(["project", "list"])
    assert args == ["project", "list"]


def test_empty_args_returns_empty_list():
    assert translate_legacy_args([]) == []
