"""Index manifest generation for session export.

This module provides functions to generate index.md manifest files
summarizing all exported sessions.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def generate_index_manifest(
    output_dir: Path,
    sources_info: Dict[str, int],
    quiet: bool,
) -> None:
    """Generate index.md manifest file summarizing all exported sessions.

    This function scans the output directory for workspace subdirectories
    and generates an index.md file with:
    - Generation timestamp
    - Total workspaces and sessions counts
    - Sources section listing sessions per home
    - Workspaces section with headings for each workspace

    Args:
        output_dir: Base output directory containing workspace subdirs.
        sources_info: Mapping of home identifier to session count.
        quiet: If True, suppress output.
    """
    workspaces = scan_workspace_directories(output_dir)

    lines = [
        "# Claude Conversation Export Index",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total Workspaces:** {len(workspaces)}",
        f"**Total Sessions:** {sum(ws['total'] for ws in workspaces.values())}",
        "",
        "## Sources",
        "",
    ]

    # Add sources section - format home names nicely
    for home, count in sorted(sources_info.items()):
        source_label = format_source_label(home)
        lines.append(f"- **{source_label}**: {count} sessions")

    lines.extend(["", "## Workspaces", ""])

    for workspace_name in sorted(workspaces.keys()):
        ws_info = workspaces[workspace_name]
        lines.append(f"### {workspace_name} ({ws_info['total']} sessions)")
        lines.append("")
        lines.extend(format_workspace_sources(ws_info["sources"]))
        lines.append("")

    index_path = output_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")
    if not quiet:
        print(f"\n[Index] Generated: {index_path}")


def scan_workspace_directories(output_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Scan workspace directories and group sessions by source.

    Args:
        output_dir: Base output directory containing workspace subdirs.

    Returns:
        Dictionary mapping workspace name to info dict with 'total' and 'sources'.
    """
    workspaces: Dict[str, Dict[str, Any]] = {}
    for item in output_dir.iterdir():
        if not item.is_dir():
            continue

        sessions = list(item.glob("*.md"))
        sources = {"local": 0, "wsl": 0, "windows": 0, "remote": 0}
        for session_file in sessions:
            sources[classify_session_source(session_file.name)] += 1

        workspaces[item.name] = {"total": len(sessions), "sources": sources}
    return workspaces


def classify_session_source(filename: str) -> str:
    """Classify session source based on filename prefix.

    Args:
        filename: Session filename (e.g., "wsl_Ubuntu_session.md").

    Returns:
        Source category: "local", "wsl", "windows", or "remote".
    """
    if filename.startswith("wsl_"):
        return "wsl"
    if filename.startswith("windows_"):
        return "windows"
    if filename.startswith("remote_"):
        return "remote"
    return "local"


def format_source_label(home: str) -> str:
    """Format home identifier as a human-readable label.

    Args:
        home: Home identifier (e.g., "local", "wsl:Ubuntu").

    Returns:
        Human-readable label (e.g., "Local", "WSL (Ubuntu)").
    """
    if home == "local":
        return "Local"
    if home.startswith("wsl:"):
        distro = home[4:]
        return f"WSL ({distro})"
    if home.startswith("windows:"):
        user = home[8:]
        return f"Windows ({user})"
    if home.startswith("remote:"):
        host = home[7:]
        return f"Remote ({host})"
    return home


def format_workspace_sources(sources: Dict[str, int]) -> List[str]:
    """Format workspace sources as markdown lines.

    Args:
        sources: Mapping of source category to session count.

    Returns:
        List of markdown lines describing non-zero sources.
    """
    lines = []
    for source, label in [
        ("local", "Local"),
        ("wsl", "WSL"),
        ("windows", "Windows"),
        ("remote", "Remote"),
    ]:
        if sources.get(source, 0) > 0:
            lines.append(f"- **{label}:** {sources[source]} sessions")
    return lines
