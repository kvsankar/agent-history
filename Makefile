.PHONY: test test-unit test-integration

ifeq ($(OS),Windows_NT)
PYTHON ?= $(CURDIR)/.venv/Scripts/python.exe
else
PYTHON ?= $(CURDIR)/.venv/bin/python
endif

# Use the project test runner so Windows gets the fast temp/cache defaults.
# Run `uv sync --dev` first on a fresh checkout, or override PYTHON.

test:
	"$(PYTHON)" scripts/run_tests.py -q

test-unit:
	"$(PYTHON)" scripts/run_tests.py -q -m "not integration"

test-integration:
	"$(PYTHON)" scripts/run_tests.py -q -m integration tests/integration

.PHONY: coverage coverage-report coverage-html coverage-clean

# Docker E2E with coverage (brings the stack down afterward)
.PHONY: docker-coverage
docker-coverage:
	docker compose -f docker/docker-compose.yml run --rm --remove-orphans test-runner /usr/local/bin/run-e2e-coverage.sh tests/e2e_docker/
	docker compose -f docker/docker-compose.yml down --remove-orphans

# Run tests with coverage (including subprocesses via coverage_startup).
coverage:
	COVERAGE_PROCESS_START=.coveragerc PYTHONPATH=scripts:$$PYTHONPATH "$(PYTHON)" -m coverage run -p -m pytest -q
	"$(PYTHON)" -m coverage combine

# Text coverage report.
coverage-report:
	"$(PYTHON)" -m coverage report

# HTML coverage report.
coverage-html:
	"$(PYTHON)" -m coverage html -d .coverage-html

# Remove coverage artifacts (cross-platform).
coverage-clean:
ifeq ($(OS),Windows_NT)
	powershell -Command "Remove-Item -Force -ErrorAction SilentlyContinue .coverage, .coverage.*, .coverage-html/*"
else
	rm -f .coverage .coverage.* .coverage-html/*
endif
