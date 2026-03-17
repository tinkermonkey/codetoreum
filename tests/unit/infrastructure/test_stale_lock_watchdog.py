"""Unit tests for StaleLockWatchdog."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codetoreum.adapters.secondary.in_memory_queue_lock_service import (
    InMemoryLockService,
)
from codetoreum.application.pipeline_lock_service import LockStatus
from codetoreum.domain.events.lock_events import LockStaleDetectedEvent
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.infrastructure.simulation.watchdogs import StaleLockWatchdog


@pytest.fixture
def simulation_clock():
    """Create a simulation clock."""
    return SimulationClock(speed_multiplier=100.0)


@pytest.fixture
def mock_event_emitter():
    """Create mock event emitter."""
    emitter = AsyncMock()
    emitter.emit = AsyncMock()
    return emitter


@pytest.fixture
def lock_service():
    """Create lock service with mock event bus."""
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock()
    return InMemoryLockService(event_bus=event_bus, stale_threshold_seconds=3600)


@pytest.fixture
def watchdog(lock_service, mock_event_emitter, simulation_clock):
    """Create watchdog instance."""
    return StaleLockWatchdog(
        lock_service=lock_service,
        event_emitter=mock_event_emitter,
        clock=simulation_clock,
        stale_threshold_seconds=3600,
        check_interval=timedelta(seconds=60),
    )


class TestStaleLockWatchdogInitialization:
    """Test watchdog initialization."""

    def test_watchdog_creation(self, watchdog, lock_service, mock_event_emitter, simulation_clock):
        """Should create watchdog with all dependencies."""
        assert watchdog._lock_service is lock_service
        assert watchdog._event_emitter is mock_event_emitter
        assert watchdog._clock is simulation_clock
        assert watchdog._stale_threshold == timedelta(seconds=3600)
        assert watchdog._check_interval == timedelta(seconds=60)


class TestWatchdogStartAndScheduling:
    """Test watchdog start and callback scheduling."""

    def test_start_schedules_callback(self, watchdog, simulation_clock):
        """Should schedule first callback when started."""
        # Arrange
        callbacks_before = len(simulation_clock.get_scheduled_callbacks())

        # Act
        watchdog.start()

        # Assert
        callbacks_after = len(simulation_clock.get_scheduled_callbacks())
        assert callbacks_after == callbacks_before + 1

        # Verify the callback is scheduled at the right time
        scheduled = simulation_clock.get_scheduled_callbacks()
        assert len(scheduled) > 0
        scheduled_time, callback = scheduled[-1]
        expected_time = simulation_clock.now() + timedelta(seconds=60)
        assert scheduled_time == expected_time


class TestStaleDetection:
    """Test stale lock detection logic."""

    @pytest.mark.asyncio
    async def test_detects_stale_lock(self, lock_service, watchdog, mock_event_emitter):
        """Should detect a lock older than threshold."""
        # Arrange: Acquire lock
        await lock_service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Manually set lock acquired time to be older than threshold (1 hour before current time)
        old_time = watchdog._clock.now() - timedelta(seconds=3700)
        lock_service.set_lock_acquired_at("proj-1", "board-1", old_time)

        # Act
        await watchdog._check_stale_locks()

        # Assert: Event should be emitted
        mock_event_emitter.emit.assert_called_once()
        event = mock_event_emitter.emit.call_args[0][0]
        assert isinstance(event, LockStaleDetectedEvent)
        assert event.work_item_id == "item-1"
        assert event.project_id == "proj-1"
        assert event.board_id == "board-1"

    @pytest.mark.asyncio
    async def test_does_not_detect_fresh_lock(self, lock_service, watchdog, mock_event_emitter):
        """Should not detect a lock younger than threshold."""
        # Arrange: Acquire lock (automatically uses current time)
        await lock_service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Act
        await watchdog._check_stale_locks()

        # Assert: No event should be emitted
        mock_event_emitter.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_releases_stale_lock(self, lock_service, watchdog, mock_event_emitter):
        """Should force-release stale lock."""
        # Arrange: Acquire lock
        await lock_service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Make it stale
        old_time = watchdog._clock.now() - timedelta(seconds=3700)
        lock_service.set_lock_acquired_at("proj-1", "board-1", old_time)

        # Verify lock is held before
        state_before = await lock_service.get_queue_state("proj-1", "board-1")
        assert state_before.lock_holder == "item-1"

        # Act
        await watchdog._check_stale_locks()

        # Assert: Lock should be released
        state_after = await lock_service.get_queue_state("proj-1", "board-1")
        assert state_after.lock_holder is None

    @pytest.mark.asyncio
    async def test_multiple_stale_locks(self, lock_service, watchdog, mock_event_emitter):
        """Should detect multiple stale locks across different boards."""
        # Arrange: Acquire locks on multiple boards
        await lock_service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        await lock_service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-2",
            work_item_id="item-2",
            board_position=0,
        )

        # Make both stale
        old_time = watchdog._clock.now() - timedelta(seconds=3700)
        lock_service.set_lock_acquired_at("proj-1", "board-1", old_time)
        lock_service.set_lock_acquired_at("proj-1", "board-2", old_time)

        # Act
        await watchdog._check_stale_locks()

        # Assert: Two events should be emitted
        assert mock_event_emitter.emit.call_count == 2
        events = [call[0][0] for call in mock_event_emitter.emit.call_args_list]
        assert all(isinstance(e, LockStaleDetectedEvent) for e in events)

    @pytest.mark.asyncio
    async def test_ignores_no_locks(self, watchdog, mock_event_emitter):
        """Should handle case with no locks held."""
        # Act
        await watchdog._check_stale_locks()

        # Assert: No events emitted
        mock_event_emitter.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_clock_now_for_time(self, lock_service, watchdog):
        """Should use clock.now() exclusively, not datetime.now()."""
        # Arrange: Acquire lock
        await lock_service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Set lock to be old according to clock
        old_time = watchdog._clock.now() - timedelta(seconds=3700)
        lock_service.set_lock_acquired_at("proj-1", "board-1", old_time)

        # Mock datetime.now to ensure it's not used
        with patch("codetoreum.infrastructure.simulation.watchdogs.datetime") as mock_datetime:
            mock_datetime.UTC = UTC
            mock_datetime.now.side_effect = Exception("Should not call datetime.now()")

            # Act & Assert: Should not raise, proving we use clock.now()
            try:
                await watchdog._check_stale_locks()
            except Exception as e:
                if "Should not call datetime.now()" in str(e):
                    pytest.fail("Watchdog should use clock.now(), not datetime.now()")
                raise


class TestTickAndRescheduling:
    """Test the tick method and self-rescheduling behavior."""

    @pytest.mark.asyncio
    async def test_tick_reschedules_on_success(self, watchdog, simulation_clock):
        """Should reschedule even after successful check."""
        # Arrange
        callbacks_before = len(simulation_clock.get_scheduled_callbacks())

        # Act
        await watchdog._tick(simulation_clock.now())

        # Assert: Should have scheduled the next tick
        callbacks_after = len(simulation_clock.get_scheduled_callbacks())
        assert callbacks_after == callbacks_before + 1

    @pytest.mark.asyncio
    async def test_tick_reschedules_on_error(self, watchdog, simulation_clock, mock_event_emitter):
        """Should reschedule even if check fails."""
        # Arrange: Make the check fail
        mock_event_emitter.emit.side_effect = Exception("Test error")

        callbacks_before = len(simulation_clock.get_scheduled_callbacks())

        # Act: Should not raise despite the error
        await watchdog._tick(simulation_clock.now())

        # Assert: Should still have scheduled the next tick
        callbacks_after = len(simulation_clock.get_scheduled_callbacks())
        assert callbacks_after == callbacks_before + 1

    @pytest.mark.asyncio
    async def test_error_logged_with_exc_info(self, lock_service, watchdog, mock_event_emitter, caplog):
        """Should log errors with exc_info=True and continue."""
        # Arrange: Create a stale lock so that emit will be called and fail
        await lock_service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )
        old_time = watchdog._clock.now() - timedelta(seconds=3700)
        lock_service.set_lock_acquired_at("proj-1", "board-1", old_time)

        # Make the emit call fail
        mock_event_emitter.emit.side_effect = Exception("Test error")

        # Act: Should not raise despite the error
        await watchdog._tick(watchdog._clock.now())

        # Assert: Error should be logged
        assert "StaleLockWatchdog check failed" in caplog.text
        # Verify error was logged with exc_info
        assert "Traceback" in caplog.text  # Indicates exc_info was captured


class TestEventEmission:
    """Test domain event emission."""

    @pytest.mark.asyncio
    async def test_stale_event_has_correct_fields(self, lock_service, watchdog, mock_event_emitter):
        """Should emit LockStaleDetectedEvent with all required fields."""
        # Arrange: Acquire lock and make it stale
        await lock_service.try_acquire_lock(
            project_id="proj-123",
            board_id="board-456",
            work_item_id="item-789",
            board_position=0,
        )

        old_time = watchdog._clock.now() - timedelta(seconds=3700)
        lock_service.set_lock_acquired_at("proj-123", "board-456", old_time)

        # Act
        await watchdog._check_stale_locks()

        # Assert
        mock_event_emitter.emit.assert_called_once()
        event = mock_event_emitter.emit.call_args[0][0]

        assert event.type == "lock.stale_detected"
        assert event.project_id == "proj-123"
        assert event.board_id == "board-456"
        assert event.work_item_id == "item-789"
        assert event.lock_acquired_at is not None
        assert event.source == "stale_lock_watchdog"


class TestEndToEndWatchdogFlow:
    """Test complete watchdog flow."""

    @pytest.mark.asyncio
    async def test_complete_watchdog_cycle(self, lock_service, watchdog, mock_event_emitter, simulation_clock):
        """Test a complete watchdog cycle: start, acquire lock, detect stale, release."""
        # Arrange
        watchdog.start()

        # Acquire lock
        await lock_service.try_acquire_lock(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            board_position=0,
        )

        # Make it stale
        old_time = simulation_clock.now() - timedelta(seconds=3700)
        lock_service.set_lock_acquired_at("proj-1", "board-1", old_time)

        # Advance time to trigger watchdog tick
        await simulation_clock.advance(timedelta(seconds=60))

        # Assert: Lock should be released by watchdog
        state = await lock_service.get_queue_state("proj-1", "board-1")
        assert state.lock_holder is None

        # Assert: Event should have been emitted
        assert mock_event_emitter.emit.called
