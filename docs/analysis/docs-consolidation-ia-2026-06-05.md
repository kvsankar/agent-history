# Docs Consolidation IA - 2026-06-05

<!-- doc-meta
doc_role: plan
audience: maintainer
lifecycle: current
content_type: architecture
surface: internal
canonicality: supporting
-->

Generated from a dryscope docs scan of `docs/`.

Raw reports:

- `.dryscope/runs/20260605-124824/report.md`
- `.dryscope/runs/20260605-124824/report.html`
- `.dryscope/runs/20260605-124824/report.json`

Run notes:

- Corpus: 37 documents, 922 sections.
- Embeddings: `all-MiniLM-L6-v2` local embeddings.
- IA backend: Codex CLI with `gpt-5.5`.
- Section similarity: 0 similar section pairs above threshold 0.9.
- IA output: 7 top-level topic groups, 6 facet dimensions, 7 diagnostics, 98 consolidation clusters.
- Doc-pair LLM analysis was skipped by dryscope because the estimated pair-analysis cost exceeded the configured cap.

Post-consolidation rerun:

- Run: `.dryscope/runs/20260605-141322/report.md`
- Commit scanned: `674c5511`
- Corpus: 39 documents, 942 sections.
- Section similarity: 0 similar section pairs above threshold 0.9; 0 section recommendations.
- IA output: 9 top-level topic groups, 6 facet dimensions, 7 diagnostics, 103 consolidation clusters.
- Interpretation: copy-like section duplication remains clean. The IA cluster count rose because the consolidation work temporarily added explicit review/documentation-governance material and made status/index topics visible to Dryscope. Review documents are no longer tracked; keep durable findings promoted into specs, tests, or architecture docs instead.
- Doc-pair LLM analysis was skipped again because the estimated pair-analysis cost exceeded the configured cap.

## Proposed IA

### 1. User Workflows

Canonical docs:

- `docs/user/usage.md` - command reference.
- `docs/user/cookbook.md` - task recipes.
- `docs/user/troubleshooting.md` - recovery and FAQ.

Owns:

- command lookup and examples
- listing sessions/workspaces
- export workflows
- stats workflows
- common errors and reset/recovery

Consolidation notes:

- Keep user export tasks here.
- Do not mix implementation/schema export details into user workflows; link to `specs/schema/unified-json-schema.md`.
- Keep stats commands here, but link to metrics storage internals in architecture/spec docs.

### 2. Session Discovery and Access

Canonical docs:

- `docs/design-v2/scope-resolution-v2.md` - scope architecture and matching model.
- `docs/specs/cagelens-spec.md` - product-level data/source model.
- `docs/testing/docker-e2e.md` - remote/SSH validation.

Owns:

- agent data sources and storage locations
- workspace discovery and matching
- scope resolution
- local, remote, Windows, and WSL access

Consolidation notes:

- Dryscope flagged this as an overloaded branch. Keep discovery, matching, home configuration, and remote/cross-platform access as distinct subtopics with cross-links.
- Move duplicated storage-location explanations toward `cagelens-spec.md` plus agent-format specs, then link from troubleshooting and usage.

### 3. Agent Formats and Normalization

Canonical docs:

- `docs/specs/agents/formats/claude-code-format.md`
- `docs/specs/agents/formats/codex-cli-format.md`
- `docs/specs/agents/formats/gemini-cli-format.md`
- `docs/specs/agents/formats/pi-format.md`
- `docs/specs/schema/unified-json-schema.md`
- `docs/analysis/schema-refresh-2026-06-04.md`

Supporting/secondary:

- `docs/specs/agents/formats/chatgpt-web-format.md`
- `docs/specs/agents/formats/gemini-web-format.md`

Owns:

- concrete agent session formats
- message/tool/token/timestamp records
- special event features
- unified NDJSON schema
- web and third-party import formats

Consolidation notes:

- Dryscope flagged local coding-agent formats and web/export formats as different reader intents. Keep local agent formats separate from web/third-party inputs.
- Keep source-format specs focused on concrete storage. Put cross-agent field mapping in `unified-json-schema.md`.
- Event-feature docs (`clearing`, `compaction`, `interruptions`, `rejections`) should link to the planned unified event envelope rather than duplicating schema rationale.

### 4. Architecture and Implementation

Canonical docs:

- `docs/design/DESIGN.md` - current architecture.
- `docs/design-v2/pipeline-architecture.md` - proposed/current v2 pipeline detail.
- `docs/design-v2/scope-resolution-v2.md` - scope model.

Owns:

- system architecture
- command pipeline and output formatting
- ingestion/parsing/indexing architecture
- configuration and environment overrides
- refactoring/code reuse planning

Consolidation notes:

- Dryscope flagged mixed lifecycle in architecture docs. Mark current, proposed, draft, generated, and review docs explicitly.
- Keep `DESIGN.md` as the current architecture entry point; make v2 docs clearly proposed/current-by-area.
- Keep review outputs out of version control once actionable findings are promoted; keep only durable architecture decisions in design docs.

### 5. Validation, Testing, and Release Readiness

Canonical docs:

- `docs/testing/testing-strategy.md`
- `docs/testing/docker-e2e.md`
- `docs/analysis/schema-refresh-2026-06-04.md`
- `docs/specs/todo.md`

Owns:

- test architecture
- Docker/SSH E2E
- real-session validation
- fixture strategy
- release risks and follow-up work

Consolidation notes:

- Keep ongoing release follow-ups in `specs/todo.md`.
- Keep one dated analysis per major release/schema refresh under `docs/analysis/`.
- Promote durable testing procedures from dated analysis into `testing/testing-strategy.md` after release.

### 6. Research, Planning, and Collaboration

Canonical/supporting docs:

- `docs/analysis/competitive-analysis.md`
- `docs/analysis/cli-command-patterns.md`
- `docs/other/claude-collaboration-playbook.md`
- `docs/other/retrospective.md`
- `docs/other/exploration-log.md`

Owns:

- market and ecosystem research
- CLI design research
- collaboration practices
- historical exploration logs
- retrospectives

Consolidation notes:

- Keep research separate from current specs and user docs.
- Archive historical exploration once its findings are promoted into specs, tests, or todos.

### 7. Navigation and Indexes

Canonical docs:

- `docs/README.md`
- `docs/specs/README.md`

Owns:

- entry points
- doc discovery
- current public doc map

Consolidation notes:

- Dryscope flagged "documentation index" and "overview" as weak top-level topics. Keep this as a small utility branch only.
- Update indexes whenever docs are promoted, archived, or consolidated.

## Facets To Add To Docs

Use lightweight frontmatter or a small metadata table for docs that are easy to confuse.

Recommended facets:

- `doc_role`: `guide`, `reference`, `spec`, `architecture`, `research`, `status`, `plan`, `troubleshooting`, `overview`
- `audience`: `user`, `contributor`, `maintainer`, `operator`, `internal`, `agent`
- `lifecycle`: `current`, `proposed`, `draft`, `historical`
- `content_type`: `workflow`, `api`, `architecture`, `requirements`, `troubleshooting`, `decision`, `benchmark`, `example`
- `surface`: `public`, `internal`, `integration`, `generated`, `extension`, `package`
- `canonicality`: `primary`, `supporting`, `index`, `archive`

Priority docs for facet tagging:

- `docs/design/DESIGN.md`
- `docs/design-v2/*.md`
- `docs/analysis/*.md`
- local ignored review outputs under `docs/reviews/`
- `docs/specs/todo.md`

## High-Signal Consolidation Targets

These are not section-level duplicate copies. They are topic-coverage overlaps where one canonical owner should be chosen and other docs should link to it.

| Topic | Canonical Owner | Supporting Docs To Link/Trim |
|-------|-----------------|-------------------------------|
| Usage statistics | `docs/user/usage.md` for commands; `docs/specs/cagelens-spec.md` or `docs/design/DESIGN.md` for storage | `cookbook.md`, `troubleshooting.md`, `cli-spec.md`, `testing-strategy.md`, `competitive-analysis.md` |
| Message record schema | agent format specs plus `unified-json-schema.md` | feature docs should link instead of restating field-level schema |
| Release follow-up items | `docs/specs/todo.md` | dated analysis/review docs should link here after findings are promoted |
| Conversation export | `docs/user/usage.md` and `docs/user/cookbook.md` for workflows; `unified-json-schema.md` for NDJSON | `cagelens-spec.md`, `cli-spec.md`, local review output after findings are promoted |
| Unified NDJSON schema | `docs/specs/schema/unified-json-schema.md` | `schema-refresh`, `clearing`, `compaction`, `interruptions`, `rejections` |
| Agent storage locations | `docs/specs/cagelens-spec.md` and per-agent format specs | `troubleshooting.md`, dated analysis |
| Scope resolution | `docs/design-v2/scope-resolution-v2.md` | `cagelens-spec.md`, `DESIGN.md`, `code-reuse-mapping.md` |
| Tool call records | per-agent format specs and `unified-json-schema.md` | avoid duplicating tool-call mapping in feature docs |
| Command result formatting | `docs/specs/cli-spec.md` | `pipeline-architecture.md`, `cli-command-patterns.md`, review docs |
| Real-agent validation | `docs/testing/testing-strategy.md` and `docs/specs/todo.md` | `schema-refresh-2026-06-04.md` should stay dated evidence |

## Recommended Folder Cleanup

### Keep As Primary

- `docs/user/`
- `docs/specs/`
- `docs/design/DESIGN.md`
- `docs/testing/`
- `docs/README.md`

### Keep As Design/Planning With Lifecycle Labels

- `docs/design-v2/`
- `docs/analysis/`

### Move Or Mark As Supporting/Archive

- `docs/reviews/` should remain ignored local review output after actionable findings are promoted.
- `docs/other/exploration-log.md` after findings are promoted.
- `docs/other/context-cli-test-restoration.md` once test restoration context is no longer active.
- Generated code maps, image prompts, and rendered schema diagrams should stay
  out of tracked release docs unless they are actively maintained and linked
  from a current documentation owner.

## Suggested Consolidation Order

1. Add doc metadata facets to high-confusion docs.
2. Make `docs/README.md` match the 7-topic IA above.
3. Update `docs/specs/README.md` to separate local agent formats, web/export inputs, event features, and unified schema.
4. Promote release and schema follow-ups into `docs/specs/todo.md`; trim duplicate TODO prose from dated analysis docs.
5. Split export docs by reader intent: user workflow in `user/`, schema contract in `specs/schema/`, pipeline implementation in `design/`.
6. Split stats docs by reader intent: command usage in `user/`, metrics storage in `design/specs`, token source fields in agent-format specs.
7. Archive or demote resolved reviews and historical exploration logs.

## Dryscope Diagnostics

- High: session discovery/scope/workspace/remote access is overloaded. Use separate child topics with cross-links.
- High: conversation export mixes user workflow and technical schema/pipeline concerns. Split by reader intent.
- Medium: stats mixes command use, metrics database, token metadata, work time, and tool usage analysis. Split by reader intent.
- Medium: architecture mixes current design, proposed v2 redesign, generated maps, and draft review findings. Add lifecycle/canonicality facets.
- Medium: agent formats mix local coding-agent formats with web/export ecosystems. Keep separate.
- Low: documentation index/overview is a weak top-level topic. Keep as utility navigation only.
- Low: process diagram requirements are a single-document intent. Keep as supporting architecture artifact.

## Post-Rerun Residual Diagnostics

The 2026-06-05 post-consolidation rerun no longer suggests section-level copy cleanup. It still flags IA-level navigation work:

- High: workspace resolution remains the dominant cross-cutting topic. Treat it as a hub with child links for model, pipeline, cross-environment access, and matching reliability.
- High: current/proposed/historical/draft docs still overlap across CLI behavior, pipeline architecture, scope resolution, and schema support. Lifecycle facets are now present, but indexes should keep exposing them.
- Medium: export still spans workflow, pipeline, schema, and web-import research. Keep reciprocal links between those owners.
- Medium: source-format lookup and normalized field/schema mapping are related but should remain distinct.
- Low: documentation governance appears across indexes, IA plans, and TODOs. It may deserve a small explicit governance section if the docs continue to grow.
