#!/usr/bin/env python3
"""
Cross-platform coverage orchestrator for Windows + WSL.

Run from Windows to:
1. Run tests with coverage on Windows
2. Run tests with coverage in WSL (via wsl command)
3. Collect and merge coverage data from both environments
4. Generate combined coverage report

Usage:
    python scripts/run-coverage.py [--windows-only] [--wsl-only] [--merge-only] [--report]

Configuration:
    Copy scripts/coverage.config.template to scripts/coverage.config
    and fill in your paths. The config file is gitignored.
"""

import argparse
import configparser
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "coverage.config"
CONFIG_TEMPLATE = SCRIPT_DIR / "coverage.config.template"


def load_config() -> configparser.ConfigParser:
    """Load configuration from coverage.config file."""
    if not CONFIG_FILE.exists():
        print(f"Error: Config file not found: {CONFIG_FILE}")
        print(f"Please copy {CONFIG_TEMPLATE} to {CONFIG_FILE} and fill in your paths.")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config


def validate_config(config: configparser.ConfigParser) -> dict:
    """Validate and extract configuration values."""
    try:
        windows_project = Path(config.get("paths", "windows_project"))
        wsl_project = config.get("paths", "wsl_project")
        wsl_distro = config.get("paths", "wsl_distro")
        output_dir = config.get("output", "output_dir", fallback=".coverage-merged")
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        print(f"Error: Missing config option: {e}")
        sys.exit(1)

    if not windows_project.exists():
        print(f"Error: Windows project path does not exist: {windows_project}")
        sys.exit(1)

    return {
        "windows_project": windows_project,
        "wsl_project": wsl_project,
        "wsl_distro": wsl_distro,
        "output_dir": windows_project / output_dir,
    }


def run_windows_tests(project_path: Path) -> bool:
    """Run tests with coverage on Windows."""
    print("\n" + "=" * 60)
    print("Running Windows tests with coverage...")
    print("=" * 60)

    # Clean old coverage data
    for f in project_path.glob(".coverage*"):
        if f.is_file():
            f.unlink()

    cmd = [
        "uv",
        "run",
        "pytest",
        "--cov=.",
        "--cov-branch",
        "--cov-report=",  # No report yet, just collect data
        "-x",
        "-q",
        "tests/unit/",
    ]

    result = subprocess.run(cmd, cwd=project_path)
    if result.returncode != 0:
        print("Windows tests failed!")
        return False

    # Rename coverage file to identify source
    cov_file = project_path / ".coverage"
    if cov_file.exists():
        cov_file.rename(project_path / ".coverage.windows")
        print("Windows coverage saved to .coverage.windows")

    return True


def run_wsl_tests(windows_project: Path, wsl_project: str, wsl_distro: str) -> bool:
    """Run tests with coverage in WSL."""
    print("\n" + "=" * 60)
    print(f"Running WSL ({wsl_distro}) tests with coverage...")
    print("=" * 60)

    # Build WSL command - run pytest with coverage in WSL
    wsl_cmd = f"""
cd "{wsl_project}" && \\
rm -f .coverage .coverage.* && \\
uv run pytest --cov=. --cov-branch --cov-report= -x -q tests/unit/ && \\
mv .coverage .coverage.wsl 2>/dev/null || true
"""

    cmd = ["wsl", "-d", wsl_distro, "bash", "-c", wsl_cmd]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("WSL tests failed!")
        return False

    print("WSL coverage saved to .coverage.wsl")
    return True


def collect_wsl_coverage(windows_project: Path, wsl_project: str, wsl_distro: str) -> bool:
    """Copy WSL coverage file to Windows project."""
    print("\nCollecting WSL coverage data...")

    # Convert WSL path to Windows UNC path
    # /home/user/project -> \\wsl.localhost\Ubuntu\home\user\project
    wsl_unc = Path(f"\\\\wsl.localhost\\{wsl_distro}") / wsl_project.lstrip("/")
    wsl_cov = wsl_unc / ".coverage.wsl"

    if not wsl_cov.exists():
        print(f"Warning: WSL coverage file not found at {wsl_cov}")
        return False

    dest = windows_project / ".coverage.wsl"
    shutil.copy2(wsl_cov, dest)
    print(f"Copied WSL coverage to {dest}")
    return True


def merge_coverage(config: dict) -> bool:
    """Merge coverage data from Windows and WSL."""
    print("\n" + "=" * 60)
    print("Merging coverage data...")
    print("=" * 60)

    project = config["windows_project"]
    output_dir = config["output_dir"]
    wsl_project = config["wsl_project"]

    # Create output directory
    output_dir.mkdir(exist_ok=True)

    # Create .coveragerc for merging with path mappings
    coveragerc = output_dir / ".coveragerc"
    coveragerc_content = f"""[run]
parallel = true
source = .
branch = true
data_file = {output_dir / '.coverage'}

[paths]
source =
    .
    {project}
    {wsl_project}

[report]
show_missing = true
skip_covered = false
"""
    coveragerc.write_text(coveragerc_content)

    # Copy coverage files to output directory
    for cov_file in project.glob(".coverage.*"):
        if cov_file.is_file() and cov_file.suffix in (".windows", ".wsl"):
            dest = output_dir / cov_file.name
            shutil.copy2(cov_file, dest)
            print(f"  Copied {cov_file.name}")

    # Combine coverage data
    cmd = [
        "uv",
        "run",
        "coverage",
        "combine",
        "--rcfile",
        str(coveragerc),
    ]
    result = subprocess.run(cmd, cwd=output_dir)
    if result.returncode != 0:
        print("Coverage combine failed!")
        return False

    print("Coverage data merged successfully")
    return True


def generate_report(config: dict) -> bool:
    """Generate coverage report."""
    print("\n" + "=" * 60)
    print("Generating coverage report...")
    print("=" * 60)

    output_dir = config["output_dir"]
    coveragerc = output_dir / ".coveragerc"

    # Terminal report
    cmd = [
        "uv",
        "run",
        "coverage",
        "report",
        "--rcfile",
        str(coveragerc),
    ]
    result = subprocess.run(cmd, cwd=output_dir)

    # HTML report
    html_dir = output_dir / "htmlcov"
    cmd = [
        "uv",
        "run",
        "coverage",
        "html",
        "--rcfile",
        str(coveragerc),
        "-d",
        str(html_dir),
    ]
    subprocess.run(cmd, cwd=output_dir)
    print(f"\nHTML report generated at: {html_dir / 'index.html'}")

    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Cross-platform coverage orchestrator for Windows + WSL"
    )
    parser.add_argument("--windows-only", action="store_true", help="Run only Windows tests")
    parser.add_argument("--wsl-only", action="store_true", help="Run only WSL tests")
    parser.add_argument(
        "--merge-only", action="store_true", help="Only merge existing coverage data (skip tests)"
    )
    parser.add_argument(
        "--report", action="store_true", help="Generate report from existing merged data"
    )
    args = parser.parse_args()

    config = load_config()
    cfg = validate_config(config)

    print(f"Windows project: {cfg['windows_project']}")
    print(f"WSL project: {cfg['wsl_project']}")
    print(f"WSL distro: {cfg['wsl_distro']}")
    print(f"Output directory: {cfg['output_dir']}")

    if args.report:
        # Just generate report from existing data
        generate_report(cfg)
        return

    if args.merge_only:
        # Just merge existing coverage files
        if merge_coverage(cfg):
            generate_report(cfg)
        return

    success = True

    # Run tests
    if not args.wsl_only:
        if not run_windows_tests(cfg["windows_project"]):
            success = False

    if not args.windows_only:
        if not run_wsl_tests(cfg["windows_project"], cfg["wsl_project"], cfg["wsl_distro"]):
            success = False
        else:
            collect_wsl_coverage(cfg["windows_project"], cfg["wsl_project"], cfg["wsl_distro"])

    # Merge and report
    if success or args.merge_only:
        if merge_coverage(cfg):
            generate_report(cfg)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
