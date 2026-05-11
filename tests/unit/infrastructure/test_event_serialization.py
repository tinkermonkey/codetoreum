"""Unit tests for EventSerializer using modern CodetoreumEvent frozen dataclasses."""

import json
from datetime import UTC, datetime

import pytest

from codetoreum.domain.events import WorkItemCreatedEvent
from codetoreum.domain.events.adapter_events import now_iso
from codetoreum.domain.events.execution_events import ExecutionInitializedEvent
from codetoreum.infrastructure.event_serialization import (
    EventSerializationError,
    EventSerializer,
    auto_register_event_types,
)


def _make_created_event(**kwargs) -> WorkItemCreatedEvent:
    defaults = {
        "type": "workitem.created",
        "timestamp": now_iso(),
        "source": "test",
        "work_item_id": "work-item-123",
        "project_id": "proj-1",
        "title": "Test Work Item",
    }
    defaults.update(kwargs)
    return WorkItemCreatedEvent(**defaults)


class TestEventSerializer:
    """Tests for EventSerializer with CodetoreumEvent."""

    def setup_method(self):
        EventSerializer._codetoeum_event_registry.clear()
        auto_register_event_types()

    def test_serialize_modern_event(self):
        """Test serializing a modern frozen dataclass event."""
        event = _make_created_event()

        json_str = EventSerializer.serialize(event)

        assert json_str is not None
        data = json.loads(json_str)
        assert data["schema_version"] == EventSerializer.SCHEMA_VERSION
        assert data["event_class"] == "CodetoreumEvent"
        assert data["type"] == "workitem.created"
        assert data["work_item_id"] == "work-item-123"

    def test_deserialize_modern_event(self):
        """Test round-trip serialize → deserialize."""
        event = _make_created_event()

        json_str = EventSerializer.serialize(event)
        deserialized = EventSerializer.deserialize(json_str)

        assert isinstance(deserialized, WorkItemCreatedEvent)
        assert deserialized.work_item_id == event.work_item_id
        assert deserialized.project_id == event.project_id
        assert deserialized.title == event.title

    def test_serialize_invalid_event_raises_error(self):
        """Test that serializing non-serializable data raises error."""

        class BadEvent(WorkItemCreatedEvent):
            def to_dict(self):
                return {"bad": object()}  # Non-serializable

        event = BadEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="test",
            work_item_id="123",
            project_id="proj-1",
            title="Test",
        )
        with pytest.raises(EventSerializationError):
            EventSerializer.serialize(event)

    def test_deserialize_invalid_json_raises_error(self):
        """Test that deserializing invalid JSON raises error."""
        with pytest.raises(EventSerializationError):
            EventSerializer.deserialize("not valid json")

    def test_deserialize_unknown_event_type_raises_error(self):
        """Test that unknown event class raises error."""
        data = json.dumps(
            {
                "schema_version": 1,
                "event_class": "CodetoreumEvent",
                "type": "unknown.event",
                "timestamp": now_iso(),
                "source": "test",
                "event_id": "some-id",
            }
        )
        with pytest.raises(EventSerializationError):
            EventSerializer.deserialize(data)

    def test_register_event_type(self):
        """Test registering event types."""
        EventSerializer._codetoeum_event_registry.clear()
        EventSerializer.register_event_type(WorkItemCreatedEvent)
        assert "WorkItemCreatedEvent" in EventSerializer._codetoeum_event_registry

    def test_register_duplicate_same_class_ok(self):
        """Test registering same event type twice is allowed."""
        EventSerializer.register_event_type(WorkItemCreatedEvent)
        EventSerializer.register_event_type(WorkItemCreatedEvent)  # Should not raise
        assert "WorkItemCreatedEvent" in EventSerializer._codetoeum_event_registry

    def test_register_duplicate_different_class_raises_error(self):
        """Test registering same name with different class raises error."""

        class WorkItemCreatedEvent:  # same name, different class
            __name__ = "WorkItemCreatedEvent"

        # Already registered by auto_register_event_types
        with pytest.raises(ValueError, match="already registered"):
            EventSerializer.register_event_type(WorkItemCreatedEvent)

    def test_schema_version_present_in_serialized(self):
        """Test schema version is present in serialized output."""
        event = _make_created_event()
        json_str = EventSerializer.serialize(event)
        data = json.loads(json_str)
        assert data["schema_version"] == EventSerializer.SCHEMA_VERSION

    def test_to_dict_conversion(self):
        """Test converting event to dictionary for indexing."""
        event = _make_created_event()
        event_dict = EventSerializer.to_dict(event)

        assert event_dict["event_type"] == "WorkItemCreatedEvent"
        assert event_dict["event_class"] == "WorkItemCreatedEvent"
        assert "work_item_id" in event_dict["data"]
        assert event_dict["data"]["work_item_id"] == "work-item-123"

    def test_auto_register_populates_registry(self):
        """Test auto_register_event_types populates the registry."""
        assert "WorkItemCreatedEvent" in EventSerializer._codetoeum_event_registry
        assert "ExecutionInitializedEvent" in EventSerializer._codetoeum_event_registry
        assert "WorkflowCreatedEvent" in EventSerializer._codetoeum_event_registry
        assert "ExecutionCancelledEvent" in EventSerializer._codetoeum_event_registry
        assert "ExecutionPausedEvent" in EventSerializer._codetoeum_event_registry
        assert "ExecutionResumedEvent" in EventSerializer._codetoeum_event_registry
        assert "ExecutionRetryScheduledEvent" in EventSerializer._codetoeum_event_registry

    def test_execution_initialized_event_round_trip(self):
        """ExecutionInitializedEvent survives a full serialize/deserialize round-trip."""
        ts = now_iso()
        event = ExecutionInitializedEvent(
            type="execution.initialized",
            timestamp=ts,
            source="test",
            execution_id="exec-rt-1",
            work_item_id="work-rt-1",
            agent_id="agent-rt-1",
        )

        json_str = EventSerializer.serialize(event)
        deserialized = EventSerializer.deserialize(json_str)

        assert isinstance(deserialized, ExecutionInitializedEvent)
        assert deserialized.execution_id == event.execution_id
        assert deserialized.work_item_id == event.work_item_id
        assert deserialized.agent_id == event.agent_id
        assert deserialized.timestamp == event.timestamp
