# IStorage Output Port Design

## Overview

The `IStorage` port provides an abstraction for file and object storage. This port is used for storing artifacts, logs, and other files that don't belong in the event store or repository.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import Optional, List, BinaryIO, AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

class IStorage(ABC):
    """Interface for file and object storage."""

    @abstractmethod
    async def upload(self,
                     key: str,
                     content: bytes,
                     content_type: Optional[str] = None,
                     metadata: Optional[Dict[str, str]] = None) -> None:
        """Upload a file."""
        pass

    @abstractmethod
    async def upload_from_file(self,
                               key: str,
                               file_path: Path,
                               content_type: Optional[str] = None,
                               metadata: Optional[Dict[str, str]] = None) -> None:
        """Upload from file."""
        pass

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download a file."""
        pass

    @abstractmethod
    async def download_to_file(self, key: str, file_path: Path) -> None:
        """Download to file."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a file."""
        pass

    @abstractmethod
    async def list_files(self,
                        prefix: Optional[str] = None,
                        limit: int = 1000) -> List[StorageObject]:
        """List files with optional prefix filter."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if file exists."""
        pass

    @abstractmethod
    async def get_metadata(self, key: str) -> Dict[str, Any]:
        """Get file metadata."""
        pass

    @abstractmethod
    async def generate_presigned_url(self,
                                    key: str,
                                    expires_in: int = 3600) -> str:
        """Generate temporary access URL."""
        pass
```

## Data Models

```python
@dataclass
class StorageObject:
    """Storage object metadata."""
    key: str
    size: int
    last_modified: datetime
    content_type: Optional[str]
    metadata: Dict[str, str]
```

## Adapter Implementations

### S3 Storage Adapter

```python
class S3StorageAdapter(IStorage):
    """AWS S3 implementation."""

    def __init__(self, bucket_name: str, s3_client):
        self.bucket = bucket_name
        self.s3 = s3_client

    async def upload(self,
                     key: str,
                     content: bytes,
                     content_type: Optional[str] = None,
                     metadata: Optional[Dict[str, str]] = None) -> None:
        """Upload to S3."""
        await self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type or 'application/octet-stream',
            Metadata=metadata or {}
        )
```

### Filesystem Storage Adapter

```python
class FilesystemStorageAdapter(IStorage):
    """Local filesystem implementation."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def upload(self,
                     key: str,
                     content: bytes,
                     content_type: Optional[str] = None,
                     metadata: Optional[Dict[str, str]] = None) -> None:
        """Write to filesystem."""
        file_path = self.base_path / key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
```

### In-Memory Storage (Testing)

```python
class InMemoryStorageAdapter(IStorage):
    """In-memory storage for testing."""

    def __init__(self):
        self.files: Dict[str, bytes] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}

    async def upload(self,
                     key: str,
                     content: bytes,
                     content_type: Optional[str] = None,
                     metadata: Optional[Dict[str, str]] = None) -> None:
        """Store in memory."""
        self.files[key] = content
        self.metadata[key] = {
            'content_type': content_type,
            'metadata': metadata or {},
            'size': len(content),
            'uploaded_at': datetime.utcnow()
        }
```

## Integration Points

### Used By
- Artifact Storage Service
- Log Archival Service
- Report Generation Service

### Dependencies
- None (standalone port)

## Implementation Notes

1. **Path Safety**: Validate and sanitize all keys/paths
2. **Large Files**: Stream large files instead of loading into memory
3. **Retry Logic**: Implement retry for transient failures
4. **Cleanup**: Implement lifecycle policies for old files
5. **Access Control**: Ensure proper permissions on stored files
