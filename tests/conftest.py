"""Test-wide fixtures and hooks."""

import os
import sys

# Keep a dedicated stdout handle that tests cannot accidentally close.
_safe_stdout = os.fdopen(
    os.dup(sys.__stdout__.fileno()),
    "w",
    encoding=sys.__stdout__.encoding,
    errors=getattr(sys.__stdout__, "errors", "strict"),
    buffering=1,
)


def _restore_stdout():
    sys.stdout = _safe_stdout


def pytest_sessionfinish(session, exitstatus):
    """Restore stdout if a test closed or replaced it.

    Some tests or third-party tools may leave ``sys.stdout`` pointing to a
    closed stream, which causes pytest's final flush to raise an OSError on
    Windows. Resetting to the dedicated safe stream keeps session teardown stable.
    """
    _restore_stdout()


def pytest_unconfigure(config):
    """Ensure stdout is valid right before pytest exits."""
    _restore_stdout()
