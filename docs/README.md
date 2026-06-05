# Documentation Index

<!-- doc-meta
doc_role: overview
audience: contributor
lifecycle: current
content_type: index
surface: public
canonicality: index
-->

Canonical map for the documentation under `docs/`. This index follows the
seven-topic IA from [docs-consolidation-ia-2026-06-05.md](analysis/docs-consolidation-ia-2026-06-05.md).

## Agent Support Status

| Agent | Status | Format | Notes |
|-------|--------|--------|-------|
| **Claude Code** | ✅ Full support | JSONL | All features implemented and tested |
| **Codex CLI** | ✅ Full support | JSONL / JSONL.ZST | All features implemented and tested |
| **Gemini CLI** | ✅ Full support | JSONL / legacy JSON | All features implemented and tested |
| **Pi** | ✅ Full support | JSONL | All features implemented and tested |

See [AGENTS.md](../AGENTS.md) for a detailed comparison of how each agent works with this tool.

## Information Architecture

| Topic | Canonical Docs | Owns |
|-------|----------------|------|
| User workflows | [usage.md](user/usage.md), [cookbook.md](user/cookbook.md), [troubleshooting.md](user/troubleshooting.md) | Command lookup, recipes, export/stat workflows, common recovery. |
| Session discovery and access | [agent-history-spec.md](specs/agent-history-spec.md), [scope-resolution-v2.md](design-v2/scope-resolution-v2.md), [docker-e2e.md](testing/docker-e2e.md) | Storage locations, workspace matching, scope resolution, local/remote/Windows/WSL access. |
| Agent formats and normalization | [specs/agents/formats/](specs/agents/formats/), [unified-json-schema.md](specs/schema/unified-json-schema.md), [schema-refresh-2026-06-04.md](analysis/schema-refresh-2026-06-04.md) | Concrete agent formats, message/tool/token fields, unified NDJSON schema, schema drift notes. |
| Architecture and implementation | [DESIGN.md](design/DESIGN.md), [pipeline-architecture.md](design-v2/pipeline-architecture.md), [scope-resolution-v2.md](design-v2/scope-resolution-v2.md), [agent-history-code-map.md](agent-history-code-map.md) | Current architecture, v2 pipeline design, scope model, generated code map. |
| Validation and release readiness | [testing-strategy.md](testing/testing-strategy.md), [docker-e2e.md](testing/docker-e2e.md), [specs/todo.md](specs/todo.md) | Unit/E2E/real-agent validation, fixture strategy, release follow-ups. |
| Research and collaboration | [analysis/](analysis/), [other/](other/) | Ecosystem research, CLI research, collaboration notes, retrospectives. |
| Navigation and indexes | [docs/README.md](README.md), [specs/README.md](specs/README.md) | Entry points and doc discovery. |

## User Documentation

| Document | Purpose |
|----------|---------|
| [usage.md](user/usage.md) | Command-by-command reference with flags, arguments, and examples. |
| [cookbook.md](user/cookbook.md) | Practical recipes for projects, backups, exports, multi-environment workflows, and reporting. |
| [troubleshooting.md](user/troubleshooting.md) | Common issues, error messages, and environment fixes. |

## Design

| Document | Purpose |
|----------|---------|
| [DESIGN.md](design/DESIGN.md) | Current architecture and data flow overview. |
| [pipeline-architecture.md](design-v2/pipeline-architecture.md) | V2 command pipeline design and implementation mapping. |
| [scope-resolution-v2.md](design-v2/scope-resolution-v2.md) | Scope resolution model for homes, workspaces, sessions, and agents. |
| [code-reuse-mapping.md](design-v2/code-reuse-mapping.md) | Planning map from legacy code to pipeline entities. |
| [agent-history-code-map.md](agent-history-code-map.md) | Generated/supporting code architecture map. |
| [agent-history-process-image.md](agent-history-process-image.md) | Supporting process diagram brief. |

## Analysis

| Document | Purpose |
|----------|---------|
| [cli-command-patterns.md](analysis/cli-command-patterns.md) | CLI patterns research (industry tools analysis). |
| [competitive-analysis.md](analysis/competitive-analysis.md) | Market analysis and roadmap. |
| [schema-refresh-2026-06-04.md](analysis/schema-refresh-2026-06-04.md) | Release schema-refresh evidence and parser impact notes. |
| [docs-consolidation-ia-2026-06-05.md](analysis/docs-consolidation-ia-2026-06-05.md) | Dryscope docs IA findings and consolidation plan. |

## Specifications

| Document | Purpose |
|----------|---------|
| [specs/](specs/README.md) | Specifications index. |
| [agent-history-spec.md](specs/agent-history-spec.md) | Main specification: purpose, supported agents, source model, data model, operations. |
| [cli-spec.md](specs/cli-spec.md) | CLI commands, flags, and expected output. |
| [unified-json-schema.md](specs/schema/unified-json-schema.md) | Normalized NDJSON export schema. |
| [todo.md](specs/todo.md) | Open release/spec follow-ups. |

## Testing

| Document | Purpose |
|----------|---------|
| [testing-strategy.md](testing/testing-strategy.md) | Default, Docker, and opt-in real-agent testing strategy. |
| [docker-e2e.md](testing/docker-e2e.md) | Docker E2E testing infrastructure for SSH operations. |

## Reviews

Review docs are supporting or historical unless promoted into specs, tests, or
architecture docs.

| Document | Purpose |
|----------|---------|
| [reviews/](reviews/README.md) | Review index with current, superseded, closed, and historical status. |

## Other

| Document | Purpose |
|----------|---------|
| [exploration-log.md](other/exploration-log.md) | Exploratory test runs log. |
| [retrospective.md](other/retrospective.md) | Collaboration retrospective. |
| [claude-collaboration-playbook.md](other/claude-collaboration-playbook.md) | Behavioral playbook for Claude collaborations. |
| [context-cli-test-restoration.md](other/context-cli-test-restoration.md) | Context for CLI test restoration work. |

If you add new docs, update this index so contributors can discover them quickly.
