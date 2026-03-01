"""Unit tests for event serialization."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from codetoreum.domain.events import DomainEvent, WorkItemCreated
from codetoreum.infrastructure.event_serialization import (
    EventSerializationError,
    EventSerializer,
    auto_register_event_types,
)


class TestEventSerializer:
    """Test suite for EventSerializer."""

    def setup_method(self):
        """Set up test fixtures."""
        # Clear registry before each test to ensure isolation
        EventSerializer._event_type_registry.clear()
        # Register event types
        auto_register_event_types()

    def test_serialize_domain_event(self):
        """Test serializing a basic domain event."""
        # Arrange
        event_id = uuid4()
        correlation_id = uuid4()
        occurred_at = datetime.now(UTC)

        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
            payload={"key": "value", "count": 42},
            user_id="user-456",
            correlation_id=correlation_id,
            event_id=event_id,
            occurred_at=occurred_at,
        )

        # Act
        json_str = EventSerializer.serialize(event)

        # Assert
        assert json_str is not None
        data = json.loads(json_str)

        assert data["event_id"] == str(event_id)
        assert data["event_type"] == "DomainEvent"
        assert data["aggregate_id"] == "test-123"
        assert data["aggregate_type"] == "TestAggregate"
        assert data["correlation_id"] == str(correlation_id)
        assert data["user_id"] == "user-456"
        assert data["payload"]["key"] == "value"
        assert data["payload"]["count"] == 42
        assert data["schema_version"] == EventSerializer.SCHEMA_VERSION

    def test_deserialize_domain_event(self):
        """Test deserializing a domain event."""
        # Arrange
        event_id = uuid4()
        correlation_id = uuid4()
        occurred_at = datetime.now(UTC)

        original_event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
            payload={"key": "value"},
            correlation_id=correlation_id,
            event_id=event_id,
            occurred_at=occurred_at,
        )

        json_str = EventSerializer.serialize(original_event)

        # Act
        deserialized_event = EventSerializer.deserialize(json_str)

        # Assert
        assert deserialized_event.event_id == original_event.event_id
        assert deserialized_event.event_type == original_event.event_type
        assert deserialized_event.aggregate_id == original_event.aggregate_id
        assert deserialized_event.aggregate_type == original_event.aggregate_type
        assert deserialized_event.correlation_id == original_event.correlation_id
        assert deserialized_event.payload == original_event.payload

    def test_serialize_work_item_created_event(self):
        """Test serializing a specific event type (WorkItemCreated)."""
        # Arrange
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "title": "Test Work Item",
                "description": "Test description",
                "project_id": "proj-456",
                "labels": ["bug", "priority:high"],
                "priority": 1,
            },
        )

        # Act
        json_str = EventSerializer.serialize(event)

        # Assert
        assert json_str is not None
        data = json.loads(json_str)

        assert data["event_type"] == "WorkItemCreated"
        assert data["aggregate_type"] == "WorkItem"
        assert data["payload"]["title"] == "Test Work Item"
        assert data["payload"]["labels"] == ["bug", "priority:high"]

    def test_deserialize_work_item_created_event(self):
        """Test deserializing WorkItemCreated event."""
        # Arrange
        original_event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "title": "Test Work Item",
                "description": "Test description",
                "project_id": "proj-456",
                "labels": ["bug"],
                "priority": 1,
            },
        )

        json_str = EventSerializer.serialize(original_event)

        # Act
        deserialized_event = EventSerializer.deserialize(json_str)

        # Assert
        assert isinstance(deserialized_event, WorkItemCreated)
        assert deserialized_event.event_type == "WorkItemCreated"
        assert deserialized_event.aggregate_type == "WorkItem"
        assert deserialized_event.payload["title"] == "Test Work Item"

    def test_to_dict_conversion(self):
        """Test converting event to dictionary."""
        # Arrange
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        # Act
        event_dict = EventSerializer.to_dict(event)

        # Assert
        assert event_dict["event_id"] == str(event.event_id)
        assert event_dict["event_type"] == "WorkItemCreated"
        assert event_dict["aggregate_id"] == "work-item-123"
        assert event_dict["aggregate_type"] == "WorkItem"
        assert event_dict["data"]["title"] == "Test"
        assert "timestamp" in event_dict

    def test_from_dict_reconstruction(self):
        """Test reconstructing event from dictionary."""
        # Arrange
        event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={"title": "Test"},
        )

        event_dict = EventSerializer.to_dict(event)

        # Act
        reconstructed_event = EventSerializer.from_dict(event_dict)

        # Assert
        assert isinstance(reconstructed_event, WorkItemCreated)
        assert reconstructed_event.event_id == event.event_id
        assert reconstructed_event.aggregate_id == event.aggregate_id
        assert reconstructed_event.payload["title"] == "Test"

    def test_serialize_with_complex_payload(self):
        """Test serializing event with complex nested payload."""
        # Arrange
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
            payload={
                "nested": {
                    "level1": {
                        "level2": {"value": "deep"},
                        "list": [1, 2, 3],
                    }
                },
                "timestamp": datetime.now(UTC),
            },
        )

        # Act
        json_str = EventSerializer.serialize(event)

        # Assert
        assert json_str is not None
        data = json.loads(json_str)
        assert data["payload"]["nested"]["level1"]["level2"]["value"] == "deep"
        assert data["payload"]["nested"]["level1"]["list"] == [1, 2, 3]

    def test_serialize_invalid_event_raises_error(self):
        """Test that serializing invalid data raises error."""
        # Arrange - create event with non-serializable object in payload
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
            payload={"bad_object": object()},  # Non-serializable object
        )

        # Act & Assert
        with pytest.raises(EventSerializationError):
            EventSerializer.serialize(event)

    def test_deserialize_invalid_json_raises_error(self):
        """Test that deserializing invalid JSON raises error."""
        # Arrange
        invalid_json = "not valid json"

        # Act & Assert
        with pytest.raises(EventSerializationError):
            EventSerializer.deserialize(invalid_json)

    def test_deserialize_missing_required_field_raises_error(self):
        """Test that deserializing with missing required field raises error."""
        # Arrange
        incomplete_json = json.dumps(
            {
                "event_id": str(uuid4()),
                "event_type": "DomainEvent",
                # Missing aggregate_id and aggregate_type
            }
        )

        # Act & Assert
        with pytest.raises(EventSerializationError):
            EventSerializer.deserialize(incomplete_json)

    def test_register_event_type(self):
        """Test registering event types."""

        # Arrange
        class CustomEvent(DomainEvent):
            pass

        # Act
        EventSerializer.register_event_type(CustomEvent)

        # Assert
        assert "CustomEvent" in EventSerializer._event_type_registry
        assert EventSerializer._event_type_registry["CustomEvent"] == CustomEvent

    def test_register_duplicate_event_type_with_same_class_ok(self):
        """Test that registering same event type twice is OK."""

        # Arrange
        class CustomEvent(DomainEvent):
            pass

        # Act - register twice
        EventSerializer.register_event_type(CustomEvent)
        EventSerializer.register_event_type(CustomEvent)  # Should not raise

        # Assert
        assert "CustomEvent" in EventSerializer._event_type_registry

    def test_register_duplicate_event_type_with_different_class_raises_error(self):
        """Test that registering same name with different class raises error."""

        # Arrange
        class CustomEvent1(DomainEvent):
            pass

        class CustomEvent2(DomainEvent):
            pass

        # Force same name
        CustomEvent2.__name__ = "CustomEvent1"

        EventSerializer.register_event_type(CustomEvent1)

        # Act & Assert
        with pytest.raises(ValueError, match="already registered"):
            EventSerializer.register_event_type(CustomEvent2)

    def test_deserialize_unknown_event_type_uses_base_class(self):
        """Test that unknown event types deserialize to base DomainEvent."""
        # Arrange
        json_str = json.dumps(
            {
                "schema_version": 1,
                "event_id": str(uuid4()),
                "event_type": "UnknownEventType",
                "event_version": 1,
                "aggregate_id": "test-123",
                "aggregate_type": "TestAggregate",
                "occurred_at": datetime.now(UTC).isoformat(),
                "correlation_id": None,
                "causation_id": None,
                "user_id": None,
                "payload": {},
                "metadata": {},
            }
        )

        # Act
        event = EventSerializer.deserialize(json_str)

        # Assert
        assert isinstance(event, DomainEvent)
        assert event.event_type == "DomainEvent"  # Falls back to base class

    def test_schema_version_compatibility(self):
        """Test schema version handling."""
        # Arrange
        event = DomainEvent(
            aggregate_id="test-123",
            aggregate_type="TestAggregate",
        )

        json_str = EventSerializer.serialize(event)
        data = json.loads(json_str)

        # Assert schema version is present
        assert data["schema_version"] == EventSerializer.SCHEMA_VERSION

    def test_round_trip_serialization(self):
        """Test that serialize → deserialize → serialize produces same result."""
        # Arrange
        original_event = WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "title": "Test Work Item",
                "description": "Test description",
                "project_id": "proj-456",
                "labels": ["bug", "priority:high"],
                "priority": 1,
                "external_id": "JIRA-1234",
                "external_url": "https://jira.example.com/JIRA-1234",
            },
        )

        # Act
        json_str1 = EventSerializer.serialize(original_event)
        deserialized = EventSerializer.deserialize(json_str1)
        json_str2 = EventSerializer.serialize(deserialized)

        # Assert
        data1 = json.loads(json_str1)
        data2 = json.loads(json_str2)

        # Compare all fields (except potentially different UUIDs for metadata)
        assert data1["event_id"] == data2["event_id"]
        assert data1["event_type"] == data2["event_type"]
        assert data1["aggregate_id"] == data2["aggregate_id"]
        assert data1["payload"] == data2["payload"]
