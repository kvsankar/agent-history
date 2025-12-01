---
name: claude-history
description: Search and analyze Claude Code conversation history. Use when user asks about past conversations, previous solutions, what was discussed earlier, finding something from history, or analyzing usage patterns. Triggers include "what did we discuss", "find that conversation", "search history", "past sessions", "how much time", "token usage", "which tools".
allowed-tools: Bash, Read, Grep, Glob
---

# Claude History Skill

Browse, search, and analyze Claude Code conversation history using the `claude-history` CLI tool.

## When to Activate

- User asks about **past conversations**: "what did we discuss about X", "find that conversation where we..."
- User wants to **find previous solutions**: "how did we fix that error", "what approach did we use for..."
- User asks about **usage patterns**: "how much time did I spend", "which tools do I use most"
- User wants to **export or backup**: "export my conversations", "backup this project's history"
- User references **earlier sessions**: "yesterday we talked about", "last week's work on..."

## Available Commands

### List Sessions
```bash
# Current workspace
./claude-history lss

# All sources (local + WSL + Windows + remotes)
./claude-history lss --as

# Filter by workspace pattern
./claude-history lss myproject

# Filter by date
./claude-history lss --since 2025-11-01
./claude-history lss --since 2025-11-01 --until 2025-11-30
```

### Export to Markdown
```bash
# Export current workspace sessions
./claude-history export

# Export specific workspace
./claude-history export myproject

# Export with date filter
./claude-history export --since 2025-11-24

# Export minimal (no metadata, cleaner for reading)
./claude-history export --minimal

# Export to specific directory
./claude-history export -o /tmp/history-export
```

### Usage Statistics
```bash
# Summary dashboard
./claude-history stats

# Time tracking (work hours per day)
./claude-history stats --time

# Tool usage breakdown
./claude-history stats --tools

# Model usage
./claude-history stats --models

# Daily trends
./claude-history stats --by-day

# Per-workspace breakdown
./claude-history stats --by-workspace
```

### List Workspaces
```bash
# All local workspaces
./claude-history lsw

# Filter by pattern
./claude-history lsw myproject
```

## Data Location

Claude Code stores conversations in `~/.claude/projects/` as JSONL files:
- Main sessions: `{uuid}.jsonl`
- Agent tasks: `agent-{id}.jsonl`

Workspace directories are encoded paths (e.g., `-home-user-myproject` = `/home/user/myproject`).

## Search Strategy (No Built-in Search Yet)

Since the tool doesn't have a search command, use this workflow:

### Method 1: Export + Grep (Recommended)
```bash
# Export recent sessions from ALL workspaces to temp directory
./claude-history export --aw --since 2025-11-24 -o /tmp/history-search --minimal

# Search the exported markdown files
grep -r -i "search term" /tmp/history-search/
```

### Method 2: Direct JSONL Search
```bash
# Find the workspace directory
ls ~/.claude/projects/ | grep myproject

# Search within JSONL files (content is in message.content)
grep -i "search term" ~/.claude/projects/-home-user-myproject/*.jsonl
```

### Method 3: Multi-term Semantic Search

For questions like "what did we discuss about database connections":

1. Generate related search terms based on the topic
2. Run multiple grep searches
3. Synthesize the findings

Example for "database connections":
```bash
# Export recent history from all workspaces first
./claude-history export --aw --since 2025-11-24 -o /tmp/search --minimal

# Search for related terms
grep -r -i -l "database" /tmp/search/
grep -r -i -l "connection" /tmp/search/
grep -r -i -l "postgres\|mysql\|sqlite\|mongo" /tmp/search/
grep -r -i -l "sql" /tmp/search/
grep -r -i -l "pool\|timeout" /tmp/search/
```

Then read the matching files to find relevant conversations.

## Common Workflows

### "What did we discuss about X last week?"

1. Export recent sessions from all workspaces:
   ```bash
   ./claude-history export --aw --since 2025-11-24 -o /tmp/history --minimal
   ```

2. Search for the topic and variations:
   ```bash
   grep -r -i -l "TOPIC" /tmp/history/
   grep -r -i -l "RELATED_TERM1" /tmp/history/
   grep -r -i -l "RELATED_TERM2" /tmp/history/
   ```

3. Read matching files to summarize findings

### "How did we fix that error?"

1. Search for error-related terms:
   ```bash
   ./claude-history export --aw --since 2025-11-01 -o /tmp/history --minimal
   grep -r -i "error\|exception\|failed" /tmp/history/ | head -50
   ```

2. Look for solution patterns:
   ```bash
   grep -r -i -A5 "fixed\|resolved\|solution" /tmp/history/
   ```

### "How much time have I spent on this project?"

```bash
./claude-history stats --time
```

### "Which tools do I use most?"

```bash
./claude-history stats --tools
```

### "Show me my activity this month"

```bash
./claude-history stats --by-day --since 2025-11-01
```

### "Export everything for backup"

```bash
./claude-history export --as --aw -o ~/claude-backup/
```

## Tips

- **Use `--minimal` for reading**: Omits UUIDs and metadata, much cleaner
- **Use `--since` to narrow scope**: Faster searches on recent history
- **Check multiple workspaces**: Use `lsw` to see all available workspaces
- **Agent files exist**: Tasks spawn `agent-*.jsonl` files with sub-conversations
- **Incremental export**: Re-running export skips unchanged files

## Output Formats

Exported markdown includes:
- Message timestamps
- User/Assistant labels
- Tool use details (name, input, output)
- Token usage (in non-minimal mode)
- Navigation links between messages (in non-minimal mode)

## Limitations

- No built-in semantic search (use grep + Claude reasoning)
- No full-text index (searches scan files each time)
- Remote sources require SSH access configured
