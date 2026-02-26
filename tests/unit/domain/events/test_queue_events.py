"""Unit tests for queue-related domain events."""

import pytest

from codetoreum.domain.events import (
    QueueItemAddedEvent,
    QueueItemRemovedEvent,
    QueuePositionChangedEvent,
    now_iso,
)

# For immutability tests (queue events are frozen dataclasses)
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    # Fallback for older Python versions
    FrozenInstanceError = AttributeError  # type: ignore


class TestQueueItemAddedEvent:
    """Test QueueItemAddedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid queue item added event."""
        event = QueueItemAddedEvent(
            type="queue.item_added",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            position=0,
            project_id="proj-1",
        )

        assert event.queue_name == "proj-1:board-1"
        assert event.item_id == "item-1"
        assert event.position == 0
        assert event.project_id == "proj-1"

    def test_item_at_middle_position(self):
        """Test adding item at middle position in queue."""
        event = QueueItemAddedEvent(
            type="queue.item_added",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-2:board-2",
            item_id="item-5",
            position=3,
            project_id="proj-2",
        )

        assert event.position == 3

    def test_event_is_frozen(self):
        """Test that event is immutable after creation."""
        event = QueueItemAddedEvent(
            type="queue.item_added",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            position=0,
            project_id="proj-1",
        )

        with pytest.raises(FrozenInstanceError):
            event.position = 5

    def test_missing_queue_name_raises_error(self):
        """Test that missing queue_name raises ValueError."""
        with pytest.raises(ValueError, match="queue_name is required"):
            QueueItemAddedEvent(
                type="queue.item_added",
                timestamp=now_iso(),
                source="mock",
                queue_name="",
                item_id="item-1",
                position=0,
                project_id="proj-1",
            )

    def test_missing_item_id_raises_error(self):
        """Test that missing item_id raises ValueError."""
        with pytest.raises(ValueError, match="item_id is required"):
            QueueItemAddedEvent(
                type="queue.item_added",
                timestamp=now_iso(),
                source="mock",
                queue_name="proj-1:board-1",
                item_id="",
                position=0,
                project_id="proj-1",
            )

    def test_negative_position_raises_error(self):
        """Test that negative position raises ValueError."""
        with pytest.raises(ValueError, match="position cannot be negative"):
            QueueItemAddedEvent(
                type="queue.item_added",
                timestamp=now_iso(),
                source="mock",
                queue_name="proj-1:board-1",
                item_id="item-1",
                position=-1,
                project_id="proj-1",
            )

    def test_to_dict_conversion(self):
        """Test serialization to dictionary."""
        event = QueueItemAddedEvent(
            type="queue.item_added",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            position=2,
            project_id="proj-1",
        )

        data = event.to_dict()

        assert data["queue_name"] == "proj-1:board-1"
        assert data["item_id"] == "item-1"
        assert data["position"] == 2
        assert data["project_id"] == "proj-1"

    def test_from_dict_conversion(self):
        """Test deserialization from dictionary."""
        data = {
            "type": "queue.item_added",
            "timestamp": now_iso(),
            "source": "mock",
            "queue_name": "proj-3:board-3",
            "item_id": "item-99",
            "position": 5,
            "project_id": "proj-3",
        }

        event = QueueItemAddedEvent.from_dict(data)

        assert event.queue_name == "proj-3:board-3"
        assert event.item_id == "item-99"
        assert event.position == 5


class TestQueueItemRemovedEvent:
    """Test QueueItemRemovedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid queue item removed event."""
        event = QueueItemRemovedEvent(
            type="queue.item_removed",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            project_id="proj-1",
        )

        assert event.queue_name == "proj-1:board-1"
        assert event.item_id == "item-1"
        assert event.project_id == "proj-1"

    def test_event_is_frozen(self):
        """Test that event is immutable after creation."""
        event = QueueItemRemovedEvent(
            type="queue.item_removed",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            project_id="proj-1",
        )

        with pytest.raises(FrozenInstanceError):
            event.item_id = "item-2"

    def test_missing_queue_name_raises_error(self):
        """Test that missing queue_name raises ValueError."""
        with pytest.raises(ValueError, match="queue_name is required"):
            QueueItemRemovedEvent(
                type="queue.item_removed",
                timestamp=now_iso(),
                source="mock",
                queue_name="",
                item_id="item-1",
                project_id="proj-1",
            )

    def test_missing_item_id_raises_error(self):
        """Test that missing item_id raises ValueError."""
        with pytest.raises(ValueError, match="item_id is required"):
            QueueItemRemovedEvent(
                type="queue.item_removed",
                timestamp=now_iso(),
                source="mock",
                queue_name="proj-1:board-1",
                item_id="",
                project_id="proj-1",
            )

    def test_to_dict_conversion(self):
        """Test serialization to dictionary."""
        event = QueueItemRemovedEvent(
            type="queue.item_removed",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            project_id="proj-1",
        )

        data = event.to_dict()

        assert data["queue_name"] == "proj-1:board-1"
        assert data["item_id"] == "item-1"
        assert data["project_id"] == "proj-1"

    def test_from_dict_conversion(self):
        """Test deserialization from dictionary."""
        data = {
            "type": "queue.item_removed",
            "timestamp": now_iso(),
            "source": "mock",
            "queue_name": "proj-2:board-2",
            "item_id": "item-50",
            "project_id": "proj-2",
        }

        event = QueueItemRemovedEvent.from_dict(data)

        assert event.queue_name == "proj-2:board-2"
        assert event.item_id == "item-50"


class TestQueuePositionChangedEvent:
    """Test QueuePositionChangedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid queue position changed event."""
        event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            old_position=2,
            new_position=0,
            project_id="proj-1",
        )

        assert event.queue_name == "proj-1:board-1"
        assert event.item_id == "item-1"
        assert event.old_position == 2
        assert event.new_position == 0
        assert event.project_id == "proj-1"

    def test_event_is_frozen(self):
        """Test that event is immutable after creation."""
        event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            old_position=2,
            new_position=0,
            project_id="proj-1",
        )

        with pytest.raises(FrozenInstanceError):
            event.new_position = 5

    def test_position_moved_forward(self):
        """Test position moved forward (higher index)."""
        event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            old_position=0,
            new_position=3,
            project_id="proj-1",
        )

        assert event.old_position == 0
        assert event.new_position == 3

    def test_position_moved_backward(self):
        """Test position moved backward (lower index)."""
        event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            old_position=5,
            new_position=1,
            project_id="proj-1",
        )

        assert event.old_position == 5
        assert event.new_position == 1

    def test_same_position_raises_error(self):
        """Test that same old and new position raises ValueError."""
        with pytest.raises(
            ValueError,
            match="old_position must differ from new_position",
        ):
            QueuePositionChangedEvent(
                type="queue.position_changed",
                timestamp=now_iso(),
                source="mock",
                queue_name="proj-1:board-1",
                item_id="item-1",
                old_position=2,
                new_position=2,  # Same position
                project_id="proj-1",
            )

    def test_missing_queue_name_raises_error(self):
        """Test that missing queue_name raises ValueError."""
        with pytest.raises(ValueError, match="queue_name is required"):
            QueuePositionChangedEvent(
                type="queue.position_changed",
                timestamp=now_iso(),
                source="mock",
                queue_name="",
                item_id="item-1",
                old_position=2,
                new_position=0,
                project_id="proj-1",
            )

    def test_missing_item_id_raises_error(self):
        """Test that missing item_id raises ValueError."""
        with pytest.raises(ValueError, match="item_id is required"):
            QueuePositionChangedEvent(
                type="queue.position_changed",
                timestamp=now_iso(),
                source="mock",
                queue_name="proj-1:board-1",
                item_id="",
                old_position=2,
                new_position=0,
                project_id="proj-1",
            )

    def test_negative_old_position_raises_error(self):
        """Test that negative old_position raises ValueError."""
        with pytest.raises(ValueError, match="old_position cannot be negative"):
            QueuePositionChangedEvent(
                type="queue.position_changed",
                timestamp=now_iso(),
                source="mock",
                queue_name="proj-1:board-1",
                item_id="item-1",
                old_position=-1,
                new_position=0,
                project_id="proj-1",
            )

    def test_negative_new_position_raises_error(self):
        """Test that negative new_position raises ValueError."""
        with pytest.raises(ValueError, match="new_position cannot be negative"):
            QueuePositionChangedEvent(
                type="queue.position_changed",
                timestamp=now_iso(),
                source="mock",
                queue_name="proj-1:board-1",
                item_id="item-1",
                old_position=2,
                new_position=-1,
                project_id="proj-1",
            )

    def test_to_dict_conversion(self):
        """Test serialization to dictionary."""
        event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp=now_iso(),
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            old_position=2,
            new_position=0,
            project_id="proj-1",
        )

        data = event.to_dict()

        assert data["queue_name"] == "proj-1:board-1"
        assert data["item_id"] == "item-1"
        assert data["old_position"] == 2
        assert data["new_position"] == 0
        assert data["project_id"] == "proj-1"

    def test_from_dict_conversion(self):
        """Test deserialization from dictionary."""
        data = {
            "type": "queue.position_changed",
            "timestamp": now_iso(),
            "source": "mock",
            "queue_name": "proj-4:board-4",
            "item_id": "item-100",
            "old_position": 5,
            "new_position": 2,
            "project_id": "proj-4",
        }

        event = QueuePositionChangedEvent.from_dict(data)

        assert event.queue_name == "proj-4:board-4"
        assert event.item_id == "item-100"
        assert event.old_position == 5
        assert event.new_position == 2
