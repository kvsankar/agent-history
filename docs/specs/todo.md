# Specs TODO

<!-- doc-meta
doc_role: status
audience: maintainer
lifecycle: current
content_type: requirements
surface: internal
canonicality: primary
-->

Items that need investigation or clarification before full specification.

## 2.0 Release Readiness

`feature/2.0-exploration` merges to `master` only after these items, in this
order:

- [ ] **Parser check.** Compare each agent's current concrete format with its
      format spec and parser: Claude Code, Codex, Gemini, Copilot (CLI and VS
      Code) and Pi. Inputs: recent real session files, release notes, and the
      source of the open-source agents. Use the real-agent capture harness only
      for gaps.
- [ ] **Code audit.** Functional defects, and design and simplicity, across
      backends, export, core and storage. Findings first; fixes follow.
- [ ] **Unified model.** Enhance the unified model (the NDJSON schema in
      [`schema/unified-json-schema.md`](schema/unified-json-schema.md) and the
      lineage model) so it represents every agent's concrete format without
      loss: shared concepts in common fields, agent-only attributes kept per
      entity, unrecognized records kept raw. This may add turns and events and
      change how sessions and messages are modelled. Existing readers keep
      working, and the schema version records the change. See "Unified Event
      Envelope / Lossless Schema" below.
- [ ] **Per-agent converters.** Convert each agent into the enhanced model,
      Copilot first. Copilot reaches parity with the other agents on every
      command and is added to the lineage model.
- [ ] **Markdown and HTML exports** show the attributes the model keeps.
- [ ] **HTML export.** Clear at every level of detail for every agent, written
      for a general reader, with sub-agents shown through lineage. Finish or
      remove the agent graph (built, turned off) and the timeline index. The
      branches `codex/html-timeline-export` (with its spec,
      `docs/specs/html-timeline-export.md`) and
      `wip/html-agent-graph-ui-playwright` are design references; delete them
      once this work replaces them. Split `agent_history/export/html.py`.
- [ ] Resolve the conflicts between `feature/2.0-exploration` and `master`,
      then merge.

## Pending Investigation

### Windows Drive Access From WSL (virtiofs)

From WSL, the Windows drive is mounted over 9P, where every file check or
open is a round trip to Windows (about 14 ms per `stat` on laptop), so
listing a Windows home from WSL takes about 10 minutes for 3,340 sessions.
Stats sync avoids this by running cagelens on Windows (`windows_native`).

- Evaluate WSL's experimental virtiofs transport for `/mnt/c`
  (`virtiofs=true` under `[wsl2]` in `.wslconfig`; needs the pre-release WSL
  kernel 6.18.26.3 or newer via `wsl.exe --update --pre-release`; laptop
  runs WSL 2.6.3 with kernel 6.6.87.2).
- Measure Windows listing and sync over virtiofs against the Windows-native
  export, and decide whether `windows_native` is still needed.
- Source: https://boxofcables.dev/wsl2-per-device-swiotlb-pools-for-virtiofs-and-virtioproxy

### Archive Library (`agent_history/archive`)

**Status:** Built and reviewed. Higher-layer tools configure and run it; this
section covers only the library.

The design is [`../design-v2/archive-library.md`](../design-v2/archive-library.md).

- [ ] Run another independent review of the archive library, limited to its
      purpose: collect, verify and catalog agent sessions. Use synthetic homes.
      Do not run selections over whole real home folders; one can take an hour
      and exhaust memory.
- [ ] Store session titles in the catalog (design section "Session titles",
      not built). First establish where each agent records titles in its
      current format, then add the column test-first.
- [ ] Read an archive as a cagelens home, with transparent `.zst` reading in
      every backend (design section "Reading The Archive With cagelens", not
      built).
- [ ] Remove the backends' imports of `storage.metrics` and `export` (design
      section "Changes To Existing Code", not built).
- [ ] `pyproject.toml` declares Python 3.8, but the package needs 3.10: some
      modules evaluate `str | None` annotations at import. Set
      `requires-python = ">=3.10"` and the matching ruff target.
- [ ] Align the ruff versions: `uv.lock` has 0.15.18 and the pre-commit hook
      pins 0.8.4. They format 26 files differently, so a whole-tree
      `ruff format --check` fails on files nobody changed.
- [ ] Archive homes decode encoded Claude project folder names without a live
      folder to check, so a hyphen in a folder name reads as a path separator.
      Prefer the working directory the sessions record.
- [ ] The workspace inventory counts a Gemini `X.json` chat and its resumed
      `X.jsonl` copy twice. The remote listing does not list Gemini sub-agent
      chats (`chats/<parent>/<id>.jsonl`).
- [ ] Rows for the old flat remote-cache paths stay in `metrics.db` after the
      cache moved to per-path folders; nothing removes them.
- [ ] Stats SQL adds counts with `SUM`, which can still overflow SQLite's
      integers on extreme inputs. Consider `TOTAL` or clamped sums.
- [ ] On a destination that ignores letter case, two live source files whose
      names differ only in case cannot both be archived; the second is
      reported as an error on every run. Decide whether to store it under
      another name.
- [ ] Some catalogued sessions have no working folder (a few hundred Claude
      sessions) or no model (Codex sessions without assistant messages, and
      Copilot in VS Code, which records none). Check whether the readers can
      recover them.

### Real Agent Session Generation / Validation

**Status:** Complete for current release validation

**Why:** Synthetic fixtures and Docker checks validate parsers against known shapes, but
they do not prove current agent CLIs still write those shapes. Schema refresh work needs
an opt-in validation path that creates fresh real sessions in isolated temp homes and
workspaces without touching a user's default cagelens.

**Tracking checklist:**
- [x] Research non-interactive real-session creation for Claude Code:
      prompt mode, storage directory override, auth requirements, and permission flags.
- [x] Research non-interactive real-session creation for Codex CLI:
      `codex exec`, `CODEX_HOME`, sandbox flags, auth requirements, and compressed
      rollout behavior.
- [x] Research non-interactive real-session creation for Gemini CLI:
      prompt invocation, `GEMINI_CLI_HOME`, auth requirements, and JSONL append log
      behavior.
- [x] Research non-interactive real-session creation for Pi:
      prompt/export commands, `PI_SESSIONS_DIR` or `PI_CODING_AGENT_SESSION_DIR`, and
      auth requirements.
- [x] Add an opt-in real-agent capture harness guarded by
      `CAGELENS_REAL_AGENT_TESTS=1`.
- [x] Make the harness create fresh temp homes, fresh workspaces, and fresh project
      settings so it never reads or writes default user session stores.
- [x] Add a sanitizer that removes prompts, paths, environment details, tool outputs,
      and other sensitive raw content before fixtures are committed.
- [x] Refresh checked-in fixtures from sanitized real sessions for Claude Code,
      Codex CLI, Gemini CLI, and Pi.
- [x] Update Docker synthetic session generation to include current Claude, Codex,
      Gemini, and Pi shapes when real CLIs are unavailable.
- [x] Document the release validation command sequence for local, Docker, CI, and
      opt-in real-agent checks.

**Current research notes:**
- Claude Code can be exercised with `claude --bare -p --output-format json`
      plus an explicit `--session-id`. Set `HOME` and `CLAUDE_CONFIG_DIR` to temp
      directories; transcripts are expected under
      `$CLAUDE_CONFIG_DIR/projects/<encoded-workspace>/<session-id>.jsonl`.
      Use `ANTHROPIC_API_KEY` for non-interactive `--bare` runs, and avoid
      `CLAUDE_CODE_SKIP_PROMPT_HISTORY` or `--no-session-persistence` because they
      suppress transcript writes.
- Pi can be exercised with `pi -p`/`pi --print`; `pi --mode json` and
      `pi --mode rpc` are also non-interactive paths. Use a temp
      `PI_CODING_AGENT_DIR` for the normal workspace-encoded layout, or
      `--session-dir` / `PI_CODING_AGENT_SESSION_DIR` for a flat explicit session
      directory. Use `--no-tools` and disable extensions, skills, prompt templates,
      themes, and context files for isolation. Do not pass `--no-session`.
- Codex CLI can be exercised with `codex exec` using temp `HOME` and temp
      `CODEX_HOME`. Use `--cd <temp-workspace>`, `--sandbox read-only`,
      `--ignore-user-config`, `--ignore-rules`, and optionally `--json`. Do not
      pass `--ephemeral`; it suppresses rollout persistence. Fresh files are expected under
      `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl`; validators should also
      accept `.jsonl.zst`.
- Gemini CLI can be exercised with `gemini -p`, `gemini --prompt`, or piped
      stdin. Set `GEMINI_CLI_HOME` to a fake home root, not a `.gemini` directory;
      current sessions are expected under
      `$GEMINI_CLI_HOME/.gemini/tmp/*/chats/session-*.jsonl`, with legacy
      `session-*.json` still accepted. Avoid bare positional prompts and
      `gemini -i` for the harness.

**Implementation notes:**
- `scripts/real_agent_validation.py` now provides the guarded harness, dry-run
      command preview, isolated temp homes/workspaces, list/export/stats
      validation, optional auth-file copying, and optional sanitized fixture
      output.
- Local OAuth-backed validation on 2026-06-05 passed for Claude Code, Codex CLI,
      Gemini CLI, and Pi using isolated temp homes and copied default auth files.
      Pi used the `openai-codex/gpt-5.5` subscription model when the copied auth
      file contained an `openai-codex` entry.
- `tests/fixtures/real_sessions/` contains sanitized real captures for Claude,
      Codex, Gemini, and Pi. `tests/unit/test_real_session_fixtures.py` parses
      them through the production backends.
- Installed Gemini CLI 0.38.2 produced `session-*.json` for the OAuth prompt
      run, so legacy JSON remains covered alongside synthetic JSONL.
- `docs/testing/testing-strategy.md` documents the real-agent validation command
      sequence and keeps it outside default CI.
- `docker/scripts/generate-sessions.sh` now writes current Codex rollouts,
      current Gemini JSONL sessions plus one legacy Gemini JSON session, and Pi
      JSONL sessions. Docker E2E assertions cover Pi list/export paths.

---

### Docs IA Consolidation

**Status:** In progress

**Why:** Dryscope found no high-confidence duplicate sections, but it did find
topic-level overlap across user workflows, session discovery, agent formats,
architecture, validation, research, and navigation. The docs need clearer
canonical owners so future schema/release work does not keep duplicating
storage, export, stats, and scope explanations.

**Tracking checklist:**
- [x] Preserve the Dryscope IA summary as a dated analysis document.
- [x] Keep generated `.dryscope/` report output out of source control.
- [x] Add lightweight doc metadata facets to primary user, spec, format,
      architecture, testing, analysis, and supporting docs.
- [x] Rewrite `docs/README.md` around the seven canonical IA buckets.
- [x] Update `docs/specs/README.md` to separate local agent formats, web/import
      reference formats, feature analysis, unified schema, and refresh notes.
- [x] Promote release/schema follow-up tracking into canonical docs and trim
      duplicated checklist prose from dated schema-refresh analysis.
- [x] Trim duplicated storage-location explanations from user/troubleshooting
      docs once all references point to `cagelens-spec.md` and per-agent
      format specs.
- [x] Trim duplicated export schema explanations from user workflow and CLI docs
      once workflow text links to `schema/unified-json-schema.md`.
- [x] Trim duplicated stats internals from user workflow docs once command usage,
      metrics storage, and token-source fields have clear canonical owners.
- [x] Remove review documents from version control and keep `docs/reviews/`
      ignored for local review output.
- [x] Re-run Dryscope docs scan after consolidation and document the residual
      diagnostics in `docs/analysis/docs-consolidation-ia-2026-06-05.md`.
- [x] Consider adding an explicit documentation governance area if index,
      consolidation-plan, and TODO docs keep growing.
- [x] Consider a dedicated workspace/scope hub page if user, spec, design, and
      troubleshooting links remain hard to navigate after the current indexes.

---

### Package Rename / PyPI Reservation

**Status:** In progress

**Why:** the previous public package name is already taken on PyPI, so the
project needs a PyPI-available distribution name before publishing. Selected
name: `cagelens` (Coding Agent Lens), chosen to describe a tool that parses
coding agent logs, collects statistics, and surfaces insights without implying
that it generates logs.

**Tracking checklist:**
- [x] Re-check PyPI availability for `cagelens` immediately before acting.
- [x] Decide whether only the PyPI distribution changes or whether the CLI
      command, import package, docs, skill name, config paths, and output
      examples also rename.
- [ ] Keep the import package as `agent_history` for this slice and decide
      separately whether to rename it or provide a public `cagelens` import
      package later.
- [ ] Reserve the PyPI name by publishing a legitimate minimal release, not an
      empty placeholder.
- [x] Update package metadata, project URLs, README, docs, and release notes for
      the selected public name.
- [x] Add compatibility/deprecation notes if legacy CLI commands or config paths
      remain supported during migration.
- [ ] Run packaging validation (`uv build`, publish dry-run/Twine check if
      available) before release.

---

### Stats Output Shape / Analytics UI

**Status:** Open

**Why:** `session stats` now returns fast cached metrics, but the default table
output is not actually a table. It is a series of loose text sections. That is
readable for a quick terminal glance, but it may be too informal for a metrics
surface that needs breadth-wise coverage, drilldowns, comparison, and machine
or agent-friendly interpretation.

**Tracking checklist:**
- [ ] Decide whether stats table output should remain section-oriented,
      become one or more real tables, or support both compact dashboard and
      tabular drilldown modes.
- [ ] Define the canonical stats views: summary, agents, homes, workspaces,
      models, tools, days, time, cache freshness, and sync/errors.
- [ ] Decide whether terminal table output should optimize for humans, coding
      agents, or both, and document the output contract.
- [ ] Generalize the stats scope banner into a shared table-output scope banner
      for all scoped commands (`session list`, `ws list`, `export`, resource
      stats), including command-specific counts and compact truncation rules.
- [ ] Evaluate Datasette as an optional analytics UI over `metrics.db`,
      including project-specific metadata YAML, saved canned queries, facets,
      labels, and safe defaults for local-only use.
- [ ] Decide whether Datasette support should be documentation-only,
      a generated `metadata.yml`, a `cagelens datasette` helper command, or a
      separate optional extra.
- [ ] If Datasette is adopted, specify privacy/security defaults: bind address,
      read-only DB access, hidden raw path columns if needed, and no accidental
      publication of personal logs.

---

### Unified Event Envelope / Lossless Schema

**Status:** Part of 2.0 release readiness (see the "Unified model" item above),
covering Copilot as well as the agents listed here.

**Why:** The current unified NDJSON model is good enough for message-level
list/export/stats compatibility, but it is intentionally not a lossless model
of each agent's concrete event stream. Recent schema refresh work made parsers
tolerant of evolved concrete formats, but several concrete records are still
represented only as message content/metadata or ignored when they are not useful
for the current commands.

**Tracking checklist:**
- [ ] Design a first-class `type: "event"` NDJSON record alongside existing
      `header`, `message`, and `session` records.
- [ ] Define common event fields: `event_type`, `agent`, `timestamp`,
      `session_id`, `role` when applicable, normalized event-specific fields,
      and `raw_payload` for forward-compatible unknown data.
- [ ] Map Codex concrete events such as `event_msg`, `turn_context`,
      `token_count`, `task_started`, `task_complete`, `turn_aborted`,
      `compacted`, and non-message `response_item` variants.
- [ ] Map Gemini append-log operations such as metadata records, `$set`,
      `$rewindTo`, function-call/function-response content parts, and nested
      subagent session metadata.
- [ ] Map Pi tree/context events such as `session_info`, `model_change`,
      `thinking_level_change`, `compaction`, `branch_summary`, `custom`,
      `custom_message`, and `label`.
- [ ] Map Claude non-message/session-adjacent records such as
      `queue-operation`, `last-prompt`, `progress`, `system`,
      `compact_boundary`, and summary/attachment/title records where safe.
- [ ] Add event-envelope fixtures and tests using synthetic edge cases plus the
      sanitized real-session fixtures.
- [ ] Update `docs/specs/schema/unified-json-schema.md` with versioning and
      backwards-compatibility guidance for consumers that only read messages.

## First-Class Lineage Model

**Status:** Implemented in the lineage IR; HTML consumption remains
incremental.

**Why:** Main sessions, child agents, branch trees, and extension-provided
delegation all need a common representation before the timeline can place
concurrent work on separate tracks.

**Tracking checklist:**
- [x] Add backend lineage extractors for Claude, Codex, Gemini, and Pi.
- [x] Normalize `kind: main | subagent | branch`.
- [x] Promote Codex child rollouts with `thread_source: "subagent"` and
      `source.subagent.thread_spawn.parent_thread_id`.
- [x] Preserve Codex `event_msg.task_complete` as completion data.
- [x] Join Claude nested `subagents/agent-<task-id>.jsonl` files to parent
      `<task-notification>` records.
- [x] Represent Gemini subagent `toolCalls[]` entries as child-agent spans;
      link nested child JSONL files when present.
- [x] Keep Pi `id` / `parentId` tree links as branch lineage, and detect
      subagents only from extension-provided `subagent` tool result metadata.
- [x] Add `confidence` and `evidence` fields so timeline UI can distinguish
      confirmed lineage from inferred lineage.
- [x] Emit synthetic parent-facing lifecycle events such as
      `subagent.completed` after a child span is joined to parent invocation and
      completion evidence.

---

### Web Sessions (Claude.ai)

**Status:** Implemented

**Current state in implementation:**
- `--web`/`--no-web` control scope resolution
- `--ah` includes web by default
- Sessions are fetched via Claude API and cached to `~/.cagelens/web-cache`

**Action:** Spec updated to reflect web support.

---

### ws list Output Fields

**Status:** Resolved

**Current state:**
- `ws list` outputs HOME, WORKSPACE, SESSIONS, STATUS, MODIFIED

**Action:** Spec updated to match current output.
