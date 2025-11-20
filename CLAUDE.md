# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`claude-sessions` is a single-file Python CLI tool that extracts and converts Claude Code conversation history by workspace. It provides a stable, file-path-based approach to exporting conversations, unlike session-ID-based tools which are brittle and change between runs.

**Key differentiator:** Filters conversations by workspace/project path instead of session IDs, making it easy to export all conversations for a specific project.

## Commands

### Development Commands

```bash
# Make script executable (if needed)
chmod +x claude-sessions

# Test listing sessions (defaults to current project)
./claude-sessions list [PATTERN|--all]

# Test export (defaults to current project)
./claude-sessions export [PATTERN|--all] --output-dir ./test-output

# Test single file conversion
./claude-sessions convert ~/.claude/projects/.../session.jsonl

# Show version
./claude-sessions --version

# Examples
./claude-sessions list                  # Current project (default)
./claude-sessions list --all            # All workspaces
./claude-sessions export myproject      # Pattern matching
```

### Testing Workflow

Manual testing is required since this tool operates on local Claude Code data:

```bash
# Test with your own Claude Code data (defaults to current project)
./claude-sessions list
./claude-sessions export --output-dir ./test

# Test with specific workspace pattern
./claude-sessions list myproject
./claude-sessions export myproject --output-dir ./test

# Test edge cases:
# - Empty workspace patterns
# - Non-existent workspaces
# - Large conversation files
# - Corrupted .jsonl files
```

## Architecture

### Single-File Design

**Critical:** The tool is intentionally a single Python file (`claude-sessions`) for easy distribution. All code must remain in one file with **no external dependencies** (stdlib only).

### Code Structure

The file is organized into five main sections:

1. **Date Parsing** (lines 23-39)
   - `parse_date_string()`: Parses ISO 8601 date strings (YYYY-MM-DD format) into datetime objects

2. **JSONL Parsing and Markdown Conversion** (lines 41-250)
   - `decode_content()`: Base64 decoding for encoded content
   - `extract_content()`: Extracts all content from message objects with full information preservation (text, tool use inputs with JSON, tool results with output)
   - `get_first_timestamp()`: Extracts first message timestamp for filename generation
   - `parse_jsonl_to_markdown()`: Main conversion logic that reads .jsonl and generates markdown with complete metadata preservation

3. **Workspace Scanning** (lines 136-248)
   - `get_claude_projects_dir()`: Locates `~/.claude/projects/` with error handling
   - `normalize_workspace_name()`: Converts directory names (e.g., `-home-alice-projects-django-app`) to readable paths (`home/alice/projects/django-app`)
   - `get_current_workspace_pattern()`: Detects current workspace based on working directory (used by `--this` flag)
   - `get_workspace_sessions()`: Scans workspaces matching a pattern, filters by date range if specified, returns session metadata

4. **Commands** (lines 232-408)
   - `cmd_list()`: Shows all sessions for a workspace with stats
   - `cmd_convert()`: Converts single .jsonl file to markdown
   - `cmd_export()`: Exports all sessions from a workspace to markdown
   - `cmd_version()`: Displays version info

5. **Main** (lines 410-550)
   - Argument parsing with `argparse` (including --since and --until flags)
   - Command dispatch to appropriate handler
   - Error handling (KeyboardInterrupt, general exceptions)

### Data Flow

```
~/.claude/projects/                     (Claude Code storage)
    └── -home-user-projects-myapp/      (workspace directory)
        ├── <uuid>.jsonl                (main conversation)
        └── agent-<id>.jsonl            (task subagents)
                ↓
    get_workspace_sessions()            (scan & filter)
                ↓
    parse_jsonl_to_markdown()           (convert)
                ↓
    ./claude-conversations/<uuid>.md    (output)
```

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

## Recent Changes

**Complete Information Preservation (v1.0.0+)**
- Zero data loss: ALL fields from JSONL files are now preserved in markdown
- Tool use inputs preserved with full JSON parameters
- Tool results preserved with complete output
- All metadata fields included: UUIDs, session IDs, working directory, git branch, version, etc.
- Model information preserved: model name, stop reason, token usage statistics
- Message threading preserved via UUID/parent UUID relationships with **clickable navigation links**
- HTML anchors enable jumping directly to parent messages
- Enables full conversation reconstruction, token analysis, and debugging from markdown

**Default to Current Workspace (v1.0.0+)**
- Commands now default to current project workspace when no arguments provided
- `./claude-sessions list` defaults to current workspace (previously required `--this`)
- `./claude-sessions export` defaults to current workspace (previously required `--this`)
- `--all` must be explicitly specified to list/export all workspaces
- Removed need for `--this` flag in most common use cases (still supported for explicitness)

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
