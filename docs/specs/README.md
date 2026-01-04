# Specifications Index

Technical specifications for `agent-history`.

## Core Specifications

| Document | Description |
|----------|-------------|
| [agent-history-spec.md](agent-history-spec.md) | Main specification: purpose, agents, data model, operations |
| [cli-spec.md](cli-spec.md) | CLI commands, flags, and expected output |

## Agent Session Formats

How each AI coding assistant stores conversation data.

| Document | Agent |
|----------|-------|
| [claude-code-format.md](agents/formats/claude-code-format.md) | Claude Code (Anthropic) |
| [codex-cli-format.md](agents/formats/codex-cli-format.md) | Codex CLI (OpenAI) |
| [gemini-cli-format.md](agents/formats/gemini-cli-format.md) | Gemini CLI (Google) |
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
