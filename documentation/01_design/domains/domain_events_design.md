# Domain Events Design

## Overview

Domain events represent things that happened in the domain. They are immutable facts about the past and form the foundation of event sourcing.

## Base Event Structure

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID, uuid4

@dataclass
class DomainEvent:
    """Base class for all domain events."""

    # Event identity
    event_id: UUID
    event_type: str
    event_version: int

    # Aggregate tracking
    aggregate_id: str
    aggregate_type: str

    # Timing
    occurred_at: datetime

    # Causation tracking
    correlation_id: Optional[UUID]  # Groups related events
    causation_id: Optional[UUID]    # Event that caused this event
    user_id: Optional[str]

    # Event data
    payload: Dict[str, Any]
    metadata: Dict[str, Any]

    @classmethod
    def create(cls,
               aggregate_id: str,
               aggregate_type: str,
               payload: Dict[str, Any],
               user_id: Optional[str] = None,
               correlation_id: Optional[UUID] = None,
               causation_id: Optional[UUID] = None) -> 'DomainEvent':
        """Factory method to create domain event."""
        return cls(
            event_id=uuid4(),
            event_type=cls.__name__,
            event_version=1,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            occurred_at=datetime.utcnow(),
            correlation_id=correlation_id or uuid4(),
            causation_id=causation_id,
            user_id=user_id,
            payload=payload,
            metadata={}
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
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
            "metadata": self.metadata
        }
```

## Work Item Events

```python
@dataclass
class WorkItemCreated(DomainEvent):
    """Emitted when a work item is created."""
    pass

@dataclass
class AgentAssigned(DomainEvent):
    """Emitted when an agent is assigned to work item."""
    pass

@dataclass
class WorkItemStarted(DomainEvent):
    """Emitted when work begins on item."""
    pass

@dataclass
class WorkItemUnderReview(DomainEvent):
    """Emitted when work item enters review."""
    pass

@dataclass
class WorkItemCompleted(DomainEvent):
    """Emitted when work item completes."""
    pass

@dataclass
class WorkItemFailed(DomainEvent):
    """Emitted when work item fails."""
    pass

@dataclass
class WorkItemBlocked(DomainEvent):
    """Emitted when work item is blocked."""
    pass

@dataclass
class WorkItemUnblocked(DomainEvent):
    """Emitted when work item is unblocked."""
    pass

@dataclass
class WorkflowAttached(DomainEvent):
    """Emitted when workflow attached to work item."""
    pass

@dataclass
class WorkItemStageUpdated(DomainEvent):
    """Emitted when work item moves to new stage."""
    pass

@dataclass
class WorkItemLabelsUpdated(DomainEvent):
    """Emitted when work item labels change."""
    pass

@dataclass
class WorkItemPriorityUpdated(DomainEvent):
    """Emitted when work item priority changes."""
    pass
```

## Workflow Events

```python
@dataclass
class WorkflowCreated(DomainEvent):
    """Emitted when workflow is created."""
    pass

@dataclass
class WorkflowStarted(DomainEvent):
    """Emitted when workflow execution begins."""
    pass

@dataclass
class WorkflowStageAdvanced(DomainEvent):
    """Emitted when workflow advances to next stage."""
    pass

@dataclass
class WorkflowStageStatusUpdated(DomainEvent):
    """Emitted when stage status changes."""
    pass

@dataclass
class WorkflowCompleted(DomainEvent):
    """Emitted when workflow completes successfully."""
    pass

@dataclass
class WorkflowFailed(DomainEvent):
    """Emitted when workflow fails."""
    pass

@dataclass
class WorkflowPaused(DomainEvent):
    """Emitted when workflow is paused."""
    pass

@dataclass
class WorkflowResumed(DomainEvent):
    """Emitted when workflow is resumed."""
    pass

@dataclass
class WorkflowCancelled(DomainEvent):
    """Emitted when workflow is cancelled."""
    pass
```

## Agent Events

```python
@dataclass
class AgentCreated(DomainEvent):
    """Emitted when agent is created."""
    pass

@dataclass
class AgentCapabilityAdded(DomainEvent):
    """Emitted when capability added to agent."""
    pass

@dataclass
class AgentCapabilityRemoved(DomainEvent):
    """Emitted when capability removed from agent."""
    pass

@dataclass
class AgentCapabilityUpdated(DomainEvent):
    """Emitted when capability proficiency updated."""
    pass

@dataclass
class AgentModelUpdated(DomainEvent):
    """Emitted when agent LLM model changed."""
    pass

@dataclass
class AgentTimeoutUpdated(DomainEvent):
    """Emitted when agent timeout changed."""
    pass

@dataclass
class AgentConstraintsUpdated(DomainEvent):
    """Emitted when agent constraints changed."""
    pass

@dataclass
class AgentMcpServerAdded(DomainEvent):
    """Emitted when MCP server added to agent."""
    pass

@dataclass
class AgentMcpServerRemoved(DomainEvent):
    """Emitted when MCP server removed from agent."""
    pass
```

## Agent Execution Events

```python
@dataclass
class ExecutionInitialized(DomainEvent):
    """Emitted when execution is initialized."""
    pass

@dataclass
class ExecutionStarted(DomainEvent):
    """Emitted when execution starts."""
    pass

@dataclass
class ExecutionCompleted(DomainEvent):
    """Emitted when execution completes successfully."""
    pass

@dataclass
class ExecutionFailed(DomainEvent):
    """Emitted when execution fails."""
    pass

@dataclass
class ExecutionTimeout(DomainEvent):
    """Emitted when execution times out."""
    pass
```

## Review Cycle Events

```python
@dataclass
class ReviewCycleCreated(DomainEvent):
    """Emitted when review cycle is created."""
    pass

@dataclass
class ReviewIterationStarted(DomainEvent):
    """Emitted when new review iteration starts."""
    pass

@dataclass
class ReviewFeedbackSubmitted(DomainEvent):
    """Emitted when reviewer provides feedback."""
    pass

@dataclass
class ReviewCycleApproved(DomainEvent):
    """Emitted when review is approved."""
    pass

@dataclass
class ReviewCycleEscalated(DomainEvent):
    """Emitted when review is escalated to human."""
    pass
```

## Project Context Events

```python
@dataclass
class ProjectContextCreated(DomainEvent):
    """Emitted when project context is created."""
    pass

@dataclass
class ProjectTestConfigUpdated(DomainEvent):
    """Emitted when test configuration changes."""
    pass

@dataclass
class ProjectDockerConfigUpdated(DomainEvent):
    """Emitted when Docker configuration changes."""
    pass

@dataclass
class ProjectWorkflowMappingAdded(DomainEvent):
    """Emitted when custom workflow mapping added."""
    pass
```

## Event Naming Conventions

### 1. Past Tense
Events describe what happened: `WorkItemCreated`, not `CreateWorkItem`

### 2. Domain Language
Use ubiquitous language: `AgentAssigned`, not `AgentSet`

### 3. Specific Names
Be specific: `WorkItemPriorityUpdated` not just `WorkItemUpdated`

### 4. Event Type Hierarchy
```
DomainEvent (base)
├── WorkItemEvent (category)
│   ├── WorkItemCreated
│   ├── WorkItemCompleted
│   └── ...
├── WorkflowEvent
│   ├── WorkflowStarted
│   └── ...
└── ...
```

## Event Usage Patterns

### Publishing Events

```python
# In aggregate method
class WorkItem:
    def complete(self) -> None:
        # Update state
        self.status = WorkItemStatus.COMPLETED
        self.completed_at = datetime.utcnow()

        # Emit event
        event = WorkItemCompleted.create(
            aggregate_id=self.id,
            aggregate_type="WorkItem",
            payload={
                "completed_at": self.completed_at.isoformat(),
                "agent_id": self.assigned_agent_id
            }
        )
        self._add_event(event)

    def get_pending_events(self) -> List[DomainEvent]:
        """Get events to publish."""
        return self._events.copy()
```

### Event Handlers

```python
class WorkItemProjection:
    """Project events to read model."""

    async def handle(self, event: DomainEvent) -> None:
        """Handle domain event."""
        if isinstance(event, WorkItemCreated):
            await self._handle_created(event)
        elif isinstance(event, WorkItemCompleted):
            await self._handle_completed(event)

    async def _handle_created(self, event: WorkItemCreated) -> None:
        """Handle WorkItemCreated event."""
        read_model = WorkItemReadModel(
            id=event.aggregate_id,
            title=event.payload["title"],
            description=event.payload["description"],
            status="new",
            created_at=event.occurred_at,
            updated_at=event.occurred_at
        )
        await self.read_store.save(read_model)
```

### Event Sourcing Reconstruction

```python
@classmethod
def from_events(cls, events: List[DomainEvent]) -> 'WorkItem':
    """Reconstruct aggregate from events."""
    if not events:
        raise DomainError("Cannot reconstruct from empty stream")

    # First event must be creation event
    first_event = events[0]
    if not isinstance(first_event, WorkItemCreated):
        raise DomainError("First event must be WorkItemCreated")

    # Create initial state
    work_item = cls._from_creation_event(first_event)

    # Apply subsequent events
    for event in events[1:]:
        work_item._apply_event(event)

    return work_item
```

## Event Store Interface

```python
from abc import ABC, abstractmethod

class IEventStore(ABC):
    """Interface for event persistence."""

    @abstractmethod
    async def append(self, event: DomainEvent) -> None:
        """Append event to store."""
        pass

    @abstractmethod
    async def get_events(self,
                        aggregate_id: str,
                        from_version: int = 0) -> List[DomainEvent]:
        """Get events for aggregate."""
        pass

    @abstractmethod
    async def get_all_events(self,
                            from_timestamp: Optional[datetime] = None) -> List[DomainEvent]:
        """Get all events after timestamp."""
        pass

    @abstractmethod
    async def get_event_stream(self) -> AsyncIterator[DomainEvent]:
        """Get real-time event stream."""
        pass
```

## Event Metadata

Events can carry additional metadata:

```python
event = WorkItemCompleted.create(
    aggregate_id=work_item.id,
    aggregate_type="WorkItem",
    payload={"completed_at": "..."},
    user_id="user-123"
)

# Add metadata
event.metadata["client_ip"] = "192.168.1.1"
event.metadata["user_agent"] = "Mozilla/5.0..."
event.metadata["environment"] = "production"
```

## Correlation and Causation

Track event relationships:

```python
# Original command creates correlation ID
correlation_id = uuid4()

# First event
work_item_created = WorkItemCreated.create(
    aggregate_id=work_item.id,
    aggregate_type="WorkItem",
    payload={...},
    correlation_id=correlation_id
)

# Subsequent event caused by first
workflow_created = WorkflowCreated.create(
    aggregate_id=workflow.id,
    aggregate_type="Workflow",
    payload={...},
    correlation_id=correlation_id,
    causation_id=work_item_created.event_id
)
```

## Testing Events

```python
def test_work_item_created_event():
    event = WorkItemCreated.create(
        aggregate_id="work-1",
        aggregate_type="WorkItem",
        payload={
            "title": "Test Item",
            "description": "Test",
            "project_id": "proj-1"
        },
        user_id="user-1"
    )

    assert event.event_type == "WorkItemCreated"
    assert event.aggregate_id == "work-1"
    assert event.payload["title"] == "Test Item"
    assert event.user_id == "user-1"

def test_event_serialization():
    event = WorkItemCreated.create(
        aggregate_id="work-1",
        aggregate_type="WorkItem",
        payload={"title": "Test"}
    )

    event_dict = event.to_dict()

    assert event_dict["event_type"] == "WorkItemCreated"
    assert event_dict["aggregate_id"] == "work-1"
    assert "occurred_at" in event_dict
```

## Event Schema Evolution

Handle schema changes over time:

```python
class EventMigrator:
    """Migrate events to current schema version."""

    def migrate(self, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate event to latest version."""
        version = event_dict.get("event_version", 1)

        if version < 2:
            event_dict = self._migrate_v1_to_v2(event_dict)

        if version < 3:
            event_dict = self._migrate_v2_to_v3(event_dict)

        return event_dict

    def _migrate_v1_to_v2(self, event: Dict) -> Dict:
        """Migrate from version 1 to 2."""
        # Add new field with default value
        if "new_field" not in event["payload"]:
            event["payload"]["new_field"] = "default_value"

        event["event_version"] = 2
        return event
```

## References

- **Event Sourcing**: `../raw_input/02-event-sourcing-cqrs.md`
- **Work Item**: `work_item_design.md`
- **Workflow**: `workflow_design.md`
- **All Domain Models**: See individual design documents
