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
    collect.add_argument(
        "--break-lock",
        action="store_true",
        help="Remove each source's lock in the archive first; only when no run holds it",
    )

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
    """Collect each source in turn. A source that fails does not stop the others.

    A source whose lock another run holds is skipped, as the design asks. Any other
    failure, including an unexpected exception, is reported and makes the exit code 1
    once every source has been tried.
    """
    from agent_history.archive import collect as collect_module

    config, names = _load(args)
    _destination(args, config)  # an invalid destination fails before any source runs
    results: list[dict[str, Any]] = []
    failed = errors = False
    for name in names:
        try:
            summary = collect_module.collect_source(
                config,
                name,
                state_dir=Path(args.state_dir).expanduser() if args.state_dir else None,
                force=args.force,
                dry_run=args.dry_run,
                # As written, so --destination keeps its own state and lock.
                destination=args.destination or config.destination,
                break_lock=args.break_lock,
            )
        except collect_module.CollectLockedError as exc:
            sys.stderr.write(f"{name}: {exc}\n")
            summary = collect_module.RunSummary("", name, skipped_reason="locked")
        except (ArchiveError, OSError) as exc:
            failed = True
            results.append(_source_failure(name, str(exc)))
            continue
        except Exception as exc:  # a defect for one source must not stop the others
            failed = True
            results.append(_source_failure(name, f"{type(exc).__name__}: {exc}"))
            continue
        errors = errors or bool(summary.errors)
        results.append(_summary_dict(summary))
        if not args.json:
            _print_collect(summary)
    if args.json:
        _print_json(results)
    if failed:
        return EXIT_FAILED
    return EXIT_PROBLEMS if errors else EXIT_OK


def _source_failure(name: str, message: str) -> dict[str, Any]:
    sys.stderr.write(f"Error: {name}: {message}\n")
    return {"source": name, "error": message}


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
    """Verify each source in turn. A source that cannot be verified, for example because
    one of its manifests is damaged, is reported with its error, and the next one runs."""
    config, names = _load(args)
    destination = _destination(args, config)
    results = [_verify_one(destination, name, args.sample) for name in names]
    if args.json:
        _print_json(results)
    else:
        for result in results:
            _print_verify(result)
    return EXIT_OK if all(result["ok"] for result in results) else EXIT_PROBLEMS


def _verify_one(destination, name: str, sample: int | None) -> dict[str, Any]:
    from agent_history.archive.verify import verify_source

    try:
        report = verify_source(destination, name, sample=sample)
    except (ArchiveError, OSError) as exc:
        return {"source": name, "ok": False, "error": str(exc)}
    except Exception as exc:  # a defect for one source must not stop the others
        return {"source": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"source": name, "ok": report.ok, **vars(report)}


def _print_verify(result: dict[str, Any]) -> None:
    name = result["source"]
    if "error" in result:
        print(f"{name}: error: {result['error']}")
        return
    print(f"{name}: checked {result['checked']}, {'ok' if result['ok'] else 'PROBLEMS'}")
    for label in ("mismatched", "missing", "unlisted", "errors", "pending"):
        for path in result[label]:
            print(f"  {label}: {path}")


def _catalog(args: argparse.Namespace) -> int:
    from agent_history.archive.catalog import open_store, sync_catalog

    if args.action == "status":
        return _catalog_status(args)
    store = open_store(_catalog_spec(args))
    try:
        # The archive's sources, not the configuration's: the archive can also hold
        # another machine's sources and retired ones.
        summary = sync_catalog(
            store,
            _catalog_destination(args),
            args.sources,
            rebuild=args.action == "rebuild",
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


def _catalog_spec(args: argparse.Namespace) -> str:
    from agent_history.storage.config import get_config_dir

    return args.store or f"sqlite:{get_config_dir() / 'archive-catalog.db'}"


def _catalog_status(args: argparse.Namespace) -> int:
    """Print the catalog's counts, opening it read-only so that status changes nothing."""
    from agent_history.archive.catalog import catalog_status, open_store

    store = open_store(_catalog_spec(args), read_only=True)
    try:
        with store.transaction():
            rows = catalog_status(store, args.sources)
    finally:
        store.close()
    if args.json:
        _print_json(rows)
    else:
        _print_status(rows)
    return EXIT_OK


def _catalog_destination(args: argparse.Namespace):
    """``--destination``, or else the configured destination.

    The configuration file is read only when it is needed, so a catalog of an archive
    can be kept on a machine that has no archive configuration.
    """
    from agent_history.archive.config import load_config
    from agent_history.archive.transport import open_destination
    from agent_history.storage.config import get_config_dir

    if args.destination:
        return open_destination(args.destination)
    path = Path(args.config).expanduser() if args.config else get_config_dir() / "archive.json"
    return open_destination(load_config(path).destination)


def _print_status(rows: list[dict[str, Any]]) -> None:
    columns = ("source", "kind", "runs", "files", "gone", "sessions", "last_run_at")
    print("\t".join(column.upper() for column in columns))
    for row in rows:
        print("\t".join(str(row.get(column) or "") for column in columns))


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


_COMMANDS = {"collect": _collect, "verify": _verify, "catalog": _catalog}
