"""In-memory storage adapter for testing."""

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.domain.events.container_events import ContainerExecutionCompletedEvent
from codetoreum.domain.events.storage_events import (
    ArtifactDeletedEvent,
    ArtifactUploadedEvent,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.storage import IStorage, StorageObject


class InMemoryStorageAdapter(IStorage):
    """
    In-memory storage adapter for testing.

    Stores all objects in memory dictionaries.
    """

    def __init__(
        self,
        event_emitter: IEventEmitter | None = None,
        event_bus: Optional[EventBus] = None,
    ):
        """Initialize in-memory storage.

        Args:
            event_emitter: Optional IEventEmitter for emitting domain events.
                          Defaults to MockEventEmitter.
            event_bus: Optional EventBus for subscribing to domain events
                      (e.g., ContainerExecutionCompletedEvent)
        """
        self._objects: dict[str, bytes] = {}
        self._metadata: dict[str, dict[str, any]] = {}
        self._lock = threading.Lock()
        self._event_emitter = event_emitter or MockEventEmitter()
        self._event_bus = event_bus

        # Subscribe to container execution completion events if event bus provided
        if self._event_bus:
            self._event_bus.subscribe(
                "ContainerExecutionCompletedEvent",
                self._handle_container_completion
            )

    async def upload(
        self,
        key: str,
        content: bytes,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Upload object to memory."""
        with self._lock:
            self._objects[key] = content
            content_type_value = content_type or "application/octet-stream"
            size_bytes = len(content)
            self._metadata[key] = {
                "size": size_bytes,
                "content_type": content_type_value,
                "metadata": metadata or {},
                "last_modified": datetime.now(UTC),
            }

            # Emit domain event
            # Note: source="mock" identifies this as a test/simulation event for traceability
            self._event_emitter.emit(
                ArtifactUploadedEvent(
                    type="storage.artifact_uploaded",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="mock",
                    key=key,
                    size_bytes=size_bytes,
                    content_type=content_type_value,
                    project_id=None,
                )
            )

    async def upload_from_file(
        self,
        key: str,
        file_path: Path,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Upload from file."""
        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise ResourceNotFoundError(msg)
        # Note: File I/O is intentionally done outside the lock since reading from disk
        # should not block the storage lock. The actual state modification (storage) is locked.
        content = file_path.read_bytes()
        await self.upload(key, content, content_type, metadata)

    async def download(self, key: str) -> bytes:
        """Download object from memory."""
        with self._lock:
            if key not in self._objects:
                msg = f"Object not found: {key}"
                raise ResourceNotFoundError(msg)
            return self._objects[key]

    async def download_to_file(self, key: str, file_path: Path) -> None:
        """Download to file."""
        content = await self.download(key)
        file_path.write_bytes(content)

    async def delete(self, key: str) -> None:
        """Delete object from memory."""
        with self._lock:
            if key not in self._objects:
                msg = f"Object not found: {key}"
                raise ResourceNotFoundError(msg)
            self._objects.pop(key)
            self._metadata.pop(key)

            # Emit domain event
            # Note: source="mock" identifies this as a test/simulation event for traceability
            self._event_emitter.emit(
                ArtifactDeletedEvent(
                    type="storage.artifact_deleted",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="mock",
                    key=key,
                    project_id=None,
                )
            )

    async def delete_many(self, keys: list[str]) -> None:
        """Delete multiple files."""
        with self._lock:
            for key in keys:
                # Only emit event if key actually exists
                if key in self._objects:
                    self._objects.pop(key, None)
                    self._metadata.pop(key, None)

                    # Emit domain event for each deleted artifact
                    # Note: source="mock" identifies this as a test/simulation event for traceability
                    self._event_emitter.emit(
                        ArtifactDeletedEvent(
                            type="storage.artifact_deleted",
                            timestamp=datetime.now(UTC).isoformat(),
                            source="mock",
                            key=key,
                            project_id=None,
                        )
                    )

    async def list_files(
        self,
        prefix: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[StorageObject]:
        """List objects in memory."""
        with self._lock:
            objects = []
            matching_keys = [
                k for k in self._metadata.keys()
                if prefix is None or k.startswith(prefix)
            ]

            for key in sorted(matching_keys)[offset:offset + limit]:
                meta = self._metadata[key]
                objects.append(
                    StorageObject(
                        key=key,
                        size=meta["size"],
                        last_modified=meta["last_modified"],
                        content_type=meta["content_type"],
                        metadata=meta["metadata"],
                    )
                )
            return objects

    async def exists(self, key: str) -> bool:
        """Check if object exists in memory."""
        with self._lock:
            return key in self._objects

    async def get_metadata(self, key: str) -> dict[str, Any]:
        """Get object metadata."""
        with self._lock:
            if key not in self._metadata:
                msg = f"Object not found: {key}"
                raise ResourceNotFoundError(msg)
            return dict(self._metadata[key])

    async def update_metadata(
        self,
        key: str,
        metadata: dict[str, str],
    ) -> None:
        """Update file metadata."""
        with self._lock:
            if key not in self._metadata:
                msg = f"Object not found: {key}"
                raise ResourceNotFoundError(msg)
            self._metadata[key]["metadata"] = metadata

    async def copy(
        self,
        source_key: str,
        destination_key: str,
    ) -> None:
        """Copy a file."""
        with self._lock:
            if source_key not in self._objects:
                msg = f"Source not found: {source_key}"
                raise ResourceNotFoundError(msg)
            self._objects[destination_key] = self._objects[source_key]
            self._metadata[destination_key] = dict(self._metadata[source_key])
            self._metadata[destination_key]["last_modified"] = datetime.now(UTC)

            # Emit ArtifactUploadedEvent for the copied artifact
            # Note: source="mock" identifies this as a test/simulation event for traceability
            self._event_emitter.emit(
                ArtifactUploadedEvent(
                    type="storage.artifact_uploaded",
                    timestamp=datetime.now(UTC).isoformat(),
                    source="mock",
                    key=destination_key,
                    size_bytes=self._metadata[destination_key]["size"],
                    content_type=self._metadata[destination_key]["content_type"],
                    project_id=None,
                )
            )

    async def move(
        self,
        source_key: str,
        destination_key: str,
    ) -> None:
        """Move a file."""
        await self.copy(source_key, destination_key)
        await self.delete(source_key)

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        method: str = "GET",
    ) -> str:
        """Generate temporary access URL (not supported in memory)."""
        with self._lock:
            if key not in self._objects:
                msg = f"Object not found: {key}"
                raise ResourceNotFoundError(msg)
            # Return fake URL for testing
            return f"memory://localhost/{key}?expires={expires_in}&method={method}"

    async def get_size(self, key: str) -> int:
        """Get file size."""
        with self._lock:
            if key not in self._metadata:
                msg = f"Object not found: {key}"
                raise ResourceNotFoundError(msg)
            return self._metadata[key]["size"]

    async def get_content_type(self, key: str) -> str:
        """Get file content type."""
        with self._lock:
            if key not in self._metadata:
                msg = f"Object not found: {key}"
                raise ResourceNotFoundError(msg)
            return self._metadata[key]["content_type"]

    async def list_prefixes(
        self,
        prefix: str | None = None,
        delimiter: str = "/",
    ) -> list[str]:
        """List common prefixes (like directories)."""
        with self._lock:
            prefixes = set()
            for key in self._objects.keys():
                if prefix and not key.startswith(prefix):
                    continue

                # Find delimiter after prefix
                search_from = len(prefix) if prefix else 0
                delimiter_pos = key.find(delimiter, search_from)

                if delimiter_pos > 0:
                    # Found a prefix
                    prefixes.add(key[:delimiter_pos + 1])

            return sorted(list(prefixes))

    async def get_storage_info(self) -> dict[str, Any]:
        """Get storage system information."""
        with self._lock:
            total_size = sum(len(content) for content in self._objects.values())
            return {
                "provider": "in-memory",
                "object_count": len(self._objects),
                "total_size_bytes": total_size,
            }

    async def _handle_container_completion(
        self, event: ContainerExecutionCompletedEvent
    ) -> None:
        """Handle container execution completion by persisting output files.

        This handler is invoked when ContainerExecutionCompletedEvent is emitted by the container
        adapter, enabling automatic artifact persistence to storage via event subscription.

        Args:
            event: ContainerExecutionCompletedEvent containing container_id, command,
                  exit_code, output_files list, and project_id
        """
        # Persist all files from the container's output directory
        for file_path in event.output_files:
            # Create a deterministic storage key based on container, file path, and project
            if event.project_id:
                storage_key = f"container/{event.project_id}/{event.container_id}/{file_path}"
            else:
                storage_key = f"container/{event.container_id}/{file_path}"

            # In a fake environment, we store a placeholder file reference
            # In production, this would read from the actual /output/ directory
            content = f"Output from container {event.container_id}: {file_path}\nCommand: {event.command}\nExit code: {event.exit_code}".encode()

            with self._lock:
                self._objects[storage_key] = content
                self._metadata[storage_key] = {
                    "size": len(content),
                    "content_type": "text/plain",
                    "metadata": {
                        "container_id": event.container_id,
                        "file_path": file_path,
                        "command": event.command,
                        "exit_code": str(event.exit_code),
                    },
                    "last_modified": datetime.now(UTC),
                }

                # Emit domain event for the persisted artifact
                self._event_emitter.emit(
                    ArtifactUploadedEvent(
                        type="storage.artifact_uploaded",
                        timestamp=datetime.now(UTC).isoformat(),
                        source="mock",
                        key=storage_key,
                        size_bytes=len(content),
                        content_type="text/plain",
                        project_id=event.project_id,
                    )
                )

    def clear(self) -> None:
        """Clear all objects (for testing)."""
        with self._lock:
            self._objects.clear()
            self._metadata.clear()
