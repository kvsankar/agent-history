"""Cross-platform test runner with Windows defaults."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _has_basetemp(args: list[str]) -> bool:
    return any(arg.startswith("--basetemp") for arg in args)


def _sets_cacheprovider_plugin(args: list[str]) -> bool:
    for index, arg in enumerate(args):
        if arg == "-p" and index + 1 < len(args):
            if "cacheprovider" in args[index + 1]:
                return True
        elif arg.startswith("-p") and "cacheprovider" in arg[2:]:
            return True
    return False


def _is_windows() -> bool:
    return sys.platform == "win32"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run pytest with platform-friendly defaults.",
        add_help=True,
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Keep pytest cacheprovider on Windows (default: disabled).",
    )
    parser.add_argument(
        "--tmp-root",
        default=None,
        help="Override temp root for --basetemp (default: <repo>/.tmp).",
    )
    args, extra = parser.parse_known_args()

    repo_root = Path(__file__).resolve().parent.parent
    tmp_root = Path(args.tmp_root) if args.tmp_root else repo_root / ".tmp"

    if _is_windows():
        tmp_root.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("TEMP", str(tmp_root))
        os.environ.setdefault("TMP", str(tmp_root))
        os.environ.setdefault("TMPDIR", str(tmp_root))

    pytest_args = list(extra)
    if _is_windows() and not args.cache and not _sets_cacheprovider_plugin(pytest_args):
        pytest_args.extend(["-p", "no:cacheprovider"])

    if not _has_basetemp(pytest_args):
        pytest_args.extend(["--basetemp", str(tmp_root / f"pytest-{os.getpid()}")])

    cmd = [sys.executable, "-m", "pytest", *pytest_args]
    return subprocess.call(cmd, cwd=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
