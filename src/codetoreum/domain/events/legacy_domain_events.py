"""Domain events base classes and specific event types.

**DEPRECATED**: This module contains legacy domain events using the old DomainEvent base class.
These are maintained for backward compatibility but new code should use the modern frozen
dataclass-based events from other event modules (e.g., adapter_events, board_events, etc.).

All events in this module are now immutable as per CLAUDE.md requirements.
The DomainEvent base class enforces immutability through a custom __setattr__ override
to prevent mutations after initialization.
"""

from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4


class DomainEvent:
    """
    Base class for all domain events.

    **IMMUTABILITY**: This class prevents mutations after initialization by overriding
    __setattr__ and __delattr__ to reject modifications or deletions after the object is
    fully constructed. All fields are read-only after construction to maintain event sourcing
    audit trail integrity. The payload and metadata dicts are wrapped in MappingProxyType
    to prevent in-place mutations. Events represent immutable facts—attempting to modify
    any field will raise AttributeError. This immutability is essential because events are
    the permanent record of state changes in the system and must never be altered once created.

    Attributes:
        aggregate_id: ID of the aggregate that emitted this event
        aggregate_type: Type of the aggregate (e.g., "WorkItem", "Agent")
        payload: Event-specific data (immutable dict-like view)
        user_id: ID of the user who triggered this event (optional)
        correlation_id: ID to group related events (optional)
        causation_id: ID of the event that caused this event (optional)
        event_id: Unique event ID (generated if not provided)
        occurred_at: Timestamp when event occurred (defaults to now)
    """

    __slots__ = (
        "event_id",
        "event_type",
        "event_version",
        "aggregate_id",
        "aggregate_type",
        "occurred_at",
        "correlation_id",
        "causation_id",
        "user_id",
        "payload",
        "metadata",
        "_initialized",
    )

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
        object.__setattr__(self, "event_id", event_id or uuid4())
        object.__setattr__(self, "event_type", self.__class__.__name__)
        object.__setattr__(self, "event_version", 1)
        object.__setattr__(self, "aggregate_id", aggregate_id)
        object.__setattr__(self, "aggregate_type", aggregate_type)
        object.__setattr__(self, "occurred_at", occurred_at or datetime.now(UTC))
        object.__setattr__(self, "correlation_id", correlation_id or uuid4())
        object.__setattr__(self, "causation_id", causation_id)
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "payload", MappingProxyType(payload or {}))
        object.__setattr__(self, "metadata", MappingProxyType({}))
        object.__setattr__(self, "_initialized", True)

    def __setattr__(self, name: str, value: Any) -> None:
        """Prevent mutations after initialization (enforce immutability)."""
        if hasattr(self, "_initialized") and self._initialized:
            msg = f"cannot assign to field {name!r}; {self.__class__.__name__} is immutable"
            raise AttributeError(msg)
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        """Prevent field deletion after initialization (enforce immutability)."""
        if hasattr(self, "_initialized") and self._initialized:
            msg = f"cannot delete field {name!r}; {self.__class__.__name__} is immutable"
            raise AttributeError(msg)
        object.__delattr__(self, name)

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
    """Emitted when a work item is created.

    Payload fields:
        - title: str - Title of the work item
        - description: str - Detailed description
        - project_id: str - Associated project ID
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkItemCreated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class AgentAssigned(DomainEvent):
    """Emitted when an agent is assigned to work item.

    Payload fields:
        - agent_id: str - ID of the assigned agent
        - assigned_at: str - ISO timestamp when assigned
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentAssigned event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemStarted(DomainEvent):
    """Emitted when work begins on item..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkItemStarted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemUnderReview(DomainEvent):
    """Emitted when work item enters review..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkItemUnderReview event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemCompleted(DomainEvent):
    """Emitted when work item completes successfully..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkItemCompleted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemFailed(DomainEvent):
    """Emitted when work item fails..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkItemFailed event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemBlocked(DomainEvent):
    """Emitted when work item is blocked..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkItemBlocked event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemUnblocked(DomainEvent):
    """Emitted when work item is unblocked..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkItemUnblocked event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkflowAttached(DomainEvent):
    """Emitted when workflow attached to work item..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkflowAttached event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemStageUpdated(DomainEvent):
    """Emitted when work item moves to new stage..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkItemStageUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemLabelsUpdated(DomainEvent):
    """Emitted when work item labels change..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkItemLabelsUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class WorkItemPriorityUpdated(DomainEvent):
    """Emitted when work item priority changes..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkItemPriorityUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


# =============================================================================
# Agent Events
# =============================================================================


class AgentCreated(DomainEvent):
    """Emitted when agent is created..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentCreated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentCapabilityAdded(DomainEvent):
    """Emitted when capability added to agent..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentCapabilityAdded event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentCapabilityRemoved(DomainEvent):
    """Emitted when capability removed from agent..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentCapabilityRemoved event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentCapabilityUpdated(DomainEvent):
    """Emitted when capability proficiency updated..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentCapabilityUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentModelUpdated(DomainEvent):
    """Emitted when agent LLM model changed..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentModelUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentTimeoutUpdated(DomainEvent):
    """Emitted when agent timeout changed..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentTimeoutUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentMaxRetriesUpdated(DomainEvent):
    """Emitted when agent max retries changed..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentMaxRetriesUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentConstraintsUpdated(DomainEvent):
    """Emitted when agent constraints changed..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentConstraintsUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentMcpServerAdded(DomainEvent):
    """Emitted when MCP server added to agent..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentMcpServerAdded event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


class AgentMcpServerRemoved(DomainEvent):
    """Emitted when MCP server removed from agent..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentMcpServerRemoved event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, **kwargs)


# =============================================================================
# Agent Execution Events
# =============================================================================


class ExecutionInitialized(DomainEvent):
    """Emitted when execution is initialized..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ExecutionInitialized event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionStarted(DomainEvent):
    """Emitted when execution starts..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ExecutionStarted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionCompleted(DomainEvent):
    """Emitted when execution completes successfully.

    Payload fields:
        - output: str - Execution result/output
        - duration_seconds: float - Total execution duration
        - completed_at: str - ISO timestamp when completed
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ExecutionCompleted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionFailed(DomainEvent):
    """Emitted when execution fails..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ExecutionFailed event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionTimeout(DomainEvent):
    """Emitted when execution times out..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ExecutionTimeout event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionCancelled(DomainEvent):
    """Emitted when execution is cancelled..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ExecutionCancelled event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionPaused(DomainEvent):
    """Emitted when execution is paused..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ExecutionPaused event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


class ExecutionResumed(DomainEvent):
    """Emitted when execution is resumed..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ExecutionResumed event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentExecution", payload=payload, **kwargs)


# =============================================================================
# Workflow Events
# =============================================================================


class WorkflowCreated(DomainEvent):
    """Emitted when a workflow is created..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkflowCreated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowStarted(DomainEvent):
    """Emitted when workflow execution begins..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkflowStarted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowStageAdvanced(DomainEvent):
    """Emitted when workflow moves to the next stage..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkflowStageAdvanced event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowStageStatusUpdated(DomainEvent):
    """Emitted when a stage's status changes..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkflowStageStatusUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowCompleted(DomainEvent):
    """Emitted when workflow completes successfully..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkflowCompleted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowFailed(DomainEvent):
    """Emitted when workflow fails..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkflowFailed event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowPaused(DomainEvent):
    """Emitted when workflow is paused..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkflowPaused event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowResumed(DomainEvent):
    """Emitted when workflow is resumed..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkflowResumed event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


class WorkflowCancelled(DomainEvent):
    """Emitted when workflow is cancelled..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkflowCancelled event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Workflow", payload=payload, **kwargs)


# =============================================================================
# Review Cycle Events
# =============================================================================


class ReviewCycleCreated(DomainEvent):
    """Emitted when a review cycle is created..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ReviewCycleCreated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewIterationStarted(DomainEvent):
    """Emitted when a new review iteration starts..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ReviewIterationStarted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewFeedbackSubmitted(DomainEvent):
    """Emitted when reviewer provides feedback..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ReviewFeedbackSubmitted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewCycleApproved(DomainEvent):
    """Emitted when review is approved..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ReviewCycleApproved event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewCycleRejected(DomainEvent):
    """Emitted when review is rejected..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ReviewCycleRejected event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


class ReviewCycleEscalated(DomainEvent):
    """Emitted when review is escalated to human..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ReviewCycleEscalated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ReviewCycle", payload=payload, **kwargs)


# =============================================================================
# Project Context Events
# =============================================================================


class ProjectContextCreated(DomainEvent):
    """Emitted when project context is created..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ProjectContextCreated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)


class ProjectTestConfigUpdated(DomainEvent):
    """Emitted when test configuration changes..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ProjectTestConfigUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)


class ProjectDockerConfigUpdated(DomainEvent):
    """Emitted when Docker configuration changes..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ProjectDockerConfigUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)


class ProjectWorkflowMappingAdded(DomainEvent):
    """Emitted when custom workflow mapping is added..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ProjectWorkflowMappingAdded event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectContext", payload=payload, **kwargs)


# =============================================================================
# Pipeline Execution Events
# =============================================================================


class PipelineStageStarted(DomainEvent):
    """Emitted when a pipeline stage starts execution..
    """

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
        """Initialize PipelineStageStarted event."""
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
    """Emitted when a pipeline stage completes successfully..
    """

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
        """Initialize PipelineStageCompleted event."""
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
    """Emitted when a pipeline stage fails..
    """

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
        """Initialize PipelineStageFailed event."""
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
    """Emitted when entire pipeline completes successfully..
    """

    def __init__(
        self,
        aggregate_id: str,
        pipeline_id: str,
        workflow_id: str,
        completed_stages: list[str],
        outputs: dict[str, Any],
        duration_seconds: float,
        timestamp: datetime | None = None,
        **kwargs: Any,
    ):
        """Initialize PipelineCompleted event."""
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
    """Emitted when pipeline execution fails..
    """

    def __init__(
        self,
        aggregate_id: str,
        pipeline_id: str,
        workflow_id: str,
        error: str,
        completed_stages: list[str],
        failed_stages: list[str],
        timestamp: datetime | None = None,
        **kwargs: Any,
    ):
        """Initialize PipelineFailed event."""
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
    """Emitted when project configuration is updated..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize ProjectConfigUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


class AgentConfigUpdated(DomainEvent):
    """Emitted when agent configuration is updated..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize AgentConfigUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="AgentConfig", payload=payload, **kwargs)


class PipelineConfigUpdated(DomainEvent):
    """Emitted when pipeline configuration is updated..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize PipelineConfigUpdated event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="PipelineConfig", payload=payload, **kwargs)


class EnvironmentVariableChanged(DomainEvent):
    """Emitted when environment variable is added, updated, or removed..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize EnvironmentVariableChanged event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


class CommandMounted(DomainEvent):
    """Emitted when command is mounted to project agent..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize CommandMounted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


class CommandUnmounted(DomainEvent):
    """Emitted when command is unmounted from project agent..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize CommandUnmounted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


class SubAgentMounted(DomainEvent):
    """Emitted when sub-agent is mounted to project agent..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize SubAgentMounted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


class SubAgentUnmounted(DomainEvent):
    """Emitted when sub-agent is unmounted from project agent..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize SubAgentUnmounted event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="ProjectConfig", payload=payload, **kwargs)


# =============================================================================
# Board Events
# =============================================================================


class WorkItemColumnChanged(DomainEvent):
    """Emitted when work item moves between board columns..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize WorkItemColumnChanged event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, **kwargs)


class BoardReconciled(DomainEvent):
    """Emitted after board structure synchronized with config..
    """

    def __init__(self, aggregate_id: str, payload: dict[str, Any], **kwargs: Any):
        """Initialize BoardReconciled event."""
        super().__init__(aggregate_id=aggregate_id, aggregate_type="Board", payload=payload, **kwargs)
