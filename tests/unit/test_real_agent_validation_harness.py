"""Tests for the opt-in real-agent validation harness."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_harness():
    script = Path(__file__).resolve().parents[2] / "scripts" / "real_agent_validation.py"
    spec = importlib.util.spec_from_file_location("real_agent_validation", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_requires_opt_in_unless_dry_run(monkeypatch) -> None:
    harness = _load_harness()

    monkeypatch.delenv("AGENT_HISTORY_REAL_AGENT_TESTS", raising=False)

    assert harness.main(["--agents", "codex"]) == 2
    assert harness.main(["--agents", "codex", "--dry-run"]) == 0


def test_codex_invocation_uses_isolated_home_and_persistent_rollout(tmp_path: Path) -> None:
    harness = _load_harness()

    invocation = harness.prepare_agent_invocation(
        "codex",
        tmp_path,
        base_env={"PATH": "/usr/bin", "CODEX_API_KEY": "sk-test-value"},
    )

    assert invocation.env["HOME"] == str(tmp_path / "codex" / "home")
    assert invocation.env["CODEX_HOME"] == str(tmp_path / "codex" / "codex-home")
    assert invocation.history_env["CODEX_HOME"] == invocation.env["CODEX_HOME"]
    assert "--ephemeral" not in invocation.command
    assert "--ask-for-approval" not in invocation.command
    assert invocation.command[:2] == ["codex", "exec"]
    assert "--sandbox" in invocation.command
    assert "read-only" in invocation.command
    assert str(tmp_path / "codex" / "codex-home" / "sessions") in invocation.session_globs[0]


def test_codex_invocation_can_copy_auth_without_user_settings(tmp_path: Path) -> None:
    harness = _load_harness()
    host_home = tmp_path / "host-home"
    (host_home / ".codex").mkdir(parents=True)
    (host_home / ".codex" / "auth.json").write_text('{"tokens":"redacted"}\n', encoding="utf-8")
    (host_home / ".codex" / "config.toml").write_text("model = 'custom'\n", encoding="utf-8")

    invocation = harness.prepare_agent_invocation(
        "codex",
        tmp_path / "run",
        base_env={"PATH": "/usr/bin", "HOME": str(host_home)},
        copy_auth_from_default=True,
    )

    assert invocation.auth_copied is True
    assert (tmp_path / "run" / "codex" / "codex-home" / "auth.json").exists()
    assert not (tmp_path / "run" / "codex" / "codex-home" / "config.toml").exists()


def test_claude_auth_copy_uses_non_bare_prompt_mode(tmp_path: Path) -> None:
    harness = _load_harness()
    host_home = tmp_path / "host-home"
    (host_home / ".claude").mkdir(parents=True)
    (host_home / ".claude" / ".credentials.json").write_text(
        '{"token":"redacted"}\n',
        encoding="utf-8",
    )

    invocation = harness.prepare_agent_invocation(
        "claude",
        tmp_path / "run",
        base_env={"PATH": "/usr/bin", "HOME": str(host_home)},
        copy_auth_from_default=True,
    )

    assert invocation.auth_copied is True
    assert "--bare" not in invocation.command
    assert (tmp_path / "run" / "claude" / "claude-config" / ".credentials.json").exists()


def test_pi_auth_copy_prefers_openai_codex_subscription_model(tmp_path: Path) -> None:
    harness = _load_harness()
    host_home = tmp_path / "host-home"
    (host_home / ".pi" / "agent").mkdir(parents=True)
    (host_home / ".pi" / "agent" / "auth.json").write_text(
        '{"openai-codex":{"type":"oauth","access":"redacted"}}\n',
        encoding="utf-8",
    )

    invocation = harness.prepare_agent_invocation(
        "pi",
        tmp_path / "run",
        base_env={"PATH": "/usr/bin", "HOME": str(host_home)},
        copy_auth_from_default=True,
    )

    assert invocation.auth_copied is True
    assert invocation.command[invocation.command.index("--model") + 1] == "openai-codex/gpt-5.5"


def test_gemini_invocation_uses_cli_home_dot_gemini_tmp(tmp_path: Path) -> None:
    harness = _load_harness()

    invocation = harness.prepare_agent_invocation(
        "gemini",
        tmp_path,
        base_env={"PATH": "/usr/bin", "GEMINI_API_KEY": "test-key"},
    )

    gemini_home = tmp_path / "gemini" / "gemini-home"
    assert invocation.env["GEMINI_CLI_HOME"] == str(gemini_home)
    assert invocation.history_env["GEMINI_CLI_HOME"] == str(gemini_home)
    assert str(gemini_home / ".gemini" / "tmp") in invocation.session_globs[0]
    assert (gemini_home / ".gemini" / "settings.json").exists()
    assert "GEMINI_SESSIONS_DIR" not in invocation.history_env


def test_gemini_cli_home_env_points_to_dot_gemini_tmp(monkeypatch, tmp_path: Path) -> None:
    from agent_history.backends.gemini import gemini_get_home_dir

    monkeypatch.delenv("GEMINI_SESSIONS_DIR", raising=False)
    monkeypatch.setenv("GEMINI_CLI_HOME", str(tmp_path / "gemini-home"))

    assert gemini_get_home_dir() == tmp_path / "gemini-home" / ".gemini" / "tmp"


def test_gemini_cli_home_accepts_direct_dot_gemini_dir(monkeypatch, tmp_path: Path) -> None:
    from agent_history.backends.gemini import gemini_get_home_dir

    monkeypatch.delenv("GEMINI_SESSIONS_DIR", raising=False)
    monkeypatch.setenv("GEMINI_CLI_HOME", str(tmp_path / ".gemini"))

    assert gemini_get_home_dir() == tmp_path / ".gemini" / "tmp"


def test_sanitize_text_redacts_paths_prompts_and_secret_like_values(tmp_path: Path) -> None:
    harness = _load_harness()
    root = tmp_path / "root"
    text = (
        f"{root}/codex/workspace contains "
        "Reply with exactly: agent-history codex persistence probe. "
        "Do not run commands, read files, edit files, or use web search. "
        "secret=sk-ant-abcdefghijklmnopqrstuvwxyz"
    )

    sanitized = harness.sanitize_text(text, {str(root): "/tmp/agent-history-real-agent"})

    assert str(root) not in sanitized
    assert "agent-history codex persistence probe" not in sanitized
    assert "sk-ant-" not in sanitized
    assert "[REDACTED_PROMPT]" in sanitized
    assert "[REDACTED_SECRET]" in sanitized


def test_sanitize_session_content_redacts_noisy_structured_fields(tmp_path: Path) -> None:
    harness = _load_harness()
    root = tmp_path / "root"
    content = "\n".join(
        [
            (
                '{"type":"session_meta","payload":{"base_instructions":{"text":"private '
                'instructions"},"cwd":"' + str(root) + '/workspace"}}'
            ),
            (
                '{"type":"response_item","payload":{"role":"developer","content":'
                '[{"type":"input_text","text":"developer context"}]}}'
            ),
            (
                '{"type":"response_item","payload":{"role":"assistant","content":'
                '[{"type":"output_text","text":"agent-history codex persistence probe",'
                '"textSignature":"sig"}],"responseId":"resp_test"}}'
            ),
        ]
    )

    sanitized = harness.sanitize_session_content(
        content,
        {str(root): "/tmp/agent-history-real-agent"},
    )

    assert "private instructions" not in sanitized
    assert "developer context" not in sanitized
    assert "agent-history codex persistence probe" not in sanitized
    assert str(root) not in sanitized
    assert "[REDACTED_BASE_INSTRUCTIONS]" in sanitized
    assert "[REDACTED_DEVELOPER_CONTEXT]" in sanitized
    assert "[REDACTED_ASSISTANT_TEXT]" in sanitized
    assert "resp_test" not in sanitized
    assert "sig" not in sanitized
    assert "[REDACTED_RESPONSEID]" in sanitized
    assert "[REDACTED_TEXTSIGNATURE]" in sanitized


def test_sanitize_session_content_redacts_gemini_thoughts() -> None:
    harness = _load_harness()
    content = (
        '{"messages":[{"type":"gemini","content":"agent-history gemini persistence probe.",'
        '"thoughts":[{"description":"hidden reasoning"}]}]}'
    )

    sanitized = harness.sanitize_session_content(content)

    assert "hidden reasoning" not in sanitized
    assert "agent-history gemini persistence probe" not in sanitized
    assert "[REDACTED_THOUGHT]" in sanitized
    assert "[REDACTED_ASSISTANT_TEXT]" in sanitized
