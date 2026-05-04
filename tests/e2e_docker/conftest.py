"""Fixtures for Docker-based E2E tests.

These tests run inside the test-runner Docker container.

Usage:
    # Option 1: Via docker compose directly
    cd docker
    docker compose up -d --build
    docker compose run --rm test-runner pytest tests/e2e_docker/ -v
    docker compose down -v

    # Option 2: Via pytest --docker flag (handles container lifecycle)
    uv run pytest --docker -v

    # Option 3: Test against legacy ah.py script
    AGENT_HISTORY_TEST_SCRIPT=v1 uv run pytest --docker -v
"""

import os
import subprocess
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.helpers.cli import get_script_path

# Mark all tests in this directory as e2e_docker
pytestmark = pytest.mark.e2e_docker


@pytest.fixture(scope="session")
def docker_env() -> Dict[str, Any]:
    """Get Docker environment configuration."""
    return {
        "node_alpha": os.environ.get("NODE_ALPHA", "node-alpha"),
        "node_beta": os.environ.get("NODE_BETA", "node-beta"),
        "alpha_users": os.environ.get("ALPHA_USERS", "alice,bob").split(","),
        "beta_users": os.environ.get("BETA_USERS", "charlie,dave").split(","),
    }


@pytest.fixture(scope="session")
def cli_path() -> Path:
    """Get path to agent-history CLI.

    Respects AGENT_HISTORY_TEST_SCRIPT environment variable to select
    between v2 (agent-history) and v1 (ah.py) implementations.
    """
    return get_script_path()


def run_cli(
    args: list,
    cli_path: Path = None,
    env: Dict[str, str] = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """Run agent-history CLI command.

    Args:
        args: CLI arguments (without the script name)
        cli_path: Path to agent-history script
        env: Additional environment variables
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess with stdout, stderr, returncode
    """
    if cli_path is None:
        cli_path = Path("/app/agent-history")

    cmd = ["python3", str(cli_path)] + args

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=run_env,
    )


def ssh_run(
    host: str,
    user: str,
    command: str,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """Run command on remote host via SSH.

    Args:
        host: SSH hostname (e.g., node-alpha)
        user: SSH username (e.g., alice)
        command: Command to execute remotely
        timeout: Command timeout in seconds

    Returns:
        CompletedProcess with stdout, stderr, returncode
    """
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        f"{user}@{host}",
        command,
    ]

    return subprocess.run(
        ssh_cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.fixture
def cli_runner(docker_env, cli_path):
    """Factory fixture for running CLI commands."""
    def _run(args: list, env: Dict = None, timeout: int = 30) -> subprocess.CompletedProcess:
        return run_cli(args, cli_path, env, timeout)

    return _run


@pytest.fixture
def run_remote_cli(docker_env, cli_path):
    """Factory fixture for running CLI with remote host.

    Returns a function that runs agent-history with -r flag.
    """
    def _run(args: list, user: str, host: str = None, env: Dict = None) -> subprocess.CompletedProcess:
        if host is None:
            host = docker_env["node_alpha"]
        remote_args = ["-r", f"{user}@{host}"] + args
        return run_cli(remote_args, cli_path, env)

    return _run


@pytest.fixture
def ssh_to_alpha(docker_env):
    """Factory fixture for SSH to node-alpha."""
    def _ssh(user: str, command: str) -> subprocess.CompletedProcess:
        return ssh_run(docker_env["node_alpha"], user, command)
    return _ssh


@pytest.fixture
def ssh_to_beta(docker_env):
    """Factory fixture for SSH to node-beta."""
    def _ssh(user: str, command: str) -> subprocess.CompletedProcess:
        return ssh_run(docker_env["node_beta"], user, command)
    return _ssh


@pytest.fixture
def alice_remote(docker_env) -> str:
    """Get alice@node-alpha remote string."""
    return f"alice@{docker_env['node_alpha']}"


@pytest.fixture
def bob_remote(docker_env) -> str:
    """Get bob@node-alpha remote string."""
    return f"bob@{docker_env['node_alpha']}"


@pytest.fixture
def charlie_remote(docker_env) -> str:
    """Get charlie@node-beta remote string."""
    return f"charlie@{docker_env['node_beta']}"


@pytest.fixture
def dave_remote(docker_env) -> str:
    """Get dave@node-beta remote string."""
    return f"dave@{docker_env['node_beta']}"
