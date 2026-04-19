"""Repair cycle CI pipeline integration utilities.

This module provides conversion functions and helper utilities for integrating
CI pipeline checks into the repair cycle framework. CI checks are routed through
ICIPipelineService rather than the agent executor path.
"""

from datetime import UTC, datetime

from codetoreum.domain.repair_cycle_types import RepairTestFailure, RepairTestResult, RepairTestType, RepairTestWarning
from codetoreum.ports.output.ci_pipeline_service import CICheckStatus, CIRunResult


def convert_ci_run_result_to_repair_test_result(
    ci_result: CIRunResult,
    iteration: int = 1,
) -> RepairTestResult:
    """Convert CIRunResult to RepairTestResult for repair cycle aggregation.

    Maps CI check failures to RepairTestFailure with file="ci" and test=<check_name>
    to enable systemic analysis integration without breaking existing aggregation.

    Args:
        ci_result: CIRunResult from ICIPipelineService.run_ci_checks()
        iteration: Iteration number (defaults to 1 for single CI check)

    Returns:
        RepairTestResult with CI results converted to repair cycle format

    Example:
        ci_result = await ci_service.run_ci_checks("proj-1", "/workspace")
        repair_result = convert_ci_run_result_to_repair_test_result(ci_result)
        # repair_result.failures contains RepairTestFailure(file="ci", test=<check_name>, ...)
    """
    # Extract failed checks from check_results
    failed_checks = [r for r in ci_result.check_results if r.status == CICheckStatus.FAILED]
    passed_checks = [r for r in ci_result.check_results if r.status == CICheckStatus.PASSED]

    # Convert CI failures to RepairTestFailure objects
    # Each failed check becomes a separate RepairTestFailure with file="ci"
    # and test=<check_name> to support systemic analysis grouping
    failures = tuple(
        RepairTestFailure(
            file="ci",
            test=check.name,
            message=check.conclusion or "Check failed",
        )
        for check in failed_checks
    )

    # Convert CI warnings to RepairTestWarning objects
    # Each warning string becomes a separate RepairTestWarning with file="ci"
    # to maintain consistency with failure conversion
    warnings = tuple(
        RepairTestWarning(
            file="ci",
            message=warning,
        )
        for warning in ci_result.warnings
    )

    return RepairTestResult(
        test_type=RepairTestType.CI,
        iteration=iteration,
        passed=len(passed_checks),
        failed=len(failed_checks),
        warnings=len(ci_result.warnings),
        failures=failures,
        warning_list=warnings,
        raw_output=ci_result.output,
        timestamp=datetime.now(UTC).isoformat(),
    )
