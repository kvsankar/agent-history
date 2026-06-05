# Specifications Index

<!-- doc-meta
doc_role: overview
audience: contributor
lifecycle: current
content_type: index
surface: public
canonicality: index
-->

Technical specifications for `cagelens`.

## Core Specifications

| Document | Description |
|----------|-------------|
| [cagelens-spec.md](cagelens-spec.md) | Main specification: purpose, agents, data model, operations |
| [cli-spec.md](cli-spec.md) | CLI commands, flags, and expected output |
| [todo.md](todo.md) | Release/spec follow-up items that are not yet part of the durable spec |

## Local Agent Session Formats

How each AI coding assistant stores conversation data.

| Document | Agent |
|----------|-------|
| [claude-code-format.md](agents/formats/claude-code-format.md) | Claude Code (Anthropic) |
| [codex-cli-format.md](agents/formats/codex-cli-format.md) | Codex CLI (OpenAI) |
| [gemini-cli-format.md](agents/formats/gemini-cli-format.md) | Gemini CLI (Google) |
| [pi-format.md](agents/formats/pi-format.md) | Pi Coding Agent |

## Web and Import Reference Formats

Claude web sessions are supported. Other web format specs are reference-only
unless an importer explicitly depends on them.

| Document | Format |
|----------|--------|
| [chatgpt-web-format.md](agents/formats/chatgpt-web-format.md) | ChatGPT Web |
| [gemini-web-format.md](agents/formats/gemini-web-format.md) | Gemini Web |

## Agent Feature Analysis

How agents handle specific features.

| Document | Feature |
|----------|---------|
| [compaction.md](agents/features/compaction.md) | Context window compaction |
| [clearing.md](agents/features/clearing.md) | Session clearing |
| [interruptions.md](agents/features/interruptions.md) | Interruption handling |
| [rejections.md](agents/features/rejections.md) | Request rejections |

## Export Schema

| Document | Description |
|----------|-------------|
| [unified-json-schema.md](schema/unified-json-schema.md) | Normalized NDJSON export format |

Keep cross-agent field mapping in the unified schema. Agent format specs should
stay focused on the concrete files each upstream tool writes.

## Refresh Notes

| Document | Description |
|----------|-------------|
| [schema-refresh-2026-06-04.md](../analysis/schema-refresh-2026-06-04.md) | Current upstream schema drift review and parser impact |
| [docs-consolidation-ia-2026-06-05.md](../analysis/docs-consolidation-ia-2026-06-05.md) | Documentation IA findings from Dryscope |
