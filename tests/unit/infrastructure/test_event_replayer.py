"""Unit tests for EventReplayer."""

from datetime import UTC, datetime, timedelta
from typing import Optional
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from codetoreum.domain.events import WorkItemCreated
from codetoreum.infrastructure.event_replayer import (
    EventReplayer,
    EventReplayerError,
    TimeManipulationReplayer,
)


class MockEventStore:
    """Mock event store for testing."""

    def __init__(self):
        """Initialize mock."""
        self.events = []
        self.appended = []

    async def get_events_since(self, since: datetime, stream_id: str | None = None):
        """Get events since timestamp."""
        events = [e for e in self.events if e.occurred_at >= since]
        if stream_id:
            events = [e for e in events if e.aggregate_id == stream_id]
        return events

    async def get_events(self, stream_id: str, from_version: int = 0, to_version: int | None = None):
        """Get events for stream."""
        events = [e for e in self.events if e.aggregate_id == stream_id]
        return events

    async def get_events_by_type(self, event_type: str, since: datetime | None = None, limit: int = 1000):
        """Get events by type."""
        events = [e for e in self.events if e.event_type == event_type]
        if since:
            events = [e for e in events if e.occurred_at >= since]
        return events[:limit]

    async def get_all_stream_ids(self):
        """Get all stream IDs."""
        return list(set(e.aggregate_id for e in self.events))

    async def replay_events(self, stream_id: str, from_version: int = 0, to_version: int | None = None):
        """Replay events (async generator)."""
        for event in self.events:
            if event.aggregate_id == stream_id:
                yield event

    async def append(self, stream_id: str, events: list, expected_version: int | None = None):
        """Append events."""
        self.appended.append((stream_id, events))


class MockEventBus:
    """Mock event bus for testing."""

    def __init__(self):
        """Initialize mock."""
        self.published_events = []

    async def publish(self, event):
        """Publish event."""
        self.published_events.append(event)


class TestEventReplayer:
    """Tests for EventReplayer."""

    def test_initialization_with_event_store_only(self):
        """Test initialization with only event store."""
        event_store = MockEventStore()
        replayer = EventReplayer(event_store)

        assert replayer.event_store is event_store
        assert replayer.event_bus is None
        assert replayer.get_statistics()["events_replayed"] == 0

    def test_initialization_with_event_bus(self):
        """Test initialization with event store and event bus."""
        event_store = MockEventStore()
        event_bus = MockEventBus()
        replayer = EventReplayer(event_store, event_bus)

        assert replayer.event_store is event_store
        assert replayer.event_bus is event_bus

    @pytest.mark.asyncio
    async def test_replay_from_timestamp_empty(self):
        """Test replaying from timestamp with no events."""
        event_store = MockEventStore()
        replayer = EventReplayer(event_store)

        since = datetime.now(UTC) - timedelta(hours=1)

        stats = await replayer.replay_from_timestamp(since)

        assert stats["events_replayed"] == 0
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_replay_from_timestamp_with_events(self):
        """Test replaying from timestamp with events."""
        event_store = MockEventStore()
        event_bus = MockEventBus()
        replayer = EventReplayer(event_store, event_bus)

        # Add events to store
        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test 1", "description": "", "project_id": "proj-1"},
                occurred_at=now,
            ),
            WorkItemCreated(
                aggregate_id="work-2",
                payload={"title": "Test 2", "description": "", "project_id": "proj-1"},
                occurred_at=now + timedelta(seconds=1),
            ),
        ]

        since = now - timedelta(minutes=1)

        stats = await replayer.replay_from_timestamp(since)

        assert stats["events_replayed"] == 2
        assert len(event_bus.published_events) == 2

    @pytest.mark.asyncio
    async def test_replay_from_timestamp_with_dry_run(self):
        """Test replay with dry_run mode (don't publish)."""
        event_store = MockEventStore()
        event_bus = MockEventBus()
        replayer = EventReplayer(event_store, event_bus)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test", "description": "", "project_id": "proj-1"},
                occurred_at=now,
            ),
        ]

        since = now - timedelta(minutes=1)

        stats = await replayer.replay_from_timestamp(since, dry_run=True)

        assert stats["events_replayed"] == 1
        # No events should be published in dry-run mode
        assert len(event_bus.published_events) == 0

    @pytest.mark.asyncio
    async def test_replay_from_timestamp_with_until(self):
        """Test replay with until timestamp."""
        event_store = MockEventStore()
        replayer = EventReplayer(event_store)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test 1", "description": "", "project_id": "proj-1"},
                occurred_at=now,
            ),
            WorkItemCreated(
                aggregate_id="work-2",
                payload={"title": "Test 2", "description": "", "project_id": "proj-1"},
                occurred_at=now + timedelta(hours=1),
            ),
            WorkItemCreated(
                aggregate_id="work-3",
                payload={"title": "Test 3", "description": "", "project_id": "proj-1"},
                occurred_at=now + timedelta(hours=2),
            ),
        ]

        since = now - timedelta(minutes=1)
        until = now + timedelta(minutes=30)

        stats = await replayer.replay_from_timestamp(since, until=until)

        assert stats["events_replayed"] == 1  # Only event 1

    @pytest.mark.asyncio
    async def test_replay_from_timestamp_with_event_type_filter(self):
        """Test replay with event type filtering."""
        event_store = MockEventStore()
        replayer = EventReplayer(event_store)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test", "description": "", "project_id": "proj-1"},
                occurred_at=now,
            ),
        ]

        since = now - timedelta(minutes=1)

        stats = await replayer.replay_from_timestamp(since, event_types=["WorkItemCreated"])

        assert stats["events_replayed"] == 1

    @pytest.mark.asyncio
    async def test_replay_stream(self):
        """Test replaying events for specific stream."""
        event_store = MockEventStore()
        event_bus = MockEventBus()
        replayer = EventReplayer(event_store, event_bus)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test 1", "description": "", "project_id": "proj-1"},
                occurred_at=now,
            ),
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test 1b", "description": "", "project_id": "proj-1"},
                occurred_at=now + timedelta(seconds=1),
            ),
            WorkItemCreated(
                aggregate_id="work-2",
                payload={"title": "Test 2", "description": "", "project_id": "proj-1"},
                occurred_at=now + timedelta(seconds=2),
            ),
        ]

        stats = await replayer.replay_stream("work-1")

        assert stats["events_replayed"] == 2

    @pytest.mark.asyncio
    async def test_replay_event_type(self):
        """Test replaying events of specific type."""
        event_store = MockEventStore()
        event_bus = MockEventBus()
        replayer = EventReplayer(event_store, event_bus)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test", "description": "", "project_id": "proj-1"},
                occurred_at=now,
            ),
        ]

        stats = await replayer.replay_event_type("WorkItemCreated")

        assert stats["events_replayed"] == 1

    @pytest.mark.asyncio
    async def test_replay_event_type_with_limit(self):
        """Test replaying event type with limit."""
        event_store = MockEventStore()
        replayer = EventReplayer(event_store)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id=f"work-{i}",
                payload={"title": f"Test {i}", "description": "", "project_id": "proj-1"},
                occurred_at=now + timedelta(seconds=i),
            )
            for i in range(10)
        ]

        stats = await replayer.replay_event_type("WorkItemCreated", limit=5)

        assert stats["events_replayed"] == 5

    @pytest.mark.asyncio
    async def test_get_statistics(self):
        """Test getting replayer statistics."""
        event_store = MockEventStore()
        replayer = EventReplayer(event_store)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test", "description": "", "project_id": "proj-1"},
                occurred_at=now,
            ),
        ]

        await replayer.replay_from_timestamp(now - timedelta(minutes=1))

        stats = replayer.get_statistics()

        assert "events_replayed" in stats
        assert "errors" in stats
        assert "duration_seconds" in stats
        assert "events_per_second" in stats

    @pytest.mark.asyncio
    async def test_progress_callback(self):
        """Test progress callback during replay."""
        event_store = MockEventStore()
        replayer = EventReplayer(event_store)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id=f"work-{i}",
                payload={"title": f"Test {i}", "description": "", "project_id": "proj-1"},
                occurred_at=now + timedelta(seconds=i),
            )
            for i in range(3)
        ]

        progress_updates = []

        def progress_callback(current: int, total: int):
            progress_updates.append((current, total))

        await replayer.replay_from_timestamp(
            now - timedelta(minutes=1),
            progress_callback=progress_callback,
        )

        assert len(progress_updates) == 3
        assert progress_updates[-1] == (3, 3)

    @pytest.mark.asyncio
    async def test_replay_stream_iterator(self):
        """Test streaming replay iterator."""
        event_store = MockEventStore()
        replayer = EventReplayer(event_store)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test", "description": "", "project_id": "proj-1"},
                occurred_at=now + timedelta(seconds=i),
            )
            for i in range(3)
        ]

        events_streamed = []
        async for event in replayer.stream_replay_iterator("work-1"):
            events_streamed.append(event)

        assert len(events_streamed) == 3

    @pytest.mark.asyncio
    async def test_rebuild_projection(self):
        """Test rebuilding projection from events."""
        event_store = MockEventStore()
        replayer = EventReplayer(event_store)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test", "description": "", "project_id": "proj-1"},
                occurred_at=now,
            ),
        ]

        # Mock projection handler
        projection_handler = Mock()
        projection_handler.handle = AsyncMock()

        stats = await replayer.rebuild_projection(projection_handler)

        assert stats["events_replayed"] == 1
        projection_handler.handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling_get_events_since_fails(self):
        """Test error handling when event store fails."""
        event_store = AsyncMock()
        event_store.get_events_since.side_effect = Exception("Store error")

        replayer = EventReplayer(event_store)

        with pytest.raises(EventReplayerError):
            await replayer.replay_from_timestamp(datetime.now(UTC))


class TestTimeManipulationReplayer:
    """Tests for TimeManipulationReplayer."""

    def test_initialization(self):
        """Test initialization."""
        event_store = MockEventStore()
        replayer = TimeManipulationReplayer(event_store)

        assert replayer.event_store is event_store

    @pytest.mark.asyncio
    async def test_fast_forward_replay(self):
        """Test fast-forward replay."""
        event_store = MockEventStore()
        replayer = TimeManipulationReplayer(event_store)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test 1", "description": "", "project_id": "proj-1"},
                occurred_at=now,
            ),
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test 2", "description": "", "project_id": "proj-1"},
                occurred_at=now + timedelta(minutes=5),
            ),
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test 3", "description": "", "project_id": "proj-1"},
                occurred_at=now + timedelta(minutes=10),
            ),
        ]

        target_timestamp = now + timedelta(minutes=7)

        stats = await replayer.fast_forward_replay("work-1", target_timestamp, speed_multiplier=100.0)

        assert stats["events_replayed"] == 2  # Only events up to target

    @pytest.mark.asyncio
    async def test_fast_forward_replay_speed_multiplier(self):
        """Test that speed multiplier affects timing."""
        event_store = MockEventStore()
        replayer = TimeManipulationReplayer(event_store)

        now = datetime.now(UTC)
        event_store.events = [
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test 1", "description": "", "project_id": "proj-1"},
                occurred_at=now,
            ),
            WorkItemCreated(
                aggregate_id="work-1",
                payload={"title": "Test 2", "description": "", "project_id": "proj-1"},
                occurred_at=now + timedelta(seconds=60),
            ),
        ]

        target_timestamp = now + timedelta(seconds=120)

        stats = await replayer.fast_forward_replay("work-1", target_timestamp, speed_multiplier=100.0)

        # Should complete quickly due to 100x speed multiplier
        assert stats["events_replayed"] >= 1
