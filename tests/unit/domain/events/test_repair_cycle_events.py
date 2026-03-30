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
    SystemicFixCompletedEvent,
    SystemicFixStartedEvent,
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
