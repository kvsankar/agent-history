"""Fixtures for Docker-based E2E tests.

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

import pytest

from .helpers import get_env, ssh_run


def _in_docker_environment():
    """Check if we're running inside the Docker test environment."""
    # Check for Docker-specific indicators
    if os.path.exists("/.dockerenv"):
        return True
    # Check if we can reach node-alpha (only available in Docker network)
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=2",
                "alice@node-alpha",
                "echo",
                "ok",
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# Skip all tests in this directory if not in Docker environment
if not _in_docker_environment():
    pytest.skip(
        "Docker E2E tests require Docker environment (run via docker-compose)",
        allow_module_level=True,
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


@pytest.fixture
def isolated_home(tmp_path):
    """Create an isolated home directory with required agent directories.

    Use this fixture when tests need to override HOME for isolation.
    Returns a dict with 'path' and 'env' ready for use with run_cli.
    """
    # Create required directory structure
    (tmp_path / ".claude" / "projects").mkdir(parents=True)
    (tmp_path / ".codex" / "sessions").mkdir(parents=True)
    (tmp_path / ".gemini" / "sessions").mkdir(parents=True)
    (tmp_path / ".claude-history").mkdir(parents=True)

    return {
        "path": tmp_path,
        "env": {"HOME": str(tmp_path)},
    }
