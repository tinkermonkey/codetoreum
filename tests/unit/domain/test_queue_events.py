"""Unit tests for queue domain events."""

import pytest

from codetoreum.domain.events.queue_events import (
    QueueItemAddedEvent,
    QueueItemRemovedEvent,
    QueuePositionChangedEvent,
)


class TestQueueItemAddedEvent:
    """Tests for QueueItemAddedEvent."""

    def test_initialization_with_all_fields(self):
        """Test event initialization with all fields."""
        event = QueueItemAddedEvent(
            type="queue.item_added",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            position=0,
            project_id="proj-1",
        )

        assert event.type == "queue.item_added"
        assert event.queue_name == "proj-1:board-1"
        assert event.item_id == "item-1"
        assert event.position == 0
        assert event.project_id == "proj-1"

    def test_missing_queue_name_raises_validation_error(self):
        """Test that missing queue_name raises ValueError."""
        with pytest.raises(ValueError, match="queue_name is required"):
            QueueItemAddedEvent(
                type="queue.item_added",
                timestamp="2025-01-14T10:30:00+00:00",
                source="mock",
                queue_name="",
                item_id="item-1",
                position=0,
            )

    def test_missing_item_id_raises_validation_error(self):
        """Test that missing item_id raises ValueError."""
        with pytest.raises(ValueError, match="item_id is required"):
            QueueItemAddedEvent(
                type="queue.item_added",
                timestamp="2025-01-14T10:30:00+00:00",
                source="mock",
                queue_name="proj-1:board-1",
                item_id="",
                position=0,
            )

    def test_negative_position_raises_validation_error(self):
        """Test that negative position raises ValueError."""
        with pytest.raises(ValueError, match="position cannot be negative"):
            QueueItemAddedEvent(
                type="queue.item_added",
                timestamp="2025-01-14T10:30:00+00:00",
                source="mock",
                queue_name="proj-1:board-1",
                item_id="item-1",
                position=-1,
            )

    def test_zero_position_is_valid(self):
        """Test that position 0 is valid (first in queue)."""
        event = QueueItemAddedEvent(
            type="queue.item_added",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            position=0,
        )

        assert event.position == 0

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        event = QueueItemAddedEvent(
            type="queue.item_added",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-5",
            position=3,
            project_id="proj-1",
            event_id="event-123",
        )

        event_dict = event.to_dict()

        assert event_dict["queue_name"] == "proj-1:board-1"
        assert event_dict["item_id"] == "item-5"
        assert event_dict["position"] == 3
        assert event_dict["project_id"] == "proj-1"
        assert event_dict["event_id"] == "event-123"

    def test_from_dict_deserialization(self):
        """Test deserialization from dictionary."""
        event_dict = {
            "type": "queue.item_added",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "mock",
            "queue_name": "proj-2:board-2",
            "item_id": "item-10",
            "position": 5,
            "project_id": "proj-2",
        }

        event = QueueItemAddedEvent.from_dict(event_dict)

        assert event.queue_name == "proj-2:board-2"
        assert event.item_id == "item-10"
        assert event.position == 5

    def test_round_trip_serialization(self):
        """Test round trip serialization."""
        original_event = QueueItemAddedEvent(
            type="queue.item_added",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-100",
            position=25,
            project_id="proj-1",
        )

        event_dict = original_event.to_dict()
        restored_event = QueueItemAddedEvent.from_dict(event_dict)

        assert restored_event.queue_name == original_event.queue_name
        assert restored_event.item_id == original_event.item_id
        assert restored_event.position == original_event.position

    def test_event_type_property(self):
        """Test event_type property."""
        event = QueueItemAddedEvent(
            type="queue.item_added",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            position=0,
        )

        assert event.event_type == "QueueItemAddedEvent"


class TestQueueItemRemovedEvent:
    """Tests for QueueItemRemovedEvent."""

    def test_initialization_with_all_fields(self):
        """Test event initialization with all fields."""
        event = QueueItemRemovedEvent(
            type="queue.item_removed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            project_id="proj-1",
        )

        assert event.type == "queue.item_removed"
        assert event.queue_name == "proj-1:board-1"
        assert event.item_id == "item-1"
        assert event.project_id == "proj-1"

    def test_missing_queue_name_raises_validation_error(self):
        """Test that missing queue_name raises ValueError."""
        with pytest.raises(ValueError, match="queue_name is required"):
            QueueItemRemovedEvent(
                type="queue.item_removed",
                timestamp="2025-01-14T10:30:00+00:00",
                source="mock",
                queue_name="",
                item_id="item-1",
            )

    def test_missing_item_id_raises_validation_error(self):
        """Test that missing item_id raises ValueError."""
        with pytest.raises(ValueError, match="item_id is required"):
            QueueItemRemovedEvent(
                type="queue.item_removed",
                timestamp="2025-01-14T10:30:00+00:00",
                source="mock",
                queue_name="proj-1:board-1",
                item_id="",
            )

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        event = QueueItemRemovedEvent(
            type="queue.item_removed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-5",
            project_id="proj-1",
            event_id="event-456",
        )

        event_dict = event.to_dict()

        assert event_dict["queue_name"] == "proj-1:board-1"
        assert event_dict["item_id"] == "item-5"
        assert event_dict["project_id"] == "proj-1"

    def test_from_dict_deserialization(self):
        """Test deserialization from dictionary."""
        event_dict = {
            "type": "queue.item_removed",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "mock",
            "queue_name": "proj-2:board-2",
            "item_id": "item-20",
            "project_id": "proj-2",
        }

        event = QueueItemRemovedEvent.from_dict(event_dict)

        assert event.queue_name == "proj-2:board-2"
        assert event.item_id == "item-20"

    def test_round_trip_serialization(self):
        """Test round trip serialization."""
        original_event = QueueItemRemovedEvent(
            type="queue.item_removed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-200",
            project_id="proj-1",
        )

        event_dict = original_event.to_dict()
        restored_event = QueueItemRemovedEvent.from_dict(event_dict)

        assert restored_event.queue_name == original_event.queue_name
        assert restored_event.item_id == original_event.item_id

    def test_event_type_property(self):
        """Test event_type property."""
        event = QueueItemRemovedEvent(
            type="queue.item_removed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
        )

        assert event.event_type == "QueueItemRemovedEvent"


class TestQueuePositionChangedEvent:
    """Tests for QueuePositionChangedEvent."""

    def test_initialization_with_all_fields(self):
        """Test event initialization with all fields."""
        event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp="2025-01-14T10:30:00+00:00",
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

    def test_missing_queue_name_raises_validation_error(self):
        """Test that missing queue_name raises ValueError."""
        with pytest.raises(ValueError, match="queue_name is required"):
            QueuePositionChangedEvent(
                type="queue.position_changed",
                timestamp="2025-01-14T10:30:00+00:00",
                source="mock",
                queue_name="",
                item_id="item-1",
                old_position=1,
                new_position=2,
            )

    def test_missing_item_id_raises_validation_error(self):
        """Test that missing item_id raises ValueError."""
        with pytest.raises(ValueError, match="item_id is required"):
            QueuePositionChangedEvent(
                type="queue.position_changed",
                timestamp="2025-01-14T10:30:00+00:00",
                source="mock",
                queue_name="proj-1:board-1",
                item_id="",
                old_position=1,
                new_position=2,
            )

    def test_negative_old_position_raises_validation_error(self):
        """Test that negative old_position raises ValueError."""
        with pytest.raises(ValueError, match="old_position cannot be negative"):
            QueuePositionChangedEvent(
                type="queue.position_changed",
                timestamp="2025-01-14T10:30:00+00:00",
                source="mock",
                queue_name="proj-1:board-1",
                item_id="item-1",
                old_position=-1,
                new_position=0,
            )

    def test_negative_new_position_raises_validation_error(self):
        """Test that negative new_position raises ValueError."""
        with pytest.raises(ValueError, match="new_position cannot be negative"):
            QueuePositionChangedEvent(
                type="queue.position_changed",
                timestamp="2025-01-14T10:30:00+00:00",
                source="mock",
                queue_name="proj-1:board-1",
                item_id="item-1",
                old_position=0,
                new_position=-1,
            )

    def test_same_positions_raises_validation_error(self):
        """Test that old_position == new_position raises ValueError."""
        with pytest.raises(
            ValueError,
            match="old_position must differ from new_position",
        ):
            QueuePositionChangedEvent(
                type="queue.position_changed",
                timestamp="2025-01-14T10:30:00+00:00",
                source="mock",
                queue_name="proj-1:board-1",
                item_id="item-1",
                old_position=5,
                new_position=5,
            )

    def test_position_moved_forward(self):
        """Test position moved forward (higher index)."""
        event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            old_position=0,
            new_position=5,
        )

        assert event.old_position == 0
        assert event.new_position == 5

    def test_position_moved_backward(self):
        """Test position moved backward (lower index)."""
        event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            old_position=5,
            new_position=1,
        )

        assert event.old_position == 5
        assert event.new_position == 1

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-10",
            old_position=8,
            new_position=3,
            project_id="proj-1",
            event_id="event-789",
        )

        event_dict = event.to_dict()

        assert event_dict["queue_name"] == "proj-1:board-1"
        assert event_dict["item_id"] == "item-10"
        assert event_dict["old_position"] == 8
        assert event_dict["new_position"] == 3
        assert event_dict["project_id"] == "proj-1"

    def test_from_dict_deserialization(self):
        """Test deserialization from dictionary."""
        event_dict = {
            "type": "queue.position_changed",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "mock",
            "queue_name": "proj-2:board-2",
            "item_id": "item-30",
            "old_position": 10,
            "new_position": 2,
            "project_id": "proj-2",
        }

        event = QueuePositionChangedEvent.from_dict(event_dict)

        assert event.queue_name == "proj-2:board-2"
        assert event.item_id == "item-30"
        assert event.old_position == 10
        assert event.new_position == 2

    def test_round_trip_serialization(self):
        """Test round trip serialization."""
        original_event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-300",
            old_position=15,
            new_position=7,
            project_id="proj-1",
        )

        event_dict = original_event.to_dict()
        restored_event = QueuePositionChangedEvent.from_dict(event_dict)

        assert restored_event.queue_name == original_event.queue_name
        assert restored_event.item_id == original_event.item_id
        assert restored_event.old_position == original_event.old_position
        assert restored_event.new_position == original_event.new_position

    def test_event_type_property(self):
        """Test event_type property."""
        event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            old_position=0,
            new_position=1,
        )

        assert event.event_type == "QueuePositionChangedEvent"

    def test_large_position_values(self):
        """Test handling of large position values."""
        event = QueuePositionChangedEvent(
            type="queue.position_changed",
            timestamp="2025-01-14T10:30:00+00:00",
            source="mock",
            queue_name="proj-1:board-1",
            item_id="item-1",
            old_position=1000,
            new_position=500,
        )

        assert event.old_position == 1000
        assert event.new_position == 500
