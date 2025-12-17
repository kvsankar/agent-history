#!/bin/bash
# Run all tests with coverage tracking
# This script runs inside the test-runner container

set -e

# Default to running all tests
TEST_PATH="${1:-tests/}"
shift 2>/dev/null || true

echo "=== Running Tests with Coverage ==="
echo "Test path: $TEST_PATH"

# Run pytest with coverage
# Unit tests run directly with coverage, E2E tests use subprocess coverage via helpers.py
coverage run --rcfile=/app/.coveragerc --data-file=/coverage/.coverage.main \
    -m pytest "$TEST_PATH" -v "$@"

# Combine parallel coverage data (from E2E subprocess calls)
echo ""
echo "=== Combining Coverage Data ==="
cd /coverage

if ls .coverage.* 1> /dev/null 2>&1; then
    coverage combine --rcfile=/app/.coveragerc

    echo ""
    echo "=== Coverage Report ==="
    coverage report --rcfile=/app/.coveragerc --include="*/agent-history" --show-missing

    echo ""
    echo "=== Coverage Summary ==="
    TOTAL=$(coverage report --rcfile=/app/.coveragerc --include="*/agent-history" --format=total)
    echo "agent-history coverage: ${TOTAL}%"
else
    echo "No coverage data files found in /coverage"
    ls -la /coverage/ || true
fi
