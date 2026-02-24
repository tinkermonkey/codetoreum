"""In-memory storage adapter for testing."""

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from codetoreum.domain.types import BucketName, StorageKey
from codetoreum.ports.exceptions import ResourceNotFoundError, UnsupportedFeatureError
from codetoreum.ports.output.storage import IStorage, StorageObject
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.domain.events.storage_events import (
    ArtifactUploadedEvent,
    ArtifactDeletedEvent,
)
from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter


class InMemoryStorageAdapter(IStorage):
    """
    In-memory storage adapter for testing.

    Stores all objects in memory dictionaries.
    """

    def __init__(self, event_emitter: Optional[IEventEmitter] = None):
        """Initialize in-memory storage.

        Args:
            event_emitter: Optional IEventEmitter for emitting domain events.
                          Defaults to MockEventEmitter.
        """
        self._objects: Dict[str, bytes] = {}
        self._metadata: Dict[str, Dict[str, any]] = {}
        self._lock = threading.Lock()
        self._event_emitter = event_emitter or MockEventEmitter()

    async def upload(
        self,
        key: str,
        content: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
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
                "last_modified": datetime.now(timezone.utc),
            }

            # Emit domain event
            # Note: source="mock" identifies this as a test/simulation event for traceability
            self._event_emitter.emit(
                ArtifactUploadedEvent(
                    type="storage.artifact_uploaded",
                    timestamp=datetime.now(timezone.utc).isoformat(),
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
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """Upload from file."""
        if not file_path.exists():
            raise ResourceNotFoundError(f"File not found: {file_path}")
        # Note: File I/O is intentionally done outside the lock since reading from disk
        # should not block the storage lock. The actual state modification (storage) is locked.
        content = file_path.read_bytes()
        await self.upload(key, content, content_type, metadata)

    async def download(self, key: str) -> bytes:
        """Download object from memory."""
        with self._lock:
            if key not in self._objects:
                raise ResourceNotFoundError(f"Object not found: {key}")
            return self._objects[key]

    async def download_to_file(self, key: str, file_path: Path) -> None:
        """Download to file."""
        content = await self.download(key)
        file_path.write_bytes(content)

    async def delete(self, key: str) -> None:
        """Delete object from memory."""
        with self._lock:
            if key not in self._objects:
                raise ResourceNotFoundError(f"Object not found: {key}")
            self._objects.pop(key)
            self._metadata.pop(key)

            # Emit domain event
            # Note: source="mock" identifies this as a test/simulation event for traceability
            self._event_emitter.emit(
                ArtifactDeletedEvent(
                    type="storage.artifact_deleted",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    source="mock",
                    key=key,
                    project_id=None,
                )
            )

    async def delete_many(self, keys: List[str]) -> None:
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
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            source="mock",
                            key=key,
                            project_id=None,
                        )
                    )

    async def list_files(
        self,
        prefix: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[StorageObject]:
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

    async def get_metadata(self, key: str) -> Dict[str, Any]:
        """Get object metadata."""
        with self._lock:
            if key not in self._metadata:
                raise ResourceNotFoundError(f"Object not found: {key}")
            return dict(self._metadata[key])

    async def update_metadata(
        self,
        key: str,
        metadata: Dict[str, str],
    ) -> None:
        """Update file metadata."""
        with self._lock:
            if key not in self._metadata:
                raise ResourceNotFoundError(f"Object not found: {key}")
            self._metadata[key]["metadata"] = metadata

    async def copy(
        self,
        source_key: str,
        destination_key: str,
    ) -> None:
        """Copy a file."""
        with self._lock:
            if source_key not in self._objects:
                raise ResourceNotFoundError(f"Source not found: {source_key}")
            self._objects[destination_key] = self._objects[source_key]
            self._metadata[destination_key] = dict(self._metadata[source_key])
            self._metadata[destination_key]["last_modified"] = datetime.now(timezone.utc)

            # Emit ArtifactUploadedEvent for the copied artifact
            # Note: source="mock" identifies this as a test/simulation event for traceability
            self._event_emitter.emit(
                ArtifactUploadedEvent(
                    type="storage.artifact_uploaded",
                    timestamp=datetime.now(timezone.utc).isoformat(),
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
                raise ResourceNotFoundError(f"Object not found: {key}")
            # Return fake URL for testing
            return f"memory://localhost/{key}?expires={expires_in}&method={method}"

    async def get_size(self, key: str) -> int:
        """Get file size."""
        with self._lock:
            if key not in self._metadata:
                raise ResourceNotFoundError(f"Object not found: {key}")
            return self._metadata[key]["size"]

    async def get_content_type(self, key: str) -> str:
        """Get file content type."""
        with self._lock:
            if key not in self._metadata:
                raise ResourceNotFoundError(f"Object not found: {key}")
            return self._metadata[key]["content_type"]

    async def list_prefixes(
        self,
        prefix: Optional[str] = None,
        delimiter: str = "/",
    ) -> List[str]:
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

    async def get_storage_info(self) -> Dict[str, Any]:
        """Get storage system information."""
        with self._lock:
            total_size = sum(len(content) for content in self._objects.values())
            return {
                "provider": "in-memory",
                "object_count": len(self._objects),
                "total_size_bytes": total_size,
            }

    def clear(self) -> None:
        """Clear all objects (for testing)."""
        with self._lock:
            self._objects.clear()
            self._metadata.clear()
