"""Repair cycle CI pipeline integration utilities.

This module provides conversion functions and helper utilities for integrating
CI pipeline checks into the repair cycle framework. CI checks are routed through
ICIPipelineService rather than the agent executor path.
"""

from datetime import UTC, datetime

from codetoreum.domain.repair_cycle_types import RepairTestFailure, RepairTestResult, RepairTestType
from codetoreum.ports.output.ci_pipeline_service import CIRunResult


def convert_ci_run_result_to_repair_test_result(
    ci_result: CIRunResult,
    iteration: int = 1,
) -> RepairTestResult:
    """Convert CIRunResult to RepairTestResult for repair cycle aggregation.

    Maps CI failures to RepairTestFailure with file="ci" and test=<check_name>
    to enable systemic analysis integration without breaking existing aggregation.

    Args:
        ci_result: CIRunResult from ICIPipelineService.run_ci_checks()
        iteration: Iteration number (defaults to 1 for single CI check)

    Returns:
        RepairTestResult with CI results converted to repair cycle format

    Example:
        ci_result = await ci_service.run_ci_checks("proj-1", "/workspace")
        repair_result = convert_ci_run_result_to_repair_test_result(ci_result)
        # repair_result.failures contains RepairTestFailure(file="ci", test=<failure>, ...)
    """
    # Convert CI failures to RepairTestFailure objects
    # Each failure string becomes a separate RepairTestFailure with file="ci"
    # and test=<failure_detail> to support systemic analysis grouping
    failures = tuple(
        RepairTestFailure(
            file="ci",
            test=f"check-{i}",
            message=failure,
        )
        for i, failure in enumerate(ci_result.failures)
    )

    return RepairTestResult(
        test_type=RepairTestType.CI,
        iteration=iteration,
        passed=ci_result.passed,
        failed=ci_result.failed,
        warnings=0,  # CI checks don't produce warnings in the current model
        failures=failures,
        warning_list=(),
        raw_output=ci_result.output,
        timestamp=datetime.now(UTC).isoformat(),
    )
