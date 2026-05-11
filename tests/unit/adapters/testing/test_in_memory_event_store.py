"""Unit tests for InMemoryEventStore."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from codetoreum.adapters.testing import InMemoryEventStore
from codetoreum.infrastructure.simulation.simulation_config import (
    FidelityLevel,
    SimulationConfig,
)
from codetoreum.ports.exceptions import ConcurrencyConflictError, ResourceNotFoundError


class DomainEvent:
    """Local shim replacing deleted legacy DomainEvent for test fixtures."""

    def __init__(self, aggregate_id="", aggregate_type="", payload=None, correlation_id=None, **kwargs):
        self.aggregate_id = aggregate_id
        self.aggregate_type = aggregate_type
        self.payload = payload or {}
        self.event_id = str(uuid4())
        self.occurred_at = datetime.now(UTC)
        self.correlation_id = correlation_id

    @property
    def event_type(self):
        return self.__class__.__name__


class WorkItemCreated(DomainEvent):
    def __init__(self, aggregate_id="", payload=None, correlation_id=None, **kwargs):
        super().__init__(
            aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, correlation_id=correlation_id
        )


class WorkItemStarted(DomainEvent):
    def __init__(self, aggregate_id="", payload=None, correlation_id=None, **kwargs):
        super().__init__(
            aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, correlation_id=correlation_id
        )


class WorkItemCompleted(DomainEvent):
    def __init__(self, aggregate_id="", payload=None, correlation_id=None, **kwargs):
        super().__init__(
            aggregate_id=aggregate_id, aggregate_type="WorkItem", payload=payload, correlation_id=correlation_id
        )


class AgentCreated(DomainEvent):
    def __init__(self, aggregate_id="", payload=None, correlation_id=None, **kwargs):
        super().__init__(
            aggregate_id=aggregate_id, aggregate_type="Agent", payload=payload, correlation_id=correlation_id
        )


@pytest.mark.asyncio
class TestInMemoryEventStore:
    """Tests for InMemoryEventStore."""

    @pytest.fixture
    def store(self):
        """Create store instance."""
        return InMemoryEventStore()

    @pytest.fixture
    def sample_event(self):
        """Create a sample event."""
        return WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "title": "Test Work Item",
                "description": "Test description",
                "project_id": "project-1",
                "labels": ["bug", "priority-high"],
                "priority": 1,
                "external_id": "EXT-123",
                "external_url": "https://github.com/test/issues/123",
            },
        )

    async def test_append_events(self, store, sample_event):
        """Test appending events to a stream."""
        stream_id = "work-item-123"

        await store.append(stream_id, [sample_event])

        events = await store.get_events(stream_id)
        assert len(events) == 1
        assert events[0].event_type == "WorkItemCreated"

    async def test_append_multiple_events(self, store):
        """Test appending multiple events at once."""
        stream_id = "work-item-123"

        events = [
            WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": "Test",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            ),
            WorkItemStarted(
                aggregate_id=stream_id,
                payload={
                    "started_at": datetime.now(UTC).isoformat(),
                    "agent_id": "agent-1",
                },
            ),
        ]

        await store.append(stream_id, events)

        retrieved = await store.get_events(stream_id)
        assert len(retrieved) == 2
        assert retrieved[0].event_type == "WorkItemCreated"
        assert retrieved[1].event_type == "WorkItemStarted"

    async def test_append_with_version_check_success(self, store, sample_event):
        """Test append with correct expected version."""
        stream_id = "work-item-123"

        # First append at version 0
        await store.append(stream_id, [sample_event], expected_version=0)

        # Second append at version 1
        new_event = WorkItemStarted(
            aggregate_id=stream_id,
            payload={
                "started_at": datetime.now(UTC).isoformat(),
                "agent_id": "agent-1",
            },
        )
        await store.append(stream_id, [new_event], expected_version=1)

        events = await store.get_events(stream_id)
        assert len(events) == 2

    async def test_append_with_version_check_conflict(self, store, sample_event):
        """Test append with incorrect expected version raises conflict error."""
        stream_id = "work-item-123"

        await store.append(stream_id, [sample_event])

        new_event = WorkItemStarted(
            aggregate_id=stream_id,
            payload={
                "started_at": datetime.now(UTC).isoformat(),
                "agent_id": "agent-1",
            },
        )

        # Try to append with wrong expected version
        with pytest.raises(ConcurrencyConflictError, match="Expected version"):
            await store.append(stream_id, [new_event], expected_version=0)

    async def test_append_empty_list(self, store):
        """Test appending empty list does nothing."""
        stream_id = "test-stream"

        await store.append(stream_id, [])

        # Stream should not be created
        assert not await store.stream_exists(stream_id)

    async def test_get_events_from_version(self, store):
        """Test getting events starting from a specific version."""
        stream_id = "work-item-123"

        events = [
            WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": f"Event {i}",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            )
            for i in range(5)
        ]

        await store.append(stream_id, events)

        # Get events from version 2 onwards
        retrieved = await store.get_events(stream_id, from_version=2)
        assert len(retrieved) == 3

    async def test_get_events_with_version_range(self, store):
        """Test getting events within a version range."""
        stream_id = "work-item-123"

        events = [
            WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": f"Event {i}",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            )
            for i in range(10)
        ]

        await store.append(stream_id, events)

        # Get events from version 2 to 5
        retrieved = await store.get_events(stream_id, from_version=2, to_version=5)
        assert len(retrieved) == 4  # Includes version 5

    async def test_get_events_nonexistent_stream_fails(self, store):
        """Test getting events from non-existent stream fails."""
        with pytest.raises(ResourceNotFoundError, match="Stream"):
            await store.get_events("nonexistent-stream")

    async def test_get_events_since_timestamp(self, store):
        """Test getting events since a timestamp."""
        stream_id = "work-item-123"

        # Create old event
        old_event = WorkItemCreated(
            aggregate_id=stream_id,
            payload={
                "title": "Old Event",
                "description": "Test",
                "project_id": "proj-1",
                "labels": [],
                "priority": 1,
            },
        )

        await store.append(stream_id, [old_event])

        # Mark the time
        cutoff_time = datetime.now(UTC)
        await asyncio.sleep(0.01)

        # Create new events
        new_events = [
            WorkItemStarted(
                aggregate_id=stream_id,
                payload={
                    "started_at": datetime.now(UTC).isoformat(),
                    "agent_id": "agent-1",
                },
            ),
            WorkItemCompleted(
                aggregate_id=stream_id,
                payload={
                    "completed_at": datetime.now(UTC).isoformat(),
                    "agent_id": "agent-1",
                },
            ),
        ]

        await store.append(stream_id, new_events)

        # Get events since cutoff
        recent = await store.get_events_since(cutoff_time, stream_id=stream_id)
        assert len(recent) == 2
        assert all(e.occurred_at > cutoff_time for e in recent)

    async def test_get_events_since_all_streams(self, store):
        """Test getting events since timestamp across all streams."""
        # Create events in multiple streams
        stream1 = "work-item-1"
        stream2 = "work-item-2"

        event1 = WorkItemCreated(
            aggregate_id=stream1,
            payload={
                "title": "Item 1",
                "description": "Test",
                "project_id": "proj-1",
                "labels": [],
                "priority": 1,
            },
        )

        await store.append(stream1, [event1])

        cutoff_time = datetime.now(UTC)
        await asyncio.sleep(0.01)

        event2 = WorkItemCreated(
            aggregate_id=stream2,
            payload={
                "title": "Item 2",
                "description": "Test",
                "project_id": "proj-1",
                "labels": [],
                "priority": 1,
            },
        )

        await store.append(stream2, [event2])

        # Get all events since cutoff
        recent = await store.get_events_since(cutoff_time)
        assert len(recent) == 1
        assert recent[0].aggregate_id == stream2

    async def test_stream_events(self, store):
        """Test streaming events from a stream."""
        stream_id = "work-item-123"

        events = [
            WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": f"Event {i}",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            )
            for i in range(3)
        ]

        await store.append(stream_id, events)

        # Stream events
        streamed = []
        async for event in store.stream_events(stream_id):
            streamed.append(event)

        assert len(streamed) == 3
        assert all(isinstance(e, DomainEvent) for e in streamed)

    async def test_stream_events_from_version(self, store):
        """Test streaming events from a specific version."""
        stream_id = "work-item-123"

        events = [
            WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": f"Event {i}",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            )
            for i in range(5)
        ]

        await store.append(stream_id, events)

        # Stream from version 2
        streamed = []
        async for event in store.stream_events(stream_id, from_version=2):
            streamed.append(event)

        assert len(streamed) == 3

    async def test_stream_events_nonexistent_stream_fails(self, store):
        """Test streaming from non-existent stream fails."""
        with pytest.raises(ResourceNotFoundError, match="Stream"):
            async for _ in store.stream_events("nonexistent"):
                pass

    async def test_get_stream_version(self, store, sample_event):
        """Test getting current stream version."""
        stream_id = "work-item-123"

        # Empty stream has version 0
        version = await store.get_stream_version(stream_id)
        assert version == 0

        # After appending, version increases
        await store.append(stream_id, [sample_event])
        version = await store.get_stream_version(stream_id)
        assert version == 1

        # Append more events
        await store.append(stream_id, [sample_event, sample_event])
        version = await store.get_stream_version(stream_id)
        assert version == 3

    async def test_stream_exists(self, store, sample_event):
        """Test checking if stream exists."""
        stream_id = "work-item-123"

        assert not await store.stream_exists(stream_id)

        await store.append(stream_id, [sample_event])

        assert await store.stream_exists(stream_id)

    async def test_save_snapshot(self, store):
        """Test saving a snapshot."""
        stream_id = "work-item-123"
        snapshot_data = {
            "title": "Test Work Item",
            "status": "in_progress",
            "agent_id": "agent-1",
        }

        await store.save_snapshot(
            stream_id=stream_id,
            version=5,
            snapshot=snapshot_data,
        )

        snapshot = await store.get_latest_snapshot(stream_id)
        assert snapshot is not None
        assert snapshot["version"] == 5
        assert snapshot["data"] == snapshot_data

    async def test_get_latest_snapshot_nonexistent(self, store):
        """Test getting snapshot for stream with no snapshot returns None."""
        snapshot = await store.get_latest_snapshot("nonexistent")
        assert snapshot is None

    async def test_save_snapshot_overwrites_previous(self, store):
        """Test saving snapshot overwrites previous one."""
        stream_id = "work-item-123"

        # Save first snapshot
        await store.save_snapshot(
            stream_id=stream_id,
            version=5,
            snapshot={"data": "old"},
        )

        # Save newer snapshot
        await store.save_snapshot(
            stream_id=stream_id,
            version=10,
            snapshot={"data": "new"},
        )

        snapshot = await store.get_latest_snapshot(stream_id)
        assert snapshot["version"] == 10
        assert snapshot["data"]["data"] == "new"

    async def test_delete_stream(self, store):
        """Test deleting a stream."""
        stream_id = "work-item-123"

        events = [
            WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": "Test",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            ),
            WorkItemStarted(
                aggregate_id=stream_id,
                payload={
                    "started_at": datetime.now(UTC).isoformat(),
                    "agent_id": "agent-1",
                },
            ),
        ]

        await store.append(stream_id, events)
        await store.save_snapshot(stream_id, 2, {"data": "test"})

        # Delete stream
        await store.delete_stream(stream_id)

        # Stream should no longer exist
        assert not await store.stream_exists(stream_id)
        assert await store.get_stream_version(stream_id) == 0
        assert await store.get_latest_snapshot(stream_id) is None

        # Should not appear in global events
        all_events = store.get_all_events_list()
        assert not any(e.aggregate_id == stream_id for e in all_events)

    async def test_delete_stream_nonexistent_fails(self, store):
        """Test deleting non-existent stream fails."""
        with pytest.raises(ResourceNotFoundError, match="Stream"):
            await store.delete_stream("nonexistent")

    async def test_get_all_stream_ids(self, store):
        """Test getting all stream IDs."""
        # Create multiple streams
        streams = ["work-item-1", "work-item-2", "agent-1"]

        for stream_id in streams:
            event = WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": "Test",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            )
            await store.append(stream_id, [event])

        stream_ids = await store.get_all_stream_ids()
        assert len(stream_ids) == 3
        assert set(stream_ids) == set(streams)

    async def test_get_all_stream_ids_filtered_by_aggregate_type(self, store):
        """Test getting stream IDs filtered by aggregate type."""
        # Create WorkItem streams
        work_item_event = WorkItemCreated(
            aggregate_id="work-item-1",
            payload={
                "title": "Test",
                "description": "Test",
                "project_id": "proj-1",
                "labels": [],
                "priority": 1,
            },
        )
        await store.append("work-item-1", [work_item_event])

        # Create Agent stream
        agent_event = AgentCreated(
            aggregate_id="agent-1",
            payload={
                "name": "test-agent",
                "display_name": "Test Agent",
                "agent_type": "coder",
                "model": "claude-3",
                "capabilities": ["python"],
            },
        )
        await store.append("agent-1", [agent_event])

        # Filter by WorkItem
        work_item_streams = await store.get_all_stream_ids(aggregate_type="WorkItem")
        assert len(work_item_streams) == 1
        assert work_item_streams[0] == "work-item-1"

        # Filter by Agent
        agent_streams = await store.get_all_stream_ids(aggregate_type="Agent")
        assert len(agent_streams) == 1
        assert agent_streams[0] == "agent-1"

    async def test_get_events_by_type(self, store):
        """Test getting events by type."""
        # Create multiple events of different types
        stream_id = "work-item-123"

        events = [
            WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": "Test",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            ),
            WorkItemStarted(
                aggregate_id=stream_id,
                payload={
                    "started_at": datetime.now(UTC).isoformat(),
                    "agent_id": "agent-1",
                },
            ),
            WorkItemCompleted(
                aggregate_id=stream_id,
                payload={
                    "completed_at": datetime.now(UTC).isoformat(),
                    "agent_id": "agent-1",
                },
            ),
        ]

        await store.append(stream_id, events)

        # Get only WorkItemStarted events
        started_events = await store.get_events_by_type("WorkItemStarted")
        assert len(started_events) == 1
        assert started_events[0].event_type == "WorkItemStarted"

    async def test_get_events_by_type_with_since(self, store):
        """Test getting events by type with timestamp filter."""
        stream_id = "work-item-123"

        # Old event
        old_event = WorkItemStarted(
            aggregate_id=stream_id,
            payload={
                "started_at": datetime.now(UTC).isoformat(),
                "agent_id": "agent-1",
            },
        )
        await store.append(stream_id, [old_event])

        cutoff_time = datetime.now(UTC)
        await asyncio.sleep(0.01)

        # New event
        new_event = WorkItemStarted(
            aggregate_id=stream_id,
            payload={
                "started_at": datetime.now(UTC).isoformat(),
                "agent_id": "agent-2",
            },
        )
        await store.append(stream_id, [new_event])

        # Get events since cutoff
        recent_events = await store.get_events_by_type(
            "WorkItemStarted",
            since=cutoff_time,
        )
        assert len(recent_events) == 1
        assert recent_events[0].occurred_at > cutoff_time

    async def test_get_events_by_type_with_limit(self, store):
        """Test getting events by type with limit."""
        stream_id = "work-item-123"

        events = [
            WorkItemStarted(
                aggregate_id=stream_id,
                payload={
                    "started_at": datetime.now(UTC).isoformat(),
                    "agent_id": f"agent-{i}",
                },
            )
            for i in range(10)
        ]

        await store.append(stream_id, events)

        # Get with limit
        limited_events = await store.get_events_by_type("WorkItemStarted", limit=5)
        assert len(limited_events) == 5

    async def test_get_events_by_correlation_id(self, store):
        """Test getting events by correlation ID."""
        correlation_id = uuid4()
        stream_id = "work-item-123"

        # Create events with same correlation ID
        events = [
            WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": "Test",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
                correlation_id=correlation_id,
            ),
            WorkItemStarted(
                aggregate_id=stream_id,
                payload={
                    "started_at": datetime.now(UTC).isoformat(),
                    "agent_id": "agent-1",
                },
                correlation_id=correlation_id,
            ),
        ]

        await store.append(stream_id, events)

        # Create event with different correlation ID
        other_event = WorkItemCompleted(
            aggregate_id=stream_id,
            payload={
                "completed_at": datetime.now(UTC).isoformat(),
                "agent_id": "agent-1",
            },
            correlation_id=uuid4(),
        )
        await store.append(stream_id, [other_event])

        # Get by correlation ID
        correlated = await store.get_events_by_correlation_id(str(correlation_id))
        assert len(correlated) == 2
        assert all(e.correlation_id == correlation_id for e in correlated)

    async def test_get_events_by_correlation_id_nonexistent(self, store):
        """Test getting events by non-existent correlation ID returns empty list."""
        events = await store.get_events_by_correlation_id(str(uuid4()))
        assert len(events) == 0

    async def test_replay_events(self, store):
        """Test replaying events from a stream."""
        stream_id = "work-item-123"

        events = [
            WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": f"Event {i}",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            )
            for i in range(3)
        ]

        await store.append(stream_id, events)

        # Replay events
        replayed = []
        async for event in store.replay_events(stream_id):
            replayed.append(event)

        assert len(replayed) == 3
        assert all(isinstance(e, DomainEvent) for e in replayed)

    async def test_replay_events_with_version_range(self, store):
        """Test replaying events within a version range."""
        stream_id = "work-item-123"

        events = [
            WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": f"Event {i}",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            )
            for i in range(10)
        ]

        await store.append(stream_id, events)

        # Replay events from version 3 to 6
        replayed = []
        async for event in store.replay_events(stream_id, from_version=3, to_version=6):
            replayed.append(event)

        assert len(replayed) == 4

    async def test_replay_events_nonexistent_stream_fails(self, store):
        """Test replaying from non-existent stream fails."""
        with pytest.raises(ResourceNotFoundError, match="Stream"):
            async for _ in store.replay_events("nonexistent"):
                pass

    async def test_get_statistics(self, store):
        """Test getting event store statistics."""
        # Create multiple streams with events
        stream1 = "work-item-1"
        stream2 = "work-item-2"

        events1 = [
            WorkItemCreated(
                aggregate_id=stream1,
                payload={
                    "title": "Item 1",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            ),
            WorkItemStarted(
                aggregate_id=stream1,
                payload={
                    "started_at": datetime.now(UTC).isoformat(),
                    "agent_id": "agent-1",
                },
            ),
        ]

        events2 = [
            WorkItemCreated(
                aggregate_id=stream2,
                payload={
                    "title": "Item 2",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            ),
        ]

        await store.append(stream1, events1)
        await store.append(stream2, events2)
        await store.save_snapshot(stream1, 2, {"data": "test"})

        stats = await store.get_statistics()

        assert stats["total_events"] == 3
        assert stats["total_streams"] == 2
        assert stats["total_snapshots"] == 1
        assert stats["events_per_stream"][stream1] == 2
        assert stats["events_per_stream"][stream2] == 1
        assert stats["events_per_type"]["WorkItemCreated"] == 2
        assert stats["events_per_type"]["WorkItemStarted"] == 1
        assert stats["unique_event_types"] == 2

    async def test_clear(self, store):
        """Test clearing all events and streams."""
        stream_id = "work-item-123"

        events = [
            WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": "Test",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            )
        ]

        await store.append(stream_id, events)
        await store.save_snapshot(stream_id, 1, {"data": "test"})

        assert store.get_total_event_count() == 1
        assert store.get_stream_count() == 1

        store.clear()

        assert store.get_total_event_count() == 0
        assert store.get_stream_count() == 0
        assert await store.get_latest_snapshot(stream_id) is None

    async def test_concurrent_append_operations(self, store):
        """Test concurrent append operations to different streams."""
        stream_ids = [f"work-item-{i}" for i in range(5)]

        tasks = []
        for stream_id in stream_ids:
            event = WorkItemCreated(
                aggregate_id=stream_id,
                payload={
                    "title": f"Item {stream_id}",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
            )
            tasks.append(store.append(stream_id, [event]))

        await asyncio.gather(*tasks)

        # All streams should be created
        stream_ids_created = await store.get_all_stream_ids()
        assert len(stream_ids_created) == 5
        assert set(stream_ids_created) == set(stream_ids)

    async def test_thread_safety_version_conflicts(self, store):
        """Test version conflicts are detected in concurrent scenarios."""
        stream_id = "work-item-123"

        # Initialize stream
        initial_event = WorkItemCreated(
            aggregate_id=stream_id,
            payload={
                "title": "Initial",
                "description": "Test",
                "project_id": "proj-1",
                "labels": [],
                "priority": 1,
            },
        )
        await store.append(stream_id, [initial_event])

        # Try concurrent appends with same expected version
        event1 = WorkItemStarted(
            aggregate_id=stream_id,
            payload={
                "started_at": datetime.now(UTC).isoformat(),
                "agent_id": "agent-1",
            },
        )

        event2 = WorkItemCompleted(
            aggregate_id=stream_id,
            payload={
                "completed_at": datetime.now(UTC).isoformat(),
                "agent_id": "agent-1",
            },
        )

        # Both try to append at version 1 - first succeeds, second should fail
        await store.append(stream_id, [event1], expected_version=1)

        with pytest.raises(ConcurrencyConflictError):
            await store.append(stream_id, [event2], expected_version=1)

    async def test_multiple_correlation_groups(self, store):
        """Test tracking multiple correlation groups."""
        corr_id_1 = uuid4()
        corr_id_2 = uuid4()

        # Create events with first correlation ID
        events_1 = [
            WorkItemCreated(
                aggregate_id="work-item-1",
                payload={
                    "title": "Item 1",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
                correlation_id=corr_id_1,
            ),
            WorkItemStarted(
                aggregate_id="work-item-1",
                payload={
                    "started_at": datetime.now(UTC).isoformat(),
                    "agent_id": "agent-1",
                },
                correlation_id=corr_id_1,
            ),
        ]

        # Create events with second correlation ID
        events_2 = [
            WorkItemCreated(
                aggregate_id="work-item-2",
                payload={
                    "title": "Item 2",
                    "description": "Test",
                    "project_id": "proj-1",
                    "labels": [],
                    "priority": 1,
                },
                correlation_id=corr_id_2,
            ),
        ]

        await store.append("work-item-1", events_1)
        await store.append("work-item-2", events_2)

        # Get events for each correlation group
        group_1 = await store.get_events_by_correlation_id(str(corr_id_1))
        group_2 = await store.get_events_by_correlation_id(str(corr_id_2))

        assert len(group_1) == 2
        assert len(group_2) == 1
        assert all(e.correlation_id == corr_id_1 for e in group_1)
        assert all(e.correlation_id == corr_id_2 for e in group_2)


@pytest.mark.asyncio
class TestBackpressureMechanism:
    """Tests for event processing backpressure latency."""

    @pytest.fixture
    def sample_event(self):
        """Create a sample event."""
        return WorkItemCreated(
            aggregate_id="work-item-123",
            payload={
                "title": "Test Work Item",
                "description": "Test description",
                "project_id": "project-1",
                "labels": ["bug"],
                "priority": 1,
            },
        )

    async def test_apply_event_processing_latency_no_config(self):
        """Test that no latency is applied when config is None."""
        store = InMemoryEventStore(config=None)

        start = asyncio.get_event_loop().time()
        await store._apply_event_processing_latency(10)
        elapsed = asyncio.get_event_loop().time() - start

        # Should complete almost instantly (< 10ms)
        assert elapsed < 0.01

    async def test_apply_event_processing_latency_low_fidelity(self):
        """Test that LOW fidelity produces no delay."""
        config = MagicMock(spec=SimulationConfig)
        config.fidelity_level = FidelityLevel.LOW
        config.ms_per_event = 10.0
        config.event_handler_count = 1

        store = InMemoryEventStore(config=config)

        start = asyncio.get_event_loop().time()
        await store._apply_event_processing_latency(10)
        elapsed = asyncio.get_event_loop().time() - start

        # Should complete almost instantly (< 10ms)
        assert elapsed < 0.01

    async def test_apply_event_processing_latency_medium_fidelity_proportional(self):
        """Test that MEDIUM fidelity produces proportional delay (event_count * handler_count * ms_per_event)."""
        config = MagicMock(spec=SimulationConfig)
        config.fidelity_level = FidelityLevel.MEDIUM
        config.ms_per_event = 10.0  # 10ms per (event * handler)
        config.event_handler_count = 1  # 1 handler

        store = InMemoryEventStore(config=config)

        # 5 events * 1 handler * 10ms = 50ms expected
        start = asyncio.get_event_loop().time()
        await store._apply_event_processing_latency(5)
        elapsed = asyncio.get_event_loop().time() - start

        # Should be approximately 50ms (allow ±12ms tolerance for timing variance)
        assert 0.038 < elapsed < 0.062

    async def test_apply_event_processing_latency_high_fidelity_with_jitter(self):
        """Test that HIGH fidelity applies jitter to the delay."""
        config = MagicMock(spec=SimulationConfig)
        config.fidelity_level = FidelityLevel.HIGH
        config.ms_per_event = 10.0  # 10ms per (event * handler)
        config.event_handler_count = 1  # 1 handler

        store = InMemoryEventStore(config=config)

        # 5 events * 1 handler * 10ms = 50ms base, with ±20% jitter
        # Expected range: 40ms to 60ms (allow 2ms tolerance for timing variance)
        durations = []
        for _ in range(5):
            start = asyncio.get_event_loop().time()
            await store._apply_event_processing_latency(5)
            elapsed = asyncio.get_event_loop().time() - start
            durations.append(elapsed)

        # All durations should be in the jittered range (±2ms tolerance for system variance)
        for duration in durations:
            assert 0.038 < duration < 0.062

    async def test_apply_event_processing_latency_zero_events(self):
        """Test that zero event count produces no delay."""
        config = MagicMock(spec=SimulationConfig)
        config.fidelity_level = FidelityLevel.MEDIUM
        config.ms_per_event = 10.0
        config.event_handler_count = 1

        store = InMemoryEventStore(config=config)

        start = asyncio.get_event_loop().time()
        await store._apply_event_processing_latency(0)
        elapsed = asyncio.get_event_loop().time() - start

        # Should complete almost instantly (< 10ms)
        assert elapsed < 0.01

    async def test_apply_event_processing_latency_with_simulation_clock(self):
        """Test that latency uses SimulationClock when available."""
        config = MagicMock(spec=SimulationConfig)
        config.fidelity_level = FidelityLevel.MEDIUM
        config.ms_per_event = 10.0
        config.event_handler_count = 1

        # Mock clock that tracks sleep calls
        mock_clock = AsyncMock()
        store = InMemoryEventStore(config=config, clock=mock_clock)

        await store._apply_event_processing_latency(5)

        # Clock sleep should have been called with 0.05 seconds (5 events * 1 handler * 10ms)
        mock_clock.sleep.assert_called_once()
        call_arg = mock_clock.sleep.call_args[0][0]
        assert 0.04 < call_arg < 0.06  # Allow for jitter in MEDIUM fidelity

    async def test_append_incurs_backpressure_latency(self, sample_event):
        """Test that append() incurs backpressure latency proportional to event count and handler count."""
        config = MagicMock(spec=SimulationConfig)
        config.fidelity_level = FidelityLevel.MEDIUM
        config.ms_per_event = 10.0  # 10ms per (event * handler)
        config.event_handler_count = 1  # 1 handler

        store = InMemoryEventStore(config=config)

        # Append 10 events * 1 handler * 10ms = 100ms expected latency
        events = [sample_event for _ in range(10)]

        start = asyncio.get_event_loop().time()
        await store.append("work-item-123", events)
        elapsed = asyncio.get_event_loop().time() - start

        # Should incur latency (allow 80-120ms range for timing variance)
        assert 0.08 < elapsed < 0.12

    async def test_append_low_fidelity_no_backpressure(self, sample_event):
        """Test that append() with LOW fidelity produces no backpressure latency."""
        config = MagicMock(spec=SimulationConfig)
        config.fidelity_level = FidelityLevel.LOW
        config.ms_per_event = 10.0
        config.event_handler_count = 1

        store = InMemoryEventStore(config=config)

        # Append 10 events, expect no latency despite high ms_per_event
        events = [sample_event for _ in range(10)]

        start = asyncio.get_event_loop().time()
        await store.append("work-item-123", events)
        elapsed = asyncio.get_event_loop().time() - start

        # Should complete quickly (< 10ms)
        assert elapsed < 0.01

    async def test_backpressure_latency_scales_linearly(self, sample_event):
        """Test that backpressure latency scales linearly with event count and handler count."""
        config = MagicMock(spec=SimulationConfig)
        config.fidelity_level = FidelityLevel.MEDIUM
        config.ms_per_event = 5.0  # 5ms per (event * handler)
        config.event_handler_count = 1  # 1 handler

        store = InMemoryEventStore(config=config)

        # Measure latency for different event counts
        durations = {}
        for count in [5, 10, 20]:
            events = [sample_event for _ in range(count)]
            start = asyncio.get_event_loop().time()
            await store.append("stream-id", events)
            elapsed = asyncio.get_event_loop().time() - start
            durations[count] = elapsed

        # Verify approximately linear scaling with event count
        # 10 events * 1 handler should take ~2x as long as 5 events * 1 handler
        ratio_10_5 = durations[10] / durations[5]
        assert 1.8 < ratio_10_5 < 2.2

        # 20 events * 1 handler should take ~4x as long as 5 events * 1 handler
        ratio_20_5 = durations[20] / durations[5]
        assert 3.8 < ratio_20_5 < 4.2

    async def test_event_processing_latency_with_multiple_handlers(self, sample_event):
        """Test that latency scales with handler count per spec (US-3.3).

        Uses same proportional relationship as spec example (100 events * 5 handlers * 10ms = 5 seconds)
        but with smaller values (100 events * 5 handlers * 0.1ms = 50ms) to avoid slow test.
        """
        config = MagicMock(spec=SimulationConfig)
        config.fidelity_level = FidelityLevel.MEDIUM
        config.ms_per_event = 0.1  # 0.1ms per (event * handler)
        config.event_handler_count = 5  # 5 handlers

        store = InMemoryEventStore(config=config)

        # Append 100 events * 5 handlers * 0.1ms = 50ms expected latency
        # This validates the same formula as spec: event_count * handler_count * ms_per_event
        events = [sample_event for _ in range(100)]

        start = asyncio.get_event_loop().time()
        await store.append("work-item-spec-test", events)
        elapsed = asyncio.get_event_loop().time() - start

        # Should be approximately 50ms (allow 40-60ms range for timing variance)
        assert 0.040 < elapsed < 0.060

    async def test_event_processing_latency_handler_count_scaling(self, sample_event):
        """Test that doubling handler count doubles latency."""
        # Test with 1 handler
        config_1 = MagicMock(spec=SimulationConfig)
        config_1.fidelity_level = FidelityLevel.MEDIUM
        config_1.ms_per_event = 10.0
        config_1.event_handler_count = 1

        store_1 = InMemoryEventStore(config=config_1)

        events = [sample_event for _ in range(10)]

        start = asyncio.get_event_loop().time()
        await store_1.append("stream-1", events)
        elapsed_1 = asyncio.get_event_loop().time() - start

        # Test with 5 handlers
        config_5 = MagicMock(spec=SimulationConfig)
        config_5.fidelity_level = FidelityLevel.MEDIUM
        config_5.ms_per_event = 10.0
        config_5.event_handler_count = 5

        store_5 = InMemoryEventStore(config=config_5)

        start = asyncio.get_event_loop().time()
        await store_5.append("stream-5", events)
        elapsed_5 = asyncio.get_event_loop().time() - start

        # 5 handlers should take approximately 5x as long as 1 handler
        ratio = elapsed_5 / elapsed_1
        assert 4.5 < ratio < 5.5
