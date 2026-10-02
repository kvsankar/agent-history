"""The ``cagelens archive`` commands: collect, verify and catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agent_history.archive.errors import ArchiveError

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_PROBLEMS = 2

DESCRIPTION = "Collect agent sessions into a compressed archive, verify it, and catalog it."
EPILOG = """\
The configuration (default ~/.cagelens/archive.json) names the destination and sources;
see docs/design-v2/archive-library.md.

Examples:
  cagelens archive collect                      collect every source
  cagelens archive collect --source laptop --dry-run
  cagelens archive verify --sample 100
  cagelens archive catalog sync --store postgres:dbname=agent_archive
"""


def build_parser(prog: str = "cagelens archive") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    collect = sub.add_parser("collect", help="Copy new and changed files into the archive")
    _common(collect)
    collect.add_argument("--force", action="store_true", help="Ignore min_interval_hours")
    collect.add_argument("--dry-run", action="store_true", help="List actions; write nothing")
    collect.add_argument("--state-dir", help="Collector state folder")

    verify = sub.add_parser("verify", help="Decompress archived files and check their hashes")
    _common(verify)
    how_many = verify.add_mutually_exclusive_group()
    how_many.add_argument("--all", action="store_true", help="Check every file (default)")
    how_many.add_argument("--sample", type=int, metavar="N", help="Check N random files")

    catalog = sub.add_parser("catalog", help="Update or show the catalog database")
    catalog.add_argument("action", choices=["sync", "rebuild", "status"])
    _common(catalog)
    catalog.add_argument(
        "--store",
        help="sqlite:<path> or postgres:<conninfo> (default: sqlite:~/.cagelens/archive-catalog.db)",
    )
    return parser


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="Archive configuration file")
    parser.add_argument(
        "--source", action="append", dest="sources", metavar="NAME", help="Limit to a source"
    )
    parser.add_argument("--destination", help="Override the configured destination")
    parser.add_argument("--json", action="store_true", help="Print JSON")


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _COMMANDS[args.verb](args)
    except ArchiveError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return EXIT_FAILED


def _load(args: argparse.Namespace):
    from agent_history.archive.config import load_config
    from agent_history.storage.config import get_config_dir

    path = Path(args.config).expanduser() if args.config else get_config_dir() / "archive.json"
    config = load_config(path)
    names = args.sources or [source.name for source in config.sources]
    for name in names:
        config.source(name)  # raises for unknown names
    return config, names


def _destination(args, config):
    from agent_history.archive.transport import open_destination

    return open_destination(args.destination or config.destination)


def _collect(args: argparse.Namespace) -> int:
    from agent_history.archive.collect import collect_source

    config, names = _load(args)
    destination = _destination(args, config)
    summaries = []
    for name in names:
        summary = collect_source(
            config,
            name,
            state_dir=Path(args.state_dir).expanduser() if args.state_dir else None,
            force=args.force,
            dry_run=args.dry_run,
            destination=destination,
        )
        summaries.append(summary)
        if not args.json:
            _print_collect(summary)
    if args.json:
        _print_json([_summary_dict(summary) for summary in summaries])
    return EXIT_PROBLEMS if any(summary.errors for summary in summaries) else EXIT_OK


def _print_collect(summary) -> None:
    if summary.skipped_reason:
        print(f"{summary.source}: skipped ({summary.skipped_reason})")
        return
    if summary.dry_run:
        for entry in summary.entries:
            label = entry.get("action") or entry.get("type")
            print(f"{label} {entry['path']}")
    print(
        f"{summary.source}: {summary.written} written ({summary.versioned} versioned), "
        f"{summary.gone} gone, {summary.errors} errors"
        + (" [dry run]" if summary.dry_run else f" [run {summary.run_id}]")
    )
    for entry in summary.entries:
        if entry.get("type") == "error":
            print(f"  error {entry['path']}: {entry['message']}")


def _summary_dict(summary) -> dict[str, Any]:
    return {
        "source": summary.source,
        "run_id": summary.run_id,
        "written": summary.written,
        "versioned": summary.versioned,
        "gone": summary.gone,
        "errors": summary.errors,
        "skipped_reason": summary.skipped_reason,
        "dry_run": summary.dry_run,
    }


def _verify(args: argparse.Namespace) -> int:
    from agent_history.archive.verify import verify_source

    config, names = _load(args)
    destination = _destination(args, config)
    reports = {name: verify_source(destination, name, sample=args.sample) for name in names}
    if args.json:
        _print_json(
            [{"source": name, "ok": report.ok, **vars(report)} for name, report in reports.items()]
        )
    else:
        for name, report in reports.items():
            print(f"{name}: checked {report.checked}, {'ok' if report.ok else 'PROBLEMS'}")
            for label in ("mismatched", "missing", "unlisted"):
                for path in getattr(report, label):
                    print(f"  {label}: {path}")
    return EXIT_OK if all(report.ok for report in reports.values()) else EXIT_PROBLEMS


def _catalog(args: argparse.Namespace) -> int:
    from agent_history.archive.catalog import catalog_status, open_store, sync_catalog
    from agent_history.storage.config import get_config_dir

    store = open_store(args.store or f"sqlite:{get_config_dir() / 'archive-catalog.db'}")
    try:
        if args.action == "status":
            rows = catalog_status(store)
            if args.json:
                _print_json(rows)
            else:
                _print_status(rows)
            return EXIT_OK
        config, names = _load(args)
        summary = sync_catalog(
            store, _destination(args, config), names, rebuild=args.action == "rebuild"
        )
    finally:
        store.close()
    if args.json:
        _print_json(vars(summary))
    else:
        print(
            f"{summary.sources} sources, {summary.runs} runs ingested, "
            f"{summary.sessions} sessions updated, {len(summary.errors)} errors"
        )
        for error in summary.errors:
            print(f"  error {error}")
    return EXIT_PROBLEMS if summary.errors else EXIT_OK


def _print_status(rows: list[dict[str, Any]]) -> None:
    columns = ("source", "kind", "runs", "files", "gone", "sessions", "last_run_at")
    print("\t".join(column.upper() for column in columns))
    for row in rows:
        print("\t".join(str(row.get(column) or "") for column in columns))


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


_COMMANDS = {"collect": _collect, "verify": _verify, "catalog": _catalog}
