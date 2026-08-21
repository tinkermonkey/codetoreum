"""Unit tests for domain events (CodetoreumEvent and frozen dataclass events)."""

from datetime import UTC, datetime

import pytest

from codetoreum.domain.events.adapter_events import CodetoreumEvent, now_iso
from codetoreum.domain.events.agent_events import (
    AgentCapabilityAddedEvent,
    AgentCreatedEvent,
    AgentModelUpdatedEvent,
)
from codetoreum.domain.events.execution_events import (
    ExecutionCancelledEvent,
    ExecutionCompletedEvent,
    ExecutionFailedEvent,
    ExecutionInitializedEvent,
    ExecutionPausedEvent,
    ExecutionResumedEvent,
    ExecutionRetryScheduledEvent,
    ExecutionStartedEvent,
)
from codetoreum.domain.events.project_context_events import (
    ProjectContextCreatedEvent,
    ProjectDockerConfigUpdatedEvent,
    ProjectTestConfigUpdatedEvent,
    ProjectWorkflowMappingAddedEvent,
)
from codetoreum.domain.events.review_cycle_events import (
    ReviewCycleApprovedEvent,
    ReviewCycleCreatedEvent,
    ReviewCycleFeedbackSubmittedEvent,
    ReviewCycleIterationStartedEvent,
)
from codetoreum.domain.events.work_item_events import (
    AgentAssignedEvent,
    WorkItemBlockedEvent,
    WorkItemCompletedEvent,
    WorkItemCreatedEvent,
    WorkItemFailedEvent,
    WorkItemLabelsUpdatedEvent,
    WorkItemStartedEvent,
)
from codetoreum.domain.events.workflow_events import (
    WorkflowCompletedEvent,
    WorkflowCreatedEvent,
    WorkflowStageAdvancedEvent,
)

# =============================================================================
# Base CodetoreumEvent Tests
# =============================================================================


class TestCodetoreumEvent:
    """Tests for the base CodetoreumEvent frozen dataclass."""

    def test_initialization(self):
        """Test event initialization with required fields."""
        ts = now_iso()
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=ts,
            source="test_adapter",
        )

        assert event.type == "workitem.created"
        assert event.timestamp == ts
        assert event.source == "test_adapter"
        assert event.correlation_id is None
        assert event.event_id is not None

    def test_immutability(self):
        """Test that events are immutable (frozen dataclass)."""
        from dataclasses import FrozenInstanceError

        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="test_adapter",
        )

        with pytest.raises(FrozenInstanceError):
            event.type = "mutated"

    def test_event_type_property_returns_class_name(self):
        """Test that event_type property returns class name."""
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="test_adapter",
        )
        assert event.event_type == "CodetoreumEvent"

    def test_to_dict_serialization(self):
        """Test event serialization to dictionary."""
        ts = now_iso()
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=ts,
            source="test_adapter",
            correlation_id="corr-123",
        )

        d = event.to_dict()

        assert d["type"] == "workitem.created"
        assert d["timestamp"] == ts
        assert d["source"] == "test_adapter"
        assert d["correlation_id"] == "corr-123"
        assert "event_id" in d

    def test_from_dict_deserialization(self):
        """Test event deserialization from dictionary."""
        ts = now_iso()
        data = {
            "type": "workitem.created",
            "timestamp": ts,
            "source": "test_adapter",
            "correlation_id": "corr-123",
            "event_id": "evt-456",
        }

        event = CodetoreumEvent.from_dict(data)

        assert event.type == "workitem.created"
        assert event.timestamp == ts
        assert event.source == "test_adapter"
        assert event.correlation_id == "corr-123"
        assert event.event_id == "evt-456"

    def test_invalid_type_raises_error(self):
        """Test that event type without dot notation raises ValueError."""
        with pytest.raises(ValueError, match="dot notation"):
            CodetoreumEvent(
                type="nodotnotation",
                timestamp=now_iso(),
                source="test",
            )

    def test_empty_source_raises_error(self):
        """Test that empty source raises ValueError."""
        with pytest.raises(ValueError, match="source"):
            CodetoreumEvent(
                type="workitem.created",
                timestamp=now_iso(),
                source="",
            )

    def test_unique_event_ids(self):
        """Test that each event gets a unique event_id."""
        ts = now_iso()
        e1 = CodetoreumEvent(type="a.b", timestamp=ts, source="src")
        e2 = CodetoreumEvent(type="a.b", timestamp=ts, source="src")
        assert e1.event_id != e2.event_id


# =============================================================================
# Work Item Event Tests
# =============================================================================


class TestWorkItemEvents:
    """Tests for WorkItem frozen dataclass events."""

    def test_work_item_created(self):
        """Test WorkItemCreatedEvent."""
        event = WorkItemCreatedEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="test",
            work_item_id="work-123",
            title="Test Work Item",
            project_id="proj-123",
            labels=["bug", "high-priority"],
            priority=1,
            created_at=now_iso(),
        )

        assert event.work_item_id == "work-123"
        assert event.title == "Test Work Item"
        assert event.event_type == "WorkItemCreatedEvent"

    def test_agent_assigned(self):
        """Test AgentAssignedEvent."""
        ts = now_iso()
        event = AgentAssignedEvent(
            type="workitem.agent_assigned",
            timestamp=ts,
            source="test",
            work_item_id="work-123",
            agent_id="agent-123",
            reason="Best match for task",
            assigned_at=ts,
        )

        assert event.work_item_id == "work-123"
        assert event.agent_id == "agent-123"
        assert event.reason == "Best match for task"
        assert event.event_type == "AgentAssignedEvent"

    def test_work_item_started(self):
        """Test WorkItemStartedEvent."""
        ts = now_iso()
        event = WorkItemStartedEvent(
            type="workitem.started",
            timestamp=ts,
            source="test",
            work_item_id="work-123",
            agent_id="agent-123",
            started_at=ts,
        )

        assert event.event_type == "WorkItemStartedEvent"
        assert event.work_item_id == "work-123"

    def test_work_item_completed(self):
        """Test WorkItemCompletedEvent."""
        ts = now_iso()
        event = WorkItemCompletedEvent(
            type="workitem.completed",
            timestamp=ts,
            source="test",
            work_item_id="work-123",
            agent_id="agent-123",
            completed_at=ts,
        )

        assert event.event_type == "WorkItemCompletedEvent"

    def test_work_item_failed(self):
        """Test WorkItemFailedEvent."""
        ts = now_iso()
        event = WorkItemFailedEvent(
            type="workitem.failed",
            timestamp=ts,
            source="test",
            work_item_id="work-123",
            agent_id="agent-123",
            reason="Timeout exceeded",
            failed_at=ts,
        )

        assert event.event_type == "WorkItemFailedEvent"
        assert event.reason == "Timeout exceeded"

    def test_work_item_blocked(self):
        """Test WorkItemBlockedEvent."""
        ts = now_iso()
        event = WorkItemBlockedEvent(
            type="workitem.blocked",
            timestamp=ts,
            source="test",
            work_item_id="work-123",
            reason="Dependency not met",
            blocking_issue_id="issue-456",
        )

        assert event.event_type == "WorkItemBlockedEvent"
        assert event.blocking_issue_id == "issue-456"

    def test_work_item_labels_updated(self):
        """Test WorkItemLabelsUpdatedEvent with tuple fields."""
        ts = now_iso()
        event = WorkItemLabelsUpdatedEvent(
            type="workitem.labels_updated",
            timestamp=ts,
            source="test",
            work_item_id="work-123",
            old_labels=("bug",),
            new_labels=("bug", "high-priority"),
        )

        assert event.event_type == "WorkItemLabelsUpdatedEvent"
        assert len(event.new_labels) == 2


# =============================================================================
# Agent Event Tests
# =============================================================================


class TestAgentEvents:
    """Tests for Agent frozen dataclass events."""

    def test_agent_created(self):
        """Test AgentCreatedEvent."""
        event = AgentCreatedEvent(
            type="agent.created",
            timestamp=now_iso(),
            source="test",
            agent_id="agent-123",
            name="test-agent",
            display_name="Test Agent",
            agent_type="coding",
            model="claude-sonnet-4-5",
        )

        assert event.event_type == "AgentCreatedEvent"
        assert event.name == "test-agent"

    def test_agent_capability_added(self):
        """Test AgentCapabilityAddedEvent."""
        event = AgentCapabilityAddedEvent(
            type="agent.capability_added",
            timestamp=now_iso(),
            source="test",
            agent_id="agent-123",
            skill="rust",
            proficiency=0.8,
        )

        assert event.event_type == "AgentCapabilityAddedEvent"
        assert event.skill == "rust"

    def test_agent_model_updated(self):
        """Test AgentModelUpdatedEvent."""
        event = AgentModelUpdatedEvent(
            type="agent.model_updated",
            timestamp=now_iso(),
            source="test",
            agent_id="agent-123",
            old_model="claude-sonnet-4-5",
            new_model="claude-opus-4",
        )

        assert event.event_type == "AgentModelUpdatedEvent"
        assert event.new_model == "claude-opus-4"


# =============================================================================
# Execution Event Tests
# =============================================================================


class TestExecutionEvents:
    """Tests for AgentExecution frozen dataclass events."""

    def test_execution_initialized(self):
        """Test ExecutionInitializedEvent."""
        ts = now_iso()
        event = ExecutionInitializedEvent(
            type="execution.initialized",
            timestamp=ts,
            source="test",
            execution_id="exec-123",
            work_item_id="work-123",
            agent_id="agent-123",
        )

        assert event.event_type == "ExecutionInitializedEvent"
        assert event.agent_id == "agent-123"
        assert event.work_item_id == "work-123"

    def test_execution_started(self):
        """Test ExecutionStartedEvent."""
        ts = now_iso()
        event = ExecutionStartedEvent(
            type="execution.started",
            timestamp=ts,
            source="test",
            execution_id="exec-123",
            work_item_id="work-123",
            agent_id="agent-123",
        )

        assert event.event_type == "ExecutionStartedEvent"

    def test_execution_completed(self):
        """Test ExecutionCompletedEvent."""
        ts = now_iso()
        event = ExecutionCompletedEvent(
            type="execution.completed",
            timestamp=ts,
            source="test",
            execution_id="exec-123",
            work_item_id="work-123",
            agent_id="agent-123",
            output="success",
        )

        assert event.event_type == "ExecutionCompletedEvent"
        assert event.output == "success"

    def test_execution_failed(self):
        """Test ExecutionFailedEvent."""
        ts = now_iso()
        event = ExecutionFailedEvent(
            type="execution.failed",
            timestamp=ts,
            source="test",
            execution_id="exec-123",
            work_item_id="work-123",
            agent_id="agent-123",
            error="Container crashed",
        )

        assert event.event_type == "ExecutionFailedEvent"
        assert event.error == "Container crashed"

    def test_execution_cancelled_event(self):
        """ExecutionCancelledEvent has correct fields and event_type."""
        ts = now_iso()
        event = ExecutionCancelledEvent(
            type="execution.cancelled",
            timestamp=ts,
            source="test",
            execution_id="exec-123",
            work_item_id="work-123",
            agent_id="agent-123",
            cancelled_at=ts,
        )

        assert event.event_type == "ExecutionCancelledEvent"
        assert event.execution_id == "exec-123"
        assert event.work_item_id == "work-123"
        assert event.agent_id == "agent-123"
        assert event.cancelled_at == ts

        with pytest.raises(Exception):  # FrozenInstanceError
            event.execution_id = "mutated"

        restored = ExecutionCancelledEvent.from_dict(event.to_dict())
        assert restored.execution_id == event.execution_id
        assert restored.work_item_id == event.work_item_id
        assert restored.agent_id == event.agent_id
        assert restored.cancelled_at == event.cancelled_at

    def test_execution_paused_event(self):
        """ExecutionPausedEvent has correct fields and event_type."""
        ts = now_iso()
        event = ExecutionPausedEvent(
            type="execution.paused",
            timestamp=ts,
            source="test",
            execution_id="exec-456",
            work_item_id="work-456",
            agent_id="agent-456",
            paused_at=ts,
        )

        assert event.event_type == "ExecutionPausedEvent"
        assert event.execution_id == "exec-456"
        assert event.work_item_id == "work-456"
        assert event.agent_id == "agent-456"
        assert event.paused_at == ts

        with pytest.raises(Exception):  # FrozenInstanceError
            event.execution_id = "mutated"

        restored = ExecutionPausedEvent.from_dict(event.to_dict())
        assert restored.execution_id == event.execution_id
        assert restored.work_item_id == event.work_item_id
        assert restored.paused_at == event.paused_at

    def test_execution_resumed_event(self):
        """ExecutionResumedEvent has correct fields and event_type."""
        ts = now_iso()
        event = ExecutionResumedEvent(
            type="execution.resumed",
            timestamp=ts,
            source="test",
            execution_id="exec-789",
            work_item_id="work-789",
            agent_id="agent-789",
            resumed_at=ts,
        )

        assert event.event_type == "ExecutionResumedEvent"
        assert event.execution_id == "exec-789"
        assert event.work_item_id == "work-789"
        assert event.agent_id == "agent-789"
        assert event.resumed_at == ts

        with pytest.raises(Exception):  # FrozenInstanceError
            event.execution_id = "mutated"

        restored = ExecutionResumedEvent.from_dict(event.to_dict())
        assert restored.execution_id == event.execution_id
        assert restored.work_item_id == event.work_item_id
        assert restored.resumed_at == event.resumed_at

    def test_execution_retry_scheduled_event(self):
        """ExecutionRetryScheduledEvent has correct fields and event_type."""
        ts = now_iso()
        event = ExecutionRetryScheduledEvent(
            type="execution.retry_scheduled",
            timestamp=ts,
            source="test",
            execution_id="exec-999",
            work_item_id="work-999",
            agent_id="agent-999",
            retry_count=3,
            retry_at=ts,
        )

        assert event.event_type == "ExecutionRetryScheduledEvent"
        assert event.execution_id == "exec-999"
        assert event.work_item_id == "work-999"
        assert event.agent_id == "agent-999"
        assert event.retry_count == 3
        assert event.retry_at == ts

        with pytest.raises(Exception):  # FrozenInstanceError
            event.execution_id = "mutated"

        restored = ExecutionRetryScheduledEvent.from_dict(event.to_dict())
        assert restored.execution_id == event.execution_id
        assert restored.work_item_id == event.work_item_id
        assert restored.retry_count == event.retry_count
        assert restored.retry_at == event.retry_at


# =============================================================================
# Workflow Event Tests
# =============================================================================


class TestWorkflowEvents:
    """Tests for Workflow frozen dataclass events."""

    def test_workflow_created(self):
        """Test WorkflowCreatedEvent."""
        event = WorkflowCreatedEvent(
            type="workflow.created",
            timestamp=now_iso(),
            source="test",
            workflow_id="workflow-123",
            work_item_id="work-123",
            pipeline_id="pipeline-123",
            stage_name="implementation",
        )

        assert event.event_type == "WorkflowCreatedEvent"
        assert event.work_item_id == "work-123"

    def test_workflow_stage_advanced(self):
        """Test WorkflowStageAdvancedEvent."""
        event = WorkflowStageAdvancedEvent(
            type="workflow.stage_advanced",
            timestamp=now_iso(),
            source="test",
            workflow_id="workflow-123",
            work_item_id="work-123",
            from_stage="implementation",
            to_stage="testing",
        )

        assert event.event_type == "WorkflowStageAdvancedEvent"
        assert event.to_stage == "testing"

    def test_workflow_completed(self):
        """Test WorkflowCompletedEvent."""
        ts = now_iso()
        event = WorkflowCompletedEvent(
            type="workflow.completed",
            timestamp=ts,
            source="test",
            workflow_id="workflow-123",
            work_item_id="work-123",
            final_stage="testing",
            completed_at=ts,
        )

        assert event.event_type == "WorkflowCompletedEvent"


# =============================================================================
# Review Cycle Event Tests
# =============================================================================


class TestReviewCycleEvents:
    """Tests for ReviewCycle events."""

    def test_review_cycle_created(self):
        """Test ReviewCycleCreatedEvent."""
        event = ReviewCycleCreatedEvent(
            type="review_cycle.created",
            timestamp=now_iso(),
            source="test",
            review_cycle_id="review-123",
            workflow_id="workflow-123",
            stage_name="review",
            maker_agent_id="agent-maker",
            reviewer_agent_id="agent-reviewer",
            max_iterations=3,
        )

        assert event.event_type == "ReviewCycleCreatedEvent"
        assert event.max_iterations == 3

    def test_review_iteration_started(self):
        """Test ReviewCycleIterationStartedEvent."""
        ts = now_iso()
        event = ReviewCycleIterationStartedEvent(
            type="review_cycle.iteration_started",
            timestamp=ts,
            source="test",
            review_cycle_id="review-123",
            iteration_number=1,
            maker_execution_id="exec-maker-123",
        )

        assert event.event_type == "ReviewCycleIterationStartedEvent"
        assert event.iteration_number == 1

    def test_review_feedback_submitted(self):
        """Test ReviewCycleFeedbackSubmittedEvent."""
        ts = now_iso()
        event = ReviewCycleFeedbackSubmittedEvent(
            type="review_cycle.feedback_submitted",
            timestamp=ts,
            source="test",
            review_cycle_id="review-123",
            iteration_number=1,
            decision="needs_changes",
            reviewer_execution_id="exec-reviewer-123",
            issues_count=2,
        )

        assert event.event_type == "ReviewCycleFeedbackSubmittedEvent"
        assert event.decision == "needs_changes"

    def test_review_cycle_approved(self):
        """Test ReviewCycleApprovedEvent."""
        ts = now_iso()
        event = ReviewCycleApprovedEvent(
            type="review_cycle.approved",
            timestamp=ts,
            source="test",
            review_cycle_id="review-123",
            work_item_id="work-123",
            total_iterations=2,
        )

        assert event.event_type == "ReviewCycleApprovedEvent"
        assert event.total_iterations == 2


# =============================================================================
# Project Context Event Tests
# =============================================================================


class TestProjectContextEvents:
    """Tests for ProjectContext frozen dataclass events."""

    def test_project_context_created(self):
        """Test ProjectContextCreatedEvent."""
        event = ProjectContextCreatedEvent(
            type="project_context.created",
            timestamp=now_iso(),
            source="test",
            project_id="project-123",
            name="test-project",
        )

        assert event.event_type == "ProjectContextCreatedEvent"
        assert event.name == "test-project"

    def test_project_test_config_updated(self):
        """Test ProjectTestConfigUpdatedEvent."""
        event = ProjectTestConfigUpdatedEvent(
            type="project_context.test_config_updated",
            timestamp=now_iso(),
            source="test",
            project_id="project-123",
            test_command="pytest",
        )

        assert event.event_type == "ProjectTestConfigUpdatedEvent"
        assert event.test_command == "pytest"

    def test_project_docker_config_updated(self):
        """Test ProjectDockerConfigUpdatedEvent."""
        event = ProjectDockerConfigUpdatedEvent(
            type="project_context.docker_config_updated",
            timestamp=now_iso(),
            source="test",
            project_id="project-123",
            image="python:3.11-slim",
        )

        assert event.event_type == "ProjectDockerConfigUpdatedEvent"
        assert event.image == "python:3.11-slim"

    def test_project_workflow_mapping_added(self):
        """Test ProjectWorkflowMappingAddedEvent."""
        event = ProjectWorkflowMappingAddedEvent(
            type="project_context.workflow_mapping_added",
            timestamp=now_iso(),
            source="test",
            project_id="project-123",
            column_name="hotfix",
            workflow_stage="hotfix-template",
        )

        assert event.event_type == "ProjectWorkflowMappingAddedEvent"
        assert event.column_name == "hotfix"
