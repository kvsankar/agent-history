# agent-history Process Image Brief

Use this document when creating the agent-history process image with ChatGPT
Images 2.0 or another image model.

## Preamble For The Diagram Agent

Create an engineering process diagram, not a marketing illustration and not a
textual flowchart. Treat this file as the source of truth for the diagram.

Return a single finished image. Do not output Mermaid, SVG code, ASCII art, a
diagram description, or multiple disconnected mini-diagrams.

The diagram must explain how agent-history collects fragmented AI coding
assistant session files from many places, organizes them by workspace and
project, and turns them into readable exports, queryable listings, and usage
metrics that engineers (and Claude itself, via the bundled skill) can act on.
The image should be accurate enough that an agent-history maintainer recognizes
the current system, and clear enough that a technically literate reader can
understand the main moving parts without reading the repository.

## Diagram Goal

Show agent-history as a unified browse-and-export front end for fragmented AI
coding assistant history:

- It reads existing session files from Claude Code, Codex CLI, Gemini CLI, and Pi;
  it does not record new conversations or modify the agents.
- It reaches across multiple "homes" (local, WSL, Windows-from-WSL, SSH remotes).
- It normalizes per-agent storage layouts into a consistent workspace/session view.
- It groups workspaces across homes via aliases.
- It produces terminal listings, markdown/HTML exports, and a small SQLite metrics db.
- It ships as a single stdlib-only Python file, plus an optional Claude skill.

The diagram should communicate this core idea:

> Scattered agent session files in -> consistent listings, exports, and metrics out.

Avoid language that implies agent-history records or replays conversations,
hosts a chat UI, runs an LLM, or modifies the upstream agents' data.

## Preferred Composition

Use one strong left-to-right engineering diagram.

Recommended layout:

1. Top: title and short subtitle.
2. Left: agent session sources across multiple homes.
3. Middle: agent-history CLI as the unifying core, with per-agent adapters
   feeding a shared workspace/session model.
4. Right: outputs (terminal listings, markdown/HTML exports, SQLite metrics,
   Claude skill integration).
5. Bottom: shared services and storage boundaries.

The agent adapters (Claude Code, Codex CLI, Gemini CLI, Pi) should be visually
parallel but distinguishable, since each has a different storage layout and
metadata shape.

## Title

Use a two-line title:

```text
agent-history
Browse, Export, and Measure AI Coding Assistant History
```

Make `agent-history` clearly larger than the subtitle. The subtitle should feel
like an explanatory caption, not an equal-weight headline.

## Visual Style

Use a serious modern engineering-diagram style:

- light background
- precise lane layout
- crisp boxes, arrows, gates, and artifact cards
- muted but distinct colors
- readable technical labels
- sparse text inside each node
- subtle depth only where it improves hierarchy

Suggested color system:

- Claude Code adapter lane: cool blue
- Codex CLI adapter lane: green or teal
- Gemini CLI adapter lane: violet
- Cross-home/transport layer (WSL / Windows / SSH): amber
- Shared services/storage: neutral gray
- Outputs/artifacts: indigo

Avoid:

- humanoid robots
- glowing brains
- magic sparkle AI imagery
- dark neon DevOps style
- generic corporate workflow art
- chat-bubble UI mockups
- dense paragraphs inside boxes
- tiny labels
- decorative icons that do not clarify the process

Text readability matters more than preserving every secondary note. If the
diagram becomes crowded, keep the lane and stage labels accurate and remove
small body text before shrinking type. The final image should remain readable
at typical README or documentation width.

## Process Overview

The diagram should show these major inputs:

- **Claude Code sessions**: JSONL files under `~/.claude/projects/<encoded-path>/`
- **Codex CLI sessions**: JSONL files under `~/.codex/sessions/YYYY/MM/DD/`
- **Gemini CLI sessions**: JSON files under `~/.gemini/tmp/<sha256-hash>/chats/`
- **Pi sessions**: JSONL files under `~/.pi/agent/sessions/<encoded-path>/`
- **Homes**: local, WSL distros, Windows-from-WSL, SSH remotes
- **User workspace**: the current project directory the CLI is invoked from
- **Aliases**: user-defined groups of workspaces across homes/sources
- **Date filters**: `--since`, `--until`

The diagram should show agent-history producing these major outputs:

- **Terminal listings**: `lsw` (workspaces), `lss` (sessions), `lsh` (homes)
- **Markdown exports**: per-workspace or per-session, in `./ai-chats/`
  - export modes: default, `--minimal`, `--flat`, `--split N`
- **Offline HTML exports**: per-session or per-workspace/source bundles
  - export controls: `--format html`, `--html-single`, `--html-level 1..4`
  - self-contained CSS/JavaScript; no backend required
- **Usage metrics**: `stats` summaries with sessions, tokens, tools, and time
- **Metrics SQLite database**: small local db used by `stats`
- **Gemini hash index**: `gemini-index` mapping SHA-256 hashes back to project paths
- **Claude skill**: installed at `~/.claude/skills/agent-history/`, lets Claude
  query history through the same CLI

Accuracy constraints:

- Do not show agent-history acting as a chat client, MCP server, or LLM. It is
  a CLI that reads existing session files and produces artifacts.
- Do not show agent-history writing back into `~/.claude/projects/`,
  `~/.codex/sessions/`, or `~/.gemini/tmp/`. The only exception is the install
  step setting `cleanupPeriodDays` in `~/.claude/settings.json` and creating the
  Claude skill folder.
- Do not show a vector database, embedding model, or semantic search. Search is
  string/path matching with optional date filters.
- Do not collapse the three agents into a single generic "AI Sessions" box;
  each has a distinct on-disk format and naming scheme that the diagram should
  reflect.
- Do not depict workspace aliases as a database join engine. Aliases are a
  small user-managed grouping config.

## Agent Adapter Lanes

Show three parallel adapter lanes feeding a shared workspace/session model.

### Claude Code Adapter

1. **Discover Workspaces**
   - scan `~/.claude/projects/`
   - workspace name = encoded path with dashes
2. **Enumerate Sessions**
   - `<uuid>.jsonl` main conversations
   - `agent-<id>.jsonl` Task subagent sessions
3. **Parse JSONL**
   - per-message tokens, tools, timestamps

### Codex CLI Adapter

1. **Discover Sessions**
   - scan `~/.codex/sessions/YYYY/MM/DD/`
2. **Extract Workspace**
   - workspace inferred from `cwd` in session metadata
3. **Parse JSONL**
   - per-turn tokens, tools, timestamps

### Gemini CLI Adapter

1. **Resolve Hash -> Path**
   - workspace dir is `~/.gemini/tmp/<sha256-of-project-path>/`
   - maintain a hash -> path index (`gemini-index`)
2. **Enumerate Sessions**
   - `chats/session-<id>.json` (full JSON, not JSONL)
3. **Parse JSON**
   - per-message tokens, tools, timestamps, reasoning where present

Make clear that all three adapters feed the same downstream
workspace/session/metric abstractions; the per-agent quirks live only in the
adapter stage.

## Cross-Home Transport Layer

Show a transport layer that lets every adapter run not just locally but across
"homes":

- **Local**: current host filesystem
- **WSL**: enumerated WSL distros, accessed via Linux paths or UNC
  (`\\wsl$\<distro>\home\...`)
- **Windows from WSL**: `/mnt/c/Users/<user>/...`
- **SSH Remotes**: `-r user@host`, accessed over SSH using stdlib subprocess

Switches that control scope:

- `--this`: current workspace only (default for many commands)
- `--aw`: all workspaces in scope
- `--ah`: all homes
- `-r <host>` / `--wsl` / `--windows` / `--local`: target a specific home

Show that adapters operate uniformly on local and remote files; the transport
layer hides path translation and SSH plumbing.

`[missing]` markers should be shown as a small annotation: when a workspace is
renamed or moved, agent-history surfaces the closest match rather than failing.

## Shared Workspace / Session Model

Show a single shared model after the adapter stage that all commands consume:

- **Workspace**: `(home, source, workspace path)`
- **Session**: file under a workspace, with timestamp, message count, tokens,
  tool calls, and duration
- **Alias**: user-defined name grouping multiple workspaces across
  homes/sources

This shared model is what `lsw`, `lss`, `export`, and `stats` operate on. It
should sit visually between the adapter lanes and the output cards.

## Commands And Outputs

Show the top-level commands as gates between the shared model and the outputs:

- **`lsh`** -> list homes and manage SSH remotes
- **`lsw`** -> list workspaces
- **`lss`** -> list sessions
- **`export`** -> markdown bundle in `./ai-chats/`
  (modes: default / `--minimal` / `--flat` / `--split N`)
- **`alias`** -> create / apply workspace aliases
- **`stats`** -> usage metrics (sessions, tokens, tools, time, daily breakdown)
- **`gemini-index`** -> manage Gemini hash -> path index
- **`reset`** -> reset stored data (db, settings, aliases)
- **`install`** -> install CLI + Claude skill, set retention

Output cards on the right side:

- `Terminal Listings: lsw / lss / lsh`
- `Markdown Exports: ./ai-chats/`
- `Usage Stats: tokens / tools / time`
- `Metrics SQLite DB`
- `Gemini Hash Index`
- `Claude Skill: ~/.claude/skills/agent-history/`

## Shared Services And Storage

Show these as a support layer below the main lanes, not as the main workflow.

Required storage/service blocks:

- **Metrics DB**
  - small local SQLite database
  - feeds `stats` and cross-home rollups
  - reusable acceleration state
  - support layer, not source repository content

- **Aliases Config**
  - user-defined groups of workspaces across homes/sources
  - small JSON/CFG file managed by `alias` command

- **Gemini Hash Index**
  - SHA-256 -> project path map
  - kept up to date by `gemini-index`
  - lets Gemini workspaces be displayed and filtered by readable path

- **Claude Settings Update**
  - `install` ensures `cleanupPeriodDays = 99999` in `~/.claude/settings.json`
  - preserves other keys
  - backs up malformed JSON before rewriting

- **Claude Skill Folder**
  - `~/.claude/skills/agent-history/` (CLI + `SKILL.md`)
  - lets Claude Code itself search history via the same CLI

Storage boundary accuracy:

- Agent session files (`~/.claude/projects/`, `~/.codex/sessions/`,
  `~/.gemini/tmp/`, `~/.pi/agent/sessions/`) are read-only inputs from
  agent-history's perspective.
- The metrics DB, aliases config, and Gemini hash index are agent-history's
  own data, used to accelerate and group queries.
- Markdown and HTML exports under `./ai-chats/` are generated outputs in the user's
  current project, not authoritative session storage.
- agent-history has no vector store, no embedding service, and no LLM backend.

## Review And Gate Semantics

Show this tool as observation and export, not transformation of agent state.

Required accuracy points:

- agent-history never edits or deletes upstream agent session files.
- The only writes outside the user's project directory are: the install step
  (skill folder + retention setting), the metrics DB under the user's home,
  and the aliases / Gemini-index config.
- Cross-home queries fan out by default in a scoped way (current workspace);
  `--aw` and `--ah` are explicit broadening switches.
- `[missing]` is a soft fallback for renamed/moved workspaces, not an error.

Use labels such as:

- `read-only sessions`
- `path matching, not semantic`
- `--this / --aw / --ah scope`
- `[missing] = closest match`
- `stdlib only`
- `single Python file`

Avoid saying:

- "records conversations"
- "replays sessions"
- "chat UI"
- "vector store"
- "semantic search"
- "MCP server"
- "rewrites agent data"

## Recommended Diagram Skeleton

Represent the main diagram like this, but do not output it as text:

```text
Agent Sessions across Homes (Local / WSL / Windows / SSH)
        |                |                |
        v                v                v
   Claude Adapter   Codex Adapter   Gemini Adapter
        |                |                |
        +--------+-------+--------+-------+
                 v
        Shared Workspace / Session Model
                 |
        +--------+--------+--------+--------+
        v        v        v        v        v
       lsw      lss     export   stats   alias
        |        |        |        |        |
        v        v        v        v        v
   Terminal  Terminal  ./ai-chats  Stats  Aliases
                                 + DB

   Shared layer: Metrics DB, Aliases, Gemini Hash Index,
                 Claude Skill, Settings Update
```

The final image should use real visual boxes, lanes, arrows, artifacts, and
storage blocks rather than rendering this ASCII sketch.

If stage numbers are shown, use them only within a single adapter lane (Parse,
Enumerate, Extract). Do not continue numbering across the three adapter lanes
or into the shared model; that makes the diagram harder to read.

## Short Labels To Prefer

Use short labels where possible:

- Claude Code Sessions
- Codex CLI Sessions
- Gemini CLI Sessions
- Local / WSL / Windows / SSH
- Encoded Path
- Date Folders
- Hash -> Path
- Adapter
- Workspace
- Session
- Alias
- Metrics DB
- Gemini Hash Index
- Claude Skill
- Settings Update
- `lsw`
- `lss`
- `lsh`
- `export`
- `stats`
- `alias`
- `gemini-index`
- `install`
- `--this` / `--aw` / `--ah`
- `--minimal` / `--flat` / `--split N`
- `./ai-chats/`
- `[missing]`

Do not use these labels:

- Vector Store
- Embeddings
- Semantic Search
- MCP Server
- Chat UI
- Conversation Recorder
- Transcript Database (for upstream agent data)

## Final Output Requirements

The output must be:

- a single high-resolution image
- landscape orientation, preferably 16:9
- readable at typical README/documentation width
- suitable for a technical README, architecture page, or project announcement
- visually polished but information-dense
- accurate to the current agent-history process on the master/main branch

The output must not be:

- Mermaid
- SVG or HTML code
- ASCII art
- a textual flowchart
- a set of unrelated panels
- a generic AI workflow graphic
