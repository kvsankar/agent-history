"""Progress lines for long-running work such as a stats sync.

A background thread writes one line per interval (default one minute) with
the current phase, what it is working on, the counters so far, and the
elapsed time. Lines go to stderr unless quiet, and are appended to a log
file, which is rotated when it grows past a size limit, so the log stays
small however long the work runs.

Code anywhere can report through the module helpers ``set_phase`` and
``add``; they do nothing when no log is running.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import IO

DEFAULT_INTERVAL_SECONDS = 60.0
DEFAULT_MAX_BYTES = 1_000_000

# The running log, if any; a dict so the helpers need no global statement.
_state: dict[str, ProgressLog | None] = {"current": None}


class ProgressLog:
    """Write a status line every ``interval`` seconds until stopped."""

    def __init__(
        self,
        interval: float = DEFAULT_INTERVAL_SECONDS,
        stream: IO[str] | None = sys.stderr,
        log_file: Path | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ):
        self.interval = interval
        self.stream = stream
        self.log_file = log_file
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._name = ""
        self._phase = ""
        self._detail = ""
        self._counts: dict[str, int] = {}
        self._started = 0.0

    def start(self, name: str) -> None:
        self._name = name
        self._started = time.monotonic()
        self._rotate()
        self._emit("started")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._emit(self._line() + " | done")

    def set_phase(self, phase: str, detail: str = "") -> None:
        with self._lock:
            self._phase = phase
            self._detail = detail

    def add(self, counter: str, amount: int = 1) -> None:
        with self._lock:
            self._counts[counter] = self._counts.get(counter, 0) + amount

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._emit(self._line())

    def _line(self) -> str:
        with self._lock:
            phase = " ".join(part for part in (self._phase, self._detail) if part)
            counts = " ".join(f"{key}={value}" for key, value in self._counts.items())
        elapsed = int(time.monotonic() - self._started)
        minutes, seconds = divmod(elapsed, 60)
        parts = [f"{self._name}: {phase or 'starting'}"]
        if counts:
            parts.append(counts)
        parts.append(f"elapsed {minutes}m{seconds:02d}s")
        return " | ".join(parts)

    def _emit(self, text: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {text}"
        if self.stream is not None:
            try:
                self.stream.write(line + "\n")
                self.stream.flush()
            except (OSError, ValueError):
                pass
        if self.log_file is not None:
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_file, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError:
                pass

    def _rotate(self) -> None:
        if self.log_file is None:
            return
        try:
            if self.log_file.stat().st_size > self.max_bytes:
                os.replace(self.log_file, self.log_file.with_name(self.log_file.name + ".1"))
        except OSError:
            pass


def start(name: str, *, quiet: bool = False, log_file: Path | None = None) -> ProgressLog:
    """Start the process-wide progress log; CAGELENS_PROGRESS_INTERVAL sets seconds."""
    if _state["current"] is not None:
        return _state["current"]
    try:
        interval = float(os.environ.get("CAGELENS_PROGRESS_INTERVAL", DEFAULT_INTERVAL_SECONDS))
    except ValueError:
        interval = DEFAULT_INTERVAL_SECONDS
    log = ProgressLog(
        interval=max(interval, 1.0), stream=None if quiet else sys.stderr, log_file=log_file
    )
    _state["current"] = log
    log.start(name)
    return log


def stop() -> None:
    log = _state["current"]
    if log is not None:
        _state["current"] = None
        log.stop()


def current() -> ProgressLog | None:
    return _state["current"]


def set_phase(phase: str, detail: str = "") -> None:
    log = _state["current"]
    if log is not None:
        log.set_phase(phase, detail)


def add(counter: str, amount: int = 1) -> None:
    log = _state["current"]
    if log is not None:
        log.add(counter, amount)
