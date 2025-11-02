"""In-memory storage adapter for testing."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from codetoreum.domain.types import BucketName, StorageKey
from codetoreum.ports.exceptions import ResourceNotFoundError, UnsupportedFeatureError
from codetoreum.ports.output.storage import IStorage, StorageObject


class InMemoryStorageAdapter(IStorage):
    """
    In-memory storage adapter for testing.

    Stores all objects in memory dictionaries.
    """

    def __init__(self):
        """Initialize in-memory storage."""
        self._objects: Dict[str, bytes] = {}
        self._metadata: Dict[str, Dict[str, any]] = {}

    async def upload(
        self,
        key: str,
        content: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """Upload object to memory."""
        self._objects[key] = content
        self._metadata[key] = {
            "size": len(content),
            "content_type": content_type or "application/octet-stream",
            "metadata": metadata or {},
            "last_modified": datetime.now(timezone.utc),
        }

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
        content = file_path.read_bytes()
        await self.upload(key, content, content_type, metadata)

    async def download(self, key: str) -> bytes:
        """Download object from memory."""
        if key not in self._objects:
            raise ResourceNotFoundError(f"Object not found: {key}")
        return self._objects[key]

    async def download_to_file(self, key: str, file_path: Path) -> None:
        """Download to file."""
        content = await self.download(key)
        file_path.write_bytes(content)

    async def delete(self, key: str) -> None:
        """Delete object from memory."""
        if key not in self._objects:
            raise ResourceNotFoundError(f"Object not found: {key}")
        self._objects.pop(key)
        self._metadata.pop(key)

    async def delete_many(self, keys: List[str]) -> None:
        """Delete multiple files."""
        for key in keys:
            self._objects.pop(key, None)
            self._metadata.pop(key, None)

    async def list_files(
        self,
        prefix: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[StorageObject]:
        """List objects in memory."""
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
        return key in self._objects

    async def get_metadata(self, key: str) -> Dict[str, Any]:
        """Get object metadata."""
        if key not in self._metadata:
            raise ResourceNotFoundError(f"Object not found: {key}")
        return dict(self._metadata[key])

    async def update_metadata(
        self,
        key: str,
        metadata: Dict[str, str],
    ) -> None:
        """Update file metadata."""
        if key not in self._metadata:
            raise ResourceNotFoundError(f"Object not found: {key}")
        self._metadata[key]["metadata"] = metadata

    async def copy(
        self,
        source_key: str,
        destination_key: str,
    ) -> None:
        """Copy a file."""
        if source_key not in self._objects:
            raise ResourceNotFoundError(f"Source not found: {source_key}")
        self._objects[destination_key] = self._objects[source_key]
        self._metadata[destination_key] = dict(self._metadata[source_key])
        self._metadata[destination_key]["last_modified"] = datetime.now(timezone.utc)

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
        if key not in self._objects:
            raise ResourceNotFoundError(f"Object not found: {key}")
        # Return fake URL for testing
        return f"memory://localhost/{key}?expires={expires_in}&method={method}"

    async def get_size(self, key: str) -> int:
        """Get file size."""
        if key not in self._metadata:
            raise ResourceNotFoundError(f"Object not found: {key}")
        return self._metadata[key]["size"]

    async def get_content_type(self, key: str) -> str:
        """Get file content type."""
        if key not in self._metadata:
            raise ResourceNotFoundError(f"Object not found: {key}")
        return self._metadata[key]["content_type"]

    async def list_prefixes(
        self,
        prefix: Optional[str] = None,
        delimiter: str = "/",
    ) -> List[str]:
        """List common prefixes (like directories)."""
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
        total_size = sum(len(content) for content in self._objects.values())
        return {
            "provider": "in-memory",
            "object_count": len(self._objects),
            "total_size_bytes": total_size,
        }

    def clear(self) -> None:
        """Clear all objects (for testing)."""
        self._objects.clear()
        self._metadata.clear()
