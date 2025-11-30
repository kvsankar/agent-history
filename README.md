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

## Highlights

**📋 Multiple Workspace Patterns:**

Specify multiple workspace patterns in a single command:

```bash
# List/export from multiple workspaces
./claude-history lsw proj1 proj2            # match any pattern
./claude-history lss proj1 proj2            # sessions from both
./claude-history export proj1 proj2         # export both

# Works with --as (all sources)
./claude-history export --as proj1 proj2 -r host

# Sessions deduplicated when patterns overlap
```

**🔄 Lenient Multi-Source Export:**

When using `export --as` with multiple patterns, the tool is lenient:
- No error when a pattern doesn't match on a particular source
- Reports "No matching sessions" and continues to next source
- Only fails if nothing matches anywhere
- Perfect for multi-environment exports

```bash
# Export proj1 and proj2 from all sources
# Won't fail if proj2 doesn't exist on remote
./claude-history export --as proj1 proj2 -r vm01

# Output:
# [Local] 8 sessions exported
# [Windows] 5 sessions exported
# [Remote] No matching sessions   ← continues without error
```

**🏷️ Workspace Aliases:**

Group related workspaces across environments for consolidated export:

```bash
# Create alias and add workspaces using patterns
./claude-history alias create myproject
./claude-history alias add myproject myproject        # pattern-based
./claude-history alias add myproject --windows myproject
./claude-history alias add myproject -r user@vm myproject

# Or add from all sources at once
./claude-history alias add myproject --as -r user@vm myproject

# Use aliases with @ prefix or --alias flag
./claude-history lss @myproject
./claude-history export @myproject -o ./backup
./claude-history export --alias myproject

# Sync aliases across machines
./claude-history alias export > aliases.json
./claude-history alias import aliases.json
```

**Key Benefits:**
- Consolidate workspaces that moved or were renamed
- Group related projects across local, WSL, Windows, and remote
- Simple JSON storage in `~/.claude-history/aliases.json`
- Easy sync via git, rsync, or cloud storage

See [CLAUDE.md](CLAUDE.md) for complete alias documentation.

**🆕 Multi-Environment Access:**

```bash
# Discover all Claude Code installations
./claude-history lsh                 # all hosts (local + WSL + Windows)
./claude-history lsh --wsl           # only WSL distributions
./claude-history lsh --windows       # only Windows users

# Access workspaces across environments
./claude-history lsw --wsl           # list WSL workspaces
./claude-history lss --windows       # list Windows sessions
./claude-history export proj --wsl   # export from WSL
```

**Key Benefits:**
- **Cleaner**: `--wsl` and `--windows` flags for local environment access
- **Network SSH**: Use `-r user@host` for remote development machines
- **Consistent**: Works across all commands (lsw, lss, export)
- **Conceptual clarity**: WSL/Windows = same machine; SSH = network remotes

See [CLAUDE.md](CLAUDE.md) for complete documentation.

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
python claude-history lsh --wsl
```

**Output:**
```
WSL Distributions:
  Ubuntu          alice           5 workspaces     \\wsl.localhost\Ubuntu\home\alice\.claude\projects
  Ubuntu-22.04    alice           3 workspaces     \\wsl.localhost\Ubuntu-22.04\home\alice\.claude\projects
```

#### Access WSL Workspaces

Use the `--wsl` flag to access WSL workspaces (auto-detects the distribution):

```powershell
# List workspaces in WSL
python claude-history lsw --wsl

# List sessions from a WSL workspace
python claude-history lss myproject --wsl

# Export WSL conversations to Windows
python claude-history export myproject --wsl

# Specify output directory
python claude-history export myproject --wsl -o ./wsl-conversations
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
PS C:\> python claude-history lsh --wsl
WSL Distributions:
  Ubuntu          alice           5 workspaces     \\wsl.localhost\Ubuntu\home\alice\.claude\projects

# 2. List all workspaces in WSL
PS C:\> python claude-history lsw --wsl

# 3. List sessions from a specific workspace
PS C:\> python claude-history lss django-app --wsl

# 4. Export to Windows filesystem
PS C:\> python claude-history export django-app --wsl -o ./wsl-exports
```

#### Tips

- **Combine with Other Flags:** Use `--since`, `--until`, `--minimal`, `--split` with `--wsl`
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
python claude-history export myproject --as -o ./backups -r user@vm01 -r user@vm02

# Or all workspaces from all sources:
python claude-history export --as --aw -o ./backups -r user@vm01 -r user@vm02

# Perfect for:
# - Backing up all Claude sessions across environments
# - Analyzing conversations across different machines
# - Creating comprehensive project history
```

**Circular Fetching Prevention:** When P1 fetches from P2 and P2 fetches from P1, the tool automatically filters out cached remote data (`remote_*` and `wsl_*` directories) to prevent infinite loops. Only native workspaces are fetched from each source.

## Cookbook

Common workflows and recipes for managing Claude Code conversations across environments.

### Recipe 1: Set Up a Cross-Environment Alias

Create an alias to manage a project that exists on Windows, WSL, and a remote VM:

```bash
# Create the alias
./claude-history alias create myproject

# Add workspaces interactively from all sources
./claude-history alias add myproject --as -r user@vm01 --pick

# Or add by pattern (non-interactive)
./claude-history alias add myproject myproject                    # local
./claude-history alias add myproject --windows myproject          # Windows
./claude-history alias add myproject -r user@vm01 myproject       # remote

# View the alias
./claude-history alias show myproject
```

### Recipe 2: Daily Backup of All Sessions

Export all sessions from all environments to a backup directory:

```bash
# One-time: create an alias for everything
./claude-history alias create all-projects
./claude-history alias add all-projects --as -r vm01 -r vm02 --pick

# Daily backup (incremental - only exports new/changed files)
./claude-history export @all-projects -o ~/backups/claude-sessions/

# Force re-export everything
./claude-history export @all-projects -o ~/backups/claude-sessions/ --force
```

### Recipe 3: Export a Single Project from Multiple Machines

```bash
# List sessions from all sources matching "myproject"
./claude-history lss myproject --as -r user@vm01

# Export from all sources
./claude-history export myproject --as -r user@vm01 -o ./exports/
```

### Recipe 4: Search Across All Environments

```bash
# List all workspaces from everywhere
./claude-history lsw --as -r user@vm01 -r user@vm02

# Find sessions mentioning a specific project
./claude-history lsw --as | grep django

# List sessions from matching workspaces
./claude-history lss django --as
```

### Recipe 5: Sync Remote Sessions for Offline Access

```bash
# Fetch and cache remote sessions locally
./claude-history export myproject -r user@vm01

# Later, work with cached data (no network needed)
./claude-history lss remote_vm01_home-user-myproject
```

### Recipe 6: Export for Sharing (Minimal Mode)

Create clean exports without metadata for blog posts or documentation:

```bash
# Export without UUIDs, token counts, and navigation links
./claude-history export myproject --minimal -o ./blog-posts/

# Split long conversations into manageable parts
./claude-history export myproject --minimal --split 500 -o ./blog-posts/
```

### Recipe 7: Move Aliases Between Machines

```bash
# On source machine: export aliases
./claude-history alias export aliases.json

# Copy to target machine
scp aliases.json user@newmachine:~/

# On target machine: import aliases
./claude-history alias import aliases.json
```

### Recipe 8: List Recent Sessions Across Everything

```bash
# Sessions from last week across all sources
./claude-history lss --as --since 2025-11-24

# Export recent sessions only
./claude-history export @myproject --since 2025-11-01 -o ./recent/
```

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
python claude-history lsh --wsl

# List WSL workspaces (auto-detects distribution)
python claude-history lsw --wsl

# Export from WSL
python claude-history export myproject --wsl
```

**How it works:**
- Auto-detects the WSL distribution
- Direct filesystem access via `\\wsl.localhost\DistroName\` paths
- No SSH or rsync needed
- Native Windows file operations

### Windows Access (from WSL)

Access conversations from Windows directly from WSL:

```bash
# List available Windows users with Claude
./claude-history lsh --windows

# List Windows workspaces (auto-detects user)
./claude-history lsw --windows

# Export from Windows
./claude-history export myproject --windows
```

**How it works:**
- Auto-detects Windows user
- Works on any drive letter (C:, D:, E:, etc.)
- Direct filesystem access via `/mnt/c/Users/...` paths
- No SSH or rsync needed
- Native file operations

**Example output:**
```bash
$ ./claude-history lsh --windows
Windows Users:
  alice       /mnt/c/Users/alice        16 workspaces

$ ./claude-history lsw --windows
/C/alice/projects/claude-sessions
/C/alice/projects/astromcp
...

$ ./claude-history export claude-sessions --windows
./claude-conversations/claude-sessions/windows_20251120_session.md
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

### `lsh` - List Hosts

List all Claude Code installations across local, WSL, and Windows environments.

```bash
./claude-history lsh [--local|--wsl|--windows]
```

**Options:**
- No flags: Show all hosts (local + WSL + Windows)
- `--local`: Show only local installation
- `--wsl`: Show only WSL distributions
- `--windows`: Show only Windows users

**Examples:**
```bash
# Show all hosts
$ ./claude-history lsh
Local:
  /home/alice/.claude	10 workspaces

WSL Distributions:
  Ubuntu          alice           5 workspaces     \\wsl.localhost\Ubuntu\home\alice\.claude\projects

Windows Users:
  alice       /mnt/c/Users/alice        16 workspaces

# Show only WSL distributions
$ ./claude-history lsh --wsl
WSL Distributions:
  Ubuntu          alice           5 workspaces     \\wsl.localhost\Ubuntu\home\alice\.claude\projects
```

### `list` (alias: `lss`)

Show all sessions for a workspace.

```bash
claude-sessions list [PATTERN|--this|--all] [--since DATE] [--until DATE] [--wsl|--windows|-r HOST]
```

**Arguments:**
- `PATTERN`: Workspace name pattern to match (optional)
- `--this`: Use current project workspace
- `--all`: Show all workspaces

**Date Filtering:**
- `--since DATE`: Only include sessions modified on or after this date (YYYY-MM-DD)
- `--until DATE`: Only include sessions modified on or before this date (YYYY-MM-DD)

**Multi-Environment Access:**
- `--wsl`: Access WSL distribution (auto-detects)
- `--windows`: Access Windows user (auto-detects)
- `-r HOST`, `--remote HOST`: Access SSH remote server (`user@hostname`)

**Output:**
- List of sessions with metadata
- Total size, message count, date range
- Grouped by workspace

**Examples:**
```bash
# List sessions from WSL
./claude-history lss myproject --wsl

# List sessions from Windows
./claude-history lss myproject --windows

# List sessions from SSH remote
./claude-history lss myproject -r user@hostname
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
- `WORKSPACE`: One or more workspace patterns (optional, defaults to current workspace)
  - Multiple patterns supported: `export proj1 proj2`
  - Sessions deduplicated when patterns overlap
- `output_dir`: Output directory positional argument (optional)

**Options:**
- `-o, --output DIR`: Output directory (overrides positional, default: `./claude-conversations`)
- `--wsl`: Export from WSL (auto-detects distribution)
- `--windows`: Export from Windows (auto-detects user)
- `-r, --remote HOST`: Add SSH remote source - can be used multiple times (`user@hostname`)
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

# All workspaces, all sources
export --as --aw

# Specific workspace, all sources, custom output
export myproject --as -o /tmp/backup

# Multiple workspaces (deduplicated)
export proj1 proj2 -o ./exports

# Multiple workspaces from all sources (lenient - continues if pattern doesn't match)
export --as proj1 proj2 -r host

# All workspaces matching pattern, all sources
export astro --as --aw

# Export from WSL
export myproject --wsl

# Export from Windows
export myproject --windows

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
- `index.md` manifest file with summary statistics (when using `--as`)

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
- `-r HOST`, `--remote HOST`: Access remote file via SSH (`user@hostname`)
- `--wsl`: Access WSL file (auto-detects distribution)
- `--windows`: Access Windows file (auto-detects user)

**Output:**
- Single markdown file
- File size information

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

A: Use the `--wsl` flag (auto-detects the distribution):
```powershell
# First, find WSL distributions with Claude workspaces
python claude-history lsh --wsl

# Then access the workspace
python claude-history lss myproject --wsl
python claude-history export myproject --wsl
```

This works without SSH or rsync setup - it uses direct filesystem access via Windows' built-in WSL integration.

---

**Q: Can I access workspaces from multiple sources (local Windows, WSL, remote servers)?**

A: Yes! You can work with all of them:
```bash
# Discover all hosts
./claude-history lsh

# Local workspaces
./claude-history lss myproject

# WSL workspaces
./claude-history lss myproject --wsl

# Windows workspaces (from WSL)
./claude-history lss myproject --windows

# Remote SSH workspaces
./claude-history lss myproject -r user@server
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

**Problem:** `lsh --wsl` returns no distributions or error

**Solution:**
1. Check if WSL is installed: `wsl --version`
2. If not installed, install WSL: `wsl --install` (requires restart)
3. After installation, install a distribution from Microsoft Store (Ubuntu recommended)
4. Launch WSL at least once to complete setup

---

### WSL: "Claude projects directory not found" (in WSL)

**Problem:** WSL distribution has no Claude Code workspaces

**Solution:**
1. Launch WSL: `wsl`
2. Install Claude Code (if not installed)
3. Log in: `claude login`
4. Create at least one conversation to initialize `~/.claude/projects/`
5. Verify: `ls ~/.claude/projects/`

---

### WSL: Permission denied or access errors

**Problem:** Can't access WSL filesystem from Windows

**Solution:**
1. Ensure WSL distribution is running: `wsl echo ok`
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

## Changelog

### Version 1.3.6

- `alias add` accepts patterns, paths, or encoded names
- `alias add --as` to add from all sources at once
- `--wsl` and `--windows` flags auto-detect (no longer take optional arguments)
- Windows path normalization handles hyphenated directory names correctly

### Version 1.3.5

- SSH remote export finds cached sessions correctly
- Helpful error messages when `lss`/`export` run outside a workspace
- `--aw` and `--as` flags work from any directory

### Version 1.3.4

- Multiple workspace patterns: `lsw/lss/export pattern1 pattern2`
- Sessions deduplicated when patterns overlap
- Lenient multi-source export (continues if pattern doesn't match on a source)

### Version 1.3.3

- Multiple patterns work with all source types: SSH, Windows, WSL

### Version 1.3.2

- Date filtering for remote sessions applied after fetching

### Version 1.3.1

- `--as` (`--all-sources`) flag for `lsw` and `lss` commands
- Multiple `-r` flags supported: `lsw --as -r vm01 -r vm02`

### Version 1.3.0

- Workspace aliases to group workspaces across environments
- `@aliasname` prefix or `--alias` flag for lss/export
- Import/export aliases for sync across machines

### Version 1.2.1

- Windows compatibility: UTF-8 encoding for console
- Removed deprecated `--list-wsl` and `--list-windows` flags

### Version 1.2.0

- `lsh` command to discover all Claude Code installations
- `--wsl` and `--windows` flags across all commands
- Unified export interface with `--as` and `--aw` flags
- Circular fetching prevention for cached workspaces
- WSL support via `\\wsl.localhost\` paths
- Organized export structure with source-tagged filenames

### Version 1.1.0

- SSH remote access with `-r user@hostname`
- Remote caching for efficient repeated operations

### Version 1.0.0

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
