# Claude History Skill - Examples

## Example 1: Finding a Past Discussion

**User**: "What did we discuss about error handling last week?"

**Claude's approach**:

```bash
# Step 1: Export recent sessions
claude-history export --since 2025-11-24 -o /tmp/history --minimal

# Step 2: Search for error-related terms
grep -r -i -l "error handling" /tmp/history/
grep -r -i -l "try.*catch\|exception" /tmp/history/
grep -r -i -l "error.*boundary" /tmp/history/

# Step 3: Read matching files
# [Read tool on matching .md files]
```

**Response**: "Based on your conversation history from last week, I found discussions about error handling in 3 sessions:

1. **Nov 25**: We implemented try-catch blocks for the API client...
2. **Nov 26**: You asked about React error boundaries...
3. **Nov 27**: We fixed the unhandled promise rejection..."

---

## Example 2: Finding How Something Was Fixed

**User**: "How did we fix the authentication bug?"

**Claude's approach**:

```bash
# Export and search
claude-history export --since 2025-11-01 -o /tmp/history --minimal

# Search for auth-related fixes
grep -r -i -l "auth.*fix\|auth.*bug\|login.*error" /tmp/history/
grep -r -i -l "authentication" /tmp/history/
grep -r -i -l "JWT\|token\|session" /tmp/history/

# Look for resolution patterns
grep -r -i -B2 -A5 "fixed\|resolved\|the issue was" /tmp/history/auth-related-file.md
```

---

## Example 3: Usage Statistics

**User**: "How much time did I spend coding this week?"

**Claude's approach**:

```bash
claude-history stats --time --since 2025-11-24
```

**Response**: "Based on your Claude Code usage this week:

- **Total active time**: 12.5 hours
- **Monday**: 3.2 hours
- **Tuesday**: 2.8 hours
- **Wednesday**: 4.1 hours
- **Thursday**: 2.4 hours

This excludes idle gaps over 30 minutes."

---

## Example 4: Tool Usage Analysis

**User**: "Which tools do I use the most?"

**Claude's approach**:

```bash
claude-history stats --tools
```

**Response**: "Your most-used Claude Code tools:

| Tool | Uses | Error Rate |
|------|------|------------|
| Read | 1,245 | 0.2% |
| Edit | 892 | 1.1% |
| Bash | 654 | 3.2% |
| Grep | 421 | 0.5% |
| Write | 234 | 0.8% |

Bash has the highest error rate - often from command failures rather than tool issues."

---

## Example 5: Finding Specific Code

**User**: "Find where we implemented the caching logic"

**Claude's approach**:

```bash
# Export recent history
claude-history export -o /tmp/history --minimal

# Search for caching-related terms
grep -r -i -l "cache" /tmp/history/
grep -r -i -l "redis\|memcache" /tmp/history/
grep -r -i -l "memoize\|lru" /tmp/history/

# Get context around cache implementations
grep -r -i -B3 -A10 "cache.*implementation\|implement.*cache" /tmp/history/
```

---

## Example 6: Export for Backup

**User**: "Backup all my Claude conversations"

**Claude's approach**:

```bash
# Create backup directory with date
mkdir -p ~/backups/claude-$(date +%Y%m%d)

# Export all workspaces from all locations
claude-history export --al --aw -o ~/backups/claude-$(date +%Y%m%d)

# Verify
ls -la ~/backups/claude-$(date +%Y%m%d)/
```

---

## Example 7: Project-Specific History

**User**: "Show me all sessions for the myproject workspace"

**Claude's approach**:

```bash
# List sessions for that workspace
claude-history lss myproject

# See detailed stats
claude-history stats myproject
```

---

## Example 8: Cross-Environment Search

**User**: "Find discussions about Docker across all my machines"

**Claude's approach**:

```bash
# Export from all locations (local + WSL + Windows + remotes)
claude-history export --al --aw -o /tmp/all-history --minimal

# Search across everything
grep -r -i -l "docker\|container\|dockerfile" /tmp/all-history/
```

---

## Example 9: Date-Range Analysis

**User**: "What did I work on in November?"

**Claude's approach**:

```bash
# Get November stats
claude-history stats --by-day --since 2025-11-01 --until 2025-11-30

# See per-workspace breakdown
claude-history stats --by-workspace --since 2025-11-01 --until 2025-11-30

# List all November sessions
claude-history lss --since 2025-11-01 --until 2025-11-30
```

---

## Example 10: Finding Agent Tasks

**User**: "What agent tasks ran during our last session?"

**Claude's approach**:

```bash
# List recent sessions (agent files are prefixed with 'agent-')
claude-history lss --since 2025-11-30

# Export and look at agent files specifically
claude-history export --since 2025-11-30 -o /tmp/recent --minimal

# Agent conversations are in files like agent-*.md
ls /tmp/recent/*/agent-*.md
```

---

## Search Term Expansion Reference

When searching for a topic, expand to related terms:

| Topic | Search Terms |
|-------|-------------|
| **database** | database, db, sql, postgres, mysql, sqlite, mongo, query, ORM, migration |
| **authentication** | auth, login, JWT, token, OAuth, session, password, credentials |
| **API** | api, endpoint, REST, GraphQL, fetch, request, response, HTTP |
| **testing** | test, spec, jest, pytest, mock, assert, coverage, TDD |
| **deployment** | deploy, CI/CD, docker, kubernetes, AWS, production, release |
| **performance** | performance, optimize, slow, fast, cache, memory, CPU |
| **error** | error, exception, bug, crash, fail, issue, problem, fix |
| **UI** | UI, frontend, React, component, CSS, style, layout, render |
