"""
Tests for Audit DTOs
"""

from datetime import datetime, timezone
import pytest
from codetoreum.adapters.primary.audit_dtos import (
    OutOfOrderEvent,
    AuditValidationResult,
    AuditStageInfo,
    WorkflowRunAuditResponse,
)
from codetoreum.adapters.primary.workflow_run_dtos import (
    WorkflowRunSummaryResponse,
    WorkflowEventResponse,
)


class TestOutOfOrderEvent:
    """Tests for OutOfOrderEvent DTO."""

    def test_out_of_order_event_creation(self):
        """Test creating OutOfOrderEvent."""
        event = OutOfOrderEvent(
            eventType="WorkflowStageAdvanced",
            timestamp=datetime(2025, 11, 8, 10, 15, 0, tzinfo=timezone.utc),
            expectedPosition=5,
            actualPosition=3
        )

        assert event.eventType == "WorkflowStageAdvanced"
        assert event.expectedPosition == 5
        assert event.actualPosition == 3

    def test_out_of_order_event_serialization(self):
        """Test OutOfOrderEvent serialization with camelCase."""
        event = OutOfOrderEvent(
            eventType="WorkflowStageAdvanced",
            timestamp=datetime(2025, 11, 8, 10, 15, 0, tzinfo=timezone.utc),
            expectedPosition=5,
            actualPosition=3
        )

        data = event.model_dump(by_alias=True, mode='json')
        assert "eventType" in data
        assert "expectedPosition" in data
        assert "actualPosition" in data

    def test_out_of_order_event_with_none_timestamp(self):
        """Test OutOfOrderEvent with optional timestamp=None."""
        event = OutOfOrderEvent(
            eventType="WorkflowStageAdvanced",
            timestamp=None,
            expectedPosition=5,
            actualPosition=3
        )

        assert event.eventType == "WorkflowStageAdvanced"
        assert event.timestamp is None
        assert event.expectedPosition == 5
        assert event.actualPosition == 3

        # Verify serialization works with None timestamp
        data = event.model_dump(by_alias=True, mode='json')
        assert data["eventType"] == "WorkflowStageAdvanced"
        assert data["timestamp"] is None
        assert data["expectedPosition"] == 5
        assert data["actualPosition"] == 3


class TestAuditValidationResult:
    """Tests for AuditValidationResult DTO."""

    def test_validation_result_valid_sequence(self):
        """Test validation result for valid sequence."""
        result = AuditValidationResult(
            sequenceValid=True,
            expectedSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
            actualSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
            missingEvents=[],
            unexpectedEvents=[],
            outOfOrderEvents=[]
        )

        assert result.sequenceValid is True
        assert len(result.expectedSequence) == 3
        assert len(result.missingEvents) == 0
        assert len(result.unexpectedEvents) == 0
        assert len(result.outOfOrderEvents) == 0

    def test_validation_result_rejects_sequence_valid_with_missing_events(self):
        """Test that sequenceValid=True is rejected when missingEvents is non-empty."""
        with pytest.raises(ValueError, match="sequenceValid is True but error lists are not empty"):
            AuditValidationResult(
                sequenceValid=True,
                expectedSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
                actualSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
                missingEvents=["WorkflowStageAdvanced"],
                unexpectedEvents=[],
                outOfOrderEvents=[]
            )

    def test_validation_result_rejects_sequence_valid_with_unexpected_events(self):
        """Test that sequenceValid=True is rejected when unexpectedEvents is non-empty."""
        with pytest.raises(ValueError, match="sequenceValid is True but error lists are not empty"):
            AuditValidationResult(
                sequenceValid=True,
                expectedSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
                actualSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
                missingEvents=[],
                unexpectedEvents=["UnexpectedEvent"],
                outOfOrderEvents=[]
            )

    def test_validation_result_rejects_sequence_valid_with_out_of_order_events(self):
        """Test that sequenceValid=True is rejected when outOfOrderEvents is non-empty."""
        out_of_order = OutOfOrderEvent(
            eventType="WorkflowStageAdvanced",
            timestamp=datetime(2025, 11, 8, 10, 15, 0, tzinfo=timezone.utc),
            expectedPosition=2,
            actualPosition=1
        )

        with pytest.raises(ValueError, match="sequenceValid is True but error lists are not empty"):
            AuditValidationResult(
                sequenceValid=True,
                expectedSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
                actualSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
                missingEvents=[],
                unexpectedEvents=[],
                outOfOrderEvents=[out_of_order]
            )

    def test_validation_result_invalid_sequence(self):
        """Test validation result for invalid sequence."""
        out_of_order = OutOfOrderEvent(
            eventType="WorkflowStageAdvanced",
            timestamp=datetime(2025, 11, 8, 10, 15, 0, tzinfo=timezone.utc),
            expectedPosition=2,
            actualPosition=1
        )

        result = AuditValidationResult(
            sequenceValid=False,
            expectedSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowStageAdvanced"],
            actualSequence=["WorkflowCreated", "WorkflowStageAdvanced", "WorkflowStarted"],
            missingEvents=[],
            unexpectedEvents=[],
            outOfOrderEvents=[out_of_order]
        )

        assert result.sequenceValid is False
        assert len(result.outOfOrderEvents) == 1
        assert result.outOfOrderEvents[0].eventType == "WorkflowStageAdvanced"

    def test_validation_result_missing_events(self):
        """Test validation result with missing events."""
        result = AuditValidationResult(
            sequenceValid=False,
            expectedSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
            actualSequence=["WorkflowCreated", "WorkflowCompleted"],
            missingEvents=["WorkflowStarted"],
            unexpectedEvents=[],
            outOfOrderEvents=[]
        )

        assert result.sequenceValid is False
        assert len(result.missingEvents) == 1
        assert "WorkflowStarted" in result.missingEvents

    def test_validation_result_unexpected_events(self):
        """Test validation result with unexpected events."""
        result = AuditValidationResult(
            sequenceValid=False,
            expectedSequence=["WorkflowCreated", "WorkflowCompleted"],
            actualSequence=["WorkflowCreated", "UnexpectedEvent", "WorkflowCompleted"],
            missingEvents=[],
            unexpectedEvents=["UnexpectedEvent"],
            outOfOrderEvents=[]
        )

        assert result.sequenceValid is False
        assert len(result.unexpectedEvents) == 1
        assert "UnexpectedEvent" in result.unexpectedEvents

    def test_validation_result_serialization(self):
        """Test AuditValidationResult serialization with camelCase."""
        result = AuditValidationResult(
            sequenceValid=True,
            expectedSequence=["WorkflowCreated"],
            actualSequence=["WorkflowCreated"],
            missingEvents=[],
            unexpectedEvents=[],
            outOfOrderEvents=[]
        )

        data = result.model_dump(by_alias=True, mode='json')
        assert "sequenceValid" in data
        assert "expectedSequence" in data
        assert "actualSequence" in data
        assert "missingEvents" in data
        assert "unexpectedEvents" in data
        assert "outOfOrderEvents" in data


class TestAuditStageInfo:
    """Tests for AuditStageInfo DTO."""

    def test_audit_stage_info_completed(self):
        """Test AuditStageInfo for completed stage."""
        event = WorkflowEventResponse(
            id="evt-123",
            eventType="ExecutionStarted",
            workflowRunId="wfrun-123",
            timestamp=datetime(2025, 11, 8, 10, 0, 0, tzinfo=timezone.utc),
            agentName="developer_agent",
            stageName="implementation",
            status=None,
            data={}
        )

        stage = AuditStageInfo(
            name="implementation",
            status="completed",
            startedAt=datetime(2025, 11, 8, 10, 0, 0, tzinfo=timezone.utc),
            completedAt=datetime(2025, 11, 8, 10, 15, 0, tzinfo=timezone.utc),
            durationSeconds=900.0,
            events=[event]
        )

        assert stage.name == "implementation"
        assert stage.status == "completed"
        assert stage.durationSeconds == 900.0
        assert len(stage.events) == 1

    def test_audit_stage_info_running(self):
        """Test AuditStageInfo for running stage."""
        stage = AuditStageInfo(
            name="review",
            status="running",
            startedAt=datetime(2025, 11, 8, 10, 15, 0, tzinfo=timezone.utc),
            completedAt=None,
            durationSeconds=None,
            events=[]
        )

        assert stage.name == "review"
        assert stage.status == "running"
        assert stage.completedAt is None
        assert stage.durationSeconds is None

    def test_audit_stage_info_serialization(self):
        """Test AuditStageInfo serialization with camelCase."""
        stage = AuditStageInfo(
            name="implementation",
            status="completed",
            startedAt=datetime(2025, 11, 8, 10, 0, 0, tzinfo=timezone.utc),
            completedAt=datetime(2025, 11, 8, 10, 15, 0, tzinfo=timezone.utc),
            durationSeconds=900.0,
            events=[]
        )

        data = stage.model_dump(by_alias=True, mode='json')
        assert "startedAt" in data
        assert "completedAt" in data
        assert "durationSeconds" in data

    def test_audit_stage_info_rejects_completed_before_started(self):
        """Test that AuditStageInfo rejects completedAt < startedAt."""
        with pytest.raises(ValueError, match="completedAt .* must be >= startedAt"):
            AuditStageInfo(
                name="implementation",
                status="completed",
                startedAt=datetime(2025, 11, 8, 10, 15, 0, tzinfo=timezone.utc),
                completedAt=datetime(2025, 11, 8, 10, 0, 0, tzinfo=timezone.utc),
                durationSeconds=900.0,
                events=[]
            )

    def test_audit_stage_info_allows_same_start_and_completion(self):
        """Test that AuditStageInfo allows completedAt == startedAt."""
        same_time = datetime(2025, 11, 8, 10, 0, 0, tzinfo=timezone.utc)
        stage = AuditStageInfo(
            name="implementation",
            status="completed",
            startedAt=same_time,
            completedAt=same_time,
            durationSeconds=0.0,
            events=[]
        )

        assert stage.startedAt == stage.completedAt


class TestWorkflowRunAuditResponse:
    """Tests for WorkflowRunAuditResponse DTO."""

    def test_audit_response_complete(self):
        """Test complete audit response."""
        workflow_run = WorkflowRunSummaryResponse(
            id="wfrun-123",
            workItemId="wi-456",
            workflowId="wf-789",
            projectId="proj-1",
            status="completed",
            currentStageIndex=2,
            currentStageName="review",
            startedAt=datetime(2025, 11, 8, 10, 0, 0, tzinfo=timezone.utc),
            completedAt=datetime(2025, 11, 8, 10, 30, 0, tzinfo=timezone.utc),
            duration=1800,
            issueTitle="Fix authentication bug",
            issueNumber=42,
            project="codetoreum",
            triggeredBy="github_webhook",
            priority="high"
        )

        event = WorkflowEventResponse(
            id="evt-123",
            eventType="WorkflowStarted",
            workflowRunId="wfrun-123",
            timestamp=datetime(2025, 11, 8, 10, 0, 0, tzinfo=timezone.utc),
            agentName=None,
            stageName=None,
            status=None,
            data={}
        )

        stage = AuditStageInfo(
            name="implementation",
            status="completed",
            startedAt=datetime(2025, 11, 8, 10, 0, 0, tzinfo=timezone.utc),
            completedAt=datetime(2025, 11, 8, 10, 15, 0, tzinfo=timezone.utc),
            durationSeconds=900.0,
            events=[]
        )

        validation = AuditValidationResult(
            sequenceValid=True,
            expectedSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
            actualSequence=["WorkflowCreated", "WorkflowStarted", "WorkflowCompleted"],
            missingEvents=[],
            unexpectedEvents=[],
            outOfOrderEvents=[]
        )

        response = WorkflowRunAuditResponse(
            workflowRun=workflow_run,
            events=[event],
            stages=[stage],
            validation=validation,
            totalEventCount=15,
            offset=0,
            limit=100,
            hasNext=False
        )

        assert response.workflowRun.id == "wfrun-123"
        assert len(response.events) == 1
        assert len(response.stages) == 1
        assert response.validation.sequenceValid is True
        assert response.totalEventCount == 15
        assert response.hasNext is False

    def test_audit_response_pagination(self):
        """Test audit response with pagination."""
        workflow_run = WorkflowRunSummaryResponse(
            id="wfrun-123",
            workItemId="wi-456",
            workflowId="wf-789",
            projectId="proj-1",
            status="running",
            currentStageIndex=1,
            currentStageName="implementation"
        )

        validation = AuditValidationResult(
            sequenceValid=True,
            expectedSequence=["WorkflowCreated", "WorkflowStarted"],
            actualSequence=["WorkflowCreated", "WorkflowStarted"],
            missingEvents=[],
            unexpectedEvents=[],
            outOfOrderEvents=[]
        )

        response = WorkflowRunAuditResponse(
            workflowRun=workflow_run,
            events=[],
            stages=[],
            validation=validation,
            totalEventCount=150,
            offset=100,
            limit=50,
            hasNext=True
        )

        assert response.totalEventCount == 150
        assert response.offset == 100
        assert response.limit == 50
        assert response.hasNext is True

    def test_audit_response_serialization(self):
        """Test WorkflowRunAuditResponse serialization with camelCase."""
        workflow_run = WorkflowRunSummaryResponse(
            id="wfrun-123",
            workItemId="wi-456",
            workflowId="wf-789",
            projectId="proj-1",
            status="completed",
            currentStageIndex=0,
            currentStageName="implementation"
        )

        validation = AuditValidationResult(
            sequenceValid=True,
            expectedSequence=["WorkflowCreated"],
            actualSequence=["WorkflowCreated"],
            missingEvents=[],
            unexpectedEvents=[],
            outOfOrderEvents=[]
        )

        response = WorkflowRunAuditResponse(
            workflowRun=workflow_run,
            events=[],
            stages=[],
            validation=validation,
            totalEventCount=10,
            offset=0,
            limit=100,
            hasNext=False
        )

        data = response.model_dump(by_alias=True, mode='json')
        assert "workflowRun" in data
        assert "totalEventCount" in data
        assert "hasNext" in data

    def test_audit_response_reuses_existing_dtos(self):
        """Test that audit response correctly reuses existing DTOs."""
        workflow_run = WorkflowRunSummaryResponse(
            id="wfrun-123",
            workItemId="wi-456",
            workflowId="wf-789",
            projectId="proj-1",
            status="completed",
            currentStageIndex=0,
            currentStageName="implementation"
        )

        event = WorkflowEventResponse(
            id="evt-123",
            eventType="WorkflowStarted",
            workflowRunId="wfrun-123",
            timestamp=datetime(2025, 11, 8, 10, 0, 0, tzinfo=timezone.utc),
            data={}
        )

        validation = AuditValidationResult(
            sequenceValid=True,
            expectedSequence=["WorkflowCreated"],
            actualSequence=["WorkflowCreated"],
            missingEvents=[],
            unexpectedEvents=[],
            outOfOrderEvents=[]
        )

        response = WorkflowRunAuditResponse(
            workflowRun=workflow_run,
            events=[event],
            stages=[],
            validation=validation,
            totalEventCount=1,
            offset=0,
            limit=100,
            hasNext=False
        )

        # Verify types are correct
        assert isinstance(response.workflowRun, WorkflowRunSummaryResponse)
        assert isinstance(response.events[0], WorkflowEventResponse)
