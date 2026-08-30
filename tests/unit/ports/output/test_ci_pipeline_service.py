"""Unit tests for CI pipeline service value objects and port interface.

Tests the contract boundary objects (CICheckResult, CIPipelineStatus, CIRunResult)
for validation, immutability, type enforcement, and cross-field consistency.
"""

import pytest

from codetoreum.ports.output.ci_pipeline_service import (
    CICheckResult,
    CICheckStatus,
    CIPipelineStatus,
    CIRunResult,
)


class TestCICheckResult:
    """Test CICheckResult value object validation."""

    def test_create_valid_check_result_minimal(self) -> None:
        """Test creating valid CICheckResult with minimal fields."""
        result = CICheckResult(
            name="unit-tests",
            status=CICheckStatus.PASSED,
        )

        assert result.name == "unit-tests"
        assert result.status == CICheckStatus.PASSED
        assert result.conclusion is None
        assert result.url is None

    def test_create_valid_check_result_complete(self) -> None:
        """Test creating valid CICheckResult with all fields."""
        result = CICheckResult(
            name="linting",
            status=CICheckStatus.FAILED,
            conclusion="failure",
            url="https://github.com/repo/runs/123",
        )

        assert result.name == "linting"
        assert result.status == CICheckStatus.FAILED
        assert result.conclusion == "failure"
        assert result.url == "https://github.com/repo/runs/123"

    def test_frozen_prevents_mutation(self) -> None:
        """Test that frozen dataclass prevents mutation."""
        result = CICheckResult(
            name="test-check",
            status=CICheckStatus.PASSED,
        )

        with pytest.raises(AttributeError):
            result.name = "modified"

    def test_rejects_empty_name(self) -> None:
        """Test that empty name is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CICheckResult(name="", status=CICheckStatus.PASSED)

        assert "name must be a non-empty string" in str(exc_info.value)

    def test_rejects_none_name(self) -> None:
        """Test that None name is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CICheckResult(name=None, status=CICheckStatus.PASSED)

        assert "name must be a non-empty string" in str(exc_info.value)

    def test_rejects_non_string_name(self) -> None:
        """Test that non-string name is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CICheckResult(name=123, status=CICheckStatus.PASSED)

        assert "name must be a non-empty string" in str(exc_info.value)

    def test_rejects_invalid_status(self) -> None:
        """Test that invalid status is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CICheckResult(name="test", status="invalid")

        assert "status must be a CICheckStatus instance" in str(exc_info.value)

    def test_rejects_non_string_conclusion(self) -> None:
        """Test that non-string conclusion is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CICheckResult(
                name="test",
                status=CICheckStatus.PASSED,
                conclusion=123,
            )

        assert "conclusion must be a string or None" in str(exc_info.value)

    def test_rejects_non_string_url(self) -> None:
        """Test that non-string URL is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CICheckResult(
                name="test",
                status=CICheckStatus.PASSED,
                url=123,
            )

        assert "url must be a string or None" in str(exc_info.value)

    def test_all_status_values_accepted(self) -> None:
        """Test that all CICheckStatus enum values are accepted."""
        for status in CICheckStatus:
            result = CICheckResult(name="test", status=status)
            assert result.status == status


class TestCIPipelineStatus:
    """Test CIPipelineStatus value object validation and cross-field consistency."""

    def test_create_valid_pipeline_status_minimal(self) -> None:
        """Test creating valid CIPipelineStatus with minimal fields."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PASSED),
            CICheckResult(name="check-2", status=CICheckStatus.PASSED),
        ]

        status = CIPipelineStatus(
            pr_id="pr-123",
            status=CICheckStatus.PASSED,
            check_results=check_results,
            total_checks=2,
            passed=2,
            failed=0,
            pending=0,
        )

        assert status.pr_id == "pr-123"
        assert status.status == CICheckStatus.PASSED
        assert len(status.check_results) == 2
        assert status.pipeline_url == ""

    def test_create_valid_pipeline_status_complete(self) -> None:
        """Test creating valid CIPipelineStatus with all fields."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.FAILED),
        ]

        status = CIPipelineStatus(
            pr_id="pr-456",
            status=CICheckStatus.FAILED,
            check_results=check_results,
            total_checks=1,
            passed=0,
            failed=1,
            pending=0,
            pipeline_url="https://github.com/repo/runs/456",
        )

        assert status.pr_id == "pr-456"
        assert status.status == CICheckStatus.FAILED
        assert status.pipeline_url == "https://github.com/repo/runs/456"

    def test_coerces_list_to_tuple_for_immutability(self) -> None:
        """Test that list check_results are coerced to tuple."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PASSED),
        ]

        status = CIPipelineStatus(
            pr_id="pr-123",
            status=CICheckStatus.PASSED,
            check_results=check_results,  # Pass list, not tuple
            total_checks=1,
            passed=1,
            failed=0,
            pending=0,
        )

        assert isinstance(status.check_results, tuple)
        assert len(status.check_results) == 1

    def test_frozen_prevents_mutation(self) -> None:
        """Test that frozen dataclass prevents mutation."""
        status = CIPipelineStatus(
            pr_id="pr-123",
            status=CICheckStatus.PASSED,
            check_results=(),
            total_checks=0,
            passed=0,
            failed=0,
            pending=0,
        )

        with pytest.raises(AttributeError):
            status.pr_id = "pr-999"

    def test_rejects_empty_pr_id(self) -> None:
        """Test that empty pr_id is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="",
                status=CICheckStatus.PASSED,
                check_results=(),
                total_checks=0,
                passed=0,
                failed=0,
                pending=0,
            )

        assert "pr_id must be a non-empty string" in str(exc_info.value)

    def test_rejects_invalid_status(self) -> None:
        """Test that invalid status is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status="invalid",
                check_results=(),
                total_checks=0,
                passed=0,
                failed=0,
                pending=0,
            )

        assert "status must be a CICheckStatus instance" in str(exc_info.value)

    def test_rejects_non_tuple_check_results(self) -> None:
        """Test that non-sequence check_results are rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.PASSED,
                check_results="invalid",
                total_checks=0,
                passed=0,
                failed=0,
                pending=0,
            )

        assert "check_results must be a list or tuple" in str(exc_info.value)

    def test_rejects_non_checkresult_in_results(self) -> None:
        """Test that non-CICheckResult elements in check_results are rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.PASSED,
                check_results=["not-a-check-result"],
                total_checks=1,
                passed=0,
                failed=0,
                pending=0,
            )

        assert "all check_results must be CICheckResult instances" in str(exc_info.value)

    def test_rejects_negative_total_checks(self) -> None:
        """Test that negative total_checks is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.PASSED,
                check_results=(),
                total_checks=-1,
                passed=0,
                failed=0,
                pending=0,
            )

        assert "total_checks must be a non-negative integer" in str(exc_info.value)

    def test_rejects_negative_passed(self) -> None:
        """Test that negative passed count is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.PASSED,
                check_results=(),
                total_checks=0,
                passed=-1,
                failed=0,
                pending=0,
            )

        assert "passed must be a non-negative integer" in str(exc_info.value)

    def test_rejects_negative_failed(self) -> None:
        """Test that negative failed count is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.PASSED,
                check_results=(),
                total_checks=0,
                passed=0,
                failed=-1,
                pending=0,
            )

        assert "failed must be a non-negative integer" in str(exc_info.value)

    def test_rejects_negative_pending(self) -> None:
        """Test that negative pending count is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.PASSED,
                check_results=(),
                total_checks=0,
                passed=0,
                failed=0,
                pending=-1,
            )

        assert "pending must be a non-negative integer" in str(exc_info.value)

    def test_rejects_non_string_pipeline_url(self) -> None:
        """Test that non-string pipeline_url is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.PASSED,
                check_results=(),
                total_checks=0,
                passed=0,
                failed=0,
                pending=0,
                pipeline_url=123,
            )

        assert "pipeline_url must be a string" in str(exc_info.value)

    def test_cross_field_consistency_total_equals_sum(self) -> None:
        """Test that total_checks equals sum of status counts."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PASSED),
            CICheckResult(name="check-2", status=CICheckStatus.PASSED),
            CICheckResult(name="check-3", status=CICheckStatus.FAILED),
        ]

        # This should fail: total_checks=5 but sum of counts = 3
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.FAILED,
                check_results=check_results,
                total_checks=5,  # Wrong: should be 3
                passed=2,
                failed=1,
                pending=0,
            )

        assert "total_checks" in str(exc_info.value) and "sum of status counts" in str(exc_info.value)

    def test_cross_field_consistency_passed_count_matches_results(self) -> None:
        """Test that passed count matches number of passed results."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PASSED),
            CICheckResult(name="check-2", status=CICheckStatus.PASSED),
            CICheckResult(name="check-3", status=CICheckStatus.FAILED),
        ]

        # This should fail: passed=1 but 2 results are passed
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.FAILED,
                check_results=check_results,
                total_checks=3,
                passed=1,  # Wrong: should be 2
                failed=1,
                pending=1,  # Also wrong, but the passed check happens first
            )

        error_msg = str(exc_info.value)
        assert "passed count" in error_msg and "does not match check_results" in error_msg

    def test_cross_field_consistency_failed_count_matches_results(self) -> None:
        """Test that failed count matches number of failed results."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PASSED),
            CICheckResult(name="check-2", status=CICheckStatus.FAILED),
            CICheckResult(name="check-3", status=CICheckStatus.FAILED),
        ]

        # This should fail: failed=1 but 2 results are failed
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.FAILED,
                check_results=check_results,
                total_checks=3,
                passed=1,
                failed=1,  # Wrong: should be 2
                pending=1,  # Adjust to make total_checks=3
            )

        error_msg = str(exc_info.value)
        assert "failed count" in error_msg and "does not match check_results" in error_msg

    def test_cross_field_consistency_pending_count_matches_results(self) -> None:
        """Test that pending count matches number of pending/running results."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PASSED),
            CICheckResult(name="check-2", status=CICheckStatus.PENDING),
            CICheckResult(name="check-3", status=CICheckStatus.RUNNING),
        ]

        # This should fail: pending=1 but 2 results are pending/running
        # The error will be caught by either the total_checks or pending_count validation
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.PENDING,
                check_results=check_results,
                total_checks=2,  # Only counts passed + pending
                passed=1,
                failed=0,
                pending=1,  # Mismatch: should be 2
            )

        error_msg = str(exc_info.value)
        # The validation will catch either the pending mismatch or the total_checks mismatch
        assert "pending" in error_msg or "total_checks" in error_msg

    def test_cross_field_consistency_empty_check_results_allowed(self) -> None:
        """Test that empty check_results with zero counts is allowed."""
        status = CIPipelineStatus(
            pr_id="pr-123",
            status=CICheckStatus.PENDING,
            check_results=(),
            total_checks=0,
            passed=0,
            failed=0,
            pending=0,
        )

        assert status.total_checks == 0
        assert len(status.check_results) == 0

    def test_cross_field_consistency_with_skipped_checks(self) -> None:
        """Test that skipped checks are counted in total_checks but not in passed/failed/pending."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PASSED),
            CICheckResult(name="check-2", status=CICheckStatus.SKIPPED),
        ]

        status = CIPipelineStatus(
            pr_id="pr-123",
            status=CICheckStatus.PASSED,
            check_results=check_results,
            total_checks=2,  # Includes skipped check
            passed=1,
            failed=0,
            pending=0,  # Skipped checks don't count as pending
        )

        assert status.total_checks == 2
        assert status.passed == 1
        assert len(status.check_results) == 2

    def test_cross_field_consistency_internally_contradictory_data_rejected(self) -> None:
        """Test that internally contradictory data (all counts zero but total non-zero) is rejected."""
        # This was the specific example from the issue: total_checks=5, passed=0, failed=0, pending=0
        with pytest.raises(ValueError) as exc_info:
            CIPipelineStatus(
                pr_id="pr-123",
                status=CICheckStatus.PENDING,
                check_results=(),
                total_checks=5,
                passed=0,
                failed=0,
                pending=0,
            )

        assert "total_checks" in str(exc_info.value) and "sum of status counts" in str(exc_info.value)


class TestCIRunResult:
    """Test CIRunResult value object validation and cross-field consistency."""

    def test_create_valid_run_result_minimal(self) -> None:
        """Test creating valid CIRunResult with minimal fields."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PASSED),
        ]

        result = CIRunResult(
            passed=True,
            failed=0,
            check_results=check_results,
        )

        assert result.passed is True
        assert result.failed == 0
        assert len(result.check_results) == 1
        assert result.failures == ()
        assert result.warnings == ()
        assert result.output == ""

    def test_create_valid_run_result_complete(self) -> None:
        """Test creating valid CIRunResult with all fields."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.FAILED),
        ]

        result = CIRunResult(
            passed=False,
            failed=1,
            check_results=check_results,
            failures=("lint: error", "tests: failed"),
            warnings=("deprecation: old API", "performance: slow test"),
            output="Full CI output logs...",
        )

        assert result.passed is False
        assert result.failed == 1
        assert result.failures == ("lint: error", "tests: failed")
        assert result.warnings == ("deprecation: old API", "performance: slow test")
        assert result.output == "Full CI output logs..."

    def test_coerces_list_to_tuple_for_immutability(self) -> None:
        """Test that list fields are coerced to tuple."""
        check_results = [CICheckResult(name="check-1", status=CICheckStatus.PASSED)]
        failures = ["error-1", "error-2"]
        warnings = ["warning-1"]

        result = CIRunResult(
            passed=True,
            failed=0,
            check_results=check_results,  # Pass list, not tuple
            failures=failures,  # Pass list, not tuple
            warnings=warnings,  # Pass list, not tuple
        )

        assert isinstance(result.check_results, tuple)
        assert isinstance(result.failures, tuple)
        assert isinstance(result.warnings, tuple)

    def test_frozen_prevents_mutation(self) -> None:
        """Test that frozen dataclass prevents mutation."""
        result = CIRunResult(
            passed=True,
            failed=0,
            check_results=(),
        )

        with pytest.raises(AttributeError):
            result.passed = False

    def test_rejects_non_bool_passed(self) -> None:
        """Test that non-boolean passed value is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=1,
                failed=0,
                check_results=(),
            )

        assert "passed must be a boolean" in str(exc_info.value)

    def test_rejects_negative_failed(self) -> None:
        """Test that negative failed count is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=False,
                failed=-1,
                check_results=(),
            )

        assert "failed must be a non-negative integer" in str(exc_info.value)

    def test_rejects_non_tuple_check_results(self) -> None:
        """Test that non-sequence check_results are rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=True,
                failed=0,
                check_results="invalid",
            )

        assert "check_results must be a list or tuple" in str(exc_info.value)

    def test_rejects_non_checkresult_in_results(self) -> None:
        """Test that non-CICheckResult elements are rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=True,
                failed=0,
                check_results=["not-a-check-result"],
            )

        assert "all check_results must be CICheckResult instances" in str(exc_info.value)

    def test_rejects_non_tuple_failures(self) -> None:
        """Test that non-sequence failures are rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=True,
                failed=0,
                check_results=(),
                failures="invalid",
            )

        assert "failures must be a list or tuple" in str(exc_info.value)

    def test_rejects_non_string_in_failures(self) -> None:
        """Test that non-string failure elements are rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=True,
                failed=0,
                check_results=(),
                failures=[123],
            )

        assert "all failures must be strings" in str(exc_info.value)

    def test_rejects_non_tuple_warnings(self) -> None:
        """Test that non-sequence warnings are rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=True,
                failed=0,
                check_results=(),
                warnings="invalid",
            )

        assert "warnings must be a list or tuple" in str(exc_info.value)

    def test_rejects_non_string_in_warnings(self) -> None:
        """Test that non-string warning elements are rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=True,
                failed=0,
                check_results=(),
                warnings=[123],
            )

        assert "all warnings must be strings" in str(exc_info.value)

    def test_rejects_non_string_output(self) -> None:
        """Test that non-string output is rejected."""
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=True,
                failed=0,
                check_results=(),
                output=123,
            )

        assert "output must be a string" in str(exc_info.value)

    def test_cross_field_consistency_passed_bool_contradicts_failed(self) -> None:
        """Test that passed boolean is consistent with failed count."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.FAILED),
        ]

        # This should fail: passed=True but failed=1 (should be 0)
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=True,  # Contradiction: passed but failed > 0
                failed=1,
                check_results=check_results,
            )

        error_msg = str(exc_info.value)
        assert "passed is True but failed count is" in error_msg

    def test_cross_field_consistency_failed_count_matches_results(self) -> None:
        """Test that failed count matches number of failed results."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PASSED),
            CICheckResult(name="check-2", status=CICheckStatus.FAILED),
            CICheckResult(name="check-3", status=CICheckStatus.FAILED),
        ]

        # This should fail: failed=1 but 2 results are failed
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=False,  # Correct: failed=1 at least
                failed=1,  # Wrong: should be 2
                check_results=check_results,
            )

        error_msg = str(exc_info.value)
        assert "failed count" in error_msg and "does not match check_results" in error_msg

    def test_cross_field_consistency_passes_when_values_match(self) -> None:
        """Test that cross-field consistency check passes when values match."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PASSED),
            CICheckResult(name="check-2", status=CICheckStatus.PASSED),
            CICheckResult(name="check-3", status=CICheckStatus.FAILED),
        ]

        result = CIRunResult(
            passed=False,
            failed=1,
            check_results=check_results,
        )

        assert result.passed is False
        assert result.failed == 1

    def test_cross_field_consistency_empty_results_allowed(self) -> None:
        """Test that empty check_results with passed=True and failed=0 is allowed."""
        result = CIRunResult(
            passed=True,
            failed=0,
            check_results=(),
        )

        assert result.passed is True
        assert result.failed == 0
        assert len(result.check_results) == 0

    def test_cross_field_consistency_other_checks_do_not_count(self) -> None:
        """Test that SKIPPED checks don't prevent passed=True, but PENDING/RUNNING do."""
        # SKIPPED checks are OK with passed=True
        result = CIRunResult(
            passed=True,
            failed=0,
            check_results=[
                CICheckResult(name="check-1", status=CICheckStatus.SKIPPED),
                CICheckResult(name="check-2", status=CICheckStatus.SKIPPED),
            ],
        )

        assert result.passed is True
        assert result.failed == 0

    def test_cross_field_consistency_passed_true_rejects_pending_checks(self) -> None:
        """Test that passed=True with pending/running checks is rejected."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PENDING),
            CICheckResult(name="check-2", status=CICheckStatus.RUNNING),
        ]

        # Should fail: passed=True but checks are still pending/running
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=True,
                failed=0,
                check_results=check_results,
            )

        error_msg = str(exc_info.value)
        assert "passed is True but" in error_msg and "still pending/running" in error_msg

    def test_cross_field_consistency_passed_false_requires_failed_gt_zero(self) -> None:
        """Test that passed=False requires failed > 0."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PASSED),
        ]

        # This should fail: passed=False but failed=0 (no checks failed)
        with pytest.raises(ValueError) as exc_info:
            CIRunResult(
                passed=False,  # Contradiction: not passed but failed=0
                failed=0,
                check_results=check_results,
            )

        error_msg = str(exc_info.value)
        assert "passed is False but failed count is 0" in error_msg

    def test_cross_field_consistency_passed_false_allowed_with_pending_checks(self) -> None:
        """Test that passed=False with failed=0 is allowed when pending/running checks exist."""
        check_results = [
            CICheckResult(name="check-1", status=CICheckStatus.PENDING),
            CICheckResult(name="check-2", status=CICheckStatus.RUNNING),
        ]

        result = CIRunResult(
            passed=False,  # Not passed because checks are still pending/running
            failed=0,  # No failures yet, checks still running
            check_results=check_results,
        )

        assert result.passed is False
        assert result.failed == 0
        assert len(result.check_results) == 2
