#!/usr/bin/env python3
"""
Per-layer coverage enforcement script.

Enforces coverage thresholds for different architectural layers:
- Domain layer: 100%
- Application layer: 90%
- Overall: 80%
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


class CoverageMetrics(NamedTuple):
    """Coverage metrics for a layer or overall."""

    percent_covered: float
    lines_covered: int
    lines_total: int


class CoverageThreshold(NamedTuple):
    """Coverage threshold for a layer."""

    name: str
    path_pattern: str
    minimum_percent: float


# Define coverage thresholds for each layer
COVERAGE_THRESHOLDS = [
    CoverageThreshold(name="Domain", path_pattern="src/codetoreum/domain", minimum_percent=100.0),
    CoverageThreshold(name="Application", path_pattern="src/codetoreum/application", minimum_percent=90.0),
]

OVERALL_MINIMUM_PERCENT = 80.0


def run_coverage_tests() -> str:
    """Run pytest with coverage and return coverage JSON output path."""
    print("Running tests with coverage...")

    # Use pytest from the project's virtual environment
    venv_pytest = Path.cwd() / ".venv" / "bin" / "pytest"
    pytest_cmd: list[str] | None = None

    if venv_pytest.exists():
        pytest_cmd = [str(venv_pytest)]
    else:
        # Try poetry as fallback (useful in CI environments)
        pytest_cmd = ["poetry", "run", "pytest"]

    result = subprocess.run(
        pytest_cmd
        + [
            "tests",
            "--cov=src/codetoreum",
            "--cov-report=json",
            "--cov-report=xml",
            "-q",
            "--tb=line",
        ],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )

    # Exit codes: 0 = all pass, 1 = test failures (coverage still collected), >1 = error
    if result.returncode > 1:
        print(f"Error running tests: {result.stderr}")
        sys.exit(1)

    # The coverage.json should be in the current directory
    coverage_json_path = Path("coverage.json")
    if not coverage_json_path.exists():
        print("Error: coverage.json not found")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        sys.exit(1)

    return str(coverage_json_path)


def parse_coverage_json(json_path: str) -> dict:
    """Parse coverage.json file."""
    with open(json_path) as f:
        return json.load(f)


def get_layer_coverage(coverage_data: dict, path_pattern: str) -> CoverageMetrics:
    """Extract coverage metrics for a specific layer/path pattern."""
    files_data = coverage_data.get("files", {})

    total_lines = 0
    covered_lines = 0

    for file_path, file_data in files_data.items():
        # Only consider files matching the path pattern
        if path_pattern not in file_path:
            continue

        summary = file_data.get("summary", {})
        total_lines += summary.get("num_statements", 0)
        covered_lines += summary.get("covered_lines", 0)

    if total_lines == 0:
        return CoverageMetrics(percent_covered=0.0, lines_covered=0, lines_total=0)

    percent_covered = (covered_lines / total_lines) * 100.0
    return CoverageMetrics(percent_covered=percent_covered, lines_covered=covered_lines, lines_total=total_lines)


def get_overall_coverage(coverage_data: dict) -> CoverageMetrics:
    """Extract overall coverage metrics."""
    total = coverage_data.get("totals", {})
    total_lines = total.get("num_statements", 0)
    covered_lines = total.get("covered_lines", 0)

    if total_lines == 0:
        return CoverageMetrics(percent_covered=0.0, lines_covered=0, lines_total=0)

    percent_covered = (covered_lines / total_lines) * 100.0
    return CoverageMetrics(percent_covered=percent_covered, lines_covered=covered_lines, lines_total=total_lines)


def enforce_coverage(coverage_json_path: str) -> int:
    """Enforce coverage thresholds and return exit code."""
    coverage_data = parse_coverage_json(coverage_json_path)

    all_passed = True
    results = []

    # Check layer-specific thresholds
    for threshold in COVERAGE_THRESHOLDS:
        metrics = get_layer_coverage(coverage_data, threshold.path_pattern)
        passed = metrics.percent_covered >= threshold.minimum_percent
        all_passed = all_passed and passed

        status = "✓ PASS" if passed else "✗ FAIL"
        results.append(
            f"{status} {threshold.name:12} {metrics.percent_covered:6.2f}% "
            f"({metrics.lines_covered}/{metrics.lines_total} lines) "
            f"[required: {threshold.minimum_percent:.2f}%]"
        )

    # Check overall threshold
    overall_metrics = get_overall_coverage(coverage_data)
    overall_passed = overall_metrics.percent_covered >= OVERALL_MINIMUM_PERCENT
    all_passed = all_passed and overall_passed

    status = "✓ PASS" if overall_passed else "✗ FAIL"
    results.append(
        f"{status} {'Overall':12} {overall_metrics.percent_covered:6.2f}% "
        f"({overall_metrics.lines_covered}/{overall_metrics.lines_total} lines) "
        f"[required: {OVERALL_MINIMUM_PERCENT:.2f}%]"
    )

    # Print results
    print("\n" + "=" * 80)
    print("Coverage Enforcement Results")
    print("=" * 80)
    for result in results:
        print(result)
    print("=" * 80 + "\n")

    return 0 if all_passed else 1


def main() -> int:
    """Main entry point."""
    try:
        coverage_json_path = run_coverage_tests()
        return enforce_coverage(coverage_json_path)
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
