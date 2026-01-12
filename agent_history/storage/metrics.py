"""Metrics database for agent-history.

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
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent_history.storage.config import get_config_dir

__all__ = [
    "get_metrics_db_path",
    "init_metrics_db",
    "sync_file_to_db",
    "sync_sessions_to_db",
    "get_session_stats_from_db",
    "get_tool_usage_stats_from_db",
    "get_time_stats_from_db",
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
        db_path: Path to database file. Defaults to ~/.agent-history/metrics.db

    Returns:
        Open sqlite3.Connection with row_factory set to sqlite3.Row

    Side Effects:
        - Creates parent directory (~/.agent-history/) with mode 0o700 if missing
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
            for line in f:
                line = line.strip()
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
            for line in f:
                line = line.strip()
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
                        info = payload.get("info", {})
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
    config_dir_override = os.environ.get("AGENT_HISTORY_CONFIG_DIR")
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
        agent: Agent type (claude, codex, gemini)

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

    # Parse the file based on agent type
    if agent == "codex":
        session_info, messages, tool_uses = _parse_codex_jsonl(jsonl_file)
    elif agent == "gemini":
        session_info, messages, tool_uses = _parse_gemini_json(jsonl_file)
    else:
        # Default to Claude format
        session_info, messages, tool_uses = _parse_claude_jsonl(jsonl_file)

    # Determine workspace - prefer metadata over passed value
    if agent == "codex" and session_info.get("cwd"):
        # Codex: use session_meta.cwd
        workspace = session_info["cwd"]
    elif agent == "gemini":
        # Gemini: try hash index lookup
        hash_dir = jsonl_file.parent.parent  # .../hash/chats/file.json -> .../hash
        project_hash = hash_dir.name if hash_dir.name else None
        if project_hash:
            resolved = _lookup_gemini_hash(project_hash)
            if resolved:
                workspace = resolved
            elif workspace is None:
                workspace = jsonl_file.parent.name
    elif workspace is None:
        workspace = jsonl_file.parent.name

    # Calculate work periods from message timestamps
    timestamps = [m["timestamp"] for m in messages if m["timestamp"]]
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
            session_info["session_id"],
            workspace,
            source_key,
            source_key,
            agent,
            current_mtime,
            1 if session_info["is_agent"] else 0,
            session_info["parent_session_id"],
            session_info["first_timestamp"],
            session_info["last_timestamp"],
            session_info["message_count"],
            session_info["user_messages"],
            session_info["assistant_messages"],
            session_info["input_tokens"],
            session_info["output_tokens"],
            session_info["cache_creation_tokens"],
            session_info["cache_read_tokens"],
            session_info["first_timestamp"],
            session_info["last_timestamp"],
            session_info["git_branch"],
            session_info["claude_version"],
            session_info["cwd"],
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
                msg["uuid"],
                file_path_str,
                msg["session_id"],
                msg["parent_uuid"],
                msg["type"],
                msg["timestamp"],
                msg["model"],
                msg["stop_reason"],
                msg["input_tokens"],
                msg["output_tokens"],
                msg["cache_creation_tokens"],
                msg["cache_read_tokens"],
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
                tu["tool_use_id"],
                tu["message_uuid"],
                file_path_str,
                tu["session_id"],
                tu["tool_name"],
                tu["is_error"],
                tu["timestamp"],
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
        agent: Agent type
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

    # For Claude: iterate over workspace directories
    if agent == "claude":
        for workspace_dir in sessions_dir.iterdir():
            if not workspace_dir.is_dir():
                continue
            if not matches_pattern(workspace_dir.name):
                continue
            # Skip cached workspaces
            dir_name = workspace_dir.name
            if dir_name.startswith("remote_") or dir_name.startswith("wsl_"):
                continue

            for jsonl_file in workspace_dir.glob("*.jsonl"):
                try:
                    if sync_file_to_db(
                        conn,
                        jsonl_file,
                        source_key,
                        force,
                        workspace=workspace_dir.name,
                        agent=agent,
                    ):
                        stats["synced"] += 1
                    else:
                        stats["skipped"] += 1
                except Exception:
                    stats["errors"] += 1

    # For Codex: iterate over date directories
    elif agent == "codex":
        for year_dir in sessions_dir.iterdir():
            if not year_dir.is_dir():
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                for day_dir in month_dir.iterdir():
                    if not day_dir.is_dir():
                        continue
                    for jsonl_file in day_dir.glob("*.jsonl"):
                        # Extract workspace from filename
                        workspace = jsonl_file.stem.rsplit("-", 1)[0]
                        if not matches_pattern(workspace):
                            continue
                        try:
                            if sync_file_to_db(
                                conn,
                                jsonl_file,
                                source_key,
                                force,
                                workspace=workspace,
                                agent=agent,
                            ):
                                stats["synced"] += 1
                            else:
                                stats["skipped"] += 1
                        except Exception:
                            stats["errors"] += 1

    # For Gemini: iterate over hash directories
    elif agent == "gemini":
        for hash_dir in sessions_dir.iterdir():
            if not hash_dir.is_dir():
                continue
            chats_dir = hash_dir / "chats"
            if not chats_dir.exists():
                continue
            for json_file in chats_dir.glob("*.json"):
                # Extract workspace from filename
                workspace = json_file.stem
                if not matches_pattern(workspace):
                    continue
                try:
                    if sync_file_to_db(
                        conn,
                        json_file,
                        source_key,
                        force,
                        workspace=workspace,
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
                        local_copy = client.ensure_local_copy(remote_host, record.workspace, session)
                        if local_copy:
                            file_path = local_copy
                    except Exception:
                        stats["errors"] += 1
                        continue
                elif home == "web":
                    from agent_history.backends.web import WebSessionsError, ensure_web_session_cache
                    from agent_history.backends.web import resolve_web_credentials

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


def get_session_stats_from_db(db_path: Optional[Path] = None) -> Dict[str, Any]:
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
    conn = init_metrics_db(db_path)
    try:
        cursor = conn.execute("""
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
        """)
        row = cursor.fetchone()
        return {
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "cache_creation_tokens": row["cache_creation_tokens"],
            "cache_read_tokens": row["cache_read_tokens"],
            "sessions": row["sessions"],
            "messages": row["messages"],
            "user_messages": row["user_messages"],
            "assistant_messages": row["assistant_messages"],
        }
    finally:
        conn.close()


def get_tool_usage_stats_from_db(db_path: Optional[Path] = None) -> Dict[str, Dict[str, int]]:
    """Get aggregated tool usage statistics from the metrics database."""
    conn = init_metrics_db(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT tool_name,
                   COUNT(*) as uses,
                   COALESCE(SUM(is_error), 0) as errors
            FROM tool_uses
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


def get_time_stats_from_db(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Get aggregated time statistics from the metrics database."""
    conn = init_metrics_db(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT
                COALESCE(SUM(work_period_seconds), 0) as total_seconds,
                SUM(CASE WHEN work_period_seconds > 0 THEN 1 ELSE 0 END) as sessions_with_time
            FROM sessions
            """
        )
        row = cursor.fetchone()
        total_seconds = row["total_seconds"] if row else 0
        sessions_with_time = row["sessions_with_time"] if row else 0
        avg_seconds = total_seconds / sessions_with_time if sessions_with_time else 0

        day_cursor = conn.execute(
            """
            SELECT SUBSTR(first_timestamp, 1, 10) as day,
                   COALESCE(SUM(work_period_seconds), 0) as total_seconds
            FROM sessions
            WHERE first_timestamp IS NOT NULL AND work_period_seconds > 0
            GROUP BY day
            """
        )
        by_day = {
            row["day"]: row["total_seconds"]
            for row in day_cursor.fetchall()
            if row["day"]
        }

        return {
            "total_duration_seconds": total_seconds,
            "sessions_with_time": sessions_with_time,
            "average_duration_seconds": avg_seconds,
            "by_day": by_day,
        }
    finally:
        conn.close()
