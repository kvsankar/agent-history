"""List and parse Windows sessions with cagelens running on Windows.

From WSL, the Windows drive is reached through /mnt/c, where every file
access is a round trip to Windows; listing a Windows home that way takes
minutes. Instead WSL starts cagelens on Windows, which lists its own
sessions and parses the files that changed, and writes one JSON lines file.
WSL then reads that one file and stores the rows under the Windows home.

Each line describes one session file::

    {"file": "C:\\\\...\\\\s.jsonl", "agent": "claude", "workspace": "C:\\\\work",
     "mtime": 1790000000.0, "record": {...} or null}

``record`` is the parsed rows (as from metrics._extract_file_stats) for a
file that changed since the mtime WSL already stored, and null otherwise.

The Windows side runs ``python -m agent_history.storage.windows_native
export --known KNOWN.json --out OUT.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

_WINDOWS_DRIVE = re.compile(r"^([A-Za-z]):(?:[\\/](.*))?$")
_WSL_DRIVE = re.compile(r"^/mnt/([a-z])(?:/(.*))?$")
# Stored and Windows mtimes of one file can differ in the last digits.
MTIME_TOLERANCE_SECONDS = 0.01


def to_wsl_path(value: str) -> str:
    """C:\\a\\b -> /mnt/c/a/b; anything that is not a drive path is unchanged."""
    match = _WINDOWS_DRIVE.match(value or "")
    if not match:
        return value
    rest = (match.group(2) or "").replace("\\", "/").strip("/")
    drive = f"/mnt/{match.group(1).lower()}"
    return f"{drive}/{rest}" if rest else drive


def to_windows_path(value: str) -> str:
    """/mnt/c/a/b -> C:\\a\\b; anything else is unchanged."""
    match = _WSL_DRIVE.match(value or "")
    if not match:
        return value
    rest = (match.group(2) or "").replace("/", "\\")
    return f"{match.group(1).upper()}:\\{rest}"


# ---------------------------------------------------------------------------
# Windows side
# ---------------------------------------------------------------------------


def export_scope(
    scope: Iterable[Any], known: dict[str, float], out: Path, jobs: int | None = None
) -> None:
    """Write one line per session file; parse files newer than ``known``."""
    from agent_history.storage import metrics

    rows: dict[str, dict[str, Any]] = {}
    todo: list[tuple[str, str, str | None, str]] = []
    for record in scope:
        for session in record.sessions:
            file_path = session.get("file")
            if not file_path or str(file_path) in rows:
                continue
            file_path = str(file_path)
            agent = session.get("agent") or "claude"
            try:
                mtime = Path(file_path).stat().st_mtime
            except OSError:
                continue
            rows[file_path] = {
                "file": file_path,
                "agent": agent,
                "workspace": record.workspace,
                "mtime": mtime,
                "record": None,
            }
            if known.get(file_path, -1.0) + MTIME_TOLERANCE_SECONDS < mtime:
                todo.append((file_path, "local", record.workspace, agent))

    jobs = jobs or metrics.default_sync_jobs()
    if jobs <= 1 or len(todo) < metrics.PARALLEL_SYNC_MIN_FILES:
        results = (metrics._extract_or_error(item) for item in todo)
    else:
        results = metrics._parallel_extract(todo, jobs)
    for _home, parsed in results:
        if parsed is not None:
            rows[parsed["file_path"]]["record"] = parsed

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        for row in rows.values():
            handle.write(json.dumps(row, default=str) + "\n")


def local_scope() -> list[Any]:
    """All sessions of this machine's own home, grouped by workspace.

    This lists through the inventory directly rather than the scope
    resolver, which on native Windows drops Codex sessions.
    """
    from agent_history.adapters.inventory import InventoryProvider
    from agent_history.scope.context import build_resolution_context
    from agent_history.scope.types import ConcreteRecord

    by_workspace: dict[str, list[dict[str, Any]]] = {}
    for session in InventoryProvider(build_resolution_context()).list_sessions("local"):
        if not session.get("file"):
            continue
        workspace = str(session.get("workspace_readable") or session.get("workspace") or "")
        by_workspace.setdefault(workspace, []).append(
            {"file": str(session["file"]), "agent": session.get("agent") or "claude"}
        )
    return [
        ConcreteRecord(home="local", workspace=workspace, sessions=sessions)
        for workspace, sessions in by_workspace.items()
    ]


def _export_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="windows_native export")
    parser.add_argument("--known", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--jobs", type=int, default=None)
    args = parser.parse_args(argv)
    known = json.loads(Path(args.known).read_text(encoding="utf-8"))
    export_scope(local_scope(), known, Path(args.out), jobs=args.jobs)
    return 0


# ---------------------------------------------------------------------------
# WSL side
# ---------------------------------------------------------------------------


def known_mtimes(conn: sqlite3.Connection, home: str) -> dict[str, float]:
    """Stored mtimes of current rows for a Windows home, keyed by Windows path."""
    from agent_history.storage.metrics import STATS_FORMAT_VERSION

    rows = conn.execute(
        "SELECT file_path, file_mtime FROM sessions WHERE home = ? AND stats_format = ?",
        (home, STATS_FORMAT_VERSION),
    ).fetchall()
    return {to_windows_path(row[0]): float(row[1] or 0) for row in rows}


def interop_env(environ: dict[str, str], run_dir: Path = Path("/run/WSL")) -> dict[str, str]:
    """Return an environment that lets WSL start Windows programs.

    A shell started over SSH has no WSL_INTEROP, so starting a Windows
    program fails; the newest socket in /run/WSL is the live one.
    """
    env = dict(environ)
    if env.get("WSL_INTEROP"):
        return env
    try:
        sockets = sorted(run_dir.glob("*_interop"), key=lambda path: path.stat().st_mtime)
    except OSError:
        sockets = []
    if sockets:
        env["WSL_INTEROP"] = str(sockets[-1])
    return env


def run_export(
    command: list[str],
    known: dict[str, float],
    work_dir: Path,
    to_windows: Callable[[str], str] = to_windows_path,
) -> list[dict[str, Any]]:
    """Run the Windows export with ``command`` and return its lines.

    ``work_dir`` must be on the Windows drive (e.g. under /mnt/c) so both
    sides can read and write the exchange files.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    known_file = work_dir / "known.json"
    out_file = work_dir / "export.jsonl"
    known_file.write_text(json.dumps(known), encoding="utf-8")
    if out_file.exists():
        out_file.unlink()
    result = subprocess.run(
        [
            *command,
            "--known",
            to_windows(str(known_file)),
            "--out",
            to_windows(str(out_file)),
        ],
        env=interop_env(dict(os.environ)),
        capture_output=True,
        text=True,
        check=False,
    )
    (work_dir / "export.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        tail = " | ".join((result.stderr or result.stdout).strip().splitlines()[-3:])
        raise RuntimeError(f"Windows export exited with {result.returncode}: {tail}")
    return [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line]


def build_scope(
    lines: Iterable[dict[str, Any]], home: str
) -> tuple[list[Any], dict[str, dict[str, Any] | None]]:
    """Turn export lines into scope records and parsed rows keyed by WSL path."""
    from agent_history.scope.types import ConcreteRecord

    by_workspace: dict[str, list[dict[str, Any]]] = {}
    prepared: dict[str, dict[str, Any] | None] = {}
    for line in lines:
        file_path = to_wsl_path(line["file"])
        workspace = to_wsl_path(line.get("workspace") or "")
        by_workspace.setdefault(workspace, []).append(
            {"file": file_path, "agent": line.get("agent") or "claude"}
        )
        record = line.get("record")
        if record is not None:
            record = dict(record)
            record["file_path"] = file_path
            record["workspace"] = to_wsl_path(record.get("workspace") or workspace)
        prepared[file_path] = record
    scope = [
        ConcreteRecord(home=home, workspace=workspace, sessions=sessions)
        for workspace, sessions in by_workspace.items()
    ]
    return scope, prepared


def read_export(path: Path, home: str) -> tuple[list[Any], dict[str, dict[str, Any] | None]]:
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return build_scope(lines, home)


def windows_command(settings: dict[str, Any]) -> list[str]:
    """Build the command that runs the export with Windows' Python.

    ``settings`` is config.json's "windows_native" block: "python" is the
    Windows python.exe as WSL sees it (/mnt/c/...), and "code" the folder
    holding this cagelens code as Windows sees it (e.g. \\\\wsl.localhost\\...),
    put first on Windows' import path so both sides run the same code.
    """
    code = settings.get("code") or ""
    bootstrap = (
        "import sys; "
        + (f"sys.path.insert(0, {code!r}); " if code else "")
        + "from agent_history.storage.windows_native import main; "
        + "sys.exit(main(sys.argv[1:]))"
    )
    return [settings["python"], "-c", bootstrap, "export"]


def prepare_windows_homes(
    homes: list[str], settings: dict[str, Any], db_path: Path | None = None, force: bool = False
) -> tuple[list[Any], dict[str, dict[str, Any] | None]]:
    """Run the Windows export for each Windows home and return scope and rows.

    Raises OSError or subprocess.CalledProcessError when Windows cannot be
    reached, so the caller can fall back to reading /mnt/c.
    """
    from agent_history.storage.metrics import init_metrics_db
    from agent_history.utils import progress

    scope: list[Any] = []
    prepared: dict[str, dict[str, Any] | None] = {}
    for home in homes:
        conn = init_metrics_db(db_path)
        try:
            known = {} if force else known_mtimes(conn, home)
        finally:
            conn.close()
        progress.set_phase("listing and parsing on Windows", home)
        lines = run_export(windows_command(settings), known, Path(settings["exchange_dir"]))
        progress.add("windows_files_listed", len(lines))
        home_scope, home_prepared = build_scope(lines, home)
        scope.extend(home_scope)
        prepared.update(home_prepared)
    return scope, prepared


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "export":
        sys.stderr.write("usage: python -m agent_history.storage.windows_native export ...\n")
        return 2
    return _export_command(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
