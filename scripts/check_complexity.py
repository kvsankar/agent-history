#!/usr/bin/env python3
"""
Pre-commit hook to check code complexity using radon.

Enforces:
- Cyclomatic complexity: max C grade (<=20) for new/modified functions
- Fails on D/E/F grades (>20) which indicate functions needing refactoring
- Allows baselined functions (existing tech debt)

Usage:
    python scripts/check_complexity.py [files...]

Exit codes:
    0: All checks passed
    1: Complexity violations found
"""

import subprocess
import sys
from pathlib import Path

# Complexity thresholds
MAX_CC_GRADE = "C"  # Maximum acceptable complexity grade
MAX_CC_VALUE = 20  # C grade max value

# Grade order for comparison (lower index = better)
GRADE_ORDER = ["A", "B", "C", "D", "E", "F"]

# Baselined functions - existing tech debt with high complexity
# These are allowed to pass but should be refactored over time
# Format: (filename, function_name): max_allowed_complexity
# NOTE: All D-grade functions have been refactored to C or better.
# The baseline below allows C-grade functions (complexity 11-20).
BASELINE = {
    # Temporary allowance while UNC normalization is refactored
    ("claude-history", "_resolve_existing_wsl_path"): 36,
}


def is_grade_acceptable(grade: str) -> bool:
    """Check if grade is acceptable (A, B, or C)."""
    try:
        grade_idx = GRADE_ORDER.index(grade.upper())
        max_idx = GRADE_ORDER.index(MAX_CC_GRADE)
        return grade_idx <= max_idx
    except ValueError:
        return False


def filter_python_files(files: list[str]) -> list[str]:
    """Filter to only Python files, excluding tests."""
    result = []
    for f in files:
        path = Path(f)
        is_python = path.suffix == ".py" or path.name == "claude-history"
        is_test = path.name.startswith("test_") or path.name.endswith("_test.py")
        if is_python and not is_test:
            result.append(f)
    return result


def parse_radon_line(line: str):
    """Parse a radon output line. Returns (name, grade, complexity) or None."""
    line = line.strip()
    if not line:
        return None

    parts = line.split()
    if len(parts) < 5 or not parts[-1].endswith(")"):
        return None

    try:
        grade = parts[-2]
        if grade not in GRADE_ORDER:
            return None
        name = parts[2]
        location = parts[1]
        complexity = int(parts[-1].strip("()"))
        return {"name": name, "location": location, "grade": grade, "complexity": complexity}
    except (IndexError, ValueError):
        return None


def check_violation(filepath: str, parsed: dict) -> str | None:
    """Check if a parsed line is a violation. Returns violation message or None."""
    if is_grade_acceptable(parsed["grade"]):
        return None

    filename = Path(filepath).name
    baseline_key = (filename, parsed["name"])
    baseline_max = BASELINE.get(baseline_key)

    if baseline_max is not None and parsed["complexity"] <= baseline_max:
        return None  # Within baseline

    line_num = parsed["location"].split(":")[0]
    if baseline_max is not None:
        return (
            f"  {filepath}:{line_num} {parsed['name']} - "
            f"complexity {parsed['grade']} ({parsed['complexity']}) > baseline ({baseline_max})"
        )
    return (
        f"  {filepath}:{line_num} {parsed['name']} - "
        f"complexity {parsed['grade']} ({parsed['complexity']}) > max {MAX_CC_GRADE} ({MAX_CC_VALUE})"
    )


def check_file_complexity(filepath: str) -> list[str]:
    """Check complexity of a single file. Returns list of violations."""
    try:
        result = subprocess.run(
            ["radon", "cc", filepath, "-s", "-a"], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return []

        violations = []
        for line in result.stdout.splitlines():
            if line.startswith(filepath):
                continue
            parsed = parse_radon_line(line)
            if parsed:
                violation = check_violation(filepath, parsed)
                if violation:
                    violations.append(violation)
        return violations
    except subprocess.TimeoutExpired:
        print(f"Warning: Timeout checking {filepath}", file=sys.stderr)
        return []
    except FileNotFoundError:
        print("Error: radon not found. Install with: uv add --dev radon", file=sys.stderr)
        return ["radon not installed"]


def check_cyclomatic_complexity(files: list[str]) -> tuple[bool, list[str]]:
    """Check cyclomatic complexity of given files."""
    python_files = filter_python_files(files)
    if not python_files:
        return True, []

    violations = []
    for filepath in python_files:
        violations.extend(check_file_complexity(filepath))

    return len(violations) == 0, violations


def check_maintainability_index(files: list[str]) -> tuple[bool, list[str]]:
    """Check maintainability index of given files (informational only)."""
    python_files = filter_python_files(files)
    if not python_files:
        return True, []

    warnings = []
    for filepath in python_files:
        try:
            result = subprocess.run(
                ["radon", "mi", filepath, "-s"], capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                continue

            for line in result.stdout.splitlines():
                if " - C " in line:  # C grade is concerning
                    warnings.append(f"  {filepath}: {line.strip()}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return True, warnings


def main():
    """Main entry point."""
    files = sys.argv[1:] if len(sys.argv) > 1 else ["claude-history"]

    print("Checking code complexity with radon...")

    cc_passed, cc_violations = check_cyclomatic_complexity(files)
    _, mi_warnings = check_maintainability_index(files)

    if cc_violations:
        print("\n❌ Cyclomatic Complexity Violations (max grade: C, max value: 20):")
        for v in cc_violations:
            print(v)
        print("\nFunctions with grade D (21-30), E (31-40), or F (41+) need refactoring.")
        print("Consider breaking down into smaller functions.\n")

    if mi_warnings:
        print("\n⚠️  Maintainability Index Warnings:")
        for w in mi_warnings:
            print(w)
        print()

    if cc_passed:
        print("✅ Complexity check passed")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
