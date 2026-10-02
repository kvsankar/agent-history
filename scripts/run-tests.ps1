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

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Python = "python"
if (Test-Path $VenvPython) {
  $Python = $VenvPython
}
$Runner = Join-Path $RepoRoot "scripts\run_tests.py"

if ($Unit) {
  & $Python $Runner -q -m "not integration"
  exit $LASTEXITCODE
}

if ($Integration) {
  & $Python $Runner -q -m integration tests/integration
  exit $LASTEXITCODE
}

# default: run all
& $Python $Runner -q
exit $LASTEXITCODE
