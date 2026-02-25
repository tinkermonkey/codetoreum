"""Work Item aggregate root."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from codetoreum.domain.events import (
    AgentAssigned,
    DomainEvent,
    WorkflowAttached,
    WorkItemBlocked,
    WorkItemCompleted,
    WorkItemCreated,
    WorkItemFailed,
    WorkItemLabelsUpdated,
    WorkItemPriorityUpdated,
    WorkItemStageUpdated,
    WorkItemStarted,
    WorkItemUnblocked,
    WorkItemUnderReview,
)
from codetoreum.domain.exceptions import DomainError


class WorkItemStatus(Enum):
    """Status enumeration for work items."""

    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    UNDER_REVIEW = "under_review"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class WorkItemPriority(Enum):
    """Priority levels for work items."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class WorkItem:
    """
    Work Item aggregate root.

    Represents a unit of work (issue, task, feature) that flows through
    the system. Maintains its own consistency boundary and emits events
    for all state changes.
    """

    # Identity
    id: str
    project_id: str

    # Core attributes
    title: str
    description: str

    # State
    status: WorkItemStatus
    priority: WorkItemPriority

    # Metadata
    labels: list[str]
    external_id: str | None  # ID in external system (GitHub issue #, etc.)
    external_url: str | None

    # Assignment
    assigned_agent_id: str | None
    assigned_at: datetime | None

    # Workflow tracking
    current_workflow_id: str | None
    current_stage: str | None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    # Event tracking
    _events: list[DomainEvent] = field(default_factory=list, init=False, repr=False)
    _version: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate invariants after initialization."""
        self._validate_invariants()

    def _validate_invariants(self) -> None:
        """
        Validate domain invariants.

        Invariants:
        - Title must be non-empty
        - Must belong to a project
        - Priority must be valid
        - Status must be valid
        """
        if not self.title or not self.title.strip():
            msg = "Work item must have a non-empty title"
            raise DomainError(msg)

        if not self.project_id:
            msg = "Work item must belong to a project"
            raise DomainError(msg)

        if not isinstance(self.status, WorkItemStatus):
            msg = f"Invalid status: {self.status}"
            raise DomainError(msg)

        if not isinstance(self.priority, WorkItemPriority):
            msg = f"Invalid priority: {self.priority}"
            raise DomainError(msg)

    # Creation
    @classmethod
    def create(
        cls,
        title: str,
        description: str,
        project_id: str,
        labels: list[str] | None = None,
        priority: WorkItemPriority = WorkItemPriority.MEDIUM,
        external_id: str | None = None,
        external_url: str | None = None,
    ) -> "WorkItem":
        """
        Factory method to create a new work item.

        Args:
            title: Work item title
            description: Work item description
            project_id: ID of the project this work item belongs to
            labels: Optional list of labels
            priority: Work item priority (defaults to MEDIUM)
            external_id: Optional external system ID
            external_url: Optional external system URL

        Returns:
            Newly created WorkItem instance

        Emits: WorkItemCreated event
        """
        work_item = cls(
            id=str(uuid4()),
            project_id=project_id,
            title=title,
            description=description,
            status=WorkItemStatus.NEW,
            priority=priority,
            labels=labels or [],
            external_id=external_id,
            external_url=external_url,
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            completed_at=None,
        )

        # Emit creation event
        event = WorkItemCreated(
            aggregate_id=work_item.id,
            payload={
                "title": title,
                "description": description,
                "project_id": project_id,
                "labels": labels or [],
                "priority": priority.value,
                "external_id": external_id,
                "external_url": external_url,
            },
        )
        work_item._add_event(event)

        return work_item

    # State transitions
    def assign_agent(self, agent_id: str, reason: str) -> None:
        """
        Assign an agent to this work item.

        Business rules:
        - Can only assign to NEW or ASSIGNED items
        - Cannot assign same agent twice

        Args:
            agent_id: ID of the agent to assign
            reason: Reason for assignment

        Raises:
            DomainError: If business rules are violated

        Emits: AgentAssigned event
        """
        if self.status not in [WorkItemStatus.NEW, WorkItemStatus.ASSIGNED]:
            msg = f"Cannot assign agent to work item in status {self.status.value}"
            raise DomainError(msg)

        if self.assigned_agent_id == agent_id:
            msg = f"Agent {agent_id} is already assigned"
            raise DomainError(msg)

        self.assigned_agent_id = agent_id
        self.assigned_at = datetime.now(UTC)
        self.status = WorkItemStatus.ASSIGNED
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = AgentAssigned(
            aggregate_id=self.id,
            payload={
                "agent_id": agent_id,
                "reason": reason,
                "assigned_at": self.assigned_at.isoformat(),
            },
        )
        self._add_event(event)

    def start(self) -> None:
        """
        Start work on this item.

        Business rules:
        - Must be assigned to an agent
        - Must be in ASSIGNED status

        Raises:
            DomainError: If business rules are violated

        Emits: WorkItemStarted event
        """
        if not self.assigned_agent_id:
            msg = "Cannot start unassigned work item"
            raise DomainError(msg)

        if self.status != WorkItemStatus.ASSIGNED:
            msg = f"Cannot start work item in status {self.status.value}"
            raise DomainError(msg)

        self.status = WorkItemStatus.IN_PROGRESS
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkItemStarted(
            aggregate_id=self.id,
            payload={
                "started_at": self.updated_at.isoformat(),
                "agent_id": self.assigned_agent_id,
            },
        )
        self._add_event(event)

    def mark_under_review(self) -> None:
        """
        Mark work item as under review.

        Business rules:
        - Must be in progress

        Raises:
            DomainError: If business rules are violated

        Emits: WorkItemUnderReview event
        """
        if self.status != WorkItemStatus.IN_PROGRESS:
            msg = f"Cannot review work item in status {self.status.value}"
            raise DomainError(msg)

        self.status = WorkItemStatus.UNDER_REVIEW
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkItemUnderReview(
            aggregate_id=self.id,
            payload={"review_started_at": self.updated_at.isoformat()},
        )
        self._add_event(event)

    def complete(self) -> None:
        """
        Mark work item as completed.

        Business rules:
        - Must be in progress or under review

        Raises:
            DomainError: If business rules are violated

        Emits: WorkItemCompleted event
        """
        if self.status not in [
            WorkItemStatus.IN_PROGRESS,
            WorkItemStatus.UNDER_REVIEW,
        ]:
            msg = f"Cannot complete work item in status {self.status.value}"
            raise DomainError(msg)

        self.status = WorkItemStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        self.updated_at = self.completed_at
        self._version += 1

        event = WorkItemCompleted(
            aggregate_id=self.id,
            payload={
                "completed_at": self.completed_at.isoformat(),
                "agent_id": self.assigned_agent_id,
            },
        )
        self._add_event(event)

    def fail(self, reason: str, error_details: dict[str, Any] | None = None) -> None:
        """
        Mark work item as failed.

        Business rules:
        - Can fail from any non-terminal state

        Args:
            reason: Reason for failure
            error_details: Optional additional error information

        Raises:
            DomainError: If business rules are violated

        Emits: WorkItemFailed event
        """
        if self.status in [WorkItemStatus.COMPLETED, WorkItemStatus.FAILED]:
            msg = f"Cannot fail work item in terminal status {self.status.value}"
            raise DomainError(msg)

        self.status = WorkItemStatus.FAILED
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkItemFailed(
            aggregate_id=self.id,
            payload={
                "failed_at": self.updated_at.isoformat(),
                "reason": reason,
                "error_details": error_details or {},
                "agent_id": self.assigned_agent_id,
            },
        )
        self._add_event(event)

    def block(self, reason: str, blocking_issue_id: str | None = None) -> None:
        """
        Block work item.

        Business rules:
        - Cannot block completed or failed items

        Args:
            reason: Reason for blocking
            blocking_issue_id: Optional ID of blocking issue

        Raises:
            DomainError: If business rules are violated

        Emits: WorkItemBlocked event
        """
        if self.status in [WorkItemStatus.COMPLETED, WorkItemStatus.FAILED]:
            msg = f"Cannot block work item in terminal status {self.status.value}"
            raise DomainError(msg)

        self.status = WorkItemStatus.BLOCKED
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkItemBlocked(
            aggregate_id=self.id,
            payload={
                "blocked_at": self.updated_at.isoformat(),
                "reason": reason,
                "blocking_issue_id": blocking_issue_id,
            },
        )
        self._add_event(event)

    def unblock(self) -> None:
        """
        Unblock work item.

        Business rules:
        - Must be in blocked status

        Raises:
            DomainError: If business rules are violated

        Emits: WorkItemUnblocked event
        """
        if self.status != WorkItemStatus.BLOCKED:
            msg = "Cannot unblock non-blocked work item"
            raise DomainError(msg)

        # Return to previous state (assume assigned if agent exists)
        self.status = WorkItemStatus.ASSIGNED if self.assigned_agent_id else WorkItemStatus.NEW
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkItemUnblocked(
            aggregate_id=self.id,
            payload={
                "unblocked_at": self.updated_at.isoformat(),
                "new_status": self.status.value,
            },
        )
        self._add_event(event)

    # Workflow tracking
    def attach_workflow(self, workflow_id: str) -> None:
        """
        Attach a workflow to this work item.

        Args:
            workflow_id: ID of the workflow to attach

        Raises:
            DomainError: If work item already has a workflow

        Emits: WorkflowAttached event
        """
        if self.current_workflow_id:
            msg = f"Work item already has workflow {self.current_workflow_id}"
            raise DomainError(msg)

        self.current_workflow_id = workflow_id
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkflowAttached(
            aggregate_id=self.id,
            payload={
                "workflow_id": workflow_id,
                "attached_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    def update_stage(self, stage: str) -> None:
        """
        Update current workflow stage.

        Args:
            stage: New stage name

        Raises:
            DomainError: If work item doesn't have a workflow

        Emits: WorkItemStageUpdated event
        """
        if not self.current_workflow_id:
            msg = "Cannot update stage without workflow"
            raise DomainError(msg)

        old_stage = self.current_stage
        self.current_stage = stage
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkItemStageUpdated(
            aggregate_id=self.id,
            payload={
                "workflow_id": self.current_workflow_id,
                "old_stage": old_stage,
                "new_stage": stage,
                "updated_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    # Metadata
    def update_labels(self, labels: list[str]) -> None:
        """
        Update work item labels.

        Args:
            labels: New list of labels

        Raises:
            DomainError: If labels is None or not a list

        Emits: WorkItemLabelsUpdated event
        """
        if labels is None:
            msg = "Labels cannot be None"
            raise DomainError(msg)

        if not isinstance(labels, list):
            msg = "Labels must be a list"
            raise DomainError(msg)

        # Validate all elements are strings
        if not all(isinstance(label, str) for label in labels):
            msg = "All labels must be strings"
            raise DomainError(msg)

        old_labels = self.labels.copy()
        self.labels = labels
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkItemLabelsUpdated(
            aggregate_id=self.id,
            payload={
                "old_labels": old_labels,
                "new_labels": labels,
                "updated_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    def update_priority(self, priority: WorkItemPriority) -> None:
        """
        Update work item priority.

        Args:
            priority: New priority level

        Emits: WorkItemPriorityUpdated event
        """
        old_priority = self.priority
        self.priority = priority
        self.updated_at = datetime.now(UTC)
        self._version += 1

        event = WorkItemPriorityUpdated(
            aggregate_id=self.id,
            payload={
                "old_priority": old_priority.value,
                "new_priority": priority.value,
                "updated_at": self.updated_at.isoformat(),
            },
        )
        self._add_event(event)

    # Query methods
    def can_start(self) -> bool:
        """
        Check if work item can be started.

        Returns:
            True if work item can be started, False otherwise
        """
        return self.assigned_agent_id is not None and self.status == WorkItemStatus.ASSIGNED

    def is_terminal(self) -> bool:
        """
        Check if work item is in terminal state.

        Returns:
            True if work item is completed or failed, False otherwise
        """
        return self.status in [WorkItemStatus.COMPLETED, WorkItemStatus.FAILED]

    def is_active(self) -> bool:
        """
        Check if work item is actively being worked on.

        Returns:
            True if work item is in progress or under review, False otherwise
        """
        return self.status in [
            WorkItemStatus.IN_PROGRESS,
            WorkItemStatus.UNDER_REVIEW,
        ]

    # Event management
    def _add_event(self, event: DomainEvent) -> None:
        """
        Add event to pending events list.

        Args:
            event: Domain event to add
        """
        self._events.append(event)

    def get_pending_events(self) -> list[DomainEvent]:
        """
        Get all pending events.

        Returns:
            Shallow copy of the pending events list. Creates a new list
            containing references to the same event objects.
        """
        return list(self._events)

    def clear_events(self) -> None:
        """Clear pending events (after persistence)."""
        self._events.clear()

    # Reconstruction from events
    @classmethod
    def from_events(cls, events: list[DomainEvent]) -> "WorkItem":
        """
        Reconstruct work item from event stream.

        Used for event sourcing - rebuild aggregate state from events.

        Args:
            events: List of domain events to replay

        Returns:
            Reconstructed WorkItem instance

        Raises:
            DomainError: If event stream is invalid
        """
        if not events:
            msg = "Cannot reconstruct work item from empty event stream"
            raise DomainError(msg)

        # First event must be WorkItemCreated
        first_event = events[0]
        if not isinstance(first_event, WorkItemCreated):
            msg = "First event must be WorkItemCreated"
            raise DomainError(msg)

        # Create initial state from creation event
        payload = first_event.payload

        # Validate required fields are present in payload
        required_fields = ["project_id", "title", "description", "priority", "labels"]
        missing_fields = [f for f in required_fields if f not in payload]
        if missing_fields:
            msg = f"Missing required fields in WorkItemCreated event: {', '.join(missing_fields)}"
            raise DomainError(msg)

        work_item = cls(
            id=first_event.aggregate_id,
            project_id=payload["project_id"],
            title=payload["title"],
            description=payload["description"],
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority(payload["priority"]),
            labels=payload["labels"],
            external_id=payload.get("external_id"),
            external_url=payload.get("external_url"),
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            created_at=first_event.occurred_at,
            updated_at=first_event.occurred_at,
            completed_at=None,
        )

        # Apply subsequent events
        for event in events[1:]:
            work_item._apply_event(event)

        work_item._version = len(events)
        return work_item

    def _apply_agent_assigned(self, event: AgentAssigned) -> None:
        """Apply AgentAssigned event."""
        self.assigned_agent_id = event.payload["agent_id"]
        self.assigned_at = datetime.fromisoformat(event.payload["assigned_at"])
        self.status = WorkItemStatus.ASSIGNED

    def _apply_work_item_started(self, _event: WorkItemStarted) -> None:
        """Apply WorkItemStarted event."""
        self.status = WorkItemStatus.IN_PROGRESS

    def _apply_work_item_under_review(self, _event: WorkItemUnderReview) -> None:
        """Apply WorkItemUnderReview event."""
        self.status = WorkItemStatus.UNDER_REVIEW

    def _apply_work_item_completed(self, event: WorkItemCompleted) -> None:
        """Apply WorkItemCompleted event."""
        self.status = WorkItemStatus.COMPLETED
        self.completed_at = datetime.fromisoformat(event.payload["completed_at"])

    def _apply_work_item_failed(self, _event: WorkItemFailed) -> None:
        """Apply WorkItemFailed event."""
        self.status = WorkItemStatus.FAILED

    def _apply_work_item_blocked(self, _event: WorkItemBlocked) -> None:
        """Apply WorkItemBlocked event."""
        self.status = WorkItemStatus.BLOCKED

    def _apply_work_item_unblocked(self, event: WorkItemUnblocked) -> None:
        """Apply WorkItemUnblocked event."""
        self.status = WorkItemStatus(event.payload["new_status"])

    def _apply_workflow_attached(self, event: WorkflowAttached) -> None:
        """Apply WorkflowAttached event."""
        self.current_workflow_id = event.payload["workflow_id"]

    def _apply_work_item_stage_updated(self, event: WorkItemStageUpdated) -> None:
        """Apply WorkItemStageUpdated event."""
        self.current_stage = event.payload["new_stage"]

    def _apply_work_item_labels_updated(self, event: WorkItemLabelsUpdated) -> None:
        """Apply WorkItemLabelsUpdated event."""
        self.labels = event.payload["new_labels"]

    def _apply_work_item_priority_updated(self, event: WorkItemPriorityUpdated) -> None:
        """Apply WorkItemPriorityUpdated event."""
        self.priority = WorkItemPriority(event.payload["new_priority"])

    def _get_event_handlers(self) -> dict[type, Any]:
        """Get mapping of event types to handler methods.

        Returns:
            Dictionary mapping event types to handler methods
        """
        return {
            AgentAssigned: self._apply_agent_assigned,
            WorkItemStarted: self._apply_work_item_started,
            WorkItemUnderReview: self._apply_work_item_under_review,
            WorkItemCompleted: self._apply_work_item_completed,
            WorkItemFailed: self._apply_work_item_failed,
            WorkItemBlocked: self._apply_work_item_blocked,
            WorkItemUnblocked: self._apply_work_item_unblocked,
            WorkflowAttached: self._apply_workflow_attached,
            WorkItemStageUpdated: self._apply_work_item_stage_updated,
            WorkItemLabelsUpdated: self._apply_work_item_labels_updated,
            WorkItemPriorityUpdated: self._apply_work_item_priority_updated,
        }

    def _apply_event(self, event: DomainEvent) -> None:
        """
        Apply an event to update state.

        Args:
            event: Domain event to apply
        """
        # Dispatch to event-specific handler using event type
        handlers = self._get_event_handlers()
        event_type = type(event)
        if event_type in handlers:
            handlers[event_type](event)

        # Update timestamp for all events
        self.updated_at = event.occurred_at
