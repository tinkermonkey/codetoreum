"""Domain events base classes and specific event types."""

from datetime import datetime
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
        self.occurred_at = occurred_at or datetime.utcnow()
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

    pass


class AgentAssigned(DomainEvent):
    """Emitted when an agent is assigned to work item."""

    pass


class WorkItemStarted(DomainEvent):
    """Emitted when work begins on item."""

    pass


class WorkItemUnderReview(DomainEvent):
    """Emitted when work item enters review."""

    pass


class WorkItemCompleted(DomainEvent):
    """Emitted when work item completes successfully."""

    pass


class WorkItemFailed(DomainEvent):
    """Emitted when work item fails."""

    pass


class WorkItemBlocked(DomainEvent):
    """Emitted when work item is blocked."""

    pass


class WorkItemUnblocked(DomainEvent):
    """Emitted when work item is unblocked."""

    pass


class WorkflowAttached(DomainEvent):
    """Emitted when workflow attached to work item."""

    pass


class WorkItemStageUpdated(DomainEvent):
    """Emitted when work item moves to new stage."""

    pass


class WorkItemLabelsUpdated(DomainEvent):
    """Emitted when work item labels change."""

    pass


class WorkItemPriorityUpdated(DomainEvent):
    """Emitted when work item priority changes."""

    pass


# =============================================================================
# Agent Events
# =============================================================================


class AgentCreated(DomainEvent):
    """Emitted when agent is created."""

    pass


class AgentCapabilityAdded(DomainEvent):
    """Emitted when capability added to agent."""

    pass


class AgentCapabilityRemoved(DomainEvent):
    """Emitted when capability removed from agent."""

    pass


class AgentCapabilityUpdated(DomainEvent):
    """Emitted when capability proficiency updated."""

    pass


class AgentModelUpdated(DomainEvent):
    """Emitted when agent LLM model changed."""

    pass


class AgentTimeoutUpdated(DomainEvent):
    """Emitted when agent timeout changed."""

    pass


class AgentConstraintsUpdated(DomainEvent):
    """Emitted when agent constraints changed."""

    pass


class AgentMcpServerAdded(DomainEvent):
    """Emitted when MCP server added to agent."""

    pass


class AgentMcpServerRemoved(DomainEvent):
    """Emitted when MCP server removed from agent."""

    pass


# =============================================================================
# Agent Execution Events
# =============================================================================


class ExecutionInitialized(DomainEvent):
    """Emitted when execution is initialized."""

    pass


class ExecutionStarted(DomainEvent):
    """Emitted when execution starts."""

    pass


class ExecutionCompleted(DomainEvent):
    """Emitted when execution completes successfully."""

    pass


class ExecutionFailed(DomainEvent):
    """Emitted when execution fails."""

    pass


class ExecutionTimeout(DomainEvent):
    """Emitted when execution times out."""

    pass
