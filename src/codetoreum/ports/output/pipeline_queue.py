"""Pipeline queue service port interface for work item coordination.

This interface defines contracts for a FIFO queue of work items waiting on a
coordinated resource. The queue knows nothing about locks. A queue has a key
and an ordered list of entries; operations are atomic at the storage layer.

Production implementation: RedisPipelineQueue (sorted set + sibling metadata hash).
Local-dev / harness: FileBackedPipelineQueue (JSONL + fsync).

The adapter emits WorkItemQueuedEvent on fresh enqueues and
WorkItemDequeuedEvent on pop/remove. These events are used by metrics
and diagnostics; the orchestrator's primary trigger for state transitions
is the lock's events (PipelineLockAcquiredEvent / PipelineLockReleasedEvent).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class QueueEntry:
    """Represents an entry in a pipeline queue.

    Tracks a work item waiting on a coordinated resource with metadata
    about its position and enqueue time.

    Attributes:
        work_item_id: Unique identifier of the work item.
        stage_name: Name of the stage the work item is in.
        board_position: Position on the external board at enqueue time.
        enqueued_at: ISO 8601 timestamp when item was enqueued.
        metadata: Opaque dict; surfaces in events. Codetoreum stashes
                 project_id, board_id, etc.
    """

    work_item_id: str
    stage_name: str
    board_position: int
    enqueued_at: datetime
    metadata: dict[str, str]

    def __post_init__(self) -> None:
        """Validate all fields at construction time."""
        if not isinstance(self.work_item_id, str) or not self.work_item_id:
            msg = "work_item_id must be a non-empty string"
            raise ValueError(msg)

        if not isinstance(self.stage_name, str):
            msg = "stage_name must be a string"
            raise ValueError(msg)

        if not isinstance(self.board_position, int) or self.board_position < 0:
            msg = "board_position must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.enqueued_at, datetime):
            msg = "enqueued_at must be a datetime object"
            raise ValueError(msg)

        if not isinstance(self.metadata, dict):
            msg = "metadata must be a dict"
            raise ValueError(msg)


@dataclass(frozen=True)
class EnqueueResult:
    """Result of an enqueue operation."""

    position: int
    already_present: bool

    def __post_init__(self) -> None:
        """Validate result."""
        if not isinstance(self.position, int) or self.position < 0:
            msg = "position must be a non-negative integer"
            raise ValueError(msg)

        if not isinstance(self.already_present, bool):
            msg = "already_present must be a boolean"
            raise ValueError(msg)


class IPipelineQueue(ABC):
    """FIFO queue of work items waiting on a coordinated resource.

    Knows nothing about locks. A queue has a key and an ordered list of
    entries; operations are atomic at the storage layer.

    Example:
        # Enqueue an item
        result = await queue.enqueue(
            queue_key="proj-1:board-1",
            entry=QueueEntry(
                work_item_id="item-123",
                stage_name="In Progress",
                board_position=0,
                enqueued_at=datetime.now(UTC),
                metadata={"project_id": "proj-1", "board_id": "board-1"}
            )
        )

        if not result.already_present:
            # Item was added to queue at result.position
            pass

        # Peek at head without removing
        head = await queue.peek("proj-1:board-1")
        if head:
            # Process head.work_item_id
            pass

        # Pop when done
        await queue.pop("proj-1:board-1")
    """

    @abstractmethod
    async def enqueue(
        self,
        queue_key: str,
        entry: QueueEntry,
    ) -> EnqueueResult:
        """Add an entry to the back of the queue.

        Idempotent on (queue_key, entry.work_item_id): if the work_item_id is
        already in the queue, returns EnqueueResult(already_present=True,
        position=existing_position) with no mutation. This is the de-dup
        guarantee that lets callers retry safely (e.g. the same trigger event
        firing twice).

        Args:
            queue_key: Opaque namespaced identifier (codetoreum convention:
                same key as the corresponding lock — f"{project_id}:{board_id}").
            entry: QueueEntry with work_item_id, stage_name, board_position,
                enqueued_at, and metadata.

        Returns:
            EnqueueResult with position (0-indexed) and already_present flag.

        Emits:
            WorkItemQueuedEvent on a fresh enqueue. Not on idempotent no-op.
        """

    @abstractmethod
    async def peek(self, queue_key: str) -> QueueEntry | None:
        """Return the head entry without removing. None if empty.

        Args:
            queue_key: The queue key to peek at.

        Returns:
            QueueEntry at the head, or None if queue is empty.
        """

    @abstractmethod
    async def pop(self, queue_key: str) -> QueueEntry | None:
        """Atomically remove and return the head entry. None if empty.

        Args:
            queue_key: The queue key to pop from.

        Returns:
            QueueEntry at the head, or None if queue is empty.

        Emits:
            WorkItemDequeuedEvent on success.
        """

    @abstractmethod
    async def contains(self, queue_key: str, work_item_id: str) -> bool:
        """Check whether a specific work item is in the queue.

        Used by PipelineOrchestrator to maintain the "lock holder is not in
        queue" invariant — on every PipelineLockAcquiredEvent, the
        orchestrator checks contains() and removes if present.

        Args:
            queue_key: The queue key to check.
            work_item_id: The work item to search for.

        Returns:
            True if the work item is in the queue, False otherwise.
        """

    @abstractmethod
    async def remove(self, queue_key: str, work_item_id: str) -> bool:
        """Remove a specific entry by work_item_id.

        Returns True if removed, False if not present (idempotent).

        Args:
            queue_key: The queue key to remove from.
            work_item_id: The work item to remove.

        Returns:
            True if an entry was removed, False if not present.

        Emits:
            WorkItemDequeuedEvent on successful removal.
        """

    @abstractmethod
    async def length(self, queue_key: str) -> int:
        """Return queue depth. For diagnostics and back-pressure checks.

        Args:
            queue_key: The queue key to check.

        Returns:
            Number of entries in the queue.
        """

    @abstractmethod
    async def list(self, queue_key: str) -> list[QueueEntry]:
        """Return all entries in FIFO order. For diagnostics.

        Args:
            queue_key: The queue key to list.

        Returns:
            List of QueueEntry objects in FIFO order.
        """

    @abstractmethod
    async def position_of(self, queue_key: str, work_item_id: str) -> int | None:
        """Return 0-indexed position of work_item_id, or None if not present.

        For diagnostics; not used in the main coordination flow.

        Args:
            queue_key: The queue key to search in.
            work_item_id: The work item to find.

        Returns:
            0-indexed position, or None if not found.
        """
