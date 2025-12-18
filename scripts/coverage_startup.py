"""Enable coverage for subprocesses when COVERAGE_PROCESS_START is set.

Keep this file off sys.path by default. When you want subprocess coverage,
set:
    COVERAGE_PROCESS_START=.coveragerc
    PYTHONPATH=<repo>/scripts:$PYTHONPATH
Then run tests under `coverage run -p ...` (or `make coverage`).
"""

import coverage

coverage.process_startup()
