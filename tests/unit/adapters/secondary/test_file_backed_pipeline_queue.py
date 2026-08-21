"""Tests for FileBackedPipelineQueue implementation.

Concrete implementation of TestPipelineQueueContract using the
file-backed adapter.
"""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

import pytest

from codetoreum.adapters.secondary.file_backed_pipeline_queue import FileBackedPipelineQueue
from tests.unit.ports.output.test_pipeline_queue_contract import TestPipelineQueueContract


class TestFileBackedPipelineQueue(TestPipelineQueueContract):
    """Test FileBackedPipelineQueue against the contract."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Set up and tear down test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.queue_file = Path(self.temp_dir) / "test_queue.jsonl"
        yield
        # Cleanup
        if self.queue_file.exists():
            self.queue_file.unlink()
        if self.queue_file.with_suffix(".jsonl.lock").exists():
            self.queue_file.with_suffix(".jsonl.lock").unlink()

    async def create_queue(self) -> FileBackedPipelineQueue:
        """Create a FileBackedPipelineQueue instance."""
        return FileBackedPipelineQueue(file_path=str(self.queue_file))

    @pytest.mark.asyncio
    async def test_persistence_across_instances(self):
        """Queue state should persist across instance creation."""
        from codetoreum.ports.output.pipeline_queue import QueueEntry

        now = datetime.now(UTC)

        # Create first instance and add items
        queue1 = await self.create_queue()
        entry1 = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))
        entry2 = QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({}))

        await queue1.enqueue("queue-1", entry1)
        await queue1.enqueue("queue-1", entry2)

        # Delete queue1 to release the PID lockfile
        del queue1

        # Create second instance from same file
        queue2 = FileBackedPipelineQueue(file_path=str(self.queue_file))

        # Should see the items
        entries = await queue2.list("queue-1")
        assert len(entries) == 2
        assert entries[0].work_item_id == "item-1"
        assert entries[1].work_item_id == "item-2"

    @pytest.mark.asyncio
    async def test_smoke_test_file_operations(self):
        """Smoke test: write state, terminate, restart, verify state preserved."""
        from codetoreum.ports.output.pipeline_queue import QueueEntry

        now = datetime.now(UTC)

        # Initial setup
        queue1 = await self.create_queue()

        # Perform operations
        entry1 = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))
        entry2 = QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({}))
        entry3 = QueueEntry("item-3", "In Progress", 2, now, MappingProxyType({}))

        await queue1.enqueue("queue-1", entry1)
        await queue1.enqueue("queue-1", entry2)
        await queue1.enqueue("queue-1", entry3)

        # Pop one
        await queue1.pop("queue-1")

        # Verify state
        length = await queue1.length("queue-1")
        assert length == 2

        # Delete queue1 to release the PID lockfile
        del queue1

        # Simulate process restart by creating new instance
        queue2 = FileBackedPipelineQueue(file_path=str(self.queue_file))

        # Verify state is preserved
        entries_after_restart = await queue2.list("queue-1")
        assert len(entries_after_restart) == 2
        assert entries_after_restart[0].work_item_id == "item-2"
        assert entries_after_restart[1].work_item_id == "item-3"

    @pytest.mark.asyncio
    async def test_single_process_guard(self):
        """Second process should fail to acquire lock."""
        # First instance
        queue1 = FileBackedPipelineQueue(file_path=str(self.queue_file))

        # Second instance should fail
        with pytest.raises(RuntimeError, match="already in use"):
            FileBackedPipelineQueue(file_path=str(self.queue_file))

    @pytest.mark.asyncio
    async def test_file_format_jsonl(self):
        """File should be in JSONL format."""
        from codetoreum.ports.output.pipeline_queue import QueueEntry

        now = datetime.now(UTC)
        queue = await self.create_queue()

        # Write some entries
        entry1 = QueueEntry("item-1", "In Progress", 0, now, {"meta": "data"})
        entry2 = QueueEntry("item-2", "In Progress", 1, now, MappingProxyType({}))

        await queue.enqueue("queue-1", entry1)
        await queue.enqueue("queue-1", entry2)
        await queue.pop("queue-1")

        # Read and verify JSONL format
        with open(self.queue_file) as f:
            lines = f.readlines()

        # Each line should be valid JSON
        for line in lines:
            if line.strip():
                entry = json.loads(line)
                assert "type" in entry
                assert entry["type"] in ("enqueued", "dequeued")

    @pytest.mark.asyncio
    async def test_multiple_independent_queues(self):
        """Different queue keys should be independent."""
        from codetoreum.ports.output.pipeline_queue import QueueEntry

        now = datetime.now(UTC)
        queue = await self.create_queue()

        # Add to different queues
        entry1 = QueueEntry("item-1", "In Progress", 0, now, MappingProxyType({}))
        entry2 = QueueEntry("item-2", "In Progress", 0, now, MappingProxyType({}))
        entry3 = QueueEntry("item-3", "In Progress", 0, now, MappingProxyType({}))

        await queue.enqueue("queue-a", entry1)
        await queue.enqueue("queue-b", entry2)
        await queue.enqueue("queue-a", entry3)

        # Verify independence
        queue_a = await queue.list("queue-a")
        queue_b = await queue.list("queue-b")

        assert len(queue_a) == 2
        assert len(queue_b) == 1
        assert queue_a[0].work_item_id == "item-1"
        assert queue_a[1].work_item_id == "item-3"
        assert queue_b[0].work_item_id == "item-2"
