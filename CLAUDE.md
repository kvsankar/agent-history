# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`claude-history` is a single-file Python CLI tool that browses and exports Claude Code conversation history. It provides a clean, UNIX-philosophy approach with simple commands for workspaces and sessions.

**Design principles:**
- Simple object-verb structure: `lsw` (list workspaces), `lss` (list sessions), `export`
- Minimal output: tab-separated data, no decoration, errors to stderr
- Remote access via SSH with `-r` flag
- Smart path handling for directories with dashes

## Commands

### Development Commands

```bash
# Make script executable (if needed)
chmod +x claude-history

# List hosts (all Claude Code installations)
./claude-history lsh                        # all hosts (local + WSL + Windows)
./claude-history lsh --local                # only local
./claude-history lsh --wsl                  # only WSL distributions
./claude-history lsh --windows              # only Windows users

# List workspaces
./claude-history lsw                        # all local workspaces
./claude-history lsw myproject              # filter by pattern
./claude-history lsw --wsl                  # WSL workspaces
./claude-history lsw --windows              # Windows workspaces
./claude-history lsw -r user@server         # SSH remote workspaces

# List sessions
./claude-history lss                        # current workspace
./claude-history lss myproject              # specific workspace
./claude-history lss --wsl                  # from WSL
./claude-history lss --windows              # from Windows
./claude-history lss myproject -r user@server    # SSH remote sessions

# Export (unified command with orthogonal scope flags)
./claude-history export                     # current workspace, local source
./claude-history export --as                # current workspace, all sources
./claude-history export --aw                # all workspaces, local source
./claude-history export --as --aw           # all workspaces, all sources

./claude-history export myproject           # specific workspace, local
./claude-history export myproject --as      # specific workspace, all sources
./claude-history export file.jsonl         # export single file

./claude-history export -o /tmp/backup      # current workspace, custom output
./claude-history export myproject -o ./out  # specific workspace, custom output

./claude-history export --wsl               # current workspace, WSL
./claude-history export --windows           # current workspace, Windows
./claude-history export -r user@server      # current workspace, SSH remote
./claude-history export --as -r user@vm01   # current workspace, all sources + SSH remote

# Show version
./claude-history --version

# Examples with date filtering
./claude-history lss myproject --since 2025-11-01
./claude-history export myproject --since 2025-11-01 --until 2025-11-30

# Export options
./claude-history export myproject --minimal       # minimal mode
./claude-history export myproject --split 500     # split long conversations
./claude-history export myproject --flat          # flat structure (no workspace subdirs)

# Backward compatible (export-all still supported)
./claude-history export-all                       # all sources, all workspaces
./claude-history export-all myproject             # filter by workspace pattern

# WSL and Windows access (new semantic flags)
./claude-history lsw --wsl                  # list WSL workspaces
./claude-history lsw --wsl Ubuntu           # filter by distro name
./claude-history lss myproject --wsl        # list WSL sessions
./claude-history export myproject --wsl     # export from WSL

./claude-history lsw --windows              # list Windows workspaces
./claude-history lss myproject --windows    # list Windows sessions
./claude-history export myproject --windows # export from Windows
```

### Testing Workflow

Manual testing is required since this tool operates on local Claude Code data:

```bash
# Test with your own Claude Code data
./claude-history lsw
./claude-history lss
./claude-history export myproject ./test

# Test remote access
./claude-history lsw -r user@server
./claude-history lss myproject -r user@server
./claude-history export myproject ./test -r user@server

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
# Instead of ./claude-history (Unix/Linux)
python claude-history lsw
python claude-history lss myproject
python claude-history export myproject ./output
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

**Critical:** The tool is intentionally a single Python file (`claude-history`) for easy distribution. All code must remain in one file with **no external dependencies** (stdlib only).

### Code Structure

The file is organized into eight main sections:

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
   - `get_wsl_distributions()`: Gets list of available WSL distributions with Claude workspaces
   - `get_wsl_projects_dir()`: Gets Claude projects directory for a WSL distribution via \\wsl.localhost\ path

7. **Remote Operations (SSH)**
   - `parse_remote_host()`: Parses user@hostname format
   - `check_ssh_connection()`: Verifies passwordless SSH connectivity
   - `get_remote_hostname()`: Extracts hostname for directory prefix
   - `list_remote_workspaces()`: Lists workspace directories on remote host via SSH
   - `get_remote_session_info()`: Gets remote file stats (size, mtime, message count) without downloading
   - `fetch_workspace_files()`: Fetches files from one remote workspace using rsync

8. **Commands**
   - `cmd_list()`: Shows all sessions for a workspace with stats (supports `-r` for remote/WSL)
   - `cmd_convert()`: Converts single .jsonl file to markdown (supports `-r` for remote/WSL)
   - `cmd_batch()`: Exports all sessions from a workspace to markdown (supports `-r` for remote/WSL, `--split` for splitting, organized export by default)
   - `cmd_list_wsl()`: Lists WSL distributions with Claude Code workspaces
   - `cmd_fetch()`: Pre-caches remote sessions via SSH (one-way sync)
   - `cmd_export_all()`: Exports from all sources (local + all WSL + optional SSH remotes) in one command
   - `generate_index_manifest()`: Generates index.md summary file with per-source and per-workspace statistics
   - `cmd_version()`: Displays version info

9. **Main**
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
- Token usage analysis and cost tracking
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
       role_emoji = "🔧"
       role_label = "Task Prompt (from Parent Claude)"
   ```

**Why this matters:**
- Prevents confusion: "User" in agent files means parent Claude, not human
- Enables traceability back to parent conversation
- Makes exported markdown self-documenting

### Minimal Export Mode

**Purpose:** Create cleaner exports suitable for sharing, blog posts, or documentation.

**Usage:** `claude-history export --minimal`

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
3. Follow existing emoji conventions (✅ ❌ ⚠ 🔍 📊 📁)
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
    print(f"❌ Error: {path} not found")
    print("\nTips:")
    print("  • Suggestion 1")
    print("  • Suggestion 2")
    sys.exit(1)
```

### Code Style

- Follow PEP 8
- Descriptive variable names (e.g., `workspace_pattern`, not `wp`)
- Comments for complex logic only
- Keep functions focused and small
- Use type hints in function signatures where it aids clarity

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

### Remote Operations

All commands support remote operations via the `-r/--remote` flag:

**Requirements:**
- Passwordless SSH access (key-based authentication)
- `rsync` installed on both local and remote machines
- Claude Code installed on remote machine with existing sessions

**Usage:**
```bash
# List remote workspaces
./claude-history lsw -r user@hostname

# List remote sessions (direct access, no caching)
./claude-history lss -r user@hostname
./claude-history lss myproject -r user@hostname

# Export remote sessions (caches locally first, then exports)
./claude-history export myproject -r user@hostname
./claude-history export myproject ./output -r user@hostname

# Convert remote file (downloads temporarily, then converts)
./claude-history export /path/to/file.jsonl -r user@hostname
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

## Recent Changes

**Windows Compatibility & Clean Syntax (v1.2.1)**
- Fixed critical Unicode encoding bug preventing multi-source operations on Windows
  - Added UTF-8 encoding configuration for Windows console
  - `export --as` and `export-all` now work correctly on Windows
- Removed deprecated flags for cleaner interface:
  - Removed `--list-wsl` and `--list-windows` (use `lsh --wsl` and `lsh --windows`)
  - Removed deprecated `-r wsl://` and `-r windows` syntax from documentation
  - Use semantic flags `--wsl` and `--windows` instead

**Semantic Flags for WSL/Windows Access (v1.2.0+)**
- Added `lsh` (list hosts) command to discover all Claude Code installations
  - `lsh` - show all hosts (local + WSL + Windows)
  - `lsh --local` - only local installation
  - `lsh --wsl` - only WSL distributions
  - `lsh --windows` - only Windows users
- Added universal `--wsl` and `--windows` flags that work across all commands
  - `lsw --wsl` - list workspaces from WSL
  - `lss --windows` - list sessions from Windows
  - `export myproject --wsl` - export from WSL
- **Conceptual separation**:
  - `--wsl` and `--windows` = same machine, different OS environments (local integration)
  - `-r user@host` = different machine over network (SSH remotes)
- Improved workspace filtering: Automatically excludes cached remote/WSL workspaces to prevent circular fetching

**Unified Export Interface (v1.2.0+)**
- Consolidated `export` command with orthogonal scope flags
- **`--as, --all-sources`**: Export from all sources (local + WSL + Windows + remotes)
- **`--aw, --all-workspaces`** (also `-a, --all`): Export all workspaces
- **`-o, --output DIR`**: Specify output directory (cleaner than positional argument)
- **Orthogonal design**: Combine flags independently
  - `export` - current workspace, local source (default)
  - `export --as` - current workspace, all sources
  - `export --aw` - all workspaces, local source
  - `export --as --aw` - all workspaces, all sources
- **Multiple remotes**: `-r` flag can now be used multiple times
- **Backward compatible**: `export-all` command still supported
- **Examples**:
  - `export myproject --as -o /tmp/backup` - specific workspace, all sources, custom output
  - `export --as --aw` - equivalent to old `export-all` behavior

**Bug Fixes (v1.2.0)**
- Fixed version output to display `claude-history` instead of `claude-sessions`
- Fixed split file location: Split files now correctly placed in workspace subdirectories
  - Previously split files were placed in root output directory
  - Now follows organized export structure with workspace subdirectories

**Windows Access from WSL (v1.2.0+)**
- Added Windows session access from WSL
- Bidirectional access now complete: Windows ↔ WSL
- Auto-detects Windows home via USERPROFILE + wslpath (works on any drive: C:, D:, etc.)
- Fallback: scans all `/mnt/*` drives for Windows users with Claude Code
- Use `--windows` flag with `lsw`, `lss`, and `export` commands
- Optional username specification: `--windows username`
- Source tag: `windows_` prefix for exported files
- Example: `./claude-history lsw --windows`, `./claude-history export myproject --windows`

**WSL Support (v1.2.0+)**
- Added WSL (Windows Subsystem for Linux) integration
- Direct filesystem access via `\\wsl.localhost\` paths (no SSH/rsync needed)
- Use `--wsl` flag with `lsw`, `lss`, and `export` commands
- Seamless access from Windows to WSL Claude sessions

**Organized Export Structure (v1.2.0+)**
- **Now default**: Exports organized by workspace subdirectories with source-tagged filenames
- Source prefixes: `wsl_{distro}_` for WSL, `windows_` for Windows (from WSL), `remote_{hostname}_` for SSH, no prefix for local
- Example: `exports/myproject/wsl_ubuntu_20251120_session.md`, `exports/myproject/windows_20251120_session.md`
- Use `--flat` flag for backward-compatible flat structure
- Enables multi-source consolidation (local + WSL + remote sessions in one organized structure)

**Windows Path Handling (v1.2.0+)**
- Fixed current workspace detection for Windows paths (C:\ drive handling)
- Windows workspace encoding: `C--alice-projects-myapp` for `C:\alice\projects\myapp`
- Consistent underscore separators for source tags throughout

**Export-All Command (v1.2.0+)** - *Superseded by unified export*
- `export-all` command still supported for backward compatibility
- **Preferred**: Use `export --as --aw` instead (unified interface)
- Environment-aware: automatically detects whether running on Windows or WSL
- **On Windows**: Exports from local Windows + all WSL distributions + optional SSH remotes
- **On WSL**: Exports from local WSL + all Windows users + optional SSH remotes
- **Pre-flight validation**: Checks all sources are accessible before starting export
  - Validates local, Windows, WSL, and SSH remote access
  - Prints all errors clearly if any source is inaccessible
  - Aborts immediately if validation fails (fail-fast behavior)
  - Only proceeds with export if ALL sources are accessible
- Automatically discovers and exports from all available sources
- Generates `index.md` manifest with per-source and per-workspace statistics
- **Migration**:
  - `export-all` → `export --as --aw`
  - `export-all myproject` → `export myproject --as`
  - `export-all -r vm01` → `export --as --aw -r vm01`

**Cache Naming Consistency (v1.2.0+)**
- Updated remote cache naming: `remote_{hostname}_{workspace}` (was `-remote-hostname-...`)
- Consistent with export source tag naming throughout
- Improves clarity and maintains naming patterns

**Circular Fetching Prevention (v1.2.0+)**
- Remote and WSL operations automatically filter out `remote_*` and `wsl_*` directories
- Prevents circular dependency loops when multiple machines fetch from each other
- Only native workspaces are fetched/exported from remote/WSL sources
- Example: P1 fetches P2 → P2 fetches P1 works correctly (skips cached data)

**Command Structure Redesign (v1.2.0)**
- Refactored from subcommands (list/export/convert/fetch) to simple object-verb structure
- **`lsw`**: List workspaces - explicit, no arbitrary defaults
- **`lss`**: List sessions in a workspace (defaults to current workspace)
- **`export`**: Export workspace, file, or all (with `-a` flag)
- Removed separate convert/fetch commands - merged into export
- All commands support `-r HOST` for remote operations (SSH)
- Tool renamed from `claude-sessions` to `claude-history` (broader, more accurate)
- Example: `./claude-history lsw`, `./claude-history lss myproject`, `./claude-history export myproject`

**Remote Operations with -r Flag (v1.1.0+, enhanced in v1.2.0)**
- `-r/--remote HOST` flag works with all commands (lsw, lss, export) for unified remote access
- **`lsw -r` / `lss -r`**: Direct remote listing via SSH (no caching) - fast, real-time view
- **`export -r`**: Caches remote files locally first, then exports - efficient for repeated operations
- Remote sessions stored with prefix: `remote_{hostname}_{workspace}` (consistent naming, no conflicts)
- One-way sync (remote → local) using passwordless SSH and rsync
- Requirements: passwordless SSH (key-based auth), rsync on both machines
- Use case: Work with conversations from multiple development machines seamlessly
- Example: `./claude-history lss myproject -r user@workstation`

**Agent Conversation Detection (v1.0.0+)**
- Agent conversations (spawned via Task tool) are automatically detected via `isSidechain` flag
- Clear visual distinction with `# Claude Conversation (Agent)` title
- Warning notice explains that "User" messages are from parent Claude, not human user
- First message labeled as `🔧 Task Prompt (from Parent Claude)` when applicable
- Includes parent session ID and agent ID in header for traceability
- Prevents confusion when reading exported agent conversations

**Conversation Splitting (v1.0.0+)**
- Added `--split LINES` flag to split long conversations into multiple parts
- Smart break point detection with priority-based scoring system:
  1. Prefers breaks before User messages (cleanest conversation flow)
  2. Prefers breaks after tool result messages
  3. Prefers breaks after time gaps (>5 minutes between messages)
- Flexible buffer zone (80%-130% of target) to prioritize clean breaks over exact line counts
- Line estimation accounts for message content and metadata sections
- Multi-part file generation with consistent naming: `timestamp_session_partN.md`
- Navigation links between parts: "Part N of M" with clickable previous/next links
- Each part header shows message range and part information
- Automatic detection - only splits when necessary
- Use `claude-history export --split 500` to split at ~500 lines per part

**Minimal Export Mode (v1.0.0+)**
- Added `--minimal` flag for cleaner exports suitable for sharing or blog posts
- Omits all metadata (UUIDs, session IDs, token usage, navigation links, etc.)
- Keeps only conversation content, timestamps, and tool execution details
- Use `claude-history export --minimal` for simplified output
- Default mode still preserves complete information

**Complete Information Preservation (v1.0.0+)**
- Zero data loss: ALL fields from JSONL files are now preserved in markdown
- Tool use inputs preserved with full JSON parameters
- Tool results preserved with complete output
- All metadata fields included: UUIDs, session IDs, working directory, git branch, version, etc.
- Model information preserved: model name, stop reason, token usage statistics
- Message threading preserved via UUID/parent UUID relationships with **clickable navigation links**
- HTML anchors enable jumping directly to parent messages
- Enables full conversation reconstruction, token analysis, and debugging from markdown

**Smart Defaults (v1.0.0+, enhanced in v1.2.0)**
- `lss` command defaults to current workspace when no workspace argument provided
- `lsw` command lists all workspaces (no default filtering)
- `export -a` must be explicitly specified to export all workspaces
- Explicit workspace names avoid ambiguity: `./claude-history lss myproject`

**Timestamped Filenames (v1.0.0+)**
- Exported markdown files now include timestamp prefix: `yyyymmddhhmmss_original-stem.md`
- Timestamp extracted from first message in conversation
- Enables chronological sorting and quick identification of conversation start time
- Falls back to original filename if no timestamp available
- Added `get_first_timestamp()` helper function

**Incremental Export (v1.0.0+)**
- Export is now incremental by default
- Skips files where the markdown output is newer than the source .jsonl file
- Shows detailed statistics: exported/skipped/failed counts
- Added `--force` flag to override and re-export everything
- Makes repeated exports much faster and more practical for backups

**CLI Refactor with Subcommands (v1.0.0+)**
- Refactored from flag-based (`--list-sessions`, `--export-workspace`) to subcommand structure
- Commands: `list`, `export`, `convert`
- Added `--this` flag to auto-detect current project workspace based on working directory
- Added explicit `--all` flag instead of implicit empty string for all workspaces
- More intuitive CLI following standard conventions (like git/docker)

**Date Filtering (v1.0.0+)**
- Added `--since` and `--until` command-line options for filtering by date
- Date parsing uses stdlib only (no external dependencies)
- Supports ISO 8601 format: YYYY-MM-DD
- Filtering happens inline during scanning for performance

## Contributing Notes

From CONTRIBUTING.md, key points:
- Test with small (< 10 sessions), medium (10-100), and large (100+) workspaces
- Verify edge cases: empty names, non-existent workspaces, corrupted files, invalid dates
- Update documentation if behavior changes
- Use existing emoji conventions consistently
- When adding date-related features, test boundary conditions (today, past, future dates)
