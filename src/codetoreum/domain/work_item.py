"""Work Item aggregate root."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from codetoreum.domain.events.adapter_events import CodetoreumEvent, now_iso
from codetoreum.domain.events.work_item_events import (
    AgentAssignedEvent,
    WorkItemBlockedEvent,
    WorkItemCompletedEvent,
    WorkItemCreatedEvent,
    WorkItemFailedEvent,
    WorkItemLabelsUpdatedEvent,
    WorkItemPriorityUpdatedEvent,
    WorkItemStageUpdatedEvent,
    WorkItemStartedEvent,
    WorkItemUnblockedEvent,
    WorkItemUnderReviewEvent,
)
from codetoreum.domain.events.workflow_events import WorkflowAttachedEvent
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

    # PR and discussion tracking
    pr_id: str | None = None
    discussion_id: str | None = None
    completed_at: datetime | None = None

    # Event tracking
    _events: list[CodetoreumEvent] = field(default_factory=list, init=False, repr=False)
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
        pr_id: str | None = None,
        discussion_id: str | None = None,
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
            pr_id: Optional GitHub PR identifier
            discussion_id: Optional GitHub discussion identifier

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
            pr_id=pr_id,
            discussion_id=discussion_id,
            completed_at=None,
        )

        # Emit creation event
        event = WorkItemCreatedEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="domain",
            work_item_id=work_item.id,
            title=title,
            description=description,
            project_id=project_id,
            priority=priority.value,
            labels=tuple(labels or []),
            external_id=external_id or "",
            external_url=external_url or "",
            pr_id=pr_id or "",
            discussion_id=discussion_id or "",
            created_at=work_item.created_at.isoformat(),
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

        event = AgentAssignedEvent(
            type="workitem.agent_assigned",
            timestamp=now_iso(),
            source="domain",
            work_item_id=self.id,
            agent_id=agent_id,
            reason=reason,
            assigned_at=self.assigned_at.isoformat() if self.assigned_at else "",
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

        event = WorkItemStartedEvent(
            type="workitem.started",
            timestamp=now_iso(),
            source="domain",
            work_item_id=self.id,
            started_at=self.updated_at.isoformat() if self.updated_at else "",
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

        event = WorkItemUnderReviewEvent(
            type="workitem.under_review",
            timestamp=now_iso(),
            source="domain",
            work_item_id=self.id,
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

        event = WorkItemCompletedEvent(
            type="workitem.completed",
            timestamp=now_iso(),
            source="domain",
            work_item_id=self.id,
            completed_at=self.completed_at.isoformat() if self.completed_at else "",
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

        event = WorkItemFailedEvent(
            type="workitem.failed",
            timestamp=now_iso(),
            source="domain",
            work_item_id=self.id,
            reason=reason,
            new_status=self.status.value,
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

        event = WorkItemBlockedEvent(
            type="workitem.blocked",
            timestamp=now_iso(),
            source="domain",
            work_item_id=self.id,
            reason=reason,
            blocking_issue_id=blocking_issue_id or "",
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

        event = WorkItemUnblockedEvent(
            type="workitem.unblocked",
            timestamp=now_iso(),
            source="domain",
            work_item_id=self.id,
            new_status=self.status.value,
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

        event = WorkflowAttachedEvent(
            type="workflow.attached",
            timestamp=self.updated_at.isoformat(),
            source="work_item",
            work_item_id=self.id,
            workflow_id=workflow_id,
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

        event = WorkItemStageUpdatedEvent(
            type="workitem.stage_updated",
            timestamp=now_iso(),
            source="domain",
            work_item_id=self.id,
            old_stage=old_stage or "",
            new_stage=stage,
        )
        self._add_event(event)

    def record_board_position(self, column: str) -> None:
        """Mirror the work item's current board column onto the aggregate.

        Unlike :meth:`update_stage` — which models a transition inside an attached
        workflow and therefore requires one — this records the board's authoritative
        position even when no workflow is attached yet (e.g. an item sitting in
        Backlog). It reuses WorkItemStageUpdatedEvent: ``current_stage`` carries the
        column name so reads (REST API ``current_column``/``current_stage``) reflect
        the item's board position. No-op when the column is unchanged.
        """
        if self.current_stage == column:
            return
        old_stage = self.current_stage
        self.current_stage = column
        self.updated_at = datetime.now(UTC)
        self._version += 1
        self._add_event(
            WorkItemStageUpdatedEvent(
                type="workitem.stage_updated",
                timestamp=now_iso(),
                source="domain",
                work_item_id=self.id,
                old_stage=old_stage or "",
                new_stage=column,
            )
        )

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

        event = WorkItemLabelsUpdatedEvent(
            type="workitem.labels_updated",
            timestamp=now_iso(),
            source="domain",
            work_item_id=self.id,
            old_labels=tuple(old_labels),
            new_labels=tuple(labels),
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

        event = WorkItemPriorityUpdatedEvent(
            type="workitem.priority_updated",
            timestamp=now_iso(),
            source="domain",
            work_item_id=self.id,
            old_priority=old_priority.value,
            new_priority=priority.value,
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
    def _add_event(self, event: CodetoreumEvent) -> None:
        """
        Add event to pending events list.

        Args:
            event: Domain event to add
        """
        self._events.append(event)

    def get_pending_events(self) -> list[CodetoreumEvent]:
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
    def from_events(cls, events: list[CodetoreumEvent]) -> "WorkItem":
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
        if not isinstance(first_event, WorkItemCreatedEvent):
            msg = "First event must be WorkItemCreated"
            raise DomainError(msg)

        # Create initial state from creation event

        work_item = cls(
            id=first_event.work_item_id,
            project_id=first_event.project_id,
            title=first_event.title,
            description=first_event.description,
            status=WorkItemStatus.NEW,
            priority=WorkItemPriority(first_event.priority),
            labels=list(first_event.labels),
            external_id=first_event.external_id or None,
            external_url=first_event.external_url or None,
            assigned_agent_id=None,
            assigned_at=None,
            current_workflow_id=None,
            current_stage=None,
            created_at=datetime.fromisoformat(first_event.created_at) if first_event.created_at else datetime.now(UTC),
            updated_at=datetime.fromisoformat(first_event.created_at) if first_event.created_at else datetime.now(UTC),
            pr_id=first_event.pr_id or None,
            discussion_id=first_event.discussion_id or None,
            completed_at=None,
        )

        # Apply subsequent events
        for event in events[1:]:
            work_item._apply_event(event)

        work_item._version = len(events)
        return work_item

    def _apply_agent_assigned(self, event: AgentAssignedEvent) -> None:
        """Apply AgentAssigned event."""
        self.assigned_agent_id = event.agent_id
        self.assigned_at = datetime.fromisoformat(event.assigned_at) if event.assigned_at else datetime.now(UTC)
        self.status = WorkItemStatus.ASSIGNED

    def _apply_work_item_started(self, _event: WorkItemStartedEvent) -> None:
        """Apply WorkItemStarted event."""
        self.status = WorkItemStatus.IN_PROGRESS

    def _apply_work_item_under_review(self, _event: WorkItemUnderReviewEvent) -> None:
        """Apply WorkItemUnderReview event."""
        self.status = WorkItemStatus.UNDER_REVIEW

    def _apply_work_item_completed(self, event: WorkItemCompletedEvent) -> None:
        """Apply WorkItemCompleted event."""
        self.status = WorkItemStatus.COMPLETED
        self.completed_at = datetime.fromisoformat(event.completed_at) if event.completed_at else datetime.now(UTC)

    def _apply_work_item_failed(self, _event: WorkItemFailedEvent) -> None:
        """Apply WorkItemFailed event."""
        self.status = WorkItemStatus.FAILED

    def _apply_work_item_blocked(self, _event: WorkItemBlockedEvent) -> None:
        """Apply WorkItemBlocked event."""
        self.status = WorkItemStatus.BLOCKED

    def _apply_work_item_unblocked(self, event: WorkItemUnblockedEvent) -> None:
        """Apply WorkItemUnblocked event."""
        self.status = WorkItemStatus(event.new_status)

    def _apply_workflow_attached(self, event: WorkflowAttachedEvent) -> None:
        """Apply WorkflowAttachedEvent."""
        self.current_workflow_id = event.workflow_id

    def _apply_work_item_stage_updated(self, event: WorkItemStageUpdatedEvent) -> None:
        """Apply WorkItemStageUpdated event."""
        self.current_stage = event.new_stage

    def _apply_work_item_labels_updated(self, event: WorkItemLabelsUpdatedEvent) -> None:
        """Apply WorkItemLabelsUpdated event."""
        self.labels = list(event.new_labels)

    def _apply_work_item_priority_updated(self, event: WorkItemPriorityUpdatedEvent) -> None:
        """Apply WorkItemPriorityUpdated event."""
        self.priority = WorkItemPriority(event.new_priority)

    def _get_event_handlers(self) -> dict[type, Any]:
        """Get mapping of event types to handler methods.

        Returns:
            Dictionary mapping event types to handler methods
        """
        return {
            AgentAssignedEvent: self._apply_agent_assigned,
            WorkItemStartedEvent: self._apply_work_item_started,
            WorkItemUnderReviewEvent: self._apply_work_item_under_review,
            WorkItemCompletedEvent: self._apply_work_item_completed,
            WorkItemFailedEvent: self._apply_work_item_failed,
            WorkItemBlockedEvent: self._apply_work_item_blocked,
            WorkItemUnblockedEvent: self._apply_work_item_unblocked,
            WorkflowAttachedEvent: self._apply_workflow_attached,
            WorkItemStageUpdatedEvent: self._apply_work_item_stage_updated,
            WorkItemLabelsUpdatedEvent: self._apply_work_item_labels_updated,
            WorkItemPriorityUpdatedEvent: self._apply_work_item_priority_updated,
        }

    def _apply_event(self, event: CodetoreumEvent) -> None:
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
        self.updated_at = datetime.fromisoformat(event.timestamp) if event.timestamp else datetime.now(UTC)
