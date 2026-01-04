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

    def _alias_mapping(subcmd: str, tail: list[str]) -> list[str]:
        if subcmd == "export":
            return ["project", "config-export", *tail]
        if subcmd == "import":
            return ["project", "config-import", *tail]
        if subcmd == "create":
            return ["project", "add", *tail, "--allow-empty"]
        if subcmd == "add":
            return ["project", "add", *tail]
        if subcmd == "remove":
            return ["project", "remove", *tail]
        if subcmd == "show":
            return ["project", "show", *tail]
        if subcmd == "list":
            return ["project", "list", *tail]
        return ["project", subcmd, *tail]

    if cmd == "export":
        mapped = ["session", "export", *rest]
    elif cmd == "stats":
        mapped = ["session", "stats", *rest]
    elif cmd == "lss":
        mapped = ["session", *rest]
    elif cmd == "lsw":
        mapped = ["ws", *rest]
    elif cmd == "lsh":
        mapped = ["home", *rest]
    elif cmd == "alias":
        if rest:
            mapped = _alias_mapping(rest[0], rest[1:])
        else:
            mapped = ["project", "list"]
    else:
        mapped = [cmd, *rest]

    return prefix + mapped
