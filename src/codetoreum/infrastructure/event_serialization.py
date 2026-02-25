"""Event serialization with schema versioning support."""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from codetoreum.domain.events import DomainEvent


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
    _event_type_registry: dict[str, type[DomainEvent]] = {}

    @classmethod
    def register_event_type(cls, event_class: type[DomainEvent]) -> None:
        """
        Register an event type for deserialization.

        Args:
            event_class: Event class to register

        Raises:
            ValueError: If event type already registered with different class
        """
        event_type_name = event_class.__name__

        if event_type_name in cls._event_type_registry:
            existing_class = cls._event_type_registry[event_type_name]
            if existing_class != event_class:
                message = f"Event type '{event_type_name}' already registered " f"with different class: {existing_class}"
                raise ValueError(message)
        else:
            cls._event_type_registry[event_type_name] = event_class

    @classmethod
    def serialize(cls, event: DomainEvent) -> str:
        """
        Serialize event to JSON string.

        Args:
            event: Domain event to serialize

        Returns:
            JSON string representation

        Raises:
            EventSerializationError: If serialization fails
        """
        try:
            data = {
                "schema_version": cls.SCHEMA_VERSION,
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "event_version": event.event_version,
                "aggregate_id": event.aggregate_id,
                "aggregate_type": event.aggregate_type,
                "occurred_at": event.occurred_at.isoformat(),
                "correlation_id": (
                    str(event.correlation_id) if event.correlation_id else None
                ),
                "causation_id": str(event.causation_id) if event.causation_id else None,
                "user_id": event.user_id,
                "payload": event.payload,
                "metadata": event.metadata,
            }

            return json.dumps(data, cls=_EventJSONEncoder, ensure_ascii=False)

        except Exception as e:
            message = f"Failed to serialize event {event.event_type}: {e}"
            raise EventSerializationError(message)

    @classmethod
    def deserialize(cls, json_str: str) -> DomainEvent:
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
                message = f"Event schema version {schema_version} is newer than " f"supported version {cls.SCHEMA_VERSION}. " f"Please upgrade the application."
                raise EventSerializationError(message)

            # Get event type class from registry
            event_type = data["event_type"]
            event_class = cls._event_type_registry.get(event_type)

            if event_class is None:
                # Fallback to generic DomainEvent for unknown types
                event_class = DomainEvent

            # Reconstruct event
            # For specific event types (e.g., WorkItemCreated), they don't accept aggregate_type
            # as it's hardcoded in their __init__. Only pass it for base DomainEvent.
            kwargs = {
                "payload": data.get("payload", {}),
                "user_id": data.get("user_id"),
                "correlation_id": (
                    UUID(data["correlation_id"]) if data.get("correlation_id") else None
                ),
                "causation_id": (
                    UUID(data["causation_id"]) if data.get("causation_id") else None
                ),
                "event_id": UUID(data["event_id"]) if data.get("event_id") else None,
                "occurred_at": (
                    datetime.fromisoformat(data["occurred_at"])
                    if data.get("occurred_at")
                    else None
                ),
            }

            # Only pass aggregate_type for base DomainEvent
            if event_class == DomainEvent:
                kwargs["aggregate_type"] = data["aggregate_type"]

            return event_class(
                aggregate_id=data["aggregate_id"],
                **kwargs
            )

        except EventSerializationError:
            raise
        except Exception as e:
            message = f"Failed to deserialize event: {e}"
            raise EventSerializationError(message)

    @classmethod
    def to_dict(cls, event: DomainEvent) -> dict[str, Any]:
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
            return {
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "event_version": event.event_version,
                "aggregate_id": event.aggregate_id,
                "aggregate_type": event.aggregate_type,
                "timestamp": event.occurred_at.isoformat(),
                "correlation_id": (
                    str(event.correlation_id) if event.correlation_id else None
                ),
                "causation_id": str(event.causation_id) if event.causation_id else None,
                "user_id": event.user_id,
                "data": event.payload,
                "metadata": event.metadata,
            }

        except Exception as e:
            message = f"Failed to convert event to dict: {e}"
            raise EventSerializationError(message)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DomainEvent:
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
            # Get event type class from registry
            event_type = data["event_type"]
            event_class = cls._event_type_registry.get(event_type, DomainEvent)

            # Build kwargs (specific event types don't accept aggregate_type)
            kwargs = {
                "payload": data.get("data", {}),
                "user_id": data.get("user_id"),
                "correlation_id": (
                    UUID(data["correlation_id"]) if data.get("correlation_id") else None
                ),
                "causation_id": (
                    UUID(data["causation_id"]) if data.get("causation_id") else None
                ),
                "event_id": UUID(data["event_id"]) if data.get("event_id") else None,
                "occurred_at": (
                    datetime.fromisoformat(data["timestamp"])
                    if data.get("timestamp")
                    else None
                ),
            }

            # Only pass aggregate_type for base DomainEvent
            if event_class == DomainEvent:
                kwargs["aggregate_type"] = data["aggregate_type"]

            return event_class(
                aggregate_id=data["aggregate_id"],
                **kwargs
            )

        except Exception as e:
            message = f"Failed to reconstruct event from dict: {e}"
            raise EventSerializationError(message)


class _EventJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for event serialization."""

    def default(self, obj):
        """Handle custom types in event data."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, UUID):
            return str(obj)
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


def auto_register_event_types() -> None:
    """
    Auto-register all known event types from domain.events module.

    This should be called at application startup to populate the
    event type registry for deserialization.
    """

    # Import all event classes
    from codetoreum.domain.events import (
        AgentAssigned,
        AgentCapabilityAdded,
        AgentCapabilityRemoved,
        AgentCapabilityUpdated,
        AgentConstraintsUpdated,
        AgentCreated,
        AgentMaxRetriesUpdated,
        AgentMcpServerAdded,
        AgentMcpServerRemoved,
        AgentModelUpdated,
        AgentTimeoutUpdated,
        ExecutionCompleted,
        ExecutionFailed,
        ExecutionInitialized,
        ExecutionStarted,
        ExecutionTimeout,
        ProjectContextCreated,
        ProjectDockerConfigUpdated,
        ProjectTestConfigUpdated,
        ProjectWorkflowMappingAdded,
        ReviewCycleApproved,
        ReviewCycleCreated,
        ReviewCycleEscalated,
        ReviewCycleRejected,
        ReviewFeedbackSubmitted,
        ReviewIterationStarted,
        WorkflowAttached,
        WorkflowCancelled,
        WorkflowCompleted,
        WorkflowCreated,
        WorkflowFailed,
        WorkflowPaused,
        WorkflowResumed,
        WorkflowStageAdvanced,
        WorkflowStageStatusUpdated,
        WorkflowStarted,
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

    # Register all event types
    event_classes = [
        # Work Item Events
        WorkItemCreated,
        AgentAssigned,
        WorkItemStarted,
        WorkItemUnderReview,
        WorkItemCompleted,
        WorkItemFailed,
        WorkItemBlocked,
        WorkItemUnblocked,
        WorkflowAttached,
        WorkItemStageUpdated,
        WorkItemLabelsUpdated,
        WorkItemPriorityUpdated,
        # Agent Events
        AgentCreated,
        AgentCapabilityAdded,
        AgentCapabilityRemoved,
        AgentCapabilityUpdated,
        AgentModelUpdated,
        AgentTimeoutUpdated,
        AgentMaxRetriesUpdated,
        AgentConstraintsUpdated,
        AgentMcpServerAdded,
        AgentMcpServerRemoved,
        # Agent Execution Events
        ExecutionInitialized,
        ExecutionStarted,
        ExecutionCompleted,
        ExecutionFailed,
        ExecutionTimeout,
        # Workflow Events
        WorkflowCreated,
        WorkflowStarted,
        WorkflowStageAdvanced,
        WorkflowStageStatusUpdated,
        WorkflowCompleted,
        WorkflowFailed,
        WorkflowPaused,
        WorkflowResumed,
        WorkflowCancelled,
        # Review Cycle Events
        ReviewCycleCreated,
        ReviewIterationStarted,
        ReviewFeedbackSubmitted,
        ReviewCycleApproved,
        ReviewCycleRejected,
        ReviewCycleEscalated,
        # Project Context Events
        ProjectContextCreated,
        ProjectTestConfigUpdated,
        ProjectDockerConfigUpdated,
        ProjectWorkflowMappingAdded,
    ]

    for event_class in event_classes:
        EventSerializer.register_event_type(event_class)
