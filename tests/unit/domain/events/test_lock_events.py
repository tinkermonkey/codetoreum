"""Unit tests for pipeline lock events."""

import pytest

from codetoreum.domain.events import (
    LockAcquiredEvent,
    LockReleasedEvent,
    StaleLockDetectedEvent,
    LockStuckEvent,
    now_iso,
)

# For immutability tests (lock events are already frozen dataclasses)
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    # Fallback for older Python versions
    FrozenInstanceError = AttributeError  # type: ignore


class TestLockAcquiredEvent:
    """Test LockAcquiredEvent."""

    def test_create_valid_event(self):
        """Test creating a valid lock acquired event."""
        event = LockAcquiredEvent(
            type="lock.acquired",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            acquisition_method="normal",
        )

        assert event.project_id == "proj-1"
        assert event.work_item_id == "123"
        assert event.acquisition_method == "normal"

    def test_lock_acquired_stale_recovery(self):
        """Test lock acquired via stale recovery."""
        event = LockAcquiredEvent(
            type="lock.acquired",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            acquisition_method="stale_recovery",
        )

        assert event.acquisition_method == "stale_recovery"

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id"):
            LockAcquiredEvent(
                type="lock.acquired",
                timestamp=now_iso(),
                source="github",
                project_id="",  # Empty
                board_id="board-1",
                work_item_id="123",
            )

    def test_missing_board_id(self):
        """Test that board_id is required."""
        with pytest.raises(ValueError, match="board_id"):
            LockAcquiredEvent(
                type="lock.acquired",
                timestamp=now_iso(),
                source="github",
                project_id="proj-1",
                board_id="",  # Empty
                work_item_id="123",
            )

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id"):
            LockAcquiredEvent(
                type="lock.acquired",
                timestamp=now_iso(),
                source="github",
                project_id="proj-1",
                board_id="board-1",
                work_item_id="",  # Empty
            )

    def test_lock_acquired_serialization(self):
        """Test lock acquired event serialization."""
        event = LockAcquiredEvent(
            type="lock.acquired",
            timestamp=now_iso(),
            source="github",
            correlation_id="corr-1",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            acquisition_method="normal",
        )

        d = event.to_dict()

        assert d["project_id"] == "proj-1"
        assert d["work_item_id"] == "123"
        assert d["acquisition_method"] == "normal"

    def test_lock_acquired_roundtrip(self):
        """Test lock acquired event roundtrip."""
        timestamp = now_iso()
        original = LockAcquiredEvent(
            type="lock.acquired",
            timestamp=timestamp,
            source="jira",
            project_id="proj-2",
            board_id="board-2",
            work_item_id="456",
            acquisition_method="stale_recovery",
        )

        d = original.to_dict()
        restored = LockAcquiredEvent.from_dict(d)

        assert restored.project_id == original.project_id
        assert restored.work_item_id == original.work_item_id
        assert restored.acquisition_method == original.acquisition_method


class TestLockReleasedEvent:
    """Test LockReleasedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid lock released event."""
        event = LockReleasedEvent(
            type="lock.released",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="completed",
            next_in_queue="124",
        )

        assert event.work_item_id == "123"
        assert event.reason == "completed"
        assert event.next_in_queue == "124"

    def test_lock_released_exit_column(self):
        """Test lock released due to column exit."""
        event = LockReleasedEvent(
            type="lock.released",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="exit_column",
        )

        assert event.reason == "exit_column"

    def test_lock_released_timeout(self):
        """Test lock released due to timeout."""
        event = LockReleasedEvent(
            type="lock.released",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="timeout",
        )

        assert event.reason == "timeout"

    def test_lock_released_manual(self):
        """Test lock released manually."""
        event = LockReleasedEvent(
            type="lock.released",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="manual",
        )

        assert event.reason == "manual"

    def test_lock_released_without_next(self):
        """Test lock released without next item in queue."""
        event = LockReleasedEvent(
            type="lock.released",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="completed",
        )

        assert event.next_in_queue is None

    def test_lock_released_serialization(self):
        """Test lock released event serialization."""
        event = LockReleasedEvent(
            type="lock.released",
            timestamp=now_iso(),
            source="github",
            correlation_id="corr-2",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="completed",
            next_in_queue="124",
        )

        d = event.to_dict()

        assert d["reason"] == "completed"
        assert d["next_in_queue"] == "124"

    def test_lock_released_roundtrip(self):
        """Test lock released event roundtrip."""
        timestamp = now_iso()
        original = LockReleasedEvent(
            type="lock.released",
            timestamp=timestamp,
            source="jira",
            project_id="proj-2",
            board_id="board-2",
            work_item_id="456",
            reason="timeout",
            next_in_queue="457",
        )

        d = original.to_dict()
        restored = LockReleasedEvent.from_dict(d)

        assert restored.work_item_id == original.work_item_id
        assert restored.reason == original.reason
        assert restored.next_in_queue == original.next_in_queue


class TestStaleLockDetectedEvent:
    """Test StaleLockDetectedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid stale lock detected event."""
        acquired_at = now_iso()
        event = StaleLockDetectedEvent(
            type="lock.stale_detected",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            lock_acquired_at=acquired_at,
        )

        assert event.work_item_id == "123"
        assert event.lock_acquired_at == acquired_at

    def test_missing_lock_acquired_at(self):
        """Test that lock_acquired_at is required."""
        with pytest.raises(ValueError, match="lock_acquired_at"):
            StaleLockDetectedEvent(
                type="lock.stale_detected",
                timestamp=now_iso(),
                source="github",
                project_id="proj-1",
                board_id="board-1",
                work_item_id="123",
                lock_acquired_at="",  # Empty
            )

    def test_stale_lock_serialization(self):
        """Test stale lock detected event serialization."""
        acquired_at = now_iso()
        event = StaleLockDetectedEvent(
            type="lock.stale_detected",
            timestamp=now_iso(),
            source="github",
            correlation_id="corr-3",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            lock_acquired_at=acquired_at,
        )

        d = event.to_dict()

        assert d["work_item_id"] == "123"
        assert d["lock_acquired_at"] == acquired_at

    def test_stale_lock_roundtrip(self):
        """Test stale lock detected event roundtrip."""
        timestamp = now_iso()
        acquired_at = "2024-01-08T10:00:00+00:00"
        original = StaleLockDetectedEvent(
            type="lock.stale_detected",
            timestamp=timestamp,
            source="jira",
            project_id="proj-2",
            board_id="board-2",
            work_item_id="456",
            lock_acquired_at=acquired_at,
        )

        d = original.to_dict()
        restored = StaleLockDetectedEvent.from_dict(d)

        assert restored.work_item_id == original.work_item_id
        assert restored.lock_acquired_at == original.lock_acquired_at


class TestLockAcquiredEventImmutability:
    """Test immutability of LockAcquiredEvent (frozen dataclass)."""

    def test_lock_acquired_event_is_frozen(self):
        """Test that LockAcquiredEvent is immutable (frozen dataclass)."""
        event = LockAcquiredEvent(
            type="lock.acquired",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            acquisition_method="normal",
        )

        # Verify the event is properly created
        assert event.project_id == "proj-1"
        assert event.work_item_id == "123"
        assert event.acquisition_method == "normal"

        # LockAcquiredEvent is a frozen dataclass, so attempting to modify
        # should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.project_id = "proj-2"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "456"  # type: ignore

    def test_lock_acquired_event_acquisition_method_immutable(self):
        """Test that acquisition_method field is immutable."""
        event = LockAcquiredEvent(
            type="lock.acquired",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            acquisition_method="stale_recovery",
        )

        assert event.acquisition_method == "stale_recovery"

        # Should raise FrozenInstanceError when attempting modification
        with pytest.raises(FrozenInstanceError):
            event.acquisition_method = "normal"  # type: ignore


class TestLockReleasedEventImmutability:
    """Test immutability of LockReleasedEvent (frozen dataclass)."""

    def test_lock_released_event_is_frozen(self):
        """Test that LockReleasedEvent is immutable (frozen dataclass)."""
        event = LockReleasedEvent(
            type="lock.released",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="completed",
            next_in_queue="124",
        )

        # Verify the event is properly created
        assert event.work_item_id == "123"
        assert event.reason == "completed"
        assert event.next_in_queue == "124"

        # LockReleasedEvent is a frozen dataclass, so attempting to modify
        # should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "456"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.reason = "timeout"  # type: ignore

    def test_lock_released_event_reason_immutable(self):
        """Test that reason field is immutable."""
        event = LockReleasedEvent(
            type="lock.released",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="completed",
        )

        assert event.reason == "completed"

        # Should raise FrozenInstanceError when attempting modification
        with pytest.raises(FrozenInstanceError):
            event.reason = "manual"  # type: ignore

    def test_lock_released_event_next_in_queue_immutable(self):
        """Test that next_in_queue field is immutable."""
        event = LockReleasedEvent(
            type="lock.released",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="completed",
            next_in_queue="124",
        )

        assert event.next_in_queue == "124"

        # Should raise FrozenInstanceError when attempting modification
        with pytest.raises(FrozenInstanceError):
            event.next_in_queue = "125"  # type: ignore


class TestStaleLockDetectedEventImmutability:
    """Test immutability of StaleLockDetectedEvent (frozen dataclass)."""

    def test_lock_stale_detected_event_is_frozen(self):
        """Test that StaleLockDetectedEvent is immutable (frozen dataclass)."""
        acquired_at = now_iso()
        event = StaleLockDetectedEvent(
            type="lock.stale_detected",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            lock_acquired_at=acquired_at,
        )

        # Verify the event is properly created
        assert event.work_item_id == "123"
        assert event.lock_acquired_at == acquired_at

        # StaleLockDetectedEvent is a frozen dataclass, so attempting to modify
        # should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "456"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.lock_acquired_at = "2024-01-01T00:00:00+00:00"  # type: ignore

    def test_lock_stale_detected_event_lock_acquired_at_immutable(self):
        """Test that lock_acquired_at field is immutable."""
        acquired_at = "2024-01-08T10:00:00+00:00"
        event = StaleLockDetectedEvent(
            type="lock.stale_detected",
            timestamp=now_iso(),
            source="github",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            lock_acquired_at=acquired_at,
        )

        assert event.lock_acquired_at == acquired_at

        # Should raise FrozenInstanceError when attempting modification
        with pytest.raises(FrozenInstanceError):
            event.lock_acquired_at = "2024-01-09T10:00:00+00:00"  # type: ignore


class TestLockStuckEvent:
    """Test LockStuckEvent."""

    def test_create_valid_event(self):
        """Test creating a valid lock stuck event."""
        event = LockStuckEvent(
            type="lock.stuck",
            timestamp=now_iso(),
            source="board_event_handler",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="Agent executor timed out",
        )

        assert event.project_id == "proj-1"
        assert event.board_id == "board-1"
        assert event.work_item_id == "123"
        assert event.reason == "Agent executor timed out"

    def test_missing_project_id(self):
        """Test that project_id is required."""
        with pytest.raises(ValueError, match="project_id"):
            LockStuckEvent(
                type="lock.stuck",
                timestamp=now_iso(),
                source="board_event_handler",
                project_id="",
                board_id="board-1",
                work_item_id="123",
                reason="some reason",
            )

    def test_missing_board_id(self):
        """Test that board_id is required."""
        with pytest.raises(ValueError, match="board_id"):
            LockStuckEvent(
                type="lock.stuck",
                timestamp=now_iso(),
                source="board_event_handler",
                project_id="proj-1",
                board_id="",
                work_item_id="123",
                reason="some reason",
            )

    def test_missing_work_item_id(self):
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id"):
            LockStuckEvent(
                type="lock.stuck",
                timestamp=now_iso(),
                source="board_event_handler",
                project_id="proj-1",
                board_id="board-1",
                work_item_id="",
                reason="some reason",
            )

    def test_missing_reason(self):
        """Test that reason is required."""
        with pytest.raises(ValueError, match="reason"):
            LockStuckEvent(
                type="lock.stuck",
                timestamp=now_iso(),
                source="board_event_handler",
                project_id="proj-1",
                board_id="board-1",
                work_item_id="123",
                reason="",
            )

    def test_lock_stuck_serialization(self):
        """Test lock stuck event serialization."""
        event = LockStuckEvent(
            type="lock.stuck",
            timestamp=now_iso(),
            source="board_event_handler",
            correlation_id="corr-4",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="Failed to trigger agent",
        )

        d = event.to_dict()

        assert d["project_id"] == "proj-1"
        assert d["board_id"] == "board-1"
        assert d["work_item_id"] == "123"
        assert d["reason"] == "Failed to trigger agent"

    def test_lock_stuck_roundtrip(self):
        """Test lock stuck event roundtrip."""
        timestamp = now_iso()
        original = LockStuckEvent(
            type="lock.stuck",
            timestamp=timestamp,
            source="board_event_handler",
            project_id="proj-2",
            board_id="board-2",
            work_item_id="456",
            reason="Lock service unreachable",
        )

        d = original.to_dict()
        restored = LockStuckEvent.from_dict(d)

        assert restored.project_id == original.project_id
        assert restored.board_id == original.board_id
        assert restored.work_item_id == original.work_item_id
        assert restored.reason == original.reason

    def test_lock_stuck_event_is_frozen(self):
        """Test that LockStuckEvent is immutable (frozen dataclass)."""
        event = LockStuckEvent(
            type="lock.stuck",
            timestamp=now_iso(),
            source="board_event_handler",
            project_id="proj-1",
            board_id="board-1",
            work_item_id="123",
            reason="test reason",
        )

        assert event.work_item_id == "123"

        with pytest.raises(FrozenInstanceError):
            event.work_item_id = "456"  # type: ignore

        with pytest.raises(FrozenInstanceError):
            event.reason = "different reason"  # type: ignore
