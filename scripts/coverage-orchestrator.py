#!/usr/bin/env python3
"""
Coverage Orchestrator for agent-history.

This script manages coverage collection across multiple environments:
- WSL (Windows Subsystem for Linux)
- Docker (E2E tests with SSH containers)
- Windows (native Windows tests)
- Linux (native Linux/Ubuntu tests)

Usage:
    python scripts/coverage-orchestrator.py status      # Show environment and coverage status
    python scripts/coverage-orchestrator.py run         # Run tests for current environment
    python scripts/coverage-orchestrator.py merge       # Merge coverage data from all sources
    python scripts/coverage-orchestrator.py report      # Generate combined coverage report
    python scripts/coverage-orchestrator.py all         # Run all: tests, merge, report

Coverage Data Flow:
    +-----------------+     +-----------------+     +-----------------+
    |   WSL Tests     |     |  Docker E2E     |     | Windows Tests   |
    | .coverage.wsl   |     | .coverage.docker|     | .coverage.win   |
    +-----------------+     +-----------------+     +-----------------+
            |                       |                       |
            +-----------------------------------------------+
                                    |
                            +---------------+
                            | coverage merge|
                            +---------------+
                                    |
                            +---------------+
                            |  .coverage    |
                            | (combined)    |
                            +---------------+
                                    |
                            +---------------+
                            | HTML Report   |
                            | htmlcov/      |
                            +---------------+
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ============================================================================
# Environment Detection
# ============================================================================


def is_wsl() -> bool:
    """Check if running in Windows Subsystem for Linux."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except (FileNotFoundError, PermissionError):
        return False


def is_docker() -> bool:
    """Check if running inside a Docker container."""
    return os.path.exists("/.dockerenv")


def is_windows() -> bool:
    """Check if running on native Windows."""
    return platform.system() == "Windows"


def is_linux() -> bool:
    """Check if running on native Linux (not WSL)."""
    return platform.system() == "Linux" and not is_wsl()


def get_environment() -> str:
    """Get the current execution environment."""
    if is_docker():
        return "docker"
    if is_windows():
        return "windows"
    if is_wsl():
        return "wsl"
    if is_linux():
        return "linux"
    return "unknown"


def has_docker() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def has_docker_compose() -> bool:
    """Check if docker-compose is available."""
    try:
        result = subprocess.run(
            ["docker-compose", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ============================================================================
# Path Configuration
# ============================================================================


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.resolve()


def get_python_cmd() -> list:
    """Get the Python command to use (prefers uv run if available)."""
    project_root = get_project_root()

    # Check for uv
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, timeout=5)
        if result.returncode == 0:
            return ["uv", "run", "python"]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check for venv Python
    venv_python = project_root / ".venv" / "bin" / "python3"
    if venv_python.exists():
        return [str(venv_python)]

    # Fall back to sys.executable
    return [sys.executable]


def get_coverage_dir() -> Path:
    """Get the directory for storing coverage data."""
    coverage_dir = get_project_root() / ".coverage-data"
    coverage_dir.mkdir(exist_ok=True)
    return coverage_dir


def get_coverage_file(env: str) -> Path:
    """Get the coverage data file for a specific environment."""
    return get_coverage_dir() / f".coverage.{env}"


# ============================================================================
# Test Execution
# ============================================================================


def run_unit_tests(project_root: Path, coverage_file: Path) -> int:
    """Run unit tests with coverage."""
    print("\n=== Running Unit Tests ===")
    python_cmd = get_python_cmd()
    cmd = [
        *python_cmd,
        "-m",
        "coverage",
        "run",
        "--rcfile",
        str(project_root / ".coveragerc"),
        "--data-file",
        str(coverage_file),
        "-m",
        "pytest",
        "tests/unit/test_claude_history.py",
        "-v",
        "--tb=short",
    ]
    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode


def run_integration_tests(project_root: Path, coverage_file: Path) -> int:
    """Run integration tests with coverage."""
    print("\n=== Running Integration Tests ===")
    python_cmd = get_python_cmd()
    cmd = [
        *python_cmd,
        "-m",
        "coverage",
        "run",
        "--rcfile",
        str(project_root / ".coveragerc"),
        "--data-file",
        str(coverage_file),
        "-m",
        "pytest",
        "tests/integration/",
        "-v",
        "--tb=short",
        "--ignore=tests/integration/test_wsl_specific.py",  # WSL tests separate
    ]
    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode


def run_wsl_tests(project_root: Path, coverage_file: Path) -> int:
    """Run WSL-specific tests with coverage."""
    if not is_wsl():
        print("Skipping WSL tests - not in WSL environment")
        return 0

    print("\n=== Running WSL-Specific Tests ===")
    python_cmd = get_python_cmd()
    cmd = [
        *python_cmd,
        "-m",
        "coverage",
        "run",
        "--rcfile",
        str(project_root / ".coveragerc"),
        "--data-file",
        str(coverage_file),
        "-m",
        "pytest",
        "tests/integration/test_wsl_specific.py",
        "-v",
        "--tb=short",
    ]
    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode


def run_docker_e2e_tests(project_root: Path, coverage_file: Path) -> int:
    """Run Docker E2E tests and extract coverage data."""
    if not has_docker() or not has_docker_compose():
        print("Skipping Docker E2E tests - Docker not available")
        return 0

    print("\n=== Running Docker E2E Tests ===")
    docker_dir = project_root / "docker"

    # Start containers
    print("Starting Docker containers...")
    result = subprocess.run(
        ["docker-compose", "up", "-d", "--build"],
        cwd=docker_dir,
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"Failed to start containers: {result.stderr.decode()}")
        return result.returncode

    # Run tests
    print("Running E2E tests...")
    result = subprocess.run(
        ["docker-compose", "run", "test-runner"],
        cwd=docker_dir,
    )
    test_returncode = result.returncode

    # Extract coverage data from Docker volume
    print("Extracting coverage data from Docker...")
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            "docker_coverage-data:/coverage:ro",
            "-v",
            f"{coverage_file.parent}:/output",
            "alpine",
            "sh",
            "-c",
            "cp /coverage/.coverage* /output/ 2>/dev/null || echo 'No coverage files found'",
        ],
        cwd=docker_dir,
        capture_output=True,
    )

    # Rename extracted coverage file
    docker_cov = coverage_file.parent / ".coverage"
    if docker_cov.exists() and docker_cov != coverage_file:
        shutil.move(str(docker_cov), str(coverage_file))

    # Clean up containers
    print("Cleaning up Docker containers...")
    subprocess.run(
        ["docker-compose", "down", "-v"],
        cwd=docker_dir,
        capture_output=True,
    )

    return test_returncode


# ============================================================================
# Coverage Operations
# ============================================================================


def list_coverage_files(coverage_dir: Path) -> list:
    """List all coverage data files."""
    files = []
    for f in coverage_dir.glob(".coverage.*"):
        if f.is_file():
            stat = f.stat()
            files.append(
                {
                    "path": f,
                    "name": f.name,
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime),
                }
            )
    return sorted(files, key=lambda x: x["name"])


def merge_coverage(project_root: Path, coverage_dir: Path, output_file: Path) -> int:
    """Merge all coverage data files into a single file."""
    print("\n=== Merging Coverage Data ===")

    coverage_files = list_coverage_files(coverage_dir)
    if not coverage_files:
        print("No coverage data files found to merge")
        return 1

    print(f"Found {len(coverage_files)} coverage files:")
    for f in coverage_files:
        print(f"  - {f['name']} ({f['size']} bytes, {f['mtime']})")

    # Copy all coverage files to project root for combining
    # coverage combine expects files in the same directory
    for f in coverage_files:
        dest = project_root / f["name"]
        if dest != f["path"]:
            shutil.copy(str(f["path"]), str(dest))

    # Run coverage combine
    python_cmd = get_python_cmd()
    cmd = [
        *python_cmd,
        "-m",
        "coverage",
        "combine",
        "--rcfile",
        str(project_root / ".coveragerc"),
        "--data-file",
        str(output_file),
    ]
    result = subprocess.run(cmd, cwd=project_root)

    # Clean up copied files
    for f in coverage_files:
        temp_file = project_root / f["name"]
        if temp_file.exists() and temp_file != f["path"]:
            temp_file.unlink()

    return result.returncode


def generate_report(project_root: Path, coverage_file: Path, html: bool = True) -> int:
    """Generate coverage report."""
    print("\n=== Coverage Report ===")

    if not coverage_file.exists():
        print(f"Coverage file not found: {coverage_file}")
        return 1

    # Terminal report
    python_cmd = get_python_cmd()
    cmd = [
        *python_cmd,
        "-m",
        "coverage",
        "report",
        "--rcfile",
        str(project_root / ".coveragerc"),
        "--data-file",
        str(coverage_file),
        "--show-missing",
    ]
    result = subprocess.run(cmd, cwd=project_root)

    if html:
        print("\n=== Generating HTML Report ===")
        cmd = [
            *python_cmd,
            "-m",
            "coverage",
            "html",
            "--rcfile",
            str(project_root / ".coveragerc"),
            "--data-file",
            str(coverage_file),
            "-d",
            str(project_root / "htmlcov"),
        ]
        html_result = subprocess.run(cmd, cwd=project_root)
        if html_result.returncode == 0:
            print(f"HTML report generated: {project_root / 'htmlcov' / 'index.html'}")

    return result.returncode


# ============================================================================
# Commands
# ============================================================================


def cmd_status(args):
    """Show environment and coverage status."""
    env = get_environment()
    project_root = get_project_root()
    coverage_dir = get_coverage_dir()

    print("=" * 60)
    print("Coverage Orchestrator Status")
    print("=" * 60)

    print(f"\nEnvironment: {env}")
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Project Root: {project_root}")
    print(f"Coverage Dir: {coverage_dir}")

    print(f"\nDocker Available: {has_docker()}")
    print(f"Docker Compose Available: {has_docker_compose()}")

    print("\n" + "-" * 60)
    print("Available Test Suites for Current Environment:")
    print("-" * 60)

    suites = [
        ("Unit Tests", True, "tests/unit/test_claude_history.py"),
        ("Integration Tests", True, "tests/integration/ (excluding WSL)"),
        ("WSL-Specific Tests", is_wsl(), "tests/integration/test_wsl_specific.py"),
        ("Docker E2E Tests", has_docker(), "tests/e2e_docker/"),
    ]

    for name, available, path in suites:
        status = "✓" if available else "✗"
        print(f"  {status} {name}: {path}")

    print("\n" + "-" * 60)
    print("Coverage Data Files:")
    print("-" * 60)

    coverage_files = list_coverage_files(coverage_dir)
    if coverage_files:
        for f in coverage_files:
            print(f"  - {f['name']}")
            print(f"    Size: {f['size']} bytes")
            print(f"    Modified: {f['mtime']}")
    else:
        print("  No coverage data files found")

    # Check for combined coverage file
    combined = project_root / ".coverage"
    if combined.exists():
        stat = combined.stat()
        print("\n  Combined coverage file:")
        print(f"    {combined}")
        print(f"    Size: {stat.st_size} bytes")
        print(f"    Modified: {datetime.fromtimestamp(stat.st_mtime)}")

    return 0


def cmd_run(args):
    """Run tests for the current environment."""
    env = get_environment()
    project_root = get_project_root()

    print(f"Running tests in {env} environment...")

    # Determine which tests to run based on flags
    run_all = not (args.unit or args.integration or args.wsl or args.docker)

    results = []

    if run_all or args.unit:
        coverage_file = get_coverage_file("unit")
        result = run_unit_tests(project_root, coverage_file)
        results.append(("Unit Tests", result))

    if run_all or args.integration:
        coverage_file = get_coverage_file("integration")
        result = run_integration_tests(project_root, coverage_file)
        results.append(("Integration Tests", result))

    if (run_all or args.wsl) and is_wsl():
        coverage_file = get_coverage_file("wsl")
        result = run_wsl_tests(project_root, coverage_file)
        results.append(("WSL Tests", result))

    if (run_all or args.docker) and has_docker():
        coverage_file = get_coverage_file("docker")
        result = run_docker_e2e_tests(project_root, coverage_file)
        results.append(("Docker E2E Tests", result))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    overall = 0
    for name, code in results:
        status = "PASSED" if code == 0 else f"FAILED ({code})"
        print(f"  {name}: {status}")
        if code != 0:
            overall = 1

    return overall


def cmd_merge(args):
    """Merge coverage data from all sources."""
    project_root = get_project_root()
    coverage_dir = get_coverage_dir()
    output_file = project_root / ".coverage"

    return merge_coverage(project_root, coverage_dir, output_file)


def cmd_report(args):
    """Generate coverage report."""
    project_root = get_project_root()
    coverage_file = project_root / ".coverage"

    return generate_report(project_root, coverage_file, html=not args.no_html)


def cmd_all(args):
    """Run all: tests, merge, and report."""
    results = []

    # Run tests
    result = cmd_run(args)
    results.append(("Tests", result))

    # Merge coverage
    result = cmd_merge(args)
    results.append(("Merge", result))

    # Generate report
    result = cmd_report(args)
    results.append(("Report", result))

    print("\n" + "=" * 60)
    print("Overall Summary")
    print("=" * 60)

    for name, code in results:
        status = "OK" if code == 0 else f"FAILED ({code})"
        print(f"  {name}: {status}")

    return max(r[1] for r in results)


def cmd_clean(args):
    """Clean coverage data files."""
    project_root = get_project_root()
    coverage_dir = get_coverage_dir()

    print("Cleaning coverage data...")

    # Clean coverage data directory
    coverage_files = list_coverage_files(coverage_dir)
    for f in coverage_files:
        print(f"  Removing {f['name']}")
        f["path"].unlink()

    # Clean combined coverage file
    combined = project_root / ".coverage"
    if combined.exists():
        print("  Removing .coverage")
        combined.unlink()

    # Clean HTML report
    htmlcov = project_root / "htmlcov"
    if htmlcov.exists():
        print("  Removing htmlcov/")
        shutil.rmtree(htmlcov)

    print("Done.")
    return 0


# ============================================================================
# Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Coverage orchestrator for agent-history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # status command (no arguments)
    subparsers.add_parser("status", help="Show environment and coverage status")

    # run command
    run_parser = subparsers.add_parser("run", help="Run tests for current environment")
    run_parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    run_parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    run_parser.add_argument("--wsl", action="store_true", help="Run WSL-specific tests only")
    run_parser.add_argument("--docker", action="store_true", help="Run Docker E2E tests only")

    # merge command (no arguments)
    subparsers.add_parser("merge", help="Merge coverage data from all sources")

    # report command
    report_parser = subparsers.add_parser("report", help="Generate coverage report")
    report_parser.add_argument("--no-html", action="store_true", help="Skip HTML report generation")

    # all command
    all_parser = subparsers.add_parser("all", help="Run all: tests, merge, report")
    all_parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    all_parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    all_parser.add_argument("--wsl", action="store_true", help="Run WSL-specific tests only")
    all_parser.add_argument("--docker", action="store_true", help="Run Docker E2E tests only")
    all_parser.add_argument("--no-html", action="store_true", help="Skip HTML report generation")

    # clean command (no arguments)
    subparsers.add_parser("clean", help="Clean coverage data files")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "status": cmd_status,
        "run": cmd_run,
        "merge": cmd_merge,
        "report": cmd_report,
        "all": cmd_all,
        "clean": cmd_clean,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
