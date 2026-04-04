"""Unit tests for repair cycle events."""

import pytest

from codetoreum.domain.events import (
    EnvironmentRebuildCompletedEvent,
    EnvironmentRebuildExhaustedEvent,
    EnvironmentRebuildStartedEvent,
    EnvironmentVerificationCompletedEvent,
    EnvironmentVerificationStartedEvent,
    RepairCycleCompletedEvent,
    RepairCycleFastFailEvent,
    RepairCycleFileFixCompletedEvent,
    RepairCycleFileFixStartedEvent,
    RepairCycleFixCycleStartedEvent,
    RepairCycleStartedEvent,
    RepairCycleTestCycleCompletedEvent,
    RepairCycleTestExecutionCompletedEvent,
    RepairCycleTestExecutionStartedEvent,
    RepairCycleWarningReviewCompletedEvent,
    RepairCycleWarningReviewStartedEvent,
    SystemicAnalysisCompletedEvent,
    SystemicAnalysisStartedEvent,
    SystemicFixCompletedEvent,
    SystemicFixStartedEvent,
    now_iso,
)
from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    FailureClassification,
    RebuildResult,
    RepairTestFailure,
    RepairTestResult,
    RepairTestType,
    RepairTestWarning,
    VerificationResult,
)

# For immutability tests
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    FrozenInstanceError = AttributeError  # type: ignore


class TestRepairCycleStartedEvent:
    """Test RepairCycleStartedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid repair cycle started event."""
        timestamp = now_iso()
        event = RepairCycleStartedEvent(
            type="repair_cycle.started",
            timestamp=timestamp,
            source="repair_cycle",
            stage_name="fix_failures",
            test_types=(RepairTestType.UNIT, RepairTestType.INTEGRATION),
            workflow_run_id="run-123",
        )

        assert event.stage_name == "fix_failures"
        assert event.test_types == (RepairTestType.UNIT, RepairTestType.INTEGRATION)
        assert event.workflow_run_id == "run-123"

    def test_missing_stage_name(self):
        """Test that stage_name is required."""
        with pytest.raises(ValueError, match="stage_name"):
            RepairCycleStartedEvent(
                type="repair_cycle.started",
                timestamp=now_iso(),
                source="repair_cycle",
                stage_name="",
                test_types=(RepairTestType.UNIT,),
                workflow_run_id="run-123",
            )

    def test_empty_test_types(self):
        """Test that test_types must not be empty."""
        with pytest.raises(ValueError, match="test_types"):
            RepairCycleStartedEvent(
                type="repair_cycle.started",
                timestamp=now_iso(),
                source="repair_cycle",
                stage_name="fix_failures",
                test_types=(),
                workflow_run_id="run-123",
            )

    def test_missing_workflow_run_id(self):
        """Test that workflow_run_id is required."""
        with pytest.raises(ValueError, match="workflow_run_id"):
            RepairCycleStartedEvent(
                type="repair_cycle.started",
                timestamp=now_iso(),
                source="repair_cycle",
                stage_name="fix_failures",
                test_types=(RepairTestType.UNIT,),
                workflow_run_id="",
            )

    def test_serialization(self):
        """Test RepairCycleStartedEvent serialization."""
        timestamp = now_iso()
        event = RepairCycleStartedEvent(
            type="repair_cycle.started",
            timestamp=timestamp,
            source="repair_cycle",
            stage_name="fix_failures",
            test_types=(RepairTestType.UNIT, RepairTestType.E2E),
            workflow_run_id="run-123",
        )
        d = event.to_dict()
        assert d["stage_name"] == "fix_failures"
        assert d["test_types"] == ["UNIT", "E2E"]
        assert d["workflow_run_id"] == "run-123"

    def test_deserialization(self):
        """Test RepairCycleStartedEvent deserialization."""
        timestamp = now_iso()
        d = {
            "type": "repair_cycle.started",
            "timestamp": timestamp,
            "source": "repair_cycle",
            "stage_name": "fix_failures",
            "test_types": ["UNIT", "INTEGRATION"],
            "workflow_run_id": "run-123",
        }
        event = RepairCycleStartedEvent.from_dict(d)
        assert event.stage_name == "fix_failures"
        assert event.test_types == (RepairTestType.UNIT, RepairTestType.INTEGRATION)
        assert event.workflow_run_id == "run-123"

    def test_immutability(self):
        """Test that RepairCycleStartedEvent is immutable."""
        event = RepairCycleStartedEvent(
            type="repair_cycle.started",
            timestamp=now_iso(),
            source="repair_cycle",
            stage_name="fix_failures",
            test_types=(RepairTestType.UNIT,),
            workflow_run_id="run-123",
        )

        with pytest.raises(FrozenInstanceError):
            event.stage_name = "fix_warnings"  # type: ignore


class TestRepairCycleTestExecutionStartedEvent:
    """Test RepairCycleTestExecutionStartedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid test execution started event."""
        timestamp = now_iso()
        event = RepairCycleTestExecutionStartedEvent(
            type="repair_cycle.test_execution_started",
            timestamp=timestamp,
            source="repair_cycle",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            test_cycle_iteration=1,
            max_test_cycle_iterations=5,
            timeout=900,
            workflow_run_id="run-123",
        )

        assert event.test_type == RepairTestType.UNIT
        assert event.test_type_index == 1
        assert event.test_cycle_iteration == 1
        assert event.timeout == 900

    def test_invalid_test_type_index(self):
        """Test that test_type_index must be >= 1."""
        with pytest.raises(ValueError, match="test_type_index"):
            RepairCycleTestExecutionStartedEvent(
                type="repair_cycle.test_execution_started",
                timestamp=now_iso(),
                source="repair_cycle",
                test_type=RepairTestType.UNIT,
                test_type_index=0,  # Invalid
                test_cycle_iteration=1,
                max_test_cycle_iterations=5,
                timeout=900,
                workflow_run_id="run-123",
            )

    def test_invalid_timeout(self):
        """Test that timeout must be > 0."""
        with pytest.raises(ValueError, match="timeout"):
            RepairCycleTestExecutionStartedEvent(
                type="repair_cycle.test_execution_started",
                timestamp=now_iso(),
                source="repair_cycle",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=1,
                max_test_cycle_iterations=5,
                timeout=0,  # Invalid
                workflow_run_id="run-123",
            )


class TestRepairCycleTestExecutionCompletedEvent:
    """Test RepairCycleTestExecutionCompletedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid test execution completed event."""
        failure1 = RepairTestFailure(
            file="test_auth.py",
            test="test_login",
            message="AssertionError: expected True",
        )
        failure2 = RepairTestFailure(
            file="test_auth.py",
            test="test_logout",
            message="AssertionError: expected False",
        )
        timestamp = now_iso()
        event = RepairCycleTestExecutionCompletedEvent(
            type="repair_cycle.test_execution_completed",
            timestamp=timestamp,
            source="repair_cycle",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            test_cycle_iteration=1,
            passed=5,
            failed=2,
            warnings=1,
            has_failures=True,
            failures=(failure1, failure2),
            agent_name="test-executor",
            workflow_run_id="run-123",
        )

        assert event.passed == 5
        assert event.failed == 2
        assert event.has_failures is True
        assert len(event.failures) == 2

    def test_serialization_with_failures(self):
        """Test serialization with failure details."""
        failure = RepairTestFailure(
            file="test_service.py",
            test="test_create_user",
            message="Timeout",
        )
        timestamp = now_iso()
        event = RepairCycleTestExecutionCompletedEvent(
            type="repair_cycle.test_execution_completed",
            timestamp=timestamp,
            source="repair_cycle",
            test_type=RepairTestType.INTEGRATION,
            test_type_index=2,
            test_cycle_iteration=1,
            passed=10,
            failed=1,
            warnings=0,
            has_failures=True,
            failures=(failure,),
            agent_name="test-executor",
            workflow_run_id="run-123",
        )

        d = event.to_dict()
        assert d["failed"] == 1
        assert len(d["failures"]) == 1
        assert d["failures"][0]["file"] == "test_service.py"

    def test_deserialization_with_failures(self):
        """Test deserialization with failure details."""
        timestamp = now_iso()
        d = {
            "type": "repair_cycle.test_execution_completed",
            "timestamp": timestamp,
            "source": "repair_cycle",
            "test_type": "UNIT",
            "test_type_index": 1,
            "test_cycle_iteration": 1,
            "passed": 5,
            "failed": 2,
            "warnings": 1,
            "has_failures": True,
            "failures": [
                {
                    "file": "test_auth.py",
                    "test": "test_login",
                    "message": "AssertionError",
                },
                {
                    "file": "test_auth.py",
                    "test": "test_logout",
                    "message": "KeyError",
                },
            ],
            "agent_name": "test-executor",
            "workflow_run_id": "run-123",
        }

        event = RepairCycleTestExecutionCompletedEvent.from_dict(d)
        assert event.failed == 2
        assert len(event.failures) == 2
        assert event.failures[0].file == "test_auth.py"

    def test_empty_agent_name(self):
        """Test that agent_name is required."""
        failure = RepairTestFailure(
            file="test_auth.py",
            test="test_login",
            message="AssertionError: expected True",
        )
        with pytest.raises(ValueError, match="agent_name"):
            RepairCycleTestExecutionCompletedEvent(
                type="repair_cycle.test_execution_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=1,
                passed=5,
                failed=1,
                warnings=0,
                has_failures=True,
                failures=(failure,),
                agent_name="",  # Invalid
                workflow_run_id="run-123",
            )


class TestRepairCycleFixCycleStartedEvent:
    """Test RepairCycleFixCycleStartedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid fix cycle started event."""
        timestamp = now_iso()
        event = RepairCycleFixCycleStartedEvent(
            type="repair_cycle.fix_cycle_started",
            timestamp=timestamp,
            source="repair_cycle",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            test_cycle_iteration=1,
            file_count=3,
            total_failures=5,
            workflow_run_id="run-123",
        )

        assert event.file_count == 3
        assert event.total_failures == 5

    def test_invalid_file_count(self):
        """Test that file_count must be >= 1."""
        with pytest.raises(ValueError, match="file_count"):
            RepairCycleFixCycleStartedEvent(
                type="repair_cycle.fix_cycle_started",
                timestamp=now_iso(),
                source="repair_cycle",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=1,
                file_count=0,  # Invalid
                total_failures=1,
                workflow_run_id="run-123",
            )


class TestRepairCycleFileFixStartedEvent:
    """Test RepairCycleFileFixStartedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid file fix started event."""
        timestamp = now_iso()
        event = RepairCycleFileFixStartedEvent(
            type="repair_cycle.file_fix_started",
            timestamp=timestamp,
            source="repair_cycle",
            test_file="auth.py",
            failure_count=2,
            test_type=RepairTestType.UNIT,
            agent_name="code-fixer",
            workflow_run_id="run-123",
        )

        assert event.test_file == "auth.py"
        assert event.failure_count == 2

    def test_missing_test_file(self):
        """Test that test_file is required."""
        with pytest.raises(ValueError, match="test_file"):
            RepairCycleFileFixStartedEvent(
                type="repair_cycle.file_fix_started",
                timestamp=now_iso(),
                source="repair_cycle",
                test_file="",
                failure_count=1,
                test_type=RepairTestType.UNIT,
                workflow_run_id="run-123",
            )

    def test_empty_agent_name(self):
        """Test that agent_name is required."""
        with pytest.raises(ValueError, match="agent_name"):
            RepairCycleFileFixStartedEvent(
                type="repair_cycle.file_fix_started",
                timestamp=now_iso(),
                source="repair_cycle",
                test_file="auth.py",
                failure_count=2,
                test_type=RepairTestType.UNIT,
                agent_name="",  # Invalid
                workflow_run_id="run-123",
            )


class TestRepairCycleFileFixCompletedEvent:
    """Test RepairCycleFileFixCompletedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid file fix completed event."""
        timestamp = now_iso()
        event = RepairCycleFileFixCompletedEvent(
            type="repair_cycle.file_fix_completed",
            timestamp=timestamp,
            source="repair_cycle",
            test_file="auth.py",
            failure_count=2,
            test_type=RepairTestType.UNIT,
            success=True,
            agent_name="code-fixer",
            workflow_run_id="run-123",
        )

        assert event.test_file == "auth.py"
        assert event.success is True

    def test_empty_agent_name(self):
        """Test that agent_name is required."""
        with pytest.raises(ValueError, match="agent_name"):
            RepairCycleFileFixCompletedEvent(
                type="repair_cycle.file_fix_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                test_file="auth.py",
                failure_count=2,
                test_type=RepairTestType.UNIT,
                success=True,
                agent_name="",  # Invalid
                workflow_run_id="run-123",
            )


class TestRepairCycleWarningReviewStartedEvent:
    """Test RepairCycleWarningReviewStartedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid warning review started event."""
        warning = RepairTestWarning(
            file="auth.py",
            message="DeprecationWarning: use new_function instead",
        )
        timestamp = now_iso()
        event = RepairCycleWarningReviewStartedEvent(
            type="repair_cycle.warning_review_started",
            timestamp=timestamp,
            source="repair_cycle",
            source_file="auth.py",
            warning_count=1,
            test_type=RepairTestType.UNIT,
            warnings=(warning,),
            agent_name="code-reviewer",
            workflow_run_id="test-run-123",
        )

        assert event.source_file == "auth.py"
        assert event.warning_count == 1
        assert len(event.warnings) == 1

    def test_missing_source_file(self):
        """Test that source_file is required."""
        with pytest.raises(ValueError, match="source_file"):
            RepairCycleWarningReviewStartedEvent(
                type="repair_cycle.warning_review_started",
                timestamp=now_iso(),
                source="repair_cycle",
                source_file="",
                warning_count=1,
                test_type=RepairTestType.UNIT,
                warnings=(),
            )

    def test_empty_agent_name(self):
        """Test that agent_name is required."""
        warning = RepairTestWarning(
            file="auth.py",
            message="DeprecationWarning: use new_function instead",
        )
        with pytest.raises(ValueError, match="agent_name"):
            RepairCycleWarningReviewStartedEvent(
                type="repair_cycle.warning_review_started",
                timestamp=now_iso(),
                source="repair_cycle",
                source_file="auth.py",
                warning_count=1,
                test_type=RepairTestType.UNIT,
                warnings=(warning,),
                agent_name="",  # Invalid
                workflow_run_id="test-run-123",
            )

    def test_serialization_with_warnings(self):
        """Test serialization with warning details."""
        warning = RepairTestWarning(
            file="service.py",
            message="PendingDeprecationWarning: foo",
        )
        timestamp = now_iso()
        event = RepairCycleWarningReviewStartedEvent(
            type="repair_cycle.warning_review_started",
            timestamp=timestamp,
            source="repair_cycle",
            source_file="service.py",
            warning_count=1,
            test_type=RepairTestType.UNIT,
            warnings=(warning,),
            agent_name="code-reviewer",
            workflow_run_id="test-run-123",
        )

        d = event.to_dict()
        assert len(d["warnings"]) == 1
        assert d["warnings"][0]["file"] == "service.py"


class TestRepairCycleWarningReviewCompletedEvent:
    """Test RepairCycleWarningReviewCompletedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid warning review completed event."""
        timestamp = now_iso()
        event = RepairCycleWarningReviewCompletedEvent(
            type="repair_cycle.warning_review_completed",
            timestamp=timestamp,
            source="repair_cycle",
            source_file="auth.py",
            warning_count=1,
            test_type=RepairTestType.UNIT,
            success=True,
            agent_name="code-reviewer",
            workflow_run_id="test-run-123",
        )

        assert event.source_file == "auth.py"
        assert event.success is True

    def test_empty_agent_name(self):
        """Test that agent_name is required."""
        with pytest.raises(ValueError, match="agent_name"):
            RepairCycleWarningReviewCompletedEvent(
                type="repair_cycle.warning_review_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                source_file="auth.py",
                warning_count=1,
                test_type=RepairTestType.UNIT,
                success=True,
                agent_name="",  # Invalid
                workflow_run_id="test-run-123",
            )


class TestRepairCycleTestCycleCompletedEvent:
    """Test RepairCycleTestCycleCompletedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid test cycle completed event."""
        timestamp = now_iso()
        event = RepairCycleTestCycleCompletedEvent(
            type="repair_cycle.test_cycle_completed",
            timestamp=timestamp,
            source="repair_cycle",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            passed=True,
            test_cycle_iterations=2,
            files_fixed=3,
            warnings_reviewed=2,
            error=None,
            duration_seconds=45.5,
            workflow_run_id="run-123",
        )

        assert event.passed is True
        assert event.files_fixed == 3
        assert event.duration_seconds == 45.5

    def test_with_error(self):
        """Test test cycle completed with error."""
        timestamp = now_iso()
        event = RepairCycleTestCycleCompletedEvent(
            type="repair_cycle.test_cycle_completed",
            timestamp=timestamp,
            source="repair_cycle",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            passed=False,
            test_cycle_iterations=5,
            files_fixed=0,
            warnings_reviewed=0,
            error="max_iterations_exceeded",
            duration_seconds=120.0,
            workflow_run_id="run-123",
        )

        assert event.passed is False
        assert event.error == "max_iterations_exceeded"


class TestRepairCycleFastFailEvent:
    """Test RepairCycleFastFailEvent."""

    def test_create_valid_event(self):
        """Test creating a valid fast fail event."""
        timestamp = now_iso()
        event = RepairCycleFastFailEvent(
            type="repair_cycle.fast_fail",
            timestamp=timestamp,
            source="repair_cycle",
            test_type=RepairTestType.UNIT,
            reason="max_agent_calls_exceeded",
            workflow_run_id="test-run-123",
        )

        assert event.test_type == RepairTestType.UNIT
        assert event.reason == "max_agent_calls_exceeded"

    def test_missing_reason(self):
        """Test that reason is required."""
        with pytest.raises(ValueError, match="reason"):
            RepairCycleFastFailEvent(
                type="repair_cycle.fast_fail",
                timestamp=now_iso(),
                source="repair_cycle",
                test_type=RepairTestType.UNIT,
                reason="",
            )


class TestRepairCycleCompletedEvent:
    """Test RepairCycleCompletedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid repair cycle completed event."""
        final_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=5,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All tests passed",
            timestamp=now_iso(),
        )
        result = CycleResult(
            test_type=RepairTestType.UNIT,
            passed=True,
            iterations=1,
            final_result=final_result,
            error=None,
            files_fixed=2,
            warnings_reviewed=0,
            duration_seconds=30.0,
        )
        timestamp = now_iso()
        event = RepairCycleCompletedEvent(
            type="repair_cycle.completed",
            timestamp=timestamp,
            source="repair_cycle",
            overall_success=True,
            test_results=(result,),
            total_agent_calls=5,
            duration_seconds=30.0,
            workflow_run_id="run-123",
        )

        assert event.overall_success is True
        assert event.total_agent_calls == 5
        assert len(event.test_results) == 1

    def test_empty_test_results(self):
        """Test that test_results must not be empty."""
        with pytest.raises(ValueError, match="test_results"):
            RepairCycleCompletedEvent(
                type="repair_cycle.completed",
                timestamp=now_iso(),
                source="repair_cycle",
                overall_success=False,
                test_results=(),
                total_agent_calls=0,
                duration_seconds=0.0,
                workflow_run_id="run-123",
            )

    def test_serialization_with_test_results(self):
        """Test serialization with test results."""
        final_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=2,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All tests passed after fixes",
            timestamp=now_iso(),
        )
        result = CycleResult(
            test_type=RepairTestType.UNIT,
            passed=True,
            iterations=2,
            final_result=final_result,
            error=None,
            files_fixed=1,
            warnings_reviewed=0,
            duration_seconds=60.0,
        )
        timestamp = now_iso()
        event = RepairCycleCompletedEvent(
            type="repair_cycle.completed",
            timestamp=timestamp,
            source="repair_cycle",
            overall_success=True,
            test_results=(result,),
            total_agent_calls=3,
            duration_seconds=60.0,
            workflow_run_id="run-123",
        )

        d = event.to_dict()
        assert d["overall_success"] is True
        assert d["total_agent_calls"] == 3
        assert len(d["test_results"]) == 1


class TestRepairCycleEventsImmutability:
    """Test immutability of repair cycle events."""

    def test_test_execution_started_is_frozen(self):
        """Test that test execution started event is immutable."""
        event = RepairCycleTestExecutionStartedEvent(
            type="repair_cycle.test_execution_started",
            timestamp=now_iso(),
            source="repair_cycle",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            test_cycle_iteration=1,
            max_test_cycle_iterations=5,
            timeout=900,
            workflow_run_id="run-123",
        )

        with pytest.raises(FrozenInstanceError):
            event.test_type = RepairTestType.INTEGRATION  # type: ignore

    def test_file_fix_started_is_frozen(self):
        """Test that file fix started event is immutable."""
        event = RepairCycleFileFixStartedEvent(
            type="repair_cycle.file_fix_started",
            timestamp=now_iso(),
            source="repair_cycle",
            test_file="auth.py",
            failure_count=1,
            test_type=RepairTestType.UNIT,
            agent_name="code-fixer",
            workflow_run_id="run-123",
        )

        with pytest.raises(FrozenInstanceError):
            event.test_file = "service.py"  # type: ignore

    def test_fast_fail_is_frozen(self):
        """Test that fast fail event is immutable."""
        event = RepairCycleFastFailEvent(
            type="repair_cycle.fast_fail",
            timestamp=now_iso(),
            source="repair_cycle",
            test_type=RepairTestType.UNIT,
            reason="max_agent_calls_exceeded",
            workflow_run_id="test-run-123",
        )

        with pytest.raises(FrozenInstanceError):
            event.reason = "timeout"  # type: ignore

    def test_environment_rebuild_started_is_frozen(self):
        """Test that environment rebuild started event is immutable."""
        event = EnvironmentRebuildStartedEvent(
            type="repair_cycle.environment_rebuild_started",
            timestamp=now_iso(),
            source="production_environment_repair",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            test_type=RepairTestType.UNIT,
            iteration=1,
        )

        with pytest.raises(FrozenInstanceError):
            event.test_type = RepairTestType.INTEGRATION  # type: ignore

    def test_environment_rebuild_completed_is_frozen(self):
        """Test that environment rebuild completed event is immutable."""
        event = EnvironmentRebuildCompletedEvent(
            type="repair_cycle.environment_rebuild_completed",
            timestamp=now_iso(),
            source="production_environment_repair",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            test_type=RepairTestType.UNIT,
            iteration=1,
            success=True,
            duration_seconds=10.5,
            actions_taken=("install_deps",),
            error=None,
        )

        with pytest.raises(FrozenInstanceError):
            event.success = False  # type: ignore

    def test_environment_verification_started_is_frozen(self):
        """Test that environment verification started event is immutable."""
        event = EnvironmentVerificationStartedEvent(
            type="repair_cycle.environment_verification_started",
            timestamp=now_iso(),
            source="production_environment_repair",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            test_type=RepairTestType.INTEGRATION,
            iteration=1,
        )

        with pytest.raises(FrozenInstanceError):
            event.test_type = RepairTestType.UNIT  # type: ignore

    def test_environment_verification_completed_is_frozen(self):
        """Test that environment verification completed event is immutable."""
        event = EnvironmentVerificationCompletedEvent(
            type="repair_cycle.environment_verification_completed",
            timestamp=now_iso(),
            source="production_environment_repair",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            test_type=RepairTestType.E2E,
            iteration=1,
            healthy=True,
            checks_passed=("deps_check", "env_check"),
            checks_failed=(),
            duration_seconds=5.2,
        )

        with pytest.raises(FrozenInstanceError):
            event.healthy = False  # type: ignore


class TestRepairCycleEventsSerialization:
    """Test serialization/deserialization of all repair cycle events."""

    def test_test_execution_roundtrip(self):
        """Test test execution started event roundtrip."""
        timestamp = now_iso()
        original = RepairCycleTestExecutionStartedEvent(
            type="repair_cycle.test_execution_started",
            timestamp=timestamp,
            source="repair_cycle",
            test_type=RepairTestType.INTEGRATION,
            test_type_index=2,
            test_cycle_iteration=3,
            max_test_cycle_iterations=5,
            timeout=1200,
            workflow_run_id="run-456",
        )

        d = original.to_dict()
        restored = RepairCycleTestExecutionStartedEvent.from_dict(d)

        assert restored.test_type == original.test_type
        assert restored.test_type_index == original.test_type_index
        assert restored.test_cycle_iteration == original.test_cycle_iteration
        assert restored.timeout == original.timeout

    def test_file_fix_roundtrip(self):
        """Test file fix completed event roundtrip."""
        timestamp = now_iso()
        original = RepairCycleFileFixCompletedEvent(
            type="repair_cycle.file_fix_completed",
            timestamp=timestamp,
            source="repair_cycle",
            test_file="service.py",
            failure_count=3,
            test_type=RepairTestType.E2E,
            success=False,
            agent_name="code-fixer",
            workflow_run_id="run-789",
        )

        d = original.to_dict()
        restored = RepairCycleFileFixCompletedEvent.from_dict(d)

        assert restored.test_file == original.test_file
        assert restored.failure_count == original.failure_count
        assert restored.success == original.success

    def test_test_cycle_completed_roundtrip(self):
        """Test test cycle completed event roundtrip."""
        timestamp = now_iso()
        original = RepairCycleTestCycleCompletedEvent(
            type="repair_cycle.test_cycle_completed",
            timestamp=timestamp,
            source="repair_cycle",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            passed=True,
            test_cycle_iterations=2,
            files_fixed=4,
            warnings_reviewed=1,
            error=None,
            duration_seconds=75.5,
            workflow_run_id="run-123",
        )

        d = original.to_dict()
        restored = RepairCycleTestCycleCompletedEvent.from_dict(d)

        assert restored.test_type == original.test_type
        assert restored.passed == original.passed
        assert restored.files_fixed == original.files_fixed
        assert restored.duration_seconds == original.duration_seconds


class TestDeprecationWarnings:
    """Test deprecation warnings for pipeline_run_id -> workflow_run_id migration."""

    def test_repair_cycle_started_deprecation_warning(self):
        """Test that using pipeline_run_id triggers a deprecation warning."""
        data = {
            "type": "repair_cycle.started",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "stage_name": "fix_failures",
            "test_types": ["UNIT", "INTEGRATION"],
            "pipeline_run_id": "run-old-123",  # Old field name
        }

        with pytest.warns(DeprecationWarning, match="pipeline_run_id.*deprecated.*workflow_run_id"):
            event = RepairCycleStartedEvent.from_dict(data)
            assert event.workflow_run_id == "run-old-123"

    def test_workflow_run_id_preferred_over_pipeline_run_id(self):
        """Test that workflow_run_id takes precedence when both fields are present."""
        data = {
            "type": "repair_cycle.started",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "stage_name": "fix_failures",
            "test_types": ["UNIT"],
            "workflow_run_id": "run-new-456",  # New field name (preferred)
            "pipeline_run_id": "run-old-123",  # Old field name (ignored)
        }

        # Should NOT warn when workflow_run_id is present
        import warnings as warnings_module

        with warnings_module.catch_warnings(record=True) as warning_list:
            warnings_module.simplefilter("always")
            event = RepairCycleStartedEvent.from_dict(data)
            assert event.workflow_run_id == "run-new-456"

        # Filter for DeprecationWarning
        deprecation_warnings = [w for w in warning_list if issubclass(w.category, DeprecationWarning)]
        assert len(deprecation_warnings) == 0, "Should not warn when workflow_run_id is present"

    def test_test_execution_started_deprecation_warning(self):
        """Test deprecation warning for RepairCycleTestExecutionStartedEvent."""
        data = {
            "type": "repair_cycle.test_execution_started",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "test_type": "UNIT",
            "test_type_index": 1,
            "test_cycle_iteration": 1,
            "max_test_cycle_iterations": 3,
            "timeout": 600,
            "pipeline_run_id": "run-789",
        }

        with pytest.warns(DeprecationWarning, match="pipeline_run_id.*deprecated"):
            event = RepairCycleTestExecutionStartedEvent.from_dict(data)
            assert event.workflow_run_id == "run-789"

    def test_completed_event_deprecation_warning(self):
        """Test deprecation warning for RepairCycleCompletedEvent."""
        timestamp = now_iso()
        data = {
            "type": "repair_cycle.completed",
            "timestamp": timestamp,
            "source": "repair_cycle",
            "overall_success": True,
            "test_results": [
                {
                    "test_type": "UNIT",
                    "passed": True,
                    "iterations": 2,
                    "final_result": {
                        "test_type": "UNIT",
                        "iteration": 2,
                        "passed": 10,
                        "failed": 0,
                        "warnings": 0,
                        "failures": [],
                        "warning_list": [],
                        "raw_output": "All tests passed",
                        "timestamp": timestamp,
                    },
                    "files_fixed": 5,
                    "warnings_reviewed": 1,
                    "duration_seconds": 150.5,
                    "error": None,
                }
            ],
            "total_agent_calls": 10,
            "duration_seconds": 150.5,
            "pipeline_run_id": "run-completed",
        }

        with pytest.warns(DeprecationWarning, match="pipeline_run_id.*deprecated"):
            event = RepairCycleCompletedEvent.from_dict(data)
            assert event.workflow_run_id == "run-completed"


class TestSystemicAnalysisStartedEvent:
    """Test SystemicAnalysisStartedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid systemic analysis started event."""
        timestamp = now_iso()
        event = SystemicAnalysisStartedEvent(
            type="repair_cycle.systemic_analysis_started",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            failure_count=3,
        )

        assert event.work_item_id == "issue-123"
        assert event.workflow_run_id == "run-456"
        assert event.failure_count == 3

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id"):
            SystemicAnalysisStartedEvent(
                type="repair_cycle.systemic_analysis_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="",
                workflow_run_id="run-456",
            )

    def test_missing_workflow_run_id(self):
        """Test that workflow_run_id is required."""
        with pytest.raises(ValueError, match="workflow_run_id"):
            SystemicAnalysisStartedEvent(
                type="repair_cycle.systemic_analysis_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-123",
                workflow_run_id="",
            )


class TestSystemicAnalysisCompletedEvent:
    """Test SystemicAnalysisCompletedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid systemic analysis completed event."""
        timestamp = now_iso()
        event = SystemicAnalysisCompletedEvent(
            type="repair_cycle.systemic_analysis_completed",
            timestamp=timestamp,
            source="repair_cycle",
            classification=FailureClassification.CODE_DEFECT.value,
            confidence=0.9,
            reasoning="Code defect detected",
            recommended_action="Fix code",
            work_item_id="issue-123",
            workflow_run_id="run-456",
        )

        assert event.classification == FailureClassification.CODE_DEFECT.value
        assert event.confidence == 0.9
        assert event.work_item_id == "issue-123"

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id"):
            SystemicAnalysisCompletedEvent(
                type="repair_cycle.systemic_analysis_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                classification=FailureClassification.CODE_DEFECT.value,
                confidence=0.9,
                reasoning="Code defect",
                recommended_action="Fix code",
                work_item_id="",
                workflow_run_id="run-456",
            )

    def test_missing_workflow_run_id(self):
        """Test that workflow_run_id is required."""
        with pytest.raises(ValueError, match="workflow_run_id"):
            SystemicAnalysisCompletedEvent(
                type="repair_cycle.systemic_analysis_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                classification=FailureClassification.CODE_DEFECT.value,
                confidence=0.9,
                reasoning="Code defect",
                recommended_action="Fix code",
                work_item_id="issue-123",
                workflow_run_id="",
            )

    def test_invalid_classification_raises_error(self):
        """Test that invalid classification raises ValueError."""
        with pytest.raises(ValueError, match="is not a valid FailureClassification"):
            SystemicAnalysisCompletedEvent(
                type="repair_cycle.systemic_analysis_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                classification="invalid",
                confidence=0.9,
                reasoning="Code defect",
                recommended_action="Fix code",
                work_item_id="issue-123",
                workflow_run_id="run-456",
            )

    def test_confidence_below_0_raises_error(self):
        """Test that confidence < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            SystemicAnalysisCompletedEvent(
                type="repair_cycle.systemic_analysis_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                classification=FailureClassification.CODE_DEFECT.value,
                confidence=-0.1,
                work_item_id="issue-123",
                workflow_run_id="run-456",
            )

    def test_deserialization_invalid_classification_string(self):
        """Test that invalid classification string defaults to CODE_DEFECT."""
        d = {
            "type": "repair_cycle.systemic_analysis_completed",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "classification": "invalid_classification",
            "confidence": 0.5,
            "reasoning": "Some reasoning",
            "recommended_action": "Some action",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
            "failure_count": 3,
        }

        event = SystemicAnalysisCompletedEvent.from_dict(d)
        # Should default to CODE_DEFECT instead of raising ValueError
        assert event.classification == FailureClassification.CODE_DEFECT

    def test_deserialization_future_enum_value(self):
        """Test that future/unknown enum values default to CODE_DEFECT."""
        d = {
            "type": "repair_cycle.systemic_analysis_completed",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "classification": "future_classification_type",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
        }

        event = SystemicAnalysisCompletedEvent.from_dict(d)
        # Should default to CODE_DEFECT for unknown enum values
        assert event.classification == FailureClassification.CODE_DEFECT


# ============================================================================
# SystemicFixStartedEvent Tests
# ============================================================================


class TestSystemicFixStartedEvent:
    """Test SystemicFixStartedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid systemic fix started event."""
        timestamp = now_iso()
        event = SystemicFixStartedEvent(
            type="repair_cycle.systemic_fix_started",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            root_cause_classification=FailureClassification.CODE_DEFECT.value,
            confidence=0.9,
            affected_file_count=5,
            failure_count=3,
        )

        assert event.work_item_id == "issue-123"
        assert event.workflow_run_id == "run-456"
        assert event.root_cause_classification == FailureClassification.CODE_DEFECT.value
        assert event.confidence == 0.9
        assert event.affected_file_count == 5
        assert event.failure_count == 3

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id is required"):
            SystemicFixStartedEvent(
                type="repair_cycle.systemic_fix_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="",
                workflow_run_id="run-456",
                root_cause_classification=FailureClassification.CODE_DEFECT.value,
                confidence=0.9,
                affected_file_count=5,
                failure_count=3,
            )

    def test_missing_workflow_run_id(self):
        """Test that workflow_run_id is required."""
        with pytest.raises(ValueError, match="workflow_run_id is required"):
            SystemicFixStartedEvent(
                type="repair_cycle.systemic_fix_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-123",
                workflow_run_id="",
                root_cause_classification=FailureClassification.CODE_DEFECT.value,
                confidence=0.9,
                affected_file_count=5,
                failure_count=3,
            )

    def test_invalid_root_cause_classification_invalid_value(self):
        """Test that invalid classification string is rejected."""
        # String that's not a valid FailureClassification value
        with pytest.raises(ValueError, match="is not a valid FailureClassification"):
            SystemicFixStartedEvent(
                type="repair_cycle.systemic_fix_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-123",
                workflow_run_id="run-456",
                root_cause_classification="not_a_classification",
                confidence=0.9,
                affected_file_count=5,
                failure_count=3,
            )

    def test_invalid_classification_value(self):
        """Test that root_cause_classification must be a valid FailureClassification value."""
        with pytest.raises(ValueError, match="is not a valid FailureClassification"):
            SystemicFixStartedEvent(
                type="repair_cycle.systemic_fix_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-123",
                workflow_run_id="run-456",
                root_cause_classification="invalid_classification",
                confidence=0.9,
                affected_file_count=5,
                failure_count=3,
            )

    def test_confidence_below_0_raises_error(self):
        """Test that confidence < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            SystemicFixStartedEvent(
                type="repair_cycle.systemic_fix_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-123",
                workflow_run_id="run-456",
                root_cause_classification=FailureClassification.CODE_DEFECT.value,
                confidence=-0.1,
                affected_file_count=5,
                failure_count=3,
            )

    def test_confidence_above_1_raises_error(self):
        """Test that confidence > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            SystemicFixStartedEvent(
                type="repair_cycle.systemic_fix_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-123",
                workflow_run_id="run-456",
                root_cause_classification=FailureClassification.CODE_DEFECT.value,
                confidence=1.1,
                affected_file_count=5,
                failure_count=3,
            )

    def test_serialization_round_trip(self):
        """Test SystemicFixStartedEvent serialization and deserialization."""
        timestamp = now_iso()
        original_event = SystemicFixStartedEvent(
            type="repair_cycle.systemic_fix_started",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            root_cause_classification=FailureClassification.ENVIRONMENT_ISSUE.value,
            confidence=0.75,
            affected_file_count=7,
            failure_count=5,
        )

        # Serialize
        d = original_event.to_dict()

        # Deserialize
        restored_event = SystemicFixStartedEvent.from_dict(d)

        # Verify round-trip fidelity
        assert restored_event.work_item_id == original_event.work_item_id
        assert restored_event.workflow_run_id == original_event.workflow_run_id
        assert restored_event.root_cause_classification == original_event.root_cause_classification
        assert restored_event.confidence == original_event.confidence
        assert restored_event.affected_file_count == original_event.affected_file_count
        assert restored_event.failure_count == original_event.failure_count

    def test_deserialization_with_missing_optional_fields(self):
        """Test that missing optional fields get default values."""
        d = {
            "type": "repair_cycle.systemic_fix_started",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
        }

        event = SystemicFixStartedEvent.from_dict(d)
        assert event.work_item_id == "issue-123"
        assert event.workflow_run_id == "run-456"
        assert event.root_cause_classification == FailureClassification.CODE_DEFECT.value
        assert event.confidence == 0.0
        assert event.affected_file_count == 0
        assert event.failure_count == 0

    def test_deserialization_invalid_classification_defaults_to_code_defect(self):
        """Test that invalid classification value defaults to CODE_DEFECT."""
        d = {
            "type": "repair_cycle.systemic_fix_started",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
            "root_cause_classification": "invalid_classification",
            "confidence": 0.5,
            "affected_file_count": 3,
            "failure_count": 2,
        }

        event = SystemicFixStartedEvent.from_dict(d)
        assert event.root_cause_classification == FailureClassification.CODE_DEFECT.value


# ============================================================================
# SystemicFixCompletedEvent Tests
# ============================================================================


class TestSystemicFixCompletedEvent:
    """Test SystemicFixCompletedEvent."""

    def test_create_successful_fix_completed_event(self):
        """Test creating a successful systemic fix completed event."""
        timestamp = now_iso()
        event = SystemicFixCompletedEvent(
            type="repair_cycle.systemic_fix_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            success=True,
            files_modified=("src/api.py", "src/models.py", "src/services.py"),
            root_cause_addressed="API contract change across modules",
            duration_seconds=45.5,
        )

        assert event.work_item_id == "issue-123"
        assert event.workflow_run_id == "run-456"
        assert event.success is True
        assert event.files_modified == ("src/api.py", "src/models.py", "src/services.py")
        assert event.root_cause_addressed == "API contract change across modules"
        assert event.duration_seconds == 45.5

    def test_create_failed_fix_completed_event(self):
        """Test creating a failed systemic fix completed event."""
        timestamp = now_iso()
        event = SystemicFixCompletedEvent(
            type="repair_cycle.systemic_fix_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            success=False,
            files_modified=(),
            root_cause_addressed="Failed to apply fix",
            duration_seconds=30.0,
        )

        assert event.success is False
        assert event.files_modified == ()

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id is required"):
            SystemicFixCompletedEvent(
                type="repair_cycle.systemic_fix_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="",
                workflow_run_id="run-456",
                success=True,
                files_modified=("file.py",),
                root_cause_addressed="Root cause",
                duration_seconds=10.0,
            )

    def test_missing_workflow_run_id(self):
        """Test that workflow_run_id is required."""
        with pytest.raises(ValueError, match="workflow_run_id is required"):
            SystemicFixCompletedEvent(
                type="repair_cycle.systemic_fix_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-123",
                workflow_run_id="",
                success=True,
                files_modified=("file.py",),
                root_cause_addressed="Root cause",
                duration_seconds=10.0,
            )

    def test_list_files_modified_coerced_to_tuple(self):
        """Test that list files_modified is coerced to tuple."""
        event = SystemicFixCompletedEvent(
            type="repair_cycle.systemic_fix_completed",
            timestamp=now_iso(),
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            success=True,
            files_modified=["file1.py", "file2.py"],  # type: ignore[arg-type]
            root_cause_addressed="Root cause",
            duration_seconds=10.0,
        )

        assert isinstance(event.files_modified, tuple)
        assert event.files_modified == ("file1.py", "file2.py")

    def test_serialization_round_trip(self):
        """Test SystemicFixCompletedEvent serialization and deserialization."""
        timestamp = now_iso()
        original_event = SystemicFixCompletedEvent(
            type="repair_cycle.systemic_fix_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            success=True,
            files_modified=("src/api.py", "src/models.py"),
            root_cause_addressed="API contract change",
            duration_seconds=120.5,
        )

        # Serialize to dict
        d = original_event.to_dict()

        # Verify that files_modified is serialized as list
        assert isinstance(d["files_modified"], list)
        assert d["files_modified"] == ["src/api.py", "src/models.py"]

        # Deserialize from dict
        restored_event = SystemicFixCompletedEvent.from_dict(d)

        # Verify round-trip fidelity
        assert restored_event.work_item_id == original_event.work_item_id
        assert restored_event.workflow_run_id == original_event.workflow_run_id
        assert restored_event.success == original_event.success
        assert restored_event.files_modified == original_event.files_modified
        assert restored_event.root_cause_addressed == original_event.root_cause_addressed
        assert restored_event.duration_seconds == original_event.duration_seconds

    def test_deserialization_with_missing_optional_fields(self):
        """Test that missing optional fields get default values."""
        d = {
            "type": "repair_cycle.systemic_fix_completed",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
        }

        event = SystemicFixCompletedEvent.from_dict(d)
        assert event.work_item_id == "issue-123"
        assert event.workflow_run_id == "run-456"
        assert event.success is False
        assert event.files_modified == ()
        assert event.root_cause_addressed == ""
        assert event.duration_seconds == 0.0

    def test_deserialization_with_invalid_files_modified(self):
        """Test that invalid files_modified defaults to empty tuple."""
        d = {
            "type": "repair_cycle.systemic_fix_completed",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
            "files_modified": 123,  # Invalid: not list or tuple
            "success": True,
            "root_cause_addressed": "Root cause",
            "duration_seconds": 10.0,
        }

        event = SystemicFixCompletedEvent.from_dict(d)
        assert event.files_modified == ()


# ============================================================================
# SystemicFixStartedEvent Edge Cases and Round-Trip Tests
# ============================================================================


class TestSystemicFixStartedEventEdgeCases:
    """Test edge cases and round-trip serialization for SystemicFixStartedEvent."""

    def test_round_trip_with_all_fields(self):
        """Test complete round-trip with all fields populated."""
        timestamp = now_iso()
        original = SystemicFixStartedEvent(
            type="repair_cycle.systemic_fix_started",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="WI-123",
            workflow_run_id="WR-456",
            root_cause_classification=FailureClassification.CODE_DEFECT.value,
            confidence=0.85,
            affected_file_count=7,
            failure_count=5,
        )

        d = original.to_dict()
        restored = SystemicFixStartedEvent.from_dict(d)

        assert restored == original
        assert restored.work_item_id == "WI-123"
        assert restored.workflow_run_id == "WR-456"
        assert restored.root_cause_classification == FailureClassification.CODE_DEFECT.value
        assert restored.confidence == 0.85
        assert restored.affected_file_count == 7
        assert restored.failure_count == 5

    def test_round_trip_immutability(self):
        """Test that deserialized event is immutable."""
        d = {
            "type": "repair_cycle.systemic_fix_started",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "work_item_id": "WI-123",
            "workflow_run_id": "WR-456",
            "root_cause_classification": FailureClassification.CODE_DEFECT.value,
            "confidence": 0.9,
            "affected_file_count": 3,
            "failure_count": 2,
        }

        event = SystemicFixStartedEvent.from_dict(d)

        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "WI-999"  # type: ignore[misc]


# ============================================================================
# SystemicFixCompletedEvent Edge Cases and Round-Trip Tests
# ============================================================================


class TestSystemicFixCompletedEventEdgeCases:
    """Test edge cases and round-trip serialization for SystemicFixCompletedEvent."""

    def test_round_trip_with_multiple_files(self):
        """Test round-trip with multiple files modified."""
        timestamp = now_iso()
        files = ("src/api.py", "src/models.py", "src/services.py", "src/utils.py")
        original = SystemicFixCompletedEvent(
            type="repair_cycle.systemic_fix_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="WI-123",
            workflow_run_id="WR-456",
            success=True,
            files_modified=files,
            root_cause_addressed="API contract changed across multiple modules",
            duration_seconds=256.75,
        )

        d = original.to_dict()
        assert d["files_modified"] == list(files)

        restored = SystemicFixCompletedEvent.from_dict(d)
        assert restored.files_modified == files
        assert isinstance(restored.files_modified, tuple)

    def test_round_trip_failed_fix(self):
        """Test round-trip with failed systemic fix."""
        timestamp = now_iso()
        original = SystemicFixCompletedEvent(
            type="repair_cycle.systemic_fix_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="WI-123",
            workflow_run_id="WR-456",
            success=False,
            files_modified=(),
            root_cause_addressed="Attempted to apply fix but validation failed",
            duration_seconds=180.0,
        )

        d = original.to_dict()
        restored = SystemicFixCompletedEvent.from_dict(d)

        assert restored.success is False
        assert restored.files_modified == ()

    def test_round_trip_zero_duration(self):
        """Test round-trip with zero duration."""
        timestamp = now_iso()
        original = SystemicFixCompletedEvent(
            type="repair_cycle.systemic_fix_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="WI-123",
            workflow_run_id="WR-456",
            success=False,
            files_modified=(),
            root_cause_addressed="Quick failure",
            duration_seconds=0.0,
        )

        d = original.to_dict()
        restored = SystemicFixCompletedEvent.from_dict(d)

        assert restored.duration_seconds == 0.0

    def test_immutability_after_deserialization(self):
        """Test that deserialized event is immutable."""
        d = {
            "type": "repair_cycle.systemic_fix_completed",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "work_item_id": "WI-123",
            "workflow_run_id": "WR-456",
            "success": True,
            "files_modified": ["src/api.py"],
            "root_cause_addressed": "Root cause",
            "duration_seconds": 100.0,
        }

        event = SystemicFixCompletedEvent.from_dict(d)

        with pytest.raises(FrozenInstanceError):
            event.success = False  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            event.root_cause_addressed = "Different cause"  # type: ignore[misc]


class TestRebuildResultType:
    """Test RebuildResult domain type."""

    def test_create_successful_rebuild_result(self):
        """Test creating a successful RebuildResult."""
        result = RebuildResult(
            success=True,
            duration_seconds=120.0,
            actions_taken=("docker build", "pip install", "pytest --collect-only"),
            error=None,
        )

        assert result.success is True
        assert result.duration_seconds == 120.0
        assert result.actions_taken == ("docker build", "pip install", "pytest --collect-only")
        assert result.error is None

    def test_create_failed_rebuild_result(self):
        """Test creating a failed RebuildResult."""
        result = RebuildResult(
            success=False,
            duration_seconds=45.0,
            actions_taken=("docker build",),
            error="Build failed: dependency resolution timeout",
        )

        assert result.success is False
        assert result.duration_seconds == 45.0
        assert result.actions_taken == ("docker build",)
        assert result.error == "Build failed: dependency resolution timeout"

    def test_empty_actions_tuple(self):
        """Test RebuildResult with empty actions."""
        result = RebuildResult(
            success=False,
            duration_seconds=0.0,
            actions_taken=(),
            error="No actions attempted",
        )

        assert result.actions_taken == ()

    def test_negative_duration_rejected(self):
        """Test that negative duration is rejected."""
        with pytest.raises(ValueError, match="duration_seconds"):
            RebuildResult(
                success=True,
                duration_seconds=-1.0,
                actions_taken=(),
                error=None,
            )

    def test_immutability(self):
        """Test that RebuildResult is immutable."""
        result = RebuildResult(
            success=True,
            duration_seconds=100.0,
            actions_taken=("action1",),
            error=None,
        )

        with pytest.raises(FrozenInstanceError):
            result.success = False  # type: ignore


class TestVerificationResultType:
    """Test VerificationResult domain type."""

    def test_create_healthy_verification_result(self):
        """Test creating a healthy VerificationResult."""
        result = VerificationResult(
            healthy=True,
            checks_passed=("docker_running", "pip_packages_installed", "workspace_mounted"),
            checks_failed=(),
            duration_seconds=30.0,
        )

        assert result.healthy is True
        assert result.checks_passed == ("docker_running", "pip_packages_installed", "workspace_mounted")
        assert result.checks_failed == ()
        assert result.duration_seconds == 30.0

    def test_create_unhealthy_verification_result(self):
        """Test creating an unhealthy VerificationResult."""
        result = VerificationResult(
            healthy=False,
            checks_passed=("docker_running",),
            checks_failed=("pip_packages_installed", "workspace_mounted"),
            duration_seconds=15.0,
        )

        assert result.healthy is False
        assert result.checks_passed == ("docker_running",)
        assert result.checks_failed == ("pip_packages_installed", "workspace_mounted")
        assert result.duration_seconds == 15.0

    def test_no_checks_performed(self):
        """Test VerificationResult with no checks."""
        result = VerificationResult(
            healthy=True,
            checks_passed=(),
            checks_failed=(),
            duration_seconds=0.0,
        )

        assert result.checks_passed == ()
        assert result.checks_failed == ()

    def test_negative_duration_rejected(self):
        """Test that negative duration is rejected."""
        with pytest.raises(ValueError, match="duration_seconds"):
            VerificationResult(
                healthy=True,
                checks_passed=(),
                checks_failed=(),
                duration_seconds=-10.0,
            )

    def test_immutability(self):
        """Test that VerificationResult is immutable."""
        result = VerificationResult(
            healthy=True,
            checks_passed=("check1",),
            checks_failed=(),
            duration_seconds=10.0,
        )

        with pytest.raises(FrozenInstanceError):
            result.healthy = False  # type: ignore


class TestEnvironmentRebuildStartedEvent:
    """Test EnvironmentRebuildStartedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid environment rebuild started event."""
        timestamp = now_iso()
        event = EnvironmentRebuildStartedEvent(
            type="repair_cycle.environment_rebuild_started",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-456",
            workflow_run_id="run-123",
            test_type="UNIT",
            iteration=1,
        )

        assert event.work_item_id == "issue-456"
        assert event.workflow_run_id == "run-123"
        assert event.test_type == RepairTestType.UNIT
        assert event.iteration == 1

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id"):
            EnvironmentRebuildStartedEvent(
                type="repair_cycle.environment_rebuild_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="",
                workflow_run_id="run-123",
                test_type="UNIT",
                iteration=1,
            )

    def test_missing_workflow_run_id(self):
        """Test that workflow_run_id is required."""
        with pytest.raises(ValueError, match="workflow_run_id"):
            EnvironmentRebuildStartedEvent(
                type="repair_cycle.environment_rebuild_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-456",
                workflow_run_id="",
                test_type="UNIT",
                iteration=1,
            )

    def test_missing_test_type(self):
        """Test that test_type is required."""
        with pytest.raises(ValueError, match="test_type"):
            EnvironmentRebuildStartedEvent(
                type="repair_cycle.environment_rebuild_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-456",
                workflow_run_id="run-123",
                test_type="",
                iteration=1,
            )

    def test_invalid_iteration(self):
        """Test that iteration must be >= 1."""
        with pytest.raises(ValueError, match="iteration"):
            EnvironmentRebuildStartedEvent(
                type="repair_cycle.environment_rebuild_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-456",
                workflow_run_id="run-123",
                test_type="UNIT",
                iteration=0,
            )

    def test_serialization(self):
        """Test EnvironmentRebuildStartedEvent serialization."""
        timestamp = now_iso()
        event = EnvironmentRebuildStartedEvent(
            type="repair_cycle.environment_rebuild_started",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-456",
            workflow_run_id="run-123",
            test_type="INTEGRATION",
            iteration=2,
        )
        d = event.to_dict()
        assert d["work_item_id"] == "issue-456"
        assert d["workflow_run_id"] == "run-123"
        assert d["test_type"] == "INTEGRATION"
        assert d["iteration"] == 2

    def test_deserialization(self):
        """Test EnvironmentRebuildStartedEvent deserialization."""
        timestamp = now_iso()
        d = {
            "type": "repair_cycle.environment_rebuild_started",
            "timestamp": timestamp,
            "source": "repair_cycle",
            "work_item_id": "issue-456",
            "workflow_run_id": "run-123",
            "test_type": "E2E",
            "iteration": 1,
        }
        event = EnvironmentRebuildStartedEvent.from_dict(d)
        assert event.work_item_id == "issue-456"
        assert event.workflow_run_id == "run-123"
        assert event.test_type == RepairTestType.E2E
        assert event.iteration == 1


class TestEnvironmentRebuildCompletedEvent:
    """Test EnvironmentRebuildCompletedEvent."""

    def test_create_successful_event(self):
        """Test creating a successful rebuild completed event."""
        timestamp = now_iso()
        event = EnvironmentRebuildCompletedEvent(
            type="repair_cycle.environment_rebuild_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-456",
            workflow_run_id="run-123",
            test_type="UNIT",
            iteration=1,
            success=True,
            duration_seconds=150.0,
            actions_taken=("docker build", "pip install"),
            error=None,
        )

        assert event.success is True
        assert event.duration_seconds == 150.0
        assert event.actions_taken == ("docker build", "pip install")
        assert event.error is None

    def test_create_failed_event(self):
        """Test creating a failed rebuild completed event."""
        timestamp = now_iso()
        event = EnvironmentRebuildCompletedEvent(
            type="repair_cycle.environment_rebuild_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-456",
            workflow_run_id="run-123",
            test_type="UNIT",
            iteration=1,
            success=False,
            duration_seconds=60.0,
            actions_taken=("docker build",),
            error="Build failed: timeout",
        )

        assert event.success is False
        assert event.error == "Build failed: timeout"

    def test_invalid_duration(self):
        """Test that negative duration is rejected."""
        with pytest.raises(ValueError, match="duration_seconds"):
            EnvironmentRebuildCompletedEvent(
                type="repair_cycle.environment_rebuild_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-456",
                workflow_run_id="run-123",
                test_type="UNIT",
                iteration=1,
                success=True,
                duration_seconds=-10.0,
                actions_taken=(),
                error=None,
            )

    def test_serialization(self):
        """Test EnvironmentRebuildCompletedEvent serialization."""
        timestamp = now_iso()
        event = EnvironmentRebuildCompletedEvent(
            type="repair_cycle.environment_rebuild_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-456",
            workflow_run_id="run-123",
            test_type="UNIT",
            iteration=1,
            success=True,
            duration_seconds=100.0,
            actions_taken=("action1", "action2"),
            error=None,
        )
        d = event.to_dict()
        assert d["work_item_id"] == "issue-456"
        assert d["success"] is True
        assert d["duration_seconds"] == 100.0
        assert d["actions_taken"] == ["action1", "action2"]
        assert d["error"] is None

    def test_deserialization_with_error(self):
        """Test EnvironmentRebuildCompletedEvent deserialization with error."""
        timestamp = now_iso()
        d = {
            "type": "repair_cycle.environment_rebuild_completed",
            "timestamp": timestamp,
            "source": "repair_cycle",
            "work_item_id": "issue-456",
            "workflow_run_id": "run-123",
            "test_type": "UNIT",
            "iteration": 1,
            "success": False,
            "duration_seconds": 50.0,
            "actions_taken": ["docker build"],
            "error": "Build failed",
        }
        event = EnvironmentRebuildCompletedEvent.from_dict(d)
        assert event.work_item_id == "issue-456"
        assert event.success is False
        assert event.error == "Build failed"
        assert event.actions_taken == ("docker build",)

    def test_round_trip_serialization(self):
        """Test round-trip serialization of rebuild completed event."""
        timestamp = now_iso()
        original = EnvironmentRebuildCompletedEvent(
            type="repair_cycle.environment_rebuild_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-789",
            workflow_run_id="run-456",
            test_type="INTEGRATION",
            iteration=2,
            success=True,
            duration_seconds=200.0,
            actions_taken=("step1", "step2", "step3"),
            error=None,
        )

        d = original.to_dict()
        restored = EnvironmentRebuildCompletedEvent.from_dict(d)

        assert restored.success == original.success
        assert restored.duration_seconds == original.duration_seconds
        assert restored.actions_taken == original.actions_taken
        assert restored.error == original.error


class TestEnvironmentVerificationStartedEvent:
    """Test EnvironmentVerificationStartedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid verification started event."""
        timestamp = now_iso()
        event = EnvironmentVerificationStartedEvent(
            type="repair_cycle.environment_verification_started",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-456",
            workflow_run_id="run-123",
            test_type="UNIT",
            iteration=1,
        )

        assert event.work_item_id == "issue-456"
        assert event.workflow_run_id == "run-123"
        assert event.test_type == RepairTestType.UNIT
        assert event.iteration == 1

    def test_serialization(self):
        """Test serialization."""
        timestamp = now_iso()
        event = EnvironmentVerificationStartedEvent(
            type="repair_cycle.environment_verification_started",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-789",
            workflow_run_id="run-789",
            test_type="E2E",
            iteration=3,
        )
        d = event.to_dict()
        assert d["work_item_id"] == "issue-789"
        assert d["workflow_run_id"] == "run-789"
        assert d["test_type"] == "E2E"
        assert d["iteration"] == 3

    def test_deserialization(self):
        """Test deserialization."""
        timestamp = now_iso()
        d = {
            "type": "repair_cycle.environment_verification_started",
            "timestamp": timestamp,
            "source": "repair_cycle",
            "work_item_id": "issue-789",
            "workflow_run_id": "run-789",
            "test_type": "INTEGRATION",
            "iteration": 2,
        }
        event = EnvironmentVerificationStartedEvent.from_dict(d)
        assert event.work_item_id == "issue-789"
        assert event.workflow_run_id == "run-789"
        assert event.test_type == RepairTestType.INTEGRATION
        assert event.iteration == 2


class TestEnvironmentVerificationCompletedEvent:
    """Test EnvironmentVerificationCompletedEvent."""

    def test_create_healthy_environment_event(self):
        """Test creating an event for healthy environment."""
        timestamp = now_iso()
        event = EnvironmentVerificationCompletedEvent(
            type="repair_cycle.environment_verification_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-456",
            workflow_run_id="run-123",
            test_type="UNIT",
            iteration=1,
            healthy=True,
            checks_passed=("docker_ready", "dependencies_installed", "workspace_mounted"),
            checks_failed=(),
            duration_seconds=30.0,
        )

        assert event.healthy is True
        assert len(event.checks_passed) == 3
        assert len(event.checks_failed) == 0
        assert event.duration_seconds == 30.0

    def test_create_unhealthy_environment_event(self):
        """Test creating an event for unhealthy environment."""
        timestamp = now_iso()
        event = EnvironmentVerificationCompletedEvent(
            type="repair_cycle.environment_verification_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-456",
            workflow_run_id="run-123",
            test_type="UNIT",
            iteration=1,
            healthy=False,
            checks_passed=("docker_ready",),
            checks_failed=("dependencies_installed", "workspace_mounted"),
            duration_seconds=20.0,
        )

        assert event.healthy is False
        assert event.checks_passed == ("docker_ready",)
        assert event.checks_failed == ("dependencies_installed", "workspace_mounted")

    def test_invalid_duration(self):
        """Test that negative duration is rejected."""
        with pytest.raises(ValueError, match="duration_seconds"):
            EnvironmentVerificationCompletedEvent(
                type="repair_cycle.environment_verification_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-456",
                workflow_run_id="run-123",
                test_type="UNIT",
                iteration=1,
                healthy=True,
                checks_passed=(),
                checks_failed=(),
                duration_seconds=-5.0,
            )

    def test_serialization_healthy(self):
        """Test serialization of healthy environment event."""
        timestamp = now_iso()
        event = EnvironmentVerificationCompletedEvent(
            type="repair_cycle.environment_verification_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-456",
            workflow_run_id="run-123",
            test_type="INTEGRATION",
            iteration=2,
            healthy=True,
            checks_passed=("check1", "check2"),
            checks_failed=(),
            duration_seconds=25.0,
        )
        d = event.to_dict()
        assert d["healthy"] is True
        assert d["checks_passed"] == ["check1", "check2"]
        assert d["checks_failed"] == []
        assert d["duration_seconds"] == 25.0

    def test_serialization_unhealthy(self):
        """Test serialization of unhealthy environment event."""
        timestamp = now_iso()
        event = EnvironmentVerificationCompletedEvent(
            type="repair_cycle.environment_verification_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-789",
            workflow_run_id="run-456",
            test_type="E2E",
            iteration=1,
            healthy=False,
            checks_passed=("check1",),
            checks_failed=("check2", "check3"),
            duration_seconds=15.0,
        )
        d = event.to_dict()
        assert d["work_item_id"] == "issue-789"
        assert d["healthy"] is False
        assert d["checks_passed"] == ["check1"]
        assert d["checks_failed"] == ["check2", "check3"]

    def test_deserialization_healthy(self):
        """Test deserialization of healthy environment event."""
        timestamp = now_iso()
        d = {
            "type": "repair_cycle.environment_verification_completed",
            "timestamp": timestamp,
            "source": "repair_cycle",
            "work_item_id": "issue-789",
            "workflow_run_id": "run-789",
            "test_type": "UNIT",
            "iteration": 1,
            "healthy": True,
            "checks_passed": ["all_good"],
            "checks_failed": [],
            "duration_seconds": 10.0,
        }
        event = EnvironmentVerificationCompletedEvent.from_dict(d)
        assert event.work_item_id == "issue-789"
        assert event.healthy is True
        assert event.checks_passed == ("all_good",)
        assert event.checks_failed == ()

    def test_deserialization_unhealthy(self):
        """Test deserialization of unhealthy environment event."""
        timestamp = now_iso()
        d = {
            "type": "repair_cycle.environment_verification_completed",
            "timestamp": timestamp,
            "source": "repair_cycle",
            "work_item_id": "issue-789",
            "workflow_run_id": "run-789",
            "test_type": "INTEGRATION",
            "iteration": 2,
            "healthy": False,
            "checks_passed": ["check1"],
            "checks_failed": ["check2", "check3"],
            "duration_seconds": 8.0,
        }
        event = EnvironmentVerificationCompletedEvent.from_dict(d)
        assert event.work_item_id == "issue-789"
        assert event.healthy is False
        assert event.checks_passed == ("check1",)
        assert event.checks_failed == ("check2", "check3")

    def test_round_trip_serialization(self):
        """Test round-trip serialization."""
        timestamp = now_iso()
        original = EnvironmentVerificationCompletedEvent(
            type="repair_cycle.environment_verification_completed",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-999",
            workflow_run_id="run-999",
            test_type="E2E",
            iteration=3,
            healthy=True,
            checks_passed=("setup", "ready", "verified"),
            checks_failed=(),
            duration_seconds=45.5,
        )

        d = original.to_dict()
        restored = EnvironmentVerificationCompletedEvent.from_dict(d)

        assert restored.work_item_id == original.work_item_id
        assert restored.healthy == original.healthy
        assert restored.checks_passed == original.checks_passed
        assert restored.checks_failed == original.checks_failed
        assert restored.duration_seconds == original.duration_seconds
        assert restored.workflow_run_id == original.workflow_run_id


class TestEnvironmentRebuildExhaustedEvent:
    """Test EnvironmentRebuildExhaustedEvent."""

    def test_create_event(self):
        """Test creating an exhausted event."""
        timestamp = now_iso()
        event = EnvironmentRebuildExhaustedEvent(
            type="repair_cycle.environment_rebuild_exhausted",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            test_type=RepairTestType.UNIT,
            iteration=2,
            max_attempts=3,
            error_message="Rebuild failed: dependency timeout",
        )
        assert event.work_item_id == "issue-123"
        assert event.workflow_run_id == "run-456"
        assert event.test_type == RepairTestType.UNIT
        assert event.iteration == 2
        assert event.max_attempts == 3
        assert event.error_message == "Rebuild failed: dependency timeout"

    def test_event_immutability(self):
        """Test that event is frozen."""
        event = EnvironmentRebuildExhaustedEvent(
            type="repair_cycle.environment_rebuild_exhausted",
            timestamp=now_iso(),
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            test_type=RepairTestType.INTEGRATION,
            iteration=1,
            max_attempts=2,
            error_message="Failed",
        )
        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "issue-999"  # type: ignore[misc]

    def test_missing_work_item_id_raises_error(self):
        """Test that missing work_item_id raises ValueError."""
        with pytest.raises(ValueError, match="work_item_id is required"):
            EnvironmentRebuildExhaustedEvent(
                type="repair_cycle.environment_rebuild_exhausted",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="",
                workflow_run_id="run-456",
                test_type=RepairTestType.UNIT,
                iteration=1,
                max_attempts=2,
                error_message="Error",
            )

    def test_missing_workflow_run_id_raises_error(self):
        """Test that missing workflow_run_id raises ValueError."""
        with pytest.raises(ValueError, match="workflow_run_id is required"):
            EnvironmentRebuildExhaustedEvent(
                type="repair_cycle.environment_rebuild_exhausted",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-123",
                workflow_run_id="",
                test_type=RepairTestType.UNIT,
                iteration=1,
                max_attempts=2,
                error_message="Error",
            )

    def test_invalid_iteration_raises_error(self):
        """Test that iteration < 1 raises ValueError."""
        with pytest.raises(ValueError, match="iteration must be >= 1"):
            EnvironmentRebuildExhaustedEvent(
                type="repair_cycle.environment_rebuild_exhausted",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-123",
                workflow_run_id="run-456",
                test_type=RepairTestType.UNIT,
                iteration=0,
                max_attempts=2,
                error_message="Error",
            )

    def test_invalid_max_attempts_raises_error(self):
        """Test that max_attempts <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="max_attempts must be > 0"):
            EnvironmentRebuildExhaustedEvent(
                type="repair_cycle.environment_rebuild_exhausted",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-123",
                workflow_run_id="run-456",
                test_type=RepairTestType.UNIT,
                iteration=1,
                max_attempts=0,
                error_message="Error",
            )

    def test_missing_error_message_raises_error(self):
        """Test that missing error_message raises ValueError."""
        with pytest.raises(ValueError, match="error_message is required"):
            EnvironmentRebuildExhaustedEvent(
                type="repair_cycle.environment_rebuild_exhausted",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="issue-123",
                workflow_run_id="run-456",
                test_type=RepairTestType.UNIT,
                iteration=1,
                max_attempts=2,
                error_message="",
            )

    def test_serialization_round_trip(self):
        """Test that event can be serialized and deserialized."""
        timestamp = now_iso()
        original = EnvironmentRebuildExhaustedEvent(
            type="repair_cycle.environment_rebuild_exhausted",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            test_type=RepairTestType.E2E,
            iteration=3,
            max_attempts=5,
            error_message="Multiple rebuild attempts failed",
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = EnvironmentRebuildExhaustedEvent.from_dict(data)

        # Verify
        assert restored.work_item_id == original.work_item_id
        assert restored.workflow_run_id == original.workflow_run_id
        assert restored.test_type == original.test_type
        assert restored.iteration == original.iteration
        assert restored.max_attempts == original.max_attempts
        assert restored.error_message == original.error_message

    def test_from_dict_with_string_test_type(self):
        """Test from_dict converts string test_type to enum."""
        data = {
            "type": "repair_cycle.environment_rebuild_exhausted",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
            "test_type": "INTEGRATION",
            "iteration": 2,
            "max_attempts": 3,
            "error_message": "Error",
        }
        event = EnvironmentRebuildExhaustedEvent.from_dict(data)
        assert event.test_type == RepairTestType.INTEGRATION
        assert isinstance(event.test_type, RepairTestType)

    def test_from_dict_missing_work_item_id_raises_error(self):
        """Test that from_dict raises KeyError for missing work_item_id."""
        data = {
            "type": "repair_cycle.environment_rebuild_exhausted",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "workflow_run_id": "run-456",
            "test_type": "UNIT",
            "iteration": 1,
            "max_attempts": 2,
            "error_message": "Error",
        }
        with pytest.raises(KeyError):
            EnvironmentRebuildExhaustedEvent.from_dict(data)

    def test_from_dict_missing_test_type_raises_error(self):
        """Test that from_dict raises KeyError for missing test_type."""
        data = {
            "type": "repair_cycle.environment_rebuild_exhausted",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
            "iteration": 1,
            "max_attempts": 2,
            "error_message": "Error",
        }
        with pytest.raises(KeyError):
            EnvironmentRebuildExhaustedEvent.from_dict(data)

    def test_from_dict_missing_iteration_raises_error(self):
        """Test that from_dict raises KeyError for missing iteration."""
        data = {
            "type": "repair_cycle.environment_rebuild_exhausted",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
            "test_type": "UNIT",
            "max_attempts": 2,
            "error_message": "Error",
        }
        with pytest.raises(KeyError):
            EnvironmentRebuildExhaustedEvent.from_dict(data)
