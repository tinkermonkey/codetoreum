"""Event serialization with schema versioning support."""

import json
import types
from datetime import datetime
from typing import Any
from uuid import UUID

from codetoreum.domain.events.adapter_events import CodetoreumEvent


class EventSerializationError(Exception):
    """Raised when event serialization/deserialization fails."""


class EventSerializer:
    """
    Serializes domain events to/from JSON with schema versioning.

    Supports:
    - JSON serialization with proper type handling
    - Schema versioning for backward/forward compatibility
    - Compression for large events (future)
    - Custom type encoders/decoders
    """

    # Schema version for this serializer implementation
    SCHEMA_VERSION = 1

    # Event type registry for deserialization
    _codetoeum_event_registry: dict[str, type[CodetoreumEvent]] = {}

    @classmethod
    def register_event_type(cls, event_class: type[CodetoreumEvent]) -> None:
        """
        Register an event type for deserialization.

        Args:
            event_class: Event class to register (CodetoreumEvent subclass)

        Raises:
            ValueError: If event type already registered with different class
        """
        event_type_name = event_class.__name__

        # Always check for duplicate registration regardless of subclass status
        if event_type_name in cls._codetoeum_event_registry:
            existing_class = cls._codetoeum_event_registry[event_type_name]
            if existing_class != event_class:
                message = f"Event type '{event_type_name}' already registered with different class: {existing_class}"
                raise ValueError(message)
            return  # Same class, idempotent

        if issubclass(event_class, CodetoreumEvent):
            cls._codetoeum_event_registry[event_type_name] = event_class
            return

        raise ValueError(
            f"Cannot register {event_type_name}: not a CodetoreumEvent subclass. "
            "Only CodetoreumEvent subclasses can be registered."
        )

    @classmethod
    def serialize(cls, event: CodetoreumEvent) -> str:
        """
        Serialize event to JSON string.

        Serializes CodetoreumEvent instances using their to_dict() method.

        Args:
            event: Domain event to serialize (CodetoreumEvent subclass)

        Returns:
            JSON string representation

        Raises:
            EventSerializationError: If serialization fails
        """
        try:
            if isinstance(event, CodetoreumEvent):
                data = {
                    "schema_version": cls.SCHEMA_VERSION,
                    "event_class": "CodetoreumEvent",
                    "concrete_class": type(event).__name__,
                    **event.to_dict(),
                }
                return json.dumps(data, cls=_EventJSONEncoder, ensure_ascii=False)

            raise EventSerializationError(
                f"serialize() requires CodetoreumEvent, got {type(event).__name__}. "
                "Only CodetoreumEvent instances can be serialized."
            )

        except EventSerializationError:
            raise
        except Exception as e:
            message = f"Failed to serialize event {getattr(event, 'event_type', type(event).__name__)}: {e}"
            raise EventSerializationError(message) from e

    @classmethod
    def deserialize(cls, json_str: str) -> CodetoreumEvent:
        """
        Deserialize event from JSON string.

        Args:
            json_str: JSON string representation

        Returns:
            Reconstructed domain event

        Raises:
            EventSerializationError: If deserialization fails
        """
        try:
            data = json.loads(json_str, cls=_EventJSONDecoder)

            # Check schema version for compatibility
            schema_version = data.get("schema_version", 1)
            if schema_version > cls.SCHEMA_VERSION:
                message = (
                    f"Event schema version {schema_version} is newer than "
                    f"supported version {cls.SCHEMA_VERSION}. "
                    f"Please upgrade the application."
                )
                raise EventSerializationError(message)

            # Look up by concrete_class first, then event_class, then type
            event_class_name = (
                data.get("concrete_class") or data.get("event_class") or data.get("type") or data.get("event_type")
            )
            event_class = cls._codetoeum_event_registry.get(event_class_name)
            if event_class is None:
                message = f"Unknown event class: {event_class_name!r}. Register it with EventSerializer.register_event_type()."
                raise EventSerializationError(message)

            return event_class.from_dict(data)
        except EventSerializationError:
            raise
        except Exception as e:
            message = f"Failed to deserialize event: {e}"
            raise EventSerializationError(message) from e

    @classmethod
    def to_dict(cls, event: CodetoreumEvent) -> dict[str, Any]:
        """
        Convert event to dictionary (for Elasticsearch indexing).

        Args:
            event: Domain event to convert

        Returns:
            Dictionary representation

        Raises:
            EventSerializationError: If conversion fails
        """
        try:
            d = event.to_dict()
            return {
                "event_id": d.get("event_id", ""),
                "event_type": event.event_type,
                "event_class": event.__class__.__name__,
                "type": d.get("type", "unknown.event"),
                "timestamp": d.get("timestamp", ""),
                "source": d.get("source", ""),
                "correlation_id": d.get("correlation_id"),
                "causation_id": d.get("causation_id"),
                "data": {
                    k: v
                    for k, v in d.items()
                    if k not in {"event_id", "type", "timestamp", "source", "correlation_id", "causation_id"}
                },
            }

        except Exception as e:
            message = f"Failed to convert event to dict: {e}"
            raise EventSerializationError(message) from e

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodetoreumEvent:
        """
        Reconstruct event from dictionary (from Elasticsearch).

        Args:
            data: Dictionary representation

        Returns:
            Reconstructed domain event

        Raises:
            EventSerializationError: If reconstruction fails
        """
        try:
            event_class_name = data.get("event_class") or data.get("event_type", "")
            event_class = cls._codetoeum_event_registry.get(event_class_name)
            if event_class is None:
                message = f"Unknown event class: {event_class_name!r}. Register it with EventSerializer.register_event_type()."
                raise EventSerializationError(message)
            payload = data.get("data", {})
            reconstructed = {
                **payload,
                "event_id": data.get("event_id", ""),
                "correlation_id": data.get("correlation_id"),
                "causation_id": data.get("causation_id"),
                "type": data.get("type", "unknown.event"),
                "source": data.get("source", "unknown"),
                "timestamp": data.get("timestamp", ""),
            }
            return event_class.from_dict(reconstructed)

        except EventSerializationError:
            raise
        except Exception as e:
            message = f"Failed to reconstruct event from dict: {e}"
            raise EventSerializationError(message) from e


class _EventJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for event serialization."""

    def default(self, obj):
        """Handle custom types in event data."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, UUID):
            return str(obj)
        # Handle immutable mappings (MappingProxyType)
        if isinstance(obj, types.MappingProxyType):
            return dict(obj)
        if hasattr(obj, "__dict__"):
            # Handle custom objects
            return obj.__dict__
        return super().default(obj)


class _EventJSONDecoder(json.JSONDecoder):
    """Custom JSON decoder for event deserialization."""

    def __init__(self, *args, **kwargs):
        """Initialize decoder with object hook."""
        super().__init__(object_hook=self._object_hook, *args, **kwargs)

    def _object_hook(self, obj: dict[str, Any]) -> dict[str, Any]:
        """Hook to process objects during decoding."""
        # Future: Handle custom type reconstruction
        return obj


def infer_aggregate_id_and_type(event: CodetoreumEvent) -> tuple[Any, str]:
    """
    Infer aggregate_id and aggregate_type from an event.

    Priority order for identifying the aggregate root:
    - If has workflow_id -> (workflow_id, "Workflow")
    - If has execution_id -> (execution_id, "AgentExecution")
    - If has review_cycle_id -> (review_cycle_id, "ReviewCycle")
    - If has work_item_id -> (work_item_id, "WorkItem")
    - If has repair_cycle_id -> (repair_cycle_id, "RepairCycle")
    - Otherwise -> (event_id, class_name without "Event" suffix)

    Args:
        event: Domain event

    Returns:
        Tuple of (aggregate_id, aggregate_type)
    """
    workflow_id = getattr(event, "workflow_id", None)
    if workflow_id is not None and workflow_id:
        return workflow_id, "Workflow"
    execution_id = getattr(event, "execution_id", None)
    if execution_id is not None and execution_id:
        return execution_id, "AgentExecution"
    review_cycle_id = getattr(event, "review_cycle_id", None)
    if review_cycle_id is not None and review_cycle_id:
        return review_cycle_id, "ReviewCycle"
    work_item_id = getattr(event, "work_item_id", None)
    if work_item_id is not None and work_item_id:
        return work_item_id, "WorkItem"
    repair_cycle_id = getattr(event, "repair_cycle_id", None)
    if repair_cycle_id is not None and repair_cycle_id:
        return repair_cycle_id, "RepairCycle"

    return event.event_id, type(event).__name__.replace("Event", "")


def auto_register_event_types() -> None:
    """
    Auto-register all known event types from domain.events module.

    This should be called at application startup to populate the
    event type registry for deserialization.
    """

    from codetoreum.domain.events import (
        AgentAssignedEvent,
        AgentCapabilityAddedEvent,
        AgentCapabilityRemovedEvent,
        AgentCapabilityUpdatedEvent,
        AgentConstraintsUpdatedEvent,
        AgentCreatedEvent,
        AgentMaxRetriesUpdatedEvent,
        AgentMcpServerAddedEvent,
        AgentMcpServerRemovedEvent,
        AgentModelUpdatedEvent,
        AgentTimeoutUpdatedEvent,
        ExecutionCancelledEvent,
        ExecutionCompletedEvent,
        ExecutionFailedEvent,
        ExecutionInitializedEvent,
        ExecutionPausedEvent,
        ExecutionResumedEvent,
        ExecutionRetryScheduledEvent,
        ExecutionStartedEvent,
        ExecutionTimedOutEvent,
        ProjectContextCreatedEvent,
        ProjectDockerConfigUpdatedEvent,
        ProjectTestConfigUpdatedEvent,
        ProjectWorkflowMappingAddedEvent,
        ReviewCycleApprovedEvent,
        ReviewCycleEscalatedToHumanEvent,
        ReviewCycleStartedEvent,
        WorkflowCancelledEvent,
        WorkflowCompletedEvent,
        WorkflowCreatedEvent,
        WorkflowFailedEvent,
        WorkflowPausedEvent,
        WorkflowResumedEvent,
        WorkflowStageAdvancedEvent,
        WorkflowStageStatusUpdatedEvent,
        WorkflowStartedEvent,
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

    event_classes = [
        AgentAssignedEvent,
        AgentCapabilityAddedEvent,
        AgentCapabilityRemovedEvent,
        AgentCapabilityUpdatedEvent,
        AgentConstraintsUpdatedEvent,
        AgentCreatedEvent,
        AgentMaxRetriesUpdatedEvent,
        AgentMcpServerAddedEvent,
        AgentMcpServerRemovedEvent,
        AgentModelUpdatedEvent,
        AgentTimeoutUpdatedEvent,
        ExecutionCancelledEvent,
        ExecutionCompletedEvent,
        ExecutionFailedEvent,
        ExecutionInitializedEvent,
        ExecutionPausedEvent,
        ExecutionResumedEvent,
        ExecutionRetryScheduledEvent,
        ExecutionStartedEvent,
        ExecutionTimedOutEvent,
        ProjectContextCreatedEvent,
        ProjectDockerConfigUpdatedEvent,
        ProjectTestConfigUpdatedEvent,
        ProjectWorkflowMappingAddedEvent,
        ReviewCycleApprovedEvent,
        ReviewCycleStartedEvent,
        ReviewCycleEscalatedToHumanEvent,
        WorkflowCancelledEvent,
        WorkflowCompletedEvent,
        WorkflowCreatedEvent,
        WorkflowFailedEvent,
        WorkflowPausedEvent,
        WorkflowResumedEvent,
        WorkflowStageAdvancedEvent,
        WorkflowStageStatusUpdatedEvent,
        WorkflowStartedEvent,
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
    ]

    for event_class in event_classes:
        EventSerializer.register_event_type(event_class)
