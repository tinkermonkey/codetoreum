"""Tests for Repair Cycle domain events.

Tests cover:
- Immutability of frozen events
- Validation of repair cycle lifecycle events
- Serialization/deserialization
- Enum handling for RepairTestType
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.codetoreum.domain.events.repair_cycle_events import (
    RepairCycleStartedEvent,
    RepairCycleTestExecutionStartedEvent,
    RepairCycleTestExecutionCompletedEvent,
    RepairCycleFixCycleStartedEvent,
)
from src.codetoreum.domain.repair_cycle_types import (
    RepairTestType,
    RepairTestFailure,
    RepairTestResult,
)


def get_iso_timestamp():
    """Get current timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


def create_test_failure(file: str = "test_foo.py", test: str = "test_bar", message: str = "Error"):
    """Helper to create a RepairTestFailure."""
    return RepairTestFailure(file=file, test=test, message=message)


class TestRepairCycleStartedEvent:
    """Test cases for RepairCycleStartedEvent."""

    def test_create_event(self):
        """Test creating RepairCycleStartedEvent."""
        ts = get_iso_timestamp()
        event = RepairCycleStartedEvent(
            type="repair_cycle.started",
            timestamp=ts,
            source="mock",
            stage_name="fix_failures",
            test_types=(RepairTestType.UNIT, RepairTestType.INTEGRATION),
            workflow_run_id="run-123",
        )
        assert event.stage_name == "fix_failures"
        assert len(event.test_types) == 2
        assert event.test_types[0] == RepairTestType.UNIT
        assert event.workflow_run_id == "run-123"

    def test_immutability(self):
        """Test that event is immutable."""
        ts = get_iso_timestamp()
        event = RepairCycleStartedEvent(
            type="repair_cycle.started",
            timestamp=ts,
            source="mock",
            stage_name="fix_failures",
            test_types=(RepairTestType.UNIT,),
            workflow_run_id="run-123",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.stage_name = "new_stage"

    def test_validation_empty_stage_name(self):
        """Test validation fails for empty stage_name."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="stage_name is required"):
            RepairCycleStartedEvent(
                type="repair_cycle.started",
                timestamp=ts,
                source="mock",
                stage_name="",
                test_types=(RepairTestType.UNIT,),
                workflow_run_id="run-123",
            )

    def test_validation_empty_test_types(self):
        """Test validation fails for empty test_types."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="test_types must not be empty"):
            RepairCycleStartedEvent(
                type="repair_cycle.started",
                timestamp=ts,
                source="mock",
                stage_name="fix_failures",
                test_types=(),
                workflow_run_id="run-123",
            )

    def test_validation_empty_workflow_run_id(self):
        """Test validation fails for empty workflow_run_id."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="workflow_run_id is required"):
            RepairCycleStartedEvent(
                type="repair_cycle.started",
                timestamp=ts,
                source="mock",
                stage_name="fix_failures",
                test_types=(RepairTestType.UNIT,),
                workflow_run_id="",
            )

    def test_serialization_roundtrip(self):
        """Test to_dict / from_dict roundtrip."""
        ts = get_iso_timestamp()
        original = RepairCycleStartedEvent(
            type="repair_cycle.started",
            timestamp=ts,
            source="mock",
            stage_name="fix_failures",
            test_types=(RepairTestType.UNIT, RepairTestType.INTEGRATION),
            workflow_run_id="run-123",
        )
        data = original.to_dict()
        restored = RepairCycleStartedEvent.from_dict(data)
        assert restored.stage_name == original.stage_name
        assert restored.test_types == original.test_types
        assert restored.workflow_run_id == original.workflow_run_id

    def test_from_dict_multiple_test_types(self):
        """Test deserialization with multiple test types."""
        ts = get_iso_timestamp()
        data = {
            "type": "repair_cycle.started",
            "timestamp": ts,
            "source": "mock",
            "correlation_id": None,
            "event_id": str(uuid4()),
            "stage_name": "fix_failures",
            "test_types": ["UNIT", "INTEGRATION", "E2E"],
            "workflow_run_id": "run-123",
        }
        event = RepairCycleStartedEvent.from_dict(data)
        assert len(event.test_types) == 3
        assert event.test_types[2] == RepairTestType.E2E

    def test_from_dict_backward_compat_pipeline_run_id(self):
        """Test deserialization with deprecated pipeline_run_id field."""
        ts = get_iso_timestamp()
        data = {
            "type": "repair_cycle.started",
            "timestamp": ts,
            "source": "mock",
            "correlation_id": None,
            "event_id": str(uuid4()),
            "stage_name": "fix_failures",
            "test_types": ["UNIT"],
            "pipeline_run_id": "run-old",
        }
        with pytest.warns(DeprecationWarning):
            event = RepairCycleStartedEvent.from_dict(data)
        assert event.workflow_run_id == "run-old"


class TestRepairCycleTestExecutionStartedEvent:
    """Test cases for RepairCycleTestExecutionStartedEvent."""

    def test_create_event(self):
        """Test creating RepairCycleTestExecutionStartedEvent."""
        ts = get_iso_timestamp()
        event = RepairCycleTestExecutionStartedEvent(
            type="repair_cycle.test_execution_started",
            timestamp=ts,
            source="mock",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            test_cycle_iteration=1,
            max_test_cycle_iterations=3,
            timeout=300,
            workflow_run_id="run-123",
        )
        assert event.test_type == RepairTestType.UNIT
        assert event.test_type_index == 1
        assert event.timeout == 300

    def test_validation_test_type_index_min(self):
        """Test validation fails for test_type_index < 1."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="test_type_index must be >= 1"):
            RepairCycleTestExecutionStartedEvent(
                type="repair_cycle.test_execution_started",
                timestamp=ts,
                source="mock",
                test_type=RepairTestType.UNIT,
                test_type_index=0,
                test_cycle_iteration=1,
                max_test_cycle_iterations=3,
                timeout=300,
                workflow_run_id="run-123",
            )

    def test_validation_test_cycle_iteration_min(self):
        """Test validation fails for test_cycle_iteration < 1."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="test_cycle_iteration must be >= 1"):
            RepairCycleTestExecutionStartedEvent(
                type="repair_cycle.test_execution_started",
                timestamp=ts,
                source="mock",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=0,
                max_test_cycle_iterations=3,
                timeout=300,
                workflow_run_id="run-123",
            )

    def test_validation_max_iterations_min(self):
        """Test validation fails for max_test_cycle_iterations < 1."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="max_test_cycle_iterations must be >= 1"):
            RepairCycleTestExecutionStartedEvent(
                type="repair_cycle.test_execution_started",
                timestamp=ts,
                source="mock",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=1,
                max_test_cycle_iterations=0,
                timeout=300,
                workflow_run_id="run-123",
            )

    def test_validation_timeout_positive(self):
        """Test validation fails for timeout <= 0."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="timeout must be > 0"):
            RepairCycleTestExecutionStartedEvent(
                type="repair_cycle.test_execution_started",
                timestamp=ts,
                source="mock",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=1,
                max_test_cycle_iterations=3,
                timeout=0,
                workflow_run_id="run-123",
            )

    def test_validation_empty_workflow_run_id(self):
        """Test validation fails for empty workflow_run_id."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="workflow_run_id is required"):
            RepairCycleTestExecutionStartedEvent(
                type="repair_cycle.test_execution_started",
                timestamp=ts,
                source="mock",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=1,
                max_test_cycle_iterations=3,
                timeout=300,
                workflow_run_id="",
            )

    def test_serialization_roundtrip(self):
        """Test to_dict / from_dict roundtrip."""
        ts = get_iso_timestamp()
        original = RepairCycleTestExecutionStartedEvent(
            type="repair_cycle.test_execution_started",
            timestamp=ts,
            source="mock",
            test_type=RepairTestType.INTEGRATION,
            test_type_index=2,
            test_cycle_iteration=1,
            max_test_cycle_iterations=3,
            timeout=600,
            workflow_run_id="run-456",
        )
        data = original.to_dict()
        restored = RepairCycleTestExecutionStartedEvent.from_dict(data)
        assert restored.test_type == RepairTestType.INTEGRATION
        assert restored.test_type_index == 2
        assert restored.timeout == 600

    def test_from_dict_string_test_type(self):
        """Test deserialization with string test_type."""
        ts = get_iso_timestamp()
        data = {
            "type": "repair_cycle.test_execution_started",
            "timestamp": ts,
            "source": "mock",
            "correlation_id": None,
            "event_id": str(uuid4()),
            "test_type": "INTEGRATION",
            "test_type_index": 2,
            "test_cycle_iteration": 1,
            "max_test_cycle_iterations": 3,
            "timeout": 600,
            "workflow_run_id": "run-456",
        }
        event = RepairCycleTestExecutionStartedEvent.from_dict(data)
        assert event.test_type == RepairTestType.INTEGRATION


class TestRepairCycleTestExecutionCompletedEvent:
    """Test cases for RepairCycleTestExecutionCompletedEvent."""

    def test_create_event_with_failures(self):
        """Test creating event with test failures."""
        ts = get_iso_timestamp()
        failures = (create_test_failure("test_foo.py", "test_bar", "Expected 1 but got 2"),)
        event = RepairCycleTestExecutionCompletedEvent(
            type="repair_cycle.test_execution_completed",
            timestamp=ts,
            source="mock",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            test_cycle_iteration=1,
            passed=9,
            failed=1,
            warnings=0,
            has_failures=True,
            failures=failures,
            agent_name="code_review_agent",
            workflow_run_id="run-123",
        )
        assert event.failed == 1
        assert event.has_failures is True
        assert len(event.failures) == 1

    def test_create_event_with_success(self):
        """Test creating event with all tests passing."""
        ts = get_iso_timestamp()
        event = RepairCycleTestExecutionCompletedEvent(
            type="repair_cycle.test_execution_completed",
            timestamp=ts,
            source="mock",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            test_cycle_iteration=2,
            passed=10,
            failed=0,
            warnings=0,
            has_failures=False,
            failures=(),
            agent_name="code_review_agent",
            workflow_run_id="run-123",
        )
        assert event.passed == 10
        assert event.failed == 0
        assert event.has_failures is False

    def test_immutability(self):
        """Test that event is immutable."""
        ts = get_iso_timestamp()
        event = RepairCycleTestExecutionCompletedEvent(
            type="repair_cycle.test_execution_completed",
            timestamp=ts,
            source="mock",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            test_cycle_iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            has_failures=False,
            failures=(),
            agent_name="code_review_agent",
            workflow_run_id="run-123",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.passed = 5

    def test_validation_agent_name_required(self):
        """Test validation fails for empty agent_name."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="agent_name is required"):
            RepairCycleTestExecutionCompletedEvent(
                type="repair_cycle.test_execution_completed",
                timestamp=ts,
                source="mock",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=1,
                passed=10,
                failed=0,
                warnings=0,
                has_failures=False,
                failures=(),
                agent_name="",
                workflow_run_id="run-123",
            )

    def test_validation_has_failures_consistency(self):
        """Test validation fails when has_failures doesn't match failed count."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="has_failures.*must match failed"):
            RepairCycleTestExecutionCompletedEvent(
                type="repair_cycle.test_execution_completed",
                timestamp=ts,
                source="mock",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=1,
                passed=9,
                failed=1,
                warnings=0,
                has_failures=False,  # Inconsistent: failed=1 but has_failures=False
                failures=(),
                agent_name="code_review_agent",
                workflow_run_id="run-123",
            )

    def test_validation_failures_count_consistency(self):
        """Test validation fails when failures tuple length doesn't match failed count."""
        ts = get_iso_timestamp()
        failures = (create_test_failure(),)
        with pytest.raises(ValueError, match="failed count.*must match len\\(failures\\)"):
            RepairCycleTestExecutionCompletedEvent(
                type="repair_cycle.test_execution_completed",
                timestamp=ts,
                source="mock",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=1,
                passed=9,
                failed=2,  # But only 1 failure in tuple
                warnings=0,
                has_failures=True,
                failures=failures,
                agent_name="code_review_agent",
                workflow_run_id="run-123",
            )


class TestRepairCycleFixCycleStartedEvent:
    """Test cases for RepairCycleFixCycleStartedEvent."""

    def test_create_event(self):
        """Test creating RepairCycleFixCycleStartedEvent."""
        ts = get_iso_timestamp()
        event = RepairCycleFixCycleStartedEvent(
            type="repair_cycle.fix_cycle_started",
            timestamp=ts,
            source="mock",
            test_type=RepairTestType.UNIT,
            test_type_index=1,
            test_cycle_iteration=1,
            file_count=2,
            total_failures=3,
            workflow_run_id="run-123",
        )
        assert event.test_type == RepairTestType.UNIT
        assert event.file_count == 2
        assert event.total_failures == 3

    def test_validation_file_count_min(self):
        """Test that file_count must be >= 1."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="file_count must be >= 1"):
            RepairCycleFixCycleStartedEvent(
                type="repair_cycle.fix_cycle_started",
                timestamp=ts,
                source="mock",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=1,
                file_count=0,
                total_failures=1,
                workflow_run_id="run-123",
            )

    def test_validation_total_failures_min(self):
        """Test that total_failures must be >= 1."""
        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="total_failures must be >= 1"):
            RepairCycleFixCycleStartedEvent(
                type="repair_cycle.fix_cycle_started",
                timestamp=ts,
                source="mock",
                test_type=RepairTestType.UNIT,
                test_type_index=1,
                test_cycle_iteration=1,
                file_count=1,
                total_failures=0,
                workflow_run_id="run-123",
            )


class TestRepairCycleCompletedEvent:
    """Test cases for RepairCycleCompletedEvent validation."""

    def test_validation_test_results_required(self):
        """Test that test_results cannot be empty."""
        from src.codetoreum.domain.events.repair_cycle_events import RepairCycleCompletedEvent

        ts = get_iso_timestamp()
        with pytest.raises(ValueError, match="test_results must not be empty"):
            RepairCycleCompletedEvent(
                type="repair_cycle.completed",
                timestamp=ts,
                source="mock",
                overall_success=True,
                test_results=(),
                total_agent_calls=5,
                duration_seconds=300.0,
                workflow_run_id="run-123",
            )

    def test_validation_workflow_run_id_required(self):
        """Test that workflow_run_id is required."""
        from src.codetoreum.domain.events.repair_cycle_events import RepairCycleCompletedEvent
        from src.codetoreum.domain.repair_cycle_types import CycleResult

        ts = get_iso_timestamp()
        # Create a minimal CycleResult for testing
        test_result = RepairTestResult(
            test_type=RepairTestType.UNIT,
            iteration=1,
            passed=10,
            failed=0,
            warnings=0,
            failures=(),
            warning_list=(),
            raw_output="All tests passed",
            timestamp=ts,
        )
        cycle_result = CycleResult(
            test_type=RepairTestType.UNIT,
            passed=True,
            iterations=1,
            final_result=test_result,
            error=None,
            files_fixed=0,
            warnings_reviewed=0,
            duration_seconds=10.0,
        )
        with pytest.raises(ValueError, match="workflow_run_id is required"):
            RepairCycleCompletedEvent(
                type="repair_cycle.completed",
                timestamp=ts,
                source="mock",
                overall_success=True,
                test_results=(cycle_result,),
                total_agent_calls=5,
                duration_seconds=300.0,
                workflow_run_id="",
            )
