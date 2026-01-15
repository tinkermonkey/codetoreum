"""Unit tests for InMemoryLockService event emission."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, call

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.application.pipeline_lock_service import LockStatus
from codetoreum.domain.events.lock_events import (
    LockStaleDetectedEvent,
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


class TestStaleLockDetection:
    """Test stale lock detection and recovery."""

    @pytest.fixture
    def lock_service_with_short_threshold(self, mock_event_bus):
        """Create lock service with short stale threshold for testing."""
        return InMemoryLockService(event_bus=mock_event_bus, stale_threshold_seconds=60)

    @pytest.mark.asyncio
    async def test_stale_lock_threshold_parameter(self, mock_event_bus):
        """Should accept configurable stale_threshold_seconds parameter."""
        # Default threshold should be 2 hours (7200 seconds)
        service_default = InMemoryLockService(event_bus=mock_event_bus)
        assert service_default._stale_threshold_seconds == 7200

        # Custom threshold
        service_custom = InMemoryLockService(
            event_bus=mock_event_bus, stale_threshold_seconds=3600
        )
        assert service_custom._stale_threshold_seconds == 3600

    @pytest.mark.asyncio
    async def test_lock_not_stale_just_below_threshold(
        self, lock_service_with_short_threshold, mock_event_bus
    ):
        """Lock just below threshold (59s of 60s test threshold) should not be detected as stale."""
        # Acquire lock
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Set lock time to 59 seconds ago (below 60 second threshold)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(seconds=59)
        lock_service_with_short_threshold.set_lock_acquired_at(
            project_id="proj-1", board_id="board-1", timestamp=old_time
        )

        # Reset mock
        mock_event_bus.publish.reset_mock()

        # Try to acquire with different item - should NOT detect stale
        result = await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )

        # Should be queued, not stale recovery
        assert result.status == LockStatus.QUEUED
        # Should NOT emit stale detected event
        assert mock_event_bus.publish.call_count == 1
        event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(event, WorkItemQueuedEvent)

    @pytest.mark.asyncio
    async def test_lock_is_stale_just_above_threshold(
        self, lock_service_with_short_threshold, mock_event_bus
    ):
        """Lock just above threshold (2h01m) should be detected as stale."""
        # Acquire lock
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Set lock time to 61 seconds ago (above 60 second threshold)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(seconds=61)
        lock_service_with_short_threshold.set_lock_acquired_at(
            project_id="proj-1", board_id="board-1", timestamp=old_time
        )

        # Reset mock
        mock_event_bus.publish.reset_mock()

        # Try to acquire with different item - should detect stale
        result = await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )

        # Should acquire lock (stale recovery)
        assert result.status == LockStatus.ACQUIRED
        # Should emit two events: stale detected + lock acquired
        assert mock_event_bus.publish.call_count == 2

        # First event should be stale detected
        stale_event = mock_event_bus.publish.call_args_list[0][0][0]
        assert isinstance(stale_event, LockStaleDetectedEvent)
        assert stale_event.project_id == "proj-1"
        assert stale_event.board_id == "board-1"
        assert stale_event.work_item_id == "item-1"  # Original stale lock holder

        # Second event should be lock acquired
        acquire_event = mock_event_bus.publish.call_args_list[1][0][0]
        assert isinstance(acquire_event, PipelineLockAcquiredEvent)
        assert acquire_event.work_item_id == "item-2"  # New lock holder

    @pytest.mark.asyncio
    async def test_stale_lock_recovery_at_exact_threshold(
        self, lock_service_with_short_threshold, mock_event_bus
    ):
        """Lock just below threshold boundary (59.5s of 60s test threshold) should not be stale."""
        # Acquire lock
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Set lock time to 59.5 seconds ago (clearly below 60 second threshold)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(seconds=59.5)
        lock_service_with_short_threshold.set_lock_acquired_at(
            project_id="proj-1", board_id="board-1", timestamp=old_time
        )

        # Reset mock
        mock_event_bus.publish.reset_mock()

        # Try to acquire with different item - should NOT detect stale
        result = await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )

        # Should be queued, not stale recovery (lock age well below threshold)
        assert result.status == LockStatus.QUEUED

    @pytest.mark.asyncio
    async def test_stale_lock_detected_event_contains_lock_acquired_at(
        self, lock_service_with_short_threshold, mock_event_bus
    ):
        """LockStaleDetectedEvent should contain lock_acquired_at timestamp."""
        # Acquire lock
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Set specific lock time
        specific_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        lock_service_with_short_threshold.set_lock_acquired_at(
            project_id="proj-1", board_id="board-1", timestamp=specific_time
        )

        # Reset mock
        mock_event_bus.publish.reset_mock()

        # Trigger stale detection
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )

        # Check stale detected event
        stale_event = mock_event_bus.publish.call_args_list[0][0][0]
        assert isinstance(stale_event, LockStaleDetectedEvent)
        assert stale_event.lock_acquired_at == "2025-01-01T12:00:00+00:00"

    @pytest.mark.asyncio
    async def test_reentrant_acquisition_does_not_trigger_stale_detection(
        self, lock_service_with_short_threshold, mock_event_bus
    ):
        """Same work item re-acquiring lock should not trigger stale detection."""
        # Acquire lock with item-1
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Age the lock
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(seconds=61)
        lock_service_with_short_threshold.set_lock_acquired_at(
            project_id="proj-1", board_id="board-1", timestamp=old_time
        )

        # Reset mock
        mock_event_bus.publish.reset_mock()

        # Same item re-acquires lock - should return ALREADY_HELD
        result = await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Should be already held, not stale recovery
        assert result.status == LockStatus.ALREADY_HELD
        # No events should be emitted
        mock_event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_lock_acquired_at_test_helper_works(self, lock_service_with_short_threshold):
        """Test helper set_lock_acquired_at should update lock timestamp."""
        # Acquire lock
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Set specific timestamp
        new_time = datetime(2024, 12, 25, 10, 30, 0, tzinfo=timezone.utc)
        lock_service_with_short_threshold.set_lock_acquired_at(
            project_id="proj-1", board_id="board-1", timestamp=new_time
        )

        # Verify by getting queue state
        state = await lock_service_with_short_threshold.get_queue_state(
            project_id="proj-1", board_id="board-1"
        )
        assert state.lock_acquired_at == new_time

    @pytest.mark.asyncio
    async def test_set_lock_acquired_at_raises_when_no_lock(self, lock_service_with_short_threshold):
        """Test helper should raise ValueError when no lock exists."""
        new_time = datetime.now(timezone.utc)

        with pytest.raises(ValueError, match="No lock exists"):
            lock_service_with_short_threshold.set_lock_acquired_at(
                project_id="proj-1",
                board_id="board-1",
                timestamp=new_time,
            )

    @pytest.mark.asyncio
    async def test_stale_recovery_with_queued_items(
        self, lock_service_with_short_threshold, mock_event_bus
    ):
        """Stale recovery should work correctly even when queue has items."""
        # Acquire lock with item-1
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Queue items 2 and 3
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-3",
            board_position=2,
        )

        # Age the lock
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(seconds=61)
        lock_service_with_short_threshold.set_lock_acquired_at(
            project_id="proj-1", board_id="board-1", timestamp=old_time
        )

        # Reset mock
        mock_event_bus.publish.reset_mock()

        # Try to acquire with item-4 - should recover stale lock
        result = await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-4",
            board_position=3,
        )

        # Item-4 should get lock (stale recovery)
        assert result.status == LockStatus.ACQUIRED

        # Queue should still have items 2 and 3
        state = await lock_service_with_short_threshold.get_queue_state(
            project_id="proj-1", board_id="board-1"
        )
        assert state.lock_holder == "item-4"
        assert len(state.queue) == 2
        assert state.queue[0].work_item_id == "item-2"
        assert state.queue[1].work_item_id == "item-3"

    @pytest.mark.asyncio
    async def test_stale_lock_detected_without_event_bus(self, lock_service_with_short_threshold):
        """Stale lock recovery should work even when event_bus is None."""
        # Create service without event bus
        service_no_bus = InMemoryLockService(
            event_bus=None, stale_threshold_seconds=60
        )

        # Acquire lock
        await service_no_bus.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Age the lock to be stale
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(seconds=61)
        service_no_bus.set_lock_acquired_at(
            project_id="proj-1", board_id="board-1", timestamp=old_time
        )

        # Try to acquire with different item - should recover stale lock
        result = await service_no_bus.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )

        # Should acquire lock (stale recovery)
        assert result.status == LockStatus.ACQUIRED

        # Verify new lock holder
        state = await service_no_bus.get_queue_state(
            project_id="proj-1", board_id="board-1"
        )
        assert state.lock_holder == "item-2"
