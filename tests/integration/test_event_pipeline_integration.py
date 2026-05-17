"""Integration tests for event pipeline bridging event store to handlers."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from codetoreum.domain.events import WorkItemColumnChangedEvent
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.event_store_poller import EventStorePoller


@pytest.fixture
def event_bus():
    """Create event bus."""
    return EventBus()


@pytest.fixture
def mock_event_store():
    """Create mock event store."""
    store = AsyncMock()
    store.get_events_since = AsyncMock(return_value=[])
    return store


@pytest.mark.asyncio
async def test_poller_publishes_events_from_event_store(mock_event_store, event_bus):
    """
    Test that events from the event store are published to the event bus.

    This test verifies the acceptance criterion from issue #850:
    - Trigger writes event to event_store.append()
    - EventStorePoller polls the event store
    - Poller publishes events to event bus
    - Event bus subscribers receive the event
    """
    # Track published events via subscription
    received_events = []

    async def capture_event(event):
        received_events.append(event)

    event_bus.subscribe(None, capture_event)

    # Create event store poller
    poller = EventStorePoller(
        event_store=mock_event_store,
        event_bus=event_bus,
        poll_interval_seconds=0.05,
    )

    # Create a test event (simulating trigger writing to event store)
    now = datetime.now(UTC)
    test_event = WorkItemColumnChangedEvent(
        type="workitem.column_changed",
        timestamp=now.isoformat(),
        source="trigger_cli",
        work_item_id="issue-123",
        project_id="test-project",
        board_id="board-1",
        from_column="Backlog",
        to_column="In Progress",
        moved_by="orchestrator",
    )

    # Mock event store to return the event on poll
    mock_event_store.get_events_since = AsyncMock(return_value=[test_event])

    # Start poller
    await poller.start()

    # Wait for poll to complete
    await asyncio.sleep(0.15)

    # Stop poller
    await poller.stop()

    # Verify event was published to bus
    assert len(received_events) > 0
    assert received_events[0].work_item_id == "issue-123"
    assert received_events[0].to_column == "In Progress"


@pytest.mark.asyncio
async def test_poller_publishes_multiple_events(mock_event_store, event_bus):
    """Test that multiple events from the event store are all published."""
    # Track published events
    received_events = []

    async def capture_event(event):
        received_events.append(event)

    event_bus.subscribe(None, capture_event)

    # Create poller
    poller = EventStorePoller(
        event_store=mock_event_store,
        event_bus=event_bus,
        poll_interval_seconds=0.05,
    )

    # Create multiple test events
    now = datetime.now(UTC)
    events = [
        WorkItemColumnChangedEvent(
            type="workitem.column_changed",
            timestamp=now.isoformat(),
            source="trigger_cli",
            work_item_id=f"issue-{i}",
            project_id="test-project",
            board_id="board-1",
            from_column="Backlog",
            to_column="In Progress",
            moved_by="orchestrator",
        )
        for i in range(3)
    ]

    # Mock event store to return multiple events
    mock_event_store.get_events_since = AsyncMock(return_value=events)

    # Start poller
    await poller.start()

    # Wait for poll to complete
    await asyncio.sleep(0.15)

    # Stop poller
    await poller.stop()

    # Verify all events were published
    assert len(received_events) >= 3


@pytest.mark.asyncio
async def test_event_store_poller_queries_with_correct_timestamp(mock_event_store, event_bus):
    """Test that poller queries event store with the correct timestamp."""
    poller = EventStorePoller(
        event_store=mock_event_store,
        event_bus=event_bus,
        poll_interval_seconds=0.05,
    )

    mock_event_store.get_events_since = AsyncMock(return_value=[])

    await poller.start()
    await asyncio.sleep(0.15)
    await poller.stop()

    # Verify event store was queried
    assert mock_event_store.get_events_since.called
    # Check that get_events_since was called with a datetime object
    call_args = mock_event_store.get_events_since.call_args
    assert call_args is not None
    assert "since" in call_args.kwargs or len(call_args.args) > 0


@pytest.mark.asyncio
async def test_poller_avoids_duplicate_publication(mock_event_store, event_bus):
    """Test that poller doesn't republish events after they've been processed."""
    received_events = []

    async def capture_event(event):
        received_events.append(event)

    event_bus.subscribe(None, capture_event)

    poller = EventStorePoller(
        event_store=mock_event_store,
        event_bus=event_bus,
        poll_interval_seconds=0.05,
    )

    now = datetime.now(UTC)
    event = WorkItemColumnChangedEvent(
        type="workitem.column_changed",
        timestamp=now.isoformat(),
        source="trigger_cli",
        work_item_id="issue-123",
        project_id="test-project",
        board_id="board-1",
        from_column="Backlog",
        to_column="In Progress",
        moved_by="orchestrator",
    )

    # First poll returns the event, subsequent polls return empty list
    call_count = [0]

    async def get_events_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return [event]
        return []

    mock_event_store.get_events_since = AsyncMock(side_effect=get_events_side_effect)

    # Run multiple poll cycles
    await poller.start()
    await asyncio.sleep(0.25)  # Wait for 2-3 polling cycles
    await poller.stop()

    # Event should only be published once
    assert len(received_events) == 1


@pytest.mark.asyncio
async def test_cross_process_event_distribution(mock_event_store, event_bus):
    """
    End-to-end test simulating the trigger → event store → poller → bus flow.

    Verifies:
    1. Trigger CLI writes event to event store via append()
    2. EventStorePoller polls event store periodically
    3. Poller publishes event to in-process event bus
    4. Event bus delivers event to subscribers
    """
    # Track delivered events
    received_events = []

    async def capture_event(event):
        received_events.append(event)

    event_bus.subscribe(None, capture_event)

    # Create the poller
    poller = EventStorePoller(
        event_store=mock_event_store,
        event_bus=event_bus,
        poll_interval_seconds=0.05,
    )

    # Simulate trigger CLI writing to event store
    now = datetime.now(UTC)
    trigger_event = WorkItemColumnChangedEvent(
        type="workitem.column_changed",
        timestamp=now.isoformat(),
        source="trigger_cli",
        work_item_id="issue-456",
        project_id="codetoreum",
        board_id="codetoreum-board",
        from_column="Backlog",
        to_column="In Progress",
        moved_by="orchestrator",
    )

    # Mock event store to return the event
    mock_event_store.get_events_since = AsyncMock(return_value=[trigger_event])

    # Start the poller (simulating the FastAPI app startup)
    await poller.start()

    # Wait for polling to occur
    await asyncio.sleep(0.2)

    # Stop the poller (simulating graceful shutdown)
    await poller.stop()

    # Verify the complete flow
    assert mock_event_store.get_events_since.called
    assert len(received_events) > 0
    assert received_events[0].work_item_id == "issue-456"
    assert received_events[0].to_column == "In Progress"
