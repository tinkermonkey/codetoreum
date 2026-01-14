"""Unit tests for InMemoryLockService event emission."""

import pytest
from unittest.mock import AsyncMock, call

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.application.pipeline_lock_service import LockStatus
from codetoreum.domain.events.lock_events import (
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
    WorkItemQueuedEvent,
)


@pytest.fixture
def mock_event_bus():
    """Create mock event bus."""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def lock_service_with_events(mock_event_bus):
    """Create lock service with event bus."""
    return InMemoryLockService(event_bus=mock_event_bus)


@pytest.fixture
def lock_service_without_events():
    """Create lock service without event bus."""
    return InMemoryLockService()


class TestLockEventEmission:
    """Test that lock service emits domain events."""

    @pytest.mark.asyncio
    async def test_emits_lock_acquired_event(
        self, lock_service_with_events, mock_event_bus
    ):
        """Should emit PipelineLockAcquiredEvent when lock is acquired."""
        # Act
        result = await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Assert
        assert result.status == LockStatus.ACQUIRED
        mock_event_bus.publish.assert_called_once()

        # Check the event
        event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(event, PipelineLockAcquiredEvent)
        assert event.work_item_id == "item-1"
        assert event.board_id == "board-1"
        assert event.queue_length_at_acquire == 0

    @pytest.mark.asyncio
    async def test_emits_queued_event(self, lock_service_with_events, mock_event_bus):
        """Should emit WorkItemQueuedEvent when item is queued."""
        # Acquire lock with first item
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Reset mock to track second call
        mock_event_bus.publish.reset_mock()

        # Try to acquire with second item (should be queued)
        result = await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )

        # Assert
        assert result.status == LockStatus.QUEUED
        mock_event_bus.publish.assert_called_once()

        # Check the event
        event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(event, WorkItemQueuedEvent)
        assert event.work_item_id == "item-2"
        assert event.board_id == "board-1"
        assert event.queue_position == 0  # First in queue

    @pytest.mark.asyncio
    async def test_emits_lock_released_event(
        self, lock_service_with_events, mock_event_bus
    ):
        """Should emit PipelineLockReleasedEvent when lock is released."""
        # Acquire lock
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Reset mock to track release
        mock_event_bus.publish.reset_mock()

        # Release lock
        result = await lock_service_with_events.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
        )

        # Assert
        assert result.next_work_item_id is None
        mock_event_bus.publish.assert_called_once()

        # Check the event
        event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(event, PipelineLockReleasedEvent)
        assert event.work_item_id == "item-1"
        assert event.board_id == "board-1"
        assert event.next_work_item_id is None

    @pytest.mark.asyncio
    async def test_emits_events_when_next_item_gets_lock(
        self, lock_service_with_events, mock_event_bus
    ):
        """Should emit both released and acquired events when next item gets lock."""
        # Acquire lock with first item
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Queue second item
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )

        # Reset mock to track release
        mock_event_bus.publish.reset_mock()

        # Release lock (should grant to item-2)
        result = await lock_service_with_events.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
        )

        # Assert
        assert result.next_work_item_id == "item-2"
        assert mock_event_bus.publish.call_count == 2

        # Check events
        calls = mock_event_bus.publish.call_args_list
        release_event = calls[0][0][0]
        acquire_event = calls[1][0][0]

        assert isinstance(release_event, PipelineLockReleasedEvent)
        assert release_event.work_item_id == "item-1"
        assert release_event.next_work_item_id == "item-2"

        assert isinstance(acquire_event, PipelineLockAcquiredEvent)
        assert acquire_event.work_item_id == "item-2"
        assert acquire_event.queue_length_at_acquire == 0  # Queue now empty

    @pytest.mark.asyncio
    async def test_no_events_without_event_bus(self, lock_service_without_events):
        """Should work normally without event bus (no events emitted)."""
        # Acquire lock
        result = await lock_service_without_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Assert - should work normally
        assert result.status == LockStatus.ACQUIRED

        # Release lock
        result = await lock_service_without_events.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
        )

        # Assert - should work normally
        assert result.released_work_item_id == "item-1"

    @pytest.mark.asyncio
    async def test_event_source_is_correct(
        self, lock_service_with_events, mock_event_bus
    ):
        """Should set correct source in emitted events."""
        # Acquire lock
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Check event source
        event = mock_event_bus.publish.call_args[0][0]
        assert event.source == "in_memory_lock_service"

    @pytest.mark.asyncio
    async def test_events_have_valid_timestamps(
        self, lock_service_with_events, mock_event_bus
    ):
        """Should set valid ISO timestamps in events."""
        # Acquire lock
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Check event timestamp
        event = mock_event_bus.publish.call_args[0][0]
        assert event.timestamp  # Not empty
        # Should be ISO format (basic validation)
        assert "T" in event.timestamp
        assert len(event.timestamp) > 19  # At least YYYY-MM-DDTHH:MM:SS

    @pytest.mark.asyncio
    async def test_events_include_project_id(
        self, lock_service_with_events, mock_event_bus
    ):
        """Should include project_id in all pipeline lock events."""
        # Acquire lock with first item
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Check acquired event has project_id
        acquired_event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(acquired_event, PipelineLockAcquiredEvent)
        assert acquired_event.project_id == "proj-1"

        # Queue second item
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )

        # Reset mock to track release
        mock_event_bus.publish.reset_mock()

        # Release lock
        await lock_service_with_events.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
        )

        # Check both released and acquired events have project_id
        calls = mock_event_bus.publish.call_args_list
        release_event = calls[0][0][0]
        acquire_event = calls[1][0][0]

        assert isinstance(release_event, PipelineLockReleasedEvent)
        assert release_event.project_id == "proj-1"

        assert isinstance(acquire_event, PipelineLockAcquiredEvent)
        assert acquire_event.project_id == "proj-1"

    @pytest.mark.asyncio
    async def test_full_lock_lifecycle_events(
        self, lock_service_with_events, mock_event_bus
    ):
        """Test complete lock lifecycle with all event types."""
        # 1. First item acquires lock
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )
        assert mock_event_bus.publish.call_count == 1
        assert isinstance(
            mock_event_bus.publish.call_args[0][0], PipelineLockAcquiredEvent
        )

        # 2. Second item gets queued
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )
        assert mock_event_bus.publish.call_count == 2
        assert isinstance(
            mock_event_bus.publish.call_args[0][0], WorkItemQueuedEvent
        )

        # 3. Third item gets queued
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-3",
            board_position=2,
        )
        assert mock_event_bus.publish.call_count == 3

        # 4. First item releases (second gets lock)
        await lock_service_with_events.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
        )
        # Should emit release + acquire (for item-2)
        assert mock_event_bus.publish.call_count == 5

        # Verify last two events
        calls = mock_event_bus.publish.call_args_list
        assert isinstance(calls[-2][0][0], PipelineLockReleasedEvent)
        assert isinstance(calls[-1][0][0], PipelineLockAcquiredEvent)
        assert calls[-1][0][0].work_item_id == "item-2"
