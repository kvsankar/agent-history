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

## Reference Documents

| Document | Purpose |
|----------|---------|
| [AGENTS.md](../AGENTS.md) | **Comparison of supported coding agents** - storage, features, and behaviors. |
| [usage.md](usage.md) | Command-by-command reference with flags, arguments, and examples. |
| [cookbook.md](cookbook.md) | Practical recipes for aliases, backups, exports, multi-environment workflows, and reporting. |
| [troubleshooting.md](troubleshooting.md) | Common issues, error messages, and environment fixes. |
| [DESIGN.md](DESIGN.md) | Architecture and data flow overview for the CLI. |

## Session Format Specifications

| Document | Purpose |
|----------|---------|
| [claude-format.md](claude-format.md) | Claude Code JSONL session file structure. |
| [codex-format.md](codex-format.md) | Codex CLI JSONL session file structure (verified from source). |
| [gemini-format.md](gemini-format.md) | Gemini CLI JSON session format (verified from source). |
| [pi-format.md](pi-format.md) | Pi JSONL session file structure. |

## Other Resources

| Document | Purpose |
|----------|---------|
| [claude-collaboration-playbook.md](claude-collaboration-playbook.md) | Behavioral playbook for Claude + developer collaborations; ideal for inclusion in `CLAUDE.md`. |

If you add new docs, update this index so contributors can discover them quickly.
