#!/usr/bin/env python3
"""
Per-layer coverage enforcement script.

Enforces coverage thresholds for different architectural layers:
- Domain layer: 100%
- Application layer: 90%
- Overall: 80%

By default, this script prevents regression from the current baseline.
Use --strict to enforce absolute thresholds (fails if below targets).
"""

import argparse
import json
import logging
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


def run_coverage_tests() -> tuple[str, bool]:
    """Run pytest with coverage and return (coverage JSON path, tests_failed).

    Raises:
        RuntimeError: If pytest encounters an error or coverage.json is not created.
    """
    logger = logging.getLogger(__name__)
    logger.info("Running tests with coverage...")

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
            "--tb=short",
        ],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
        check=False,
    )

    # Print pytest output when tests fail or if there's a critical error
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

    # Exit codes: 0 = all pass, 1 = test failures (coverage still collected), >1 = error
    if result.returncode > 1:
        raise RuntimeError(f"Pytest encountered an error (exit code {result.returncode})")

    # The coverage.json should be in the current directory
    coverage_json_path = Path("coverage.json")
    if not coverage_json_path.exists():
        raise RuntimeError(
            f"coverage.json not found. STDOUT: {result.stdout}, STDERR: {result.stderr}"
        )

    # Track whether tests failed (returncode == 1)
    tests_failed = result.returncode == 1
    return str(coverage_json_path), tests_failed


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


def check_regression(current_metrics: CoverageMetrics, baseline_metrics: CoverageMetrics) -> bool:
    """Check if coverage regressed from baseline.

    Args:
        current_metrics: Current coverage metrics
        baseline_metrics: Baseline coverage metrics to compare against

    Returns:
        True if no regression (current >= baseline), False otherwise
    """
    return current_metrics.percent_covered >= baseline_metrics.percent_covered


def load_baseline(baseline_path: str) -> dict | None:
    """Load baseline coverage data if it exists.

    Args:
        baseline_path: Path to baseline coverage.json file

    Returns:
        Coverage data dict if file exists, None otherwise
    """
    path = Path(baseline_path)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def save_baseline(coverage_data: dict, baseline_path: str) -> None:
    """Save coverage data as baseline for future regression detection.

    Args:
        coverage_data: Coverage data to save
        baseline_path: Path where to save baseline
    """
    with open(baseline_path, "w") as f:
        json.dump(coverage_data, f, indent=2)


def enforce_coverage(
    coverage_json_path: str,
    tests_failed: bool,
    strict_mode: bool = False,
    baseline_path: str = "coverage.baseline.json",
) -> int:
    """Enforce coverage thresholds and return exit code.

    Args:
        coverage_json_path: Path to coverage.json file
        tests_failed: Whether pytest exited with returncode 1 (test failures)
        strict_mode: If True, fail on absolute thresholds; if False, only fail on regression
        baseline_path: Path to baseline coverage file for regression detection

    Returns:
        Exit code: 0 if all checks pass, 1 otherwise
    """
    coverage_data = parse_coverage_json(coverage_json_path)
    baseline_data = load_baseline(baseline_path)

    all_passed = True
    results = []

    # Check layer-specific thresholds
    for threshold in COVERAGE_THRESHOLDS:
        metrics = get_layer_coverage(coverage_data, threshold.path_pattern)

        # Pre-compute baseline metrics once if available
        baseline_metrics = None
        if baseline_data is not None:
            baseline_metrics = get_layer_coverage(baseline_data, threshold.path_pattern)

        # Determine pass/fail based on mode
        if strict_mode:
            # Strict mode: enforce absolute thresholds
            passed = metrics.percent_covered >= threshold.minimum_percent
        else:
            # Default mode: only fail on regression
            if baseline_metrics is not None:
                passed = check_regression(metrics, baseline_metrics)
            else:
                # No baseline yet, so can't regress
                passed = True

        all_passed = all_passed and passed

        status = "✓ PASS" if passed else "✗ FAIL"
        status_text = f"{status} {threshold.name:12} {metrics.percent_covered:6.2f}% "
        status_text += f"({metrics.lines_covered}/{metrics.lines_total} lines) "
        status_text += f"[required: {threshold.minimum_percent:.2f}%]"

        # Add baseline comparison if available and not in strict mode
        if not strict_mode and baseline_metrics is not None:
            diff = metrics.percent_covered - baseline_metrics.percent_covered
            sign = "+" if diff >= 0 else ""
            status_text += f" (baseline: {baseline_metrics.percent_covered:.2f}%, {sign}{diff:.2f}%)"

        results.append(status_text)

    # Check overall threshold
    overall_metrics = get_overall_coverage(coverage_data)

    # Pre-compute baseline metrics once if available
    baseline_overall = None
    if baseline_data is not None:
        baseline_overall = get_overall_coverage(baseline_data)

    if strict_mode:
        overall_passed = overall_metrics.percent_covered >= OVERALL_MINIMUM_PERCENT
    else:
        if baseline_overall is not None:
            overall_passed = check_regression(overall_metrics, baseline_overall)
        else:
            overall_passed = True

    all_passed = all_passed and overall_passed

    status = "✓ PASS" if overall_passed else "✗ FAIL"
    status_text = f"{status} {'Overall':12} {overall_metrics.percent_covered:6.2f}% "
    status_text += f"({overall_metrics.lines_covered}/{overall_metrics.lines_total} lines) "
    status_text += f"[required: {OVERALL_MINIMUM_PERCENT:.2f}%]"

    if not strict_mode and baseline_overall is not None:
        diff = overall_metrics.percent_covered - baseline_overall.percent_covered
        sign = "+" if diff >= 0 else ""
        status_text += f" (baseline: {baseline_overall.percent_covered:.2f}%, {sign}{diff:.2f}%)"

    results.append(status_text)

    # Print results
    mode_label = "Strict Mode (Absolute Thresholds)" if strict_mode else "Regression Detection"
    print("\n" + "=" * 80)
    print(f"Coverage Enforcement Results ({mode_label})")
    print("=" * 80)

    # Warn if no baseline found in regression mode
    if not strict_mode and baseline_data is None:
        print("⚠ No baseline found — regression detection skipped.")
        print("  Run with --save-baseline to establish one.\n")

    for result in results:
        print(result)
    print("=" * 80)

    # If tests failed, report and fail CI
    if tests_failed:
        print("⚠ WARNING: Tests failed — coverage results may be incomplete\n")
        return 1

    print()
    return 0 if all_passed else 1


def main() -> int:
    """Main entry point."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Enforce per-layer coverage thresholds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run tests and enforce regression detection (default)
  python3 scripts/enforce_coverage.py

  # Run tests and enforce strict absolute thresholds
  python3 scripts/enforce_coverage.py --strict

  # Use existing coverage.json and enforce regression detection
  python3 scripts/enforce_coverage.py --use-existing

  # Use existing coverage.json and enforce strict thresholds
  python3 scripts/enforce_coverage.py --use-existing --strict

  # Save current coverage as baseline for future regression detection
  python3 scripts/enforce_coverage.py --use-existing --save-baseline
        """,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enforce strict absolute thresholds (fail if below targets)",
    )
    parser.add_argument(
        "--use-existing",
        action="store_true",
        help="Use existing coverage.json instead of running tests",
    )
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="Save current coverage as baseline for regression detection",
    )
    parser.add_argument(
        "--baseline",
        default="coverage.baseline.json",
        help="Path to baseline coverage file (default: coverage.baseline.json)",
    )

    args = parser.parse_args()

    # Configure basic logging to capture exception details
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    try:
        # Run tests or use existing coverage
        if args.use_existing:
            coverage_json_path = "coverage.json"
            if not Path(coverage_json_path).exists():
                raise RuntimeError("coverage.json not found. Run tests first or remove --use-existing.")
            tests_failed = False
        else:
            coverage_json_path, tests_failed = run_coverage_tests()

        # Save baseline if requested
        if args.save_baseline:
            coverage_data = parse_coverage_json(coverage_json_path)
            save_baseline(coverage_data, args.baseline)
            print(f"✓ Baseline saved to {args.baseline}\n")

        # Enforce coverage
        return enforce_coverage(
            coverage_json_path,
            tests_failed,
            strict_mode=args.strict,
            baseline_path=args.baseline,
        )
    except Exception:
        logger.exception("Coverage enforcement failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
