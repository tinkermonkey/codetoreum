"""Unit tests for InMemoryLockService event emission."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.application.pipeline_lock_service import LockStatus
from codetoreum.domain.events.lock_events import (
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
    StaleLockDetectedEvent,
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
    async def test_emits_lock_acquired_event(self, lock_service_with_events, mock_event_bus):
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
    async def test_emits_lock_released_event(self, lock_service_with_events, mock_event_bus):
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
    async def test_emits_events_when_next_item_gets_lock(self, lock_service_with_events, mock_event_bus):
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
    async def test_event_source_is_correct(self, lock_service_with_events, mock_event_bus):
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
    async def test_events_have_valid_timestamps(self, lock_service_with_events, mock_event_bus):
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
    async def test_events_include_project_id(self, lock_service_with_events, mock_event_bus):
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
    async def test_full_lock_lifecycle_events(self, lock_service_with_events, mock_event_bus):
        """Test complete lock lifecycle with all event types."""
        # 1. First item acquires lock
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )
        assert mock_event_bus.publish.call_count == 1
        assert isinstance(mock_event_bus.publish.call_args[0][0], PipelineLockAcquiredEvent)

        # 2. Second item gets queued
        await lock_service_with_events.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )
        assert mock_event_bus.publish.call_count == 2
        assert isinstance(mock_event_bus.publish.call_args[0][0], WorkItemQueuedEvent)

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
        service_custom = InMemoryLockService(event_bus=mock_event_bus, stale_threshold_seconds=3600)
        assert service_custom._stale_threshold_seconds == 3600

    @pytest.mark.asyncio
    async def test_lock_not_stale_just_below_threshold(self, lock_service_with_short_threshold, mock_event_bus):
        """Lock just below threshold (59s of 60s test threshold) should not be detected as stale."""
        # Acquire lock
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Set lock time to 59 seconds ago (below 60 second threshold)
        now = datetime.now(UTC)
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
    async def test_lock_is_stale_just_above_threshold(self, lock_service_with_short_threshold, mock_event_bus):
        """Lock just above threshold (2h01m) should be detected as stale."""
        # Acquire lock
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Set lock time to 61 seconds ago (above 60 second threshold)
        now = datetime.now(UTC)
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
        assert isinstance(stale_event, StaleLockDetectedEvent)
        assert stale_event.project_id == "proj-1"
        assert stale_event.board_id == "board-1"
        assert stale_event.work_item_id == "item-1"  # Original stale lock holder

        # Second event should be lock acquired
        acquire_event = mock_event_bus.publish.call_args_list[1][0][0]
        assert isinstance(acquire_event, PipelineLockAcquiredEvent)
        assert acquire_event.work_item_id == "item-2"  # New lock holder

    @pytest.mark.asyncio
    async def test_stale_lock_recovery_at_exact_threshold(self, lock_service_with_short_threshold, mock_event_bus):
        """Lock just below threshold boundary (59.5s of 60s test threshold) should not be stale."""
        # Acquire lock
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Set lock time to 59.5 seconds ago (clearly below 60 second threshold)
        now = datetime.now(UTC)
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
        """StaleLockDetectedEvent should contain lock_acquired_at timestamp."""
        # Acquire lock
        await lock_service_with_short_threshold.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Set specific lock time
        specific_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
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
        assert isinstance(stale_event, StaleLockDetectedEvent)
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
        now = datetime.now(UTC)
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
        new_time = datetime(2024, 12, 25, 10, 30, 0, tzinfo=UTC)
        lock_service_with_short_threshold.set_lock_acquired_at(
            project_id="proj-1", board_id="board-1", timestamp=new_time
        )

        # Verify by getting queue state
        state = await lock_service_with_short_threshold.get_queue_state(project_id="proj-1", board_id="board-1")
        assert state.lock_acquired_at == new_time

    @pytest.mark.asyncio
    async def test_set_lock_acquired_at_raises_when_no_lock(self, lock_service_with_short_threshold):
        """Test helper should raise ValueError when no lock exists."""
        new_time = datetime.now(UTC)

        with pytest.raises(ValueError, match="No lock exists"):
            lock_service_with_short_threshold.set_lock_acquired_at(
                project_id="proj-1",
                board_id="board-1",
                timestamp=new_time,
            )

    @pytest.mark.asyncio
    async def test_stale_recovery_with_queued_items(self, lock_service_with_short_threshold, mock_event_bus):
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
        now = datetime.now(UTC)
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
        state = await lock_service_with_short_threshold.get_queue_state(project_id="proj-1", board_id="board-1")
        assert state.lock_holder == "item-4"
        assert len(state.queue) == 2
        assert state.queue[0].work_item_id == "item-2"
        assert state.queue[1].work_item_id == "item-3"

    @pytest.mark.asyncio
    async def test_stale_lock_detected_without_event_bus(self, lock_service_with_short_threshold):
        """Stale lock recovery should work even when event_bus is None."""
        # Create service without event bus
        service_no_bus = InMemoryLockService(event_bus=None, stale_threshold_seconds=60)

        # Acquire lock
        await service_no_bus.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Age the lock to be stale
        now = datetime.now(UTC)
        old_time = now - timedelta(seconds=61)
        service_no_bus.set_lock_acquired_at(project_id="proj-1", board_id="board-1", timestamp=old_time)

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
        state = await service_no_bus.get_queue_state(project_id="proj-1", board_id="board-1")
        assert state.lock_holder == "item-2"


class TestInMemoryLockServiceBehavior:
    """Test behavioral characteristics of InMemoryLockService."""

    @pytest.mark.asyncio
    async def test_successful_lock_acquisition(self):
        """Should successfully acquire lock when not held."""
        service = InMemoryLockService()

        result = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        assert result.status == LockStatus.ACQUIRED
        assert result.work_item_id == "item-1"
        assert result.queue_position is None
        assert result.queue_length == 0

    @pytest.mark.asyncio
    async def test_lock_acquisition_when_already_held(self):
        """Should return ALREADY_HELD when same item tries to re-acquire."""
        service = InMemoryLockService()

        # First acquisition
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Re-acquisition attempt
        result = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        assert result.status == LockStatus.ALREADY_HELD
        assert result.work_item_id == "item-1"

    @pytest.mark.asyncio
    async def test_lock_contention_queues_item(self):
        """Should queue item when lock is already held by another."""
        service = InMemoryLockService()

        # Item 1 acquires lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Item 2 tries to acquire - should be queued
        result = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )

        assert result.status == LockStatus.QUEUED
        assert result.work_item_id == "item-2"
        assert result.queue_position == 0
        assert result.queue_length == 1

    @pytest.mark.asyncio
    async def test_lock_release_success(self):
        """Should successfully release lock held by item."""
        service = InMemoryLockService()

        # Acquire lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Release lock
        result = await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
        )

        assert result.released_work_item_id == "item-1"
        assert result.next_work_item_id is None
        assert result.queue_length_after_release == 0

    @pytest.mark.asyncio
    async def test_lock_release_with_queued_items(self):
        """Should grant lock to next queued item on release."""
        service = InMemoryLockService()

        # Item 1 acquires lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Items 2 and 3 get queued
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-3",
            board_position=2,
        )

        # Item 1 releases
        result = await service.release_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
        )

        # Item 2 should get lock
        assert result.next_work_item_id == "item-2"
        assert result.queue_length_after_release == 1

        # Verify new lock holder
        state = await service.get_queue_state(
            project_id="proj-1",
            board_id="board-1",
        )
        assert state.lock_holder == "item-2"
        assert len(state.queue) == 1
        assert state.queue[0].work_item_id == "item-3"

    @pytest.mark.asyncio
    async def test_lock_release_fails_for_non_holder(self):
        """Should raise ValueError when non-holder tries to release."""
        service = InMemoryLockService()

        # Item 1 acquires lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Item 2 tries to release (doesn't hold lock)
        with pytest.raises(ValueError, match="does not hold lock"):
            await service.release_lock(
                project_id="proj-1",
                board_id="board-1",
                work_item_id="item-2",
            )

    @pytest.mark.asyncio
    async def test_queue_ordering_by_board_position(self):
        """Queue should be ordered by board_position (lowest/topmost first)."""
        service = InMemoryLockService()

        # Item 1 acquires lock at position 0
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Items queue in non-sequential order
        # Item 3 at position 3
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-3",
            board_position=3,
        )

        # Item 2 at position 1 (should become first in queue)
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )

        # Item 4 at position 2
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-4",
            board_position=2,
        )

        # Get queue state
        state = await service.get_queue_state(
            project_id="proj-1",
            board_id="board-1",
        )

        # Queue should be ordered by position
        assert len(state.queue) == 3
        assert state.queue[0].work_item_id == "item-2"  # position 1 (first)
        assert state.queue[0].board_position == 1
        assert state.queue[1].work_item_id == "item-4"  # position 2 (second)
        assert state.queue[1].board_position == 2
        assert state.queue[2].work_item_id == "item-3"  # position 3 (third)
        assert state.queue[2].board_position == 3

    @pytest.mark.asyncio
    async def test_update_queue_positions_reorders_queue(self):
        """Should reorder queue when positions are updated."""
        service = InMemoryLockService()

        # Item 1 acquires lock
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Queue items 2, 3, 4 in order
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-3",
            board_position=2,
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-4",
            board_position=3,
        )

        # Update positions - item 4 moves to top of queue
        await service.update_queue_positions(
            project_id="proj-1",
            board_id="board-1",
            updated_positions={
                "item-4": 0,
                "item-2": 2,
                "item-3": 3,
            },
        )

        # Get queue state
        state = await service.get_queue_state(
            project_id="proj-1",
            board_id="board-1",
        )

        # Queue should be reordered
        assert state.queue[0].work_item_id == "item-4"  # Now position 0 (first)
        assert state.queue[1].work_item_id == "item-2"  # Now position 2
        assert state.queue[2].work_item_id == "item-3"  # Still position 3

    @pytest.mark.asyncio
    async def test_get_queue_state_returns_copy(self):
        """get_queue_state should return independent copy, not reference."""
        service = InMemoryLockService()

        # Acquire lock and queue items
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )
        await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-2",
            board_position=1,
        )

        # Get state and modify it
        state1 = await service.get_queue_state("proj-1", "board-1")
        original_length = len(state1.queue)

        # Try to modify returned state (should not affect internal state)
        state1.queue.clear()

        # Get state again
        state2 = await service.get_queue_state("proj-1", "board-1")

        # Internal state should be unchanged
        assert len(state2.queue) == original_length

    @pytest.mark.asyncio
    async def test_get_all_lock_states_returns_all_boards(self):
        """get_all_lock_states should return states for all boards."""
        service = InMemoryLockService()

        # Create locks on multiple boards
        await service.try_acquire_lock("proj-1", "board-1", "item-1", 0)
        await service.try_acquire_lock("proj-1", "board-2", "item-2", 0)
        await service.try_acquire_lock("proj-2", "board-1", "item-3", 0)

        # Get all states
        states = service.get_all_lock_states()

        # Should have 3 entries
        assert len(states) == 3
        assert "proj-1:board-1" in states
        assert "proj-1:board-2" in states
        assert "proj-2:board-1" in states

        # Verify each state
        assert states["proj-1:board-1"].lock_holder == "item-1"
        assert states["proj-1:board-2"].lock_holder == "item-2"
        assert states["proj-2:board-1"].lock_holder == "item-3"

    @pytest.mark.asyncio
    async def test_parallel_boards_independent_locks(self):
        """Locks on different boards should be independent."""
        service = InMemoryLockService()

        # Board 1: item-1 acquires lock
        result1 = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Board 2: item-2 should also acquire lock
        result2 = await service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-2",
            work_item_id="item-2",
            board_position=0,
        )

        # Both should have locks
        assert result1.status == LockStatus.ACQUIRED
        assert result2.status == LockStatus.ACQUIRED

    @pytest.mark.asyncio
    async def test_validation_rejects_empty_project_id(self):
        """Should raise ValueError for empty project_id."""
        service = InMemoryLockService()

        with pytest.raises(ValueError, match="project_id cannot be empty"):
            await service.try_acquire_lock("", "board-1", "item-1", 0)

    @pytest.mark.asyncio
    async def test_validation_rejects_empty_board_id(self):
        """Should raise ValueError for empty board_id."""
        service = InMemoryLockService()

        with pytest.raises(ValueError, match="board_id cannot be empty"):
            await service.try_acquire_lock("proj-1", "", "item-1", 0)

    @pytest.mark.asyncio
    async def test_validation_rejects_empty_work_item_id(self):
        """Should raise ValueError for empty work_item_id."""
        service = InMemoryLockService()

        with pytest.raises(ValueError, match="work_item_id cannot be empty"):
            await service.try_acquire_lock("proj-1", "board-1", "", 0)

    @pytest.mark.asyncio
    async def test_validation_rejects_negative_board_position(self):
        """Should raise ValueError for negative board_position."""
        service = InMemoryLockService()

        with pytest.raises(ValueError, match="board_position cannot be negative"):
            await service.try_acquire_lock("proj-1", "board-1", "item-1", -1)

    @pytest.mark.asyncio
    async def test_thread_safe_concurrent_acquisitions(self):
        """Lock service should be thread-safe for concurrent operations."""
        import asyncio

        service = InMemoryLockService()

        # Item 1 acquires lock
        await service.try_acquire_lock("proj-1", "board-1", "item-1", 0)

        # Simulate concurrent acquisition attempts from multiple tasks
        results = []

        async def acquire_lock(item_id, position):
            result = await service.try_acquire_lock("proj-1", "board-1", item_id, position)
            results.append((item_id, result.status))

        # Run 5 concurrent acquisition attempts
        await asyncio.gather(
            acquire_lock("item-2", 1),
            acquire_lock("item-3", 2),
            acquire_lock("item-4", 3),
            acquire_lock("item-5", 4),
            acquire_lock("item-6", 5),
        )

        # Should have 5 results
        assert len(results) == 5

        # All should be queued (not acquired)
        for item_id, status in results:
            assert status == LockStatus.QUEUED

        # Queue should have all 5 items
        state = await service.get_queue_state("proj-1", "board-1")
        assert len(state.queue) == 5


class TestInMemoryLockServiceInitialization:
    """Test InMemoryLockService initialization and parameter handling.

    These tests verify implementation-specific behavior such as parameter
    acceptance, default values, and initialization state.
    """

    def test_accepts_event_bus_parameter(self):
        """InMemoryLockService should accept optional event_bus parameter."""
        mock_bus = AsyncMock()
        service = InMemoryLockService(event_bus=mock_bus)
        assert service._event_bus is mock_bus

    def test_accepts_stale_threshold_parameter(self):
        """InMemoryLockService should accept optional stale_threshold_seconds parameter."""
        service = InMemoryLockService(stale_threshold_seconds=3600)
        assert service._stale_threshold_seconds == 3600

    def test_accepts_clock_parameter(self):
        """InMemoryLockService should accept optional clock parameter."""
        from unittest.mock import Mock

        mock_clock = Mock()
        service = InMemoryLockService(clock=mock_clock)
        assert service._clock is mock_clock

    def test_default_stale_threshold_is_2_hours(self):
        """InMemoryLockService should have 2-hour (7200 second) default stale threshold."""
        service = InMemoryLockService()
        assert service._stale_threshold_seconds == 7200

    @pytest.mark.asyncio
    async def test_can_initialize_with_all_parameters(self):
        """InMemoryLockService should initialize with all optional parameters together."""
        from unittest.mock import Mock

        mock_bus = AsyncMock()
        mock_clock = Mock()

        service = InMemoryLockService(
            event_bus=mock_bus,
            stale_threshold_seconds=1800,
            clock=mock_clock,
        )

        assert service._event_bus is mock_bus
        assert service._stale_threshold_seconds == 1800
        assert service._clock is mock_clock
