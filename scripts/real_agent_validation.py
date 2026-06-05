#!/usr/bin/env python3
"""Create and validate real coding-agent sessions in isolated temp directories.

This script is intentionally opt-in. It launches installed agent CLIs only when
AGENT_HISTORY_REAL_AGENT_TESTS=1 is set, then points agent-history at the temp
session roots it created.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_HISTORY_SCRIPT = REPO_ROOT / "agent-history"
OPT_IN_ENV = "AGENT_HISTORY_REAL_AGENT_TESTS"
DEFAULT_AGENTS = ("claude", "codex", "gemini", "pi")

PROMPTS = {
    "claude": "Reply with exactly: agent-history claude persistence probe. Do not use tools.",
    "codex": (
        "Reply with exactly: agent-history codex persistence probe. "
        "Do not run commands, read files, edit files, or use web search."
    ),
    "gemini": "Reply with exactly: agent-history gemini persistence probe. Do not use tools.",
    "pi": "Reply with exactly: agent-history pi persistence probe. Do not use tools.",
}

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_-]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"\bmsg_[A-Za-z0-9_]+\b"),
    re.compile(r"\breq_[A-Za-z0-9_]+\b"),
    re.compile(r"\bresp_[A-Za-z0-9_]+\b"),
)
PROBE_RESPONSE_PATTERN = re.compile(
    r"agent-\s*history\s+(claude|codex|gemini|pi)\s+persistence\s+probe\.?",
    re.IGNORECASE,
)


@dataclass
class AgentInvocation:
    """Prepared command and validation context for one real-agent run."""

    agent: str
    command: list[str]
    env: dict[str, str]
    history_env: dict[str, str]
    workspace: Path
    session_globs: list[str]
    required_any_env: tuple[str, ...]
    auth_copied: bool = False


@dataclass
class AgentResult:
    """Result summary for one real-agent validation."""

    agent: str
    status: str
    session_files: list[Path]
    message: str = ""


def parse_agents(value: str) -> list[str]:
    """Parse a comma-separated agent list."""
    if value == "all":
        return list(DEFAULT_AGENTS)
    agents = [agent.strip() for agent in value.split(",") if agent.strip()]
    invalid = sorted(set(agents) - set(DEFAULT_AGENTS))
    if invalid:
        raise ValueError(f"unsupported agent(s): {', '.join(invalid)}")
    return agents


def _base_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    # Keep subprocesses independent from external direct session overrides.
    for key in (
        "CLAUDE_PROJECTS_DIR",
        "CODEX_SESSIONS_DIR",
        "GEMINI_SESSIONS_DIR",
        "PI_SESSIONS_DIR",
        "PI_CODING_AGENT_SESSION_DIR",
        "AGENT_HISTORY_HOME",
        "AGENT_HISTORY_HOME_WSL",
        "AGENT_HISTORY_HOME_WINDOWS",
    ):
        env.pop(key, None)
    return env


def _mkdirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def _write_workspace_fixture(workspace: Path, agent: str) -> None:
    _mkdirs(workspace)
    (workspace / "README.md").write_text(
        f"agent-history real-session validation fixture for {agent}\n",
        encoding="utf-8",
    )


def _host_home(base_env: dict[str, str] | None = None) -> Path:
    if base_env and base_env.get("HOME"):
        return Path(base_env["HOME"]).expanduser()
    return Path.home()


def _copy_file(src: Path, dst: Path) -> bool:
    if not src.exists() or not src.is_file():
        return False
    _mkdirs(dst.parent)
    shutil.copy2(src, dst)
    return True


def _looks_nonempty_auth_file(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        return path.stat().st_size > 0
    except OSError:
        return False
    return bool(content and content != "{}")


def _auth_file_has_provider(path: Path, provider: str) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False
    return isinstance(data, dict) and provider in data


def _copy_default_auth_files(
    agent: str,
    target_root: Path,
    base_env: dict[str, str] | None = None,
) -> bool:
    """Copy only default auth files into the isolated agent root."""
    home = _host_home(base_env)
    copied: list[Path] = []

    if agent == "claude":
        dst = target_root / ".credentials.json"
        if _copy_file(home / ".claude" / ".credentials.json", dst):
            copied.append(dst)
    elif agent == "codex":
        dst = target_root / "auth.json"
        if _copy_file(home / ".codex" / "auth.json", dst):
            copied.append(dst)
    elif agent == "gemini":
        gemini_root = target_root / ".gemini"
        for name in ("oauth_creds.json", "google_accounts.json"):
            dst = gemini_root / name
            if _copy_file(home / ".gemini" / name, dst):
                copied.append(dst)
    elif agent == "pi":
        dst = target_root / "auth.json"
        if _copy_file(home / ".pi" / "agent" / "auth.json", dst):
            copied.append(dst)

    return any(_looks_nonempty_auth_file(path) for path in copied)


def prepare_agent_invocation(
    agent: str,
    root: Path,
    base_env: dict[str, str] | None = None,
    copy_auth_from_default: bool = False,
) -> AgentInvocation:
    """Create isolated directories and command metadata for one agent."""
    if agent not in DEFAULT_AGENTS:
        raise ValueError(f"unsupported agent: {agent}")

    env = _base_env(base_env)
    home = root / agent / "home"
    workspace = root / agent / "workspace"
    config_dir = root / agent / "agent-history-config"
    _write_workspace_fixture(workspace, agent)
    _mkdirs(home, config_dir)

    history_env = {
        "HOME": str(home),
        "AGENT_HISTORY_CONFIG_DIR": str(config_dir),
        "AGENT_HISTORY_TEST_MODE": "1",
    }

    prompt = PROMPTS[agent]

    if agent == "claude":
        claude_config = root / agent / "claude-config"
        _mkdirs(claude_config)
        auth_copied = (
            _copy_default_auth_files(agent, claude_config, base_env)
            if copy_auth_from_default
            else False
        )
        session_id = str(uuid.uuid4())
        env.update(
            {
                "HOME": str(home),
                "CLAUDE_CONFIG_DIR": str(claude_config),
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "DISABLE_TELEMETRY": "1",
                "DO_NOT_TRACK": "1",
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
            }
        )
        history_env.update(
            {
                "CLAUDE_PROJECTS_DIR": str(claude_config / "projects"),
            }
        )
        return AgentInvocation(
            agent=agent,
            command=[
                "claude",
                "-p",
                "--session-id",
                session_id,
                "--output-format",
                "json",
                "--max-turns",
                "1",
                "--tools",
                "",
                "--permission-mode",
                "dontAsk",
                prompt,
            ],
            env=env,
            history_env=history_env,
            workspace=workspace,
            session_globs=[str(claude_config / "projects" / "**" / f"{session_id}.jsonl")],
            required_any_env=("ANTHROPIC_API_KEY",),
            auth_copied=auth_copied,
        )

    if agent == "codex":
        codex_home = root / agent / "codex-home"
        _mkdirs(codex_home)
        auth_copied = (
            _copy_default_auth_files(agent, codex_home, base_env)
            if copy_auth_from_default
            else False
        )
        env.update({"HOME": str(home), "CODEX_HOME": str(codex_home)})
        history_env.update({"CODEX_HOME": str(codex_home)})
        return AgentInvocation(
            agent=agent,
            command=[
                "codex",
                "exec",
                "--cd",
                str(workspace),
                "--sandbox",
                "read-only",
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "--json",
                prompt,
            ],
            env=env,
            history_env=history_env,
            workspace=workspace,
            session_globs=[
                str(codex_home / "sessions" / "**" / "rollout-*.jsonl"),
                str(codex_home / "sessions" / "**" / "rollout-*.jsonl.zst"),
            ],
            required_any_env=("CODEX_API_KEY", "OPENAI_API_KEY"),
            auth_copied=auth_copied,
        )

    if agent == "gemini":
        gemini_cli_home = root / agent / "gemini-home"
        gemini_settings = gemini_cli_home / ".gemini" / "settings.json"
        _mkdirs(gemini_settings.parent)
        auth_copied = (
            _copy_default_auth_files(agent, gemini_cli_home, base_env)
            if copy_auth_from_default
            else False
        )
        gemini_settings.write_text(
            json.dumps(
                {
                    "privacy": {"usageStatisticsEnabled": False},
                    "tools": {"core": []},
                    "mcp": {"servers": {}},
                    "security": {
                        "auth": {"selectedType": "oauth-personal"} if auth_copied else {},
                        "disableYoloMode": True,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        env.update({"HOME": str(home), "GEMINI_CLI_HOME": str(gemini_cli_home)})
        history_env.update({"GEMINI_CLI_HOME": str(gemini_cli_home)})
        return AgentInvocation(
            agent=agent,
            command=[
                "gemini",
                "-p",
                prompt,
                "--model",
                env.get("AGENT_HISTORY_GEMINI_MODEL", "gemini-2.5-flash"),
                "--output-format",
                "json",
                "--approval-mode",
                "default",
                "--extensions",
                "none",
            ],
            env=env,
            history_env=history_env,
            workspace=workspace,
            session_globs=[
                str(gemini_cli_home / ".gemini" / "tmp" / "**" / "session-*.jsonl"),
                str(gemini_cli_home / ".gemini" / "tmp" / "**" / "session-*.json"),
            ],
            required_any_env=(
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "GOOGLE_APPLICATION_CREDENTIALS",
                "GOOGLE_GENAI_USE_VERTEXAI",
            ),
            auth_copied=auth_copied,
        )

    pi_agent_dir = root / agent / "pi-agent"
    _mkdirs(pi_agent_dir)
    auth_copied = (
        _copy_default_auth_files(agent, pi_agent_dir, base_env) if copy_auth_from_default else False
    )
    pi_model = env.get("AGENT_HISTORY_PI_MODEL", "openai/gpt-4o-mini")
    if (
        "AGENT_HISTORY_PI_MODEL" not in env
        and auth_copied
        and _auth_file_has_provider(pi_agent_dir / "auth.json", "openai-codex")
    ):
        pi_model = "openai-codex/gpt-5.5"
    env.update(
        {
            "HOME": str(home),
            "PI_CODING_AGENT_DIR": str(pi_agent_dir),
            "PI_OFFLINE": "1",
            "PI_TELEMETRY": "0",
        }
    )
    history_env.update({"PI_CODING_AGENT_DIR": str(pi_agent_dir)})
    return AgentInvocation(
        agent=agent,
        command=[
            "pi",
            "--model",
            pi_model,
            "--thinking",
            "off",
            "--no-tools",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-context-files",
            "--name",
            "agent-history pi smoke",
            "-p",
            prompt,
        ],
        env=env,
        history_env=history_env,
        workspace=workspace,
        session_globs=[str(pi_agent_dir / "sessions" / "**" / "*.jsonl")],
        required_any_env=("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"),
        auth_copied=auth_copied,
    )


def missing_requirements(invocation: AgentInvocation) -> list[str]:
    """Return missing CLI/auth requirements for an invocation."""
    missing = []
    if shutil.which(invocation.command[0], path=invocation.env.get("PATH")) is None:
        missing.append(f"missing executable: {invocation.command[0]}")
    if (
        invocation.required_any_env
        and not any(invocation.env.get(name) for name in invocation.required_any_env)
        and not invocation.auth_copied
    ):
        missing.append("missing one of: " + ", ".join(invocation.required_any_env))
    return missing


def find_session_files(invocation: AgentInvocation) -> list[Path]:
    """Find session files created by an agent invocation."""
    files = []
    for pattern in invocation.session_globs:
        files.extend(Path(path) for path in sorted(glob.glob(pattern, recursive=True)))
    return sorted(set(files))


def run_command(
    command: Sequence[str],
    env: dict[str, str],
    cwd: Path | None,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """Run a command with captured output."""
    return subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _agent_history_env(invocation: AgentInvocation) -> dict[str, str]:
    env = _base_env(invocation.env)
    env.update(invocation.history_env)
    return env


def validate_with_agent_history(
    invocation: AgentInvocation,
    export_dir: Path,
    timeout: int,
) -> None:
    """Validate list/export/stats against the captured isolated session root."""
    env = _agent_history_env(invocation)
    commands = [
        [
            sys.executable,
            str(AGENT_HISTORY_SCRIPT),
            "--agent",
            invocation.agent,
            "session",
            "list",
            str(invocation.workspace),
            "--format",
            "json",
        ],
        [
            sys.executable,
            str(AGENT_HISTORY_SCRIPT),
            "--agent",
            invocation.agent,
            "session",
            "export",
            str(invocation.workspace),
            str(export_dir),
            "--json",
            "--force",
            "--quiet",
        ],
        [
            sys.executable,
            str(AGENT_HISTORY_SCRIPT),
            "--agent",
            invocation.agent,
            "session",
            "stats",
            str(invocation.workspace),
            "--no-sync",
            "--format",
            "json",
        ],
    ]
    for command in commands:
        result = run_command(command, env=env, cwd=REPO_ROOT, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(
                "agent-history validation failed: "
                + " ".join(command)
                + f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )


def sanitize_text(text: str, replacements: dict[str, str] | None = None) -> str:
    """Redact local paths, known prompts, and secret-like values from text."""
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    for prompt in PROMPTS.values():
        sanitized = sanitized.replace(prompt, "[REDACTED_PROMPT]")
    sanitized = PROBE_RESPONSE_PATTERN.sub("[REDACTED_ASSISTANT_TEXT]", sanitized)
    for raw, redacted in (replacements or {}).items():
        if raw:
            sanitized = sanitized.replace(raw, redacted)
    return sanitized


def _sanitize_json_value(value: object, replacements: dict[str, str]) -> object:
    """Redact sensitive/noisy values inside parsed session JSON."""
    if isinstance(value, str):
        return sanitize_text(value, replacements)
    if isinstance(value, list):
        return [_sanitize_json_value(item, replacements) for item in value]
    if not isinstance(value, dict):
        return value

    sanitized = {key: _sanitize_json_value(item, replacements) for key, item in value.items()}

    for key in ("access", "refresh", "accountId", "requestId", "responseId", "textSignature"):
        if key in sanitized:
            sanitized[key] = f"[REDACTED_{key.upper()}]"

    base_instructions = sanitized.get("base_instructions")
    if isinstance(base_instructions, dict) and "text" in base_instructions:
        base_instructions["text"] = "[REDACTED_BASE_INSTRUCTIONS]"

    payload = sanitized.get("payload")
    if isinstance(payload, dict):
        payload_base_instructions = payload.get("base_instructions")
        if isinstance(payload_base_instructions, dict) and "text" in payload_base_instructions:
            payload_base_instructions["text"] = "[REDACTED_BASE_INSTRUCTIONS]"
        if payload.get("role") == "developer":
            payload["content"] = [{"type": "input_text", "text": "[REDACTED_DEVELOPER_CONTEXT]"}]

    if sanitized.get("role") == "developer":
        sanitized["content"] = [{"type": "input_text", "text": "[REDACTED_DEVELOPER_CONTEXT]"}]

    thoughts = sanitized.get("thoughts")
    if isinstance(thoughts, list):
        for thought in thoughts:
            if isinstance(thought, dict) and "description" in thought:
                thought["description"] = "[REDACTED_THOUGHT]"

    return sanitized


def sanitize_session_content(content: str, replacements: dict[str, str] | None = None) -> str:
    """Redact session content while preserving JSON/JSONL structure."""
    replacements = replacements or {}
    stripped = content.lstrip()
    if stripped.startswith("{") and "\n{" not in stripped:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return sanitize_text(content, replacements)
        return json.dumps(_sanitize_json_value(parsed, replacements), indent=2) + "\n"

    lines = []
    parsed_any_jsonl = False
    for line in content.splitlines():
        if not line.strip():
            lines.append(line)
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            lines.append(sanitize_text(line, replacements))
            continue
        parsed_any_jsonl = True
        lines.append(json.dumps(_sanitize_json_value(parsed, replacements), separators=(",", ":")))

    if parsed_any_jsonl:
        return "\n".join(lines) + ("\n" if content.endswith("\n") else "")
    return sanitize_text(content, replacements)


def write_sanitized_sessions(
    invocation: AgentInvocation,
    session_files: Iterable[Path],
    output_dir: Path,
    root: Path,
) -> list[Path]:
    """Write redacted copies of captured session files."""
    agent_dir = output_dir / invocation.agent
    agent_dir.mkdir(parents=True, exist_ok=True)
    replacements = {
        str(root): "/tmp/agent-history-real-agent",
        str(invocation.workspace): "/tmp/agent-history-real-agent/workspace",
    }
    written = []
    for index, session_file in enumerate(session_files, start=1):
        suffix = "".join(session_file.suffixes) or ".txt"
        target = agent_dir / f"session-{index:02d}{suffix}"
        content = session_file.read_text(encoding="utf-8", errors="replace")
        target.write_text(sanitize_session_content(content, replacements), encoding="utf-8")
        written.append(target)
    return written


def run_agent_validation(
    invocation: AgentInvocation,
    root: Path,
    timeout: int,
    sanitized_output_dir: Path | None = None,
) -> AgentResult:
    """Run one real agent and validate the captured sessions."""
    result = run_command(
        invocation.command, env=invocation.env, cwd=invocation.workspace, timeout=timeout
    )
    if result.returncode != 0:
        return AgentResult(
            agent=invocation.agent,
            status="failed",
            session_files=[],
            message=f"agent command failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    session_files = find_session_files(invocation)
    if not session_files:
        return AgentResult(
            agent=invocation.agent,
            status="failed",
            session_files=[],
            message="agent completed but no session file was created",
        )

    try:
        validate_with_agent_history(invocation, root / invocation.agent / "exports", timeout)
    except RuntimeError as err:
        return AgentResult(
            agent=invocation.agent,
            status="failed",
            session_files=session_files,
            message=str(err),
        )

    if sanitized_output_dir is not None:
        write_sanitized_sessions(invocation, session_files, sanitized_output_dir, root)

    return AgentResult(agent=invocation.agent, status="passed", session_files=session_files)


def _print_dry_run(invocation: AgentInvocation) -> None:
    print(f"\n[{invocation.agent}]")
    print("workspace:", invocation.workspace)
    print("command:", " ".join(invocation.command))
    print("history env:")
    for key in sorted(invocation.history_env):
        print(f"  {key}={invocation.history_env[key]}")
    print("session globs:")
    for pattern in invocation.session_globs:
        print(f"  {pattern}")
    print("auth copied:", "yes" if invocation.auth_copied else "no")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agents",
        default="all",
        help="Comma-separated agents to run: claude,codex,gemini,pi or all",
    )
    parser.add_argument("--timeout", type=int, default=180, help="Timeout per command in seconds")
    parser.add_argument("--keep-temp", action="store_true", help="Keep the temp root after running")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without launching agents"
    )
    parser.add_argument(
        "--skip-unavailable",
        action="store_true",
        help="Skip agents with missing CLIs or credentials instead of failing",
    )
    parser.add_argument(
        "--sanitized-output-dir",
        type=Path,
        help="Optional directory for redacted copies of captured real sessions",
    )
    parser.add_argument(
        "--copy-auth-from-default",
        action="store_true",
        help=(
            "Copy only agent auth files from default homes into isolated temp homes. "
            "Does not copy sessions, history, projects, settings, or raw inputs."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        agents = parse_agents(args.agents)
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    if not args.dry_run and os.environ.get(OPT_IN_ENV) != "1":
        print(
            f"error: set {OPT_IN_ENV}=1 to launch real agent CLIs, or use --dry-run",
            file=sys.stderr,
        )
        return 2

    temp_dir = tempfile.TemporaryDirectory(prefix="agent-history-real-agents-")
    root = Path(temp_dir.name)
    results = []
    try:
        for agent in agents:
            invocation = prepare_agent_invocation(
                agent,
                root,
                copy_auth_from_default=args.copy_auth_from_default,
            )
            if args.dry_run:
                _print_dry_run(invocation)
                continue

            missing = missing_requirements(invocation)
            if missing:
                message = "; ".join(missing)
                if args.skip_unavailable:
                    results.append(
                        AgentResult(
                            agent=agent, status="skipped", session_files=[], message=message
                        )
                    )
                    continue
                print(f"{agent}: {message}", file=sys.stderr)
                return 2

            print(f"running {agent} in {invocation.workspace}")
            results.append(
                run_agent_validation(
                    invocation,
                    root=root,
                    timeout=args.timeout,
                    sanitized_output_dir=args.sanitized_output_dir,
                )
            )

        if args.dry_run:
            return 0

        failed = False
        for result in results:
            sessions = ", ".join(str(path) for path in result.session_files) or "none"
            print(f"{result.agent}: {result.status}; sessions: {sessions}")
            if result.message:
                print(result.message)
            failed = failed or result.status == "failed"
        return 1 if failed else 0
    finally:
        if args.keep_temp:
            print(f"temp root kept: {root}")
        else:
            temp_dir.cleanup()


if __name__ == "__main__":
    sys.exit(main())
