"""Comprehensive error handling tests for mock adapters.

Tests verify that adapters properly raise ResourceNotFoundError for missing resources,
matching production adapter behavior and ensuring error handling code is tested realistically.
"""

import pytest
from pathlib import Path

from codetoreum.adapters.testing import InMemoryRepositoryAdapter
from codetoreum.adapters.testing.in_memory_storage_adapter import InMemoryStorageAdapter
from codetoreum.adapters.testing.mock_board_adapter import MockBoardAdapter
from codetoreum.ports.exceptions import ResourceNotFoundError
from codetoreum.ports.output.board_service import MovedByType


@pytest.mark.asyncio
class TestRepositoryAdapterErrorHandling:
    """Tests for InMemoryRepositoryAdapter error handling."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        return InMemoryRepositoryAdapter()

    async def test_get_file_content_missing_file_raises_error(self, adapter):
        """Test that getting non-existent file raises ResourceNotFoundError."""
        # Setup: Create a repository
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Act & Assert: Request non-existent file should raise error
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.get_file_content(
                repo_path=Path("/tmp/test-repo"),
                file_path="nonexistent.py",
            )

        error = exc_info.value
        assert "nonexistent.py" in str(error)
        assert error.resource_id is not None

    async def test_get_file_content_error_message_includes_details(self, adapter):
        """Test that error message includes file path and repository context."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.get_file_content(
                repo_path=Path("/tmp/test-repo"),
                file_path="src/utils/helpers.py",
            )

        error_message = str(exc_info.value)
        assert "helpers.py" in error_message or "src" in error_message

    async def test_get_file_content_with_specific_ref(self, adapter):
        """Test error handling when file missing at specific ref."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Try to get file at non-existent ref
        with pytest.raises(ResourceNotFoundError):
            await adapter.get_file_content(
                repo_path=Path("/tmp/test-repo"),
                file_path="config.json",
                ref="v1.0.0",  # Tag that doesn't exist in test adapter
            )

    async def test_get_file_content_existing_file_succeeds(self, adapter):
        """Test that existing file is retrieved successfully (positive case)."""
        await adapter.clone(
            url="https://github.com/test/repo.git",
            destination=Path("/tmp/test-repo"),
        )

        # Set file content
        adapter.set_file_content(
            repo_path=Path("/tmp/test-repo"),
            file_path="README.md",
            content="# My Project",
        )

        # Should succeed
        content = await adapter.get_file_content(
            repo_path=Path("/tmp/test-repo"),
            file_path="README.md",
        )

        assert content == "# My Project"


@pytest.mark.asyncio
class TestStorageAdapterErrorHandling:
    """Tests for InMemoryStorageAdapter error handling."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        return InMemoryStorageAdapter()

    async def test_download_missing_artifact_raises_error(self, adapter):
        """Test that downloading non-existent artifact raises ResourceNotFoundError."""
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.download("nonexistent-artifact-key")

        error = exc_info.value
        assert "nonexistent-artifact-key" in str(error)
        assert error.resource_id is not None

    async def test_download_error_includes_artifact_key(self, adapter):
        """Test that error message includes the artifact key for debugging."""
        artifact_key = "project-1/build-output/app.tar.gz"

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.download(artifact_key)

        error_message = str(exc_info.value)
        assert artifact_key in error_message or "app.tar.gz" in error_message

    async def test_delete_missing_artifact_raises_error(self, adapter):
        """Test that deleting non-existent artifact raises ResourceNotFoundError."""
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.delete("missing-artifact")

        error = exc_info.value
        assert "missing-artifact" in str(error)
        assert error.resource_id is not None

    async def test_download_existing_artifact_succeeds(self, adapter):
        """Test that existing artifact can be downloaded successfully."""
        # Upload an artifact
        content = b"test content for artifact"
        await adapter.upload("my-artifact", content)

        # Should be able to download it
        downloaded = await adapter.download("my-artifact")
        assert downloaded == content

    async def test_upload_and_download_roundtrip(self, adapter):
        """Test that uploaded artifacts can be retrieved exactly."""
        key = "project-1/build/output.zip"
        original_content = b"Binary content of output file"

        await adapter.upload(key, original_content)
        retrieved_content = await adapter.download(key)

        assert retrieved_content == original_content

    async def test_delete_then_download_fails(self, adapter):
        """Test that deleted artifacts cannot be downloaded."""
        key = "temp-artifact"
        await adapter.upload(key, b"temporary data")

        # Delete it
        await adapter.delete(key)

        # Should not be able to download
        with pytest.raises(ResourceNotFoundError):
            await adapter.download(key)


@pytest.mark.asyncio
class TestBoardAdapterErrorHandling:
    """Tests for MockBoardAdapter error handling."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        adapter = MockBoardAdapter()
        adapter.current_project = "proj-1"
        return adapter

    async def test_get_item_position_missing_item_raises_error(self, adapter):
        """Test that getting position of non-existent item raises ResourceNotFoundError."""
        adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "Done"])

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.get_item_position("nonexistent-item-id")

        error = exc_info.value
        assert "nonexistent-item-id" in str(error)
        assert error.resource_id is not None

    async def test_get_item_position_error_includes_item_id(self, adapter):
        """Test that error message includes the item ID."""
        adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "Done"])

        item_id = "work-item-12345"
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.get_item_position(item_id)

        error_message = str(exc_info.value)
        assert item_id in error_message

    async def test_move_item_missing_work_item_raises_error(self, adapter):
        """Test that moving non-existent item raises ResourceNotFoundError."""
        adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "In Progress"])

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.move_item_to_column(
                "nonexistent-item",
                "In Progress",
                MovedByType.ORCHESTRATOR
            )

        error = exc_info.value
        assert "nonexistent-item" in str(error)
        assert error.resource_id is not None

    async def test_move_item_missing_column_raises_error(self, adapter):
        """Test that moving to non-existent column raises ResourceNotFoundError."""
        adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "Done"])
        adapter.add_item_to_column("board-1", "Backlog", "item-1")

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await adapter.move_item_to_column(
                "item-1",
                "NonExistentColumn",
                MovedByType.ORCHESTRATOR
            )

        error = exc_info.value
        assert "NonExistentColumn" in str(error)
        assert error.resource_id is not None

    async def test_get_item_position_with_existing_item_succeeds(self, adapter):
        """Test that existing item position can be retrieved."""
        adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "Done"])
        adapter.add_item_to_column("board-1", "Backlog", "item-1")

        position = await adapter.get_item_position("item-1")

        assert position.work_item_id == "item-1"
        assert position.column_name == "Backlog"
        assert position.position == 0

    async def test_move_item_to_existing_column_succeeds(self, adapter):
        """Test that item can be moved to existing column."""
        adapter.create_board("proj-1", "board-1", "Test Board", ["Backlog", "In Progress", "Done"])
        adapter.add_item_to_column("board-1", "Backlog", "item-1")

        result = await adapter.move_item_to_column(
            "item-1",
            "In Progress",
            MovedByType.ORCHESTRATOR
        )

        assert result.work_item_id == "item-1"
        assert result.to_column == "In Progress"

        # Verify position updated
        position = await adapter.get_item_position("item-1")
        assert position.column_name == "In Progress"
