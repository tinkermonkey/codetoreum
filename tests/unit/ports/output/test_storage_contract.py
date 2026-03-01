"""Contract tests for IStorage interface.

These abstract tests define the contract that all IStorage implementations must
satisfy. Subclasses provide specific implementations to test via create_storage().

The tests validate:
- Basic upload/download operations with state consistency
- Error conditions (missing files, resource not found)
- Multi-operation sequences (upload+download, delete+error)
- Metadata operations
- File listing and prefix operations
"""

from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.storage import IStorage


class TestStorageContract(ABC):
    """Abstract contract tests for IStorage implementations.

    Subclasses must implement create_storage() to provide a concrete
    IStorage implementation to test.

    These tests verify:
    - State consistency: upload→download returns same content
    - Error conditions: delete→download raises ResourceNotFoundError
    - Last-write-wins: multiple uploads overwrite previous content
    - Exists checks: state reflected correctly before/after operations
    - Metadata operations: creation and retrieval
    - File operations: copy, move, delete
    - Listing: prefix filtering and pagination
    """

    @abstractmethod
    async def create_storage(self) -> IStorage:
        """Create and return an IStorage instance for testing."""

    # ===== Basic Upload/Download Tests =====

    @pytest.mark.asyncio
    async def test_upload_then_download_returns_same_content(self):
        """State consistency: upload→download returns identical content."""
        storage = await self.create_storage()
        content = b"test content with special chars: \x00\xff\xfe"

        await storage.upload("test-key", content, "application/octet-stream")
        result = await storage.download("test-key")

        assert result == content

    @pytest.mark.asyncio
    async def test_upload_multiple_times_last_write_wins(self):
        """State consistency: multiple uploads overwrite previous content."""
        storage = await self.create_storage()

        await storage.upload("test-key", b"first", "text/plain")
        await storage.upload("test-key", b"second", "text/plain")
        await storage.upload("test-key", b"third", "text/plain")

        result = await storage.download("test-key")
        assert result == b"third"

    @pytest.mark.asyncio
    async def test_upload_empty_content(self):
        """State consistency: empty content uploads and downloads correctly."""
        storage = await self.create_storage()
        content = b""

        await storage.upload("empty-key", content, "text/plain")
        result = await storage.download("empty-key")

        assert result == content
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_upload_large_content(self):
        """State consistency: large content uploads and downloads correctly."""
        storage = await self.create_storage()
        # 10 MB of content
        content = b"x" * (10 * 1024 * 1024)

        await storage.upload("large-key", content, "application/octet-stream")
        result = await storage.download("large-key")

        assert result == content
        assert len(result) == len(content)

    # ===== Error Condition Tests =====

    @pytest.mark.asyncio
    async def test_download_nonexistent_key_raises_error(self):
        """Error condition: download missing key raises ResourceNotFoundError."""
        storage = await self.create_storage()

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await storage.download("nonexistent-key")
        assert "nonexistent-key" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_then_download_raises_error(self):
        """Error condition: delete→download raises ResourceNotFoundError."""
        storage = await self.create_storage()

        await storage.upload("test-key", b"content", "text/plain")
        await storage.delete("test-key")

        with pytest.raises(ResourceNotFoundError):
            await storage.download("test-key")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key_raises_error(self):
        """Error condition: delete missing key raises ResourceNotFoundError."""
        storage = await self.create_storage()

        with pytest.raises(ResourceNotFoundError):
            await storage.delete("nonexistent-key")

    # ===== Exists Tests =====

    @pytest.mark.asyncio
    async def test_exists_returns_false_initially(self):
        """State consistency: exists returns False for new key."""
        storage = await self.create_storage()

        exists = await storage.exists("test-key")
        assert exists is False

    @pytest.mark.asyncio
    async def test_exists_returns_true_after_upload(self):
        """State consistency: exists returns True after upload."""
        storage = await self.create_storage()

        await storage.upload("test-key", b"content", "text/plain")

        exists = await storage.exists("test-key")
        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_after_delete(self):
        """State consistency: exists returns False after delete."""
        storage = await self.create_storage()

        await storage.upload("test-key", b"content", "text/plain")
        await storage.delete("test-key")

        exists = await storage.exists("test-key")
        assert exists is False

    # ===== Metadata Tests =====

    @pytest.mark.asyncio
    async def test_upload_with_metadata(self):
        """State consistency: metadata is stored and retrieved correctly."""
        storage = await self.create_storage()
        metadata = {"user": "test-user", "project": "test-project"}

        await storage.upload("test-key", b"content", "text/plain", metadata)

        retrieved = await storage.get_metadata("test-key")
        assert retrieved["metadata"] == metadata
        assert retrieved["content_type"] == "text/plain"

    @pytest.mark.asyncio
    async def test_get_metadata_nonexistent_key_raises_error(self):
        """Error condition: get_metadata missing key raises ResourceNotFoundError."""
        storage = await self.create_storage()

        with pytest.raises(ResourceNotFoundError):
            await storage.get_metadata("nonexistent-key")

    @pytest.mark.asyncio
    async def test_update_metadata_changes_stored_values(self):
        """State consistency: update_metadata overwrites previous metadata."""
        storage = await self.create_storage()

        await storage.upload("test-key", b"content", "text/plain", {"old": "value"})
        await storage.update_metadata("test-key", {"new": "value", "updated": "true"})

        retrieved = await storage.get_metadata("test-key")
        assert retrieved["metadata"] == {"new": "value", "updated": "true"}

    @pytest.mark.asyncio
    async def test_update_metadata_nonexistent_key_raises_error(self):
        """Error condition: update_metadata missing key raises ResourceNotFoundError."""
        storage = await self.create_storage()

        with pytest.raises(ResourceNotFoundError):
            await storage.update_metadata("nonexistent-key", {"key": "value"})

    # ===== Size and Content Type Tests =====

    @pytest.mark.asyncio
    async def test_get_size_returns_correct_bytes(self):
        """State consistency: get_size returns correct byte count."""
        storage = await self.create_storage()
        content = b"hello world"

        await storage.upload("test-key", content, "text/plain")

        size = await storage.get_size("test-key")
        assert size == len(content)
        assert size == 11

    @pytest.mark.asyncio
    async def test_get_size_nonexistent_key_raises_error(self):
        """Error condition: get_size missing key raises ResourceNotFoundError."""
        storage = await self.create_storage()

        with pytest.raises(ResourceNotFoundError):
            await storage.get_size("nonexistent-key")

    @pytest.mark.asyncio
    async def test_get_content_type_returns_correct_type(self):
        """State consistency: get_content_type returns uploaded content type."""
        storage = await self.create_storage()

        await storage.upload("test-key", b"content", "application/json")

        content_type = await storage.get_content_type("test-key")
        assert content_type == "application/json"

    @pytest.mark.asyncio
    async def test_get_content_type_nonexistent_key_raises_error(self):
        """Error condition: get_content_type missing key raises ResourceNotFoundError."""
        storage = await self.create_storage()

        with pytest.raises(ResourceNotFoundError):
            await storage.get_content_type("nonexistent-key")

    @pytest.mark.asyncio
    async def test_upload_defaults_content_type(self):
        """State consistency: upload without content_type defaults to application/octet-stream."""
        storage = await self.create_storage()

        await storage.upload("test-key", b"content")

        content_type = await storage.get_content_type("test-key")
        assert content_type == "application/octet-stream"

    # ===== Copy and Move Tests =====

    @pytest.mark.asyncio
    async def test_copy_creates_identical_content(self):
        """State consistency: copy creates identical content at destination."""
        storage = await self.create_storage()
        content = b"original content"

        await storage.upload("source-key", content, "text/plain")
        await storage.copy("source-key", "dest-key")

        result = await storage.download("dest-key")
        assert result == content

    @pytest.mark.asyncio
    async def test_copy_nonexistent_source_raises_error(self):
        """Error condition: copy from missing source raises ResourceNotFoundError."""
        storage = await self.create_storage()

        with pytest.raises(ResourceNotFoundError):
            await storage.copy("nonexistent-source", "dest-key")

    @pytest.mark.asyncio
    async def test_move_transfers_content_and_removes_source(self):
        """State consistency: move transfers content and removes source."""
        storage = await self.create_storage()
        content = b"original content"

        await storage.upload("source-key", content, "text/plain")
        await storage.move("source-key", "dest-key")

        # Destination should have content
        result = await storage.download("dest-key")
        assert result == content

        # Source should be gone
        assert await storage.exists("source-key") is False

    @pytest.mark.asyncio
    async def test_move_nonexistent_source_raises_error(self):
        """Error condition: move from missing source raises ResourceNotFoundError."""
        storage = await self.create_storage()

        with pytest.raises(ResourceNotFoundError):
            await storage.move("nonexistent-source", "dest-key")

    # ===== List Files Tests =====

    @pytest.mark.asyncio
    async def test_list_files_empty_storage(self):
        """State consistency: list_files returns empty list for empty storage."""
        storage = await self.create_storage()

        files = await storage.list_files()
        assert files == []

    @pytest.mark.asyncio
    async def test_list_files_returns_all_objects(self):
        """State consistency: list_files returns all uploaded objects."""
        storage = await self.create_storage()

        await storage.upload("key-1", b"content1", "text/plain")
        await storage.upload("key-2", b"content2", "text/plain")
        await storage.upload("key-3", b"content3", "text/plain")

        files = await storage.list_files()
        assert len(files) == 3
        keys = {f.key for f in files}
        assert keys == {"key-1", "key-2", "key-3"}

    @pytest.mark.asyncio
    async def test_list_files_with_prefix(self):
        """State consistency: list_files filters by prefix correctly."""
        storage = await self.create_storage()

        await storage.upload("project-1/file-1", b"content1", "text/plain")
        await storage.upload("project-1/file-2", b"content2", "text/plain")
        await storage.upload("project-2/file-1", b"content3", "text/plain")

        files = await storage.list_files(prefix="project-1/")
        assert len(files) == 2
        keys = {f.key for f in files}
        assert keys == {"project-1/file-1", "project-1/file-2"}

    @pytest.mark.asyncio
    async def test_list_files_pagination(self):
        """State consistency: list_files respects limit and offset."""
        storage = await self.create_storage()

        for i in range(10):
            await storage.upload(f"key-{i:02d}", b"content", "text/plain")

        # First page
        files = await storage.list_files(limit=3, offset=0)
        assert len(files) == 3

        # Second page
        files = await storage.list_files(limit=3, offset=3)
        assert len(files) == 3

        # Last page (only 1 item)
        files = await storage.list_files(limit=3, offset=9)
        assert len(files) == 1

    # ===== Delete Many Tests =====

    @pytest.mark.asyncio
    async def test_delete_many_removes_all_files(self):
        """State consistency: delete_many removes all specified files."""
        storage = await self.create_storage()

        await storage.upload("key-1", b"content1", "text/plain")
        await storage.upload("key-2", b"content2", "text/plain")
        await storage.upload("key-3", b"content3", "text/plain")

        await storage.delete_many(["key-1", "key-2"])

        assert await storage.exists("key-1") is False
        assert await storage.exists("key-2") is False
        assert await storage.exists("key-3") is True

    @pytest.mark.asyncio
    async def test_delete_many_empty_list(self):
        """State consistency: delete_many with empty list does nothing."""
        storage = await self.create_storage()

        await storage.upload("key-1", b"content1", "text/plain")
        await storage.delete_many([])

        assert await storage.exists("key-1") is True

    # ===== Upload/Download From File Tests =====

    @pytest.mark.asyncio
    async def test_upload_from_file(self):
        """State consistency: upload_from_file transfers file content."""
        storage = await self.create_storage()

        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_content = b"file content here"
            file_path.write_bytes(file_content)

            await storage.upload_from_file("test-key", file_path, "text/plain")

            result = await storage.download("test-key")
            assert result == file_content

    @pytest.mark.asyncio
    async def test_upload_from_file_nonexistent_raises_error(self):
        """Error condition: upload_from_file with missing file raises error."""
        storage = await self.create_storage()

        with pytest.raises(ResourceNotFoundError):
            await storage.upload_from_file("test-key", Path("/nonexistent/file.txt"))

    @pytest.mark.asyncio
    async def test_download_to_file(self):
        """State consistency: download_to_file creates file with correct content."""
        storage = await self.create_storage()
        content = b"downloaded content"

        await storage.upload("test-key", content, "text/plain")

        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "downloaded.txt"
            await storage.download_to_file("test-key", file_path)

            assert file_path.exists()
            assert file_path.read_bytes() == content

    @pytest.mark.asyncio
    async def test_download_to_file_nonexistent_key_raises_error(self):
        """Error condition: download_to_file for missing key raises error."""
        storage = await self.create_storage()

        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "downloaded.txt"

            with pytest.raises(ResourceNotFoundError):
                await storage.download_to_file("nonexistent-key", file_path)

    # ===== List Prefixes Tests =====

    @pytest.mark.asyncio
    async def test_list_prefixes_hierarchical_structure(self):
        """State consistency: list_prefixes discovers directory-like structure."""
        storage = await self.create_storage()

        await storage.upload("projects/proj-1/file-1", b"content", "text/plain")
        await storage.upload("projects/proj-1/file-2", b"content", "text/plain")
        await storage.upload("projects/proj-2/file-1", b"content", "text/plain")
        await storage.upload("artifacts/artifact-1", b"content", "text/plain")

        prefixes = await storage.list_prefixes()
        # Should find top-level prefixes
        assert "projects/" in prefixes
        assert "artifacts/" in prefixes

    @pytest.mark.asyncio
    async def test_list_prefixes_with_starting_prefix(self):
        """State consistency: list_prefixes with prefix parameter filters correctly."""
        storage = await self.create_storage()

        await storage.upload("projects/proj-1/file-1", b"content", "text/plain")
        await storage.upload("projects/proj-1/file-2", b"content", "text/plain")
        await storage.upload("projects/proj-2/file-1", b"content", "text/plain")

        prefixes = await storage.list_prefixes(prefix="projects/")
        # Should find project prefixes
        assert any("proj-1" in p for p in prefixes)
        assert any("proj-2" in p for p in prefixes)

    # ===== Storage Info Tests =====

    @pytest.mark.asyncio
    async def test_get_storage_info_returns_stats(self):
        """State consistency: get_storage_info returns accurate statistics."""
        storage = await self.create_storage()

        await storage.upload("key-1", b"12345", "text/plain")
        await storage.upload("key-2", b"1234567890", "text/plain")

        info = await storage.get_storage_info()
        assert info["object_count"] == 2
        assert info["total_size_bytes"] == 15  # 5 + 10
        assert "provider" in info

    # ===== Presigned URL Tests =====

    @pytest.mark.asyncio
    async def test_generate_presigned_url_returns_string(self):
        """State consistency: generate_presigned_url returns a non-empty string for existing key."""
        storage = await self.create_storage()

        await storage.upload("test-key", b"content", "text/plain")

        # Presigned URL should be a non-empty string
        url = await storage.generate_presigned_url("test-key", expires_in=3600)
        assert isinstance(url, str)
        assert len(url) > 0

    @pytest.mark.asyncio
    async def test_generate_presigned_url_nonexistent_key_raises_error(self):
        """Error condition: generate_presigned_url for missing key raises ResourceNotFoundError."""
        storage = await self.create_storage()

        with pytest.raises(ResourceNotFoundError):
            await storage.generate_presigned_url("nonexistent-key", expires_in=3600)
