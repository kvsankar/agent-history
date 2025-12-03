param(
  [switch]$Unit,
  [switch]$Integration
)

# PowerShell helper to run tests consistently on Windows
# Examples:
#   scripts\run-tests.ps1               # all tests
#   scripts\run-tests.ps1 -Unit         # unit tests only
#   scripts\run-tests.ps1 -Integration  # integration tests only

if ($Unit -and $Integration) {
  Write-Error "Specify either -Unit or -Integration, not both."
  exit 2
}

if ($Unit) {
  uv run python -m pytest -q -m "not integration"
  exit $LASTEXITCODE
}

if ($Integration) {
  uv run python -m pytest -q -m integration tests/integration
  exit $LASTEXITCODE
}

# default: run all
uv run python -m pytest -q
exit $LASTEXITCODE

