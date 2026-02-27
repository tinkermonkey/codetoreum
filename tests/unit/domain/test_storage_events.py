"""Unit tests for storage domain events."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from codetoreum.domain.events.storage_events import (
    ArtifactDeletedEvent,
    ArtifactUploadedEvent,
)


class TestArtifactUploadedEvent:
    """Tests for ArtifactUploadedEvent."""

    def test_initialization_with_all_fields(self):
        """Test event initialization with all fields."""
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="projects/proj-1/artifacts/output.txt",
            size_bytes=1024,
            content_type="text/plain",
            project_id="proj-1",
        )

        assert event.type == "storage.artifact_uploaded"
        assert event.timestamp == "2025-01-14T10:30:00+00:00"
        assert event.source == "github"
        assert event.key == "projects/proj-1/artifacts/output.txt"
        assert event.size_bytes == 1024
        assert event.content_type == "text/plain"
        assert event.project_id == "proj-1"
        assert event.event_id is not None
        assert event.correlation_id is None

    def test_initialization_with_minimal_required_fields(self):
        """Test event initialization with minimal required fields."""
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="output.txt",
            size_bytes=0,
            content_type="text/plain",
        )

        assert event.key == "output.txt"
        assert event.size_bytes == 0
        assert event.content_type == "text/plain"
        assert event.project_id is None

    def test_missing_key_raises_validation_error(self):
        """Test that missing key raises ValueError."""
        with pytest.raises(ValueError, match="key is required"):
            ArtifactUploadedEvent(
                type="storage.artifact_uploaded",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                key="",
                size_bytes=100,
                content_type="text/plain",
            )

    def test_missing_content_type_raises_validation_error(self):
        """Test that missing content_type raises ValueError."""
        with pytest.raises(ValueError, match="content_type is required"):
            ArtifactUploadedEvent(
                type="storage.artifact_uploaded",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                key="output.txt",
                size_bytes=100,
                content_type="",
            )

    def test_negative_size_raises_validation_error(self):
        """Test that negative size_bytes raises ValueError."""
        with pytest.raises(ValueError, match="size_bytes cannot be negative"):
            ArtifactUploadedEvent(
                type="storage.artifact_uploaded",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                key="output.txt",
                size_bytes=-1,
                content_type="text/plain",
            )

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="output.txt",
            size_bytes=2048,
            content_type="application/json",
            project_id="proj-1",
            event_id="event-123",
        )

        event_dict = event.to_dict()

        assert event_dict["type"] == "storage.artifact_uploaded"
        assert event_dict["timestamp"] == "2025-01-14T10:30:00+00:00"
        assert event_dict["source"] == "github"
        assert event_dict["key"] == "output.txt"
        assert event_dict["size_bytes"] == 2048
        assert event_dict["content_type"] == "application/json"
        assert event_dict["project_id"] == "proj-1"
        assert event_dict["event_id"] == "event-123"
        assert event_dict["correlation_id"] is None

    def test_from_dict_deserialization(self):
        """Test deserialization from dictionary."""
        event_id = "event-456"
        event_dict = {
            "type": "storage.artifact_uploaded",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "github",
            "key": "output.txt",
            "size_bytes": 5120,
            "content_type": "text/csv",
            "project_id": "proj-2",
            "event_id": event_id,
            "correlation_id": "corr-123",
        }

        event = ArtifactUploadedEvent.from_dict(event_dict)

        assert event.type == "storage.artifact_uploaded"
        assert event.timestamp == "2025-01-14T10:30:00+00:00"
        assert event.source == "github"
        assert event.key == "output.txt"
        assert event.size_bytes == 5120
        assert event.content_type == "text/csv"
        assert event.project_id == "proj-2"
        assert event.event_id == event_id
        assert event.correlation_id == "corr-123"

    def test_from_dict_with_missing_optional_fields(self):
        """Test deserialization with missing optional fields."""
        event_dict = {
            "type": "storage.artifact_uploaded",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "github",
            "key": "output.txt",
            "size_bytes": 100,
            "content_type": "text/plain",
        }

        event = ArtifactUploadedEvent.from_dict(event_dict)

        assert event.project_id is None
        assert event.correlation_id is None
        assert event.event_id is not None

    def test_round_trip_serialization(self):
        """Test that serialization and deserialization are reversible."""
        original_event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="report.pdf",
            size_bytes=10240,
            content_type="application/pdf",
            project_id="proj-1",
        )

        # Serialize and deserialize
        event_dict = original_event.to_dict()
        restored_event = ArtifactUploadedEvent.from_dict(event_dict)

        # Compare key attributes
        assert restored_event.key == original_event.key
        assert restored_event.size_bytes == original_event.size_bytes
        assert restored_event.content_type == original_event.content_type
        assert restored_event.project_id == original_event.project_id

    def test_immutability_prevents_modification(self):
        """Test that event is frozen and cannot be modified."""
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="output.txt",
            size_bytes=1024,
            content_type="text/plain",
        )

        # Attempting to modify should raise FrozenInstanceError
        with pytest.raises(Exception):  # FrozenInstanceError
            event.size_bytes = 2048

    def test_event_type_property(self):
        """Test that event_type property returns class name."""
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="output.txt",
            size_bytes=100,
            content_type="text/plain",
        )

        assert event.event_type == "ArtifactUploadedEvent"


class TestArtifactDeletedEvent:
    """Tests for ArtifactDeletedEvent."""

    def test_initialization_with_all_fields(self):
        """Test event initialization with all fields."""
        event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="projects/proj-1/artifacts/output.txt",
            project_id="proj-1",
        )

        assert event.type == "storage.artifact_deleted"
        assert event.timestamp == "2025-01-14T10:30:00+00:00"
        assert event.source == "github"
        assert event.key == "projects/proj-1/artifacts/output.txt"
        assert event.project_id == "proj-1"

    def test_missing_key_raises_validation_error(self):
        """Test that missing key raises ValueError."""
        with pytest.raises(ValueError, match="key is required"):
            ArtifactDeletedEvent(
                type="storage.artifact_deleted",
                timestamp="2025-01-14T10:30:00+00:00",
                source="github",
                key="",
                project_id="proj-1",
            )

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="old_artifact.txt",
            project_id="proj-1",
            event_id="event-789",
        )

        event_dict = event.to_dict()

        assert event_dict["type"] == "storage.artifact_deleted"
        assert event_dict["key"] == "old_artifact.txt"
        assert event_dict["project_id"] == "proj-1"
        assert event_dict["event_id"] == "event-789"

    def test_from_dict_deserialization(self):
        """Test deserialization from dictionary."""
        event_dict = {
            "type": "storage.artifact_deleted",
            "timestamp": "2025-01-14T10:30:00+00:00",
            "source": "github",
            "key": "artifact.txt",
            "project_id": "proj-3",
            "event_id": "event-999",
        }

        event = ArtifactDeletedEvent.from_dict(event_dict)

        assert event.key == "artifact.txt"
        assert event.project_id == "proj-3"

    def test_round_trip_serialization(self):
        """Test round trip serialization and deserialization."""
        original_event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="cleanup.log",
            project_id="proj-2",
        )

        event_dict = original_event.to_dict()
        restored_event = ArtifactDeletedEvent.from_dict(event_dict)

        assert restored_event.key == original_event.key
        assert restored_event.project_id == original_event.project_id

    def test_immutability_prevents_modification(self):
        """Test that event is frozen and cannot be modified."""
        event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="artifact.txt",
            project_id="proj-1",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            event.key = "new_artifact.txt"

    def test_event_type_property(self):
        """Test that event_type property returns class name."""
        event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="artifact.txt",
        )

        assert event.event_type == "ArtifactDeletedEvent"

    def test_project_id_is_optional(self):
        """Test that project_id is optional."""
        event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp="2025-01-14T10:30:00+00:00",
            source="github",
            key="artifact.txt",
        )

        assert event.project_id is None
