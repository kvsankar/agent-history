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
| **Copilot CLI** | Initial support | JSONL | Separate terminal-agent backend |
| **VS Code Copilot** | Initial support | JSONL | Separate VS Code extension backend |

Copilot support currently covers local, WSL, and Windows filesystem sources.
SSH remote Copilot discovery is not implemented yet.

See [AGENTS.md](../AGENTS.md) for a detailed comparison of how each agent works with this tool.

## Information Architecture

| Topic | Canonical Docs | Owns |
|-------|----------------|------|
| User workflows | [usage.md](user/usage.md), [cookbook.md](user/cookbook.md), [troubleshooting.md](user/troubleshooting.md) | Command lookup, recipes, export/stat workflows, common recovery. |
| Session discovery and access | [workspace-scope-hub.md](design-v2/workspace-scope-hub.md), [cagelens-spec.md](specs/cagelens-spec.md), [scope-resolution-v2.md](design-v2/scope-resolution-v2.md), [docker-e2e.md](testing/docker-e2e.md) | Storage locations, workspace matching, scope resolution, local/remote/Windows/WSL access. |
| Agent formats and normalization | [specs/agents/formats/](specs/agents/formats/), [unified-json-schema.md](specs/schema/unified-json-schema.md), [schema-refresh-2026-06-04.md](analysis/schema-refresh-2026-06-04.md) | Concrete agent formats, message/tool/token fields, unified NDJSON schema, schema drift notes. |
| Architecture and implementation | [DESIGN.md](design/DESIGN.md), [pipeline-architecture.md](design-v2/pipeline-architecture.md), [scope-resolution-v2.md](design-v2/scope-resolution-v2.md), [cagelens-code-map.md](cagelens-code-map.md) | Current architecture, v2 pipeline design, scope model, generated code map. |
| Validation and release readiness | [testing-strategy.md](testing/testing-strategy.md), [docker-e2e.md](testing/docker-e2e.md), [specs/todo.md](specs/todo.md) | Unit/E2E/real-agent validation, fixture strategy, release follow-ups. |
| Research and collaboration | [research/](research/), [analysis/](analysis/), [other/](other/) | Ecosystem research, historical CLI research, collaboration notes, retrospectives. |
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
| [workspace-scope-hub.md](design-v2/workspace-scope-hub.md) | Navigation hub for workspace, home, source, and session-scope docs. |
| [pipeline-architecture.md](design-v2/pipeline-architecture.md) | V2 command pipeline design and implementation mapping. |
| [scope-resolution-v2.md](design-v2/scope-resolution-v2.md) | Scope resolution model for homes, workspaces, sessions, and agents. |
| [code-reuse-mapping.md](design-v2/code-reuse-mapping.md) | Planning map from legacy code to pipeline entities. |
| [cagelens-code-map.md](cagelens-code-map.md) | Generated/supporting code architecture map. |
| [cagelens-process-image.md](cagelens-process-image.md) | Supporting process diagram brief. |

## Analysis

| Document | Purpose |
|----------|---------|
| [cli-command-patterns.md](analysis/cli-command-patterns.md) | CLI patterns research (industry tools analysis). |
| [competitive-analysis.md](analysis/competitive-analysis.md) | Historical market analysis and pre-rename roadmap context. |
| [schema-refresh-2026-06-04.md](analysis/schema-refresh-2026-06-04.md) | Release schema-refresh evidence and parser impact notes. |
| [docs-consolidation-ia-2026-06-05.md](analysis/docs-consolidation-ia-2026-06-05.md) | Dryscope docs IA findings and consolidation plan. |

## Research

| Document | Purpose |
|----------|---------|
| [copilot-local-formats-2026-06-19.md](research/copilot-local-formats-2026-06-19.md) | Copilot CLI and VS Code Copilot local-format findings. |

## Specifications

| Document | Purpose |
|----------|---------|
| [specs/](specs/README.md) | Specifications index. |
| [cagelens-spec.md](specs/cagelens-spec.md) | Main specification: purpose, supported agents, source model, data model, operations. |
| [cli-spec.md](specs/cli-spec.md) | CLI commands, flags, and expected output. |
| [unified-json-schema.md](specs/schema/unified-json-schema.md) | Normalized NDJSON export schema. |
| [todo.md](specs/todo.md) | Open release/spec follow-ups. |

## Testing

| Document | Purpose |
|----------|---------|
| [testing-strategy.md](testing/testing-strategy.md) | Default, Docker, and opt-in real-agent testing strategy. |
| [docker-e2e.md](testing/docker-e2e.md) | Docker E2E testing infrastructure for SSH operations. |

## Other

| Document | Purpose |
|----------|---------|
| [exploration-log.md](other/exploration-log.md) | Exploratory test runs log. |
| [retrospective.md](other/retrospective.md) | Collaboration retrospective. |
| [claude-collaboration-playbook.md](other/claude-collaboration-playbook.md) | Behavioral playbook for Claude collaborations. |
| [context-cli-test-restoration.md](other/context-cli-test-restoration.md) | Context for CLI test restoration work. |
| [docs-governance.md](other/docs-governance.md) | Documentation ownership, metadata, generated output, and promotion rules. |

If you add new docs, update this index so contributors can discover them quickly.
