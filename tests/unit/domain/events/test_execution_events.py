"""Unit tests for execution domain events."""

import pytest

from codetoreum.domain.events import ExecutionTimedOutEvent, now_iso


class TestExecutionTimedOutEvent:
    """Test ExecutionTimedOutEvent."""

    def test_create_valid_event(self) -> None:
        """Test creating a valid execution timed out event."""
        timestamp = now_iso()
        started_at = now_iso()

        event = ExecutionTimedOutEvent(
            type="execution.timed_out",
            timestamp=timestamp,
            source="execution_timeout_watchdog",
            execution_id="exec-123",
            work_item_id="issue-456",
            timeout_seconds=3600,
            started_at=started_at,
        )

        assert event.execution_id == "exec-123"
        assert event.work_item_id == "issue-456"
        assert event.timeout_seconds == 3600
        assert event.started_at == started_at

    def test_missing_execution_id(self) -> None:
        """Test that execution_id is required."""
        with pytest.raises(ValueError, match="execution_id is required"):
            ExecutionTimedOutEvent(
                type="execution.timed_out",
                timestamp=now_iso(),
                source="execution_timeout_watchdog",
                execution_id="",
                work_item_id="issue-456",
                timeout_seconds=3600,
                started_at=now_iso(),
            )

    def test_missing_work_item_id(self) -> None:
        """Test that work_item_id is required."""
        with pytest.raises(ValueError, match="work_item_id is required"):
            ExecutionTimedOutEvent(
                type="execution.timed_out",
                timestamp=now_iso(),
                source="execution_timeout_watchdog",
                execution_id="exec-123",
                work_item_id="",
                timeout_seconds=3600,
                started_at=now_iso(),
            )

    def test_invalid_timeout_seconds_zero(self) -> None:
        """Test that timeout_seconds must be > 0."""
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            ExecutionTimedOutEvent(
                type="execution.timed_out",
                timestamp=now_iso(),
                source="execution_timeout_watchdog",
                execution_id="exec-123",
                work_item_id="issue-456",
                timeout_seconds=0,
                started_at=now_iso(),
            )

    def test_invalid_timeout_seconds_negative(self) -> None:
        """Test that negative timeout_seconds is invalid."""
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            ExecutionTimedOutEvent(
                type="execution.timed_out",
                timestamp=now_iso(),
                source="execution_timeout_watchdog",
                execution_id="exec-123",
                work_item_id="issue-456",
                timeout_seconds=-100,
                started_at=now_iso(),
            )

    def test_missing_started_at(self) -> None:
        """Test that started_at is required."""
        with pytest.raises(ValueError, match="started_at is required"):
            ExecutionTimedOutEvent(
                type="execution.timed_out",
                timestamp=now_iso(),
                source="execution_timeout_watchdog",
                execution_id="exec-123",
                work_item_id="issue-456",
                timeout_seconds=3600,
                started_at="",
            )

    def test_event_immutable(self) -> None:
        """Test that event is immutable."""
        event = ExecutionTimedOutEvent(
            type="execution.timed_out",
            timestamp=now_iso(),
            source="execution_timeout_watchdog",
            execution_id="exec-123",
            work_item_id="issue-456",
            timeout_seconds=3600,
            started_at=now_iso(),
        )

        with pytest.raises(AttributeError):
            event.execution_id = "exec-999"  # type: ignore

    def test_to_dict_serialization(self) -> None:
        """Test serializing event to dictionary."""
        timestamp = now_iso()
        started_at = now_iso()

        event = ExecutionTimedOutEvent(
            type="execution.timed_out",
            timestamp=timestamp,
            source="execution_timeout_watchdog",
            execution_id="exec-123",
            work_item_id="issue-456",
            timeout_seconds=3600,
            started_at=started_at,
        )

        event_dict = event.to_dict()

        assert event_dict["execution_id"] == "exec-123"
        assert event_dict["work_item_id"] == "issue-456"
        assert event_dict["timeout_seconds"] == 3600
        assert event_dict["started_at"] == started_at

    def test_large_timeout_seconds(self) -> None:
        """Test with large timeout_seconds value."""
        event = ExecutionTimedOutEvent(
            type="execution.timed_out",
            timestamp=now_iso(),
            source="execution_timeout_watchdog",
            execution_id="exec-123",
            work_item_id="issue-456",
            timeout_seconds=86400,  # 24 hours
            started_at=now_iso(),
        )

        assert event.timeout_seconds == 86400

    def test_various_execution_id_formats(self) -> None:
        """Test with various execution ID formats."""
        exec_ids = [
            "exec-123",
            "execution_abc_def",
            "exec-with-dashes",
            "abc123def456",
        ]

        for exec_id in exec_ids:
            event = ExecutionTimedOutEvent(
                type="execution.timed_out",
                timestamp=now_iso(),
                source="execution_timeout_watchdog",
                execution_id=exec_id,
                work_item_id="issue-456",
                timeout_seconds=3600,
                started_at=now_iso(),
            )

            assert event.execution_id == exec_id

    def test_event_type_correct(self) -> None:
        """Test that event type is correct."""
        event = ExecutionTimedOutEvent(
            type="execution.timed_out",
            timestamp=now_iso(),
            source="execution_timeout_watchdog",
            execution_id="exec-123",
            work_item_id="issue-456",
            timeout_seconds=3600,
            started_at=now_iso(),
        )

        assert event.type == "execution.timed_out"

    def test_event_source_correct(self) -> None:
        """Test that event source is correct."""
        event = ExecutionTimedOutEvent(
            type="execution.timed_out",
            timestamp=now_iso(),
            source="execution_timeout_watchdog",
            execution_id="exec-123",
            work_item_id="issue-456",
            timeout_seconds=3600,
            started_at=now_iso(),
        )

        assert event.source == "execution_timeout_watchdog"
