"""Work item domain events using frozen dataclasses.

All events are immutable frozen dataclasses subclassing CodetoreumEvent.
"""

from dataclasses import dataclass, field
from uuid import uuid4

from .adapter_events import CodetoreumEvent, now_iso


@dataclass(frozen=True)
class WorkItemCreatedEvent(CodetoreumEvent):
    """Emitted when a work item is created."""

    work_item_id: str = ""
    title: str = ""
    description: str = ""
    project_id: str = ""
    priority: int = 2
    labels: tuple = ()
    external_id: str = ""
    external_url: str = ""
    pr_id: str = ""
    discussion_id: str = ""
    initial_column: str | None = None
    created_at: str = ""
    parent_issue_id: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.title:
            raise ValueError("title is required")
        object.__setattr__(self, "labels", tuple(self.labels))

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "title": self.title,
                "description": self.description,
                "project_id": self.project_id,
                "priority": self.priority,
                "labels": list(self.labels),
                "external_id": self.external_id,
                "external_url": self.external_url,
                "pr_id": self.pr_id,
                "discussion_id": self.discussion_id,
                "initial_column": self.initial_column,
                "created_at": self.created_at,
                "parent_issue_id": self.parent_issue_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemCreatedEvent":
        return cls(
            type=data.get("type", "workitem.created"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data["work_item_id"],
            title=data["title"],
            description=data.get("description", ""),
            project_id=data["project_id"],
            priority=data.get("priority", 2),
            labels=tuple(data.get("labels", [])),
            external_id=data.get("external_id", ""),
            external_url=data.get("external_url", ""),
            pr_id=data.get("pr_id", ""),
            discussion_id=data.get("discussion_id", ""),
            initial_column=data.get("initial_column"),
            created_at=data.get("created_at", ""),
            parent_issue_id=data.get("parent_issue_id"),
        )


@dataclass(frozen=True)
class WorkItemUpdatedEvent(CodetoreumEvent):
    """Emitted when a work item is updated."""

    work_item_id: str = ""
    project_id: str = ""
    changes: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"work_item_id": self.work_item_id, "project_id": self.project_id, "changes": self.changes})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemUpdatedEvent":
        return cls(
            type=data.get("type", "workitem.updated"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            project_id=data.get("project_id", ""),
            changes=data.get("changes", {}),
        )


@dataclass(frozen=True)
class AgentAssignedEvent(CodetoreumEvent):
    """Emitted when an agent is assigned to a work item."""

    work_item_id: str = ""
    agent_id: str = ""
    reason: str = ""
    assigned_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "agent_id": self.agent_id,
                "reason": self.reason,
                "assigned_at": self.assigned_at,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AgentAssignedEvent":
        return cls(
            type=data.get("type", "workitem.agent_assigned"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            agent_id=data.get("agent_id", ""),
            reason=data.get("reason", ""),
            assigned_at=data.get("assigned_at", ""),
        )


@dataclass(frozen=True)
class WorkItemStartedEvent(CodetoreumEvent):
    """Emitted when a work item is started."""

    work_item_id: str = ""
    agent_id: str = ""
    started_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"work_item_id": self.work_item_id, "agent_id": self.agent_id, "started_at": self.started_at})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemStartedEvent":
        return cls(
            type=data.get("type", "workitem.started"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            agent_id=data.get("agent_id", ""),
            started_at=data.get("started_at", ""),
        )


@dataclass(frozen=True)
class WorkItemUnderReviewEvent(CodetoreumEvent):
    """Emitted when a work item enters review."""

    work_item_id: str = ""

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"work_item_id": self.work_item_id})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemUnderReviewEvent":
        return cls(
            type=data.get("type", "workitem.under_review"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
        )


@dataclass(frozen=True)
class WorkItemCompletedEvent(CodetoreumEvent):
    """Emitted when a work item is completed."""

    work_item_id: str = ""
    agent_id: str = ""
    completed_at: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"work_item_id": self.work_item_id, "agent_id": self.agent_id, "completed_at": self.completed_at})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemCompletedEvent":
        return cls(
            type=data.get("type", "workitem.completed"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            agent_id=data.get("agent_id", ""),
            completed_at=data.get("completed_at", ""),
        )


@dataclass(frozen=True)
class WorkItemFailedEvent(CodetoreumEvent):
    """Emitted when a work item fails."""

    work_item_id: str = ""
    agent_id: str = ""
    reason: str = ""
    failed_at: str = ""
    new_status: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "agent_id": self.agent_id,
                "reason": self.reason,
                "failed_at": self.failed_at,
                "new_status": self.new_status,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemFailedEvent":
        return cls(
            type=data.get("type", "workitem.failed"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            agent_id=data.get("agent_id", ""),
            reason=data.get("reason", ""),
            failed_at=data.get("failed_at", ""),
            new_status=data.get("new_status", ""),
        )


@dataclass(frozen=True)
class WorkItemBlockedEvent(CodetoreumEvent):
    """Emitted when a work item is blocked."""

    work_item_id: str = ""
    reason: str = ""
    blocking_issue_id: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "reason": self.reason,
                "blocking_issue_id": self.blocking_issue_id,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemBlockedEvent":
        return cls(
            type=data.get("type", "workitem.blocked"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            reason=data.get("reason", ""),
            blocking_issue_id=data.get("blocking_issue_id", ""),
        )


@dataclass(frozen=True)
class WorkItemUnblockedEvent(CodetoreumEvent):
    """Emitted when a work item is unblocked."""

    work_item_id: str = ""
    new_status: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"work_item_id": self.work_item_id, "new_status": self.new_status})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemUnblockedEvent":
        return cls(
            type=data.get("type", "workitem.unblocked"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            new_status=data.get("new_status", ""),
        )


@dataclass(frozen=True)
class WorkItemStageUpdatedEvent(CodetoreumEvent):
    """Emitted when a work item's stage is updated."""

    work_item_id: str = ""
    old_stage: str = ""
    new_stage: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"work_item_id": self.work_item_id, "old_stage": self.old_stage, "new_stage": self.new_stage})
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemStageUpdatedEvent":
        return cls(
            type=data.get("type", "workitem.stage_updated"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            old_stage=data.get("old_stage", ""),
            new_stage=data.get("new_stage", ""),
        )


@dataclass(frozen=True)
class WorkItemLabelsUpdatedEvent(CodetoreumEvent):
    """Emitted when a work item's labels are updated."""

    work_item_id: str = ""
    old_labels: tuple = ()
    new_labels: tuple = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "old_labels", tuple(self.old_labels))
        object.__setattr__(self, "new_labels", tuple(self.new_labels))

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "old_labels": list(self.old_labels),
                "new_labels": list(self.new_labels),
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemLabelsUpdatedEvent":
        return cls(
            type=data.get("type", "workitem.labels_updated"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            old_labels=tuple(data.get("old_labels", [])),
            new_labels=tuple(data.get("new_labels", [])),
        )


@dataclass(frozen=True)
class WorkItemPriorityUpdatedEvent(CodetoreumEvent):
    """Emitted when a work item's priority is updated."""

    work_item_id: str = ""
    old_priority: int = 0
    new_priority: int = 0

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.work_item_id:
            raise ValueError("work_item_id is required")

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update(
            {
                "work_item_id": self.work_item_id,
                "old_priority": self.old_priority,
                "new_priority": self.new_priority,
            }
        )
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkItemPriorityUpdatedEvent":
        return cls(
            type=data.get("type", "workitem.priority_updated"),
            timestamp=data.get("timestamp", now_iso()),
            source=data.get("source", "domain"),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            work_item_id=data.get("work_item_id", ""),
            old_priority=data.get("old_priority", 0),
            new_priority=data.get("new_priority", 0),
        )
