"""Unit tests for EventStorePoller."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.domain.events import WorkItemColumnChangedEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.event_store_poller import EventStorePoller


@pytest.fixture
def mock_event_store():
    """Create a mock event store."""
    store = AsyncMock()
    store.get_events_since = AsyncMock(return_value=[])
    return store


@pytest.fixture
def event_bus():
    """Create a real event bus."""
    return EventBus()


@pytest.fixture
def poller(mock_event_store, event_bus):
    """Create an event store poller."""
    return EventStorePoller(
        event_store=mock_event_store,
        event_bus=event_bus,
        poll_interval_seconds=0.1,  # Fast polling for tests
    )


@pytest.mark.asyncio
async def test_poller_starts_and_stops(poller):
    """Test that poller can start and stop gracefully."""
    assert not poller._running

    await poller.start()
    assert poller._running

    await asyncio.sleep(0.05)  # Let it run briefly

    await poller.stop()
    assert not poller._running


@pytest.mark.asyncio
async def test_poller_raises_if_already_running(poller):
    """Test that poller raises if trying to start while already running."""
    await poller.start()

    with pytest.raises(RuntimeError, match="already running"):
        await poller.start()

    await poller.stop()


@pytest.mark.asyncio
async def test_poller_polls_event_store(mock_event_store, event_bus, poller):
    """Test that poller queries the event store."""
    # Set up mock to return one event
    now = datetime.now(UTC)
    event = WorkItemColumnChangedEvent(
        type="workitem.column_changed",
        timestamp=now.isoformat(),
        source="test",
        work_item_id="test-1",
        project_id="test-proj",
        board_id="test-board",
        from_column="Backlog",
        to_column="In Progress",
        moved_by="test_user",
    )
    mock_event_store.get_events_since = AsyncMock(return_value=[event])

    await poller.start()
    await asyncio.sleep(0.15)  # Wait for poll to complete
    await poller.stop()

    # Verify event store was queried
    assert mock_event_store.get_events_since.called


@pytest.mark.asyncio
async def test_poller_publishes_events_to_bus(mock_event_store, event_bus, poller):
    """Test that poller publishes events to the event bus."""
    # Track published events
    published_events = []

    async def capture_event(event):
        published_events.append(event)

    event_bus.subscribe(None, capture_event)

    # Set up mock to return one event
    now = datetime.now(UTC)
    event = WorkItemColumnChangedEvent(
        type="workitem.column_changed",
        timestamp=now.isoformat(),
        source="test",
        work_item_id="test-1",
        project_id="test-proj",
        board_id="test-board",
        from_column="Backlog",
        to_column="In Progress",
        moved_by="test_user",
    )
    mock_event_store.get_events_since = AsyncMock(return_value=[event])

    await poller.start()
    await asyncio.sleep(0.2)  # Wait for poll to complete
    await poller.stop()

    # Verify event was published to bus
    assert len(published_events) > 0
    assert published_events[0].event_type == "WorkItemColumnChangedEvent"


@pytest.mark.asyncio
async def test_poller_handles_empty_event_list(mock_event_store, event_bus, poller):
    """Test that poller handles empty event list gracefully."""
    mock_event_store.get_events_since = AsyncMock(return_value=[])

    await poller.start()
    await asyncio.sleep(0.15)
    await poller.stop()

    assert not poller._running


@pytest.mark.asyncio
async def test_poller_continues_on_error(mock_event_store, event_bus, poller):
    """Test that poller continues running even if event store query fails."""
    # First query fails, second query succeeds
    call_count = [0]

    async def side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("Event store error")
        return []

    mock_event_store.get_events_since = AsyncMock(side_effect=side_effect)

    await poller.start()
    await asyncio.sleep(0.25)  # Wait for multiple polls
    await poller.stop()

    # Verify poller called get_events_since multiple times despite first error
    assert call_count[0] >= 2


@pytest.mark.asyncio
async def test_poller_handles_publish_error_gracefully(mock_event_store, event_bus, poller):
    """Test that poller continues even if publishing an event fails."""
    # Set up mock to return one event
    now = datetime.now(UTC)
    event = WorkItemColumnChangedEvent(
        type="workitem.column_changed",
        timestamp=now.isoformat(),
        source="test",
        work_item_id="test-1",
        project_id="test-proj",
        board_id="test-board",
        from_column="Backlog",
        to_column="In Progress",
        moved_by="test_user",
    )
    mock_event_store.get_events_since = AsyncMock(return_value=[event])

    # Mock event bus to fail on publish
    original_publish = event_bus.publish

    async def failing_publish(*args, **kwargs):
        raise Exception("Publish error")

    event_bus.publish = failing_publish

    # This should not raise
    await poller.start()
    await asyncio.sleep(0.15)
    await poller.stop()

    # Restore original publish
    event_bus.publish = original_publish

    # Poller should have stopped gracefully
    assert not poller._running


@pytest.mark.asyncio
async def test_poller_updates_last_polled_timestamp(mock_event_store, event_bus, poller):
    """Test that poller updates the last polled timestamp."""
    initial_time = poller._last_polled_timestamp
    await asyncio.sleep(0.05)

    now = datetime.now(UTC)
    event = WorkItemColumnChangedEvent(
        type="workitem.column_changed",
        timestamp=now.isoformat(),
        source="test",
        work_item_id="test-1",
        project_id="test-proj",
        board_id="test-board",
        from_column="Backlog",
        to_column="In Progress",
        moved_by="test_user",
    )
    mock_event_store.get_events_since = AsyncMock(return_value=[event])

    await poller.start()
    await asyncio.sleep(0.15)
    await poller.stop()

    # Last polled timestamp should have been updated
    assert poller._last_polled_timestamp > initial_time
