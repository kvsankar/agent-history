# Documentation Index

Quick links to the reference material under `docs/`.

## Agent Support Status

| Agent | Status | Format | Notes |
|-------|--------|--------|-------|
| **Claude Code** | ✅ Full support | JSONL | All features implemented and tested |
| **Codex CLI** | ✅ Full support | JSONL | All features implemented and tested |
| **Gemini CLI** | ✅ Full support | JSON | All features implemented and tested |
| **Pi** | ✅ Full support | JSONL | All features implemented and tested |

See [AGENTS.md](../AGENTS.md) for a detailed comparison of how each agent works with this tool.

---

## User Documentation

| Document | Purpose |
|----------|---------|
| [usage.md](user/usage.md) | Command-by-command reference with flags, arguments, and examples. |
| [cookbook.md](user/cookbook.md) | Practical recipes for projects, backups, exports, multi-environment workflows, and reporting. |
| [troubleshooting.md](user/troubleshooting.md) | Common issues, error messages, and environment fixes. |
| [agent-history-process-image.md](agent-history-process-image.md) | Process diagram brief for how sessions are collected, normalized, and exported. |

---

## Design

| Document | Purpose |
|----------|---------|
| [DESIGN.md](design/DESIGN.md) | Architecture and data flow overview for the CLI. |

---

## Analysis

| Document | Purpose |
|----------|---------|
| [cli-command-patterns.md](analysis/cli-command-patterns.md) | CLI patterns research (industry tools analysis). |
| [competitive-analysis.md](analysis/competitive-analysis.md) | Market analysis and roadmap. |

---

## Specifications

| Document | Purpose |
|----------|---------|
| [specs/](specs/README.md) | Specifications index |
| [agent-history-spec.md](specs/agent-history-spec.md) | **Main specification** - purpose, agents, data model, operations |

### CLI Design

| Document | Purpose |
|----------|---------|
| [cli-spec.md](specs/cli-spec.md) | CLI specification with commands, flags, and expected output. |

### Agent Formats

| Document | Purpose |
|----------|---------|
| [claude-code-format.md](specs/agents/formats/claude-code-format.md) | Claude Code JSONL session file structure. |
| [codex-cli-format.md](specs/agents/formats/codex-cli-format.md) | Codex CLI JSONL session file structure. |
| [gemini-cli-format.md](specs/agents/formats/gemini-cli-format.md) | Gemini CLI JSON session format. |
| [pi-format.md](specs/agents/formats/pi-format.md) | Pi JSONL session file structure. |
| [chatgpt-web-format.md](specs/agents/formats/chatgpt-web-format.md) | ChatGPT web session format. |
| [gemini-web-format.md](specs/agents/formats/gemini-web-format.md) | Gemini web session format. |

### Agent Features

| Document | Purpose |
|----------|---------|
| [compaction.md](specs/agents/features/compaction.md) | Context compaction feature analysis. |
| [clearing.md](specs/agents/features/clearing.md) | Session clearing feature analysis. |
| [interruptions.md](specs/agents/features/interruptions.md) | Interruption handling analysis. |
| [rejections.md](specs/agents/features/rejections.md) | Rejection handling analysis. |

### Export Schema

| Document | Purpose |
|----------|---------|
| [unified-json-schema.md](specs/schema/unified-json-schema.md) | Normalized NDJSON export format spec. |

---

## Testing

| Document | Purpose |
|----------|---------|
| [docker-e2e.md](testing/docker-e2e.md) | Docker E2E testing infrastructure for SSH operations. |

---

## Reviews

| Document | Purpose |
|----------|---------|
| [assessment_report.md](reviews/assessment_report.md) | Codebase assessment report. |
| [codex_review.md](reviews/codex_review.md) | Codex integration review. |
| [COVERAGE_REPORT.md](reviews/COVERAGE_REPORT.md) | Test coverage report. |
| [RHODES_REVIEW.md](reviews/RHODES_REVIEW.md) | Rhodes coding principles review. |
| [FORMAT_REFACTORING_REVIEW.md](reviews/FORMAT_REFACTORING_REVIEW.md) | Format refactoring review. |
| [REFACTORING_REVIEW.md](reviews/REFACTORING_REVIEW.md) | General refactoring review. |
| [done/](reviews/done/) | Completed code reviews (8 files). |

---

## Other

| Document | Purpose |
|----------|---------|
| [exploration-log.md](other/exploration-log.md) | Exploratory test runs log. |
| [retrospective.md](other/retrospective.md) | Collaboration retrospective. |
| [claude-collaboration-playbook.md](other/claude-collaboration-playbook.md) | Behavioral playbook for Claude collaborations. |
| [context-cli-test-restoration.md](other/context-cli-test-restoration.md) | Context for CLI test restoration work. |

---

If you add new docs, update this index so contributors can discover them quickly.
