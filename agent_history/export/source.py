"""Source file copying for session export.

This module provides functions to copy raw source files alongside exports.
"""

import shutil
from pathlib import Path


def copy_source_file(
    source_file: Path,
    output_dir: Path,
    quiet: bool,
) -> None:
    """Copy raw source file to output directory.

    Args:
        source_file: Source session file (JSONL or JSON).
        output_dir: Destination directory.
        quiet: If True, suppress output.
    """
    dest_file = output_dir / source_file.name
    shutil.copy2(source_file, dest_file)
    if not quiet:
        print(dest_file)
