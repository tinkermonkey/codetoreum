"""Unit tests for repair cycle events."""

import pytest

from codetoreum.domain.events import (
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
    now_iso,
)
from codetoreum.domain.repair_cycle_types import (
    CycleResult,
    FailureClassification,
    RepairTestFailure,
    RepairTestResult,
    RepairTestType,
    RepairTestWarning,
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
            "workflow_run_id": "run-123",
        }

        event = RepairCycleTestExecutionCompletedEvent.from_dict(d)
        assert event.failed == 2
        assert len(event.failures) == 2
        assert event.failures[0].file == "test_auth.py"


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
            workflow_run_id="run-123",
        )

        assert event.test_file == "auth.py"
        assert event.success is True


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
            workflow_run_id="test-run-123",
        )

        assert event.source_file == "auth.py"
        assert event.success is True


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
            failure_count=5,
        )

        assert event.work_item_id == "issue-123"
        assert event.workflow_run_id == "run-456"
        assert event.failure_count == 5
        assert event.type == "repair_cycle.systemic_analysis_started"

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id"):
            SystemicAnalysisStartedEvent(
                type="repair_cycle.systemic_analysis_started",
                timestamp=now_iso(),
                source="repair_cycle",
                work_item_id="",
                workflow_run_id="run-456",
                failure_count=5,
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
                failure_count=5,
            )

    def test_default_failure_count(self):
        """Test that failure_count defaults to 0."""
        event = SystemicAnalysisStartedEvent(
            type="repair_cycle.systemic_analysis_started",
            timestamp=now_iso(),
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
        )
        assert event.failure_count == 0

    def test_serialization(self):
        """Test SystemicAnalysisStartedEvent serialization."""
        timestamp = now_iso()
        event = SystemicAnalysisStartedEvent(
            type="repair_cycle.systemic_analysis_started",
            timestamp=timestamp,
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            failure_count=5,
        )

        d = event.to_dict()
        assert d["work_item_id"] == "issue-123"
        assert d["workflow_run_id"] == "run-456"
        assert d["failure_count"] == 5
        assert d["type"] == "repair_cycle.systemic_analysis_started"
        assert d["timestamp"] == timestamp

    def test_deserialization(self):
        """Test SystemicAnalysisStartedEvent deserialization."""
        timestamp = now_iso()
        d = {
            "type": "repair_cycle.systemic_analysis_started",
            "timestamp": timestamp,
            "source": "repair_cycle",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
            "failure_count": 5,
        }

        event = SystemicAnalysisStartedEvent.from_dict(d)
        assert event.work_item_id == "issue-123"
        assert event.workflow_run_id == "run-456"
        assert event.failure_count == 5
        assert event.timestamp == timestamp

    def test_deserialization_missing_optional_fields(self):
        """Test deserialization with missing optional fields uses defaults."""
        d = {
            "type": "repair_cycle.systemic_analysis_started",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
        }

        event = SystemicAnalysisStartedEvent.from_dict(d)
        assert event.failure_count == 0

    def test_round_trip_serialization(self):
        """Test that serialization round-trips through deserialization."""
        original = SystemicAnalysisStartedEvent(
            type="repair_cycle.systemic_analysis_started",
            timestamp=now_iso(),
            source="repair_cycle",
            work_item_id="issue-789",
            workflow_run_id="run-999",
            failure_count=10,
        )

        d = original.to_dict()
        restored = SystemicAnalysisStartedEvent.from_dict(d)

        assert restored.work_item_id == original.work_item_id
        assert restored.workflow_run_id == original.workflow_run_id
        assert restored.failure_count == original.failure_count
        assert restored.timestamp == original.timestamp

    def test_immutability(self):
        """Test that SystemicAnalysisStartedEvent is immutable."""
        event = SystemicAnalysisStartedEvent(
            type="repair_cycle.systemic_analysis_started",
            timestamp=now_iso(),
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            failure_count=5,
        )

        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "issue-999"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.workflow_run_id = "run-999"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.failure_count = 10  # type: ignore


class TestSystemicAnalysisCompletedEvent:
    """Test SystemicAnalysisCompletedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid systemic analysis completed event."""
        timestamp = now_iso()
        event = SystemicAnalysisCompletedEvent(
            type="repair_cycle.systemic_analysis_completed",
            timestamp=timestamp,
            source="repair_cycle",
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Consistent failure pattern in test file suggests code logic error",
            recommended_action="Apply code fix and re-run tests",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            failure_count=5,
        )

        assert event.classification == FailureClassification.CODE_DEFECT
        assert event.confidence == 0.95
        assert event.reasoning == "Consistent failure pattern in test file suggests code logic error"
        assert event.recommended_action == "Apply code fix and re-run tests"
        assert event.work_item_id == "issue-123"
        assert event.workflow_run_id == "run-456"
        assert event.failure_count == 5

    def test_classification_enum(self):
        """Test that classification is a FailureClassification enum."""
        event = SystemicAnalysisCompletedEvent(
            type="repair_cycle.systemic_analysis_completed",
            timestamp=now_iso(),
            source="repair_cycle",
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.8,
            reasoning="Tests pass in local environment but fail in CI",
            recommended_action="Verify CI environment setup",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            failure_count=3,
        )

        assert isinstance(event.classification, FailureClassification)
        assert event.classification == FailureClassification.ENVIRONMENT_ISSUE

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id"):
            SystemicAnalysisCompletedEvent(
                type="repair_cycle.systemic_analysis_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.95,
                reasoning="Some reason",
                recommended_action="Some action",
                work_item_id="",
                workflow_run_id="run-456",
                failure_count=5,
            )

    def test_missing_workflow_run_id(self):
        """Test that workflow_run_id is required."""
        with pytest.raises(ValueError, match="workflow_run_id"):
            SystemicAnalysisCompletedEvent(
                type="repair_cycle.systemic_analysis_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                classification=FailureClassification.CODE_DEFECT,
                confidence=0.95,
                reasoning="Some reason",
                recommended_action="Some action",
                work_item_id="issue-123",
                workflow_run_id="",
                failure_count=5,
            )

    def test_default_values(self):
        """Test that fields have appropriate defaults."""
        event = SystemicAnalysisCompletedEvent(
            type="repair_cycle.systemic_analysis_completed",
            timestamp=now_iso(),
            source="repair_cycle",
            work_item_id="issue-123",
            workflow_run_id="run-456",
        )

        assert event.classification == FailureClassification.CODE_DEFECT
        assert event.confidence == 0.0
        assert event.reasoning == ""
        assert event.recommended_action == ""
        assert event.failure_count == 0

    def test_serialization(self):
        """Test SystemicAnalysisCompletedEvent serialization."""
        timestamp = now_iso()
        event = SystemicAnalysisCompletedEvent(
            type="repair_cycle.systemic_analysis_completed",
            timestamp=timestamp,
            source="repair_cycle",
            classification=FailureClassification.TRANSIENT_FAILURE,
            confidence=0.6,
            reasoning="Intermittent failures suggest flaky test or transient resource issue",
            recommended_action="Retry execution or investigate resource contention",
            work_item_id="issue-456",
            workflow_run_id="run-789",
            failure_count=7,
        )

        d = event.to_dict()
        assert d["classification"] == "transient_failure"
        assert d["confidence"] == 0.6
        assert d["reasoning"] == "Intermittent failures suggest flaky test or transient resource issue"
        assert d["recommended_action"] == "Retry execution or investigate resource contention"
        assert d["work_item_id"] == "issue-456"
        assert d["workflow_run_id"] == "run-789"
        assert d["failure_count"] == 7
        assert d["type"] == "repair_cycle.systemic_analysis_completed"
        assert d["timestamp"] == timestamp

    def test_deserialization(self):
        """Test SystemicAnalysisCompletedEvent deserialization."""
        timestamp = now_iso()
        d = {
            "type": "repair_cycle.systemic_analysis_completed",
            "timestamp": timestamp,
            "source": "repair_cycle",
            "classification": "dependency_issue",
            "confidence": 0.85,
            "reasoning": "Multiple dependencies fail to resolve",
            "recommended_action": "Update dependency versions",
            "work_item_id": "issue-789",
            "workflow_run_id": "run-111",
            "failure_count": 4,
        }

        event = SystemicAnalysisCompletedEvent.from_dict(d)
        assert event.classification == FailureClassification.DEPENDENCY_ISSUE
        assert event.confidence == 0.85
        assert event.reasoning == "Multiple dependencies fail to resolve"
        assert event.recommended_action == "Update dependency versions"
        assert event.work_item_id == "issue-789"
        assert event.workflow_run_id == "run-111"
        assert event.failure_count == 4

    def test_deserialization_missing_optional_fields(self):
        """Test deserialization with missing optional fields uses defaults."""
        d = {
            "type": "repair_cycle.systemic_analysis_completed",
            "timestamp": now_iso(),
            "source": "repair_cycle",
            "work_item_id": "issue-123",
            "workflow_run_id": "run-456",
        }

        event = SystemicAnalysisCompletedEvent.from_dict(d)
        assert event.classification == FailureClassification.CODE_DEFECT
        assert event.confidence == 0.0
        assert event.reasoning == ""
        assert event.recommended_action == ""
        assert event.failure_count == 0

    def test_round_trip_serialization(self):
        """Test that serialization round-trips through deserialization."""
        original = SystemicAnalysisCompletedEvent(
            type="repair_cycle.systemic_analysis_completed",
            timestamp=now_iso(),
            source="repair_cycle",
            classification=FailureClassification.CONFIGURATION_ISSUE,
            confidence=0.92,
            reasoning="Configuration mismatch between test environments",
            recommended_action="Standardize test configuration",
            work_item_id="issue-999",
            workflow_run_id="run-555",
            failure_count=8,
        )

        d = original.to_dict()
        restored = SystemicAnalysisCompletedEvent.from_dict(d)

        assert restored.classification == original.classification
        assert restored.confidence == original.confidence
        assert restored.reasoning == original.reasoning
        assert restored.recommended_action == original.recommended_action
        assert restored.work_item_id == original.work_item_id
        assert restored.workflow_run_id == original.workflow_run_id
        assert restored.failure_count == original.failure_count
        assert restored.timestamp == original.timestamp

    def test_confidence_boundary_values(self):
        """Test that confidence bounds are validated (0.0 to 1.0)."""
        # Test 0.0 (no confidence)
        event_zero = SystemicAnalysisCompletedEvent(
            type="repair_cycle.systemic_analysis_completed",
            timestamp=now_iso(),
            source="repair_cycle",
            classification=FailureClassification.ENVIRONMENT_ISSUE,
            confidence=0.0,
            work_item_id="issue-123",
            workflow_run_id="run-456",
        )
        assert event_zero.confidence == 0.0

        # Test 1.0 (full confidence)
        event_full = SystemicAnalysisCompletedEvent(
            type="repair_cycle.systemic_analysis_completed",
            timestamp=now_iso(),
            source="repair_cycle",
            classification=FailureClassification.CODE_DEFECT,
            confidence=1.0,
            work_item_id="issue-123",
            workflow_run_id="run-456",
        )
        assert event_full.confidence == 1.0

        # Test intermediate value
        event_mid = SystemicAnalysisCompletedEvent(
            type="repair_cycle.systemic_analysis_completed",
            timestamp=now_iso(),
            source="repair_cycle",
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.5,
            work_item_id="issue-123",
            workflow_run_id="run-456",
        )
        assert event_mid.confidence == 0.5

    def test_immutability(self):
        """Test that SystemicAnalysisCompletedEvent is immutable."""
        event = SystemicAnalysisCompletedEvent(
            type="repair_cycle.systemic_analysis_completed",
            timestamp=now_iso(),
            source="repair_cycle",
            classification=FailureClassification.CODE_DEFECT,
            confidence=0.95,
            reasoning="Test failure analysis",
            recommended_action="Fix code issue",
            work_item_id="issue-123",
            workflow_run_id="run-456",
            failure_count=5,
        )

        with pytest.raises(FrozenInstanceError):
            event.classification = FailureClassification.ENVIRONMENT_ISSUE  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.confidence = 0.8  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.reasoning = "Different reasoning"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.recommended_action = "Different action"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "issue-999"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.workflow_run_id = "run-999"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.failure_count = 10  # type: ignore

    def test_invalid_classification(self):
        """Test that invalid classification type raises ValueError."""
        with pytest.raises(ValueError, match="classification must be a FailureClassification"):
            SystemicAnalysisCompletedEvent(
                type="repair_cycle.systemic_analysis_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                classification="invalid_type",  # type: ignore
                confidence=0.5,
                work_item_id="issue-123",
                workflow_run_id="run-456",
            )

    def test_confidence_above_one(self):
        """Test that confidence > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            SystemicAnalysisCompletedEvent(
                type="repair_cycle.systemic_analysis_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                classification=FailureClassification.CODE_DEFECT,
                confidence=1.5,
                work_item_id="issue-123",
                workflow_run_id="run-456",
            )

    def test_confidence_below_zero(self):
        """Test that confidence < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            SystemicAnalysisCompletedEvent(
                type="repair_cycle.systemic_analysis_completed",
                timestamp=now_iso(),
                source="repair_cycle",
                classification=FailureClassification.CODE_DEFECT,
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
