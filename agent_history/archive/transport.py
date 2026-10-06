"""Archive destinations: a local folder (which may be a network mount) or SSH."""

from __future__ import annotations

import os
import secrets
import shutil
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator, Tuple

from agent_history.archive.errors import ArchiveError


def _check_rel(rel: str) -> str:
    parts = rel.split("/")
    if rel.startswith("/") or any(part in ("", ".", "..") for part in parts):
        raise ArchiveError(f"Unsafe archive path: {rel!r}")
    return rel


def fsync_file(path: Path) -> None:
    """Flush a file's content to disk, so a rename that follows cannot expose an empty file.

    On Windows the file is opened in binary mode: in text mode, the C runtime removes a
    final Ctrl-Z byte (0x1A) from a file opened for reading and writing, and a compressed
    copy or manifest ends in that byte about once in 256.
    """
    fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_dir(path: Path) -> None:
    """Flush a folder's entries (renames and new names) to disk.

    Windows cannot open a folder for flushing, and some network filesystems refuse it;
    there the rename is as durable as the filesystem makes it.
    """
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _check_discardable(rel: str) -> str:
    """Only a source's ``incoming`` folder, which holds no committed file, may be removed."""
    parts = _check_rel(rel).split("/")
    if len(parts) < 3 or parts[0] != "sources" or parts[2] != "incoming":
        raise ArchiveError(f"Refusing to remove {rel!r}: only incoming folders can be removed")
    return rel


LOCK_FOLDER = "LOCK"
LOCK_OWNER = "owner.json"
# Tries to create the owner file when a run releasing the lock removes its folder meanwhile.
_LOCK_ATTEMPTS = 5


def _check_lock(rel: str) -> str:
    """Only a source's lock folder, ``sources/<source>/LOCK``, is created or removed as one."""
    parts = _check_rel(rel).split("/")
    if len(parts) != 3 or parts[0] != "sources" or parts[2] != LOCK_FOLDER:
        raise ArchiveError(f"Refusing to use {rel!r} as a lock: only sources/<source>/LOCK is one")
    return rel


# A rewritten file's archived copy to keep as a version: (current path, version path,
# incoming path of the new copy). The move is due while the new copy is still incoming.
Keep = Tuple[str, str, str]
# A new copy to move into place: (incoming path, current path).
Put = Tuple[str, str]


class Destination:
    """Operations the collector, verifier and catalog need from an archive root."""

    description: str

    def read_bytes(self, rel: str) -> bytes | None:
        raise NotImplementedError

    def write_bytes(self, rel: str, data: bytes) -> None:
        raise NotImplementedError

    def list_files(self, rel_dir: str) -> list[str]:
        """Paths of all files under ``rel_dir``, relative to it, "/"-separated."""
        raise NotImplementedError

    def list_dirs(self, rel_dir: str) -> list[str]:
        """Names of the folders directly in ``rel_dir``, sorted; [] when it does not exist.

        Unlike list_files, this does not walk what the folders hold.
        """
        raise NotImplementedError

    def exists(self, rel: str) -> bool:
        raise NotImplementedError

    def missing(self, rels: list[str]) -> list[str]:
        """The paths among ``rels`` that do not exist."""
        return [rel for rel in rels if not self.exists(rel)]

    def sizes(self, rels: list[str]) -> dict[str, int]:
        """The size in bytes of each file among ``rels``; paths that are no file are left out."""
        raise NotImplementedError

    def move(self, src: str, dst: str) -> bool:
        """Rename within the archive; False when ``src`` does not exist."""
        raise NotImplementedError

    def put_tree(self, staging: Path) -> None:
        """Copy every file under ``staging`` to the same relative path, keeping times.

        A failed transfer can leave a partial file at its target path, so callers send
        only to paths that no manifest lists (a run's incoming folder).
        """
        raise NotImplementedError

    def place(self, keeps: list[Keep], puts: list[Put]) -> None:
        """Move kept copies to their version paths, then move new copies into place.

        Every step can be repeated: a keep is skipped once its version path exists or its
        incoming copy has gone, and a put once its incoming copy has gone. So a run that
        stopped part way is finished by calling this again with the same lists.
        """
        raise NotImplementedError

    def discard_tree(self, rel: str) -> None:
        """Remove a source's incoming folder and everything in it, if it exists."""
        raise NotImplementedError

    def create_lock(self, rel: str, owner: bytes) -> bool:
        """Take the lock ``rel``: create its owner.json, holding ``owner``, exclusively.

        The owner file is the lock; the folder around it only holds it. The owner is
        written to a temporary file in the folder, flushed, and hard-linked to
        owner.json. Creating a link fails when the name exists, so of two runs that try
        at the same time only one succeeds, and owner.json appears with its whole
        content: a run killed part way leaves at most the temporary file, which is no
        lock. Where the filesystem has no hard links and owner.json is absent, owner.json
        is created with an exclusive create (O_EXCL) and written through the same
        descriptor instead. False when the owner file exists already.
        """
        raise NotImplementedError

    def remove_lock(self, rel: str) -> None:
        """Remove a lock folder and everything in it, if it exists.

        The owner file is removed last, so the lock is held until nothing else is left.
        The folder itself is removed when it is then empty; a folder without an owner
        file is no lock.
        """
        raise NotImplementedError

    @contextmanager
    def open_binary(self, rel: str) -> Iterator[IO[bytes]]:
        raise NotImplementedError
        yield  # pragma: no cover


class LocalDestination(Destination):
    def __init__(self, root: Path):
        self.root = Path(root)
        self.description = str(self.root)

    def _path(self, rel: str) -> Path:
        return self.root / _check_rel(rel)

    def read_bytes(self, rel: str) -> bytes | None:
        try:
            return self._path(rel).read_bytes()
        except FileNotFoundError:
            return None

    def write_bytes(self, rel: str, data: bytes) -> None:
        path = self._path(rel)
        folders = _make_parent(path)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        fsync_file(tmp)
        os.replace(tmp, path)
        _sync_dirs(folders)

    def list_files(self, rel_dir: str) -> list[str]:
        base = self._path(rel_dir)
        if not base.is_dir():
            return []
        found = []
        for dirpath, _dirnames, filenames in os.walk(base):
            for filename in filenames:
                found.append((Path(dirpath) / filename).relative_to(base).as_posix())
        return sorted(found)

    def list_dirs(self, rel_dir: str) -> list[str]:
        base = self._path(rel_dir)
        if not base.is_dir():
            return []
        with os.scandir(base) as entries:  # like list_files, symbolic links are not followed
            return sorted(entry.name for entry in entries if entry.is_dir(follow_symlinks=False))

    def exists(self, rel: str) -> bool:
        return self._path(rel).exists()

    def sizes(self, rels: list[str]) -> dict[str, int]:
        found = {}
        for rel in rels:
            path = self._path(rel)
            if path.is_file():
                found[rel] = path.stat().st_size
        return found

    def move(self, src: str, dst: str) -> bool:
        source = self._path(src)
        if not source.exists():
            return False
        target = self._path(dst)
        folders = _make_parent(target) | {source.parent}
        os.replace(source, target)
        _sync_dirs(folders)
        return True

    def put_tree(self, staging: Path) -> None:
        folders = set()
        for dirpath, _dirnames, filenames in os.walk(staging):
            for filename in sorted(filenames):
                src = Path(dirpath) / filename
                rel = src.relative_to(staging).as_posix()
                target = self._path(rel)
                folders |= _make_parent(target)
                tmp = target.with_name(target.name + ".part")
                shutil.copy2(src, tmp)
                fsync_file(tmp)
                os.replace(tmp, target)
        _sync_dirs(folders)

    def place(self, keeps: list[Keep], puts: list[Put]) -> None:
        folders: set[Path] = set()
        try:
            for current, version, incoming in keeps:
                if self.exists(version) or not self.exists(incoming):
                    continue
                if not self.exists(current):
                    raise ArchiveError(
                        f"The archived copy {current} to keep as {version} is missing"
                    )
                self._rename(current, version, folders)
            for incoming, current in puts:
                if self.exists(incoming):
                    self._rename(incoming, current, folders)
        finally:
            _sync_dirs(folders)

    def _rename(self, src: str, dst: str, folders: set[Path]) -> None:
        source, target = self._path(src), self._path(dst)
        folders |= _make_parent(target) | {source.parent}
        os.replace(source, target)

    def discard_tree(self, rel: str) -> None:
        path = self._path(_check_discardable(rel))
        if path.exists():
            shutil.rmtree(path)

    def create_lock(self, rel: str, owner: bytes) -> bool:
        target = self._path(_check_lock(rel)) / LOCK_OWNER
        for _ in range(_LOCK_ATTEMPTS):
            folders = _make_parent(target)
            tmp = target.with_name(f"{LOCK_OWNER}.{secrets.token_hex(8)}.tmp")
            try:
                taken = _link_owner(tmp, target, owner)
            except FileNotFoundError:
                continue  # a run releasing the lock removed the folder just now
            finally:
                tmp.unlink(missing_ok=True)
            if taken:
                _sync_dirs(folders)
            return taken
        raise ArchiveError(f"Could not create {rel}/{LOCK_OWNER}: its folder kept disappearing")

    def remove_lock(self, rel: str) -> None:
        path = self._path(_check_lock(rel))
        if not path.is_dir():
            return
        owner = path / LOCK_OWNER
        with os.scandir(path) as entries:
            others = [Path(entry.path) for entry in entries if entry.name != LOCK_OWNER]
        for item in [*others, owner]:
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink(missing_ok=True)
        try:
            path.rmdir()
        except OSError:
            pass  # something appeared meanwhile; without an owner file it is no lock
        fsync_dir(path.parent)

    @contextmanager
    def open_binary(self, rel: str) -> Iterator[IO[bytes]]:
        with self._path(rel).open("rb") as handle:
            yield handle


def _link_owner(tmp: Path, target: Path, owner: bytes) -> bool:
    """Write the owner to ``tmp``, flush it, and hard-link it to ``target``.

    A hard link fails when ``target`` exists, and ``target`` appears with its whole
    content, so it never exists empty, even when the run is killed part way. Where the
    filesystem has no hard links and ``target`` is absent, ``target`` is created with
    O_EXCL instead. False when another run holds the lock.
    """
    _create_exclusive(tmp, owner)
    try:
        os.link(tmp, target)
    except FileExistsError:
        return False
    except FileNotFoundError:
        raise  # the folder was removed meanwhile; the caller tries again
    except OSError:  # no hard links on this filesystem
        if target.exists():
            return False
        return _create_exclusive(target, owner)
    return True


def _create_exclusive(path: Path, data: bytes) -> bool:
    """Create ``path`` holding ``data``, flushed; False when it exists.

    The file is removed if the write fails, so it never stays empty after an error.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError:
        return False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return True


def _make_parent(path: Path) -> set[Path]:
    """Create ``path``'s folder; return the folders whose entries change and need a flush.

    Those are the folder itself, and the parent of every folder that had to be created.
    """
    folder = path.parent
    created = []
    while not folder.exists():
        created.append(folder)
        folder = folder.parent
    path.parent.mkdir(parents=True, exist_ok=True)
    return {path.parent, *(new.parent for new in created)}


def _sync_dirs(folders: set[Path]) -> None:
    """Flush folders, deepest first, so a new folder is on disk before its parent's entry."""
    for folder in sorted(folders, key=lambda path: len(path.parts), reverse=True):
        fsync_dir(folder)


def fold_case(path: str) -> str:
    """``path`` as a destination that ignores letter case compares it.

    NTFS, SMB shares and default APFS volumes treat names that differ only in case as one
    name, and APFS also ignores Unicode normalization. Case folding folds a little more
    than NTFS does (``ß`` and ``ss``), which only makes the collector more careful.
    """
    return unicodedata.normalize("NFC", path).casefold()


def ignores_case(destination: Destination) -> bool:
    """True when ``destination`` treats names that differ only in letter case as one.

    Tested on ARCHIVE.json, which an archive holds from its first run on, so an archive
    without one counts as telling case apart. Only reads.
    """
    return destination.exists("ARCHIVE.json") and destination.exists("archive.json")


def open_destination(destination: str) -> Destination:
    """Open a destination given as a local path or ``ssh://host/path``."""
    if destination.startswith("ssh://"):
        from agent_history.archive.ssh_destination import SshDestination

        return SshDestination.from_url(destination)
    return LocalDestination(Path(destination).expanduser())
