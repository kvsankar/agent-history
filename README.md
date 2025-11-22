# claude-sessions

Extract and convert Claude Code conversation history by workspace with multi-environment support.

> **TL;DR:** A better way to export Claude Code conversations. Filter by workspace/project, export from local + WSL + remote sources, with automatic circular fetching prevention.

## Why This Tool?

When you use [Claude Code](https://claude.com/claude-code), your conversations are stored in `~/.claude/projects/`. While tools like [`claude-conversation-extractor`](https://github.com/simonw/claude-conversation-extractor) exist, they have limitations:

| Problem | This Tool's Solution |
|---------|---------------------|
| ❌ Session IDs change between runs | ✅ Stable file-path-based approach |
| ❌ Can't filter by workspace/repo | ✅ Search by workspace pattern |
| ❌ Manual session number selection | ✅ Automatic batch processing |
| ❌ Mixed conversations from different projects | ✅ Workspace-filtered extraction |
| ❌ No multi-environment support | ✅ Export from local + WSL + remote in one command |
| ❌ Circular syncing issues | ✅ Automatic circular fetching prevention |

This tool extracts conversations **by workspace** and supports **multi-environment consolidation**, making it easy to get conversation history from local machines, WSL distributions, and remote servers.

## Quick Start

**Unix/Linux/Mac:**
```bash
# Make executable
chmod +x claude-history

# List sessions from current project (default)
./claude-history lss

# Export sessions from current project to markdown (default)
./claude-history export

# Output goes to ./claude-conversations/ by default
```

**Windows:**
```powershell
# List sessions from current project (default)
python claude-history lss

# Export sessions from current project to markdown (default)
python claude-history export

# Output goes to ./claude-conversations/ by default
```

## Installation

### Option 1: Direct Download

```bash
# Download the script
curl -O https://raw.githubusercontent.com/yourusername/claude-workspace-extract/main/claude-sessions

# Make it executable
chmod +x claude-sessions

# Move to your PATH (optional)
sudo mv claude-sessions /usr/local/bin/
```

### Option 2: Clone Repository

```bash
git clone https://github.com/yourusername/claude-workspace-extract.git
cd claude-workspace-extract
chmod +x claude-sessions

# Optional: Add to PATH
ln -s $(pwd)/claude-sessions /usr/local/bin/claude-sessions
```

### Requirements

**All Platforms:**
- Python 3.6 or higher (uses only stdlib, no external dependencies)
- Claude Code installed and logged in
- At least one Claude Code conversation/session

**For Remote Operations:**
- OpenSSH client (included in Windows 10/11, macOS, and most Linux distributions)
- rsync (for remote export - see Windows Installation below)
- Passwordless SSH key setup

### Windows Installation

The tool works natively on Windows with a few platform-specific considerations:

#### 1. Install Python

Download and install Python from [python.org](https://www.python.org/downloads/) (version 3.6 or higher).

Verify installation:
```powershell
python --version
```

#### 2. Download the Tool

```powershell
# Download the script
curl -O https://raw.githubusercontent.com/yourusername/claude-history/main/claude-history

# Or clone the repository
git clone https://github.com/yourusername/claude-history.git
cd claude-history
```

#### 3. Running the Tool

On Windows, run the script using `python`:

```powershell
# Instead of ./claude-history (Unix), use:
python claude-history lsw
python claude-history lss myproject
python claude-history export myproject
```

#### 4. Local Operations (Work Out of the Box)

All local operations work perfectly on Windows without additional setup:
- ✅ `python claude-history lsw` - List workspaces
- ✅ `python claude-history lss` - List sessions
- ✅ `python claude-history export` - Export conversations
- ✅ Date filtering with `--since` and `--until`
- ✅ Minimal mode with `--minimal`
- ✅ Conversation splitting with `--split`

#### 5. Remote Operations (Require Additional Setup)

To use remote features (`-r` flag) on Windows, you need SSH and rsync:

**OpenSSH Client (Usually Pre-installed):**

Windows 10/11 includes OpenSSH client by default. Verify:
```powershell
ssh -V
```

If not installed, enable it via:
- Settings → Apps → Optional Features → Add a feature → OpenSSH Client

**rsync (Required for remote export):**

rsync is NOT included in Windows by default and has limited compatibility with Windows OpenSSH.

**Recommended Solution: WSL (Windows Subsystem for Linux)**
```powershell
# Use Windows Subsystem for Linux (most reliable)
wsl python claude-history export -r user@hostname
```

**Alternative Options (May Have SSH Compatibility Issues):**

**Option B: Chocolatey**
```powershell
# Install via Chocolatey
choco install rsync

# Note: May encounter "dup() in/out/err failed" error with Windows OpenSSH
# If this happens, use WSL instead
```

**Option C: Git Bash**

Git for Windows includes rsync. Download from [git-scm.com](https://git-scm.com/). May have same SSH integration issues.

**Option D: cwRsync**

Download from [itefix.net/cwrsync](https://www.itefix.net/cwrsync) - specifically designed for Windows but requires configuration.

**Why WSL is Recommended:**
- Full rsync compatibility with SSH
- No path conversion issues (C: drive not interpreted as remote host)
- Native Linux environment for rsync
- Your SSH keys from Windows are accessible in WSL via `/mnt/c/Users/...`

### WSL (Windows Subsystem for Linux) Access

If you have Claude Code installed in WSL distributions, you can access those workspaces directly from Windows without SSH or rsync setup.

#### Prerequisites

1. **Windows 10/11 with WSL installed:**
   ```powershell
   # Check if WSL is installed
   wsl --version

   # If not installed, install WSL:
   wsl --install
   ```

2. **Claude Code installed in WSL:**
   ```bash
   # Inside WSL
   claude login
   # Create at least one conversation
   ```

#### List Available WSL Distributions

Find which WSL distributions have Claude Code workspaces:

```powershell
python claude-history --list-wsl
```

**Output:**
```
DISTRO          USERNAME        PATH
Ubuntu          alice           /home/alice/.claude/projects
Ubuntu-22.04    alice           /home/alice/.claude/projects
```

#### Access WSL Workspaces

Use the `wsl://` prefix with the `-r` flag to access WSL workspaces:

```powershell
# List workspaces in WSL
python claude-history lsw -r wsl://Ubuntu

# List sessions from a WSL workspace
python claude-history lss myproject -r wsl://Ubuntu

# Export WSL conversations to Windows
python claude-history export myproject -r wsl://Ubuntu
python claude-history export myproject -r wsl://Ubuntu ./wsl-conversations
```

**Key Benefits:**
- ✅ No SSH setup required
- ✅ No rsync installation needed
- ✅ Direct filesystem access via `\\wsl.localhost\` paths
- ✅ Works seamlessly from Windows PowerShell or Command Prompt
- ✅ Export to Windows filesystem for easy access

#### Example Workflow

```powershell
# 1. Find WSL distributions with Claude workspaces
PS C:\> python claude-history --list-wsl
DISTRO          USERNAME        PATH
Ubuntu          alice           /home/alice/.claude/projects

# 2. List all workspaces in Ubuntu WSL
PS C:\> python claude-history lsw -r wsl://Ubuntu

# 3. List sessions from a specific workspace
PS C:\> python claude-history lss django-app -r wsl://Ubuntu

🔍 Searching for workspaces matching: 'django-app'

✓ Found workspace: home/alice/projects/django-app
  • c7e6fbcb-6a8a-4637-ab33-6075d83060a8.jsonl: 2112 messages, 6206.8 KB, 2025-11-12 20:28
  • agent-c17c2c4d.jsonl: 41 messages, 698.0 KB, 2025-11-12 20:03

# 4. Export to Windows filesystem
PS C:\> python claude-history export django-app -r wsl://Ubuntu ./wsl-exports

✓ Found 2 sessions
📁 Output directory: C:\Users\alice\wsl-exports\

[1/2] c7e6fbcb-6a8a-4637-ab33-6075d83060a8.jsonl ✓
[2/2] agent-c17c2c4d.jsonl ✓
```

#### Tips

- **Multiple WSL Distributions:** If you have multiple WSL distributions, specify the exact name: `wsl://Ubuntu-22.04`
- **Combine with Other Flags:** Use `--since`, `--until`, `--minimal`, `--split` with WSL access
- **Fast Performance:** Direct filesystem access is faster than SSH/rsync
- **No Network Required:** Works completely offline

#### 6. SSH Key Setup (For Remote Access)

```powershell
# Generate SSH key (if you don't have one)
ssh-keygen -t ed25519

# Copy key to remote server (requires password once)
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh user@hostname "cat >> .ssh/authorized_keys"

# Test passwordless connection
ssh -o BatchMode=yes user@hostname echo ok
```

If you have SSH keys in WSL, copy them to Windows:
```powershell
wsl cp ~/.ssh/id_* /mnt/c/Users/$env:USERNAME/.ssh/
```

#### Windows-Specific Notes

- **File Encoding:** The tool automatically uses UTF-8 encoding on Windows to handle Unicode characters correctly
- **Path Handling:** Windows paths (with backslashes) are handled automatically via Python's `pathlib`
- **Line Endings:** Remote bash scripts are automatically converted to Unix line endings
- **Home Directory:** `~/.claude/projects/` resolves to `C:\Users\<username>\.claude\projects\` on Windows

## Usage

### List Sessions

Show all conversation sessions for a workspace:

```bash
claude-sessions list [PATTERN|--all]
```

**Examples:**
```bash
# List sessions from current project (default)
$ claude-sessions list

🔍 Searching for workspaces matching: 'home-alice-projects-django-app'

✓ Found workspace: home/alice/projects/django-app
  • c7e6fbcb-6a8a-4637-ab33-6075d83060a8.jsonl: 2112 messages, 6206.8 KB, 2025-11-12 20:28
  • agent-c17c2c4d.jsonl: 41 messages, 698.0 KB, 2025-11-12 20:03

================================================================================
📊 Summary
================================================================================
Sessions found:    2
Total size:        6904.8 KB (6.74 MB)
Total messages:    2,153
Date range:        2025-11-12 to 2025-11-12

# List sessions matching a pattern
$ claude-sessions list another-project

# List all sessions from all workspaces
$ claude-sessions list --all
```

**Arguments:**
- `PATTERN`: Workspace name pattern to filter sessions (default: current project)
- `--all`: List sessions from all workspaces

**Tips:**
- Defaults to current project when no arguments provided
- Use partial workspace names: `django` instead of full path
- Pattern matching: any workspace containing the pattern
- Case-sensitive matching

### Export

Export all sessions from a workspace to markdown.

**Incremental by default:** Only exports new or updated sessions. Re-running the command will skip files that are already up-to-date.

```bash
claude-sessions export [PATTERN|--all] [OPTIONS]
```

**Examples:**
```bash
# Export current project (default, incremental)
$ claude-sessions export

🔍 Finding all 'home-alice-projects-django-app' sessions...

✓ Found 2 sessions
📁 Output directory: ./claude-conversations/

[1/2] c7e6fbcb-6a8a-4637-ab33-6075d83060a8.jsonl ✓
[2/2] agent-c17c2c4d.jsonl ✓

================================================================================
📊 Export Complete
================================================================================
Exported:   2/2
Total size: 347.2 KB
Location:   /home/alice/projects/claude-conversations

# Second run - skips unchanged files (incremental)
$ claude-sessions export

[1/2] c7e6fbcb-6a8a-4637-ab33-6075d83060a8.jsonl ⊘ (already exported)
[2/2] agent-c17c2c4d.jsonl ⊘ (already exported)

================================================================================
📊 Export Complete
================================================================================
Exported:   0/2
Skipped:    2/2 (already up-to-date)

# Export with custom output directory
$ claude-sessions export --output-dir ./blog-material

# Export a specific workspace by pattern
$ claude-sessions export another-project

# Force re-export all files
$ claude-sessions export --force

# Export all workspaces
$ claude-sessions export --all -o ./all-conversations
```

**Arguments:**
- `PATTERN`: Workspace name pattern to filter sessions (default: current project)
- `--all`: Export sessions from all workspaces

**Options:**
- `--output-dir`, `-o DIR`: Output directory (default: `./claude-conversations`)
- `--force`, `-f`: Force re-export all sessions, even if already exported
- `--minimal`: Minimal mode - omit all metadata, keep only conversation content, timestamps, and tool execution details
- `--split LINES`: Split long conversations into multiple parts at approximately LINES per file (e.g., `--split 500`)

**Export Modes:**

By default, exports include complete information (all metadata, UUIDs, token usage, etc.). Use `--minimal` for cleaner output suitable for sharing or blog posts:

```bash
# Full export (default) - complete information preservation
$ claude-sessions export

# Minimal export - conversation content only
$ claude-sessions export --minimal
```

**Minimal mode includes:**
- Message text content
- Tool use inputs (full JSON)
- Tool results (complete output)
- Timestamps

**Minimal mode omits:**
- All metadata (UUIDs, session IDs, working directory, git branch, version, etc.)
- HTML anchors and navigation links
- Model information and token usage statistics

**Conversation Splitting:**

For very long conversations, you can split them into multiple parts for easier reading:

```bash
# Split conversations into ~500 lines per part
$ claude-sessions export --split 500

# Combine with other options
$ claude-sessions export --split 500 --minimal
```

**How splitting works:**
- Automatically detects when conversations exceed the target line count
- Uses smart break points to avoid splitting in awkward places
- Prioritizes breaks:
  1. Before User messages (cleanest breaks)
  2. After tool result messages
  3. After time gaps (>5 minutes between messages)
- Flexible on exact line count (±20-30%) to get cleaner breaks
- Creates multiple files: `timestamp_session_part1.md`, `timestamp_session_part2.md`, etc.
- Adds navigation links between parts for easy browsing
- Each part shows: "Part N of M" and message range (#X-#Y)

**When to use splitting:**
- Conversations with >500 messages
- Very long sessions that are hard to scroll through
- When you want to read conversations in manageable chunks

### Convert Single File

Convert a specific conversation file to markdown:

```bash
claude-sessions convert JSONL_FILE [OPTIONS]
```

**Example:**
```bash
$ claude-sessions convert ~/.claude/projects/.../session.jsonl

🔄 Converting session.jsonl to markdown...
✅ Saved to session.md
   Size: 173.4 KB

# Specify custom output file
$ claude-sessions convert session.jsonl --output my-conversation.md
```

**Arguments:**
- `JSONL_FILE`: Path to `.jsonl` conversation file

**Options:**
- `--output`, `-o FILE`: Output markdown filename (default: same name with `.md`)

### Date Filtering

Filter conversations by modification date using `--since` and `--until` options. Both work with `list` and `export` commands.

**Date Format:** ISO 8601 format (`YYYY-MM-DD`)

**Examples:**
```bash
# List sessions modified on or after November 1, 2025
claude-sessions list myproject --since 2025-11-01

# Export only sessions from November 2025
claude-sessions export myproject --since 2025-11-01 --until 2025-11-30

# List sessions from a specific day
claude-sessions list myproject --since 2025-11-15 --until 2025-11-15

# Export recent conversations only
claude-sessions export myproject --since 2025-11-01 --output-dir ./recent
```

**Options:**
- `--since DATE`: Only include sessions modified on or after this date
- `--until DATE`: Only include sessions modified on or before this date

**Notes:**
- Dates are based on file modification time, not conversation timestamps
- Both options can be used together or independently
- Invalid date formats will show an error message
- The `--since` date must be before the `--until` date

## How It Works

### Workspace Structure

Claude Code stores conversations in workspace-specific directories under `~/.claude/projects/`:

```
~/.claude/projects/
├── -home-alice-projects-django-app/
│   ├── c7e6fbcb-6a8a-4637-ab33-6075d83060a8.jsonl  ← Main conversation
│   └── agent-c17c2c4d.jsonl                         ← Task subagent
├── -home-alice-projects-react-frontend/
│   └── 152a2a19-a97d-4988-8630-2b37499487c7.jsonl
└── ...
```

Directory names encode the workspace path:
- `-home-alice-projects-django-app` → `/home/alice/projects/django-app`

This tool:
1. Scans `~/.claude/projects/` for directories matching your pattern
2. Reads `.jsonl` conversation files directly
3. Parses user/assistant messages with timestamps
4. Generates clean, readable markdown

### JSONL Format

Each `.jsonl` file contains JSON Lines with conversation entries:

**User Message:**
```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": "Help me build a Django app"
  },
  "timestamp": "2025-11-12T10:00:00.000Z",
  "cwd": "/home/alice/projects/django-app"
}
```

**Assistant Message:**
```json
{
  "type": "assistant",
  "message": {
    "role": "assistant",
    "content": [
      {"type": "text", "text": "I'll help you build..."},
      {"type": "tool_use", "name": "Bash", ...}
    ]
  },
  "timestamp": "2025-11-12T10:00:05.000Z"
}
```

### Markdown Output

**Filename Format:**

Exported markdown files are named using the timestamp of the first message:
```
yyyymmddhhmmss_original-stem.md
```

Examples:
- `20251120103045_c7e6fbcb-6a8a-4637-ab33-6075d83060a8.md`
- `20251120150230_agent-c17c2c4d.md`

This format makes it easy to:
- Sort conversations chronologically
- Identify when a conversation started at a glance
- Keep the original session ID for reference

**Content Format:**

**Complete Information Preservation:** All data from the JSONL files is preserved in the markdown output, including:
- Message content (text, tool use inputs, tool results)
- All metadata (UUIDs, session IDs, working directory, git branch, etc.)
- Model information and token usage statistics
- Parent/child message relationships with **clickable navigation links**
- Tool execution details

**Conversation Threading:** Parent-child message relationships are preserved with clickable navigation:
- Each message has an HTML anchor based on its UUID
- Parent UUID links jump directly to the parent message
- Within-file links: `[parent-uuid](#msg-parent-uuid) (→ Message 5)`
- Cross-file links: `parent-uuid (in different session)` for agent spawning

**Agent Conversation Detection:** Agent conversations (spawned via the Task tool) are clearly identified:
- Title shows `# Claude Conversation (Agent)` instead of `# Claude Conversation`
- Warning notice explains that "User" messages are from parent Claude, not human user
- First message labeled as `🔧 Task Prompt (from Parent Claude)` when applicable
- Includes parent session ID and agent ID in the header
- Example:
  ```markdown
  # Claude Conversation (Agent)

  > ⚠️ **Agent Conversation:** This is a sub-task executed by an agent spawned from the main conversation.
  >
  > - Messages labeled 'User' represent task instructions from the parent Claude session
  > - Messages labeled 'Assistant' are responses from this agent
  > - **Parent Session ID:** `aec67da6-f741-49ac-bca9-cd2b2c89fa15`
  > - **Agent ID:** `79885a3c`
  ```

Generated markdown files include:

```markdown
# Claude Conversation

**File:** session.jsonl
**Messages:** 42
**First message:** 2025-11-12T10:00:00.000Z
**Last message:** 2025-11-12T10:30:00.000Z

---

## Message 1 - 👤 User

*2025-11-12T10:00:00.000Z*

Help me build a Django app for task management...

### Metadata

- **UUID:** `04f01c10-a464-4988-9f84-0852e00390af`
- **Session ID:** `4cf3e1b9-69e4-4667-b04e-a2e3e22879ee`
- **Working Directory:** `/home/alice/projects/django-app`
- **Git Branch:** `main`
- **Version:** `2.0.47`

---

## Message 2 - 🤖 Assistant

*2025-11-12T10:00:05.000Z*

I'll help you build a Django task management app. Let me start by creating the project structure...

**[Tool Use: Bash]**
Tool ID: `toolu_01AbCdEfGhIjKlMnOpQrStUv`

Input:
```json
{
  "command": "django-admin startproject taskmanager",
  "description": "Create Django project"
}
```

### Metadata

- **UUID:** `23426b30-cbd4-4f10-a5e8-ca4e9a3e211b`
- **Parent UUID:** `04f01c10-a464-4988-9f84-0852e00390af`
- **Session ID:** `4cf3e1b9-69e4-4667-b04e-a2e3e22879ee`
- **Model:** `claude-sonnet-4-5-20250929`
- **Usage:**
  - Input tokens: 632
  - Output tokens: 130
  - Cache read tokens: 12392

---

## Message 3 - 👤 User

*2025-11-12T10:00:10.000Z*

**[Tool Result: Success]**
Tool Use ID: `toolu_01AbCdEfGhIjKlMnOpQrStUv`

```
Successfully created project 'taskmanager'
```

### Metadata

- **UUID:** `5ddae6d4-f903-40d9-aad2-3c49835ead65`
- **Parent UUID:** `23426b30-cbd4-4f10-a5e8-ca4e9a3e211b`
- **Session ID:** `4cf3e1b9-69e4-4667-b04e-a2e3e22879ee`

---

## Message 2 - 🤖 Assistant

*2025-11-12T10:00:05.000Z*

I'll help you build a Django task management app. Let me start by...

[Tool Use: Bash]
...
```

## Use Cases

### 📝 Blog Post Material

Extract conversation history for writing blog posts. Run repeatedly to keep it up-to-date:

```bash
# Initial export
claude-sessions export my-project --output-dir ./blog-material

# Later - only exports new/updated conversations
claude-sessions export my-project --output-dir ./blog-material
```

### 📊 Project Documentation

Document development decisions and iterations:

```bash
claude-sessions export backend-api --output-dir ./docs/development-log
```

### 🔍 Analysis & Learning

Review problem-solving approaches across sessions:

```bash
# Export all sessions for a project
claude-sessions export ml-pipeline

# Analyze patterns, decisions, iterations
grep -r "Error:" claude-conversations/
```

### 💾 Archival

Archive conversation history by date/project:

```bash
claude-sessions export project-2024 --output-dir archives/2024-11/
```

### 🎓 Portfolio & Showcases

Share development process with collaborators or for portfolios:

```bash
claude-sessions export portfolio-site --output-dir showcase/
```

### 🌐 Multi-Environment Consolidation

Consolidate conversations from multiple development environments (local, WSL, remote servers):

```bash
# Export all sources: local Windows + all WSL distributions + SSH remotes
python claude-history export-all myproject -r user@vm01 user@vm02

# Perfect for:
# - Backing up all Claude sessions across environments
# - Analyzing conversations across different machines
# - Creating comprehensive project history
```

**Circular Fetching Prevention:** When P1 fetches from P2 and P2 fetches from P1, the tool automatically filters out cached remote data (`remote_*` and `wsl_*` directories) to prevent infinite loops. Only native workspaces are fetched from each source.

## Remote Operations

The tool supports accessing Claude Code conversations from remote machines via SSH and WSL distributions.

### SSH Remote Access

Access conversations from remote development machines:

```bash
# List remote workspaces
claude-history lsw -r user@server

# List sessions from remote
claude-history lss myproject -r user@server

# Export from remote
claude-history export myproject -r user@server
```

**Requirements:**
- Passwordless SSH key setup (`ssh-copy-id user@server`)
- `rsync` installed on both local and remote machines

**Setup:**
```bash
# Generate SSH key (if needed)
ssh-keygen -t ed25519

# Copy key to remote
ssh-copy-id user@server

# Test connection
ssh -o BatchMode=yes user@server echo ok
```

### WSL Access (Windows)

Access conversations from WSL distributions directly from Windows:

```bash
# List available WSL distributions
python claude-history --list-wsl

# List WSL workspaces
python claude-history lsw -r wsl://Ubuntu

# Export from WSL
python claude-history export myproject -r wsl://Ubuntu
```

**How it works:**
- Direct filesystem access via `\\wsl.localhost\DistroName\` paths
- No SSH or rsync needed
- Native Windows file operations

### Windows Access (from WSL)

Access conversations from Windows directly from WSL:

```bash
# List available Windows users with Claude
./claude-history --list-windows

# List Windows workspaces
./claude-history lsw -r windows

# Export from Windows
./claude-history export myproject -r windows

# Specify Windows user (if multiple users)
./claude-history lss -r windows://username
```

**How it works:**
- Auto-detects Windows home via USERPROFILE + wslpath
- Works on any drive letter (C:, D:, E:, etc.)
- Fallback: scans all `/mnt/*` drives for Windows users
- Direct filesystem access via `/mnt/c/Users/...` paths
- No SSH or rsync needed
- Native file operations

**Example output:**
```bash
$ ./claude-history --list-windows
USERNAME    DRIVE    WORKSPACES    PATH
alice       c        16            /mnt/c/Users/alice

$ ./claude-history lsw -r windows
/C//alice/projects/claude-sessions
/C//alice/projects/astromcp
...

$ ./claude-history export claude-sessions -r windows
/tmp/export/claude-sessions/windows_20251120_session.md
...
```

### Circular Fetching Prevention

When syncing conversations between multiple machines, the tool prevents circular dependencies:

**Problem:**
- P1 fetches from P2 → creates `remote_p2_*` cache on P1
- P2 fetches from P1 → would fetch `remote_p2_*` (which is P2's own data)

**Solution:**
- Automatically filters out `remote_*` and `wsl_*` directories when listing/exporting from remote sources
- Only native workspaces are fetched, not cached remote data
- Enables safe bidirectional syncing between machines

### Cache Storage

**Remote caches:**
- Format: `remote_hostname_workspace`
- Location: `~/.claude/projects/remote_hostname_workspace`
- Example: `remote_vm01_home-alice-myproject`

**WSL caches:**
- WSL uses direct filesystem access (no caching)
- Remote caches on Windows use same format as SSH remotes

## Command Reference

### `--list-wsl`

List available WSL distributions with Claude Code workspaces.

```powershell
python claude-history --list-wsl
```

**Output:**
- Tab-separated table of WSL distributions
- Distribution name, username, and Claude projects path
- Only shows distributions with Claude Code installed

**Example:**
```powershell
PS C:\> python claude-history --list-wsl
DISTRO          USERNAME        PATH
Ubuntu          alice           /home/alice/.claude/projects
Ubuntu-22.04    bob             /home/bob/.claude/projects
```

### `--list-windows`

List available Windows users with Claude Code workspaces (from WSL).

```bash
./claude-history --list-windows
```

**Output:**
- Tab-separated table of Windows users
- Username, drive letter, workspace count, and path
- Only shows users with Claude Code installed

**Example:**
```bash
$ ./claude-history --list-windows
USERNAME    DRIVE    WORKSPACES    PATH
alice       c        16            /mnt/c/Users/alice
bob         d        8             /mnt/d/Users/bob
```

**Note:** This command is only available when running from WSL.

### `list` (alias: `lss`)

Show all sessions for a workspace.

```bash
claude-sessions list [PATTERN|--this|--all] [--since DATE] [--until DATE] [-r HOST]
```

**Arguments:**
- `PATTERN`: Workspace name pattern to match (optional)
- `--this`: Use current project workspace
- `--all`: Show all workspaces

**Date Filtering:**
- `--since DATE`: Only include sessions modified on or after this date (YYYY-MM-DD)
- `--until DATE`: Only include sessions modified on or before this date (YYYY-MM-DD)

**Remote Access:**
- `-r HOST`, `--remote HOST`: Access remote or WSL workspaces
  - SSH: `-r user@hostname`
  - WSL: `-r wsl://DistroName`

**Output:**
- List of sessions with metadata
- Total size, message count, date range
- Grouped by workspace

**WSL Example:**
```powershell
# List sessions from WSL workspace
python claude-history lss myproject -r wsl://Ubuntu
```

### `export`

Export sessions from workspace(s) to markdown with flexible scope control.

```bash
claude-history export [WORKSPACE] [OPTIONS]
```

**Scope Flags (Orthogonal):**
- `--as, --all-sources`: Export from ALL sources (local + WSL + Windows + remotes)
- `--aw, --all-workspaces` (also `-a, --all`): Export ALL workspaces (default: current workspace)

**Arguments:**
- `WORKSPACE`: Workspace name pattern (optional, defaults to current workspace)
- `output_dir`: Output directory positional argument (optional)

**Options:**
- `-o, --output DIR`: Output directory (overrides positional, default: `./claude-conversations`)
- `-r, --remote HOST`: Add remote source - can be used multiple times
  - SSH: `-r user@hostname`
  - WSL: `-r wsl://DistroName`
  - Windows: `-r windows`
- `--force`, `-f`: Force re-export all sessions (default: incremental)
- `--since DATE`: Only include sessions modified on or after this date (YYYY-MM-DD)
- `--until DATE`: Only include sessions modified on or before this date (YYYY-MM-DD)
- `--minimal`: Export minimal mode (conversation content only, no metadata)
- `--split LINES`: Split long conversations into parts of approximately LINES per file
- `--flat`: Use flat directory structure (default: organized by workspace)

**Orthogonal Design:**

The export command uses independent flags that can be combined:

| Command | Workspace Scope | Source Scope |
|---------|----------------|--------------|
| `export` | Current | Local only |
| `export --as` | Current | All sources |
| `export --aw` | All | Local only |
| `export --as --aw` | All | All sources |

**Examples:**

```bash
# Current workspace, local source (default)
export

# Current workspace, all sources (local + WSL + Windows + remotes)
export --as

# All workspaces, local source
export --aw

# All workspaces, all sources (equivalent to old export-all)
export --as --aw

# Specific workspace, all sources, custom output
export myproject --as -o /tmp/backup

# All workspaces matching pattern, all sources
export astro --as --aw

# Current workspace, all sources + specific SSH remote
export --as -r user@vm01 -r user@vm02

# With splitting and minimal mode
export myproject --as --minimal --split 500 -o ./exports
```

**Output:**
- Markdown files named `{timestamp}_{session-id}.md`
- Source-tagged filenames: `wsl_ubuntu_`, `windows_`, `remote_hostname_`
- Organized by workspace subdirectories (unless `--flat`)
- Conversion summary with per-source statistics

### `export-all`

Export conversations from all sources in a single command. Environment-aware: automatically detects whether running on Windows or WSL and exports from all available sources.

```bash
claude-history export-all [WORKSPACE_PATTERN] [OUTPUT_DIR] [OPTIONS]
```

**Arguments:**
- `WORKSPACE_PATTERN`: Optional workspace pattern to filter (default: all workspaces)
- `OUTPUT_DIR`: Output directory (default: `./claude-conversations`)

**Options:**
- `--force`, `-f`: Force re-export all sessions (default: incremental)
- `--since DATE`: Only include sessions modified on or after this date (YYYY-MM-DD)
- `--until DATE`: Only include sessions modified on or before this date (YYYY-MM-DD)
- `--minimal`: Export minimal mode (conversation content only, no metadata)
- `--split LINES`: Split long conversations into parts of approximately LINES per file
- `-r HOST [HOST ...]`, `--remotes HOST [HOST ...]`: Additional SSH remote hosts to include
- `--no-index`: Skip index.md manifest generation

**Output:**
- Organized workspace subdirectories with source-tagged filenames:
  - Local: `20251120_session.md` (no prefix)
  - WSL: `wsl_ubuntu_20251120_session.md`
  - Windows (from WSL): `windows_username_20251120_session.md`
  - SSH Remote: `remote_hostname_20251120_session.md`
- `index.md` manifest file with summary statistics

**Features:**
- **Environment-aware**: Automatically detects Windows or WSL environment
  - **On Windows**: Exports from local Windows + all WSL distributions + remote SSH hosts
  - **On WSL**: Exports from local WSL + all Windows users + remote SSH hosts
- **Pre-flight validation**: Checks all sources before starting export
  - Validates access to local, Windows, WSL, and SSH remotes
  - Prints clear error messages for inaccessible sources
  - Aborts immediately if any source fails validation
  - Only proceeds when ALL sources are accessible
- Consolidates sessions from multiple sources into one location
- Generates index.md with per-source and per-workspace statistics
- Organized by workspace with source tags for easy analysis

**Examples:**

**On Windows:**
```powershell
# Export all workspaces from local Windows + all WSL distributions
python claude-history export-all

# Filter by workspace pattern
python claude-history export-all myproject

# Include SSH remote hosts
python claude-history export-all -r user@vm01 user@vm02

# Custom output directory with splitting
python claude-history export-all ./backups --split 500
```

**On WSL:**
```bash
# Export all workspaces from local WSL + all Windows users
./claude-history export-all

# Filter by workspace pattern
./claude-history export-all myproject

# Include SSH remote hosts
./claude-history export-all -r user@vm01 user@vm02

# Custom output directory with minimal mode
./claude-history export-all ./backups --minimal
```

**Use Case:**
Perfect for backing up all Claude Code conversations across multiple environments, or consolidating sessions for analysis across local systems (Windows/WSL), WSL distributions, Windows users, and remote development machines.

### `convert`

Convert a single conversation file to markdown.

```bash
claude-sessions convert JSONL_FILE [--output FILE] [-r HOST]
```

**Arguments:**
- `JSONL_FILE`: Path to `.jsonl` conversation file

**Options:**
- `--output`, `-o FILE`: Output markdown filename (default: same name with `.md`)
- `--minimal`: Export minimal mode (conversation content only, no metadata)
- `-r HOST`, `--remote HOST`: Access remote or WSL file
  - SSH: `-r user@hostname`
  - WSL: `-r wsl://DistroName`

**Output:**
- Single markdown file
- File size information

**WSL Example:**
```powershell
# Convert a specific WSL session file
python claude-history convert /home/alice/.claude/projects/-home-alice-django/session.jsonl -r wsl://Ubuntu
```

## FAQ

**Q: Where are Claude Code conversations stored?**

A: `~/.claude/projects/` - each workspace has its own subdirectory.

---

**Q: What if I don't know my workspace name?**

A: List all workspaces with:
```bash
ls ~/.claude/projects/
```

Or try a partial match:
```bash
claude-sessions list projects  # Match any workspace with "projects"
```

---

**Q: Can I extract conversations from multiple workspaces?**

A: Yes! Use a broader pattern:
```bash
claude-sessions export ""  # Extract ALL workspaces (use cautiously)
claude-sessions export django  # All workspaces containing "django"
```

---

**Q: What about privacy/sensitive data?**

A: This tool only reads from your local `~/.claude/` directory. No data is sent anywhere. Review generated markdown files before sharing.

---

**Q: Can I use this with the official claude-conversation-extractor?**

A: Yes, they're complementary:
- Use this tool for **workspace-filtered** extraction
- Use `claude-conversation-extractor` for **session-ID-based** extraction

---

**Q: What's the difference between main sessions and agent sessions?**

A:
- **Main sessions** (UUID filenames): Your primary conversations with Claude
- **Agent sessions** (`agent-*` filenames): Task subagents spawned during conversations

Both are extracted and converted.

---

**Q: How do I find conversations from a specific date range?**

A: Use the `--since` and `--until` options:
```bash
# List sessions from a date range
claude-sessions list myproject --since 2025-11-01 --until 2025-11-30

# Export only recent conversations
claude-sessions export myproject --since 2025-11-01
```

See the Date Filtering section for more examples.

---

**Q: How do I access Claude Code workspaces in WSL from Windows?**

A: Use the `wsl://` prefix with the `-r` flag:
```powershell
# First, find WSL distributions with Claude workspaces
python claude-history --list-wsl

# Then access the workspace
python claude-history lss myproject -r wsl://Ubuntu
python claude-history export myproject -r wsl://Ubuntu
```

This works without SSH or rsync setup - it uses direct filesystem access via Windows' built-in WSL integration.

---

**Q: Can I access workspaces from multiple sources (local Windows, WSL, remote servers)?**

A: Yes! You can work with all of them:
```powershell
# Local Windows workspaces
python claude-history lss myproject

# WSL workspaces
python claude-history lss myproject -r wsl://Ubuntu

# Remote SSH workspaces
python claude-history lss myproject -r user@server
```

## Troubleshooting

### "Claude projects directory not found"

**Problem:** `~/.claude/projects/` doesn't exist

**Solution:**
1. Install Claude Code: https://claude.com/claude-code
2. Log in: `claude login`
3. Create at least one project/conversation

---

### "No sessions found matching 'pattern'"

**Problem:** No workspaces match your pattern

**Solution:**
1. List all workspaces: `ls ~/.claude/projects/`
2. Try a partial match: use just part of the workspace name
3. Check spelling and case-sensitivity

---

### Permission denied errors

**Problem:** Can't read from `~/.claude/projects/`

**Solution:**
```bash
# Check permissions
ls -la ~/.claude/projects/

# Fix if needed (be careful!)
chmod 700 ~/.claude/projects/
```

---

### Empty or incomplete markdown files

**Problem:** Generated markdown files are empty or cut off

**Solution:**
1. Check the source `.jsonl` file isn't corrupted
2. Ensure the conversation wasn't interrupted mid-session
3. Try converting individual files with `convert` command for better error messages

---

### Windows: "python: command not found"

**Problem:** Windows can't find Python

**Solution:**
1. Install Python from [python.org](https://www.python.org/downloads/)
2. During installation, check "Add Python to PATH"
3. Restart your terminal/PowerShell
4. Verify: `python --version`

---

### Windows: UnicodeEncodeError or codec errors

**Problem:** Encoding errors when exporting conversations

**Solution:**
This should be fixed in the latest version. If you still encounter issues:
1. Ensure you're using the latest version of the tool
2. The tool automatically uses UTF-8 encoding on all platforms
3. Report the issue if it persists

---

### Windows: Remote operations fail with "rsync not found"

**Problem:** Remote export requires rsync, which isn't included in Windows

**Solution:**
Use WSL (Windows Subsystem for Linux) which has full rsync compatibility:
```powershell
wsl python claude-history export -r user@host
```

Alternative options (Chocolatey, Git Bash, Cygwin) may have SSH integration issues.

---

### Windows: "dup() in/out/err failed" rsync error

**Problem:** rsync fails with "dup() in/out/err failed" when using Chocolatey or Git Bash rsync

**Root Cause:** These Windows rsync builds don't properly integrate with Windows OpenSSH client

**Solution:**
Use WSL instead, which has native rsync with full SSH support:
```powershell
wsl python claude-history export -r user@host ./output
```

---

### Windows: SSH connection fails

**Problem:** Can't connect to remote host

**Solution:**
1. Verify OpenSSH client is installed: `ssh -V`
2. If missing: Settings → Apps → Optional Features → OpenSSH Client
3. Set up SSH key: `ssh-keygen -t ed25519`
4. Copy key to remote: `type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh user@host "cat >> .ssh/authorized_keys"`
5. Test connection: `ssh user@host echo ok`

---

### WSL: "No WSL distributions found"

**Problem:** `--list-wsl` returns no distributions or error

**Solution:**
1. Check if WSL is installed: `wsl --version`
2. If not installed, install WSL: `wsl --install` (requires restart)
3. After installation, install a distribution from Microsoft Store (Ubuntu recommended)
4. Launch WSL at least once to complete setup

---

### WSL: "WSL distribution not found"

**Problem:** Error when using `-r wsl://Ubuntu`

**Solution:**
1. List available distributions: `python claude-history --list-wsl`
2. Use exact distribution name from the list (case-sensitive)
3. Common names: `Ubuntu`, `Ubuntu-22.04`, `Ubuntu-20.04`, `Debian`, `kali-linux`
4. Verify the distribution has Claude Code installed: `wsl -d Ubuntu -- test -d ~/.claude/projects && echo "Found" || echo "Not found"`

---

### WSL: "Claude projects directory not found" (in WSL)

**Problem:** WSL distribution has no Claude Code workspaces

**Solution:**
1. Launch WSL: `wsl -d Ubuntu`
2. Install Claude Code (if not installed)
3. Log in: `claude login`
4. Create at least one conversation to initialize `~/.claude/projects/`
5. Verify: `ls ~/.claude/projects/`

---

### WSL: Permission denied or access errors

**Problem:** Can't access WSL filesystem from Windows

**Solution:**
1. Ensure WSL distribution is running: `wsl -d Ubuntu echo ok`
2. Check Windows has WSL integration enabled
3. Try accessing via File Explorer: `\\wsl.localhost\Ubuntu\home\yourusername\.claude\projects`
4. If still failing, restart WSL: `wsl --shutdown` then `wsl -d Ubuntu`

## Contributing

Contributions welcome! This tool was built with Claude Code and is open source.

### Ideas for Contributions

- [x] Add filtering by date range (completed!)
- [ ] Export to other formats (JSON, HTML, PDF)
- [ ] Search functionality within conversations
- [ ] Conversation statistics and analytics
- [ ] Support for conversation threading/branching
- [ ] Integration with other tools

### Development

```bash
# Clone the repository
git clone https://github.com/yourusername/claude-workspace-extract.git
cd claude-workspace-extract

# Make changes
vim claude-sessions

# Test your changes
./claude-sessions list test-workspace
```

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [Claude Code](https://claude.com/claude-code)
- Inspired by Simon Willison's [claude-conversation-extractor](https://github.com/simonw/claude-conversation-extractor)
- Thanks to the Claude Code community

## What's New

### Version 1.2.0 (Latest)

**🎉 Export-All Command:**
- Export from all sources in one command: local + all WSL distributions + SSH remotes
- Automatic WSL distribution discovery
- Generates index.md manifest with per-source statistics
- Example: `python claude-history export-all myproject -r vm01 vm02`

**🔒 Circular Fetching Prevention:**
- Prevents infinite loops when machines fetch from each other
- Automatically filters `remote_*` and `wsl_*` cached directories
- Safe bidirectional syncing between P1 ↔ P2

**🐧 WSL Support:**
- Native Windows support for WSL distributions
- Direct filesystem access via `\\wsl.localhost\` paths
- List, export, and access WSL conversations from Windows
- Example: `python claude-history export myproject -r wsl://Ubuntu`

**📁 Organized Export Structure (Default):**
- Workspace subdirectories with source-tagged filenames
- Source tags: `wsl_ubuntu_`, `remote_hostname_`, or no prefix for local
- Use `--flat` for backward-compatible flat structure

**🔧 Windows Path Handling:**
- Fixed current workspace detection for Windows (C:\ drive support)
- Consistent underscore separators for source tags

### Version 1.1.0

**Remote Operations:**
- SSH remote access with `-r user@hostname`
- Workspace-only listing with `--workspaces-only` flag
- Remote caching for efficient repeated operations

### Version 1.0.0

**Core Features:**
- Workspace-based extraction
- Date filtering with `--since` and `--until`
- Conversation splitting with `--split`
- Complete metadata preservation
- Agent conversation detection
- Incremental export (only new/modified sessions)

## Links

- **Repository:** https://github.com/yourusername/claude-workspace-extract
- **Issues:** https://github.com/yourusername/claude-workspace-extract/issues
- **Claude Code:** https://claude.com/claude-code
- **Claude Code Documentation:** https://docs.claude.com/claude-code

---

**Built with Claude Code** 🤖
