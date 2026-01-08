"""Helpers to translate legacy CLI arguments to the redesigned noun-verb form."""

from __future__ import annotations


def translate_legacy_args(args: list[str]) -> list[str]:  # noqa: C901
    """Map legacy commands/flags to the new CLI surface."""
    if not args:
        return []

    # Replace deprecated --out with the new -o/--output flag
    normalized = ["-o" if arg == "--out" else arg for arg in args]

    # Separate global prefix flags (e.g., --agent) from the command noun
    prefix: list[str] = []
    i = 0
    opts_with_value = {"--agent"}
    while i < len(normalized):
        tok = normalized[i]
        if not tok.startswith("-"):
            break
        prefix.append(tok)
        if tok in opts_with_value and i + 1 < len(normalized):
            i += 1
            prefix.append(normalized[i])
        i += 1

    if i >= len(normalized):
        return prefix

    cmd = normalized[i]
    rest = normalized[i + 1 :]

    agent_overridden = any(tok == "--agent" for tok in prefix)

    if cmd == "export":
        mapped = ["session", "export", *rest]
    elif cmd == "stats":
        mapped = ["session", "stats", *rest]
    elif cmd == "lss":
        mapped = ["session", *rest]
        if not agent_overridden:
            mapped = ["--agent", "claude", *mapped]
    elif cmd == "lsw":
        mapped = ["ws", *rest]
        if not agent_overridden:
            mapped = ["--agent", "claude", *mapped]
    elif cmd == "lsh":
        mapped = ["lsh", *rest]
    else:
        mapped = [cmd, *rest]

    return prefix + mapped
