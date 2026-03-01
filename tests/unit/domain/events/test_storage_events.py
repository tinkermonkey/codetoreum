"""Unit tests for storage-related domain events."""

import pytest

from codetoreum.domain.events import (
    ArtifactDeletedEvent,
    ArtifactUploadedEvent,
    now_iso,
)

# For immutability tests (storage events are frozen dataclasses)
try:
    from dataclasses import FrozenInstanceError
except ImportError:
    # Fallback for older Python versions
    FrozenInstanceError = AttributeError  # type: ignore


class TestArtifactUploadedEvent:
    """Test ArtifactUploadedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid artifact uploaded event."""
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp=now_iso(),
            source="mock",
            key="projects/proj-1/artifacts/output.txt",
            size_bytes=1024,
            content_type="text/plain",
            project_id="proj-1",
        )

        assert event.key == "projects/proj-1/artifacts/output.txt"
        assert event.size_bytes == 1024
        assert event.content_type == "text/plain"
        assert event.project_id == "proj-1"

    def test_event_is_frozen(self):
        """Test that event is immutable after creation."""
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp=now_iso(),
            source="mock",
            key="projects/proj-1/artifacts/output.txt",
            size_bytes=1024,
            content_type="text/plain",
            project_id="proj-1",
        )

        with pytest.raises(FrozenInstanceError):
            event.size_bytes = 2048

    def test_missing_key_raises_error(self):
        """Test that missing key raises ValueError."""
        with pytest.raises(ValueError, match="key is required"):
            ArtifactUploadedEvent(
                type="storage.artifact_uploaded",
                timestamp=now_iso(),
                source="mock",
                key="",
                size_bytes=1024,
                content_type="text/plain",
                project_id="proj-1",
            )

    def test_negative_size_raises_error(self):
        """Test that negative size_bytes raises ValueError."""
        with pytest.raises(ValueError, match="size_bytes cannot be negative"):
            ArtifactUploadedEvent(
                type="storage.artifact_uploaded",
                timestamp=now_iso(),
                source="mock",
                key="projects/proj-1/artifacts/output.txt",
                size_bytes=-1,
                content_type="text/plain",
                project_id="proj-1",
            )

    def test_missing_content_type_raises_error(self):
        """Test that missing content_type raises ValueError."""
        with pytest.raises(ValueError, match="content_type is required"):
            ArtifactUploadedEvent(
                type="storage.artifact_uploaded",
                timestamp=now_iso(),
                source="mock",
                key="projects/proj-1/artifacts/output.txt",
                size_bytes=1024,
                content_type="",
                project_id="proj-1",
            )

    def test_zero_size_is_valid(self):
        """Test that zero size_bytes is valid (empty file)."""
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp=now_iso(),
            source="mock",
            key="projects/proj-1/artifacts/empty.txt",
            size_bytes=0,
            content_type="text/plain",
            project_id="proj-1",
        )

        assert event.size_bytes == 0

    def test_large_file_size(self):
        """Test handling of large file sizes."""
        large_size = 1024 * 1024 * 1024  # 1 GB
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp=now_iso(),
            source="mock",
            key="projects/proj-1/artifacts/large.zip",
            size_bytes=large_size,
            content_type="application/zip",
            project_id="proj-1",
        )

        assert event.size_bytes == large_size

    def test_common_mime_types(self):
        """Test various common MIME types."""
        test_cases = [
            ("text/plain", "output.txt"),
            ("application/json", "data.json"),
            ("application/pdf", "report.pdf"),
            ("image/png", "screenshot.png"),
            ("application/zip", "archive.zip"),
        ]

        for mime_type, filename in test_cases:
            event = ArtifactUploadedEvent(
                type="storage.artifact_uploaded",
                timestamp=now_iso(),
                source="mock",
                key=f"projects/proj-1/artifacts/{filename}",
                size_bytes=1024,
                content_type=mime_type,
                project_id="proj-1",
            )

            assert event.content_type == mime_type

    def test_to_dict_conversion(self):
        """Test serialization to dictionary."""
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp=now_iso(),
            source="mock",
            key="projects/proj-1/artifacts/output.txt",
            size_bytes=2048,
            content_type="text/plain",
            project_id="proj-1",
        )

        data = event.to_dict()

        assert data["key"] == "projects/proj-1/artifacts/output.txt"
        assert data["size_bytes"] == 2048
        assert data["content_type"] == "text/plain"
        assert data["project_id"] == "proj-1"
        assert data["type"] == "storage.artifact_uploaded"

    def test_from_dict_conversion(self):
        """Test deserialization from dictionary."""
        data = {
            "type": "storage.artifact_uploaded",
            "timestamp": now_iso(),
            "source": "mock",
            "key": "projects/proj-2/artifacts/results.json",
            "size_bytes": 4096,
            "content_type": "application/json",
            "project_id": "proj-2",
        }

        event = ArtifactUploadedEvent.from_dict(data)

        assert event.key == "projects/proj-2/artifacts/results.json"
        assert event.size_bytes == 4096
        assert event.content_type == "application/json"

    def test_nested_path(self):
        """Test artifact with nested path."""
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp=now_iso(),
            source="mock",
            key="projects/proj-1/builds/stage-1/outputs/results.zip",
            size_bytes=5000,
            content_type="application/zip",
            project_id="proj-1",
        )

        assert "builds/stage-1/outputs" in event.key


class TestArtifactDeletedEvent:
    """Test ArtifactDeletedEvent."""

    def test_create_valid_event(self):
        """Test creating a valid artifact deleted event."""
        event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp=now_iso(),
            source="mock",
            key="projects/proj-1/artifacts/output.txt",
            project_id="proj-1",
        )

        assert event.key == "projects/proj-1/artifacts/output.txt"
        assert event.project_id == "proj-1"

    def test_event_is_frozen(self):
        """Test that event is immutable after creation."""
        event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp=now_iso(),
            source="mock",
            key="projects/proj-1/artifacts/output.txt",
            project_id="proj-1",
        )

        with pytest.raises(FrozenInstanceError):
            event.key = "projects/proj-1/artifacts/other.txt"

    def test_missing_key_raises_error(self):
        """Test that missing key raises ValueError."""
        with pytest.raises(ValueError, match="key is required"):
            ArtifactDeletedEvent(
                type="storage.artifact_deleted",
                timestamp=now_iso(),
                source="mock",
                key="",
                project_id="proj-1",
            )

    def test_delete_after_upload(self):
        """Test deleting an artifact that was previously uploaded."""
        # First upload
        upload_event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp=now_iso(),
            source="mock",
            key="projects/proj-1/artifacts/temp.txt",
            size_bytes=512,
            content_type="text/plain",
            project_id="proj-1",
        )

        # Then delete
        delete_event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp=now_iso(),
            source="mock",
            key=upload_event.key,  # Same key
            project_id=upload_event.project_id,
        )

        assert delete_event.key == upload_event.key

    def test_multiple_artifact_deletions(self):
        """Test deleting multiple artifacts."""
        artifacts = [
            "projects/proj-1/artifacts/file1.txt",
            "projects/proj-1/artifacts/file2.txt",
            "projects/proj-1/artifacts/file3.txt",
        ]

        events = [
            ArtifactDeletedEvent(
                type="storage.artifact_deleted",
                timestamp=now_iso(),
                source="mock",
                key=key,
                project_id="proj-1",
            )
            for key in artifacts
        ]

        assert len(events) == 3
        assert all(isinstance(e, ArtifactDeletedEvent) for e in events)
        assert [e.key for e in events] == artifacts

    def test_to_dict_conversion(self):
        """Test serialization to dictionary."""
        event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp=now_iso(),
            source="mock",
            key="projects/proj-1/artifacts/old.zip",
            project_id="proj-1",
        )

        data = event.to_dict()

        assert data["key"] == "projects/proj-1/artifacts/old.zip"
        assert data["project_id"] == "proj-1"
        assert data["type"] == "storage.artifact_deleted"

    def test_from_dict_conversion(self):
        """Test deserialization from dictionary."""
        data = {
            "type": "storage.artifact_deleted",
            "timestamp": now_iso(),
            "source": "mock",
            "key": "projects/proj-2/artifacts/cleanup.tar.gz",
            "project_id": "proj-2",
        }

        event = ArtifactDeletedEvent.from_dict(data)

        assert event.key == "projects/proj-2/artifacts/cleanup.tar.gz"
        assert event.project_id == "proj-2"

    def test_nested_path_deletion(self):
        """Test deleting artifact with nested path."""
        event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp=now_iso(),
            source="mock",
            key="projects/proj-1/builds/2025-02/01/output.json",
            project_id="proj-1",
        )

        assert "builds/2025-02/01" in event.key

    def test_correlation_id_preservation(self):
        """Test that correlation_id is preserved in event."""
        import uuid

        correlation_id = str(uuid.uuid4())
        event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp=now_iso(),
            source="mock",
            correlation_id=correlation_id,
            key="projects/proj-1/artifacts/file.txt",
            project_id="proj-1",
        )

        assert event.correlation_id == correlation_id

    def test_project_id_optional(self):
        """Test that project_id can be None."""
        event = ArtifactDeletedEvent(
            type="storage.artifact_deleted",
            timestamp=now_iso(),
            source="mock",
            key="shared/artifacts/global_file.txt",
            project_id=None,
        )

        assert event.project_id is None
