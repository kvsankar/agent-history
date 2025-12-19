# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`agent-history` is a single-file Python CLI tool that browses and exports AI coding assistant conversation history (Claude Code, Codex CLI, and Gemini CLI). It provides a clean, UNIX-philosophy approach with simple commands for workspaces and sessions.

> **Note:** This tool was previously named `claude-history`. A wrapper script `claude-history` is provided for backward compatibility.

**Design principles:**
- Simple object-verb structure: `lsw` (list workspaces), `lss` (list sessions), `export`
- Minimal output: tab-separated data, no decoration, errors to stderr
- Remote access via SSH with `-r` flag
- Smart path handling for directories with dashes

## Commands

### Development Commands

```bash
# Make script executable (if needed)
chmod +x agent-history

# List homes (all Claude Code installations)
./agent-history lsh                        # all hosts (local + WSL + Windows)
./agent-history lsh --local                # only local
./agent-history lsh --wsl                  # only WSL distributions (shows available agents)
./agent-history lsh --windows              # only Windows users

# List workspaces
./agent-history lsw                        # all local workspaces
./agent-history lsw myproject              # filter by pattern
./agent-history lsw proj1 proj2            # multiple patterns (match any)
./agent-history lsw --wsl                  # WSL workspaces
./agent-history lsw --windows              # Windows workspaces
./agent-history lsw -r user@server         # SSH remote workspaces
./agent-history lsw --ah                   # all homes (local + WSL/Windows + remotes)
./agent-history lsw --ah -r vm01 -r vm02   # all homes + multiple SSH remotes
./agent-history lsw proj1 proj2 --ah       # multiple patterns from all homes

# List sessions
./agent-history lss                        # current workspace
./agent-history lss myproject              # specific workspace
./agent-history lss proj1 proj2            # multiple workspaces (deduplicated)
./agent-history lss --wsl                  # from WSL
./agent-history lss --windows              # from Windows
./agent-history lss myproject -r user@server    # SSH remote sessions
./agent-history lss myproject --ah         # from all homes
./agent-history lss --ah -r vm01 -r vm02   # all homes + multiple SSH remotes
./agent-history lss proj1 proj2 --ah       # multiple patterns from all homes

# Export (unified command with orthogonal scope flags)
./agent-history export                     # current workspace, local source
./agent-history export --ah                # current workspace, all homes
./agent-history export --aw                # all workspaces, local source
./agent-history export --ah --aw           # all workspaces, all homes

./agent-history export myproject           # specific workspace, local
./agent-history export proj1 proj2         # multiple workspaces (deduplicated)
./agent-history export myproject --ah      # specific workspace, all homes
./agent-history export proj1 proj2 --ah    # multiple workspaces, all homes (lenient)
./agent-history export file.jsonl         # export single file (defaults to ./claude-conversations/)
./agent-history export file.jsonl -o ./out  # export single file to directory

./agent-history export -o /tmp/backup      # current workspace, custom output
./agent-history export myproject -o ./out  # specific workspace, custom output

./agent-history export --wsl               # current workspace, WSL
./agent-history export --windows           # current workspace, Windows
./agent-history export -r user@server      # current workspace, SSH remote
./agent-history export --ah -r user@vm01   # current workspace, all homes + SSH remote
./agent-history export --ah proj1 proj2 -r host  # multiple patterns, all homes + remote

# Show version
./agent-history --version

# Examples with date filtering
./agent-history lss myproject --since 2025-11-01
./agent-history export myproject --since 2025-11-01 --until 2025-11-30

# Export options
./agent-history export myproject --minimal       # minimal mode
./agent-history export myproject --split 500     # split long conversations
./agent-history export myproject --flat          # flat structure (no workspace subdirs)
./agent-history export myproject --jobs 4        # parallel export
./agent-history export myproject --quiet         # suppress per-file output
./agent-history export --ah --no-remote          # skip SSH remotes
./agent-history export --ah --no-wsl             # skip WSL sources
./agent-history export --ah --no-windows         # skip Windows sources

# Workspace Aliases (group workspaces across environments)
./agent-history alias list                       # list all aliases
./agent-history alias show myproject             # show workspaces in an alias
./agent-history alias create myproject           # create new alias
./agent-history alias delete myproject           # delete an alias
./agent-history alias add myproject myproject    # add by pattern (searches local)
./agent-history alias add myproject --windows myproject  # add by pattern from Windows
./agent-history alias add myproject --ah -r vm myproject  # add from all homes at once
./agent-history alias remove myproject -- -home-user-myproject  # remove workspace from alias
./agent-history alias export aliases.json        # export aliases to file
./agent-history alias import aliases.json        # import aliases from file

# Using aliases with lss and export
./agent-history lss @myproject                   # list sessions from all alias workspaces
./agent-history lss --alias myproject            # same as above
./agent-history export @myproject                # export from all alias workspaces
./agent-history export --alias myproject         # same as above
./agent-history export @myproject --ah           # export alias from all homes

# WSL and Windows access (flags auto-detect)
./agent-history lsw --wsl                  # list WSL workspaces
./agent-history lss myproject --wsl        # list WSL sessions
./agent-history export myproject --wsl     # export from WSL
./agent-history lss --wsl --agent codex    # list Codex WSL sessions
./agent-history lss --wsl --agent gemini   # list Gemini WSL sessions

./agent-history lsw --windows              # list Windows workspaces
./agent-history lss myproject --windows    # list Windows sessions
./agent-history export myproject --windows # export from Windows

# Saved Sources (for --ah flag)
./agent-history lsh                        # list saved sources
./agent-history lsh add user@vm01          # add SSH remote (WSL/Windows auto-detected)
./agent-history lsh add user@vm02     # add another remote
./agent-history lsh remove user@vm01  # remove a source
./agent-history lsh clear             # remove all saved sources

# Usage Statistics and Metrics (orthogonal --ah/--aw flags)
./agent-history stats --sync               # sync local sessions to database
./agent-history stats --sync --ah          # sync from all homes (includes saved remotes)
./agent-history stats --sync --ah -r vm03  # sync all homes + additional remote
./agent-history stats --sync --ah --jobs 4 # parallel remote sync
./agent-history stats --sync --ah --no-remote  # skip SSH remotes
./agent-history stats --sync --ah --no-wsl     # skip WSL sources
./agent-history stats                      # summary dashboard (current workspace)
./agent-history stats --aw                 # summary dashboard (all workspaces)
./agent-history stats myproject            # filter by workspace pattern
./agent-history stats --tools              # tool usage statistics
./agent-history stats --models             # model usage breakdown
./agent-history stats --by-workspace       # per-workspace stats
./agent-history stats --by-day             # daily usage trends
./agent-history stats --since 2025-11-01   # filter by date
./agent-history stats --source local       # filter by source

# Time tracking (orthogonal --ah/--aw flags)
./agent-history stats --time               # current workspace, local DB
./agent-history stats --time --ah          # current workspace, sync all homes first
./agent-history stats --time --aw          # all workspaces, local DB
./agent-history stats --time --ah --aw     # all workspaces, sync all homes first

# Agent selection (Claude Code, Codex CLI, Gemini CLI)
./agent-history --agent auto lss           # auto-detect (default)
./agent-history --agent claude lss         # Claude Code only
./agent-history --agent codex lss          # Codex CLI only
./agent-history --agent gemini lss         # Gemini CLI only

# Gemini CLI hash index management
./agent-history gemini-index               # list all hash→path mappings
./agent-history gemini-index --add         # add current directory to index
./agent-history gemini-index --add ~/proj  # add specific directory to index
```

### Testing Workflow

**Automated tests (1100+ tests):**

```bash
# Run all tests
uv run pytest

# Unit tests only
uv run pytest tests/unit/ -v

# Integration tests only
uv run pytest -m integration tests/integration/
```

**Coverage (subprocess-aware, parallel-friendly):**

```bash
# Host coverage (uses .coveragerc + scripts/coverage_startup.py)
make coverage           # runs pytest under coverage with subprocess tracing
make coverage-report    # text report
make coverage-html      # HTML in .coverage-html/
make coverage-clean     # remove coverage artifacts
```

Notes:
- `.coveragerc` enables branch + parallel + multiprocessing coverage with `source=.` and `[paths]` to remap Docker paths (`/app` → `.`).
- Subprocess coverage is enabled by setting `COVERAGE_PROCESS_START=.coveragerc` and `PYTHONPATH=scripts` (handled by `make coverage`).

After running host + Docker coverage, merge and report:

```bash
.venv/Scripts/python -m coverage combine --rcfile=.coveragerc .coverage-data .
.venv/Scripts/python -m coverage report --rcfile=.coveragerc --include="*agent-history"
```

**Docker E2E tests (real SSH connections):**

```bash
cd docker
docker-compose up -d --build      # Start SSH nodes
docker-compose run test-runner    # Run E2E tests
docker-compose down -v            # Cleanup
```

With coverage (from repo root, auto-teardown):

```bash
make docker-coverage              # runs E2E tests under coverage and downs the stack
```

Docker coverage is bind-mounted to `.coverage-data/` for easy merging on the host.

The Docker setup creates:
- `node-alpha`: SSH node with users alice, bob
- `node-beta`: SSH node with users charlie, dave
- Synthetic Claude/Codex/Gemini session fixtures
- Real SSH key-based authentication between containers

See [docker/README.md](docker/README.md) for details.

**Manual testing with real data:**

```bash
# Test with your own Claude Code data
./agent-history lsw
./agent-history lss
./agent-history export myproject ./test

# Test remote access
./agent-history lsw -r user@server
./agent-history lss myproject -r user@server
./agent-history export myproject ./test -r user@server

# Test edge cases:
# - Empty workspace patterns
# - Non-existent workspaces
# - Large conversation files
# - Paths with dashes (e.g., moon-phase)
# - Corrupted .jsonl files
```

## Windows Compatibility

The tool runs natively on Windows with the following considerations:

### Running on Windows

Use `python` or `python3` to execute the script:

```powershell
# Instead of ./agent-history (Unix/Linux)
python agent-history lsw
python agent-history lss myproject
python agent-history export myproject ./output
```

### Local Operations

All local operations work perfectly on Windows:
- ✅ List workspaces (`lsw`)
- ✅ List sessions (`lss`)
- ✅ Export conversations (`export`)
- ✅ Convert single files
- ✅ Date filtering
- ✅ Minimal mode
- ✅ Conversation splitting

**Encoding:** The script explicitly uses UTF-8 encoding for all file operations, ensuring proper handling of Unicode characters on Windows.

**Paths:** Uses `pathlib.Path` which handles Windows paths (backslashes) correctly.

### Remote Operations

Remote operations (`-r` flag) require additional setup on Windows:

**OpenSSH Client:**
- Windows 10/11 includes OpenSSH client by default
- Verify: `ssh -V` in PowerShell/CMD
- If missing, install via: Settings → Apps → Optional Features → OpenSSH Client

**rsync (for fetch/export -r):**
- Not included in Windows by default
- Install options:
  - **WSL (Recommended):** Use Windows Subsystem for Linux with `wsl ssh ...` and `wsl rsync ...`
  - **Chocolatey:** `choco install rsync`
  - **Cygwin:** Install rsync package
  - **Git Bash:** Includes rsync

**Passwordless SSH:**
```powershell
# Generate SSH key (if needed)
ssh-keygen -t ed25519

# Copy to remote (requires password once)
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh user@hostname "cat >> .ssh/authorized_keys"

# Test connection
ssh -o BatchMode=yes user@hostname echo ok
```

### Platform-Specific Notes

- **Line endings:** Python handles CRLF/LF automatically
- **Home directory:** `~/.claude/projects/` resolves to `C:\Users\<username>\.claude\projects\` on Windows
- **Temp files:** Uses system temp directory via `tempfile` module
- **Path separators:** All path operations use `pathlib.Path` for cross-platform compatibility

## Architecture

### Single-File Design

**Critical:** The tool is intentionally a single Python file (`agent-history`) for easy distribution. All code must remain in one file with **no external dependencies** (stdlib only).

### Code Structure

The file is organized into twelve main sections:

1. **Date Parsing**
   - `parse_date_string()`: Parses ISO 8601 date strings (YYYY-MM-DD format) into datetime objects

2. **Content Extraction and Utilities**
   - `decode_content()`: Base64 decoding for encoded content
   - `extract_content()`: Extracts all content from message objects with full information preservation (text, tool use inputs with JSON, tool results with output)
   - `get_first_timestamp()`: Extracts first message timestamp for filename generation

3. **Conversation Splitting Helpers**
   - `estimate_message_lines()`: Estimates line count for a message (~27-47 lines)
   - `is_tool_result_message()`: Detects tool result messages
   - `calculate_time_gap()`: Calculates time gap between messages in seconds
   - `find_best_split_point()`: Priority-based scoring to find optimal break points
   - `generate_markdown_parts()`: Orchestrates splitting into multiple parts
   - `generate_markdown_for_messages()`: Generates markdown for message subsets with part indicators

4. **JSONL Parsing and Markdown Conversion**
   - `read_jsonl_messages()`: Reads and parses messages from JSONL file (refactored for reuse)
   - `parse_jsonl_to_markdown()`: Main conversion logic that generates markdown with complete metadata preservation

5. **Workspace Scanning**
   - `get_claude_projects_dir()`: Locates `~/.claude/projects/` with error handling
   - `normalize_workspace_name()`: Converts directory names (e.g., `-home-alice-projects-django-app`) to readable paths (`home/alice/projects/django-app`)
   - `get_current_workspace_pattern()`: Detects current workspace based on working directory (handles Windows C:\ paths)
   - `get_workspace_sessions()`: Scans workspaces matching a pattern, filters by date range if specified, returns session metadata

6. **WSL Access (Windows)**
   - `is_wsl_remote()`: Checks if remote spec is a WSL distribution (wsl://DistroName)
   - `get_source_tag()`: Generates source tag for filename/directory prefixes (wsl_{distro}_, remote_{host}_, or empty for local)
   - `get_workspace_name_from_path()`: Extracts clean workspace name from directory name, removing source tags
   - `get_wsl_distributions()`: Gets list of available WSL distributions with agent data
   - `get_wsl_projects_dir()`: Gets Claude projects directory for a WSL distribution via \\wsl.localhost\ path

7. **Remote Operations (SSH)**
   - `parse_remote_host()`: Parses user@hostname format
   - `check_ssh_connection()`: Verifies passwordless SSH connectivity
   - `get_remote_hostname()`: Extracts hostname for directory prefix
   - `list_remote_workspaces()`: Lists workspace directories on remote host via SSH
   - `get_remote_session_info()`: Gets remote file stats (size, mtime, message count) without downloading
   - `fetch_workspace_files()`: Fetches files from one remote workspace using rsync

8. **Workspace Aliases**
   - `get_aliases_dir()`: Returns `~/.claude-history/` directory
   - `get_aliases_file()`: Returns `~/.claude-history/aliases.json` path
   - `load_aliases()`: Loads aliases from JSON file (returns empty dict if not found)
   - `save_aliases()`: Saves aliases to JSON file
   - `path_to_encoded_workspace()`: Converts absolute path to Claude's encoded workspace name
   - `resolve_workspace_input()`: Resolves pattern/path/encoded name to matching workspaces
   - `cmd_alias_list()`: Lists all defined aliases
   - `cmd_alias_show()`: Shows workspaces in a specific alias
   - `cmd_alias_create()`: Creates a new empty alias
   - `cmd_alias_delete()`: Deletes an alias
   - `cmd_alias_add()`: Adds workspaces to an alias (supports patterns, `--ah` flag for all homes)
   - `cmd_alias_remove()`: Removes a workspace from an alias
   - `cmd_alias_config_export()`: Exports aliases to a JSON file
   - `cmd_alias_config_import()`: Imports aliases from a JSON file
   - `cmd_alias_lss()`: Lists sessions from all workspaces in an alias
   - `cmd_alias_export()`: Exports sessions from all workspaces in an alias

9. **Configuration and Saved Sources**
   - `get_config_file()`: Returns `~/.claude-history/config.json` path
   - `load_config()`: Loads configuration from JSON file
   - `save_config()`: Saves configuration to JSON file
   - `get_saved_sources()`: Returns list of saved SSH remotes
   - `cmd_sources_list()`: Lists saved sources
   - `cmd_sources_add()`: Adds SSH remote (validates WSL/Windows are auto-detected)
   - `cmd_sources_remove()`: Removes a saved source
   - `cmd_sources_clear()`: Clears all saved sources

10. **Metrics Database (SQLite)**
   - `get_metrics_db_path()`: Returns `~/.claude-history/metrics.db` path
   - `init_metrics_db()`: Creates/opens database, initializes schema
   - `extract_metrics_from_jsonl()`: Extracts session, message, and tool use metrics from JSONL
   - `sync_file_to_db()`: Syncs a single JSONL file to database (incremental)
   - `cmd_stats_sync()`: Syncs JSONL files from local/WSL/Windows/SSH sources
   - `cmd_stats()`: Displays metrics with various views (orthogonal --ah/--aw flags)
   - `display_summary_stats()`: Summary dashboard (alias-aware)
   - `display_tool_stats()`: Tool usage statistics
   - `display_model_stats()`: Model usage breakdown
   - `display_workspace_stats()`: Per-workspace statistics (alias-aware)
   - `display_daily_stats()`: Daily usage trends
   - `display_time_stats()`: Time tracking with daily breakdown
   - `calculate_daily_work_time()`: Calculates work time per day with gap detection

11. **Commands**
   - `cmd_list()`: Shows all sessions for a workspace with stats (supports `-r` for remote/WSL)
   - `cmd_convert()`: Converts single .jsonl file to markdown (supports `-r` for remote/WSL)
   - `cmd_batch()`: Exports all sessions from a workspace to markdown (supports `-r` for remote/WSL, `--split` for splitting, organized export by default)
   - `cmd_list_wsl()`: Lists WSL distributions with agent data
   - `cmd_fetch()`: Pre-caches remote sessions via SSH (one-way sync)
   - `cmd_export_all()`: Exports from all homes (local + all WSL + optional SSH remotes) in one command
   - `generate_index_manifest()`: Generates index.md summary file with per-source and per-workspace statistics
   - `cmd_version()`: Displays version info
   - `cmd_alias_*()`: Alias management commands (see section 8)
   - `cmd_sources_*()`: Source management commands (see section 9)

12. **Main**
   - Argument parsing with `argparse` (including -r/--remote, --since, --until, --minimal, --split, --flat flags)
   - Command dispatch to appropriate handler
   - Error handling (KeyboardInterrupt, general exceptions)

### Data Flow

```
~/.claude/projects/                     (Claude Code storage)
    ├── C--alice-projects-myapp/        (local Windows workspace)
    │   ├── <uuid>.jsonl                (main conversation)
    │   └── agent-<id>.jsonl            (task subagents)
    ├── wsl_ubuntu_home-alice-myapp/    (WSL workspace - if cached)
    └── remote_vm01_home-user-myapp/    (SSH remote - if cached)
                ↓
    get_workspace_sessions()            (scan & filter)
                ↓
    parse_jsonl_to_markdown()           (convert)
                ↓
    ./exports/                          (organized output - default)
        └── myapp/                      (workspace subdirectory)
            ├── 20251120_<uuid>.md      (local Windows - no prefix)
            ├── wsl_ubuntu_20251120_<uuid>.md  (WSL)
            └── remote_vm01_20251120_<uuid>.md (SSH remote)

    OR with --flat flag:
    ./exports/                          (flat output)
        └── 20251120_<uuid>.md          (all files in one directory)
```

### Organized Export Structure (Default)

**Default behavior:** Exports are organized by workspace with source-tagged filenames.

**Directory structure:**
```
exports/
  ├── workspace-name/
  │   ├── 20251120_session.md              ← Local (no prefix)
  │   ├── wsl_ubuntu_20251120_session.md   ← WSL Ubuntu
  │   └── remote_vm01_20251120_session.md  ← SSH remote
  └── another-workspace/
      └── ...
```

**Source tagging:**
- **Local Windows**: No prefix (e.g., `20251120_session.md`)
- **WSL**: `wsl_{distro}_` prefix (e.g., `wsl_ubuntu_20251120_session.md`)
- **SSH Remote**: `remote_{hostname}_` prefix (e.g., `remote_vm01_20251120_session.md`)

**Rationale:**
- Workspace organization enables per-project analysis
- Source tags identify where each session originated
- Supports multi-source consolidation (local + WSL + remote)
- Use `--flat` flag for backward-compatible flat structure

### JSONL Format Details

Each `.jsonl` file contains one JSON object per line:

**User messages:**
```json
{
  "type": "user",
  "message": {"role": "user", "content": "string"},
  "timestamp": "ISO-8601",
  "cwd": "/path"
}
```

**Assistant messages:**
```json
{
  "type": "assistant",
  "message": {
    "role": "assistant",
    "content": [
      {"type": "text", "text": "..."},
      {"type": "tool_use", "name": "Bash", "input": {...}},
      {"type": "tool_result", ...}
    ]
  },
  "timestamp": "ISO-8601"
}
```

### Information Preservation

**Critical Design Principle:** The tool preserves ALL information from JSONL files with zero data loss.

**Preserved Fields:**
- **Message Content:**
  - User text messages
  - Assistant text responses
  - Tool use requests (full JSON input parameters)
  - Tool results (complete output)
  - Tool IDs for tracking tool use/result pairs

- **Metadata (per message):**
  - UUID (unique message ID)
  - Parent UUID (message threading/relationships)
  - Session ID (conversation identifier)
  - Agent ID (for task subagents)
  - Request ID (API request tracking)
  - Working directory (cwd)
  - Git branch
  - Claude Code version
  - User type
  - Is sidechain (task agent flag)

- **Model Information (assistant messages):**
  - Model name (e.g., claude-sonnet-4-5-20250929)
  - Stop reason (end_turn, tool_use, etc.)
  - Stop sequence
  - Token usage:
    - Input tokens
    - Output tokens
    - Cache creation tokens
    - Cache read tokens

**Why This Matters:**
- Full conversation reconstruction from markdown
- Token usage analysis
- Message threading and relationship analysis
- Debugging tool execution
- Audit trail for all operations

**Navigation Links:**
The tool creates clickable navigation between related messages:

1. **HTML Anchors:** Each message gets an anchor: `<a name="msg-{uuid}"></a>`
2. **Parent Links:** When a message has a parent UUID:
   - If parent is in same file: Clickable link `[uuid](#msg-uuid) (→ Message N)`
   - If parent is in different file: Shows `uuid (in different session)`
3. **Use Cases:**
   - Follow conversation flow by clicking parent links
   - Navigate to the message that triggered a tool use
   - Trace agent spawning back to main session
   - Jump between related messages without scrolling

**Implementation:**
```python
# Build UUID to message index map
uuid_to_index = {msg['uuid']: i for i, msg in enumerate(messages, 1) if msg.get('uuid')}

# Add anchor for each message
if msg.get('uuid'):
    md_lines.append(f'<a name="msg-{msg["uuid"]}"></a>')

# Link to parent if it exists in same file
if parent_uuid in uuid_to_index:
    md_lines.append(f"[`{parent_uuid}`](#msg-{parent_uuid}) *(→ Message {uuid_to_index[parent_uuid]})*")
```

### Agent Conversation Detection

**Purpose:** Clearly identify agent conversations (Task tool sub-tasks) to prevent confusion about who the "User" is.

**Detection:**
```python
# Check if this is an agent conversation
is_agent = any(msg.get('isSidechain') for msg in messages)
```

**Implementation:**
1. **Title differentiation:**
   - Normal: `# Claude Conversation`
   - Agent: `# Claude Conversation (Agent)`

2. **Warning notice in header:**
   ```markdown
   > ⚠️ **Agent Conversation:** This is a sub-task executed by an agent spawned from the main conversation.
   >
   > - Messages labeled 'User' represent task instructions from the parent Claude session
   > - Messages labeled 'Assistant' are responses from this agent
   > - **Parent Session ID:** `{session_id}`
   > - **Agent ID:** `{agent_id}`
   ```

3. **First message labeling:**
   ```python
   if is_agent and i == 1 and msg['role'] == 'user':
       role_label = "Task Prompt (from Parent Claude)"
   ```

**Why this matters:**
- Prevents confusion: "User" in agent files means parent Claude, not human
- Enables traceability back to parent conversation
- Makes exported markdown self-documenting

### Minimal Export Mode

**Purpose:** Create cleaner exports suitable for sharing, blog posts, or documentation.

**Usage:** `agent-history export --minimal`

**Implementation:**
```python
def parse_jsonl_to_markdown(jsonl_file: Path, minimal: bool = False) -> str:
    # Skip metadata section when minimal=True
    if not minimal:
        md_lines.append("### Metadata")
        # ... add all metadata fields

    # Skip HTML anchors when minimal=True
    if not minimal and msg.get('uuid'):
        md_lines.append(f'<a name="msg-{msg["uuid"]}"></a>')
```

**What's included:**
- Message text content
- Tool use inputs (full JSON)
- Tool results (complete output)
- Timestamps

**What's omitted:**
- All metadata sections (UUIDs, session IDs, etc.)
- HTML anchors and navigation links
- Model information
- Token usage statistics

## Development Guidelines

### When Adding Features

**Before adding new functionality:**
1. Maintain single-file design - do not split into modules
2. Use only Python stdlib (no external dependencies like `click`, `rich`, etc.)
3. Use minimal UNIX-style output (no emojis, brief messages)
4. Provide helpful error messages with actionable suggestions
5. Test with real Claude Code data of varying sizes

**Adding a new command:**
```python
# 1. Add command function in Commands section
def cmd_newcommand(args):
    """Description."""
    # Implementation

# 2. Add argparse argument in main()
action_group.add_argument('--new-command',
    help='Description')

# 3. Add dispatch in main()
elif args.new_command:
    class NewArgs:
        # Define args
    cmd_newcommand(NewArgs())
```

### Error Handling Pattern

Exit codes:
- `0`: Success
- `1`: General error
- `130`: Interrupted by user (Ctrl+C)

Always provide helpful error messages:
```python
if not path.exists():
    print(f"Error: {path} not found", file=sys.stderr)
    print("\nTips:", file=sys.stderr)
    print("  - Suggestion 1", file=sys.stderr)
    print("  - Suggestion 2", file=sys.stderr)
    sys.exit(1)
```

### Code Style

- Follow PEP 8
- Descriptive variable names (e.g., `workspace_pattern`, not `wp`)
- Comments for complex logic only
- Keep functions focused and small
- Use type hints in function signatures where it aids clarity

### Code Quality Metrics

The codebase uses pre-commit hooks for quality enforcement:

```bash
# Check complexity manually
uv run radon cc agent-history -a -s    # Cyclomatic complexity
uv run radon mi agent-history -s       # Maintainability index
```

**Current metrics (~485 functions):**
- Grade A (1-5): 288 functions (61%)
- Grade B (6-10): 166 functions (35%)
- Grade C (11-20): 18 functions (4%)
- Grade D/E/F (21+): 0 functions
- Average complexity: B (5.0)

**Dataclasses for configuration:**
- `ListCommandArgs`, `SyncCommandArgs`, `StatsCommandArgs`, `ConvertCommandArgs`
- `ExportAllConfig`, `SummaryStatsData`

These replace ad-hoc argument classes, improving testability and IDE support.

### Incremental Export

The `export` command implements incremental export by comparing file modification timestamps:

**How it works:**
- Before exporting, checks if the output .md file exists
- Compares source .jsonl `mtime` with output .md `mtime`
- Skips export if output is newer than or equal to source
- Only processes files that are new or have been updated

**Implementation** (in `cmd_export()`):
```python
if not force and output_file.exists():
    source_mtime = jsonl_file.stat().st_mtime
    output_mtime = output_file.stat().st_mtime
    if output_mtime >= source_mtime:
        # Skip - already up-to-date
        skipped += 1
        continue
```

**Statistics tracking:**
- `exported`: Files that were converted
- `skipped`: Files that were already up-to-date
- `failed`: Files that encountered errors

**Override:** Use `--force` flag to re-export all files regardless of timestamps

### Output Filename Format

Exported markdown files are named using the timestamp of the first message in the conversation:

**Format:** `yyyymmddhhmmss_original-stem.md`

**Examples:**
- `20251120103045_c7e6fbcb-6a8a-4637-ab33-6075d83060a8.md`
- `20251120150230_agent-c17c2c4d.md`

**Implementation** (in `cmd_export()`):
```python
# Extract first timestamp from JSONL file
first_ts = get_first_timestamp(jsonl_file)
if first_ts:
    # Parse ISO 8601 timestamp and format as yyyymmddhhmmss
    dt = datetime.fromisoformat(first_ts.replace('Z', '+00:00'))
    ts_prefix = dt.strftime('%Y%m%d%H%M%S')
    output_name = f"{ts_prefix}_{jsonl_file.stem}.md"
else:
    # Fallback: use original stem if no timestamp found
    output_name = f"{jsonl_file.stem}.md"
```

**Benefits:**
- Chronological sorting: Files automatically sort by conversation start time
- Quick identification: See when a conversation started without opening the file
- Preserves original ID: Full session UUID is retained for reference
- Handles edge cases: Falls back to original filename if no timestamp exists

**Helper function:**
- `get_first_timestamp(jsonl_file)`: Efficiently scans the JSONL file to extract the timestamp from the first user or assistant message

### Date Filtering

Date filtering is implemented inline during session scanning for efficiency:

**Filter points:**
- Filters are applied during file scanning (in `get_workspace_sessions()`) before sessions are added to the list
- This prevents unnecessary file reading and message counting for filtered-out sessions
- Filtering is based on file modification timestamp, not internal conversation dates

**Implementation details:**
- Date strings are parsed using `datetime.strptime()` with `'%Y-%m-%d'` format
- Invalid dates trigger clear error messages with format examples
- Validation ensures `--since` date is before `--until` date
- Both filters are optional and can be used independently

### Conversation Splitting

The `--split` flag enables splitting long conversations into multiple manageable parts:

**Smart Break Point Detection:**

The tool uses a priority-based scoring system to find optimal split points:

```python
def find_best_split_point(messages, target_lines: int, minimal: bool) -> int:
    """Find the best message index to split at, near target_lines."""
    min_lines = int(target_lines * 0.8)  # Buffer zone: 80%-130%
    max_lines = int(target_lines * 1.3)

    # Score each potential break point:
    # +100: Next message is User (cleanest break)
    # +50: Current message is tool result
    # +30: Time gap > 5 minutes
    # +10: Time gap > 1 minute
    # -0.05 per line away from target (prefer closer)
```

**Line Estimation:**

Messages are estimated at ~27-47 lines depending on content and metadata:
- Message header and timestamp: ~4 lines
- Content: actual line count of text
- Metadata section: ~20 lines (if not minimal mode)
- Separator: ~2 lines

**Multi-Part File Generation:**

Implementation in `cmd_batch()`:
```python
if split_lines and len(messages) > 0:
    parts = generate_markdown_parts(messages, jsonl_file, minimal, split_lines)

    if parts:
        for part_num, total_parts, part_md, start_msg, end_msg in parts:
            # Create filename: timestamp_session_part1.md
            part_filename = f"{base_name}_part{part_num}.md"

            # Add navigation footer
            nav = f"**Part {part_num} of {total_parts}**"
            if part_num > 1:
                nav += f" | [← Part {part_num - 1}](filename_part{part_num-1}.md)"
            if part_num < total_parts:
                nav += f" | [Part {part_num + 1} →](filename_part{part_num+1}.md)"
```

**Helper Functions:**
- `read_jsonl_messages(jsonl_file)`: Extracts messages from JSONL (refactored for reuse)
- `estimate_message_lines(msg_content, has_metadata)`: Estimates line count
- `is_tool_result_message(msg_content)`: Detects tool results
- `calculate_time_gap(msg1, msg2)`: Calculates seconds between messages
- `find_best_split_point()`: Scoring-based break point finder
- `generate_markdown_parts()`: Orchestrates splitting into multiple parts
- `generate_markdown_for_messages()`: Generates markdown for message subsets

**Part Headers:**

Each part includes:
- Title: `# Claude Conversation - Part N of M`
- Part number: `**Part:** N of M`
- Message range: `**Messages in this part:** 16 (#26-#41)`
- Timestamps for first and last message in part

**Benefits:**
- Makes very long conversations (>500 messages) more manageable
- Preserves conversation flow with smart breaks
- Easy navigation between parts
- Maintains message numbering continuity across parts

## Key Concepts

### Workspace Directory Naming

Claude Code encodes workspace paths as directory names:
- Path: `/home/alice/projects/django-app`
- Directory: `-home-alice-projects-django-app`

Conversion logic in `normalize_workspace_name()`: strip leading dash, replace remaining dashes with slashes.

### Session vs Agent Files

- **Main sessions** (UUID filenames): Primary conversations with Claude
- **Agent sessions** (`agent-*` filenames): Task subagents spawned during conversations

Both types are processed identically.

### Pattern Matching

Workspace pattern matching is substring-based:
- Pattern `django` matches `-home-alice-projects-django-app`
- Empty pattern (`""`, `"*"`, or `"all"`) matches all workspaces
- Case-sensitive matching

### Workspace Aliases

Aliases group related workspaces across different sources for unified access.

**Storage Location:**
- Config directory: `~/.claude-history/`
- Alias file: `~/.claude-history/aliases.json`

**JSON Structure:**
```json
{
  "version": 1,
  "aliases": {
    "myproject": {
      "local": ["-home-alice-projects-myproject"],
      "windows": ["C--alice-projects-myproject"],
      "wsl": {"Ubuntu": ["-home-alice-myproject"]},
      "remote": {"workstation": ["-home-alice-myproject"]}
    }
  }
}
```

**Source Types:**
- `local`: Local workspaces (current environment)
- `windows`: Windows workspaces (from WSL)
- `wsl`: WSL workspaces (from Windows), keyed by distro name
- `remote`: SSH remote workspaces, keyed by hostname

**Usage Patterns:**
```bash
# Using @ prefix
./agent-history lss @myproject
./agent-history export @myproject

# Using --alias flag
./agent-history lss --alias myproject
./agent-history export --alias myproject

# Combine with other flags
./agent-history export @myproject --ah     # all homes
./agent-history export @myproject --minimal
```

**Automatic Alias Scoping:**

When running `lss`, `export`, or `stats` without arguments, if the current workspace belongs to an alias, the tool automatically scopes to the alias:

```bash
# If current workspace is part of @myproject alias:
./agent-history lss        # 📎 Using alias @myproject (use --this for current workspace only)
./agent-history export     # 📎 Using alias @myproject (use --this for current workspace only)
./agent-history stats      # 📎 Using alias @myproject (use --this for current workspace only)

# To force current workspace only:
./agent-history lss --this
./agent-history export --this
./agent-history stats --this
```

This behavior makes it easy to work with related workspaces across environments without explicitly specifying the alias each time.

**Syncing Aliases Across Machines:**
```bash
# Export aliases to file
./agent-history alias export aliases.json

# Copy to another machine
scp aliases.json user@other-machine:~/

# Import on other machine
./agent-history alias import aliases.json
```

**Adding Workspaces to Aliases:**
```bash
# Add by pattern (searches local workspaces)
./agent-history alias add myproject myproject

# Add from Windows (auto-detects user)
./agent-history alias add myproject --windows myproject

# Add from all homes at once (local + WSL/Windows + remotes)
./agent-history alias add myproject --ah -r vm myproject

# Workspace names starting with '-' need '--' separator
./agent-history alias remove myproject -- -home-user-myproject
```

### Remote Operations

All commands support remote operations via the `-r/--remote` flag:

**Requirements:**
- Passwordless SSH access (key-based authentication)
- `rsync` installed on both local and remote machines
- Claude Code installed on remote machine with existing sessions

**Usage:**
```bash
# List remote workspaces
./agent-history lsw -r user@hostname

# List remote sessions (direct access, no caching)
./agent-history lss -r user@hostname
./agent-history lss myproject -r user@hostname

# Export remote sessions (caches locally first, then exports)
./agent-history export myproject -r user@hostname
./agent-history export myproject ./output -r user@hostname

# Skip selected sources (useful with --ah)
./agent-history export --ah --no-remote
./agent-history export --ah --no-wsl
./agent-history export --ah --no-windows

# Convert remote file (downloads temporarily, then converts)
./agent-history export /path/to/file.jsonl -r user@hostname
```

**Storage Strategy:**
- Remote sessions cached with prefix: `remote_{hostname}_{workspace}`
- Example: `-home-user-project` on remote `workstation` becomes `remote_workstation_home-user-project` locally
- Keeps remote and local sessions completely separate (no conflicts)

**Circular Fetching Prevention:**
- Remote operations automatically filter out `remote_*` and `wsl_*` directories
- Prevents circular dependency: P1 fetches P2 → P2 fetches P1 → infinite loop
- Only native workspaces are fetched/exported from remote/WSL sources
- Example: When P1 fetches from P2, it skips P2's `remote_p1_*` cache (which is P1's own data)

**Caching Behavior:**
- **`lsw -r` / `lss -r`**: Direct remote access via SSH (no caching) - fast, real-time view
- **`export -r`**: Caches files locally first using rsync, then exports - efficient for repeated operations

**Implementation:**
- `check_ssh_connection()`: Verifies SSH connectivity with `BatchMode=yes` (no password prompts)
- `get_remote_session_info()`: Gets remote file stats without downloading (for list)
- `list_remote_workspaces()`: Lists remote workspace directories via SSH (filters out remote_* and wsl_*)
- `fetch_workspace_files()`: Uses `rsync -avh` to sync .jsonl files
- One-way sync only (remote → local), never modifies remote machine
- Incremental by default (rsync only transfers new/changed files)

**SSH Setup:**
```bash
# Generate SSH key (if needed)
ssh-keygen -t ed25519

# Copy key to remote
ssh-copy-id user@hostname

# Test connection
ssh -o BatchMode=yes user@hostname echo ok
```

### Orthogonal Flag Design

The `--ah` and `--aw` flags are designed to be orthogonal (independent):

| Flag | Meaning | Scope |
|------|---------|-------|
| `--ah` (`--all-homes`) | Include all homes (local + WSL/Windows + saved SSH remotes) | **Where** to get data from |
| `--aw` (`--all-workspaces`) | Include all workspaces (not just current) | **Which** workspaces to include |

**Key principle:** These flags can be used together or separately:
- `stats` → Current workspace, local DB only
- `stats --ah` → Current workspace, sync all homes first
- `stats --aw` → All workspaces, local DB only
- `stats --ah --aw` → All workspaces, sync all homes first

**Implementation notes:**
- `--ah` for `stats --time` triggers auto-sync before display
- WSL and Windows are auto-detected by `--ah` (no configuration needed)
- Only SSH remotes need to be saved via `lsh add`
- Saved sources are stored in `~/.claude-history/config.json`

### Mutually Exclusive Flags

Some flags cannot be used together:

| Flags | Behavior |
|-------|----------|
| `--wsl` + `--windows` | Error: mutually exclusive (use one or the other) |
| `--this` + `@alias` | `--this` overrides alias auto-detection |
| Multiple `-r` flags | Only first remote is used for single-target operations |

### Flag Precedence

When multiple related flags are specified:
1. Explicit patterns override auto-detection
2. `--this` forces current workspace only
3. Remote flags (`-r`, `--wsl`, `--windows`) determine data source
4. `--ah` expands to include all available sources

## Development Tools

### Pre-commit Hooks

The project uses pre-commit hooks for code quality enforcement:

```yaml
# .pre-commit-config.yaml hooks:
- ruff          # Linting and formatting
- ruff-format   # Code formatting
- ty            # Type checking (Astral's Python type checker)
```

**Running pre-commit manually:**
```bash
uv run pre-commit run --all-files    # Run all hooks
uv run pre-commit run ty --all-files # Run ty only
```

**Type checking with ty:**

The codebase uses [ty](https://github.com/astral-sh/ty) (Astral's Python type checker, 10-60x faster than mypy):
- TypedDicts for complex nested dictionaries (`SessionMetrics`, `MetricsDict`, etc.)
- `Optional[T]` for parameters with `None` defaults
- `Union[str, Path]` for multi-type parameters
- `cast()` for TypedDict → dict conversions at call sites
- `# type: ignore[attr-defined]` for platform-specific code (e.g., `msvcrt` on Windows)

```bash
# Check types directly
uv run ty check agent-history
```

### Cross-Platform Coverage Orchestrator

The `scripts/run-coverage.py` tool aggregates test coverage from multiple environments:

**Supported environments:**
- **Windows**: Native pytest with coverage
- **WSL**: Linux tests via `wsl` command
- **Docker**: E2E tests from `.coverage-data/` directory

**Setup:**
```bash
# Copy template and configure paths
cp scripts/coverage.config.template scripts/coverage.config
# Edit coverage.config with your Windows/WSL paths
```

**Configuration (coverage.config):**
```ini
[paths]
windows_project = C:/Users/yourname/projects/claude-history
wsl_project = /home/yourname/projects/claude-history
wsl_distro = Ubuntu

[output]
output_dir = .coverage-merged
```

**Usage:**
```bash
# Run from Windows - executes tests in both Windows and WSL, then merges
python scripts/run-coverage.py

# Windows tests only
python scripts/run-coverage.py --windows-only

# WSL tests only
python scripts/run-coverage.py --wsl-only

# Merge existing coverage data (skip running tests)
python scripts/run-coverage.py --merge-only

# Generate report from previously merged data
python scripts/run-coverage.py --report
```

**Output:**
- Terminal coverage report with missing lines
- HTML report at `.coverage-merged/htmlcov/index.html`
- Merged `.coverage` file with path mappings across environments

**How it works:**
1. Runs pytest with `--cov` in Windows → `.coverage.windows`
2. Runs pytest with `--cov` in WSL → `.coverage.wsl`
3. Collects Docker E2E coverage from `.coverage-data/`
4. Merges all coverage files with path remapping
5. Generates unified coverage report

**Version:** 1.5.1

## Contributing Notes

From CONTRIBUTING.md, key points:
- Test with small (< 10 sessions), medium (10-100), and large (100+) workspaces
- Verify edge cases: empty names, non-existent workspaces, corrupted files, invalid dates
- Update documentation if behavior changes
- Use minimal UNIX-style output (no emojis, brief error messages)
- When adding date-related features, test boundary conditions (today, past, future dates)

## Context Window Management

Your context window will be automatically compacted as it approaches its limit, allowing you to continue working indefinitely from where you left off. Therefore, do not stop tasks early due to token budget concerns. As you approach your token budget limit, save your current progress and state to memory before the context window refreshes. Always be as persistent and autonomous as possible and complete tasks fully, even if the end of your budget is approaching. Never artificially stop any task early regardless of the context remaining.
