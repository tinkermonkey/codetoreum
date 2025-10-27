"""Domain events base classes and specific event types."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


class DomainEvent:
    """Base class for all domain events."""

    def __init__(
        self,
        aggregate_id: str,
        aggregate_type: str,
        payload: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        correlation_id: Optional[UUID] = None,
        causation_id: Optional[UUID] = None,
        event_id: Optional[UUID] = None,
        occurred_at: Optional[datetime] = None,
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
        self.occurred_at = occurred_at or datetime.now(timezone.utc)
        self.correlation_id = correlation_id or uuid4()
        self.causation_id = causation_id
        self.user_id = user_id
        self.payload = payload or {}
        self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
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


# =============================================================================
# Work Item Events
# =============================================================================


class WorkItemCreated(DomainEvent):
    """Emitted when a work item is created."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
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
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


class AgentAssigned(DomainEvent):
    """Emitted when an agent is assigned to work item."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize AgentAssigned event.

        Required payload fields:
        - agent_id: str
        - reason: str
        - assigned_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


class WorkItemStarted(DomainEvent):
    """Emitted when work begins on item."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize WorkItemStarted event.

        Required payload fields:
        - started_at: str (ISO format)
        - agent_id: str
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


class WorkItemUnderReview(DomainEvent):
    """Emitted when work item enters review."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize WorkItemUnderReview event.

        Required payload fields:
        - review_started_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


class WorkItemCompleted(DomainEvent):
    """Emitted when work item completes successfully."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize WorkItemCompleted event.

        Required payload fields:
        - completed_at: str (ISO format)
        - agent_id: Optional[str]
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


class WorkItemFailed(DomainEvent):
    """Emitted when work item fails."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize WorkItemFailed event.

        Required payload fields:
        - failed_at: str (ISO format)
        - reason: str
        - error_details: Dict[str, Any]
        - agent_id: Optional[str]
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


class WorkItemBlocked(DomainEvent):
    """Emitted when work item is blocked."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize WorkItemBlocked event.

        Required payload fields:
        - blocked_at: str (ISO format)
        - reason: str
        - blocking_issue_id: Optional[str]
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


class WorkItemUnblocked(DomainEvent):
    """Emitted when work item is unblocked."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize WorkItemUnblocked event.

        Required payload fields:
        - unblocked_at: str (ISO format)
        - new_status: str
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


class WorkflowAttached(DomainEvent):
    """Emitted when workflow attached to work item."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize WorkflowAttached event.

        Required payload fields:
        - workflow_id: str
        - attached_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


class WorkItemStageUpdated(DomainEvent):
    """Emitted when work item moves to new stage."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize WorkItemStageUpdated event.

        Required payload fields:
        - workflow_id: str
        - old_stage: Optional[str]
        - new_stage: str
        - updated_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


class WorkItemLabelsUpdated(DomainEvent):
    """Emitted when work item labels change."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize WorkItemLabelsUpdated event.

        Required payload fields:
        - old_labels: List[str]
        - new_labels: List[str]
        - updated_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


class WorkItemPriorityUpdated(DomainEvent):
    """Emitted when work item priority changes."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize WorkItemPriorityUpdated event.

        Required payload fields:
        - old_priority: int
        - new_priority: int
        - updated_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="WorkItem",
            payload=payload,
            **kwargs
        )


# =============================================================================
# Agent Events
# =============================================================================


class AgentCreated(DomainEvent):
    """Emitted when agent is created."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize AgentCreated event.

        Required payload fields:
        - name: str
        - display_name: str
        - agent_type: str
        - model: str
        - capabilities: List[str]
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="Agent",
            payload=payload,
            **kwargs
        )


class AgentCapabilityAdded(DomainEvent):
    """Emitted when capability added to agent."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize AgentCapabilityAdded event.

        Required payload fields:
        - skill: str
        - proficiency: float
        - added_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="Agent",
            payload=payload,
            **kwargs
        )


class AgentCapabilityRemoved(DomainEvent):
    """Emitted when capability removed from agent."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize AgentCapabilityRemoved event.

        Required payload fields:
        - skill: str
        - removed_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="Agent",
            payload=payload,
            **kwargs
        )


class AgentCapabilityUpdated(DomainEvent):
    """Emitted when capability proficiency updated."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize AgentCapabilityUpdated event.

        Required payload fields:
        - skill: str
        - old_proficiency: float
        - new_proficiency: float
        - updated_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="Agent",
            payload=payload,
            **kwargs
        )


class AgentModelUpdated(DomainEvent):
    """Emitted when agent LLM model changed."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize AgentModelUpdated event.

        Required payload fields:
        - old_model: str
        - new_model: str
        - updated_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="Agent",
            payload=payload,
            **kwargs
        )


class AgentTimeoutUpdated(DomainEvent):
    """Emitted when agent timeout changed."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize AgentTimeoutUpdated event.

        Required payload fields:
        - old_timeout: int
        - new_timeout: int
        - updated_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="Agent",
            payload=payload,
            **kwargs
        )


class AgentMaxRetriesUpdated(DomainEvent):
    """Emitted when agent max retries changed."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize AgentMaxRetriesUpdated event.

        Required payload fields:
        - old_max_retries: int
        - new_max_retries: int
        - updated_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="Agent",
            payload=payload,
            **kwargs
        )


class AgentConstraintsUpdated(DomainEvent):
    """Emitted when agent constraints changed."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize AgentConstraintsUpdated event.

        Required payload fields:
        - old_constraints: Dict[str, bool]
        - new_constraints: Dict[str, bool]
        - updated_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="Agent",
            payload=payload,
            **kwargs
        )


class AgentMcpServerAdded(DomainEvent):
    """Emitted when MCP server added to agent."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize AgentMcpServerAdded event.

        Required payload fields:
        - server_name: str
        - added_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="Agent",
            payload=payload,
            **kwargs
        )


class AgentMcpServerRemoved(DomainEvent):
    """Emitted when MCP server removed from agent."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize AgentMcpServerRemoved event.

        Required payload fields:
        - server_name: str
        - removed_at: str (ISO format)
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="Agent",
            payload=payload,
            **kwargs
        )


# =============================================================================
# Agent Execution Events
# =============================================================================


class ExecutionInitialized(DomainEvent):
    """Emitted when execution is initialized."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize ExecutionInitialized event.

        Required payload fields:
        - agent_id: str
        - work_item_id: str
        - workflow_id: str
        - stage_name: str
        - model: str
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="AgentExecution",
            payload=payload,
            **kwargs
        )


class ExecutionStarted(DomainEvent):
    """Emitted when execution starts."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize ExecutionStarted event.

        Required payload fields:
        - started_at: str (ISO format)
        - container_name: Optional[str]
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="AgentExecution",
            payload=payload,
            **kwargs
        )


class ExecutionCompleted(DomainEvent):
    """Emitted when execution completes successfully."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize ExecutionCompleted event.

        Required payload fields:
        - completed_at: str (ISO format)
        - input_tokens: int
        - output_tokens: int
        - duration_seconds: Optional[float]
        - session_id: Optional[str]
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="AgentExecution",
            payload=payload,
            **kwargs
        )


class ExecutionFailed(DomainEvent):
    """Emitted when execution fails."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize ExecutionFailed event.

        Required payload fields:
        - failed_at: str (ISO format)
        - error_message: str
        - exit_code: Optional[int]
        - duration_seconds: Optional[float]
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="AgentExecution",
            payload=payload,
            **kwargs
        )


class ExecutionTimeout(DomainEvent):
    """Emitted when execution times out."""

    def __init__(self, aggregate_id: str, payload: Dict[str, Any], **kwargs):
        """
        Initialize ExecutionTimeout event.

        Required payload fields:
        - timeout_at: str (ISO format)
        - duration_seconds: Optional[float]
        """
        super().__init__(
            aggregate_id=aggregate_id,
            aggregate_type="AgentExecution",
            payload=payload,
            **kwargs
        )
