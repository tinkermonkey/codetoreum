"""IStorage output port interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from codetoreum.domain.types import BucketName, StorageKey


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class StorageObject:
    """Storage object metadata."""

    key: StorageKey
    size: int
    last_modified: datetime
    content_type: Optional[str]
    metadata: Dict[str, str]
    etag: Optional[str] = None


# ============================================================================
# Port Interface
# ============================================================================


class IStorage(ABC):
    """Interface for file and object storage."""

    @abstractmethod
    async def upload(
        self,
        key: str,
        content: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Upload a file.

        Args:
            key: Object key/path
            content: File content as bytes
            content_type: MIME type (defaults to application/octet-stream)
            metadata: Optional metadata key-value pairs

        Raises:
            ValidationError: Invalid key or content
            StorageError: Upload failed
        """
        pass

    @abstractmethod
    async def upload_from_file(
        self,
        key: str,
        file_path: Path,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Upload from file.

        Args:
            key: Object key/path
            file_path: Path to file to upload
            content_type: MIME type (auto-detected if not provided)
            metadata: Optional metadata key-value pairs

        Raises:
            ResourceNotFoundError: File doesn't exist
            ValidationError: Invalid key or file
            StorageError: Upload failed
        """
        pass

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """
        Download a file.

        Args:
            key: Object key/path

        Returns:
            bytes: File content

        Raises:
            ResourceNotFoundError: Object doesn't exist
            StorageError: Download failed
        """
        pass

    @abstractmethod
    async def download_to_file(self, key: str, file_path: Path) -> None:
        """
        Download to file.

        Args:
            key: Object key/path
            file_path: Destination file path

        Raises:
            ResourceNotFoundError: Object doesn't exist
            StorageError: Download failed
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """
        Delete a file.

        Args:
            key: Object key/path

        Raises:
            ResourceNotFoundError: Object doesn't exist
            StorageError: Delete failed
        """
        pass

    @abstractmethod
    async def delete_many(self, keys: List[str]) -> None:
        """
        Delete multiple files.

        Args:
            keys: List of object keys/paths

        Raises:
            StorageError: Delete failed
        """
        pass

    @abstractmethod
    async def list_files(
        self,
        prefix: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[StorageObject]:
        """
        List files with optional prefix filter.

        Args:
            prefix: Optional key prefix to filter by
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List[StorageObject]: List of storage objects

        Raises:
            StorageError: List operation failed
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if file exists.

        Args:
            key: Object key/path

        Returns:
            bool: True if object exists

        Raises:
            StorageError: Check failed
        """
        pass

    @abstractmethod
    async def get_metadata(self, key: str) -> Dict[str, Any]:
        """
        Get file metadata.

        Args:
            key: Object key/path

        Returns:
            Dict[str, Any]: Object metadata

        Raises:
            ResourceNotFoundError: Object doesn't exist
            StorageError: Metadata retrieval failed
        """
        pass

    @abstractmethod
    async def update_metadata(
        self,
        key: str,
        metadata: Dict[str, str],
    ) -> None:
        """
        Update file metadata.

        Args:
            key: Object key/path
            metadata: New metadata key-value pairs

        Raises:
            ResourceNotFoundError: Object doesn't exist
            StorageError: Update failed
        """
        pass

    @abstractmethod
    async def copy(
        self,
        source_key: str,
        destination_key: str,
    ) -> None:
        """
        Copy a file.

        Args:
            source_key: Source object key/path
            destination_key: Destination object key/path

        Raises:
            ResourceNotFoundError: Source doesn't exist
            StorageError: Copy failed
        """
        pass

    @abstractmethod
    async def move(
        self,
        source_key: str,
        destination_key: str,
    ) -> None:
        """
        Move a file.

        Args:
            source_key: Source object key/path
            destination_key: Destination object key/path

        Raises:
            ResourceNotFoundError: Source doesn't exist
            StorageError: Move failed
        """
        pass

    @abstractmethod
    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        method: str = "GET",
    ) -> str:
        """
        Generate temporary access URL.

        Args:
            key: Object key/path
            expires_in: URL expiration in seconds
            method: HTTP method (GET, PUT, DELETE)

        Returns:
            str: Presigned URL

        Raises:
            ResourceNotFoundError: Object doesn't exist
            UnsupportedFeatureError: Provider doesn't support presigned URLs
            StorageError: URL generation failed
        """
        pass

    @abstractmethod
    async def get_size(self, key: str) -> int:
        """
        Get file size.

        Args:
            key: Object key/path

        Returns:
            int: Size in bytes

        Raises:
            ResourceNotFoundError: Object doesn't exist
            StorageError: Query failed
        """
        pass

    @abstractmethod
    async def get_content_type(self, key: str) -> str:
        """
        Get file content type.

        Args:
            key: Object key/path

        Returns:
            str: MIME content type

        Raises:
            ResourceNotFoundError: Object doesn't exist
            StorageError: Query failed
        """
        pass

    @abstractmethod
    async def list_prefixes(
        self,
        prefix: Optional[str] = None,
        delimiter: str = "/",
    ) -> List[str]:
        """
        List common prefixes (like directories).

        Args:
            prefix: Optional starting prefix
            delimiter: Delimiter for prefix detection

        Returns:
            List[str]: List of prefixes

        Raises:
            StorageError: List operation failed
        """
        pass

    @abstractmethod
    async def get_storage_info(self) -> Dict[str, Any]:
        """
        Get storage system information.

        Returns:
            Dict[str, Any]: Storage info (total size, object count, etc.)

        Raises:
            StorageError: Query failed
        """
        pass
