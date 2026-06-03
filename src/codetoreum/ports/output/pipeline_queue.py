"""FIFO queue port interface for pipeline coordination.

IPipelineQueue is a FIFO queue of work items waiting on a coordinated resource.
Knows nothing about locks. A queue has a key and an ordered list of entries;
operations are atomic at the storage layer.

Production implementation: RedisPipelineQueue (sorted set + sibling metadata hash).
Local-dev / harness: FileBackedPipelineQueue (JSONL + fsync).

Callers are responsible for emitting domain events (WorkItemQueuedEvent,
WorkItemDequeuedEvent) based on returned EnqueueResult status and pop/remove
operation results. This separation lets callers inject context (project_id, board_id)
that the queue primitive itself lacks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType


@dataclass(frozen=True)
class QueueEntry:
    """Entry in the pipeline queue."""
    work_item_id: str
    stage_name: str
    board_position: int  # Position on the external board at enqueue time
    enqueued_at: datetime
    metadata: MappingProxyType[str, str]  # Immutable view of metadata dict. Codetoreum stashes
                                           # project_id, board_id, etc.


@dataclass(frozen=True)
class EnqueueResult:
    """Result of an enqueue operation."""
    position: int  # 0-indexed position in the queue (after enqueue)
    already_present: bool  # True if no-op due to existing entry


class IPipelineQueue(ABC):
    """FIFO queue of work items waiting on a coordinated resource.

    Knows nothing about locks. A queue has a key and an ordered list of
    entries; operations are atomic at the storage layer.

    Production implementation: RedisPipelineQueue (sorted set + sibling
    metadata hash).
    Local-dev / harness: FileBackedPipelineQueue (JSONL + fsync).

    Callers are responsible for emitting domain events (WorkItemQueuedEvent,
    WorkItemDequeuedEvent). The orchestrator's primary trigger for state
    transitions is the lock's events (PipelineLockAcquiredEvent /
    PipelineLockReleasedEvent).
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
            entry: QueueEntry { work_item_id, stage_name, board_position,
                enqueued_at, metadata }. board_position is the external
                board's position (used as a tiebreaker when two items race
                to enqueue at the same logical time).

        Returns:
            EnqueueResult { position: int, already_present: bool }.
            Callers MUST emit WorkItemQueuedEvent when already_present == False.
        """

    @abstractmethod
    async def peek(self, queue_key: str) -> QueueEntry | None:
        """Return the head entry without removing. None if empty."""

    @abstractmethod
    async def pop(self, queue_key: str) -> QueueEntry | None:
        """Atomically remove and return the head entry. None if empty.

        Callers MUST emit WorkItemDequeuedEvent when an entry is successfully popped.
        """

    @abstractmethod
    async def contains(self, queue_key: str, work_item_id: str) -> bool:
        """Check whether a specific work item is in the queue.

        Used by PipelineOrchestrator to maintain the "lock holder is not in
        queue" invariant — on every PipelineLockAcquiredEvent, the
        orchestrator checks contains() and removes if present.
        """

    @abstractmethod
    async def remove(self, queue_key: str, work_item_id: str) -> bool:
        """Remove a specific entry by work_item_id.

        Returns True if removed, False if not present (idempotent).

        Callers MUST emit WorkItemDequeuedEvent when True is returned.
        """

    @abstractmethod
    async def length(self, queue_key: str) -> int:
        """Return queue depth. For diagnostics and back-pressure checks."""

    @abstractmethod
    async def list(self, queue_key: str) -> list[QueueEntry]:
        """Return all entries in FIFO order. For diagnostics."""

    @abstractmethod
    async def position_of(self, queue_key: str, work_item_id: str) -> int | None:
        """Return 0-indexed position of work_item_id, or None if not present.

        For diagnostics; not used in the main coordination flow.
        """
