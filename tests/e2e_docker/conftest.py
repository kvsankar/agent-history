"""Fixtures and helpers for Docker-based E2E tests.

These tests run inside the test-runner container and execute the agent-history
CLI against real SSH nodes (node-alpha and node-beta).

Environment variables (set by docker-compose):
    NODE_ALPHA: Hostname of first SSH node (default: node-alpha)
    NODE_BETA: Hostname of second SSH node (default: node-beta)
    ALPHA_USERS: Comma-separated users on node-alpha (default: alice,bob)
    BETA_USERS: Comma-separated users on node-beta (default: charlie,dave)
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Path to the agent-history script
SCRIPT_PATH = Path("/app/agent-history")


def get_env():
    """Get environment configuration from docker-compose."""
    return {
        "node_alpha": os.environ.get("NODE_ALPHA", "node-alpha"),
        "node_beta": os.environ.get("NODE_BETA", "node-beta"),
        "alpha_users": os.environ.get("ALPHA_USERS", "alice,bob").split(","),
        "beta_users": os.environ.get("BETA_USERS", "charlie,dave").split(","),
    }


def run_cli(args, timeout=30, env=None):
    """Run the agent-history CLI and return the result.

    Args:
        args: List of command-line arguments
        timeout: Command timeout in seconds
        env: Optional environment overrides

    Returns:
        subprocess.CompletedProcess with stdout, stderr, returncode
    """
    cmd = [sys.executable, str(SCRIPT_PATH), *args]

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=run_env,
        check=False,
    )


def ssh_run(user, host, command, timeout=30):
    """Run a command on a remote host via SSH.

    Args:
        user: Remote username
        host: Remote hostname
        command: Command to execute
        timeout: SSH timeout in seconds

    Returns:
        subprocess.CompletedProcess
    """
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        f"{user}@{host}",
        command,
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@pytest.fixture(scope="session")
def env_config():
    """Get Docker environment configuration."""
    return get_env()


@pytest.fixture(scope="session")
def node_alpha(env_config):
    """Return node-alpha hostname."""
    return env_config["node_alpha"]


@pytest.fixture(scope="session")
def node_beta(env_config):
    """Return node-beta hostname."""
    return env_config["node_beta"]


@pytest.fixture(scope="session")
def alpha_users(env_config):
    """Return list of users on node-alpha."""
    return env_config["alpha_users"]


@pytest.fixture(scope="session")
def beta_users(env_config):
    """Return list of users on node-beta."""
    return env_config["beta_users"]


@pytest.fixture(scope="session")
def alice(node_alpha):
    """Return alice@node-alpha remote spec."""
    return f"alice@{node_alpha}"


@pytest.fixture(scope="session")
def bob(node_alpha):
    """Return bob@node-alpha remote spec."""
    return f"bob@{node_alpha}"


@pytest.fixture(scope="session")
def charlie(node_beta):
    """Return charlie@node-beta remote spec."""
    return f"charlie@{node_beta}"


@pytest.fixture(scope="session")
def dave(node_beta):
    """Return dave@node-beta remote spec."""
    return f"dave@{node_beta}"


@pytest.fixture(scope="session")
def verify_ssh_connectivity(alice, charlie):
    """Verify SSH connectivity to all nodes before running tests."""
    # Test connection to alice on node-alpha
    result = ssh_run("alice", "node-alpha", "echo ok")
    if result.returncode != 0:
        pytest.skip(f"Cannot SSH to alice@node-alpha: {result.stderr}")

    # Test connection to charlie on node-beta
    result = ssh_run("charlie", "node-beta", "echo ok")
    if result.returncode != 0:
        pytest.skip(f"Cannot SSH to charlie@node-beta: {result.stderr}")

    return True
