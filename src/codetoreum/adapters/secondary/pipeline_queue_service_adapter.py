"""Adapter wrapping IPipelineQueueService to provide IPipelineQueue interface.

This adapter allows components expecting IPipelineQueue to work with
IPipelineQueueService implementations. It translates between the two
different queue semantics:

- IPipelineQueue: Uses queue_key (opaque identifier combining project + board)
- IPipelineQueueService: Uses explicit project_id and board_id parameters

The queue_key format is "{project_id}:{board_id}" by convention.
"""

import logging
from typing import TYPE_CHECKING

from codetoreum.ports.output.pipeline_queue import IPipelineQueue, QueueEntry
from codetoreum.ports.output.pipeline_queue_service import IPipelineQueueService

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PipelineQueueServiceAdapter(IPipelineQueue):
    """Adapts IPipelineQueueService to provide IPipelineQueue interface."""

    def __init__(self, queue_service: IPipelineQueueService):
        """Initialize adapter.

        Args:
            queue_service: IPipelineQueueService to wrap
        """
        self._queue_service = queue_service

    def _parse_queue_key(self, queue_key: str) -> tuple[str, str]:
        """Parse queue_key into (project_id, board_id).

        Convention: queue_key = "{project_id}:{board_id}"

        Args:
            queue_key: Opaque queue identifier

        Returns:
            Tuple of (project_id, board_id)

        Raises:
            ValueError: If queue_key doesn't follow the convention
        """
        parts = queue_key.split(":", 1)
        if len(parts) != 2:
            msg = f"Invalid queue_key format: {queue_key}, expected '{{project_id}}:{{board_id}}'"
            raise ValueError(msg)
        return parts[0], parts[1]

    async def enqueue(self, queue_key: str, entry: QueueEntry) -> "Any":
        """Not implemented - IPipelineQueue enqueue uses a different contract."""
        msg = "PipelineQueueServiceAdapter.enqueue() not implemented - use IPipelineQueueService.enqueue_item() instead"
        raise NotImplementedError(msg)

    async def peek(self, queue_key: str) -> QueueEntry | None:
        """Get the next waiting queue entry without removing it.

        Args:
            queue_key: Queue identifier ("{project_id}:{board_id}")

        Returns:
            Next waiting QueueEntry or None if queue empty

        Raises:
            ValueError: If queue_key format is invalid
        """
        try:
            project_id, board_id = self._parse_queue_key(queue_key)
        except ValueError as e:
            logger.error(f"Invalid queue_key in peek: {e}")
            raise

        # Get next waiting item from queue service
        entry = await self._queue_service.get_next_waiting_item(project_id, board_id)
        if entry is None:
            return None

        # Convert PipelineQueueEntry to QueueEntry for IPipelineQueue interface
        # NOTE: This is a lossy conversion - PipelineQueueEntry has more fields
        # but QueueEntry is what IPipelineQueue.peek() returns
        from types import MappingProxyType

        return QueueEntry(
            work_item_id=entry.work_item_id,
            stage_name="",  # Not available from PipelineQueueEntry
            board_position=entry.position_in_column,
            enqueued_at=entry.queued_at,
            metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
        )

    async def pop(self, queue_key: str) -> QueueEntry | None:
        """Not implemented - use remove() instead for PipelineQueueService."""
        msg = "PipelineQueueServiceAdapter.pop() not implemented - use remove() instead"
        raise NotImplementedError(msg)

    async def contains(self, queue_key: str, work_item_id: str) -> bool:
        """Check if a work item is in the queue.

        Args:
            queue_key: Queue identifier ("{project_id}:{board_id}")
            work_item_id: Work item to check

        Returns:
            True if item is in queue, False otherwise
        """
        return await self._queue_service.is_item_in_queue(work_item_id)

    async def remove(self, queue_key: str, work_item_id: str) -> bool:
        """Remove a specific work item from the queue.

        Args:
            queue_key: Queue identifier ("{project_id}:{board_id}")
            work_item_id: Work item to remove

        Returns:
            True if removed, False if not in queue
        """
        return await self._queue_service.remove_from_queue(work_item_id)

    async def length(self, queue_key: str) -> int:
        """Not implemented."""
        msg = "PipelineQueueServiceAdapter.length() not implemented"
        raise NotImplementedError(msg)

    async def list(self, queue_key: str) -> list[QueueEntry]:
        """Not implemented."""
        msg = "PipelineQueueServiceAdapter.list() not implemented"
        raise NotImplementedError(msg)

    async def position_of(self, queue_key: str, work_item_id: str) -> int | None:
        """Not implemented."""
        msg = "PipelineQueueServiceAdapter.position_of() not implemented"
        raise NotImplementedError(msg)
