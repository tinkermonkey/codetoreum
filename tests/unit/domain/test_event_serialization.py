"""Unit tests for domain event serialization (from_dict validation).

Tests verify that from_dict() methods properly validate required fields
and raise KeyError when validation invariants would be violated.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from codetoreum.domain.events.board_events import (
    ColumnSLAExceededEvent,
    WorkItemColumnChangedEvent,
    WorkItemPositionChangedEvent,
)
from codetoreum.domain.events.execution_events import ExecutionTimedOutEvent
from codetoreum.domain.events.lock_events import LockStuckEvent
from codetoreum.domain.events.queue_events import QueuePositionChangedEvent
from codetoreum.domain.events.review_cycle_events import (
    ReviewCycleApprovedEvent,
    ReviewCycleEscalatedToHumanEvent,
    ReviewCycleHumanFeedbackReceivedEvent,
    ReviewCycleIterationCompletedEvent,
    ReviewCycleMakerRevisionEvent,
    ReviewCycleMaxIterationsReachedEvent,
    ReviewCycleStartedEvent,
)
from codetoreum.domain.events.work_item_events import (
    WorkItemCreatedEvent,
    WorkItemUpdatedEvent,
)


class TestWorkItemPositionChangedEventSerialization:
    """Tests for WorkItemPositionChangedEvent.from_dict() validation."""

    def test_from_dict_valid_data(self):
        """Test valid deserialization."""
        data = {
            "type": "workitem.position_changed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock",
            "work_item_id": "123",
            "project_id": "proj-1",
            "board_id": "board-1",
            "column_name": "In Progress",
            "old_position": 2,
            "new_position": 1,
        }
        event = WorkItemPositionChangedEvent.from_dict(data)
        assert event.old_position == 2
        assert event.new_position == 1
        assert event.work_item_id == "123"

    def test_from_dict_missing_old_position(self):
        """Test that missing old_position raises KeyError."""
        data = {
            "type": "workitem.position_changed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock",
            "work_item_id": "123",
            "project_id": "proj-1",
            "board_id": "board-1",
            "column_name": "In Progress",
            "new_position": 1,
        }
        with pytest.raises(KeyError):
            WorkItemPositionChangedEvent.from_dict(data)

    def test_from_dict_missing_new_position(self):
        """Test that missing new_position raises KeyError."""
        data = {
            "type": "workitem.position_changed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock",
            "work_item_id": "123",
            "project_id": "proj-1",
            "board_id": "board-1",
            "column_name": "In Progress",
            "old_position": 2,
        }
        with pytest.raises(KeyError):
            WorkItemPositionChangedEvent.from_dict(data)

    def test_from_dict_equal_positions_validation(self):
        """Test that equal positions violate validation after deserialization."""
        data = {
            "type": "workitem.position_changed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock",
            "work_item_id": "123",
            "project_id": "proj-1",
            "board_id": "board-1",
            "column_name": "In Progress",
            "old_position": 1,
            "new_position": 1,
        }
        with pytest.raises(ValueError, match="old_position must differ from new_position"):
            WorkItemPositionChangedEvent.from_dict(data)


class TestColumnSLAExceededEventSerialization:
    """Tests for ColumnSLAExceededEvent.from_dict() validation."""

    def test_from_dict_valid_data(self):
        """Test valid deserialization."""
        data = {
            "type": "column.sla_exceeded",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "watchdog",
            "work_item_id": "123",
            "project_id": "proj-1",
            "board_id": "board-1",
            "column_name": "In Progress",
            "elapsed_seconds": 3700,
            "sla_threshold_seconds": 3600,
            "entered_at": datetime.now(UTC).isoformat(),
        }
        event = ColumnSLAExceededEvent.from_dict(data)
        assert event.elapsed_seconds == 3700
        assert event.sla_threshold_seconds == 3600

    def test_from_dict_missing_elapsed_seconds(self):
        """Test that missing elapsed_seconds raises KeyError."""
        data = {
            "type": "column.sla_exceeded",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "watchdog",
            "work_item_id": "123",
            "project_id": "proj-1",
            "board_id": "board-1",
            "column_name": "In Progress",
            "sla_threshold_seconds": 3600,
            "entered_at": datetime.now(UTC).isoformat(),
        }
        with pytest.raises(KeyError):
            ColumnSLAExceededEvent.from_dict(data)

    def test_from_dict_missing_sla_threshold(self):
        """Test that missing sla_threshold_seconds raises KeyError."""
        data = {
            "type": "column.sla_exceeded",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "watchdog",
            "work_item_id": "123",
            "project_id": "proj-1",
            "board_id": "board-1",
            "column_name": "In Progress",
            "elapsed_seconds": 3700,
            "entered_at": datetime.now(UTC).isoformat(),
        }
        with pytest.raises(KeyError):
            ColumnSLAExceededEvent.from_dict(data)

    def test_from_dict_zero_elapsed_seconds_validation(self):
        """Test that zero elapsed_seconds violates validation."""
        data = {
            "type": "column.sla_exceeded",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "watchdog",
            "work_item_id": "123",
            "project_id": "proj-1",
            "board_id": "board-1",
            "column_name": "In Progress",
            "elapsed_seconds": 0,
            "sla_threshold_seconds": 3600,
            "entered_at": datetime.now(UTC).isoformat(),
        }
        with pytest.raises(ValueError, match="elapsed_seconds must be positive"):
            ColumnSLAExceededEvent.from_dict(data)


class TestWorkItemColumnChangedEventSerialization:
    """Tests for WorkItemColumnChangedEvent.from_dict() validation."""

    def test_from_dict_valid_data(self):
        """Test valid deserialization."""
        data = {
            "type": "workitem.column_changed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "github",
            "work_item_id": "123",
            "project_id": "proj-1",
            "board_id": "board-1",
            "from_column": "Backlog",
            "to_column": "In Progress",
            "moved_by": "human",
        }
        event = WorkItemColumnChangedEvent.from_dict(data)
        assert event.work_item_id == "123"
        assert event.from_column == "Backlog"
        assert event.to_column == "In Progress"

    def test_from_dict_missing_work_item_id(self):
        """Test that missing work_item_id raises KeyError."""
        data = {
            "type": "workitem.column_changed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "github",
            "project_id": "proj-1",
            "board_id": "board-1",
            "from_column": "Backlog",
            "to_column": "In Progress",
        }
        with pytest.raises(KeyError):
            WorkItemColumnChangedEvent.from_dict(data)

    def test_from_dict_missing_from_column(self):
        """Test that missing from_column raises KeyError."""
        data = {
            "type": "workitem.column_changed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "github",
            "work_item_id": "123",
            "project_id": "proj-1",
            "board_id": "board-1",
            "to_column": "In Progress",
        }
        with pytest.raises(KeyError):
            WorkItemColumnChangedEvent.from_dict(data)


class TestExecutionTimedOutEventSerialization:
    """Tests for ExecutionTimedOutEvent.from_dict() validation."""

    def test_from_dict_valid_data(self):
        """Test valid deserialization."""
        data = {
            "type": "execution.timed_out",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "execution_timeout_watchdog",
            "execution_id": "exec-123",
            "work_item_id": "item-456",
            "timeout_seconds": 3600,
            "started_at": datetime.now(UTC).isoformat(),
        }
        event = ExecutionTimedOutEvent.from_dict(data)
        assert event.execution_id == "exec-123"
        assert event.timeout_seconds == 3600

    def test_from_dict_missing_timeout_seconds(self):
        """Test that missing timeout_seconds raises KeyError."""
        data = {
            "type": "execution.timed_out",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "execution_timeout_watchdog",
            "execution_id": "exec-123",
            "work_item_id": "item-456",
            "started_at": datetime.now(UTC).isoformat(),
        }
        with pytest.raises(KeyError):
            ExecutionTimedOutEvent.from_dict(data)

    def test_from_dict_zero_timeout_validation(self):
        """Test that zero timeout violates validation."""
        data = {
            "type": "execution.timed_out",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "execution_timeout_watchdog",
            "execution_id": "exec-123",
            "work_item_id": "item-456",
            "timeout_seconds": 0,
            "started_at": datetime.now(UTC).isoformat(),
        }
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            ExecutionTimedOutEvent.from_dict(data)


class TestWorkItemCreatedEventSerialization:
    """Tests for WorkItemCreatedEvent.from_dict() validation."""

    def test_from_dict_valid_data(self):
        """Test valid deserialization."""
        data = {
            "type": "workitem.created",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "github",
            "work_item_id": "123",
            "project_id": "proj-1",
            "title": "Implement new feature",
        }
        event = WorkItemCreatedEvent.from_dict(data)
        assert event.work_item_id == "123"
        assert event.title == "Implement new feature"

    def test_from_dict_missing_title(self):
        """Test that missing title raises KeyError."""
        data = {
            "type": "workitem.created",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "github",
            "work_item_id": "123",
            "project_id": "proj-1",
        }
        with pytest.raises(KeyError):
            WorkItemCreatedEvent.from_dict(data)


class TestReviewCycleStartedEventSerialization:
    """Tests for ReviewCycleStartedEvent.from_dict() validation."""

    def test_from_dict_valid_data(self):
        """Test valid deserialization."""
        data = {
            "type": "review_cycle.started",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock_adapter",
            "review_cycle_id": "cycle-1",
            "work_item_id": "item-1",
            "project_id": "proj-1",
            "maker_agent": "junior_dev",
            "reviewer_agent": "senior_dev",
            "max_iterations": 3,
        }
        event = ReviewCycleStartedEvent.from_dict(data)
        assert event.review_cycle_id == "cycle-1"
        assert event.max_iterations == 3

    def test_from_dict_missing_max_iterations(self):
        """Test that missing max_iterations raises KeyError."""
        data = {
            "type": "review_cycle.started",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock_adapter",
            "review_cycle_id": "cycle-1",
            "work_item_id": "item-1",
            "project_id": "proj-1",
            "maker_agent": "junior_dev",
            "reviewer_agent": "senior_dev",
        }
        with pytest.raises(KeyError):
            ReviewCycleStartedEvent.from_dict(data)

    def test_from_dict_zero_max_iterations_validation(self):
        """Test that zero max_iterations violates validation."""
        data = {
            "type": "review_cycle.started",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock_adapter",
            "review_cycle_id": "cycle-1",
            "work_item_id": "item-1",
            "project_id": "proj-1",
            "maker_agent": "junior_dev",
            "reviewer_agent": "senior_dev",
            "max_iterations": 0,
        }
        with pytest.raises(ValueError, match="max_iterations must be greater than 0"):
            ReviewCycleStartedEvent.from_dict(data)


class TestQueuePositionChangedEventSerialization:
    """Tests for QueuePositionChangedEvent.from_dict() validation."""

    def test_from_dict_valid_data(self):
        """Test valid deserialization."""
        data = {
            "type": "queue.position_changed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock",
            "queue_name": "priority_queue",
            "item_id": "item-1",
            "old_position": 5,
            "new_position": 3,
            "project_id": "proj-1",
        }
        event = QueuePositionChangedEvent.from_dict(data)
        assert event.old_position == 5
        assert event.new_position == 3

    def test_from_dict_missing_queue_name(self):
        """Test that missing queue_name raises KeyError."""
        data = {
            "type": "queue.position_changed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock",
            "item_id": "item-1",
            "old_position": 5,
            "new_position": 3,
        }
        with pytest.raises(KeyError):
            QueuePositionChangedEvent.from_dict(data)

    def test_from_dict_equal_positions_validation(self):
        """Test that equal positions violate validation."""
        data = {
            "type": "queue.position_changed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock",
            "queue_name": "priority_queue",
            "item_id": "item-1",
            "old_position": 3,
            "new_position": 3,
            "project_id": "proj-1",
        }
        with pytest.raises(ValueError, match="old_position must differ from new_position"):
            QueuePositionChangedEvent.from_dict(data)


class TestLockStuckEventSerialization:
    """Tests for LockStuckEvent.from_dict() validation."""

    def test_from_dict_valid_data(self):
        """Test valid deserialization."""
        data = {
            "type": "lock.stuck",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "watchdog",
            "project_id": "proj-1",
            "board_id": "board-1",
            "work_item_id": "item-1",
            "reason": "Execution timeout",
        }
        event = LockStuckEvent.from_dict(data)
        assert event.reason == "Execution timeout"
        assert event.project_id == "proj-1"

    def test_from_dict_missing_reason(self):
        """Test that missing reason raises KeyError."""
        data = {
            "type": "lock.stuck",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "watchdog",
            "project_id": "proj-1",
            "board_id": "board-1",
            "work_item_id": "item-1",
        }
        with pytest.raises(KeyError):
            LockStuckEvent.from_dict(data)

    def test_from_dict_empty_reason_validation(self):
        """Test that empty reason violates validation."""
        data = {
            "type": "lock.stuck",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "watchdog",
            "project_id": "proj-1",
            "board_id": "board-1",
            "work_item_id": "item-1",
            "reason": "",
        }
        with pytest.raises(ValueError, match="reason is required"):
            LockStuckEvent.from_dict(data)


class TestReviewCycleIterationCompletedEventSerialization:
    """Tests for ReviewCycleIterationCompletedEvent.from_dict() validation."""

    def test_from_dict_valid_data(self):
        """Test valid deserialization."""
        data = {
            "type": "review_cycle.iteration_completed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock_adapter",
            "review_cycle_id": "cycle-1",
            "work_item_id": "item-1",
            "iteration": 1,
            "status": "CHANGES_REQUESTED",
            "blocking_count": 0,
        }
        event = ReviewCycleIterationCompletedEvent.from_dict(data)
        assert event.iteration == 1
        assert event.status == "CHANGES_REQUESTED"

    def test_from_dict_missing_iteration(self):
        """Test that missing iteration raises KeyError."""
        data = {
            "type": "review_cycle.iteration_completed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock_adapter",
            "review_cycle_id": "cycle-1",
            "work_item_id": "item-1",
            "status": "CHANGES_REQUESTED",
        }
        with pytest.raises(KeyError):
            ReviewCycleIterationCompletedEvent.from_dict(data)

    def test_from_dict_zero_iteration_validation(self):
        """Test that zero iteration violates validation."""
        data = {
            "type": "review_cycle.iteration_completed",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "mock_adapter",
            "review_cycle_id": "cycle-1",
            "work_item_id": "item-1",
            "iteration": 0,
            "status": "CHANGES_REQUESTED",
        }
        with pytest.raises(ValueError, match="iteration must be greater than 0"):
            ReviewCycleIterationCompletedEvent.from_dict(data)
