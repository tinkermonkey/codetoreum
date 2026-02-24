"""Unit tests for domain event emission in core simulation adapters.

Tests verify that InMemoryQueueService, InMemoryRepositoryAdapter, and
InMemoryStorageAdapter emit appropriate domain events for all state-changing
operations, establishing complete event sourcing audit trail for simulation testing.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from codetoreum.adapters.testing.in_memory_queue_service import InMemoryQueueService
from codetoreum.adapters.testing.in_memory_repository_adapter import InMemoryRepositoryAdapter
from codetoreum.adapters.testing.in_memory_storage_adapter import InMemoryStorageAdapter
from codetoreum.adapters.testing.capturing_mock_event_emitter import CapturingMockEventEmitter
from codetoreum.domain.events.queue_events import (
    QueueItemAddedEvent,
    QueueItemRemovedEvent,
    QueuePositionChangedEvent,
)
from codetoreum.domain.events.repository_events import (
    CommitCreatedEvent,
    BranchCreatedEvent,
    FilesStagedEvent,
)
from codetoreum.domain.events.storage_events import (
    ArtifactUploadedEvent,
    ArtifactDeletedEvent,
)
from codetoreum.ports.output.pipeline_queue_service import QueueStatus
from codetoreum.domain.types import BranchName, CommitHash


class TestQueueServiceEventEmission:
    """Tests for domain event emission in InMemoryQueueService."""

    @pytest.fixture
    def emitter(self):
        """Create a fresh event emitter for each test."""
        return CapturingMockEventEmitter()

    @pytest.fixture
    def queue_service(self, emitter):
        """Create a queue service with event emitter."""
        return InMemoryQueueService(event_emitter=emitter)

    @pytest.mark.asyncio
    async def test_enqueue_item_emits_queue_item_added_event(self, queue_service, emitter):
        """Enqueuing item should emit QueueItemAddedEvent."""
        now = datetime.now(timezone.utc)

        await queue_service.enqueue_item(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            position_in_column=0,
            timestamp=now,
        )

        events = emitter.get_events_by_type("queue.item_added")
        assert len(events) == 1

        event = events[0]
        assert event.type == "queue.item_added"
        assert event.queue_name == "proj-1:board-1"
        assert event.item_id == "item-1"
        assert event.position == 0
        assert event.project_id == "proj-1"
        assert event.event_id is not None
        assert event.timestamp is not None

    @pytest.mark.asyncio
    async def test_remove_from_queue_emits_queue_item_removed_event(self, queue_service, emitter):
        """Removing item from queue should emit QueueItemRemovedEvent."""
        now = datetime.now(timezone.utc)

        # Enqueue an item first
        await queue_service.enqueue_item(
            project_id="proj-1",
            board_id="board-1",
            work_item_id="item-1",
            position_in_column=0,
            timestamp=now,
        )

        # Clear previous events
        emitter.clear_events()

        # Remove the item
        removed = await queue_service.remove_from_queue("item-1")
        assert removed is True

        events = emitter.get_events_by_type("queue.item_removed")
        assert len(events) == 1

        event = events[0]
        assert event.type == "queue.item_removed"
        assert event.queue_name == "proj-1:board-1"
        assert event.item_id == "item-1"
        assert event.project_id == "proj-1"

    @pytest.mark.asyncio
    async def test_enqueue_multiple_items_emits_multiple_events(self, queue_service, emitter):
        """Enqueuing multiple items should emit multiple events."""
        now = datetime.now(timezone.utc)

        for i in range(3):
            await queue_service.enqueue_item(
                project_id="proj-1",
                board_id="board-1",
                work_item_id=f"item-{i}",
                position_in_column=i,
                timestamp=now,
            )

        events = emitter.get_events_by_type("queue.item_added")
        assert len(events) == 3

        # Verify each event has correct item_id
        item_ids = {event.item_id for event in events}
        assert item_ids == {"item-0", "item-1", "item-2"}


class TestRepositoryAdapterEventEmission:
    """Tests for domain event emission in InMemoryRepositoryAdapter."""

    @pytest.fixture
    def emitter(self):
        """Create a fresh event emitter for each test."""
        return CapturingMockEventEmitter()

    @pytest.fixture
    def repo_adapter(self, emitter):
        """Create a repository adapter with event emitter."""
        return InMemoryRepositoryAdapter(event_emitter=emitter)

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary directory for testing."""
        return tmp_path

    @pytest.mark.asyncio
    async def test_commit_emits_commit_created_event(self, repo_adapter, emitter, temp_dir):
        """Creating a commit should emit CommitCreatedEvent."""
        # Clone a repo first
        repo_id = await repo_adapter.clone(
            url="https://example.com/repo.git",
            destination=temp_dir / "repo",
        )

        # Clear initial events (from clone)
        emitter.clear_events()

        # Create a commit
        commit_sha = await repo_adapter.commit(
            repo_path=temp_dir / "repo",
            message="Test commit",
            author_name="Test Author",
            author_email="test@example.com",
            files=["src/main.py", "tests/test_main.py"],
        )

        events = emitter.get_events_by_type("repository.commit_created")
        assert len(events) == 1

        event = events[0]
        assert event.type == "repository.commit_created"
        assert event.repository_id == str(repo_id)
        assert event.commit_sha == str(commit_sha)
        assert event.message == "Test commit"
        assert event.author == "Test Author <test@example.com>"
        assert set(event.changed_files) == {"src/main.py", "tests/test_main.py"}

    @pytest.mark.asyncio
    async def test_commit_emits_files_staged_event(self, repo_adapter, emitter, temp_dir):
        """Creating a commit with files should emit FilesStagedEvent."""
        # Clone a repo first
        repo_id = await repo_adapter.clone(
            url="https://example.com/repo.git",
            destination=temp_dir / "repo",
        )

        # Clear initial events
        emitter.clear_events()

        # Create a commit with files
        await repo_adapter.commit(
            repo_path=temp_dir / "repo",
            message="Test commit",
            author_name="Test Author",
            author_email="test@example.com",
            files=["src/main.py", "tests/test_main.py"],
        )

        events = emitter.get_events_by_type("repository.files_staged")
        assert len(events) == 1

        event = events[0]
        assert event.type == "repository.files_staged"
        assert event.repository_id == str(repo_id)
        assert set(event.file_paths) == {"src/main.py", "tests/test_main.py"}

    @pytest.mark.asyncio
    async def test_create_branch_emits_branch_created_event(self, repo_adapter, emitter, temp_dir):
        """Creating a branch should emit BranchCreatedEvent."""
        # Clone a repo first
        repo_id = await repo_adapter.clone(
            url="https://example.com/repo.git",
            destination=temp_dir / "repo",
        )

        # Clear initial events
        emitter.clear_events()

        # Create a branch
        await repo_adapter.create_branch(
            repo_path=temp_dir / "repo",
            branch_name=BranchName("feature/test"),
            from_branch=BranchName("main"),
        )

        events = emitter.get_events_by_type("repository.branch_created")
        assert len(events) == 1

        event = events[0]
        assert event.type == "repository.branch_created"
        assert event.repository_id == str(repo_id)
        assert event.branch_name == "feature/test"
        assert event.base_commit is not None  # Should have the base commit SHA

    @pytest.mark.asyncio
    async def test_commit_without_files_does_not_emit_files_staged(self, repo_adapter, emitter, temp_dir):
        """Creating a commit without files should not emit FilesStagedEvent."""
        # Clone a repo first
        await repo_adapter.clone(
            url="https://example.com/repo.git",
            destination=temp_dir / "repo",
        )

        # Clear initial events
        emitter.clear_events()

        # Create a commit without files
        await repo_adapter.commit(
            repo_path=temp_dir / "repo",
            message="Test commit",
            author_name="Test Author",
            author_email="test@example.com",
            files=None,
        )

        events = emitter.get_events_by_type("repository.files_staged")
        assert len(events) == 0


class TestStorageAdapterEventEmission:
    """Tests for domain event emission in InMemoryStorageAdapter."""

    @pytest.fixture
    def emitter(self):
        """Create a fresh event emitter for each test."""
        return CapturingMockEventEmitter()

    @pytest.fixture
    def storage_adapter(self, emitter):
        """Create a storage adapter with event emitter."""
        return InMemoryStorageAdapter(event_emitter=emitter)

    @pytest.mark.asyncio
    async def test_upload_emits_artifact_uploaded_event(self, storage_adapter, emitter):
        """Uploading an artifact should emit ArtifactUploadedEvent."""
        content = b"Test content"

        await storage_adapter.upload(
            key="projects/proj-1/artifacts/output.txt",
            content=content,
            content_type="text/plain",
            metadata={"source": "test"},
        )

        events = emitter.get_events_by_type("storage.artifact_uploaded")
        assert len(events) == 1

        event = events[0]
        assert event.type == "storage.artifact_uploaded"
        assert event.key == "projects/proj-1/artifacts/output.txt"
        assert event.size_bytes == len(content)
        assert event.content_type == "text/plain"
        assert event.event_id is not None
        assert event.timestamp is not None

    @pytest.mark.asyncio
    async def test_delete_emits_artifact_deleted_event(self, storage_adapter, emitter):
        """Deleting an artifact should emit ArtifactDeletedEvent."""
        # Upload first
        await storage_adapter.upload(
            key="projects/proj-1/artifacts/output.txt",
            content=b"Test content",
            content_type="text/plain",
        )

        # Clear events
        emitter.clear_events()

        # Delete the artifact
        await storage_adapter.delete("projects/proj-1/artifacts/output.txt")

        events = emitter.get_events_by_type("storage.artifact_deleted")
        assert len(events) == 1

        event = events[0]
        assert event.type == "storage.artifact_deleted"
        assert event.key == "projects/proj-1/artifacts/output.txt"

    @pytest.mark.asyncio
    async def test_delete_many_emits_multiple_artifact_deleted_events(self, storage_adapter, emitter):
        """Deleting multiple artifacts should emit multiple events."""
        # Upload multiple artifacts
        for i in range(3):
            await storage_adapter.upload(
                key=f"projects/proj-1/artifacts/file-{i}.txt",
                content=b"Test content",
                content_type="text/plain",
            )

        # Clear events
        emitter.clear_events()

        # Delete multiple artifacts
        await storage_adapter.delete_many([
            "projects/proj-1/artifacts/file-0.txt",
            "projects/proj-1/artifacts/file-1.txt",
            "projects/proj-1/artifacts/file-2.txt",
        ])

        events = emitter.get_events_by_type("storage.artifact_deleted")
        assert len(events) == 3

        keys = {event.key for event in events}
        assert keys == {
            "projects/proj-1/artifacts/file-0.txt",
            "projects/proj-1/artifacts/file-1.txt",
            "projects/proj-1/artifacts/file-2.txt",
        }

    @pytest.mark.asyncio
    async def test_upload_multiple_artifacts_emits_multiple_events(self, storage_adapter, emitter):
        """Uploading multiple artifacts should emit multiple events."""
        for i in range(3):
            await storage_adapter.upload(
                key=f"projects/proj-1/artifacts/file-{i}.txt",
                content=f"Content {i}".encode(),
                content_type="text/plain",
            )

        events = emitter.get_events_by_type("storage.artifact_uploaded")
        assert len(events) == 3

        keys = {event.key for event in events}
        assert keys == {
            "projects/proj-1/artifacts/file-0.txt",
            "projects/proj-1/artifacts/file-1.txt",
            "projects/proj-1/artifacts/file-2.txt",
        }

    @pytest.mark.asyncio
    async def test_copy_artifact_emits_upload_event(self, storage_adapter, emitter):
        """Copying an artifact should emit ArtifactUploadedEvent."""
        # Upload first
        await storage_adapter.upload(
            key="projects/proj-1/artifacts/source.txt",
            content=b"Test content",
            content_type="text/plain",
        )

        # Clear events
        emitter.clear_events()

        # Copy the artifact
        await storage_adapter.copy(
            source_key="projects/proj-1/artifacts/source.txt",
            destination_key="projects/proj-1/artifacts/destination.txt",
        )

        events = emitter.get_events_by_type("storage.artifact_uploaded")
        assert len(events) == 1

        event = events[0]
        assert event.key == "projects/proj-1/artifacts/destination.txt"
        assert event.size_bytes == len(b"Test content")


class TestEventImmutability:
    """Tests for event immutability (frozen dataclasses)."""

    @pytest.fixture
    def emitter(self):
        """Create a fresh event emitter for each test."""
        return CapturingMockEventEmitter()

    @pytest.mark.asyncio
    async def test_queue_item_added_event_is_immutable(self, emitter):
        """QueueItemAddedEvent should be immutable."""
        event = QueueItemAddedEvent(
            type="queue.item_added",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="mock",
            queue_name="queue-1",
            item_id="item-1",
            position=0,
            project_id="proj-1",
        )

        # Attempt to modify should raise error
        with pytest.raises(Exception):  # FrozenInstanceError
            event.position = 5

    def test_commit_created_event_is_immutable(self):
        """CommitCreatedEvent should be immutable."""
        event = CommitCreatedEvent(
            type="repository.commit_created",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="mock",
            repository_id="repo-1",
            commit_sha="abc123",
            message="Test commit",
            author="Test Author",
            changed_files=("src/main.py",),
            project_id="proj-1",
        )

        # Attempt to modify should raise error
        with pytest.raises(Exception):  # FrozenInstanceError
            event.commit_sha = "def456"

    def test_artifact_uploaded_event_is_immutable(self):
        """ArtifactUploadedEvent should be immutable."""
        event = ArtifactUploadedEvent(
            type="storage.artifact_uploaded",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="mock",
            key="artifact-1",
            size_bytes=1024,
            content_type="text/plain",
            project_id="proj-1",
        )

        # Attempt to modify should raise error
        with pytest.raises(Exception):  # FrozenInstanceError
            event.size_bytes = 2048
