"""Unit tests for domain events."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from codetoreum.domain.events import (
    AgentAssigned,
    AgentCapabilityAdded,
    AgentCreated,
    AgentModelUpdated,
    DomainEvent,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionInitialized,
    ExecutionStarted,
    ProjectContextCreated,
    ProjectDockerConfigUpdated,
    ProjectTestConfigUpdated,
    ProjectWorkflowMappingAdded,
    ReviewCycleApproved,
    ReviewCycleCreated,
    ReviewCycleEscalated,
    ReviewFeedbackSubmitted,
    ReviewIterationStarted,
    WorkflowCompleted,
    WorkflowCreated,
    WorkflowStageAdvanced,
    WorkItemBlocked,
    WorkItemCompleted,
    WorkItemCreated,
    WorkItemFailed,
    WorkItemLabelsUpdated,
    WorkItemStarted,
)

# =============================================================================
# Base DomainEvent Tests
# =============================================================================


class TestDomainEvent:
    """Tests for the base DomainEvent class."""

    def test_initialization_with_defaults(self):
        """Test event initialization with default values."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
            payload={"key": "value"},
        )

        assert event.aggregate_id == "test-123"
        assert event.aggregate_type == "TestAggregate"
        assert event.payload == {"key": "value"}
        assert event.event_type == "DomainEvent"
        assert event.event_version == 1
        assert isinstance(event.event_id, UUID)
        assert isinstance(event.occurred_at, datetime)
        assert isinstance(event.correlation_id, UUID)
        assert event.causation_id is None
        assert event.user_id is None
        assert event.metadata == {}

    def test_initialization_with_custom_values(self):
        """Test event initialization with custom values."""
        event_id = uuid4()
        correlation_id = uuid4()
        causation_id = uuid4()
        occurred_at = datetime.now(UTC)

        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
            payload={"key": "value"},
            user_id="user-456",
            correlation_id=correlation_id,
            causation_id=causation_id,
            event_id=event_id,
            occurred_at=occurred_at,
        )

        assert event.event_id == event_id
        assert event.correlation_id == correlation_id
        assert event.causation_id == causation_id
        assert event.occurred_at == occurred_at
        assert event.user_id == "user-456"

    def test_to_dict_serialization(self):
        """Test event serialization to dictionary."""
        event_id = uuid4()
        correlation_id = uuid4()
        causation_id = uuid4()
        occurred_at = datetime.now(UTC)

        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
            payload={"key": "value"},
            user_id="user-456",
            correlation_id=correlation_id,
            causation_id=causation_id,
            event_id=event_id,
            occurred_at=occurred_at,
        )
        event.metadata = {"source": "test"}

        event_dict = event.to_dict()

        assert event_dict["event_id"] == str(event_id)
        assert event_dict["event_type"] == "DomainEvent"
        assert event_dict["event_version"] == 1
        assert event_dict["aggregate_id"] == "test-123"
        assert event_dict["aggregate_type"] == "TestAggregate"
        assert event_dict["occurred_at"] == occurred_at.isoformat()
        assert event_dict["correlation_id"] == str(correlation_id)
        assert event_dict["causation_id"] == str(causation_id)
        assert event_dict["user_id"] == "user-456"
        assert event_dict["payload"] == {"key": "value"}
        assert event_dict["metadata"] == {"source": "test"}

    def test_to_dict_with_none_values(self):
        """Test serialization with None values."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        event_dict = event.to_dict()

        assert event_dict["user_id"] is None
        assert event_dict["causation_id"] is None
        assert event_dict["correlation_id"] is not None  # Auto-generated

    def test_from_dict_deserialization(self):
        """Test event deserialization from dictionary."""
        event_id = str(uuid4())
        correlation_id = str(uuid4())
        causation_id = str(uuid4())
        occurred_at = datetime.now(UTC).isoformat()

        event_dict = {
            "event_id": event_id,
            "event_type": "DomainEvent",
            "event_version": 1,
            "aggregate_id": "test-123",
            "aggregate_type": "TestAggregate",
            "occurred_at": occurred_at,
            "correlation_id": correlation_id,
            "causation_id": causation_id,
            "user_id": "user-456",
            "payload": {"key": "value"},
            "metadata": {"source": "test"},
        }

        event = DomainEvent.from_dict(event_dict)

        assert str(event.event_id) == event_id
        assert event.aggregate_id == "test-123"
        assert event.aggregate_type == "TestAggregate"
        assert event.occurred_at.isoformat() == occurred_at
        assert str(event.correlation_id) == correlation_id
        assert str(event.causation_id) == causation_id
        assert event.user_id == "user-456"
        assert event.payload == {"key": "value"}

    def test_from_dict_with_missing_optional_fields(self):
        """Test deserialization with missing optional fields."""
        event_dict = {
            "aggregate_id": "test-123",
            "aggregate_type": "TestAggregate",
            "occurred_at": datetime.now(UTC).isoformat(),
        }

        event = DomainEvent.from_dict(event_dict)

        assert event.aggregate_id == "test-123"
        assert event.aggregate_type == "TestAggregate"
        assert event.user_id is None
        assert event.causation_id is None
        assert event.payload == {}

    def test_from_dict_with_missing_required_fields(self):
        """Test deserialization with missing required fields."""
        event_dict = {
            "aggregate_id": "test-123",
            # Missing aggregate_type
        }

        with pytest.raises(ValueError, match="Missing required field"):
            DomainEvent.from_dict(event_dict)

    def test_from_dict_with_invalid_uuid(self):
        """Test deserialization with invalid UUID."""
        event_dict = {
            "aggregate_id": "test-123",
            "aggregate_type": "TestAggregate",
            "event_id": "invalid-uuid",
        }

        with pytest.raises(ValueError, match="Invalid field value"):
            DomainEvent.from_dict(event_dict)

    def test_round_trip_serialization(self):
        """Test that serialization and deserialization are reversible."""
        original_event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
            payload={"key": "value"},
            user_id="user-456",
        )
        original_event.metadata = {"source": "test"}

        # Serialize and deserialize
        event_dict = original_event.to_dict()
        restored_event = DomainEvent.from_dict(event_dict)

        # Compare key attributes
        assert str(restored_event.event_id) == event_dict["event_id"]
        assert restored_event.aggregate_id == original_event.aggregate_id
        assert restored_event.aggregate_type == original_event.aggregate_type
        assert restored_event.user_id == original_event.user_id
        assert restored_event.payload == original_event.payload

    def test_equality_same_event_id(self):
        """Test that events with same event_id are equal."""
        event_id = uuid4()

        event1 = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
            event_id=event_id,
        )

        event2 = DomainEvent(
            aggregate_id="test-456",  # Different aggregate_id
            aggregate_type="DifferentAggregate",
            event_id=event_id,  # Same event_id
        )

        assert event1 == event2

    def test_equality_different_event_id(self):
        """Test that events with different event_id are not equal."""
        event1 = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        event2 = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        assert event1 != event2

    def test_equality_with_non_event(self):
        """Test equality comparison with non-event object."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        assert event != "not an event"
        assert event != 123
        assert event is not None

    def test_hash_consistency(self):
        """Test that hash is consistent for same event."""
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        hash1 = hash(event)
        hash2 = hash(event)

        assert hash1 == hash2

    def test_hash_different_for_different_events(self):
        """Test that different events have different hashes."""
        event1 = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        event2 = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        assert hash(event1) != hash(event2)

    def test_events_in_set(self):
        """Test that events can be used in sets."""
        event1 = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        event2 = DomainEvent(
            aggregate_id="test-456",
            aggregate_type="TestAggregate",
        )

        event_set = {event1, event2}

        assert len(event_set) == 2
        assert event1 in event_set
        assert event2 in event_set

    def test_events_in_dict(self):
        """Test that events can be used as dict keys."""
        event1 = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        event2 = DomainEvent(
            aggregate_id="test-456",
            aggregate_type="TestAggregate",
        )

        event_dict = {event1: "value1", event2: "value2"}

        assert event_dict[event1] == "value1"
        assert event_dict[event2] == "value2"


# =============================================================================
# Work Item Event Tests
# =============================================================================


class TestWorkItemEvents:
    """Tests for WorkItem domain events."""

    def test_work_item_created(self):
        """Test WorkItemCreated event."""
        payload = {
            "title": "Test Work Item",
            "description": "Test description",
            "project_id": "proj-123",
            "labels": ["bug", "high-priority"],
            "priority": 1,
        }

        event = WorkItemCreated(
            aggregate_id="work-123",
            payload=payload,
            user_id="user-456",
        )

        assert event.aggregate_id == "work-123"
        assert event.aggregate_type == "WorkItem"
        assert event.event_type == "WorkItemCreated"
        assert event.payload == payload
        assert event.user_id == "user-456"

    def test_agent_assigned(self):
        """Test AgentAssigned event."""
        payload = {
            "agent_id": "agent-123",
            "reason": "Best match for task",
            "assigned_at": datetime.now(UTC).isoformat(),
        }

        event = AgentAssigned(
            aggregate_id="work-123",
            payload=payload,
        )

        assert event.aggregate_type == "WorkItem"
        assert event.event_type == "AgentAssigned"
        assert event.payload["agent_id"] == "agent-123"

    def test_work_item_started(self):
        """Test WorkItemStarted event."""
        payload = {
            "started_at": datetime.now(UTC).isoformat(),
            "agent_id": "agent-123",
        }

        event = WorkItemStarted(
            aggregate_id="work-123",
            payload=payload,
        )

        assert event.event_type == "WorkItemStarted"
        assert event.aggregate_type == "WorkItem"

    def test_work_item_completed(self):
        """Test WorkItemCompleted event."""
        payload = {
            "completed_at": datetime.now(UTC).isoformat(),
            "agent_id": "agent-123",
        }

        event = WorkItemCompleted(
            aggregate_id="work-123",
            payload=payload,
        )

        assert event.event_type == "WorkItemCompleted"
        assert event.aggregate_type == "WorkItem"

    def test_work_item_failed(self):
        """Test WorkItemFailed event."""
        payload = {
            "failed_at": datetime.now(UTC).isoformat(),
            "reason": "Timeout exceeded",
            "error_details": {"code": "TIMEOUT", "message": "Agent timed out"},
            "agent_id": "agent-123",
        }

        event = WorkItemFailed(
            aggregate_id="work-123",
            payload=payload,
        )

        assert event.event_type == "WorkItemFailed"
        assert event.payload["reason"] == "Timeout exceeded"

    def test_work_item_blocked(self):
        """Test WorkItemBlocked event."""
        payload = {
            "blocked_at": datetime.now(UTC).isoformat(),
            "reason": "Dependency not met",
            "blocking_issue_id": "issue-456",
        }

        event = WorkItemBlocked(
            aggregate_id="work-123",
            payload=payload,
        )

        assert event.event_type == "WorkItemBlocked"
        assert event.payload["blocking_issue_id"] == "issue-456"

    def test_work_item_labels_updated(self):
        """Test WorkItemLabelsUpdated event."""
        payload = {
            "old_labels": ["bug"],
            "new_labels": ["bug", "high-priority"],
            "updated_at": datetime.now(UTC).isoformat(),
        }

        event = WorkItemLabelsUpdated(
            aggregate_id="work-123",
            payload=payload,
        )

        assert event.event_type == "WorkItemLabelsUpdated"
        assert len(event.payload["new_labels"]) == 2


# =============================================================================
# Agent Event Tests
# =============================================================================


class TestAgentEvents:
    """Tests for Agent domain events."""

    def test_agent_created(self):
        """Test AgentCreated event."""
        payload = {
            "name": "test-agent",
            "display_name": "Test Agent",
            "agent_type": "coding",
            "model": "claude-3-sonnet",
            "capabilities": ["python", "testing"],
        }

        event = AgentCreated(
            aggregate_id="agent-123",
            payload=payload,
        )

        assert event.aggregate_type == "Agent"
        assert event.event_type == "AgentCreated"
        assert event.payload["name"] == "test-agent"

    def test_agent_capability_added(self):
        """Test AgentCapabilityAdded event."""
        payload = {
            "skill": "rust",
            "proficiency": 0.8,
            "added_at": datetime.now(UTC).isoformat(),
        }

        event = AgentCapabilityAdded(
            aggregate_id="agent-123",
            payload=payload,
        )

        assert event.event_type == "AgentCapabilityAdded"
        assert event.payload["skill"] == "rust"

    def test_agent_model_updated(self):
        """Test AgentModelUpdated event."""
        payload = {
            "old_model": "claude-3-sonnet",
            "new_model": "claude-3-opus",
            "updated_at": datetime.now(UTC).isoformat(),
        }

        event = AgentModelUpdated(
            aggregate_id="agent-123",
            payload=payload,
        )

        assert event.event_type == "AgentModelUpdated"
        assert event.payload["new_model"] == "claude-3-opus"


# =============================================================================
# Execution Event Tests
# =============================================================================


class TestExecutionEvents:
    """Tests for AgentExecution domain events."""

    def test_execution_initialized(self):
        """Test ExecutionInitialized event."""
        payload = {
            "agent_id": "agent-123",
            "work_item_id": "work-123",
            "workflow_id": "workflow-123",
            "stage_name": "implementation",
            "model": "claude-3-sonnet",
        }

        event = ExecutionInitialized(
            aggregate_id="exec-123",
            payload=payload,
        )

        assert event.aggregate_type == "AgentExecution"
        assert event.event_type == "ExecutionInitialized"

    def test_execution_started(self):
        """Test ExecutionStarted event."""
        payload = {
            "started_at": datetime.now(UTC).isoformat(),
            "container_name": "container-123",
        }

        event = ExecutionStarted(
            aggregate_id="exec-123",
            payload=payload,
        )

        assert event.event_type == "ExecutionStarted"

    def test_execution_completed(self):
        """Test ExecutionCompleted event."""
        payload = {
            "completed_at": datetime.now(UTC).isoformat(),
            "input_tokens": 1000,
            "output_tokens": 500,
            "duration_seconds": 45.5,
        }

        event = ExecutionCompleted(
            aggregate_id="exec-123",
            payload=payload,
        )

        assert event.event_type == "ExecutionCompleted"
        assert event.payload["input_tokens"] == 1000

    def test_execution_failed(self):
        """Test ExecutionFailed event."""
        payload = {
            "failed_at": datetime.now(UTC).isoformat(),
            "error_message": "Container crashed",
            "exit_code": 1,
            "duration_seconds": 10.5,
        }

        event = ExecutionFailed(
            aggregate_id="exec-123",
            payload=payload,
        )

        assert event.event_type == "ExecutionFailed"
        assert event.payload["exit_code"] == 1


# =============================================================================
# Workflow Event Tests
# =============================================================================


class TestWorkflowEvents:
    """Tests for Workflow domain events."""

    def test_workflow_created(self):
        """Test WorkflowCreated event."""
        payload = {
            "work_item_id": "work-123",
            "template_id": "template-123",
            "project_id": "proj-123",
            "stage_count": 3,
        }

        event = WorkflowCreated(
            aggregate_id="workflow-123",
            payload=payload,
        )

        assert event.aggregate_type == "Workflow"
        assert event.event_type == "WorkflowCreated"

    def test_workflow_stage_advanced(self):
        """Test WorkflowStageAdvanced event."""
        payload = {
            "from_stage": "implementation",
            "to_stage": "testing",
            "stage_index": 1,
            "advanced_at": datetime.now(UTC).isoformat(),
        }

        event = WorkflowStageAdvanced(
            aggregate_id="workflow-123",
            payload=payload,
        )

        assert event.event_type == "WorkflowStageAdvanced"
        assert event.payload["to_stage"] == "testing"

    def test_workflow_completed(self):
        """Test WorkflowCompleted event."""
        payload = {
            "completed_at": datetime.now(UTC).isoformat(),
            "work_item_id": "work-123",
            "duration_seconds": 300.5,
        }

        event = WorkflowCompleted(
            aggregate_id="workflow-123",
            payload=payload,
        )

        assert event.event_type == "WorkflowCompleted"
        assert event.payload["duration_seconds"] == 300.5


# =============================================================================
# Review Cycle Event Tests
# =============================================================================


class TestReviewCycleEvents:
    """Tests for ReviewCycle domain events."""

    def test_review_cycle_created(self):
        """Test ReviewCycleCreated event."""
        payload = {
            "work_item_id": "work-123",
            "workflow_id": "workflow-123",
            "stage_name": "review",
            "execution_id": "exec-123",
            "max_iterations": 3,
            "review_type": "automated",
        }

        event = ReviewCycleCreated(
            aggregate_id="review-123",
            payload=payload,
        )

        assert event.aggregate_type == "ReviewCycle"
        assert event.event_type == "ReviewCycleCreated"
        assert event.payload["max_iterations"] == 3

    def test_review_iteration_started(self):
        """Test ReviewIterationStarted event."""
        payload = {
            "iteration_number": 1,
            "started_at": datetime.now(UTC).isoformat(),
            "reviewer_agent_id": "agent-456",
        }

        event = ReviewIterationStarted(
            aggregate_id="review-123",
            payload=payload,
        )

        assert event.event_type == "ReviewIterationStarted"
        assert event.payload["iteration_number"] == 1

    def test_review_feedback_submitted(self):
        """Test ReviewFeedbackSubmitted event."""
        payload = {
            "iteration_number": 1,
            "submitted_at": datetime.now(UTC).isoformat(),
            "feedback": "Please fix the error handling",
            "decision": "needs_changes",
            "reviewer_id": "agent-456",
            "issues_found": [{"type": "error", "message": "Missing error handling"}],
        }

        event = ReviewFeedbackSubmitted(
            aggregate_id="review-123",
            payload=payload,
        )

        assert event.event_type == "ReviewFeedbackSubmitted"
        assert event.payload["decision"] == "needs_changes"

    def test_review_cycle_approved(self):
        """Test ReviewCycleApproved event."""
        payload = {
            "approved_at": datetime.now(UTC).isoformat(),
            "final_iteration": 2,
            "reviewer_id": "agent-456",
            "approval_notes": "All issues resolved",
        }

        event = ReviewCycleApproved(
            aggregate_id="review-123",
            payload=payload,
        )

        assert event.event_type == "ReviewCycleApproved"
        assert event.payload["final_iteration"] == 2

    def test_review_cycle_escalated(self):
        """Test ReviewCycleEscalated event."""
        payload = {
            "escalated_at": datetime.now(UTC).isoformat(),
            "reason": "Maximum iterations exceeded",
            "iteration_count": 3,
            "escalated_to": "human-reviewer",
            "escalation_notes": "Needs human review",
        }

        event = ReviewCycleEscalated(
            aggregate_id="review-123",
            payload=payload,
        )

        assert event.event_type == "ReviewCycleEscalated"
        assert event.payload["reason"] == "Maximum iterations exceeded"


# =============================================================================
# Project Context Event Tests
# =============================================================================


class TestProjectContextEvents:
    """Tests for ProjectContext domain events."""

    def test_project_context_created(self):
        """Test ProjectContextCreated event."""
        payload = {
            "project_name": "test-project",
            "repository_url": "https://github.com/test/repo",
            "default_branch": "main",
            "language": "python",
            "framework": "fastapi",
        }

        event = ProjectContextCreated(
            aggregate_id="project-123",
            payload=payload,
        )

        assert event.aggregate_type == "ProjectContext"
        assert event.event_type == "ProjectContextCreated"
        assert event.payload["project_name"] == "test-project"

    def test_project_test_config_updated(self):
        """Test ProjectTestConfigUpdated event."""
        payload = {
            "updated_at": datetime.now(UTC).isoformat(),
            "test_command": "pytest",
            "test_directory": "tests/",
            "coverage_threshold": 80.0,
        }

        event = ProjectTestConfigUpdated(
            aggregate_id="project-123",
            payload=payload,
        )

        assert event.event_type == "ProjectTestConfigUpdated"
        assert event.payload["coverage_threshold"] == 80.0

    def test_project_docker_config_updated(self):
        """Test ProjectDockerConfigUpdated event."""
        payload = {
            "updated_at": datetime.now(UTC).isoformat(),
            "base_image": "python:3.11-slim",
            "build_args": {"BUILD_ENV": "production"},
            "environment_vars": {"APP_ENV": "production"},
        }

        event = ProjectDockerConfigUpdated(
            aggregate_id="project-123",
            payload=payload,
        )

        assert event.event_type == "ProjectDockerConfigUpdated"
        assert event.payload["base_image"] == "python:3.11-slim"

    def test_project_workflow_mapping_added(self):
        """Test ProjectWorkflowMappingAdded event."""
        payload = {
            "added_at": datetime.now(UTC).isoformat(),
            "label_pattern": "bug.*",
            "workflow_template_id": "template-123",
            "priority": 10,
        }

        event = ProjectWorkflowMappingAdded(
            aggregate_id="project-123",
            payload=payload,
        )

        assert event.event_type == "ProjectWorkflowMappingAdded"
        assert event.payload["label_pattern"] == "bug.*"


# =============================================================================
# Event Versioning Tests
# =============================================================================


class TestEventVersioning:
    """Tests for event versioning functionality."""

    def test_event_version_is_set(self):
        """Test that all events have version set to 1."""
        event = WorkItemCreated(
            aggregate_id="work-123",
            payload={"title": "Test"},
        )

        assert event.event_version == 1

    def test_event_version_in_serialization(self):
        """Test that version is included in serialization."""
        event = WorkItemCreated(
            aggregate_id="work-123",
            payload={"title": "Test"},
        )

        event_dict = event.to_dict()

        assert "event_version" in event_dict
        assert event_dict["event_version"] == 1


# =============================================================================
# Event Causation and Correlation Tests
# =============================================================================


class TestEventCausationAndCorrelation:
    """Tests for event causation and correlation tracking."""

    def test_correlation_id_groups_related_events(self):
        """Test that correlation_id can group related events."""
        correlation_id = uuid4()

        event1 = WorkItemCreated(
            aggregate_id="work-123",
            payload={"title": "Test"},
            correlation_id=correlation_id,
        )

        event2 = WorkflowCreated(
            aggregate_id="workflow-123",
            payload={
                "work_item_id": "work-123",
                "template_id": "template-1",
                "project_id": "proj-1",
                "stage_count": 3,
            },
            correlation_id=correlation_id,
        )

        assert event1.correlation_id == event2.correlation_id

    def test_causation_id_tracks_cause(self):
        """Test that causation_id tracks which event caused another."""
        event1 = WorkItemCreated(
            aggregate_id="work-123",
            payload={"title": "Test"},
        )

        event2 = WorkflowCreated(
            aggregate_id="workflow-123",
            payload={
                "work_item_id": "work-123",
                "template_id": "template-1",
                "project_id": "proj-1",
                "stage_count": 3,
            },
            causation_id=event1.event_id,
        )

        assert event2.causation_id == event1.event_id

    def test_user_id_tracks_initiator(self):
        """Test that user_id tracks who initiated the event."""
        event = WorkItemCreated(
            aggregate_id="work-123",
            payload={"title": "Test"},
            user_id="user-456",
        )

        assert event.user_id == "user-456"
