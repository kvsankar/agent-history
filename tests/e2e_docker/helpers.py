"""Helper functions for Docker-based E2E tests.

These are utility functions used by the e2e_docker tests.
"""

import os
import subprocess
import sys
from pathlib import Path

# Path to the agent-history script
SCRIPT_PATH = Path("/app/agent-history")

# Coverage configuration for subprocess tracking
COVERAGE_RC = Path("/app/.coveragerc")


def get_env():
    """Get environment configuration from docker-compose."""
    return {
        "node_alpha": os.environ.get("NODE_ALPHA", "node-alpha"),
        "node_beta": os.environ.get("NODE_BETA", "node-beta"),
        "alpha_users": os.environ.get("ALPHA_USERS", "alice,bob").split(","),
        "beta_users": os.environ.get("BETA_USERS", "charlie,dave").split(","),
    }


def get_coverage_env():
    """Get environment variables for coverage subprocess tracking.

    Coverage is only enabled if COVERAGE_DATA_FILE is set in the environment,
    indicating that we're running in coverage collection mode.
    """
    coverage_env = {}
    # Only enable coverage if explicitly requested via COVERAGE_DATA_FILE
    if COVERAGE_RC.exists() and os.environ.get("COVERAGE_DATA_FILE"):
        coverage_env["COVERAGE_PROCESS_START"] = str(COVERAGE_RC)
    return coverage_env


def run_cli(args, timeout=30, env=None):
    """Run the agent-history CLI and return the result.

    Args:
        args: List of command-line arguments
        timeout: Command timeout in seconds
        env: Optional environment overrides

    Returns:
        subprocess.CompletedProcess with stdout, stderr, returncode
    """
    run_env = os.environ.copy()
    run_env.update(get_coverage_env())
    if env:
        run_env.update(env)

    # Use coverage run to track subprocess coverage
    if COVERAGE_RC.exists() and run_env.get("COVERAGE_PROCESS_START"):
        # Get coverage data file location from env
        coverage_data_file = run_env.get("COVERAGE_DATA_FILE", "/coverage/.coverage")
        cmd = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--parallel-mode",
            "--rcfile",
            str(COVERAGE_RC),
            "--data-file",
            coverage_data_file,
            str(SCRIPT_PATH),
            *args,
        ]
    else:
        cmd = [sys.executable, str(SCRIPT_PATH), *args]

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
