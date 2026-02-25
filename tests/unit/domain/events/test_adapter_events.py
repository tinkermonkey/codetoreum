"""Unit tests for vendor-agnostic adapter events.

Tests verify event creation, serialization/deserialization, and validation
of the core CodetoreumEvent base class.
"""

import json
from datetime import datetime

import pytest

from codetoreum.domain.events import CodetoreumEvent, now_iso


class TestCodetoreumEventBasics:
    """Test basic CodetoreumEvent functionality."""

    def test_create_valid_event(self):
        """Test creating a valid CodetoreumEvent."""
        timestamp = now_iso()
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=timestamp,
            source="github",
            correlation_id="corr-123",
        )

        assert event.type == "workitem.created"
        assert event.timestamp == timestamp
        assert event.source == "github"
        assert event.correlation_id == "corr-123"
        assert event.event_id is not None

    def test_event_id_auto_generated(self):
        """Test that event_id is auto-generated if not provided."""
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="github",
        )

        assert event.event_id is not None
        assert len(event.event_id) > 0

    def test_event_id_custom(self):
        """Test providing custom event_id."""
        custom_id = "custom-event-id-123"
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="github",
            event_id=custom_id,
        )

        assert event.event_id == custom_id

    def test_correlation_id_optional(self):
        """Test that correlation_id is optional."""
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="github",
        )

        assert event.correlation_id is None

    def test_invalid_type_missing_dot(self):
        """Test that event type must include dot notation."""
        with pytest.raises(ValueError, match="dot notation"):
            CodetoreumEvent(
                type="workitem_created",
                timestamp=now_iso(),
                source="github",
            )

    def test_invalid_type_empty(self):
        """Test that event type cannot be empty."""
        with pytest.raises(ValueError, match="dot notation"):
            CodetoreumEvent(
                type="",
                timestamp=now_iso(),
                source="github",
            )

    def test_invalid_source_empty(self):
        """Test that source cannot be empty."""
        with pytest.raises(ValueError, match="source"):
            CodetoreumEvent(
                type="workitem.created",
                timestamp=now_iso(),
                source="",
            )

    def test_invalid_timestamp_format(self):
        """Test that timestamp must be ISO 8601."""
        # Note: Validation is lenient - accepts basic ISO dates
        # This is acceptable since the validation just ensures ISO format
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp="2024-01-01",  # Basic ISO date
            source="github",
        )
        assert event.timestamp == "2024-01-01"

    def test_truly_invalid_timestamp_format(self):
        """Test that clearly invalid timestamps are rejected."""
        with pytest.raises(ValueError, match="ISO 8601"):
            CodetoreumEvent(
                type="workitem.created",
                timestamp="not-a-date",  # Clearly invalid
                source="github",
            )

    def test_timestamp_with_z_suffix(self):
        """Test that ISO timestamps with Z suffix are accepted."""
        timestamp = "2024-01-08T12:34:56Z"
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=timestamp,
            source="github",
        )

        assert event.timestamp == timestamp

    def test_timestamp_with_timezone_offset(self):
        """Test that ISO timestamps with timezone offset are accepted."""
        timestamp = "2024-01-08T12:34:56+00:00"
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=timestamp,
            source="github",
        )

        assert event.timestamp == timestamp


class TestCodetoreumEventSerialization:
    """Test event serialization and deserialization."""

    def test_to_dict(self):
        """Test serializing event to dictionary."""
        timestamp = now_iso()
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=timestamp,
            source="github",
            correlation_id="corr-123",
            event_id="event-456",
        )

        d = event.to_dict()

        assert d["type"] == "workitem.created"
        assert d["timestamp"] == timestamp
        assert d["source"] == "github"
        assert d["correlation_id"] == "corr-123"
        assert d["event_id"] == "event-456"

    def test_to_dict_none_correlation_id(self):
        """Test that None correlation_id is preserved in dict."""
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="github",
        )

        d = event.to_dict()
        assert d["correlation_id"] is None

    def test_from_dict(self):
        """Test deserializing event from dictionary."""
        timestamp = now_iso()
        d = {
            "type": "workitem.created",
            "timestamp": timestamp,
            "source": "github",
            "correlation_id": "corr-123",
            "event_id": "event-456",
        }

        event = CodetoreumEvent.from_dict(d)

        assert event.type == "workitem.created"
        assert event.timestamp == timestamp
        assert event.source == "github"
        assert event.correlation_id == "corr-123"
        assert event.event_id == "event-456"

    def test_from_dict_missing_required_field(self):
        """Test deserialization fails with missing required field."""
        d = {
            "type": "workitem.created",
            "timestamp": now_iso(),
            # Missing 'source'
        }

        with pytest.raises(ValueError, match="Missing required field"):
            CodetoreumEvent.from_dict(d)

    def test_roundtrip_serialization(self):
        """Test that event survives roundtrip serialization."""
        timestamp = now_iso()
        original = CodetoreumEvent(
            type="workitem.created",
            timestamp=timestamp,
            source="github",
            correlation_id="corr-123",
            event_id="event-456",
        )

        # Roundtrip through dict
        d = original.to_dict()
        restored = CodetoreumEvent.from_dict(d)

        assert restored.type == original.type
        assert restored.timestamp == original.timestamp
        assert restored.source == original.source
        assert restored.correlation_id == original.correlation_id
        assert restored.event_id == original.event_id

    def test_json_serializable(self):
        """Test that event dict is JSON serializable."""
        event = CodetoreumEvent(
            type="workitem.created",
            timestamp=now_iso(),
            source="github",
            correlation_id="corr-123",
        )

        d = event.to_dict()
        json_str = json.dumps(d)  # Should not raise

        assert len(json_str) > 0


class TestNowIso:
    """Test the now_iso() helper function."""

    def test_now_iso_format(self):
        """Test that now_iso returns valid ISO 8601 timestamp."""
        timestamp = now_iso()

        # Should not raise
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    def test_now_iso_in_utc(self):
        """Test that now_iso returns UTC timezone."""
        timestamp = now_iso()

        # Parse and check timezone
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert dt.tzinfo is not None
