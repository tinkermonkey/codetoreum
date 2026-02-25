"""Storage-related events for artifact management.

Events track changes to storage including artifact uploads and deletions.
"""

from dataclasses import dataclass
from uuid import uuid4

from .adapter_events import CodetoreumEvent


@dataclass(frozen=True)
class ArtifactUploadedEvent(CodetoreumEvent):
    """Emitted when an artifact is uploaded to storage.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "storage.artifact_uploaded"
        key (str): Storage key/path of the uploaded artifact
        size_bytes (int): Size of the uploaded artifact in bytes
        content_type (str): MIME type of the artifact
        project_id (str): ID of the project that owns the artifact

    Example:
        >>> event = ArtifactUploadedEvent(
        ...     type="storage.artifact_uploaded",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="mock",
        ...     key="projects/proj-1/artifacts/output.txt",
        ...     size_bytes=1024,
        ...     content_type="text/plain",
        ...     project_id="proj-1"
        ... )
        >>> event.size_bytes = 2048  # ❌ Raises FrozenInstanceError
    """

    key: str = ""
    size_bytes: int = 0
    content_type: str = ""
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.key:
            msg = "key is required"
            raise ValueError(msg)
        if self.size_bytes < 0:
            msg = "size_bytes cannot be negative"
            raise ValueError(msg)
        if not self.content_type:
            msg = "content_type is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "key": self.key,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "project_id": self.project_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ArtifactUploadedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "storage.artifact_uploaded"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            key=data.get("key", ""),
            size_bytes=data.get("size_bytes", 0),
            content_type=data.get("content_type", ""),
            project_id=data.get("project_id"),
        )


@dataclass(frozen=True)
class ArtifactDeletedEvent(CodetoreumEvent):
    """Emitted when an artifact is deleted from storage.

    **Immutability**: This is an immutable event (frozen dataclass). All fields
    are read-only after construction to maintain event sourcing audit trail
    integrity. Events represent immutable facts—attempting to modify any field
    will raise `FrozenInstanceError`. This immutability is essential because
    events are the permanent record of state changes in the system and must
    never be altered once created.

    Attributes:
        type (str): Fixed to "storage.artifact_deleted"
        key (str): Storage key/path of the deleted artifact
        project_id (str): ID of the project that owned the artifact

    Example:
        >>> event = ArtifactDeletedEvent(
        ...     type="storage.artifact_deleted",
        ...     timestamp="2025-01-14T10:30:00+00:00",
        ...     source="mock",
        ...     key="projects/proj-1/artifacts/output.txt",
        ...     project_id="proj-1"
        ... )
        >>> event.key = "projects/proj-1/artifacts/other.txt"  # ❌ Raises FrozenInstanceError
    """

    key: str = ""
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        super().__post_init__()
        if not self.key:
            msg = "key is required"
            raise ValueError(msg)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = super().to_dict()
        d.update({
            "key": self.key,
            "project_id": self.project_id,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ArtifactDeletedEvent":
        """Deserialize from dictionary."""
        return cls(
            type=data.get("type", "storage.artifact_deleted"),
            timestamp=data.get("timestamp", ""),
            source=data.get("source", ""),
            correlation_id=data.get("correlation_id"),
            event_id=data.get("event_id") or str(uuid4()),
            key=data.get("key", ""),
            project_id=data.get("project_id"),
        )
