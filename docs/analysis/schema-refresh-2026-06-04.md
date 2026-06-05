# Coding Agent Schema Refresh - 2026-06-04

<!-- doc-meta
doc_role: research
audience: maintainer
lifecycle: current
content_type: decision
surface: internal
canonicality: supporting
-->

This refresh checks the persisted session formats used by supported coding
agents before release. The goal is to separate verified upstream behavior from
older empirical notes and to patch parser gaps that would cause missing or
misclassified sessions.

## Summary

| Agent | Drift Risk | Release Impact |
|-------|------------|----------------|
| Claude Code | Medium | JSONL remains opaque and evolving; parser should be tolerant and preserve structured blocks. |
| Codex CLI | Medium | Current upstream uses `CODEX_HOME`, may compress rollouts, and has expanded event variants. |
| Gemini CLI | High | Current persistence is JSONL append records; legacy single JSON remains possible. |
| Pi | Medium | Current format is versioned tree JSONL; docs and unified schema must include Pi consistently. |

## Sources

- Claude Code sessions: <https://code.claude.com/docs/en/sessions>
- Claude Agent SDK session storage: <https://code.claude.com/docs/en/agent-sdk/session-storage>
- Claude Agent SDK Python message shapes: <https://code.claude.com/docs/en/agent-sdk/python>
- Claude cost tracking: <https://code.claude.com/docs/en/agent-sdk/cost-tracking>
- Claude schema stability request: <https://github.com/anthropics/claude-code/issues/53516>
- Codex CLI docs: <https://developers.openai.com/codex/cli/>
- Codex source: <https://github.com/openai/codex>
- Gemini CLI session docs: <https://geminicli.com/docs/cli/session-management/>
- Gemini CLI commands: <https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/commands.md>
- Gemini chat recording types: <https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/chatRecordingTypes.ts>
- Gemini chat recording service: <https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/chatRecordingService.ts>
- Gemini storage/project registry: <https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/config/storage.ts>
- Pi sessions: <https://pi.dev/docs/latest/sessions>
- Pi session format: <https://pi.dev/docs/latest/session-format>
- Pi source: <https://github.com/earendil-works/pi>

## Claude Code

Verified behavior:

- Main transcripts are JSONL under `~/.claude/projects/<project>/<session-id>.jsonl`.
- `CLAUDE_CONFIG_DIR` can move the base config directory.
- Agent SDK storage treats records as opaque JSON-safe entries; subagents can be represented with a `subpath`.
- Content blocks include text, thinking, tool use, tool result, image, and document blocks.
- Official docs do not provide a stable raw JSONL schema.

Observed drift:

- Top-level records can include `progress`, `queue-operation`, `last-prompt`,
  `file-history-snapshot`, `attachment`, `ai-title`, `permission-mode`,
  `worktree-state`, `system`, and `summary`, not only user/assistant.
- Compaction can use `system.subtype == "compact_boundary"` followed by a user
  record with `isCompactSummary: true`.
- Product-level branching can create separate forked sessions, so same-file
  `parentUuid` branching is only one fork signal.
- Assistant usage can contain more fields than input/output/cache totals.

Implementation action in this round:

- Preserve Claude raw `message` objects in parsed messages so unified NDJSON can
  emit structured `tool_calls` instead of only formatted Markdown content.

## Codex CLI

Verified behavior:

- Upstream storage root is `CODEX_HOME`, defaulting to `~/.codex`; rollouts live
  under `sessions/YYYY/MM/DD/`.
- Rollout files can be plain `.jsonl` or compressed `.jsonl.zst`.
- Top-level rollout item types include `session_meta`, `turn_context`,
  `response_item`, `event_msg`, and `compacted`.
- `session_meta.instructions` has drifted toward `base_instructions` and turn
  context fields.
- Response variants now include local shell calls, tool search, web search,
  image generation, compaction-related items, and unknown/other variants.

Implementation action in this round:

- Keep `CODEX_SESSIONS_DIR` as the direct sessions-dir compatibility override.
- Add upstream `CODEX_HOME` support.
- Discover `.jsonl.zst` rollouts and read them when the optional `zstandard`
  package is available.

## Gemini CLI

Verified behavior:

- Current canonical persistence is append-only JSONL under
  `~/.gemini/tmp/<projectIdentifier>/chats/`.
- Legacy `session-*.json` files are still relevant and can be migrated/read.
- The project directory component is no longer reliably a SHA-256 hash; current
  Gemini uses project registry identifiers and may migrate old hash dirs.
- JSONL records can include metadata, message records, `$set` snapshots, and
  `$rewindTo` records.
- Subagent sessions can be nested under `chats/<parentSessionId>/<agentId>.jsonl`.
- Content is a Gemini `PartListUnion`, not just strings.
- `GEMINI_CLI_HOME` moves the `.gemini` home.

Implementation action in this round:

- Read both legacy JSON and current JSONL Gemini sessions.
- Handle `$set.messages`, metadata `$set`, and `$rewindTo`.
- Extract text from function-call and function-response content parts.
- Discover top-level JSONL sessions and nested subagent JSONL sessions.
- Add `GEMINI_CLI_HOME` support while retaining `GEMINI_SESSIONS_DIR`.

## Pi

Verified behavior:

- Current sessions are versioned JSONL under
  `~/.pi/agent/sessions/--<path>--/<timestamp>_<uuid>.jsonl`.
- The first record is a `session` header with `version`, `id`, `timestamp`, and
  `cwd`.
- Entries form a tree with `id`/`parentId`.
- Version 3 renamed `hookMessage` to `custom`; loader migrations are expected.
- Entry types include `message`, `model_change`, `thinking_level_change`,
  `compaction`, `branch_summary`, `custom`, `custom_message`, `label`, and
  `session_info`.
- Official override is `PI_CODING_AGENT_SESSION_DIR`; `PI_SESSIONS_DIR` is an
  cagelens compatibility/test override.

Implementation action in this round:

- Bring docs/schema references in line with the already-registered Pi backend.

## Remaining Release Risks

- Claude Code raw JSONL is intentionally undocumented and should remain
  tolerant/lossy only where unavoidable.
- Codex `.jsonl.zst` reading depends on optional `zstandard`; without it, files
  are discovered but cannot be parsed.
- Gemini project identifiers need stronger path resolution using upstream
  `projects.json`; current behavior falls back to hash/identifier display.
- Feature docs for compaction, clearing, interruptions, and rejections describe
  research/proposed enrichment more than current unified NDJSON output.

## Post-Release Schema Follow-Up

The current unified NDJSON schema remains message-oriented. It now carries the
main normalized fields needed by current commands (`model`, `tokens`,
`tool_calls`, `raw_role`, and `tool_result`), but it does not fully model each
agent's concrete event stream.

The canonical tracker for that next schema round is
[specs/todo.md](../specs/todo.md#unified-event-envelope--lossless-schema).
Keep the durable schema contract in
[unified-json-schema.md](../specs/schema/unified-json-schema.md).

## Real-Session Validation Outcome

The canonical validation checklist and non-interactive session creation notes
now live in
[specs/todo.md](../specs/todo.md#real-agent-session-generation--validation).
The release validation command sequence lives in
[testing-strategy.md](../testing/testing-strategy.md#real-agent-validation-harness).

Validation findings from this refresh:

- `scripts/real_agent_validation.py` implements the opt-in harness and dry-run
  mode. It creates per-agent temp homes/workspaces, launches only when
  `AGENT_HISTORY_REAL_AGENT_TESTS=1`, validates list/export/stats, and can write
  sanitized fixture candidates with `--sanitized-output-dir`.
- Local OAuth-backed validation on 2026-06-05 passed for Claude Code, Codex CLI,
  Gemini CLI, and Pi with `--copy-auth-from-default`; only auth files were
  copied into isolated temp homes, not default sessions/projects/settings. Pi
  used `openai-codex/gpt-5.5` when the copied auth file contained an
  `openai-codex` OAuth entry.
- The sanitized real-session fixtures live under `tests/fixtures/real_sessions/`
  and are parsed by `tests/unit/test_real_session_fixtures.py`.
- Installed Gemini CLI 0.38.2 produced a legacy-style `session-*.json` file for
  this OAuth prompt-mode run, so the parser and fixtures continue to treat both
  `.json` and `.jsonl` as active compatibility requirements.
- Gemini `GEMINI_CLI_HOME` resolution was corrected to the current upstream
  layout: `$GEMINI_CLI_HOME/.gemini/tmp`, with compatibility for callers that
  point `GEMINI_CLI_HOME` directly at a `.gemini` directory.
- Docker synthetic data now generates current Codex `rollout-*.jsonl`, current
  Gemini `session-*.jsonl`, one legacy Gemini `session-*.json`, and Pi JSONL
  sessions so remote E2E exercises all supported local agent backends.
