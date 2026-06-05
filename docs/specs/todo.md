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

## Pending Investigation

### Real Agent Session Generation / Validation

**Status:** Complete for current release validation

**Why:** Synthetic fixtures and Docker checks validate parsers against known shapes, but
they do not prove current agent CLIs still write those shapes. Schema refresh work needs
an opt-in validation path that creates fresh real sessions in isolated temp homes and
workspaces without touching a user's default agent history.

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
      `AGENT_HISTORY_REAL_AGENT_TESTS=1`.
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
      docs once all references point to `agent-history-spec.md` and per-agent
      format specs.
- [x] Trim duplicated export schema explanations from user workflow and CLI docs
      once workflow text links to `schema/unified-json-schema.md`.
- [x] Trim duplicated stats internals from user workflow docs once command usage,
      metrics storage, and token-source fields have clear canonical owners.
- [x] Remove review documents from version control and keep `docs/reviews/`
      ignored for local review output.
- [x] Re-run Dryscope docs scan after consolidation and document the residual
      diagnostics in `docs/analysis/docs-consolidation-ia-2026-06-05.md`.
- [ ] Consider adding an explicit documentation governance area if index,
      consolidation-plan, and TODO docs keep growing.
- [ ] Consider a dedicated workspace/scope hub page if user, spec, design, and
      troubleshooting links remain hard to navigate after the current indexes.

---

### Unified Event Envelope / Lossless Schema

**Status:** Planned for a post-release v2.1 schema round

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

---

### Web Sessions (Claude.ai)

**Status:** Implemented

**Current state in implementation:**
- `--web`/`--no-web` control scope resolution
- `--ah` includes web by default
- Sessions are fetched via Claude API and cached to `~/.agent-history/web-cache`

**Action:** Spec updated to reflect web support.

---

### ws list Output Fields

**Status:** Resolved

**Current state:**
- `ws list` outputs HOME, WORKSPACE, SESSIONS, STATUS, LAST_MODIFIED

**Action:** Spec updated to match current output.
