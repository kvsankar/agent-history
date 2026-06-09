"""Metrics database for cagelens.

This module provides functions for managing the SQLite metrics database
that caches session statistics for fast queries.

The metrics database stores:
- Session metadata (file path, workspace, agent, timestamps)
- Message counts and token usage
- Tool usage statistics

See docs/design-v2/pipeline-architecture.md for specifications.
"""

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from agent_history.storage.config import get_config_dir

if TYPE_CHECKING:
    from agent_history.scope.types import ConcreteScope

__all__ = [
    "get_metrics_db_path",
    "get_session_stats_from_db",
    "get_stats_rollup_from_db",
    "get_time_stats_from_db",
    "get_tool_usage_stats_from_db",
    "init_metrics_db",
    "sync_file_to_db",
    "sync_sessions_to_db",
]

# Schema version for migrations
METRICS_DB_VERSION = 7

# Work period gap threshold in seconds (30 minutes per spec)
WORK_PERIOD_GAP_THRESHOLD = 30 * 60


def _apply_secure_permissions(path: Path, mode: int) -> None:
    """Apply POSIX-style permissions unless on Windows."""
    if os.name == "nt":
        return
    os.chmod(path, mode)


def get_metrics_db_path() -> Path:
    """Get the metrics database file path.

    Returns:
        Path to the metrics.db file in the config directory.
    """
    return get_config_dir() / "metrics.db"


def init_metrics_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Initialize the metrics database, creating tables if needed.

    Opens (or creates) the SQLite metrics database and ensures the schema
    is up to date. Handles migrations from older schema versions.

    Args:
        db_path: Path to database file. Defaults to ~/.cagelens/metrics.db

    Returns:
        Open sqlite3.Connection with row_factory set to sqlite3.Row

    Side Effects:
        - Creates parent directory (~/.cagelens/) with mode 0o700 if missing
        - Creates database file with mode 0o600 if missing
        - Runs schema migrations if database version is outdated
    """
    if db_path is None:
        db_path = get_metrics_db_path()

    # Ensure directory exists with secure permissions
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _apply_secure_permissions(db_path.parent, 0o700)

    # Track if this is a new database
    is_new_db = not db_path.exists()

    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.create_function("REGEXP", 2, _sqlite_regexp)

    # Enable foreign key enforcement (disabled by default in SQLite)
    conn.execute("PRAGMA foreign_keys = ON")

    # Set secure permissions on new database file
    if is_new_db:
        _apply_secure_permissions(db_path, 0o600)
    conn.row_factory = sqlite3.Row  # Enable column access by name

    # Create tables
    conn.executescript("""
        -- Schema version tracking
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );

        -- Sessions table (one row per session file)
        CREATE TABLE IF NOT EXISTS sessions (
            file_path TEXT PRIMARY KEY,
            session_id TEXT,
            workspace TEXT NOT NULL,
            home TEXT NOT NULL DEFAULT 'local',
            source TEXT NOT NULL DEFAULT 'local',
            agent TEXT NOT NULL DEFAULT 'claude',
            file_mtime REAL,
            is_agent INTEGER DEFAULT 0,
            parent_session_id TEXT,
            start_time TEXT,
            end_time TEXT,
            message_count INTEGER DEFAULT 0,
            user_messages INTEGER DEFAULT 0,
            assistant_messages INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_creation_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            first_timestamp TEXT,
            last_timestamp TEXT,
            git_branch TEXT,
            claude_version TEXT,
            cwd TEXT,
            work_period_seconds REAL DEFAULT 0,
            num_work_periods INTEGER DEFAULT 1,
            git_remote_url TEXT,
            project TEXT,
            project_short TEXT
        );

        -- Messages table (aggregated stats per message)
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            file_path TEXT NOT NULL,
            session_id TEXT,
            parent_uuid TEXT,
            type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            model TEXT,
            stop_reason TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_creation_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            FOREIGN KEY (file_path) REFERENCES sessions(file_path)
        );

        -- Tool uses table
        CREATE TABLE IF NOT EXISTS tool_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_use_id TEXT,
            message_uuid TEXT,
            file_path TEXT NOT NULL,
            session_id TEXT,
            tool_name TEXT NOT NULL,
            is_error INTEGER DEFAULT 0,
            timestamp TEXT,
            FOREIGN KEY (file_path) REFERENCES sessions(file_path)
        );

        -- Synced files tracking (for incremental sync)
        CREATE TABLE IF NOT EXISTS synced_files (
            file_path TEXT PRIMARY KEY,
            mtime REAL NOT NULL,
            synced_at TEXT NOT NULL
        );

        -- Create indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON sessions(workspace);
        CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source);
        CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time);
        CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON sessions(session_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent);
        CREATE INDEX IF NOT EXISTS idx_messages_file_path ON messages(file_path);
        CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
        CREATE INDEX IF NOT EXISTS idx_messages_model ON messages(model);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_tool_uses_file_path ON tool_uses(file_path);
        CREATE INDEX IF NOT EXISTS idx_tool_uses_tool_name ON tool_uses(tool_name);
        CREATE INDEX IF NOT EXISTS idx_tool_uses_session ON tool_uses(session_id);

        -- Composite indexes for common filter combinations
        CREATE INDEX IF NOT EXISTS idx_sessions_workspace_source ON sessions(workspace, source);
        CREATE INDEX IF NOT EXISTS idx_sessions_source_time ON sessions(source, start_time);

        -- Aggregated tool/model usage tables
        CREATE TABLE IF NOT EXISTS tool_usage (
            session_id TEXT,
            tool_name TEXT NOT NULL,
            call_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_tool_usage_session ON tool_usage(session_id);

        CREATE TABLE IF NOT EXISTS model_usage (
            session_id TEXT,
            model_name TEXT NOT NULL,
            message_count INTEGER DEFAULT 0,
            tokens INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_model_usage_session ON model_usage(session_id);
    """)

    # Check/set schema version
    cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
    row = cursor.fetchone()
    current_version = row["version"] if row else 0

    if current_version < METRICS_DB_VERSION:
        _run_migrations(conn, current_version, row is None)

    conn.commit()
    return conn


def _sqlite_regexp(pattern: str, value: str | None) -> int:
    """SQLite REGEXP implementation for workspace filters."""
    if value is None:
        return 0
    try:
        return 1 if re.search(pattern, str(value)) else 0
    except re.error:
        return 0


def _run_migrations(conn: sqlite3.Connection, current_version: int, is_new: bool) -> None:
    """Run database schema migrations.

    Args:
        conn: Database connection
        current_version: Current schema version
        is_new: True if this is a new database
    """
    # For new databases, just set the version
    if is_new:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (METRICS_DB_VERSION,))
        return

    # Run migrations for existing databases
    # Version 3: add time tracking columns
    if current_version < 3:
        for col, default in [
            ("work_period_seconds", "REAL DEFAULT 0"),
            ("num_work_periods", "INTEGER DEFAULT 1"),
        ]:
            try:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {default}")
            except sqlite3.OperationalError:
                pass

    # Version 4: add agent column
    if current_version < 4:
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN agent TEXT NOT NULL DEFAULT 'claude'")
        except sqlite3.OperationalError:
            pass

    # Version 5: add git_remote_url
    if current_version < 5:
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN git_remote_url TEXT")
        except sqlite3.OperationalError:
            pass

    # Version 6: add project columns
    if current_version < 6:
        for col in ("project", "project_short"):
            try:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project)")

    # Version 7: add home and aggregated columns
    if current_version < 7:
        new_columns = [
            ("home", "TEXT DEFAULT 'local'"),
            ("user_messages", "INTEGER DEFAULT 0"),
            ("assistant_messages", "INTEGER DEFAULT 0"),
            ("input_tokens", "INTEGER DEFAULT 0"),
            ("output_tokens", "INTEGER DEFAULT 0"),
            ("cache_creation_tokens", "INTEGER DEFAULT 0"),
            ("cache_read_tokens", "INTEGER DEFAULT 0"),
            ("first_timestamp", "TEXT"),
            ("last_timestamp", "TEXT"),
        ]
        for col, ddl in new_columns:
            try:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {ddl}")
            except sqlite3.OperationalError:
                pass
        # Backfill home from source
        try:
            conn.execute("UPDATE sessions SET home = source WHERE home IS NULL OR home = ''")
        except sqlite3.OperationalError:
            pass

    # Update version
    conn.execute("UPDATE schema_version SET version = ?", (METRICS_DB_VERSION,))


def _parse_claude_jsonl(
    jsonl_file: Path,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parse a JSONL file and extract session info, messages, and tool uses.

    Args:
        jsonl_file: Path to the JSONL file

    Returns:
        Tuple of (session_info, messages_list, tool_uses_list)
    """
    session_info: Dict[str, Any] = {
        "session_id": None,
        "message_count": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "first_timestamp": None,
        "last_timestamp": None,
        "cwd": None,
        "git_branch": None,
        "claude_version": None,
        "is_agent": False,
        "parent_session_id": None,
    }
    messages: List[Dict[str, Any]] = []
    tool_uses: List[Dict[str, Any]] = []
    timestamps: List[str] = []

    try:
        with open(jsonl_file, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type")
                timestamp = entry.get("timestamp", "")

                # Extract session metadata from first relevant entry
                if session_info["session_id"] is None:
                    session_info["session_id"] = entry.get("sessionId")
                    session_info["cwd"] = entry.get("cwd")
                    session_info["git_branch"] = entry.get("gitBranch")
                    session_info["claude_version"] = entry.get("version")
                    if entry.get("agentId"):
                        session_info["is_agent"] = True
                        session_info["parent_session_id"] = entry.get("parentUuid")

                if entry_type in ("user", "assistant"):
                    session_info["message_count"] += 1
                    if entry_type == "user":
                        session_info["user_messages"] += 1
                    else:
                        session_info["assistant_messages"] += 1

                    if timestamp:
                        timestamps.append(timestamp)

                    # Extract token usage
                    message_obj = entry.get("message", {})
                    usage = message_obj.get("usage", {})
                    input_tokens = usage.get("input_tokens", 0) or 0
                    output_tokens = usage.get("output_tokens", 0) or 0
                    cache_creation = usage.get("cache_creation_input_tokens", 0) or 0
                    cache_read = usage.get("cache_read_input_tokens", 0) or 0

                    session_info["input_tokens"] += input_tokens
                    session_info["output_tokens"] += output_tokens
                    session_info["cache_creation_tokens"] += cache_creation
                    session_info["cache_read_tokens"] += cache_read

                    # Build message record
                    msg_record = {
                        "uuid": entry.get("uuid"),
                        "session_id": entry.get("sessionId"),
                        "parent_uuid": entry.get("parentUuid"),
                        "type": entry_type,
                        "timestamp": timestamp,
                        "model": message_obj.get("model"),
                        "stop_reason": message_obj.get("stop_reason"),
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_creation_tokens": cache_creation,
                        "cache_read_tokens": cache_read,
                    }
                    messages.append(msg_record)

                    # Extract tool uses from content
                    content = message_obj.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict):
                                block_type = block.get("type")
                                if block_type == "tool_use":
                                    tool_uses.append(
                                        {
                                            "tool_use_id": block.get("id"),
                                            "message_uuid": entry.get("uuid"),
                                            "session_id": entry.get("sessionId"),
                                            "tool_name": block.get("name", "unknown"),
                                            "is_error": 0,
                                            "timestamp": timestamp,
                                        }
                                    )
                                elif block_type == "tool_result":
                                    # Check for errors in tool results
                                    if block.get("is_error"):
                                        # Mark the tool use as error
                                        tool_use_id = block.get("tool_use_id")
                                        for tu in tool_uses:
                                            if tu["tool_use_id"] == tool_use_id:
                                                tu["is_error"] = 1
                                                break

    except OSError:
        pass

    # Set first/last timestamps
    if timestamps:
        session_info["first_timestamp"] = min(timestamps)
        session_info["last_timestamp"] = max(timestamps)

    return session_info, messages, tool_uses


def _parse_codex_jsonl(
    jsonl_file: Path,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parse a Codex JSONL file and extract session info, messages, and tool uses.

    Codex uses a different format:
    - Session metadata in type="session_meta" entries
    - Messages in type="response_item" with payload.type="message"
    - Tool calls in type="response_item" with payload.type="function_call"
    - Token usage in type="event_msg" with payload.type="token_count"

    Args:
        jsonl_file: Path to the JSONL file

    Returns:
        Tuple of (session_info, messages_list, tool_uses_list)
    """
    session_info: Dict[str, Any] = {
        "session_id": None,
        "message_count": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "first_timestamp": None,
        "last_timestamp": None,
        "cwd": None,
        "git_branch": None,
        "claude_version": None,
        "is_agent": False,
        "parent_session_id": None,
    }
    messages: List[Dict[str, Any]] = []
    tool_uses: List[Dict[str, Any]] = []
    timestamps: List[str] = []

    try:
        with open(jsonl_file, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type")
                timestamp = entry.get("timestamp", "")
                payload = entry.get("payload", {})

                # Extract session metadata
                if entry_type == "session_meta":
                    session_info["session_id"] = payload.get("id")
                    session_info["cwd"] = payload.get("cwd")
                    git_info = payload.get("git", {})
                    session_info["git_branch"] = git_info.get("branch")
                    session_info["claude_version"] = payload.get("cli_version")

                # Extract messages
                elif entry_type == "response_item":
                    payload_type = payload.get("type")
                    if payload_type == "message":
                        role = payload.get("role", "")
                        if role in ("user", "assistant"):
                            session_info["message_count"] += 1
                            if role == "user":
                                session_info["user_messages"] += 1
                            else:
                                session_info["assistant_messages"] += 1

                            if timestamp:
                                timestamps.append(timestamp)

                            # Build message record
                            msg_record = {
                                "uuid": None,
                                "session_id": session_info["session_id"],
                                "parent_uuid": None,
                                "type": role,
                                "timestamp": timestamp,
                                "model": None,
                                "stop_reason": None,
                                "input_tokens": 0,
                                "output_tokens": 0,
                                "cache_creation_tokens": 0,
                                "cache_read_tokens": 0,
                            }
                            messages.append(msg_record)

                    elif payload_type == "function_call":
                        tool_uses.append(
                            {
                                "tool_use_id": payload.get("call_id"),
                                "message_uuid": None,
                                "session_id": session_info["session_id"],
                                "tool_name": payload.get("name", "unknown"),
                                "is_error": 0,
                                "timestamp": timestamp,
                            }
                        )

                # Extract token usage from event_msg
                elif entry_type == "event_msg":
                    if payload.get("type") == "token_count":
                        info = payload.get("info") or {}
                        total_usage = info.get("total_token_usage", {})
                        input_tokens = total_usage.get("input_tokens", 0)
                        output_tokens = total_usage.get("output_tokens", 0) + total_usage.get(
                            "reasoning_output_tokens", 0
                        )
                        cache_read = total_usage.get("cached_input_tokens", 0)

                        session_info["input_tokens"] = input_tokens
                        session_info["output_tokens"] = output_tokens
                        session_info["cache_read_tokens"] = cache_read

                        # Store tokens on the last assistant message for DB queries
                        # that sum from messages table
                        for msg in reversed(messages):
                            if msg["type"] == "assistant":
                                msg["input_tokens"] = input_tokens
                                msg["output_tokens"] = output_tokens
                                msg["cache_read_tokens"] = cache_read
                                break

    except OSError:
        pass

    # Set first/last timestamps
    if timestamps:
        session_info["first_timestamp"] = min(timestamps)
        session_info["last_timestamp"] = max(timestamps)

    return session_info, messages, tool_uses


def _lookup_gemini_hash(project_hash: str) -> Optional[str]:
    """Look up a Gemini project hash in the index file.

    Args:
        project_hash: The SHA256 hash of the project path

    Returns:
        The resolved project path, or None if not found
    """
    # Check environment variable for test override
    config_dir_override = os.environ.get("CAGELENS_CONFIG_DIR") or os.environ.get(
        "AGENT_HISTORY_CONFIG_DIR"
    )
    if config_dir_override:
        index_path = Path(config_dir_override) / "gemini_index.json"
    else:
        index_path = get_config_dir() / "gemini_index.json"

    if not index_path.exists():
        return None

    try:
        with open(index_path, encoding="utf-8") as f:
            index_data = json.load(f)
        return index_data.get("hashes", {}).get(project_hash)
    except (json.JSONDecodeError, OSError):
        return None


def _parse_gemini_json(
    json_file: Path,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parse a Gemini JSON file and extract session info, messages, and tool uses.

    Gemini uses a single JSON file format:
    - Session metadata at root level (sessionId, projectHash, startTime, lastUpdated)
    - Messages in messages array with type="user" or type="gemini"
    - Token usage in tokens object within each gemini message
    - Tool calls in toolCalls array within gemini messages

    Args:
        json_file: Path to the JSON file

    Returns:
        Tuple of (session_info, messages_list, tool_uses_list)
    """
    session_info: Dict[str, Any] = {
        "session_id": None,
        "message_count": 0,
        "user_messages": 0,
        "assistant_messages": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "first_timestamp": None,
        "last_timestamp": None,
        "cwd": None,
        "git_branch": None,
        "claude_version": None,
        "is_agent": False,
        "parent_session_id": None,
    }
    messages: List[Dict[str, Any]] = []
    tool_uses: List[Dict[str, Any]] = []
    timestamps: List[str] = []

    try:
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)

        session_info["session_id"] = data.get("sessionId")
        session_info["cwd"] = data.get("projectHash")
        session_info["first_timestamp"] = data.get("startTime")
        session_info["last_timestamp"] = data.get("lastUpdated")

        for msg in data.get("messages", []):
            msg_type = msg.get("type", "")
            timestamp = msg.get("timestamp", "")

            if msg_type == "user":
                session_info["message_count"] += 1
                session_info["user_messages"] += 1
                if timestamp:
                    timestamps.append(timestamp)

                messages.append(
                    {
                        "uuid": msg.get("id"),
                        "session_id": session_info["session_id"],
                        "parent_uuid": None,
                        "type": "user",
                        "timestamp": timestamp,
                        "model": None,
                        "stop_reason": None,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_creation_tokens": 0,
                        "cache_read_tokens": 0,
                    }
                )

            elif msg_type == "gemini":
                session_info["message_count"] += 1
                session_info["assistant_messages"] += 1
                if timestamp:
                    timestamps.append(timestamp)

                # Extract tokens
                tokens = msg.get("tokens", {})
                input_tokens = tokens.get("input", 0)
                output_tokens = tokens.get("output", 0)

                session_info["input_tokens"] += input_tokens
                session_info["output_tokens"] += output_tokens

                messages.append(
                    {
                        "uuid": msg.get("id"),
                        "session_id": session_info["session_id"],
                        "parent_uuid": None,
                        "type": "assistant",
                        "timestamp": timestamp,
                        "model": msg.get("model"),
                        "stop_reason": None,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_creation_tokens": 0,
                        "cache_read_tokens": tokens.get("cached", 0),
                    }
                )

                # Extract tool calls
                for tc in msg.get("toolCalls", []):
                    status = tc.get("status", "")
                    tool_uses.append(
                        {
                            "tool_use_id": tc.get("id"),
                            "message_uuid": msg.get("id"),
                            "session_id": session_info["session_id"],
                            "tool_name": tc.get("name", "unknown"),
                            "is_error": 1
                            if status.lower() in ("error", "failed", "failure")
                            else 0,
                            "timestamp": tc.get("timestamp", timestamp),
                        }
                    )

    except (OSError, json.JSONDecodeError):
        pass

    # Update first/last timestamps from messages if needed
    if timestamps:
        session_info["first_timestamp"] = min(timestamps)
        session_info["last_timestamp"] = max(timestamps)

    return session_info, messages, tool_uses


def _calculate_work_periods(
    timestamps: List[str], gap_threshold: float = WORK_PERIOD_GAP_THRESHOLD
) -> Tuple[float, int]:
    """Calculate work period time from a list of timestamps.

    Args:
        timestamps: List of ISO 8601 timestamp strings
        gap_threshold: Gap in seconds that defines a new work period

    Returns:
        Tuple of (total_seconds, num_periods)
    """
    if not timestamps or len(timestamps) < 2:
        return 0.0, 1

    def parse_ts(ts: str) -> Optional[datetime]:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(ts.rstrip("Z"), fmt.rstrip("Z"))
            except ValueError:
                continue
        return None

    parsed = []
    for ts in timestamps:
        dt = parse_ts(ts)
        if dt:
            parsed.append(dt)

    if len(parsed) < 2:
        return 0.0, 1

    parsed.sort()
    total_seconds = 0.0
    num_periods = 1

    for i in range(1, len(parsed)):
        gap = (parsed[i] - parsed[i - 1]).total_seconds()
        if gap > gap_threshold:
            num_periods += 1
        else:
            total_seconds += gap

    return total_seconds, num_periods


def sync_file_to_db(
    conn: sqlite3.Connection,
    jsonl_file: Path,
    source_key: str = "local",
    force: bool = False,
    workspace: Optional[str] = None,
    agent: str = "claude",
) -> bool:
    """Sync a single session file to the database.

    Args:
        conn: Database connection
        jsonl_file: Path to the JSONL session file
        source_key: Source identifier (e.g., "local", "wsl:Ubuntu")
        force: If True, re-sync even if file hasn't changed
        workspace: Workspace name (defaults to parent directory name)
        agent: Agent type (claude, codex, gemini, pi, or a registered backend)

    Returns:
        True if file was synced, False if skipped
    """
    file_path_str = str(jsonl_file)

    # Check if file needs syncing
    try:
        stat = jsonl_file.stat()
        current_mtime = stat.st_mtime
    except OSError:
        return False

    if not force:
        cursor = conn.execute(
            "SELECT file_mtime FROM sessions WHERE file_path = ?", (file_path_str,)
        )
        row = cursor.fetchone()
        if row and row["file_mtime"] and row["file_mtime"] >= current_mtime:
            return False

    from agent_history.backends.registry import require_backend

    backend = require_backend(agent)
    session_info, messages, tool_uses = backend.extract_stats(jsonl_file)
    workspace = backend.resolve_stats_workspace(jsonl_file, session_info, workspace)

    # Calculate work periods from message timestamps
    timestamps = [m.get("timestamp", "") for m in messages if m.get("timestamp")]
    work_seconds, num_periods = _calculate_work_periods(timestamps)

    # Delete existing data for this file
    conn.execute("DELETE FROM tool_uses WHERE file_path = ?", (file_path_str,))
    conn.execute("DELETE FROM messages WHERE file_path = ?", (file_path_str,))
    conn.execute("DELETE FROM sessions WHERE file_path = ?", (file_path_str,))

    # Insert session record
    conn.execute(
        """
        INSERT INTO sessions (
            file_path, session_id, workspace, home, source, agent,
            file_mtime, is_agent, parent_session_id,
            start_time, end_time, message_count,
            user_messages, assistant_messages,
            input_tokens, output_tokens,
            cache_creation_tokens, cache_read_tokens,
            first_timestamp, last_timestamp,
            git_branch, claude_version, cwd,
            work_period_seconds, num_work_periods
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_path_str,
            session_info.get("session_id"),
            workspace,
            source_key,
            source_key,
            agent,
            current_mtime,
            1 if session_info.get("is_agent") else 0,
            session_info.get("parent_session_id"),
            session_info.get("first_timestamp"),
            session_info.get("last_timestamp"),
            session_info.get("message_count", 0),
            session_info.get("user_messages", 0),
            session_info.get("assistant_messages", 0),
            session_info.get("input_tokens", 0),
            session_info.get("output_tokens", 0),
            session_info.get("cache_creation_tokens", 0),
            session_info.get("cache_read_tokens", 0),
            session_info.get("first_timestamp"),
            session_info.get("last_timestamp"),
            session_info.get("git_branch"),
            session_info.get("claude_version"),
            session_info.get("cwd"),
            work_seconds,
            num_periods,
        ),
    )

    # Insert message records
    for msg in messages:
        conn.execute(
            """
            INSERT INTO messages (
                uuid, file_path, session_id, parent_uuid, type, timestamp,
                model, stop_reason, input_tokens, output_tokens,
                cache_creation_tokens, cache_read_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg.get("uuid"),
                file_path_str,
                msg.get("session_id"),
                msg.get("parent_uuid"),
                msg.get("type", "unknown"),
                msg.get("timestamp", ""),
                msg.get("model"),
                msg.get("stop_reason"),
                msg.get("input_tokens", 0),
                msg.get("output_tokens", 0),
                msg.get("cache_creation_tokens", 0),
                msg.get("cache_read_tokens", 0),
            ),
        )

    # Insert tool use records
    for tu in tool_uses:
        conn.execute(
            """
            INSERT INTO tool_uses (
                tool_use_id, message_uuid, file_path, session_id,
                tool_name, is_error, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tu.get("tool_use_id"),
                tu.get("message_uuid"),
                file_path_str,
                tu.get("session_id"),
                tu.get("tool_name", "unknown"),
                tu.get("is_error", 0),
                tu.get("timestamp"),
            ),
        )

    # Update synced files tracking
    conn.execute(
        """
        INSERT OR REPLACE INTO synced_files (file_path, mtime, synced_at)
        VALUES (?, ?, ?)
        """,
        (file_path_str, current_mtime, datetime.now().isoformat()),
    )

    return True


def sync_sessions_to_db(
    conn: sqlite3.Connection,
    sessions_dir: Path,
    source_key: str = "local",
    agent: str = "claude",
    force: bool = False,
    patterns: Optional[List[str]] = None,
) -> Dict[str, int]:
    """Sync all sessions from a directory to the database.

    Args:
        conn: Database connection
        sessions_dir: Path to sessions directory (e.g., ~/.claude/projects)
        source_key: Source identifier
        agent: Registered agent backend id
        force: Force re-sync all files
        patterns: Optional list of workspace patterns to match

    Returns:
        Dict with counts: {"synced": N, "skipped": N, "errors": N}
    """
    stats = {"synced": 0, "skipped": 0, "errors": 0}

    if not sessions_dir or not sessions_dir.exists():
        return stats

    def matches_pattern(name: str) -> bool:
        if not patterns:
            return True
        name_lower = name.lower()
        for pattern in patterns:
            if pattern.lower() in name_lower:
                return True
        return False

    from agent_history.backends.registry import get_backend

    backend = get_backend(agent)
    if backend is None:
        stats["errors"] += 1
        return stats

    try:
        sessions = backend.scan_sessions(sessions_dir)
    except Exception:
        stats["errors"] += 1
        return stats

    for session in sessions:
        file_value = session.get("file")
        if not file_value:
            stats["errors"] += 1
            continue

        workspace = (
            session.get("workspace_key")
            or session.get("workspace")
            or session.get("workspace_readable")
            or ""
        )
        workspace_display = session.get("workspace_readable") or workspace
        if not (
            matches_pattern(str(workspace))
            or matches_pattern(str(workspace_display))
            or matches_pattern(str(session.get("filename", "")))
        ):
            continue

        try:
            if sync_file_to_db(
                conn,
                Path(str(file_value)),
                source_key,
                force,
                workspace=str(workspace) if workspace else None,
                agent=agent,
            ):
                stats["synced"] += 1
            else:
                stats["skipped"] += 1
        except Exception:
            stats["errors"] += 1

    conn.commit()
    return stats


def sync_scope_to_db(
    conn: sqlite3.Connection,
    scope: "ConcreteScope",
    force: bool = False,
) -> Dict[str, int]:
    """Sync all sessions referenced in a resolved scope to the database."""
    stats = {"synced": 0, "skipped": 0, "errors": 0}
    seen_paths: set[str] = set()

    for record in scope:
        home = record.home
        for session in record.sessions:
            file_value = session.get("file")
            if not file_value:
                stats["errors"] += 1
                continue

            file_path = Path(str(file_value))

            if not file_path.exists():
                if home.startswith("remote:"):
                    from agent_history.adapters.remote import SSHRemoteClient

                    remote_host = home[7:]
                    try:
                        client = SSHRemoteClient()
                        local_copy = client.ensure_local_copy(
                            remote_host, record.workspace, session
                        )
                        if local_copy:
                            file_path = local_copy
                    except Exception:
                        stats["errors"] += 1
                        continue
                elif home == "web":
                    from agent_history.backends.web import (
                        WebSessionsError,
                        ensure_web_session_cache,
                        resolve_web_credentials,
                    )

                    session_id = (
                        session.get("session_id") or session.get("id") or session.get("filename")
                    )
                    if not session_id:
                        stats["errors"] += 1
                        continue
                    try:
                        token, org_uuid = resolve_web_credentials()
                        file_path = ensure_web_session_cache(
                            str(session_id), token, org_uuid, force=force
                        )
                    except WebSessionsError:
                        stats["errors"] += 1
                        continue

            if not file_path.exists():
                stats["errors"] += 1
                continue

            file_key = str(file_path)
            if file_key in seen_paths:
                continue
            seen_paths.add(file_key)

            agent = session.get("agent") or "claude"
            try:
                synced = sync_file_to_db(
                    conn,
                    file_path,
                    source_key=home,
                    force=force,
                    workspace=record.workspace,
                    agent=agent,
                )
            except Exception:
                stats["errors"] += 1
                continue

            if synced:
                stats["synced"] += 1
            else:
                stats["skipped"] += 1

    return stats


def _install_file_scope(conn: sqlite3.Connection, file_paths: Optional[List[str]]) -> str:
    """Install a temporary file-path scope and return a sessions table suffix.

    When ``file_paths`` is ``None``, callers want the whole database. When it is
    an empty list, callers want an explicitly empty scope.
    """
    if file_paths is None:
        return ""

    conn.execute("DROP TABLE IF EXISTS temp.metric_file_scope")
    conn.execute("CREATE TEMP TABLE metric_file_scope (file_path TEXT PRIMARY KEY)")
    if file_paths:
        conn.executemany(
            "INSERT OR IGNORE INTO metric_file_scope (file_path) VALUES (?)",
            [(path,) for path in file_paths],
        )
    return " JOIN metric_file_scope fs ON fs.file_path = sessions.file_path"


def _install_tool_file_scope(conn: sqlite3.Connection, file_paths: Optional[List[str]]) -> str:
    if file_paths is None:
        return ""
    _install_file_scope(conn, file_paths)
    return " JOIN metric_file_scope fs ON fs.file_path = tool_uses.file_path"


def _normalize_file_paths(file_paths: Optional[List[str]]) -> Optional[List[str]]:
    if file_paths is None:
        return None
    return [str(path) for path in file_paths if path]


def _where_sql(filters: Optional[Dict[str, Any]], alias: str = "sessions") -> tuple[str, list[Any]]:
    if not filters:
        return "", []

    clauses: list[str] = []
    params: list[Any] = []
    prefix = f"{alias}."

    homes = filters.get("homes")
    if homes:
        placeholders = ", ".join("?" for _ in homes)
        clauses.append(f"{prefix}home IN ({placeholders})")
        params.extend(homes)

    agent = filters.get("agent")
    if agent:
        clauses.append(f"{prefix}agent = ?")
        params.append(agent)

    workspaces = filters.get("workspaces")
    if workspaces:
        placeholders = ", ".join("?" for _ in workspaces)
        clauses.append(f"{prefix}workspace IN ({placeholders})")
        params.extend(workspaces)

    workspace_patterns = filters.get("workspace_patterns")
    if workspace_patterns:
        pattern_clauses = []
        for pattern in workspace_patterns:
            pattern_clauses.append(f"LOWER({prefix}workspace) LIKE ?")
            params.append(f"%{str(pattern).lower()}%")
        clauses.append("(" + " OR ".join(pattern_clauses) + ")")

    workspace_globs = filters.get("workspace_globs")
    if workspace_globs:
        glob_clauses = []
        for pattern in workspace_globs:
            glob_clauses.append(f"{prefix}workspace GLOB ?")
            params.append(str(pattern))
        clauses.append("(" + " OR ".join(glob_clauses) + ")")

    workspace_regexes = filters.get("workspace_regexes")
    if workspace_regexes:
        regex_clauses = []
        for pattern in workspace_regexes:
            regex_clauses.append(f"{prefix}workspace REGEXP ?")
            params.append(str(pattern))
        clauses.append("(" + " OR ".join(regex_clauses) + ")")

    since = filters.get("since")
    if since:
        clauses.append(
            f"COALESCE({prefix}start_time, {prefix}first_timestamp, {prefix}last_timestamp) >= ?"
        )
        params.append(str(since))

    until = filters.get("until")
    if until:
        clauses.append(
            f"SUBSTR(COALESCE({prefix}start_time, {prefix}first_timestamp, {prefix}last_timestamp), 1, 10) <= ?"
        )
        params.append(str(until)[:10])

    if not clauses:
        return "", []
    return " WHERE " + " AND ".join(clauses), params


def get_scoped_stats_from_db(
    filters: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
    include_day: bool = False,
) -> Dict[str, Any]:
    """Get aggregate stats directly from SQLite using session predicates."""
    conn = init_metrics_db(db_path)
    try:
        where_sql, params = _where_sql(filters, "sessions")
        cursor = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(input_tokens), 0) as input_tokens,
                COALESCE(SUM(output_tokens), 0) as output_tokens,
                COALESCE(SUM(cache_creation_tokens), 0) as cache_creation_tokens,
                COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
                COUNT(*) as sessions,
                COALESCE(SUM(is_agent), 0) as agent_sessions,
                COALESCE(SUM(CASE WHEN is_agent THEN 0 ELSE 1 END), 0) as main_sessions,
                COALESCE(SUM(message_count), 0) as messages,
                COALESCE(SUM(user_messages), 0) as user_messages,
                COALESCE(SUM(assistant_messages), 0) as assistant_messages,
                COALESCE(SUM(work_period_seconds), 0) as total_seconds,
                SUM(CASE WHEN work_period_seconds > 0 THEN 1 ELSE 0 END) as sessions_with_time,
                MAX(file_mtime) as last_synced
            FROM sessions
            {where_sql}
            """,
            params,
        )
        row = cursor.fetchone()
        total_seconds = row["total_seconds"] if row else 0
        sessions_with_time = row["sessions_with_time"] if row else 0
        avg_seconds = total_seconds / sessions_with_time if sessions_with_time else 0

        by_agent = _stats_group_query(conn, "agent", where_sql, params)
        by_home = _stats_group_query(conn, "home", where_sql, params)
        by_workspace = _stats_group_query(conn, "workspace", where_sql, params)
        by_model = _model_stats_query(conn, filters)
        by_tool = _tool_stats_query(conn, filters)
        time_by_day = _time_by_day_query(conn, where_sql, params)

        stats: Dict[str, Any] = {
            "sessions": row["sessions"] if row else 0,
            "total_sessions": row["sessions"] if row else 0,
            "main_sessions": row["main_sessions"] if row else 0,
            "agent_sessions": row["agent_sessions"] if row else 0,
            "messages": row["messages"] if row else 0,
            "total_messages": row["messages"] if row else 0,
            "user_messages": row["user_messages"] if row else 0,
            "assistant_messages": row["assistant_messages"] if row else 0,
            "tokens": {
                "input": row["input_tokens"] if row else 0,
                "output": row["output_tokens"] if row else 0,
                "cache_creation": row["cache_creation_tokens"] if row else 0,
                "cache_read": row["cache_read_tokens"] if row else 0,
            },
            "by_agent": by_agent,
            "by_home": by_home,
            "by_workspace": by_workspace,
            "by_model": by_model,
            "by_tool": by_tool,
            "time_stats": {
                "total_duration_seconds": total_seconds,
                "sessions_with_time": sessions_with_time,
                "total_sessions": row["sessions"] if row else 0,
                "average_duration_seconds": avg_seconds,
                "by_day": time_by_day,
            },
            "cache": {
                "cached": True,
                "last_synced": row["last_synced"] if row else None,
            },
        }

        if include_day:
            stats["by_day"] = _day_stats_query(conn, where_sql, params)

        return stats
    finally:
        conn.close()


ROLLUP_DIMENSIONS: Dict[str, str] = {
    "project": "COALESCE(project, project_short, workspace)",
    "workspace": "workspace",
    "home": "home",
    "agent": "agent",
    "day": "SUBSTR(COALESCE(start_time, first_timestamp, last_timestamp), 1, 10)",
    "month": "SUBSTR(COALESCE(start_time, first_timestamp, last_timestamp), 1, 7)",
}

MESSAGE_ROLLUP_DIMENSIONS: Dict[str, str] = {
    "project": "COALESCE(s.project, s.project_short, s.workspace)",
    "workspace": "s.workspace",
    "home": "s.home",
    "agent": "s.agent",
    "day": "SUBSTR(COALESCE(s.start_time, s.first_timestamp, s.last_timestamp), 1, 10)",
    "month": "SUBSTR(COALESCE(s.start_time, s.first_timestamp, s.last_timestamp), 1, 7)",
    "model": "m.model",
}

ROLLUP_DIMENSION_ALIASES: Dict[str, str] = {
    "ws": "workspace",
    "workspaces": "workspace",
    "proj": "project",
    "projects": "project",
    "homes": "home",
    "agents": "agent",
    "days": "day",
    "months": "month",
    "models": "model",
    "tools": "tool",
}

ROLLUP_SORT_ALIASES: Dict[str, str] = {
    "metric": "metric",
    "value": "metric",
    "tokens": "tokens",
    "token": "tokens",
    "total_tokens": "tokens",
    "time": "time_seconds",
    "time_seconds": "time_seconds",
    "seconds": "time_seconds",
    "hours": "time_hours",
    "time_hours": "time_hours",
    "sessions": "sessions",
    "session": "sessions",
    "messages": "messages",
    "message": "messages",
    "input": "input_tokens",
    "input_tokens": "input_tokens",
    "output": "output_tokens",
    "output_tokens": "output_tokens",
    "cache_read": "cache_read_tokens",
    "cache_read_tokens": "cache_read_tokens",
    "cache_create": "cache_creation_tokens",
    "cache_creation": "cache_creation_tokens",
    "cache_creation_tokens": "cache_creation_tokens",
}


def get_stats_rollup_from_db(
    filters: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
    by: Optional[List[str]] = None,
    metric: str = "all",
    top: Optional[int] = None,
    sort_by: Optional[List[str]] = None,
    sort_direction: str = "default",
) -> list[Dict[str, Any]]:
    """Return DB-backed stats rollup rows grouped by requested dimensions."""
    dimensions = _normalize_rollup_dimensions(by or ["project"])
    dimension_map = MESSAGE_ROLLUP_DIMENSIONS if "model" in dimensions else ROLLUP_DIMENSIONS
    invalid = [dimension for dimension in dimensions if dimension not in dimension_map]
    if invalid:
        raise ValueError(f"Unsupported rollup dimension(s): {', '.join(invalid)}")
    if metric not in {"time", "tokens", "all"}:
        raise ValueError(f"Unsupported rollup metric: {metric}")
    if metric == "time" and "model" in dimensions:
        raise ValueError(
            "Unsupported rollup: --metric time cannot be grouped by model because "
            "time is tracked per session, not per message/model. Use tokens by model, "
            "or time by project/workspace/agent/month/day."
        )

    conn = init_metrics_db(db_path)
    try:
        if "model" in dimensions:
            return _message_stats_rollup(
                conn, filters, dimensions, metric, top, sort_by, sort_direction
            )

        where_sql, params = _where_sql(filters, "sessions")
        select_parts = [
            f"{ROLLUP_DIMENSIONS[dimension]} AS dim_{index}"
            for index, dimension in enumerate(dimensions)
        ]
        group_parts = [f"dim_{index}" for index in range(len(dimensions))]
        sql = f"""
            SELECT
                {", ".join(select_parts)},
                COUNT(*) as sessions,
                COALESCE(SUM(message_count), 0) as messages,
                COALESCE(SUM(input_tokens), 0) as input_tokens,
                COALESCE(SUM(output_tokens), 0) as output_tokens,
                COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
                COALESCE(SUM(cache_creation_tokens), 0) as cache_creation_tokens,
                COALESCE(SUM(work_period_seconds), 0) as time_seconds
            FROM sessions
            {where_sql}
            GROUP BY {", ".join(group_parts)}
        """
        cursor = conn.execute(sql, params)
        rows: list[Dict[str, Any]] = []
        for row in cursor.fetchall():
            if _skip_rollup_row(row, dimensions, metric):
                continue
            item: Dict[str, Any] = {
                "sessions": row["sessions"],
                "messages": row["messages"],
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "cache_read_tokens": row["cache_read_tokens"],
                "cache_creation_tokens": row["cache_creation_tokens"],
                "time_seconds": row["time_seconds"],
                "time_hms": _format_seconds_hms(row["time_seconds"]),
                "time_hours": row["time_seconds"] / 3600 if row["time_seconds"] else 0,
            }
            for index, dimension in enumerate(dimensions):
                item[dimension] = row[f"dim_{index}"] or "(none)"
            rows.append(item)
        return _sort_and_limit_rollup_rows(rows, dimensions, metric, top, sort_by, sort_direction)
    finally:
        conn.close()


def _normalize_rollup_dimensions(dimensions: list[str]) -> list[str]:
    normalized: list[str] = []
    for dimension in dimensions:
        canonical = ROLLUP_DIMENSION_ALIASES.get(dimension, dimension)
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized


def _message_stats_rollup(
    conn: sqlite3.Connection,
    filters: Optional[Dict[str, Any]],
    dimensions: list[str],
    metric: str,
    top: Optional[int],
    sort_by: Optional[list[str]],
    sort_direction: str,
) -> list[Dict[str, Any]]:
    where_sql, params = _where_sql(filters, "s")
    model_filter = "m.model IS NOT NULL AND m.model != ''"
    if where_sql:
        where_sql += f" AND {model_filter}"
    else:
        where_sql = f" WHERE {model_filter}"
    select_parts = [
        f"{MESSAGE_ROLLUP_DIMENSIONS[dimension]} AS dim_{index}"
        for index, dimension in enumerate(dimensions)
    ]
    group_parts = [f"dim_{index}" for index in range(len(dimensions))]
    sql = f"""
        SELECT
            {", ".join(select_parts)},
            COUNT(DISTINCT s.file_path) as sessions,
            COUNT(*) as messages,
            COALESCE(SUM(m.input_tokens), 0) as input_tokens,
            COALESCE(SUM(m.output_tokens), 0) as output_tokens,
            COALESCE(SUM(m.cache_read_tokens), 0) as cache_read_tokens,
            COALESCE(SUM(m.cache_creation_tokens), 0) as cache_creation_tokens,
            0 as time_seconds
        FROM messages m
        JOIN sessions s ON s.file_path = m.file_path
        {where_sql}
        GROUP BY {", ".join(group_parts)}
    """
    cursor = conn.execute(sql, params)
    rows: list[Dict[str, Any]] = []
    for row in cursor.fetchall():
        if _skip_rollup_row(row, dimensions, metric):
            continue
        item: Dict[str, Any] = {
            "sessions": row["sessions"],
            "messages": row["messages"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "cache_read_tokens": row["cache_read_tokens"],
            "cache_creation_tokens": row["cache_creation_tokens"],
            "time_seconds": None,
            "time_hms": None,
            "time_hours": None,
        }
        for index, dimension in enumerate(dimensions):
            item[dimension] = row[f"dim_{index}"] or "(none)"
        rows.append(item)
    return _sort_and_limit_rollup_rows(rows, dimensions, metric, top, sort_by, sort_direction)


def _skip_rollup_row(row: sqlite3.Row, dimensions: list[str], metric: str) -> bool:
    """Return True when a rollup bucket has no useful metric value."""
    if metric == "time" and not row["time_seconds"]:
        return True
    if metric == "tokens" and _rollup_metric_total(row, metric) == 0:
        return True
    if (
        any(
            dimension in {"day", "month"} and not row[f"dim_{index}"]
            for index, dimension in enumerate(dimensions)
        )
        and _rollup_metric_total(row, metric) == 0
    ):
        return True
    return False


def _rollup_metric_total(row: sqlite3.Row, metric: str) -> float:
    if metric == "time":
        return float(row["time_seconds"] or 0)
    if metric == "tokens":
        return float(
            (row["input_tokens"] or 0)
            + (row["output_tokens"] or 0)
            + (row["cache_read_tokens"] or 0)
            + (row["cache_creation_tokens"] or 0)
        )
    return float(
        (row["time_seconds"] or 0)
        + (row["input_tokens"] or 0)
        + (row["output_tokens"] or 0)
        + (row["cache_read_tokens"] or 0)
        + (row["cache_creation_tokens"] or 0)
        + (row["messages"] or 0)
        + (row["sessions"] or 0)
    )


def _format_seconds_hms(value: Any) -> str:
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return ""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def _sort_and_limit_rollup_rows(
    rows: list[Dict[str, Any]],
    dimensions: list[str],
    metric: str,
    top: Optional[int],
    sort_by: Optional[list[str]],
    sort_direction: str,
) -> list[Dict[str, Any]]:
    sort_fields = _normalize_rollup_sort_fields(sort_by, dimensions, metric)
    reverse = _rollup_sort_reverse(sort_by, sort_direction, dimensions)
    sorted_rows = sorted(
        rows,
        key=lambda row: tuple(_rollup_sort_value(row, field, metric) for field in sort_fields),
        reverse=reverse,
    )
    if top:
        return sorted_rows[:top]
    return sorted_rows


def _normalize_rollup_sort_fields(
    sort_by: Optional[list[str]], dimensions: list[str], metric: str
) -> list[str]:
    if not sort_by:
        if dimensions and all(dimension in {"day", "month"} for dimension in dimensions):
            return dimensions
        return ["metric"]

    fields: list[str] = []
    valid_dimensions = set(ROLLUP_DIMENSIONS) | {"model"}
    for raw_field in sort_by:
        field = raw_field.strip().lower().replace("-", "_")
        field = ROLLUP_DIMENSION_ALIASES.get(field, field)
        field = ROLLUP_SORT_ALIASES.get(field, field)
        if field in valid_dimensions or field in ROLLUP_SORT_ALIASES.values():
            if field not in fields:
                fields.append(field)
            continue
        raise ValueError(f"Unsupported rollup sort field: {raw_field}")
    return fields or _normalize_rollup_sort_fields(None, dimensions, metric)


def _rollup_sort_reverse(
    sort_by: Optional[list[str]], sort_direction: str, dimensions: list[str]
) -> bool:
    if sort_direction == "asc":
        return False
    if sort_direction == "desc":
        return True
    if sort_by:
        return False
    return not (dimensions and all(dimension in {"day", "month"} for dimension in dimensions))


def _rollup_sort_value(row: Dict[str, Any], field: str, metric: str) -> Any:
    if field == "metric":
        return _row_metric_total(row, metric)
    if field == "tokens":
        return _row_metric_total(row, "tokens")
    value = row.get(field)
    if field in {
        "time_seconds",
        "time_hours",
        "sessions",
        "messages",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
    }:
        return float(value or 0)
    return "" if value is None else str(value)


def _row_metric_total(row: Dict[str, Any], metric: str) -> float:
    if metric == "time":
        return float(row.get("time_seconds") or 0)
    if metric == "tokens":
        return float(
            (row.get("input_tokens") or 0)
            + (row.get("output_tokens") or 0)
            + (row.get("cache_read_tokens") or 0)
            + (row.get("cache_creation_tokens") or 0)
        )
    return float(
        (row.get("time_seconds") or 0)
        + (row.get("input_tokens") or 0)
        + (row.get("output_tokens") or 0)
        + (row.get("cache_read_tokens") or 0)
        + (row.get("cache_creation_tokens") or 0)
        + (row.get("messages") or 0)
        + (row.get("sessions") or 0)
    )


def _rollup_order_sql(dimensions: list[str], metric: str, message_query: bool = False) -> str:
    if dimensions and all(dimension in {"day", "month"} for dimension in dimensions):
        return " ORDER BY " + ", ".join(f"dim_{index}" for index in range(len(dimensions)))
    if message_query and metric == "tokens":
        return (
            " ORDER BY (COALESCE(SUM(m.input_tokens), 0) + "
            "COALESCE(SUM(m.output_tokens), 0) + "
            "COALESCE(SUM(m.cache_read_tokens), 0) + "
            "COALESCE(SUM(m.cache_creation_tokens), 0)) DESC"
        )
    if message_query and metric == "all":
        return (
            " ORDER BY (COALESCE(SUM(m.input_tokens), 0) + "
            "COALESCE(SUM(m.output_tokens), 0)) DESC, sessions DESC"
        )
    if metric == "time":
        return " ORDER BY time_seconds DESC"
    if metric == "tokens":
        return " ORDER BY (input_tokens + output_tokens + cache_read_tokens + cache_creation_tokens) DESC"
    return " ORDER BY time_seconds DESC, (input_tokens + output_tokens) DESC, sessions DESC"


def _stats_group_query(
    conn: sqlite3.Connection, column: str, where_sql: str, params: list[Any]
) -> Dict[str, Dict[str, int]]:
    cursor = conn.execute(
        f"""
        SELECT {column} as name,
               COUNT(*) as sessions,
               COALESCE(SUM(message_count), 0) as messages
        FROM sessions
        {where_sql}
        GROUP BY {column}
        ORDER BY sessions DESC
        """,
        params,
    )
    return {
        row["name"]: {"sessions": row["sessions"], "messages": row["messages"]}
        for row in cursor.fetchall()
        if row["name"]
    }


def _model_stats_query(
    conn: sqlite3.Connection, filters: Optional[Dict[str, Any]]
) -> Dict[str, Dict[str, int]]:
    where_sql, params = _where_sql(filters, "s")
    if where_sql:
        where_sql += " AND m.model IS NOT NULL AND m.model != ''"
    else:
        where_sql = " WHERE m.model IS NOT NULL AND m.model != ''"
    cursor = conn.execute(
        f"""
        SELECT m.model,
               COUNT(*) as messages,
               COALESCE(SUM(m.output_tokens), 0) as tokens
        FROM messages m
        JOIN sessions s ON s.file_path = m.file_path
        {where_sql}
        GROUP BY m.model
        ORDER BY messages DESC
        """,
        params,
    )
    return {
        row["model"]: {"messages": row["messages"], "tokens": row["tokens"]}
        for row in cursor.fetchall()
        if row["model"]
    }


def _tool_stats_query(
    conn: sqlite3.Connection, filters: Optional[Dict[str, Any]]
) -> Dict[str, Dict[str, int]]:
    where_sql, params = _where_sql(filters, "s")
    cursor = conn.execute(
        f"""
        SELECT t.tool_name,
               COUNT(*) as uses,
               COALESCE(SUM(t.is_error), 0) as errors
        FROM tool_uses t
        JOIN sessions s ON s.file_path = t.file_path
        {where_sql}
        GROUP BY t.tool_name
        ORDER BY uses DESC
        """,
        params,
    )
    return {
        row["tool_name"]: {"uses": row["uses"], "errors": row["errors"]}
        for row in cursor.fetchall()
        if row["tool_name"]
    }


def _time_by_day_query(
    conn: sqlite3.Connection, where_sql: str, params: list[Any]
) -> Dict[str, float]:
    day_filter = "first_timestamp IS NOT NULL AND work_period_seconds > 0"
    scoped_where = where_sql
    if scoped_where:
        scoped_where += f" AND {day_filter}"
    else:
        scoped_where = f" WHERE {day_filter}"
    cursor = conn.execute(
        f"""
        SELECT SUBSTR(first_timestamp, 1, 10) as day,
               COALESCE(SUM(work_period_seconds), 0) as total_seconds
        FROM sessions
        {scoped_where}
        GROUP BY day
        ORDER BY day
        """,
        params,
    )
    return {row["day"]: row["total_seconds"] for row in cursor.fetchall() if row["day"]}


def _day_stats_query(
    conn: sqlite3.Connection, where_sql: str, params: list[Any]
) -> Dict[str, Dict[str, int]]:
    day_filter = "first_timestamp IS NOT NULL"
    scoped_where = where_sql
    if scoped_where:
        scoped_where += f" AND {day_filter}"
    else:
        scoped_where = f" WHERE {day_filter}"
    cursor = conn.execute(
        f"""
        SELECT SUBSTR(first_timestamp, 1, 10) as day,
               COUNT(*) as sessions,
               COALESCE(SUM(message_count), 0) as messages
        FROM sessions
        {scoped_where}
        GROUP BY day
        ORDER BY day
        """,
        params,
    )
    return {
        row["day"]: {"sessions": row["sessions"], "messages": row["messages"]}
        for row in cursor.fetchall()
        if row["day"]
    }


def get_session_stats_from_db(
    db_path: Optional[Path] = None,
    file_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Get aggregated session statistics from the metrics database.

    Returns aggregate totals for all sessions in the database, including
    token counts, message counts, and session counts.

    Args:
        db_path: Optional path to metrics database. Defaults to standard location.

    Returns:
        Dictionary containing:
        - input_tokens: Total input tokens across all sessions
        - output_tokens: Total output tokens across all sessions
        - cache_creation_tokens: Total cache creation tokens
        - cache_read_tokens: Total cache read tokens
        - sessions: Total session count
        - messages: Total message count
        - user_messages: Total user message count
        - assistant_messages: Total assistant message count
    """
    file_paths = _normalize_file_paths(file_paths)
    conn = init_metrics_db(db_path)
    try:
        scope_join = _install_file_scope(conn, file_paths)
        cursor = conn.execute(f"""
            SELECT
                COALESCE(SUM(input_tokens), 0) as input_tokens,
                COALESCE(SUM(output_tokens), 0) as output_tokens,
                COALESCE(SUM(cache_creation_tokens), 0) as cache_creation_tokens,
                COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
                COUNT(*) as sessions,
                COALESCE(SUM(message_count), 0) as messages,
                COALESCE(SUM(user_messages), 0) as user_messages,
                COALESCE(SUM(assistant_messages), 0) as assistant_messages
            FROM sessions
            {scope_join}
        """)
        row = cursor.fetchone()

        by_agent_cursor = conn.execute(f"""
            SELECT agent, COUNT(*) as sessions, COALESCE(SUM(message_count), 0) as messages
            FROM sessions
            {scope_join}
            GROUP BY agent
            ORDER BY sessions DESC
        """)
        by_home_cursor = conn.execute(f"""
            SELECT home, COUNT(*) as sessions, COALESCE(SUM(message_count), 0) as messages
            FROM sessions
            {scope_join}
            GROUP BY home
            ORDER BY sessions DESC
        """)
        by_workspace_cursor = conn.execute(f"""
            SELECT workspace, COUNT(*) as sessions, COALESCE(SUM(message_count), 0) as messages
            FROM sessions
            {scope_join}
            GROUP BY workspace
            ORDER BY sessions DESC
        """)
        by_model_cursor = conn.execute(
            """
            SELECT model,
                   COUNT(*) as messages,
                   COALESCE(SUM(output_tokens), 0) as tokens
            FROM messages
            """
            + (
                " JOIN metric_file_scope fs ON fs.file_path = messages.file_path"
                if file_paths is not None
                else ""
            )
            + """
            WHERE model IS NOT NULL AND model != ''
            GROUP BY model
            ORDER BY messages DESC
            """
        )
        return {
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "cache_creation_tokens": row["cache_creation_tokens"],
            "cache_read_tokens": row["cache_read_tokens"],
            "sessions": row["sessions"],
            "messages": row["messages"],
            "user_messages": row["user_messages"],
            "assistant_messages": row["assistant_messages"],
            "by_agent": {
                row["agent"]: {"sessions": row["sessions"], "messages": row["messages"]}
                for row in by_agent_cursor.fetchall()
                if row["agent"]
            },
            "by_home": {
                row["home"]: {"sessions": row["sessions"], "messages": row["messages"]}
                for row in by_home_cursor.fetchall()
                if row["home"]
            },
            "by_workspace": {
                row["workspace"]: {"sessions": row["sessions"], "messages": row["messages"]}
                for row in by_workspace_cursor.fetchall()
                if row["workspace"]
            },
            "by_model": {
                row["model"]: {"messages": row["messages"], "tokens": row["tokens"]}
                for row in by_model_cursor.fetchall()
                if row["model"]
            },
        }
    finally:
        conn.close()


def get_tool_usage_stats_from_db(
    db_path: Optional[Path] = None,
    file_paths: Optional[List[str]] = None,
) -> Dict[str, Dict[str, int]]:
    """Get aggregated tool usage statistics from the metrics database."""
    file_paths = _normalize_file_paths(file_paths)
    conn = init_metrics_db(db_path)
    try:
        scope_join = _install_tool_file_scope(conn, file_paths)
        cursor = conn.execute(
            f"""
            SELECT tool_name,
                   COUNT(*) as uses,
                   COALESCE(SUM(is_error), 0) as errors
            FROM tool_uses
            {scope_join}
            GROUP BY tool_name
            """
        )
        return {
            row["tool_name"]: {"uses": row["uses"], "errors": row["errors"]}
            for row in cursor.fetchall()
            if row["tool_name"]
        }
    finally:
        conn.close()


def get_time_stats_from_db(
    db_path: Optional[Path] = None,
    file_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Get aggregated time statistics from the metrics database."""
    file_paths = _normalize_file_paths(file_paths)
    conn = init_metrics_db(db_path)
    try:
        scope_join = _install_file_scope(conn, file_paths)
        cursor = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(work_period_seconds), 0) as total_seconds,
                SUM(CASE WHEN work_period_seconds > 0 THEN 1 ELSE 0 END) as sessions_with_time,
                COUNT(*) as total_sessions
            FROM sessions
            {scope_join}
            """
        )
        row = cursor.fetchone()
        total_seconds = row["total_seconds"] if row else 0
        sessions_with_time = row["sessions_with_time"] if row else 0
        total_sessions = row["total_sessions"] if row else 0
        avg_seconds = total_seconds / sessions_with_time if sessions_with_time else 0

        day_cursor = conn.execute(
            f"""
            SELECT SUBSTR(first_timestamp, 1, 10) as day,
                   COALESCE(SUM(work_period_seconds), 0) as total_seconds
            FROM sessions
            {scope_join}
            WHERE first_timestamp IS NOT NULL AND work_period_seconds > 0
            GROUP BY day
            """
        )
        by_day = {row["day"]: row["total_seconds"] for row in day_cursor.fetchall() if row["day"]}

        return {
            "total_duration_seconds": total_seconds,
            "sessions_with_time": sessions_with_time,
            "total_sessions": total_sessions,
            "average_duration_seconds": avg_seconds,
            "by_day": by_day,
        }
    finally:
        conn.close()
