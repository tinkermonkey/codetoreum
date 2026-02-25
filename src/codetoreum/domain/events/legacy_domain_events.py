"""Domain events base classes and specific event types."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


class DomainEvent:
    """Base class for all domain events."""

    def __init__(
        self,
        aggregate_id: str,
        aggregate_type: str,
        payload: dict[str, Any] | None = None,
        user_id: str | None = None,
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
        event_id: UUID | None = None,
        occurred_at: datetime | None = None,
    ):
        """
        Initialize domain event.

        Args:
            aggregate_id: ID of the aggregate that emitted this event
            aggregate_type: Type of the aggregate (e.g., "WorkItem", "Agent")
            payload: Event-specific data
            user_id: ID of the user who triggered this event (optional)
            correlation_id: ID to group related events (optional)
            causation_id: ID of the event that caused this event (optional)
            event_id: Unique event ID (generated if not provided)
            occurred_at: Timestamp when event occurred (defaults to now)
        """
        self.event_id = event_id or uuid4()
        self.event_type = self.__class__.__name__
        self.event_version = 1
        self.aggregate_id = aggregate_id
        self.aggregate_type = aggregate_type
        self.occurred_at = occurred_at or datetime.now(UTC)
        self.correlation_id = correlation_id or uuid4()
        self.causation_id = causation_id
        self.user_id = user_id
        self.payload = payload or {}
        self.metadata: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize event to dictionary.

        Returns:
            Dictionary representation of the event
        """
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "event_version": self.event_version,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "causation_id": str(self.causation_id) if self.causation_id else None,
            "user_id": self.user_id,
            "payload": self.payload,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainEvent":
        """
        Deserialize event from dictionary.

        Args:
            data: Dictionary representation of the event

        Returns:
            DomainEvent instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        try:
            return cls(
                aggregate_id=data["aggregate_id"],
                aggregate_type=data["aggregate_type"],
                payload=data.get("payload", {}),
                user_id=data.get("user_id"),
                correlation_id=UUID(data["correlation_id"]) if data.get("correlation_id") else None,
                causation_id=UUID(data["causation_id"]) if data.get("causation_id") else None,
                event_id=UUID(data["event_id"]) if data.get("event_id") else None,
                occurred_at=datetime.fromisoformat(data["occurred_at"]) if data.get("occurred_at") else None,
            )
        except KeyError as e:
            msg = f"Missing required field: {e}"
            raise ValueError(msg)
        except (ValueError, TypeError) as e:
            msg = f"Invalid field value: {e}"
            raise ValueError(msg)

    def __eq__(self, other: object) -> bool:
        """
        Compare events for equality based on event_id.

        Args:
            other: Object to compare with

        Returns:
            True if events have the same event_id
        """
        if not isinstance(other, DomainEvent):
            return False
        return self.event_id == other.event_id

    def __hash__(self) -> int:
        """
        Generate hash based on event_id.

        Returns:
            Hash value
        """
        return hash(self.event_id)


# =============================================================================
# Work Item Events
# =============================================================================


class WorkItemCreated(DomainEvent):
    """Emitted when a work item is created."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkItemCreated event.

        Required payload fields:
        - title: str
        - description: str
        - project_id: str
        - labels: List[str]
        - priority: int
        - external_id: Optional[str]
        - external_url: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class AgentAssigned(DomainEvent):
    """Emitted when an agent is assigned to work item."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentAssigned event.

        Required payload fields:
        - agent_id: str
        - reason: str
        - assigned_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemStarted(DomainEvent):
    """Emitted when work begins on item."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkItemStarted event.

        Required payload fields:
        - started_at: str (ISO format)
        - agent_id: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemUnderReview(DomainEvent):
    """Emitted when work item enters review."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkItemUnderReview event.

        Required payload fields:
        - review_started_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemCompleted(DomainEvent):
    """Emitted when work item completes successfully."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkItemCompleted event.

        Required payload fields:
        - completed_at: str (ISO format)
        - agent_id: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemFailed(DomainEvent):
    """Emitted when work item fails."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkItemFailed event.

        Required payload fields:
        - failed_at: str (ISO format)
        - reason: str
        - error_details: Dict[str, Any]
        - agent_id: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemBlocked(DomainEvent):
    """Emitted when work item is blocked."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkItemBlocked event.

        Required payload fields:
        - blocked_at: str (ISO format)
        - reason: str
        - blocking_issue_id: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemUnblocked(DomainEvent):
    """Emitted when work item is unblocked."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkItemUnblocked event.

        Required payload fields:
        - unblocked_at: str (ISO format)
        - new_status: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkflowAttached(DomainEvent):
    """Emitted when workflow attached to work item."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkflowAttached event.

        Required payload fields:
        - workflow_id: str
        - attached_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemStageUpdated(DomainEvent):
    """Emitted when work item moves to new stage."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkItemStageUpdated event.

        Required payload fields:
        - workflow_id: str
        - old_stage: Optional[str]
        - new_stage: str
        - updated_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemLabelsUpdated(DomainEvent):
    """Emitted when work item labels change."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkItemLabelsUpdated event.

        Required payload fields:
        - old_labels: List[str]
        - new_labels: List[str]
        - updated_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemPriorityUpdated(DomainEvent):
    """Emitted when work item priority changes."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkItemPriorityUpdated event.

        Required payload fields:
        - old_priority: int
        - new_priority: int
        - updated_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


# =============================================================================
# Agent Events
# =============================================================================


class AgentCreated(DomainEvent):
    """Emitted when agent is created."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentCreated event.

        Required payload fields:
        - name: str
        - display_name: str
        - agent_type: str
        - model: str
        - capabilities: List[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentCapabilityAdded(DomainEvent):
    """Emitted when capability added to agent."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentCapabilityAdded event.

        Required payload fields:
        - skill: str
        - proficiency: float
        - added_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentCapabilityRemoved(DomainEvent):
    """Emitted when capability removed from agent."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentCapabilityRemoved event.

        Required payload fields:
        - skill: str
        - removed_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentCapabilityUpdated(DomainEvent):
    """Emitted when capability proficiency updated."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentCapabilityUpdated event.

        Required payload fields:
        - skill: str
        - old_proficiency: float
        - new_proficiency: float
        - updated_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentModelUpdated(DomainEvent):
    """Emitted when agent LLM model changed."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentModelUpdated event.

        Required payload fields:
        - old_model: str
        - new_model: str
        - updated_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentTimeoutUpdated(DomainEvent):
    """Emitted when agent timeout changed."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentTimeoutUpdated event.

        Required payload fields:
        - old_timeout: int
        - new_timeout: int
        - updated_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentMaxRetriesUpdated(DomainEvent):
    """Emitted when agent max retries changed."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentMaxRetriesUpdated event.

        Required payload fields:
        - old_max_retries: int
        - new_max_retries: int
        - updated_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentConstraintsUpdated(DomainEvent):
    """Emitted when agent constraints changed."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentConstraintsUpdated event.

        Required payload fields:
        - old_constraints: Dict[str, bool]
        - new_constraints: Dict[str, bool]
        - updated_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentMcpServerAdded(DomainEvent):
    """Emitted when MCP server added to agent."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentMcpServerAdded event.

        Required payload fields:
        - server_name: str
        - added_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentMcpServerRemoved(DomainEvent):
    """Emitted when MCP server removed from agent."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentMcpServerRemoved event.

        Required payload fields:
        - server_name: str
        - removed_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


# =============================================================================
# Agent Execution Events
# =============================================================================


class ExecutionInitialized(DomainEvent):
    """Emitted when execution is initialized."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ExecutionInitialized event.

        Required payload fields:
        - agent_id: str
        - work_item_id: str
        - workflow_id: str
        - stage_name: str
        - model: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionStarted(DomainEvent):
    """Emitted when execution starts."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ExecutionStarted event.

        Required payload fields:
        - started_at: str (ISO format)
        - container_name: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionCompleted(DomainEvent):
    """Emitted when execution completes successfully."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ExecutionCompleted event.

        Required payload fields:
        - completed_at: str (ISO format)
        - input_tokens: int
        - output_tokens: int
        - duration_seconds: Optional[float]
        - session_id: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionFailed(DomainEvent):
    """Emitted when execution fails."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ExecutionFailed event.

        Required payload fields:
        - failed_at: str (ISO format)
        - error_message: str
        - exit_code: Optional[int]
        - duration_seconds: Optional[float]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionTimeout(DomainEvent):
    """Emitted when execution times out."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ExecutionTimeout event.

        Required payload fields:
        - timeout_at: str (ISO format)
        - duration_seconds: Optional[float]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionCancelled(DomainEvent):
    """Emitted when execution is cancelled."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ExecutionCancelled event.

        Required payload fields:
        - cancelled_at: str (ISO format)
        - reason: Optional[str]
        - duration_seconds: Optional[float]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionPaused(DomainEvent):
    """Emitted when execution is paused."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ExecutionPaused event.

        Required payload fields:
        - paused_at: str (ISO format)
        - reason: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionResumed(DomainEvent):
    """Emitted when execution is resumed."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ExecutionResumed event.

        Required payload fields:
        - resumed_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


# =============================================================================
# Workflow Events
# =============================================================================


class WorkflowCreated(DomainEvent):
    """Emitted when a workflow is created."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkflowCreated event.

        Required payload fields:
        - work_item_id: str
        - template_id: str
        - project_id: str
        - stage_count: int
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowStarted(DomainEvent):
    """Emitted when workflow execution begins."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkflowStarted event.

        Required payload fields:
        - started_at: str (ISO format)
        - work_item_id: str
        - first_stage: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowStageAdvanced(DomainEvent):
    """Emitted when workflow moves to the next stage."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkflowStageAdvanced event.

        Required payload fields:
        - from_stage: str
        - to_stage: str
        - stage_index: int
        - advanced_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowStageStatusUpdated(DomainEvent):
    """Emitted when a stage's status changes."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkflowStageStatusUpdated event.

        Required payload fields:
        - stage_name: str
        - old_status: str
        - new_status: str
        - updated_at: str (ISO format)
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowCompleted(DomainEvent):
    """Emitted when workflow completes successfully."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkflowCompleted event.

        Required payload fields:
        - completed_at: str (ISO format)
        - work_item_id: str
        - duration_seconds: float
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowFailed(DomainEvent):
    """Emitted when workflow fails."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkflowFailed event.

        Required payload fields:
        - failed_at: str (ISO format)
        - reason: str
        - failed_stage: str
        - completed_stages: List[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowPaused(DomainEvent):
    """Emitted when workflow is paused."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkflowPaused event.

        Required payload fields:
        - paused_at: str (ISO format)
        - reason: str
        - current_stage: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowResumed(DomainEvent):
    """Emitted when workflow is resumed."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkflowResumed event.

        Required payload fields:
        - resumed_at: str (ISO format)
        - current_stage: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowCancelled(DomainEvent):
    """Emitted when workflow is cancelled."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkflowCancelled event.

        Required payload fields:
        - cancelled_at: str (ISO format)
        - reason: str
        - completed_stages: List[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


# =============================================================================
# Review Cycle Events
# =============================================================================


class ReviewCycleCreated(DomainEvent):
    """Emitted when a review cycle is created."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ReviewCycleCreated event.

        Required payload fields:
        - work_item_id: str
        - workflow_id: str
        - stage_name: str
        - execution_id: str
        - max_iterations: int
        - review_type: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewIterationStarted(DomainEvent):
    """Emitted when a new review iteration starts."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ReviewIterationStarted event.

        Required payload fields:
        - iteration_number: int
        - started_at: str (ISO format)
        - reviewer_agent_id: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewFeedbackSubmitted(DomainEvent):
    """Emitted when reviewer provides feedback."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ReviewFeedbackSubmitted event.

        Required payload fields:
        - iteration_number: int
        - submitted_at: str (ISO format)
        - feedback: str
        - decision: str (approved, rejected, needs_changes)
        - reviewer_id: str
        - issues_found: List[Dict[str, Any]]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewCycleApproved(DomainEvent):
    """Emitted when review is approved."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ReviewCycleApproved event.

        Required payload fields:
        - approved_at: str (ISO format)
        - final_iteration: int
        - reviewer_id: str
        - approval_notes: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewCycleRejected(DomainEvent):
    """Emitted when review is rejected."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ReviewCycleRejected event.

        Required payload fields:
        - rejected_at: str (ISO format)
        - final_iteration: int
        - reviewer_id: str
        - rejection_reason: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewCycleEscalated(DomainEvent):
    """Emitted when review is escalated to human."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ReviewCycleEscalated event.

        Required payload fields:
        - escalated_at: str (ISO format)
        - reason: str
        - iteration_count: int
        - escalated_to: str
        - escalation_notes: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


# =============================================================================
# Project Context Events
# =============================================================================


class ProjectContextCreated(DomainEvent):
    """Emitted when project context is created."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ProjectContextCreated event.

        Required payload fields:
        - project_name: str
        - repository_url: str
        - default_branch: str
        - language: Optional[str]
        - framework: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)


class ProjectTestConfigUpdated(DomainEvent):
    """Emitted when test configuration changes."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ProjectTestConfigUpdated event.

        Required payload fields:
        - updated_at: str (ISO format)
        - test_command: str
        - test_directory: str
        - coverage_threshold: Optional[float]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)


class ProjectDockerConfigUpdated(DomainEvent):
    """Emitted when Docker configuration changes."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ProjectDockerConfigUpdated event.

        Required payload fields:
        - updated_at: str (ISO format)
        - base_image: str
        - build_args: Dict[str, str]
        - environment_vars: Dict[str, str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)


class ProjectWorkflowMappingAdded(DomainEvent):
    """Emitted when custom workflow mapping is added."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ProjectWorkflowMappingAdded event.

        Required payload fields:
        - added_at: str (ISO format)
        - label_pattern: str
        - workflow_template_id: str
        - priority: int
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)


# =============================================================================
# Pipeline Execution Events
# =============================================================================


class PipelineStageStarted(DomainEvent):
    """Emitted when a pipeline stage starts execution."""

    def __init__(
        self,
        aggregate_id: str,
        pipeline_id: str,
        stage_name: str,
        stage_type: str,
        agent_config: dict[str, Any],
        execution_id: str,
        timestamp: datetime | None = None,
        **kwargs: Any,
    ):
        """
        Initialize PipelineStageStarted event.

        Args:
            aggregate_id: Workflow ID
            pipeline_id: Pipeline execution ID
            stage_name: Name of the stage
            stage_type: Type of stage (sequential, parallel, review)
            agent_config: Agent configuration for this stage
            execution_id: Execution ID for this stage
            timestamp: Event timestamp
        """
        payload = {
            "pipeline_id": pipeline_id,
            "stage_name": stage_name,
            "stage_type": stage_type,
            "agent_config": agent_config,
            "execution_id": execution_id,
            "started_at": (timestamp or datetime.now(UTC)).isoformat(),
        }
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class PipelineStageCompleted(DomainEvent):
    """Emitted when a pipeline stage completes successfully."""

    def __init__(
        self,
        aggregate_id: str,
        pipeline_id: str,
        stage_name: str,
        execution_id: str,
        output: str,
        duration_seconds: float,
        timestamp: datetime | None = None,
        **kwargs: Any,
    ):
        """
        Initialize PipelineStageCompleted event.

        Args:
            aggregate_id: Workflow ID
            pipeline_id: Pipeline execution ID
            stage_name: Name of the stage
            execution_id: Execution ID for this stage
            output: Stage output
            duration_seconds: Duration in seconds
            timestamp: Event timestamp
        """
        payload = {
            "pipeline_id": pipeline_id,
            "stage_name": stage_name,
            "execution_id": execution_id,
            "output": output,
            "duration_seconds": duration_seconds,
            "completed_at": (timestamp or datetime.now(UTC)).isoformat(),
        }
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class PipelineStageFailed(DomainEvent):
    """Emitted when a pipeline stage fails."""

    def __init__(
        self,
        aggregate_id: str,
        pipeline_id: str,
        stage_name: str,
        execution_id: str,
        error: str,
        duration_seconds: float,
        timestamp: datetime | None = None,
        **kwargs: Any,
    ):
        """
        Initialize PipelineStageFailed event.

        Args:
            aggregate_id: Workflow ID
            pipeline_id: Pipeline execution ID
            stage_name: Name of the stage
            execution_id: Execution ID for this stage
            error: Error message
            duration_seconds: Duration in seconds
            timestamp: Event timestamp
        """
        payload = {
            "pipeline_id": pipeline_id,
            "stage_name": stage_name,
            "execution_id": execution_id,
            "error": error,
            "duration_seconds": duration_seconds,
            "failed_at": (timestamp or datetime.now(UTC)).isoformat(),
        }
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class PipelineCompleted(DomainEvent):
    """Emitted when entire pipeline completes successfully."""

    def __init__(
        self,
        aggregate_id: str,
        pipeline_id: str,
        workflow_id: str,
        completed_stages: list,
        outputs: dict[str, Any],
        duration_seconds: float,
        timestamp: datetime | None = None,
        **kwargs: Any,
    ):
        """
        Initialize PipelineCompleted event.

        Args:
            aggregate_id: Pipeline execution ID
            pipeline_id: Pipeline execution ID
            workflow_id: Workflow ID
            completed_stages: List of completed stage names
            outputs: Dictionary of stage outputs
            duration_seconds: Total duration in seconds
            timestamp: Event timestamp
        """
        payload = {
            "pipeline_id": pipeline_id,
            "workflow_id": workflow_id,
            "completed_stages": completed_stages,
            "outputs": outputs,
            "duration_seconds": duration_seconds,
            "completed_at": (timestamp or datetime.now(UTC)).isoformat(),
        }
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Pipeline", payload=payload, **kwargs)


class PipelineFailed(DomainEvent):
    """Emitted when pipeline execution fails."""

    def __init__(
        self,
        aggregate_id: str,
        pipeline_id: str,
        workflow_id: str,
        error: str,
        completed_stages: list,
        failed_stages: list,
        timestamp: datetime | None = None,
        **kwargs: Any,
    ):
        """
        Initialize PipelineFailed event.

        Args:
            aggregate_id: Pipeline execution ID
            pipeline_id: Pipeline execution ID
            workflow_id: Workflow ID
            error: Error message
            completed_stages: List of completed stage names
            failed_stages: List of failed stage names
            timestamp: Event timestamp
        """
        payload = {
            "pipeline_id": pipeline_id,
            "workflow_id": workflow_id,
            "error": error,
            "completed_stages": completed_stages,
            "failed_stages": failed_stages,
            "failed_at": (timestamp or datetime.now(UTC)).isoformat(),
        }
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Pipeline", payload=payload, **kwargs)


# =============================================================================
# Configuration Events
# =============================================================================


class ProjectConfigUpdated(DomainEvent):
    """Emitted when project configuration is updated."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize ProjectConfigUpdated event.

        Required payload fields:
        - project_id: str
        - version: int
        - changes: Dict[str, Any]
        - updated_by: str
        - reason: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


class AgentConfigUpdated(DomainEvent):
    """Emitted when agent configuration is updated."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize AgentConfigUpdated event.

        Required payload fields:
        - project_id: str
        - agent_name: str
        - version: int
        - changes: Dict[str, Any]
        - updated_by: str
        - reason: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentConfig", payload=payload, **kwargs)


class PipelineConfigUpdated(DomainEvent):
    """Emitted when pipeline configuration is updated."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize PipelineConfigUpdated event.

        Required payload fields:
        - project_id: str
        - pipeline_name: str
        - version: int
        - changes: Dict[str, Any]
        - updated_by: str
        - reason: Optional[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="PipelineConfig", payload=payload, **kwargs)


class EnvironmentVariableChanged(DomainEvent):
    """Emitted when environment variable is added, updated, or removed."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize EnvironmentVariableChanged event.

        Required payload fields:
        - project_id: str
        - variable_name: str
        - action: str (added, updated, removed)
        - is_secret: bool
        - changed_by: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


class CommandMounted(DomainEvent):
    """Emitted when command is mounted to project agent."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize CommandMounted event.

        Required payload fields:
        - project_id: str
        - command_name: str
        - command_path: str
        - mounted_by: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


class CommandUnmounted(DomainEvent):
    """Emitted when command is unmounted from project agent."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize CommandUnmounted event.

        Required payload fields:
        - project_id: str
        - command_name: str
        - unmounted_by: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


class SubAgentMounted(DomainEvent):
    """Emitted when sub-agent is mounted to project agent."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize SubAgentMounted event.

        Required payload fields:
        - project_id: str
        - subagent_name: str
        - mounted_by: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


class SubAgentUnmounted(DomainEvent):
    """Emitted when sub-agent is unmounted from project agent."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize SubAgentUnmounted event.

        Required payload fields:
        - project_id: str
        - subagent_name: str
        - unmounted_by: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


# =============================================================================
# Board Events
# =============================================================================


class WorkItemColumnChanged(DomainEvent):
    """Emitted when work item moves between board columns."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize WorkItemColumnChanged event.

        Required payload fields:
        - work_item_id: str
        - from_column: Optional[str]
        - to_column: str
        - moved_by: str (HUMAN or ORCHESTRATOR)
        - board_id: str
        - project_id: str
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class BoardReconciled(DomainEvent):
    """Emitted after board structure synchronized with config."""

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """
        Initialize BoardReconciled event.

        Required payload fields:
        - board_id: str
        - columns_added: List[str]
        - columns_removed: List[str]
        - orphaned_items: List[str]
        """
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Board", payload=payload, **kwargs)
