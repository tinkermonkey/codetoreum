"""In-memory implementation of IPipelineQueue for testing."""

from codetoreum.ports.output.pipeline_queue import (
    EnqueueResult,
    IPipelineQueue,
    QueueEntry,
)


class InMemoryPipelineQueue(IPipelineQueue):
    """In-memory pipeline queue implementation for testing."""

    def __init__(self):
        """Initialize the queue service."""
        self._queues: dict[str, list[QueueEntry]] = {}

    async def enqueue(
        self,
        queue_key: str,
        entry: QueueEntry,
    ) -> EnqueueResult:
        """Add an entry to the queue."""
        if queue_key not in self._queues:
            self._queues[queue_key] = []

        queue = self._queues[queue_key]

        # Check if already present (idempotent)
        for i, existing_entry in enumerate(queue):
            if existing_entry.work_item_id == entry.work_item_id:
                return EnqueueResult(position=i, already_present=True)

        # Add to queue
        queue.append(entry)
        position = len(queue) - 1
        return EnqueueResult(position=position, already_present=False)

    async def peek(self, queue_key: str) -> QueueEntry | None:
        """Get the head entry without removing."""
        if queue_key not in self._queues or not self._queues[queue_key]:
            return None
        return self._queues[queue_key][0]

    async def pop(self, queue_key: str) -> QueueEntry | None:
        """Remove and return the head entry."""
        if queue_key not in self._queues or not self._queues[queue_key]:
            return None
        return self._queues[queue_key].pop(0)

    async def contains(self, queue_key: str, work_item_id: str) -> bool:
        """Check if a work item is in the queue."""
        if queue_key not in self._queues:
            return False
        return any(entry.work_item_id == work_item_id for entry in self._queues[queue_key])

    async def remove(self, queue_key: str, work_item_id: str) -> bool:
        """Remove a specific entry by work_item_id."""
        if queue_key not in self._queues:
            return False

        queue = self._queues[queue_key]
        for i, entry in enumerate(queue):
            if entry.work_item_id == work_item_id:
                queue.pop(i)
                return True
        return False

    async def length(self, queue_key: str) -> int:
        """Return queue depth."""
        if queue_key not in self._queues:
            return 0
        return len(self._queues[queue_key])

    async def list(self, queue_key: str) -> list[QueueEntry]:
        """Return all entries in FIFO order."""
        if queue_key not in self._queues:
            return []
        return list(self._queues[queue_key])

    async def position_of(self, queue_key: str, work_item_id: str) -> int | None:
        """Return 0-indexed position of work_item_id."""
        if queue_key not in self._queues:
            return None

        for i, entry in enumerate(self._queues[queue_key]):
            if entry.work_item_id == work_item_id:
                return i
        return None
