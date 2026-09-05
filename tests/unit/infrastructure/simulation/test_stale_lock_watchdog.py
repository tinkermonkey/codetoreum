"""Unit tests for StaleLockWatchdog."""

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock

import pytest

from codetoreum.domain.events.lock_events import StaleLockDetectedEvent
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.infrastructure.simulation.watchdogs import StaleLockWatchdog
from codetoreum.ports.output.distributed_lock import (
    IDistributedLock,
    LockHolder,
    ReleaseReason,
    ReleaseResult,
)


@pytest.fixture
def simulation_clock():
    """Create a simulation clock."""
    return SimulationClock(speed_multiplier=100.0)


@pytest.fixture
def mock_event_emitter():
    """Create mock event emitter.

    Note: emit() is synchronous (returns None), so we use a regular MagicMock.
    """
    emitter = MagicMock()
    emitter.emit = MagicMock()
    return emitter


@pytest.fixture
def mock_lock_service():
    """Create mock distributed lock service."""
    service = AsyncMock(spec=IDistributedLock)
    service.get_all_holders = AsyncMock(return_value=[])
    service.release = AsyncMock()
    return service


@pytest.fixture
def watchdog(mock_lock_service, mock_event_emitter, simulation_clock):
    """Create watchdog instance."""
    return StaleLockWatchdog(
        lock_service=mock_lock_service,
        event_emitter=mock_event_emitter,
        clock=simulation_clock,
        stale_threshold_seconds=7200,
        check_interval=timedelta(seconds=60),
    )


class TestStaleLockWatchdogInitialization:
    """Test watchdog initialization."""

    def test_watchdog_creation(self, mock_lock_service, mock_event_emitter, simulation_clock):
        """Should create watchdog with all dependencies."""
        watchdog = StaleLockWatchdog(
            lock_service=mock_lock_service,
            event_emitter=mock_event_emitter,
            clock=simulation_clock,
            stale_threshold_seconds=7200,
            check_interval=timedelta(seconds=60),
        )
        assert watchdog._lock_service is mock_lock_service
        assert watchdog._event_emitter is mock_event_emitter
        assert watchdog._clock is simulation_clock
        assert watchdog._stale_threshold == timedelta(seconds=7200)
        assert watchdog._check_interval == timedelta(seconds=60)
        assert watchdog._recovered_locks == set()
        assert watchdog._stopped is False


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

    def test_stop_prevents_future_checks(self, watchdog):
        """Should prevent future checks when stopped."""
        # Act
        watchdog.stop()

        # Assert
        assert watchdog._stopped is True
        assert watchdog._recovered_locks == set()


class TestStaleLockDetection:
    """Test stale lock detection logic."""

    @pytest.mark.asyncio
    async def test_detects_stale_lock(self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock):
        """Should detect a lock older than stale threshold."""
        # Arrange: Create a stale lock (held for 3 hours)
        now = simulation_clock.now()
        acquired_at = now - timedelta(seconds=10800)  # 3 hours

        holder = LockHolder(
            lock_key="proj-1:board-1",
            holder_id="item-1",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [holder]
        mock_lock_service.release.return_value = ReleaseResult(
            released=True,
            reason=None,
            lock_key="proj-1:board-1",
        )

        # Act
        await watchdog._check_stale_locks()

        # Assert: Event should be emitted
        mock_event_emitter.emit.assert_called_once()
        event = mock_event_emitter.emit.call_args[0][0]
        assert isinstance(event, StaleLockDetectedEvent)
        assert event.project_id == "proj-1"
        assert event.board_id == "board-1"
        assert event.work_item_id == "item-1"

    @pytest.mark.asyncio
    async def test_does_not_detect_fresh_lock(self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock):
        """Should not detect a lock within stale threshold."""
        # Arrange: Create a fresh lock (held for 30 minutes)
        now = simulation_clock.now()
        acquired_at = now - timedelta(seconds=1800)  # 30 minutes

        holder = LockHolder(
            lock_key="proj-1:board-1",
            holder_id="item-1",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [holder]

        # Act
        await watchdog._check_stale_locks()

        # Assert: No event should be emitted
        mock_event_emitter.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_already_recovered_locks(
        self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock
    ):
        """Should not emit duplicate events for already-recovered locks."""
        # Arrange
        now = simulation_clock.now()
        acquired_at = now - timedelta(seconds=10800)  # 3 hours
        lock_key = "proj-1:board-1"

        holder = LockHolder(
            lock_key=lock_key,
            holder_id="item-1",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [holder]

        # Mark as already recovered
        watchdog._recovered_locks.add(lock_key)

        # Act
        await watchdog._check_stale_locks()

        # Assert: No new event should be emitted
        mock_event_emitter.emit.assert_not_called()
        mock_lock_service.release.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_no_locks(self, mock_lock_service, watchdog, mock_event_emitter):
        """Should handle case with no held locks."""
        # Arrange
        mock_lock_service.get_all_holders.return_value = []

        # Act
        await watchdog._check_stale_locks()

        # Assert: No events emitted
        mock_event_emitter.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_clock_now_for_time(self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock):
        """Should use clock.now() exclusively for time comparisons."""
        # Arrange
        now = simulation_clock.now()
        acquired_at = now - timedelta(seconds=10800)  # 3 hours

        holder = LockHolder(
            lock_key="proj-1:board-1",
            holder_id="item-1",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [holder]
        mock_lock_service.release.return_value = ReleaseResult(
            released=True,
            reason=None,
            lock_key="proj-1:board-1",
        )

        # Act & Assert: Should complete without error
        # The test passes if no AttributeError is raised from wrong clock access
        await watchdog._check_stale_locks()
        mock_event_emitter.emit.assert_called_once()


class TestLockRelease:
    """Test lock release behavior."""

    @pytest.mark.asyncio
    async def test_calls_release_with_correct_arguments(
        self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock
    ):
        """Should call release() with lock_key and holder_id."""
        # Arrange
        now = simulation_clock.now()
        acquired_at = now - timedelta(seconds=10800)

        holder = LockHolder(
            lock_key="proj-1:board-1",
            holder_id="item-1",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [holder]
        mock_lock_service.release.return_value = ReleaseResult(
            released=True,
            reason=None,
            lock_key="proj-1:board-1",
        )

        # Act
        await watchdog._check_stale_locks()

        # Assert
        mock_lock_service.release.assert_called_once_with("proj-1:board-1", "item-1")

    @pytest.mark.asyncio
    async def test_marks_lock_as_recovered_on_successful_release(
        self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock
    ):
        """Should add lock to _recovered_locks after successful release."""
        # Arrange
        now = simulation_clock.now()
        acquired_at = now - timedelta(seconds=10800)
        lock_key = "proj-1:board-1"

        holder = LockHolder(
            lock_key=lock_key,
            holder_id="item-1",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [holder]
        mock_lock_service.release.return_value = ReleaseResult(
            released=True,
            reason=None,
            lock_key=lock_key,
        )

        # Act
        await watchdog._check_stale_locks()

        # Assert
        assert lock_key in watchdog._recovered_locks

    @pytest.mark.asyncio
    async def test_does_not_mark_lock_as_recovered_on_failed_release(
        self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock
    ):
        """Should not mark lock as recovered if release fails."""
        # Arrange
        now = simulation_clock.now()
        acquired_at = now - timedelta(seconds=10800)
        lock_key = "proj-1:board-1"

        holder = LockHolder(
            lock_key=lock_key,
            holder_id="item-1",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [holder]
        mock_lock_service.release.return_value = ReleaseResult(
            released=False,
            reason=ReleaseReason.HELD_BY_OTHER,
            lock_key=lock_key,
        )

        # Act
        await watchdog._check_stale_locks()

        # Assert
        assert lock_key not in watchdog._recovered_locks
        # But event should still be emitted
        mock_event_emitter.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_emits_event_even_if_release_fails(
        self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock
    ):
        """Should emit event even if release fails (non-blocking)."""
        # Arrange
        now = simulation_clock.now()
        acquired_at = now - timedelta(seconds=10800)

        holder = LockHolder(
            lock_key="proj-1:board-1",
            holder_id="item-1",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [holder]
        mock_lock_service.release.side_effect = Exception("Transient error")

        # Act
        await watchdog._check_stale_locks()

        # Assert: Event should still be emitted despite release failure
        mock_event_emitter.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_multiple_stale_locks(
        self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock
    ):
        """Should detect and release multiple stale locks."""
        # Arrange
        now = simulation_clock.now()
        acquired_at = now - timedelta(seconds=10800)

        holder1 = LockHolder(
            lock_key="proj-1:board-1",
            holder_id="item-1",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        holder2 = LockHolder(
            lock_key="proj-2:board-2",
            holder_id="item-2",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [holder1, holder2]
        mock_lock_service.release.return_value = ReleaseResult(
            released=True,
            reason=None,
            lock_key="",
        )

        # Act
        await watchdog._check_stale_locks()

        # Assert: Two events should be emitted
        assert mock_event_emitter.emit.call_count == 2
        events = [call[0][0] for call in mock_event_emitter.emit.call_args_list]
        assert all(isinstance(e, StaleLockDetectedEvent) for e in events)

    @pytest.mark.asyncio
    async def test_mixed_stale_and_fresh_locks(
        self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock
    ):
        """Should detect only stale locks, ignoring fresh ones."""
        # Arrange
        now = simulation_clock.now()
        stale_acquired_at = now - timedelta(seconds=10800)  # 3 hours
        fresh_acquired_at = now - timedelta(seconds=1800)  # 30 minutes

        stale_holder = LockHolder(
            lock_key="proj-1:board-1",
            holder_id="item-1",
            acquired_at=stale_acquired_at,
            ttl_seconds=7200,
            expires_at=stale_acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        fresh_holder = LockHolder(
            lock_key="proj-2:board-2",
            holder_id="item-2",
            acquired_at=fresh_acquired_at,
            ttl_seconds=7200,
            expires_at=fresh_acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [stale_holder, fresh_holder]
        mock_lock_service.release.return_value = ReleaseResult(
            released=True,
            reason=None,
            lock_key="proj-1:board-1",
        )

        # Act
        await watchdog._check_stale_locks()

        # Assert: Only one event should be emitted (for the stale lock)
        mock_event_emitter.emit.assert_called_once()
        event = mock_event_emitter.emit.call_args[0][0]
        assert event.project_id == "proj-1"
        assert event.board_id == "board-1"


class TestEventEmission:
    """Test domain event emission."""

    @pytest.mark.asyncio
    async def test_stale_lock_event_has_correct_fields(
        self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock
    ):
        """Should emit StaleLockDetectedEvent with all required fields."""
        # Arrange
        now = simulation_clock.now()
        acquired_at = now - timedelta(seconds=10800)

        holder = LockHolder(
            lock_key="proj-123:board-456",
            holder_id="item-789",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [holder]
        mock_lock_service.release.return_value = ReleaseResult(
            released=True,
            reason=None,
            lock_key="proj-123:board-456",
        )

        # Act
        await watchdog._check_stale_locks()

        # Assert
        mock_event_emitter.emit.assert_called_once()
        event = mock_event_emitter.emit.call_args[0][0]

        assert event.type == "lock.stale_detected"
        assert event.project_id == "proj-123"
        assert event.board_id == "board-456"
        assert event.work_item_id == "item-789"
        assert event.source == "stale_lock_watchdog"
        assert event.lock_acquired_at == acquired_at.isoformat()


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
    async def test_tick_reschedules_on_error(self, watchdog, simulation_clock, mock_lock_service):
        """Should reschedule even if check fails."""
        # Arrange: Make the check fail
        mock_lock_service.get_all_holders.side_effect = Exception("Test error")

        callbacks_before = len(simulation_clock.get_scheduled_callbacks())

        # Act: Should not raise despite the error
        await watchdog._tick(simulation_clock.now())

        # Assert: Should still have scheduled the next tick
        callbacks_after = len(simulation_clock.get_scheduled_callbacks())
        assert callbacks_after == callbacks_before + 1

    @pytest.mark.asyncio
    async def test_does_not_tick_when_stopped(self, watchdog, simulation_clock):
        """Should not perform check or reschedule when stopped."""
        # Arrange
        watchdog.stop()
        callbacks_before = len(simulation_clock.get_scheduled_callbacks())

        # Act
        await watchdog._tick(simulation_clock.now())

        # Assert: Should not have scheduled anything
        callbacks_after = len(simulation_clock.get_scheduled_callbacks())
        assert callbacks_after == callbacks_before

    @pytest.mark.asyncio
    async def test_error_logged_with_exc_info(self, watchdog, mock_lock_service, caplog, simulation_clock):
        """Should log errors with exc_info=True and continue."""
        # Arrange: Make the check fail
        mock_lock_service.get_all_holders.side_effect = Exception("Test error")

        # Act: Should not raise despite the error
        await watchdog._tick(simulation_clock.now())

        # Assert: Error should be logged
        assert "StaleLockWatchdog check failed" in caplog.text


class TestLockAcquiredEventHandler:
    """Test on_lock_acquired event handler for deduplication."""

    def test_clears_dedup_tracking_on_lock_acquired(self, watchdog):
        """Should clear deduplication tracking when lock is re-acquired."""
        # Arrange
        lock_key = "proj-1:board-1"
        watchdog._recovered_locks.add(lock_key)

        # Create a mock event with project_id and board_id
        event = MagicMock()
        event.project_id = "proj-1"
        event.board_id = "board-1"

        # Act
        watchdog.on_lock_acquired(event)

        # Assert
        assert lock_key not in watchdog._recovered_locks

    def test_ignores_missing_event_attributes(self, watchdog):
        """Should handle events with missing attributes gracefully."""
        # Arrange
        event = MagicMock()
        # Don't set project_id or board_id

        # Act & Assert: Should not raise
        watchdog.on_lock_acquired(event)

    def test_handles_event_processing_errors(self, watchdog):
        """Should handle unexpected errors during event processing."""
        # Arrange
        event = MagicMock()
        event.project_id = None
        event.board_id = None

        # Act & Assert: Should not raise
        watchdog.on_lock_acquired(event)


class TestEndToEndWatchdogFlow:
    """Test complete watchdog flow."""

    @pytest.mark.asyncio
    async def test_complete_watchdog_cycle(
        self, mock_lock_service, watchdog, mock_event_emitter, simulation_clock
    ):
        """Test a complete watchdog cycle: start, detect stale lock, release."""
        # Arrange
        watchdog.start()

        now = simulation_clock.now()
        acquired_at = now - timedelta(seconds=10800)

        holder = LockHolder(
            lock_key="proj-1:board-1",
            holder_id="item-1",
            acquired_at=acquired_at,
            ttl_seconds=7200,
            expires_at=acquired_at + timedelta(seconds=7200),
            holder_metadata=MappingProxyType({}),
        )
        mock_lock_service.get_all_holders.return_value = [holder]
        mock_lock_service.release.return_value = ReleaseResult(
            released=True,
            reason=None,
            lock_key="proj-1:board-1",
        )

        # Advance time to trigger watchdog tick
        await simulation_clock.advance(timedelta(seconds=60))

        # Assert: Event should have been emitted and lock released
        assert mock_event_emitter.emit.called
        assert mock_lock_service.release.called
        assert "proj-1:board-1" in watchdog._recovered_locks
