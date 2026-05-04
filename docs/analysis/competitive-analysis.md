# Claude History Tool: Competitive Analysis & Roadmap

*Research Date: December 2025*

## Executive Summary

The Claude Code conversation history export ecosystem has grown significantly, with tools ranging from simple CLI extractors to full desktop applications with analytics. This report analyzes **15+ competing tools** and provides a comparison matrix to position `claude-history` within the market.

**Key Finding:** `claude-history` has unique capabilities in **multi-environment access** (SSH, WSL, Windows), **workspace aliases**, and **orthogonal source/workspace filtering** that no other tool offers. However, there are opportunities in areas like GUI interfaces, MCP integration, and real-time monitoring.

---

## Tool Categories

### 1. CLI Export Tools
- [claude-history (this project)](#claude-history-this-project)
- [claude-conversation-extractor](#claude-conversation-extractor-zerosumquant)
- [cc-history-export](#cc-history-export-eternnoir)
- [claude-history (thejud)](#claude-history-thejud)

### 2. Desktop/GUI Applications
- [claude-code-history-viewer (jhlee0409)](#claude-code-history-viewer-jhlee0409)
- [claude-code-history-viewer (yanicklandry)](#claude-code-history-viewer-yanicklandry)

### 3. Usage Analytics & Monitoring
- [ccusage](#ccusage-ryoppippi)
- [Claude-Code-Usage-Monitor](#claude-code-usage-monitor-maciek-roboblog)

### 4. MCP Servers
- [claude-historian](#claude-historian-vvkmnn)
- [Claude Code History MCP](#claude-code-history-mcp)
- [ClaudeKeep](#claudekeep-sdairs) (discontinued)

### 5. Browser Extensions & Web Tools
- [claude-export](#claude-export-ryanschiang)
- [Claude Exporter](#claude-exporter-chrome-extension)
- [Simon Willison's Observable Notebook](#simon-willisons-observable-notebook)
- [claude-chat-viewer](#claude-chat-viewer-osteele)

---

## Detailed Tool Analysis

### claude-history (this project)

**Repository:** Local project
**Language:** Python (single file, no dependencies)
**Status:** Active (v1.4.1)

**Unique Strengths:**
- Multi-environment access (SSH remotes, WSL, Windows cross-access)
- Workspace aliases for grouping related projects
- Orthogonal `--ah`/`--aw` flags for source/workspace scoping
- Full metadata preservation with navigation links
- Usage statistics with SQLite database
- Time tracking with daily breakdown
- Incremental export (only new/changed files)
- Conversation splitting for long sessions
- Automatic alias scoping

**Limitations:**
- CLI only (no GUI)
- No MCP server integration
- No real-time monitoring

---

### claude-conversation-extractor (ZeroSumQuant)

**Repository:** [github.com/ZeroSumQuant/claude-conversation-extractor](https://github.com/ZeroSumQuant/claude-conversation-extractor)
**Language:** Python
**Installation:** `pipx install claude-conversation-extractor`

**Features:**
- Interactive UI with ASCII art (`claude-start`)
- Real-time search across conversations
- Export to Markdown, JSON, HTML
- Detailed mode with tool invocations and MCP responses
- Case-insensitive full-text search

**Limitations:**
- Local-only (no remote access)
- No date filtering
- No usage statistics
- No workspace aliasing

---

### cc-history-export (eternnoir)

**Repository:** [github.com/eternnoir/cc-history-export](https://github.com/eternnoir/cc-history-export)
**Language:** Go
**Installation:** Binary downloads or build from source

**Features:**
- Export to JSON, Markdown, HTML
- Date/time range filtering
- Project filtering
- Batch export to separate files
- Pipeline integration (stdout + jq)
- Token usage in JSON output
- Todo list extraction
- Cross-platform binaries

**Limitations:**
- Local-only (no remote/WSL access)
- No usage analytics dashboard
- No workspace aliasing
- No incremental export

---

### claude-history (thejud)

**Repository:** [github.com/thejud/claude-history](https://github.com/thejud/claude-history)
**Language:** Python
**Status:** Minimal activity (2 commits)

**Features:**
- Extract user prompts or full conversations
- Chronological ordering
- Timestamp toggle
- Markdown output

**Limitations:**
- Markdown only
- No date filtering
- No search
- No remote access
- No statistics
- Early-stage maturity

---

### claude-code-history-viewer (jhlee0409)

**Repository:** [github.com/jhlee0409/claude-code-history-viewer](https://github.com/jhlee0409/claude-code-history-viewer)
**Platform:** Desktop (macOS, Linux; Windows planned)
**Tech:** Tauri + React + Rust

**Features:**
- Visual file tree navigation
- Syntax-highlighted code blocks
- Activity heatmap
- Tool usage statistics
- Per-project token breakdown
- Dark theme
- Privacy-first (local only)

**Limitations:**
- No Windows support yet
- No remote/WSL access
- No export functionality mentioned
- Beta status (v1.0.0-beta.3)

---

### claude-code-history-viewer (yanicklandry)

**Repository:** [github.com/yanicklandry/claude-code-history-viewer](https://github.com/yanicklandry/claude-code-history-viewer)
**Platform:** Desktop

**Features:**
- Session browser sorted by date
- Full conversation formatting
- Syntax highlighting
- Tool usage display
- Dark theme

**Limitations:**
- Limited documentation
- No analytics
- Local-only

---

### ccusage (ryoppippi)

**Repository:** [github.com/ryoppippi/ccusage](https://github.com/ryoppippi/ccusage)
**Language:** TypeScript/Node.js
**Installation:** `npx ccusage@latest`

**Features:**
- Token tracking (input, output, cache)
- Cost analysis in USD
- Daily/monthly/session views
- 5-hour billing block monitoring
- Live dashboard with real-time burn rate
- JSON export
- Model breakdown (Opus, Sonnet, etc.)
- Compact mode for screenshots
- Offline mode with cached pricing

**Limitations:**
- Usage analytics only (no conversation export)
- No remote access
- No workspace aliasing

---

### Claude-Code-Usage-Monitor (Maciek-roboblog)

**Repository:** [github.com/Maciek-roboblog/Claude-Code-Usage-Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor)
**Language:** Python
**Installation:** `uv tool install claude-monitor`

**Features:**
- Real-time terminal monitoring
- ML-based predictions for session limits
- Rich UI with color-coded progress bars
- Multi-level alert warnings
- Token burn rate tracking
- Cost estimation

**Limitations:**
- Monitoring only (no export)
- Real-time focus (no historical analysis)
- No remote access

---

### claude-historian (Vvkmnn)

**Repository:** [github.com/Vvkmnn/claude-historian](https://github.com/Vvkmnn/claude-historian)
**Type:** MCP Server
**Installation:** `npx claude-historian`

**Features:**
- Search past conversations from within Claude
- Find file context for specific files
- Get error solutions from history
- Find similar queries
- List recent sessions
- Find tool usage patterns
- No external dependencies
- 50% token reduction with parallel processing

**Limitations:**
- Search only (no export)
- Claude Desktop blocked by LevelDB locks
- Requires Claude Code to access

---

### Claude Code History MCP

**Repository:** Listed on LobeHub MCP registry
**Type:** MCP Server

**Features:**
- List all projects with conversation history
- List conversation sessions
- Read from `.jsonl` files

**Limitations:**
- Basic functionality
- No search
- No export

---

### ClaudeKeep (sdairs)

**Repository:** [github.com/sdairs/claudekeep](https://github.com/sdairs/claudekeep)
**Status:** **Discontinued** (Anthropic trademark takedown)

**Features (historical):**
- Save conversations during chat
- Share chats publicly
- OAuth login integration

**Note:** Code remains available but service is shut down.

---

### claude-export (ryanschiang)

**Repository:** [github.com/ryanschiang/claude-export](https://github.com/ryanschiang/claude-export)
**Type:** Browser script

**Features:**
- Export from Claude.ai web interface
- Markdown, JSON, PNG formats
- Runs locally in browser console

**Limitations:**
- Claude.ai only (not Claude Code)
- Manual process
- No batch export

---

### Claude Exporter (Chrome Extension)

**URL:** [Chrome Web Store](https://chromewebstore.google.com/detail/claude-exporter-save-clau/elhmfakncmnghlnabnolalcjkdpfjnin)

**Features:**
- Export to PDF, Markdown, Text, CSV, JSON
- Supports artifacts and reasoning
- Works with Claude.ai web interface

**Limitations:**
- Claude.ai only (not Claude Code)
- Browser extension required

---

### Simon Willison's Observable Notebook

**URL:** [observablehq.com/@simonw/convert-claude-json-to-markdown](https://observablehq.com/@simonw/convert-claude-json-to-markdown)

**Features:**
- Convert Claude JSON to Markdown
- Web-based tool
- No installation required

**Limitations:**
- Claude.ai only (not Claude Code)
- Requires manual JSON extraction via DevTools
- No batch processing

---

### claude-chat-viewer (osteele)

**Repository:** [github.com/osteele/claude-chat-viewer](https://github.com/osteele/claude-chat-viewer)

**Features:**
- Web viewer for exported JSON
- Code block rendering
- Artifact support
- Thinking process sections

**Limitations:**
- Viewer only (not extractor)
- Requires pre-exported JSON

---

## Comparison Matrix

| Feature | claude-history (this) | claude-conversation-extractor | cc-history-export | ccusage | claude-code-history-viewer | claude-historian |
|---------|----------------------|------------------------------|-------------------|---------|---------------------------|------------------|
| **Export Formats** |
| Markdown | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| JSON | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| HTML | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Filtering** |
| Date range | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| Workspace pattern | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Full-text search | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |
| **Multi-Environment** |
| SSH remote | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| WSL access | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Windows access | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| All homes (--ah) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Organization** |
| Workspace aliases | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Auto alias scoping | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Incremental export | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Analytics** |
| Token usage | ✅ | ❌ | ✅ (JSON) | ✅ | ✅ | ❌ |
| Cost tracking | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Time tracking | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Tool usage stats | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| Activity heatmap | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **Interface** |
| CLI | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| GUI | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| MCP Server | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Real-time monitor | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| **Other** |
| Conversation splitting | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Minimal mode | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Agent detection | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Navigation links | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Zero dependencies | ✅ | ✅ | ✅ (binary) | ❌ | ❌ | ✅ |

### Legend
- ✅ Fully supported
- ❌ Not supported

---

## Competitive Positioning

### claude-history Unique Advantages

1. **Multi-Environment Champion**: Only tool supporting SSH, WSL, and Windows cross-access
2. **Workspace Aliases**: Unique feature for grouping related workspaces
3. **Orthogonal Flags**: Clean `--ah`/`--aw` design for source vs workspace scoping
4. **Time Tracking**: Only CLI tool with work time calculation
5. **Information Preservation**: Full metadata with clickable navigation links
6. **Single File**: Easy distribution with no dependencies

### Market Gaps This Project Fills

| Gap | claude-history Solution |
|-----|------------------------|
| Can't export from remote dev servers | SSH remote access with `-r` flag |
| Can't consolidate WSL + Windows sessions | `--ah` flag for all homes |
| Projects scattered across environments | Workspace aliases |
| Re-exporting unchanged files | Incremental export |
| Long conversations are unwieldy | `--split` for manageable parts |

### Where Competitors Excel

| Competitor | Advantage Over claude-history |
|------------|------------------------------|
| ccusage | Real-time cost monitoring, USD pricing |
| claude-code-history-viewer | Visual GUI with heatmaps |
| claude-conversation-extractor | Interactive search UI, HTML export |
| claude-historian | MCP integration for in-Claude search |

---

## Roadmap Recommendations

### Phase 1: Feature Parity (Short-term)

| Feature | Priority | Complexity | Rationale |
|---------|----------|------------|-----------|
| JSON export format | High | Low | Industry standard, enables jq integration |
| Full-text search | High | Medium | Every competitor has this |
| HTML export format | Medium | Medium | Nice for sharing |
| Cost tracking (USD) | Medium | Low | Leverage existing token data |

### Phase 2: Competitive Edge (Medium-term)

| Feature | Priority | Complexity | Rationale |
|---------|----------|------------|-----------|
| MCP Server mode | High | Medium | Enable in-Claude search like claude-historian |
| Interactive TUI | Medium | High | Improve UX without full GUI |
| Activity heatmap (CLI) | Low | Medium | ASCII-based visualization |
| Real-time monitoring | Medium | Medium | Complement ccusage |

### Phase 3: Innovation (Long-term)

| Feature | Priority | Complexity | Rationale |
|---------|----------|------------|-----------|
| Semantic search | Low | High | Beyond keyword matching |
| AI-powered summaries | Low | High | Auto-generate session summaries |
| Git integration | Medium | Medium | Link conversations to commits |
| Team analytics | Low | High | Enterprise feature |
| Web dashboard | Low | High | Optional GUI component |

### Recommended Priority Order

```
1. JSON export format          [Quick win - enables ecosystem integration]
2. Full-text search            [Expected feature - close gap]
3. MCP Server mode             [Strategic - enables new use case]
4. Cost tracking (USD)         [Quick win - data already available]
5. HTML export format          [Nice to have]
6. Interactive TUI             [Differentiation - unique in CLI space]
```

---

## Implementation Notes

### JSON Export (Priority 1)

```python
# Add to existing export command
./claude-history export myproject --format json
./claude-history export myproject --format json | jq '.sessions[].messages'
```

Leverage existing `extract_metrics_from_jsonl()` for structured output.

### Full-Text Search (Priority 2)

```python
# New command
./claude-history search "database connection" --workspace myproject
./claude-history search "error" --since 2025-11-01
```

Index on first run, update incrementally.

### MCP Server Mode (Priority 3)

```python
# New command that starts MCP server
./claude-history mcp serve

# In Claude Desktop config:
{
  "mcpServers": {
    "claude-history": {
      "command": "claude-history",
      "args": ["mcp", "serve"]
    }
  }
}
```

Implement MCP protocol tools: `search_conversations`, `list_sessions`, `export_conversation`.

---

## Sources

### CLI Tools
- [ZeroSumQuant/claude-conversation-extractor](https://github.com/ZeroSumQuant/claude-conversation-extractor)
- [eternnoir/cc-history-export](https://github.com/eternnoir/cc-history-export)
- [thejud/claude-history](https://github.com/thejud/claude-history)
- [ryoppippi/ccusage](https://github.com/ryoppippi/ccusage)
- [Maciek-roboblog/Claude-Code-Usage-Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor)

### Desktop Applications
- [jhlee0409/claude-code-history-viewer](https://github.com/jhlee0409/claude-code-history-viewer)
- [yanicklandry/claude-code-history-viewer](https://github.com/yanicklandry/claude-code-history-viewer)

### MCP Servers
- [Vvkmnn/claude-historian](https://github.com/Vvkmnn/claude-historian)
- [Claude Code History MCP on LobeHub](https://lobehub.com/mcp/yudppp-claude-code-history-mcp)
- [sdairs/claudekeep](https://github.com/sdairs/claudekeep) (discontinued)

### Browser Tools
- [ryanschiang/claude-export](https://github.com/ryanschiang/claude-export)
- [Claude Exporter Chrome Extension](https://chromewebstore.google.com/detail/claude-exporter-save-clau/elhmfakncmnghlnabnolalcjkdpfjnin)
- [Simon Willison's Observable Notebook](https://observablehq.com/@simonw/convert-claude-json-to-markdown)
- [osteele/claude-chat-viewer](https://github.com/osteele/claude-chat-viewer)

### Documentation
- [Claude Code Usage Analytics](https://support.claude.com/en/articles/12157520-claude-code-usage-analytics)
- [Claude Data Export](https://support.claude.com/en/articles/9450526-how-can-i-export-my-claude-data)
- [Simon Willison's Claude Tag](https://simonwillison.net/tags/claude/)

---

*Report generated by Claude Code for the claude-history project*
