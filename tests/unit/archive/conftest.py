"""Shared fixtures for the archive tests."""

from __future__ import annotations

import os
import stat

import pytest

CTRL_Z = b"\x1a"


@pytest.fixture
def windows_text_mode(monkeypatch):
    """Model the Windows C runtime's text mode on every platform.

    On Windows, ``os.open`` without ``os.O_BINARY`` opens a file in text mode, and the C
    runtime then drops a final Ctrl-Z byte (0x1A) of a file opened for reading and
    writing. A compressed file ends in that byte about once in 256, so code that reopens
    a file that way loses data. Elsewhere the fixture makes ``os.open`` do the same, with
    a stand-in ``os.O_BINARY`` flag that turns it off. On Windows the real runtime does it.
    """
    if os.name == "nt":
        return
    binary = 0x10000000  # not a flag Linux or macOS use
    monkeypatch.setattr(os, "O_BINARY", binary, raising=False)
    real_open = os.open

    def text_mode_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags & ~binary, *args, **kwargs)
        info = os.fstat(fd)
        read_write = flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR) == os.O_RDWR
        if read_write and not flags & binary and stat.S_ISREG(info.st_mode) and info.st_size:
            if os.pread(fd, 1, info.st_size - 1) == CTRL_Z:
                os.ftruncate(fd, info.st_size - 1)
        return fd

    monkeypatch.setattr(os, "open", text_mode_open)
