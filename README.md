# claude-sessions

Extract and convert Claude Code conversation history by workspace.

> **TL;DR:** A better way to export Claude Code conversations. Filter by workspace/project instead of juggling brittle session IDs.

## Why This Tool?

When you use [Claude Code](https://claude.com/claude-code), your conversations are stored in `~/.claude/projects/`. While tools like [`claude-conversation-extractor`](https://github.com/simonw/claude-conversation-extractor) exist, they have limitations:

| Problem | This Tool's Solution |
|---------|---------------------|
| ❌ Session IDs change between runs | ✅ Stable file-path-based approach |
| ❌ Can't filter by workspace/repo | ✅ Search by workspace pattern |
| ❌ Manual session number selection | ✅ Automatic batch processing |
| ❌ Mixed conversations from different projects | ✅ Workspace-filtered extraction |

This tool extracts conversations **by workspace**, making it easy to get conversation history for a specific project.

## Quick Start

```bash
# Make executable
chmod +x claude-sessions

# List sessions from current project (default)
./claude-sessions list

# Export sessions from current project to markdown (default)
./claude-sessions export

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

- Python 3.6 or higher (uses only stdlib, no external dependencies)
- Claude Code installed and logged in (`claude login`)
- At least one Claude Code conversation/session

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

## Command Reference

### `list`

Show all sessions for a workspace.

```bash
claude-sessions list [PATTERN|--this|--all] [--since DATE] [--until DATE]
```

**Arguments:**
- `PATTERN`: Workspace name pattern to match (optional)
- `--this`: Use current project workspace
- `--all`: Show all workspaces

**Date Filtering:**
- `--since DATE`: Only include sessions modified on or after this date (YYYY-MM-DD)
- `--until DATE`: Only include sessions modified on or before this date (YYYY-MM-DD)

**Output:**
- List of sessions with metadata
- Total size, message count, date range
- Grouped by workspace

### `export`

Export all sessions from a workspace to markdown.

```bash
claude-sessions export [PATTERN|--this|--all] [OPTIONS]
```

**Arguments:**
- `PATTERN`: Workspace name pattern to match (optional)
- `--this`: Use current project workspace
- `--all`: Export all workspaces

**Options:**
- `--output-dir`, `-o DIR`: Output directory (default: `./claude-conversations`)
- `--force`, `-f`: Force re-export all sessions, even if already exported (default: incremental)
- `--since DATE`: Only include sessions modified on or after this date (YYYY-MM-DD)
- `--until DATE`: Only include sessions modified on or before this date (YYYY-MM-DD)

**Output:**
- Markdown files named `{session-id}.md`
- Conversion summary with statistics

### `convert`

Convert a single conversation file to markdown.

```bash
claude-sessions convert JSONL_FILE [--output FILE]
```

**Arguments:**
- `JSONL_FILE`: Path to `.jsonl` conversation file

**Options:**
- `--output`, `-o FILE`: Output markdown filename (default: same name with `.md`)

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

## Links

- **Repository:** https://github.com/yourusername/claude-workspace-extract
- **Issues:** https://github.com/yourusername/claude-workspace-extract/issues
- **Claude Code:** https://claude.com/claude-code
- **Claude Code Documentation:** https://docs.claude.com/claude-code

---

**Built with Claude Code** 🤖
