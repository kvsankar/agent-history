"""Multi-workspace/home fixtures for scope resolution tests.

This module provides fixtures that simulate multiple workspaces across multiple
homes for testing scope modifiers (--aw, --ah, -n, --project, --wsl, --windows, etc.)
"""

import hashlib
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import pytest

# ---------------------------------------------------------------------------
# Platform Detection
# ---------------------------------------------------------------------------


def is_wsl() -> bool:
    """Check if running in WSL."""
    try:
        return "microsoft" in os.uname().release.lower()
    except AttributeError:
        return False


def get_windows_tmp_path() -> Optional[Path]:
    """Get a temp path on Windows filesystem accessible from WSL."""
    override = os.environ.get("AGENT_HISTORY_HOME_WINDOWS")
    if override:
        return Path(override)
    if not is_wsl():
        return None
    windows_tmp = Path("/mnt/c/tmp")
    parent = windows_tmp.parent
    if not (windows_tmp.exists() or parent.exists()):
        return None
    # Skip if not writable (common in CI/WSL without Windows drives mounted)
    if not (os.access(windows_tmp, os.W_OK) or os.access(parent, os.W_OK)):
        return None
    return windows_tmp


from tests.helpers.session_builders import (
    ClaudeSessionBuilder,
    CodexSessionBuilder,
    GeminiSessionBuilder,
)

# ---------------------------------------------------------------------------
# Workspace Naming Helpers
# ---------------------------------------------------------------------------


def encode_workspace_path(path: str) -> str:
    """Encode a path as a Claude workspace directory name.

    Claude encodes paths by replacing / with - and prefixing the path.
    Example: /home/user/project -> -home-user-project
    """
    # Normalize path separators
    path = path.replace("\\", "/")
    # Replace slashes with dashes and ensure leading dash
    encoded = path.replace("/", "-")
    if not encoded.startswith("-"):
        encoded = "-" + encoded
    return encoded


def compute_gemini_hash(path: str) -> str:
    """Compute Gemini project hash (SHA-256 of path)."""
    return hashlib.sha256(path.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Session Configuration Constants
# ---------------------------------------------------------------------------


# Default workspaces for scope testing
DEFAULT_WORKSPACES = {
    "project-alpha": {
        "path": "/home/user/project-alpha",
        "sessions": 3,
        "agents": ["claude", "codex"],
    },
    "project-beta": {
        "path": "/home/user/project-beta",
        "sessions": 2,
        "agents": ["claude"],
    },
    "auth-service": {
        "path": "/home/user/services/auth-service",
        "sessions": 1,
        "agents": ["claude", "gemini"],
    },
    "api-gateway": {
        "path": "/home/user/services/api-gateway",
        "sessions": 2,
        "agents": ["codex", "gemini"],
    },
    "frontend-app": {
        "path": "/home/user/apps/frontend-app",
        "sessions": 1,
        "agents": ["gemini"],
    },
}


# Home configurations for multi-home testing
HOME_CONFIGS = {
    "local": {
        "type": "local",
        "workspaces": ["project-alpha", "project-beta", "auth-service"],
    },
    "wsl": {
        "type": "wsl",
        "workspaces": ["project-alpha", "api-gateway"],
    },
    "windows": {
        "type": "windows",
        "workspaces": ["project-beta", "frontend-app"],
    },
    "remote_vm01": {
        "type": "remote",
        "host": "user@vm01",
        "workspaces": ["project-alpha", "auth-service", "api-gateway"],
    },
}


# ---------------------------------------------------------------------------
# Session Creation Helpers
# ---------------------------------------------------------------------------


def create_claude_sessions(
    claude_dir: Path,
    workspace_name: str,
    workspace_path: str,
    count: int,
    base_date: datetime,
) -> List[Path]:
    """Create Claude sessions in a workspace.

    Args:
        claude_dir: Path to .claude/projects directory
        workspace_name: Human-readable workspace name
        workspace_path: Original filesystem path
        count: Number of sessions to create
        base_date: Base date for session timestamps

    Returns:
        List of created session file paths
    """
    encoded_ws = encode_workspace_path(workspace_path)
    ws_dir = claude_dir / encoded_ws
    ws_dir.mkdir(parents=True, exist_ok=True)

    session_paths = []
    for i in range(count):
        session_date = base_date + timedelta(days=i)
        builder = ClaudeSessionBuilder(
            workspace=encoded_ws,
            session_id=f"claude-{workspace_name}-{i + 1:03d}",
        )
        builder._timestamp = session_date

        # Add basic conversation
        builder.add_user_message(f"Help with {workspace_name} task {i + 1}")
        builder.add_assistant_message(
            f"I'll help with {workspace_name}",
            input_tokens=100 + i * 10,
            output_tokens=50 + i * 5,
        )

        session_path = builder.write_to(claude_dir)
        session_paths.append(session_path)

    return session_paths


def create_codex_sessions(
    codex_dir: Path,
    workspace_name: str,
    workspace_path: str,
    count: int,
    base_date: datetime,
) -> List[Path]:
    """Create Codex sessions.

    Args:
        codex_dir: Path to .codex/sessions directory
        workspace_name: Human-readable workspace name
        workspace_path: Original filesystem path (used as cwd)
        count: Number of sessions to create
        base_date: Base date for session timestamps

    Returns:
        List of created session file paths
    """
    session_paths = []
    for i in range(count):
        session_date = base_date + timedelta(days=i)
        date_str = session_date.strftime("%Y-%m-%d")

        builder = CodexSessionBuilder(
            session_id=f"codex-{workspace_name}-{i + 1:03d}",
            cwd=workspace_path,
        )
        builder._timestamp = session_date

        # Add basic conversation
        builder.add_user_message(f"Work on {workspace_name} item {i + 1}")
        builder.add_assistant_message(f"Working on {workspace_name}")
        builder.add_token_count(
            input_tokens=150 + i * 15,
            output_tokens=75 + i * 8,
        )

        session_path = builder.write_to(codex_dir, date_str=date_str)
        session_paths.append(session_path)

    return session_paths


def create_gemini_sessions(
    gemini_dir: Path,
    workspace_name: str,
    workspace_path: str,
    count: int,
    base_date: datetime,
) -> List[Path]:
    """Create Gemini sessions.

    Args:
        gemini_dir: Path to .gemini/tmp directory
        workspace_name: Human-readable workspace name
        workspace_path: Original filesystem path (used for hash)
        count: Number of sessions to create
        base_date: Base date for session timestamps

    Returns:
        List of created session file paths
    """
    project_hash = compute_gemini_hash(workspace_path)
    session_paths = []

    for i in range(count):
        session_date = base_date + timedelta(days=i)

        builder = GeminiSessionBuilder(
            session_id=f"gemini-{workspace_name}-{i + 1:03d}",
            project_hash=project_hash,
        )
        builder._timestamp = session_date

        # Add basic conversation
        builder.add_user_message(f"Gemini help with {workspace_name} task {i + 1}")
        builder.add_gemini_message(
            f"I'll assist with {workspace_name}",
            input_tokens=200 + i * 20,
            output_tokens=100 + i * 10,
        )

        session_path = builder.write_to(gemini_dir)
        session_paths.append(session_path)

    return session_paths


# ---------------------------------------------------------------------------
# Fixture: Multi-Workspace Single Home
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_workspace_home(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:  # noqa: PLR0915
    """Create a single home with multiple workspaces for workspace scope testing.

    Creates workspaces:
    - project-alpha (3 Claude sessions, 2 Codex sessions)
    - project-beta (2 Claude sessions)
    - auth-service (1 Claude session, 1 Gemini session)
    - api-gateway (2 Codex sessions, 1 Gemini session)
    - frontend-app (1 Gemini session)

    Yields:
        Dict with:
        - path: home directory path
        - env: environment variables for test isolation
        - workspaces: dict of workspace info
        - session_counts: expected session counts by workspace
        - agent_counts: expected session counts by agent
    """
    # Create agent directories
    claude_dir = tmp_path / ".claude" / "projects"
    codex_dir = tmp_path / ".codex" / "sessions"
    gemini_dir = tmp_path / ".gemini" / "tmp"
    history_dir = tmp_path / ".agent-history"

    claude_dir.mkdir(parents=True)
    codex_dir.mkdir(parents=True)
    gemini_dir.mkdir(parents=True)
    history_dir.mkdir(parents=True)

    # Base date for sessions
    base_date = datetime(2025, 1, 1, 10, 0, 0)

    # Create sessions for each workspace
    workspaces = {}
    session_counts = {}
    agent_counts = {"claude": 0, "codex": 0, "gemini": 0}
    all_sessions = []

    for ws_name, ws_config in DEFAULT_WORKSPACES.items():
        ws_path = ws_config["path"]
        ws_sessions = []

        # Create Claude sessions
        if "claude" in ws_config["agents"]:
            sessions = create_claude_sessions(
                claude_dir, ws_name, ws_path, ws_config["sessions"], base_date
            )
            ws_sessions.extend(sessions)
            agent_counts["claude"] += len(sessions)

        # Create Codex sessions
        if "codex" in ws_config["agents"]:
            sessions = create_codex_sessions(
                codex_dir, ws_name, ws_path, ws_config["sessions"], base_date
            )
            ws_sessions.extend(sessions)
            agent_counts["codex"] += len(sessions)

        # Create Gemini sessions
        if "gemini" in ws_config["agents"]:
            sessions = create_gemini_sessions(
                gemini_dir, ws_name, ws_path, ws_config["sessions"], base_date
            )
            ws_sessions.extend(sessions)
            agent_counts["gemini"] += len(sessions)

        workspaces[ws_name] = {
            "path": ws_path,
            "encoded": encode_workspace_path(ws_path),
            "sessions": ws_sessions,
            "agents": ws_config["agents"],
        }
        session_counts[ws_name] = len(ws_sessions)
        all_sessions.extend(ws_sessions)

    # Environment variables for test isolation
    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(claude_dir)
    env["CODEX_SESSIONS_DIR"] = str(codex_dir)
    env["GEMINI_SESSIONS_DIR"] = str(gemini_dir)
    env["HOME"] = str(tmp_path)
    env["AGENT_HISTORY_HOME"] = str(tmp_path)
    env["AGENT_HISTORY_HOME_WSL"] = str(tmp_path)
    env["AGENT_HISTORY_CONFIG_DIR"] = str(history_dir)
    if sys.platform == "win32":
        env["USERPROFILE"] = str(tmp_path)

    # For Windows home on WSL, use actual Windows filesystem
    windows_home_path = None
    if is_wsl():
        windows_tmp = get_windows_tmp_path()
        if windows_tmp:
            try:
                windows_home_path = windows_tmp / f"agent-history-test-{uuid.uuid4().hex[:8]}"
                windows_home_path.mkdir(parents=True, exist_ok=True)
                # Create Claude/Codex/Gemini dirs on Windows
                win_claude = windows_home_path / ".claude" / "projects"
                win_codex = windows_home_path / ".codex" / "sessions"
                win_gemini = windows_home_path / ".gemini" / "tmp"
                win_claude.mkdir(parents=True)
                win_codex.mkdir(parents=True)
                win_gemini.mkdir(parents=True)
                # Create a test session on Windows home
                create_claude_sessions(
                    win_claude, "win-project", "/mnt/c/projects/win-project", 1, base_date
                )
                env["AGENT_HISTORY_HOME_WINDOWS"] = str(windows_home_path)
            except (PermissionError, OSError):
                windows_home_path = None

    # Fallback if not on WSL or can't access Windows
    if "AGENT_HISTORY_HOME_WINDOWS" not in env:
        env["AGENT_HISTORY_HOME_WINDOWS"] = str(tmp_path)

    try:
        yield {
            "path": tmp_path,
            "env": env,
            "claude_dir": claude_dir,
            "codex_dir": codex_dir,
            "gemini_dir": gemini_dir,
            "workspaces": workspaces,
            "session_counts": session_counts,
            "agent_counts": agent_counts,
            "total_sessions": len(all_sessions),
            "all_sessions": all_sessions,
            "windows_home": windows_home_path,
        }
    finally:
        # Cleanup Windows home if created
        if windows_home_path and windows_home_path.exists():
            shutil.rmtree(windows_home_path, ignore_errors=True)


# ---------------------------------------------------------------------------
# Fixture: Multi-Home Setup
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_home_setup(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create multiple homes for home scope testing.

    Creates homes:
    - local: project-alpha, project-beta, auth-service
    - wsl: project-alpha, api-gateway
    - windows: project-beta, frontend-app
    - remote_vm01: project-alpha, auth-service, api-gateway

    Yields:
        Dict with:
        - homes: dict of home configurations
        - env: environment variables
        - session_counts: by home and workspace
    """
    homes = {}
    session_counts_by_home = {}
    base_date = datetime(2025, 1, 1, 10, 0, 0)

    for home_name, home_config in HOME_CONFIGS.items():
        home_dir = tmp_path / home_name
        claude_dir = home_dir / ".claude" / "projects"
        codex_dir = home_dir / ".codex" / "sessions"
        gemini_dir = home_dir / ".gemini" / "tmp"
        history_dir = home_dir / ".agent-history"

        claude_dir.mkdir(parents=True)
        codex_dir.mkdir(parents=True)
        gemini_dir.mkdir(parents=True)
        history_dir.mkdir(parents=True)

        home_sessions = []
        home_workspaces = {}

        for ws_name in home_config["workspaces"]:
            ws_config = DEFAULT_WORKSPACES[ws_name]
            ws_path = ws_config["path"]
            ws_sessions = []

            if "claude" in ws_config["agents"]:
                sessions = create_claude_sessions(
                    claude_dir, ws_name, ws_path, ws_config["sessions"], base_date
                )
                ws_sessions.extend(sessions)

            if "codex" in ws_config["agents"]:
                sessions = create_codex_sessions(
                    codex_dir, ws_name, ws_path, ws_config["sessions"], base_date
                )
                ws_sessions.extend(sessions)

            if "gemini" in ws_config["agents"]:
                sessions = create_gemini_sessions(
                    gemini_dir, ws_name, ws_path, ws_config["sessions"], base_date
                )
                ws_sessions.extend(sessions)

            home_workspaces[ws_name] = {
                "path": ws_path,
                "encoded": encode_workspace_path(ws_path),
                "sessions": ws_sessions,
            }
            home_sessions.extend(ws_sessions)

        homes[home_name] = {
            "path": home_dir,
            "type": home_config["type"],
            "claude_dir": claude_dir,
            "codex_dir": codex_dir,
            "gemini_dir": gemini_dir,
            "workspaces": home_workspaces,
            "total_sessions": len(home_sessions),
        }
        if "host" in home_config:
            homes[home_name]["host"] = home_config["host"]

        session_counts_by_home[home_name] = len(home_sessions)

    # Environment variables - default to local home
    local_home = homes["local"]["path"]
    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(homes["local"]["claude_dir"])
    env["CODEX_SESSIONS_DIR"] = str(homes["local"]["codex_dir"])
    env["GEMINI_SESSIONS_DIR"] = str(homes["local"]["gemini_dir"])
    env["HOME"] = str(local_home)
    if sys.platform == "win32":
        env["USERPROFILE"] = str(local_home)

    # Additional environment variables for cross-environment access
    env["AGENT_HISTORY_HOME"] = str(homes["local"]["path"])
    env["AGENT_HISTORY_HOME_WSL"] = str(homes["wsl"]["path"])
    env["AGENT_HISTORY_HOME_WINDOWS"] = str(homes["windows"]["path"])

    yield {
        "base_path": tmp_path,
        "homes": homes,
        "env": env,
        "session_counts_by_home": session_counts_by_home,
        "home_configs": HOME_CONFIGS,
    }


# ---------------------------------------------------------------------------
# Fixture: Date-Range Sessions
# ---------------------------------------------------------------------------


@pytest.fixture
def date_range_sessions(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create sessions spanning a date range for filter testing.

    Creates sessions on:
    - 2025-01-01: 2 sessions
    - 2025-01-05: 3 sessions
    - 2025-01-10: 2 sessions
    - 2025-01-15: 1 session
    - 2025-01-20: 2 sessions

    Yields:
        Dict with session info and date ranges
    """
    claude_dir = tmp_path / ".claude" / "projects"
    claude_dir.mkdir(parents=True)

    ws_path = "/home/user/date-test-project"
    encoded_ws = encode_workspace_path(ws_path)

    sessions_by_date = {}
    all_sessions = []

    date_configs = [
        (datetime(2025, 1, 1), 2),
        (datetime(2025, 1, 5), 3),
        (datetime(2025, 1, 10), 2),
        (datetime(2025, 1, 15), 1),
        (datetime(2025, 1, 20), 2),
    ]

    for date, count in date_configs:
        date_str = date.strftime("%Y-%m-%d")
        sessions = []
        for i in range(count):
            builder = ClaudeSessionBuilder(
                workspace=encoded_ws,
                session_id=f"session-{date_str}-{i + 1:03d}",
            )
            # Set timestamp to specific date
            builder._timestamp = date + timedelta(hours=10 + i)
            builder.add_user_message(f"Task on {date_str}")
            builder.add_assistant_message(f"Working on {date_str}")

            session_path = builder.write_to(claude_dir)
            sessions.append(session_path)
            all_sessions.append(session_path)

        sessions_by_date[date_str] = sessions

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(claude_dir)
    env["HOME"] = str(tmp_path)

    yield {
        "path": tmp_path,
        "env": env,
        "claude_dir": claude_dir,
        "workspace_path": ws_path,
        "workspace_encoded": encoded_ws,
        "sessions_by_date": sessions_by_date,
        "all_sessions": all_sessions,
        "total_sessions": len(all_sessions),
        "date_range": {
            "earliest": "2025-01-01",
            "latest": "2025-01-20",
        },
    }


# ---------------------------------------------------------------------------
# Fixture: Project Configuration
# ---------------------------------------------------------------------------


@pytest.fixture
def project_config_setup(multi_home_setup: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
    """Set up project configurations for --project scope testing.

    Creates projects.json with:
    - "myproject": workspaces from local and wsl
    - "services": auth-service and api-gateway workspaces

    Format: {"version": 2, "projects": {"name": {"source_key": ["encoded-ws", ...]}}}
    """
    # Create projects config in CLI's expected format:
    # source_key -> list of encoded workspace paths
    projects = {
        "myproject": {
            "local": [
                encode_workspace_path("/home/user/project-alpha"),
            ],
            "wsl": [
                encode_workspace_path("/home/user/project-alpha"),
            ],
        },
        "services": {
            "local": [
                encode_workspace_path("/home/user/services/auth-service"),
            ],
            "remote:user@vm01": [
                encode_workspace_path("/home/user/services/api-gateway"),
            ],
        },
    }

    # Write config.json (projects) to local home
    local_history_dir = multi_home_setup["homes"]["local"]["path"] / ".agent-history"
    projects_file = local_history_dir / "config.json"
    projects_data = {"version": 2, "projects": projects, "sources": []}
    with open(projects_file, "w", encoding="utf-8") as f:
        json.dump(projects_data, f, indent=2)

    yield {
        **multi_home_setup,
        "projects": projects,
        "projects_file": projects_file,
    }


# ---------------------------------------------------------------------------
# Fixture: Agent Filter Sessions
# ---------------------------------------------------------------------------


@pytest.fixture
def agent_filter_sessions(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create sessions from all three agents for agent filter testing.

    Creates in a single workspace:
    - 3 Claude sessions
    - 2 Codex sessions
    - 2 Gemini sessions

    Yields:
        Dict with session info by agent
    """
    claude_dir = tmp_path / ".claude" / "projects"
    codex_dir = tmp_path / ".codex" / "sessions"
    gemini_dir = tmp_path / ".gemini" / "tmp"

    claude_dir.mkdir(parents=True)
    codex_dir.mkdir(parents=True)
    gemini_dir.mkdir(parents=True)

    ws_path = "/home/user/multi-agent-project"
    base_date = datetime(2025, 1, 10, 10, 0, 0)

    sessions_by_agent = {
        "claude": create_claude_sessions(claude_dir, "multi-agent", ws_path, 3, base_date),
        "codex": create_codex_sessions(codex_dir, "multi-agent", ws_path, 2, base_date),
        "gemini": create_gemini_sessions(gemini_dir, "multi-agent", ws_path, 2, base_date),
    }

    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(claude_dir)
    env["CODEX_SESSIONS_DIR"] = str(codex_dir)
    env["GEMINI_SESSIONS_DIR"] = str(gemini_dir)
    env["HOME"] = str(tmp_path)

    yield {
        "path": tmp_path,
        "env": env,
        "workspace_path": ws_path,
        "sessions_by_agent": sessions_by_agent,
        "counts": {
            "claude": 3,
            "codex": 2,
            "gemini": 2,
            "total": 7,
        },
    }


# ---------------------------------------------------------------------------
# Scope Combination Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scope_combo_setup(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:  # noqa: C901
    """Comprehensive setup for testing scope combinations.

    Creates a realistic multi-home, multi-workspace, multi-agent setup
    with sessions spanning multiple dates.

    This fixture is designed for parameterized combination tests.
    """
    # Structure: 2 homes x 3 workspaces x 3 agents x varying sessions
    homes_config = {
        "local": {
            "workspaces": {
                "project-alpha": {"claude": 2, "codex": 1, "gemini": 1},
                "project-beta": {"claude": 1, "codex": 0, "gemini": 0},
                "auth-service": {"claude": 0, "codex": 1, "gemini": 1},
            }
        },
        "remote": {
            "workspaces": {
                "project-alpha": {"claude": 1, "codex": 1, "gemini": 0},
                "project-beta": {"claude": 0, "codex": 0, "gemini": 1},
                "auth-service": {"claude": 1, "codex": 0, "gemini": 1},
            }
        },
    }

    homes = {}
    session_matrix = {}  # [home][workspace][agent] = count

    for home_name, home_config in homes_config.items():
        home_dir = tmp_path / home_name
        claude_dir = home_dir / ".claude" / "projects"
        codex_dir = home_dir / ".codex" / "sessions"
        gemini_dir = home_dir / ".gemini" / "tmp"

        claude_dir.mkdir(parents=True)
        codex_dir.mkdir(parents=True)
        gemini_dir.mkdir(parents=True)
        (home_dir / ".agent-history").mkdir(parents=True)

        session_matrix[home_name] = {}
        home_sessions = []

        for ws_name, agents in home_config["workspaces"].items():
            ws_path = f"/home/user/{ws_name}"
            ws_sessions = []
            session_matrix[home_name][ws_name] = {}

            # Use different base dates for date filtering tests
            base_dates = {
                "project-alpha": datetime(2025, 1, 1),
                "project-beta": datetime(2025, 1, 10),
                "auth-service": datetime(2025, 1, 20),
            }
            base_date = base_dates.get(ws_name, datetime(2025, 1, 1))

            for agent, count in agents.items():
                session_matrix[home_name][ws_name][agent] = count
                if count == 0:
                    continue

                if agent == "claude":
                    sessions = create_claude_sessions(
                        claude_dir, ws_name, ws_path, count, base_date
                    )
                elif agent == "codex":
                    sessions = create_codex_sessions(codex_dir, ws_name, ws_path, count, base_date)
                else:  # gemini
                    sessions = create_gemini_sessions(
                        gemini_dir, ws_name, ws_path, count, base_date
                    )

                ws_sessions.extend(sessions)

            home_sessions.extend(ws_sessions)

        homes[home_name] = {
            "path": home_dir,
            "claude_dir": claude_dir,
            "codex_dir": codex_dir,
            "gemini_dir": gemini_dir,
            "sessions": home_sessions,
        }

    # Default environment (local home)
    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(homes["local"]["claude_dir"])
    env["CODEX_SESSIONS_DIR"] = str(homes["local"]["codex_dir"])
    env["GEMINI_SESSIONS_DIR"] = str(homes["local"]["gemini_dir"])
    env["HOME"] = str(homes["local"]["path"])
    env["AGENT_HISTORY_HOME"] = str(homes["local"]["path"])
    env["AGENT_HISTORY_HOME_WSL"] = str(homes["remote"]["path"])  # Simulate WSL
    env["AGENT_HISTORY_HOME_WINDOWS"] = str(homes["remote"]["path"])  # Simulate Windows

    # Compute expected totals
    def compute_totals(
        home_filter: Optional[List[str]] = None,
        workspace_filter: Optional[List[str]] = None,
        agent_filter: Optional[str] = None,
    ) -> int:
        """Compute expected session count for given filters."""
        total = 0
        for home_name, workspaces in session_matrix.items():
            if home_filter and home_name not in home_filter:
                continue
            for ws_name, agents in workspaces.items():
                if workspace_filter and ws_name not in workspace_filter:
                    continue
                for agent, count in agents.items():
                    if agent_filter and agent != agent_filter:
                        continue
                    total += count
        return total

    yield {
        "base_path": tmp_path,
        "homes": homes,
        "env": env,
        "session_matrix": session_matrix,
        "compute_totals": compute_totals,
    }


# ---------------------------------------------------------------------------
# Fixture: Current Workspace Setup
# ---------------------------------------------------------------------------


@pytest.fixture
def current_workspace_setup(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Create a workspace at an actual filesystem path for current-workspace tests.

    Unlike other fixtures that use virtual paths like /home/user/project-alpha,
    this fixture creates sessions for the actual tmp_path, allowing tests to
    run from that directory and have the CLI detect it as the current workspace.

    Yields:
        Dict with:
        - workspace_dir: the actual workspace directory to run from
        - env: environment variables for test isolation
        - session_count: number of sessions created
    """
    # Create the workspace directory
    workspace_dir = tmp_path / "test-workspace"
    workspace_dir.mkdir(parents=True)

    # Create agent directories
    claude_dir = tmp_path / ".claude" / "projects"
    codex_dir = tmp_path / ".codex" / "sessions"
    history_dir = tmp_path / ".agent-history"

    claude_dir.mkdir(parents=True)
    codex_dir.mkdir(parents=True)
    history_dir.mkdir(parents=True)

    # Create Claude sessions for the ACTUAL workspace path
    workspace_path = str(workspace_dir)
    workspace_encoded = encode_workspace_path(workspace_path)
    session_dir = claude_dir / workspace_encoded
    session_dir.mkdir(parents=True)

    base_date = datetime(2025, 1, 15, 10, 0, 0)
    sessions_created = []

    # Create 2 Claude sessions
    for i in range(2):
        session_id = f"session-{uuid.uuid4()}"
        session_file = session_dir / f"{session_id}.jsonl"
        timestamp = (base_date + timedelta(hours=i)).isoformat() + "Z"

        messages = [
            {
                "type": "user",
                "message": {"role": "user", "content": f"Test message {i}"},
                "timestamp": timestamp,
                "uuid": f"user-{i}",
                "sessionId": session_id,
                "cwd": workspace_path,
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": f"Response {i}"}],
                },
                "timestamp": timestamp,
                "uuid": f"asst-{i}",
                "sessionId": session_id,
                "model": "claude-sonnet-4-20250514",
            },
        ]

        with open(session_file, "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg) + "\n")

        sessions_created.append(session_id)

    # Environment variables for test isolation
    env = os.environ.copy()
    env["CLAUDE_PROJECTS_DIR"] = str(claude_dir)
    env["CODEX_SESSIONS_DIR"] = str(codex_dir)
    env["HOME"] = str(tmp_path)
    env["AGENT_HISTORY_CONFIG_DIR"] = str(history_dir)

    yield {
        "workspace_dir": workspace_dir,
        "workspace_path": workspace_path,
        "env": env,
        "session_count": len(sessions_created),
        "sessions": sessions_created,
    }


# ---------------------------------------------------------------------------
# Pytest Markers
# ---------------------------------------------------------------------------


def pytest_configure(config):
    """Register custom markers for scope tests."""
    config.addinivalue_line("markers", "scope: marks tests as scope resolution tests")
    config.addinivalue_line(
        "markers", "workspace_scope: marks tests for workspace scope resolution"
    )
    config.addinivalue_line("markers", "home_scope: marks tests for home scope resolution")
    config.addinivalue_line("markers", "filter_scope: marks tests for filter scope (date, agent)")
    config.addinivalue_line("markers", "scope_combination: marks tests for scope combinations")
