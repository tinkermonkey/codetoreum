"""Unit tests for simulation SSE stream router."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from codetoreum.adapters.primary.routers.simulation_stream import (
    SSEEventPayload,
    event_matches_filters,
    format_keepalive_comment,
    format_sse_frame,
)
from codetoreum.infrastructure.event_bus import EventBus


class DomainEvent:
    def __init__(self, aggregate_id="", aggregate_type="", payload=None, **kwargs):
        self.aggregate_id = aggregate_id
        self.aggregate_type = aggregate_type
        self.payload = payload or {}
        self.event_id = str(uuid4())
        self.occurred_at = datetime.now(UTC)
        self.correlation_id = None
        # Expose payload keys as direct attributes to match modern CodetoreumEvent interface
        for key, val in self.payload.items():
            setattr(self, key, val)

    @property
    def event_type(self):
        return self.__class__.__name__


from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine

# =========================================================================
# Unit Tests for SSE Frame Formatting
# =========================================================================


class TestSSEFrameFormatting:
    """Test SSE frame formatting."""

    def test_format_sse_frame_produces_valid_protocol(self):
        """Test that SSE frame follows the standard SSE protocol."""
        event_type = "WorkItemColumnChangedEvent"
        event_id = str(uuid4())
        data = {"work_item_id": "WI-123", "column": "In Progress"}

        frame = format_sse_frame(event_type, event_id, data)

        # Should contain event line
        assert f"event: {event_type}\n" in frame

        # Should contain id line
        assert f"id: {event_id}\n" in frame

        # Should contain data line with JSON
        expected_json = json.dumps(data)
        assert f"data: {expected_json}\n" in frame

        # Should end with double newline
        assert frame.endswith("\n\n")

    def test_format_sse_frame_with_special_characters(self):
        """Test SSE frame formatting with special characters in data."""
        event_type = "TestEvent"
        event_id = str(uuid4())
        data = {
            "message": 'Contains "quotes" and\\backslashes',
            "unicode": "Contains émojis 🚀",
        }

        frame = format_sse_frame(event_type, event_id, data)

        # Frame should be valid
        assert frame.startswith("event:")
        assert "\n\n" in frame

        # Extract the JSON data part
        lines = frame.split("\n")
        data_line = [line for line in lines if line.startswith("data: ")][0]
        data_json = data_line[6:]  # Remove "data: " prefix

        # Should be valid JSON
        parsed = json.loads(data_json)
        assert parsed["message"] == data["message"]
        assert parsed["unicode"] == data["unicode"]

    def test_format_keepalive_comment(self):
        """Test keepalive comment format."""
        comment = format_keepalive_comment()

        assert comment == ":keepalive\n\n"


# =========================================================================
# Unit Tests for Event Filtering
# =========================================================================


class TestEventFiltering:
    """Test event filtering logic."""

    @pytest.fixture
    def work_item_event(self):
        """Create a sample work item event."""
        return DomainEvent(
            aggregate_id="WI-123",
            aggregate_type="WorkItem",
            payload={
                "work_item_id": "WI-123",
                "agent_id": "agent-dev-01",
                "column": "In Progress",
            },
        )

    @pytest.fixture
    def workflow_event(self):
        """Create a sample workflow event."""
        return DomainEvent(
            aggregate_id="workflow-1",
            aggregate_type="Workflow",
            payload={"workflow_id": "workflow-1", "status": "started"},
        )

    def test_event_matches_filters_with_no_filters(self, work_item_event):
        """Test that event matches when no filters are specified."""
        assert event_matches_filters(work_item_event, None, None) is True

    def test_event_matches_filters_with_event_type_match(self, work_item_event):
        """Test event type filter when event matches."""
        assert (
            event_matches_filters(
                work_item_event,
                ["DomainEvent", "WorkItemColumnChangedEvent"],
                None,
            )
            is True
        )

    def test_event_matches_filters_with_event_type_mismatch(self, work_item_event):
        """Test event type filter when event does not match."""
        assert (
            event_matches_filters(
                work_item_event,
                ["WorkflowStartedEvent", "ReviewRequestedEvent"],
                None,
            )
            is False
        )

    def test_event_matches_filters_with_work_item_id_match(self, work_item_event):
        """Test work item ID filter when event matches."""
        assert event_matches_filters(work_item_event, None, "WI-123") is True

    def test_event_matches_filters_with_work_item_id_mismatch(self, work_item_event):
        """Test work item ID filter when event does not match."""
        assert event_matches_filters(work_item_event, None, "WI-999") is False

    def test_event_matches_filters_with_both_filters_match(self, work_item_event):
        """Test both filters when event matches both."""
        assert (
            event_matches_filters(
                work_item_event,
                ["DomainEvent"],
                "WI-123",
            )
            is True
        )

    def test_event_matches_filters_with_both_filters_event_type_mismatch(self, work_item_event):
        """Test both filters when event type doesn't match."""
        assert (
            event_matches_filters(
                work_item_event,
                ["WorkflowStartedEvent"],
                "WI-123",
            )
            is False
        )

    def test_event_matches_filters_with_both_filters_work_item_mismatch(self, work_item_event):
        """Test both filters when work item doesn't match."""
        assert (
            event_matches_filters(
                work_item_event,
                ["DomainEvent"],
                "WI-999",
            )
            is False
        )

    def test_event_matches_filters_with_event_without_work_item_id(self, workflow_event):
        """Test filtering event that doesn't have work_item_id in payload."""
        # Event has no work_item_id, filter requires WI-123
        assert event_matches_filters(workflow_event, None, "WI-123") is False

    def test_event_matches_filters_with_none_work_item_in_payload(self):
        """Test filtering when work_item_id is None in payload."""
        event = DomainEvent(
            aggregate_id="agg-1",
            aggregate_type="Aggregate",
            payload={"work_item_id": None},
        )

        # Filter requires WI-123, but event has None
        assert event_matches_filters(event, None, "WI-123") is False

        # Filter with None should match
        assert event_matches_filters(event, None, None) is True


# =========================================================================
# Unit Tests for SSEEventPayload
# =========================================================================


class TestSSEEventPayload:
    """Test SSE event payload Pydantic model."""

    def test_sse_event_payload_creation(self):
        """Test creating SSE event payload."""
        now = datetime.now(UTC)
        payload = SSEEventPayload(
            event_type="WorkItemColumnChangedEvent",
            event_id="event-uuid",
            timestamp=now,
            simulation_time=now,
            work_item_id="WI-123",
            agent_id="agent-dev-01",
            details={"column": "In Progress"},
        )

        assert payload.event_type == "WorkItemColumnChangedEvent"
        assert payload.event_id == "event-uuid"
        assert payload.timestamp == now
        assert payload.simulation_time == now
        assert payload.work_item_id == "WI-123"
        assert payload.agent_id == "agent-dev-01"
        assert payload.details == {"column": "In Progress"}

    def test_sse_event_payload_with_none_optional_fields(self):
        """Test creating SSE event payload with optional fields as None."""
        now = datetime.now(UTC)
        payload = SSEEventPayload(
            event_type="WorkflowStartedEvent",
            event_id="event-uuid",
            timestamp=now,
            simulation_time=now,
        )

        assert payload.event_type == "WorkflowStartedEvent"
        assert payload.work_item_id is None
        assert payload.agent_id is None
        assert payload.details == {}

    def test_sse_event_payload_serialization(self):
        """Test serializing SSE event payload to JSON."""
        now = datetime.now(UTC)
        payload = SSEEventPayload(
            event_type="WorkItemColumnChangedEvent",
            event_id="event-uuid",
            timestamp=now,
            simulation_time=now,
            work_item_id="WI-123",
            agent_id="agent-dev-01",
            details={"column": "In Progress"},
        )

        # Serialize to JSON (as would be done in the SSE frame)
        json_data = payload.model_dump(mode="json", exclude_none=False)

        assert json_data["event_type"] == "WorkItemColumnChangedEvent"
        assert json_data["event_id"] == "event-uuid"
        assert json_data["work_item_id"] == "WI-123"
        assert json_data["agent_id"] == "agent-dev-01"


# =========================================================================
# Integration Tests for Event Bus Subscription
# =========================================================================


@pytest.mark.asyncio
class TestEventBusSubscription:
    """Test event bus subscription mechanics used by SSE stream."""

    @pytest.fixture
    def event_bus(self):
        """Create an event bus."""
        return EventBus()

    @pytest.fixture
    def engine(self):
        """Create a simulation engine."""
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        config = SimulationConfig.create_fast_config("test")
        return SimulationEngine(config)

    async def test_wildcard_subscription_receives_all_events(self, event_bus):
        """Test that wildcard subscription receives all event types."""
        received_events = []

        async def callback(event: DomainEvent):
            received_events.append(event)

        event_bus.subscribe(None, callback)

        # Publish different event types
        event1 = DomainEvent("agg-1", "Type1")
        event2 = DomainEvent("agg-2", "Type2")

        await event_bus.publish(event1)
        await event_bus.publish(event2)

        assert len(received_events) == 2
        assert received_events[0].aggregate_type == "Type1"
        assert received_events[1].aggregate_type == "Type2"

    async def test_unsubscribe_stops_receiving_events(self, event_bus):
        """Test that unsubscribing stops receiving events."""
        received_events = []

        async def callback(event: DomainEvent):
            received_events.append(event)

        event_bus.subscribe(None, callback)

        event1 = DomainEvent("agg-1", "Type1")
        await event_bus.publish(event1)
        assert len(received_events) == 1

        # Unsubscribe
        event_bus.unsubscribe(None, callback)

        event2 = DomainEvent("agg-2", "Type2")
        await event_bus.publish(event2)

        # Should still be 1 (unsubscribed)
        assert len(received_events) == 1

    async def test_multiple_wildcard_subscriptions(self, event_bus):
        """Test multiple wildcard subscriptions."""
        received1 = []
        received2 = []

        async def callback1(event: DomainEvent):
            received1.append(event)

        async def callback2(event: DomainEvent):
            received2.append(event)

        event_bus.subscribe(None, callback1)
        event_bus.subscribe(None, callback2)

        event = DomainEvent("agg-1", "Type1")
        await event_bus.publish(event)

        assert len(received1) == 1
        assert len(received2) == 1

    async def test_callback_can_extract_payload_data(self, event_bus):
        """Test that callback can extract data from event payload."""
        received_data = []

        async def callback(event: DomainEvent):
            work_item_id = event.payload.get("work_item_id")
            received_data.append(work_item_id)

        event_bus.subscribe(None, callback)

        event = DomainEvent(
            "WI-123",
            "WorkItem",
            payload={"work_item_id": "WI-123", "column": "In Progress"},
        )
        await event_bus.publish(event)

        assert received_data == ["WI-123"]
