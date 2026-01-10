# Agent-History Code Architecture & Analysis

## Overview
`agent-history` is a comprehensive Python 3 CLI tool (19,545 lines) for managing and exporting AI coding assistant conversation sessions from Claude Code, Codex CLI, and Gemini CLI. It provides workspace organization, session filtering, statistics aggregation, export capabilities, and statistics synchronization across local, WSL, Windows, and remote SSH environments.

**Version:** 1.5.1 | **Unified Schema Version:** 2.0

---

## High-Level Architecture

The script is organized into 8 major sections:

| Section | Lines | Purpose |
|---------|-------|---------|
| Configuration & Types | 1-630 | CLI parsing, dataclasses, TypedDicts |
| Input Validation | 663-950 | Workspace/host validation, path safety |
| Pattern Matching | 983-1300 | Unified filtering across backends |
| Output Formatting | 1493-1900 | TablePrinter, session formatting |
| Message Processing | 1950-3045 | JSONL parsing, Markdown generation |
| Backend Modules | 2929-5725 | Codex, Gemini, Claude backends |
| Cross-Platform | 5727-6100 | WSL, Windows, SSH support |
| Data Persistence | 7600-12831 | Config, SQLite metrics DB |
| Command Dispatch | 17337-19545 | CLI routing, subcommands |

---

## Key Functions by Category

### Entry Points

| Function | Line | Purpose |
|----------|------|---------|
| `main()` | 19501 | CLI entry point; handles argv parsing and command dispatch |
| `_dispatch_command(args)` | 19411 | Routes parsed args to appropriate command handler |
| `_create_argument_parser()` | 17337 | Builds complete argparse ArgumentParser |

### Command Handlers

| Function | Line | Purpose |
|----------|------|---------|
| `cmd_list(args)` | 13753 | List workspaces/sessions from single backend |
| `cmd_lsh(args)` | 15256 | List saved home directories |
| `cmd_stats(args)` | 11970 | Display aggregated statistics from metrics DB |
| `cmd_stats_sync(args)` | 11633 | Sync metrics from session files to database |
| `cmd_export_all(args)` | 16245 | Batch export from all homes/backends |
| `cmd_project_*()` | 9230+ | Project alias management |
| `cmd_gemini_index(args)` | 15831 | Manage Gemini hash-to-path index |
| `cmd_reset(args)` | 15750 | Reset databases/caches |

### Session Scanning (Backend-Agnostic)

| Function | Line | Purpose |
|----------|------|---------|
| `get_unified_sessions()` | 4728 | Query sessions from active backends with filtering |
| `_scan_backend()` | 4665 | Scan single backend (Claude/Codex/Gemini) |
| `get_active_backends()` | 4636 | Determine which backends exist |
| `collect_sessions_with_dedup()` | 1421 | Deduplicate sessions across backends |

### Claude Backend

| Function | Line | Purpose |
|----------|------|---------|
| `get_workspace_sessions()` | 5670 | Scan `~/.claude/projects/` for sessions |
| `_get_session_from_file()` | 5597 | Build session dict from JSONL file |
| `_normalize_role()` | 4099 | Normalize message role across formats |
| `_claude_message_to_unified()` | 4150 | Convert Claude message to unified format |

### Codex Backend

| Function | Line | Purpose |
|----------|------|---------|
| `codex_scan_sessions()` | 3361 | Scan `~/.codex/sessions/YYYY/MM/DD/` |
| `codex_read_jsonl_messages()` | 2985 | Parse Codex JSONL envelope format |
| `codex_extract_content()` | 2934 | Extract text from Codex message payload |
| `codex_load_index()` / `codex_save_index()` | 3281/3324 | Manage session index |

### Gemini Backend

| Function | Line | Purpose |
|----------|------|---------|
| `gemini_scan_sessions()` | 4571 | Scan `~/.gemini/tmp/<hash>/chats/` |
| `gemini_get_workspace_readable()` | 4063 | Map hash to readable path |
| `gemini_compute_project_hash()` | 4005 | SHA-256 hash matching Gemini CLI |
| `gemini_load_hash_index()` / `gemini_save_hash_index()` | 3970/3997 | Manage hash-to-path index |

### Metrics Database

| Function | Line | Purpose |
|----------|------|---------|
| `init_metrics_db()` | 10329 | Initialize SQLite database with schema |
| `_run_metrics_db_migrations()` | 10492 | Handle version upgrades |
| `_compute_session_aggregates()` | 10875 | Calculate message/token stats |
| `_compute_time_stats()` | 12831 | Aggregate time-based statistics |

### Export & Markdown Generation

| Function | Line | Purpose |
|----------|------|---------|
| `parse_jsonl_to_markdown()` | 2620 | Convert JSONL to Markdown |
| `generate_markdown_for_messages()` | 2886 | Generate message content blocks |
| `find_best_split_point()` | 2250 | Smart conversation splitting |
| `analyze_conversation_graph()` | 2381 | Detect conversation forks/branches |

### Output Formatting

| Function | Line | Purpose |
|----------|------|---------|
| `print_sessions_output()` | 1815 | Print sessions with formatting |
| `TablePrinter.print()` | 1631 | Output table in TSV/JSON/console format |

### Workspace/Path Handling

| Function | Line | Purpose |
|----------|------|---------|
| `normalize_workspace_name()` | (imported) | Decode Claude-encoded paths |
| `_matches_workspace_pattern()` | 1140 | Pattern matching with readable name lookup |
| `matches_any_pattern()` | 1020 | Check workspace against pattern list |

### WSL/Windows Access

| Function | Line | Purpose |
|----------|------|---------|
| `get_windows_home_from_wsl()` | 5810 | Discover Windows home from WSL |
| `_find_user_home_on_drives()` | 5742 | Scan /mnt for Windows users |
| `get_windows_users_with_claude()` | 5884 | Find all Windows users with Claude |

---

## Data Flow

### Session Discovery Flow
```
main()
  -> _dispatch_command(args)
    -> cmd_list() or cmd_lsh()
      -> get_unified_sessions()
        -> get_active_backends()
        -> _scan_backend() [Claude, Codex, Gemini in parallel]
          -> codex_scan_sessions() / gemini_scan_sessions() / get_workspace_sessions()
        -> collect_sessions_with_dedup()
        -> Sort by modification time
```

### Export Flow
```
main()
  -> _dispatch_command(args)
    -> _dispatch_export(args)
      -> For each workspace:
        -> get_session_from_workspace()
        -> parse_jsonl_to_markdown()
          -> read_jsonl_messages()
          -> find_best_split_point() [if --split]
          -> generate_markdown_for_messages()
        -> Write to output directory
```

### Metrics Sync Flow
```
main()
  -> cmd_stats_sync()
    -> init_metrics_db()
    -> For each workspace:
      -> get_workspace_sessions()
      -> For each session file:
        -> parse_jsonl_to_metrics()
        -> INSERT into sessions/messages/tool_uses tables
    -> conn.commit()
```

---

## Key Data Structures

### Session Dictionary
```python
{
    "agent": "claude|codex|gemini",
    "workspace": str,              # Encoded or real path
    "workspace_readable": str,     # Human-readable path
    "file": Path,                  # Absolute path to session file
    "filename": str,
    "message_count": int,
    "modified": datetime,
    "source": str,                 # "local", "remote:<host>", "wsl:<distro>"
    "home": str,                   # "local", "windows", "wsl", "<hostname>"
}
```

### Metrics Database Schema (v7)
```
sessions (file_path PRIMARY KEY)
  - workspace, home, source, agent
  - message_count, user_messages, assistant_messages
  - input_tokens, output_tokens, cache_*_tokens
  - start_time, end_time, work_period_seconds
  - git_branch, git_remote_url, project

messages (file_path FOREIGN KEY)
  - uuid, type, timestamp, model, stop_reason
  - input_tokens, output_tokens

tool_uses (file_path FOREIGN KEY)
  - tool_name, tool_use_id, is_error, timestamp

synced_files (incremental tracking)
  - file_path, mtime, synced_at
```

---

## Important Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `__version__` | 1.5.1 | Script version |
| `UNIFIED_SCHEMA_VERSION` | 2.0 | Schema version for exports |
| `METRICS_DB_VERSION` | 7 | Database schema version |
| `DEFAULT_MAX_JOBS` | 2 | Parallel worker threads |

---

## Architecture Patterns

### Backend Abstraction
Each backend (Claude, Codex, Gemini) implements:
- `<backend>_scan_sessions()` - List sessions with filtering
- `<backend>_get_workspace_readable()` - Human-readable paths
- `<backend>_count_messages()` - Message statistics
- `<backend>_read_jsonl_messages()` - Parse session files

### Caching Strategy
1. **Windows home cache** - Avoids repeated `/mnt` scans
2. **Codex index** - Session file -> workspace mapping
3. **Gemini hash index** - Hash -> path progressive building
4. **Message count cache** - Per-file counts in metrics DB

---

## Problem Areas for Redesign

### The Scope Resolution Bug
Different commands resolve scope differently:
- `session list` uses CWD workspace as pattern with **substring matching**
- `project stats` uses exact workspace paths from project definition

Result: `/home/user/projects/auth` matches `/home/user/projects/auth-infra`

### Current Issues
1. Pattern matching scattered across multiple functions
2. No unified resolution context (platform, CWD, available homes)
3. Commands duplicate scope resolution logic
4. No typed specifications for homes/workspaces/sessions

### Fix Strategy (v2 Architecture)
See `docs/design-v2/pipeline-architecture.md` and `docs/design-v2/scope-resolution-v2.md` for the new design that addresses these issues with:
- Typed specification system (HomeSpec, WorkspaceSpec, SessionSpec)
- 4-stage resolution pipeline (Projects -> Homes -> Workspaces -> Sessions)
- Explicit match types (Exact vs Contains vs Glob)
- Single resolution path for all commands
