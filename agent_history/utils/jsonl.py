"""Fast line reading for transcript files.

Text-mode iteration asks the operating system for small pieces of a file at a
time. On network-style mounts such as WSL's /mnt/c each request is a round
trip, which made reading Windows transcripts several times slower than the
disk allowed. Reading in large binary blocks and decoding each line gives the
same lines with far fewer requests.
"""

from pathlib import Path
from typing import Iterator, Union

# Bytes requested from the file at a time.
READ_BUFFER_BYTES = 16 * 1024 * 1024


def iter_jsonl_lines(path: Union[str, Path]) -> Iterator[str]:
    """Yield a file's lines as text, like ``open(path, encoding="utf-8-sig")``.

    A UTF-8 byte-order mark at the start is dropped, and invalid UTF-8 raises
    UnicodeDecodeError, as in text mode. Line endings are kept as read.
    """
    with open(path, "rb", buffering=READ_BUFFER_BYTES) as handle:
        first = True
        for raw in handle:
            if first:
                first = False
                yield raw.decode("utf-8-sig")
            else:
                yield raw.decode("utf-8")
