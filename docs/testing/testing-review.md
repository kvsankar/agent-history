# Testing Strategy Review

Scope: Reviewed the specs in `docs/specs/` and the testing plans in `docs/testing/` to assess test coverage, risks, and next steps.

## Strengths
- Strong spec traceability: tests are intended to map back to specific spec sections (formats, CLI, unified schema).
- Synthetic, agent-specific fixtures are planned, avoiding reliance on real agent data and enabling deterministic stats checks.
- Environment isolation is designed up front (home overrides, platform markers, Docker SSH layer), reducing risk of touching real user data.
- CLI coverage plan is broad, including export flags, stats grouping, and multi-home/scope combinations.
- Stats validation considers mathematical invariants and time-tracking gaps, not just surface-level output.

## Gaps & Risks
- Critical-path prioritization is missing: the plan is very wide (8 agent tracks) without a minimal set to get green quickly.
- Telemetry-only behaviors (context clearing) are not fully covered: no fixtures/tests around `~/.claude/history.jsonl`, `~/.codex/history.jsonl`, or Gemini `logs.json`, so clear events remain untested.
- Compaction/forks coverage is underspecified: no fixtures for Claude dual-layer compaction (summary.md + compact_boundary), Codex inline compaction, or conversation graph branches; unified export tests could miss these.
- Rejection detection for Claude and absence for Codex/Gemini are noted in specs but not reflected in concrete test cases/fixtures.
- Stats fixtures lack defined golden datasets: expected token/tool/time totals are sketched conceptually but not enumerated, risking flaky or incomplete assertions.
- Spec/impl drift is unaddressed: `docs/specs/todo.md` flags `ws list` output mismatch; tests written to spec will fail against current behavior unless reconciled.
- Web session support is undecided; current plan ignores it, so either the feature should be explicitly out of scope or tests need to be added once scope is resolved.
- Cross-environment and Docker tests are heavy; pass/fail gating, time budget, and skip conditions are not defined, risking long or flaky runs.

## Recommendations
1) Define a minimal v1 test slice: parser + unified-export golden fixtures for each agent (user/assistant, tool_use/result, interruption, rejection, compaction, timestamps) and basic CLI `ws/session list`, `session export`, `session stats` happy paths. Defer combinatorial scope matrices until this slice is green.
2) Add telemetry fixtures for context clearing: small `history.jsonl` / `logs.json` samples that prove we detect clears (Claude/Codex in same sessionId, Gemini new sessionId).
3) Create compaction/branch fixtures:
   - Claude: main + session-memory/summary.md + compact_boundary markers.
   - Codex: `compacted` with `replacement_history`.
   - Forked conversation graph to exercise `graph` export fields.
4) Lock down stats golden data: enumerate exact expected totals (messages, tokens, tools, time gaps, work periods) for 2–3 small mixed-agent sessions; use these in stats tests and invariants.
5) Clarify spec/impl conflicts before writing assertions (e.g., `ws list` columns, web sessions scope). Document chosen behavior in tests to avoid churn.
6) Gate heavy suites: mark Docker/SSH and cross-platform tests with explicit opts, set timeouts, and provide skip messaging to keep default CI fast.
7) Add unified NDJSON export checks for edge content: reasoning formats (`thinking`/`summary`/`thoughts`), compaction, interruptions, synthetic Gemini tool_result splitting, and rejection/user_reason mapping.

Natural next steps: agree on the v1 minimal slice and fixture contents, then implement the telemetry + compaction fixtures so parser/unified-export and stats tests have concrete data.
