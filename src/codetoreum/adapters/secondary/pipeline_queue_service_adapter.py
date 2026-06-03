"""Adapter translating IPipelineQueueService to IPipelineQueue interface."""

import logging
from types import MappingProxyType

from codetoreum.ports.output.pipeline_queue import (
    EnqueueResult,
    IPipelineQueue,
    QueueEntry,
)
from codetoreum.ports.output.pipeline_queue_service import (
    DuplicateQueueEntryError,
    IPipelineQueueService,
)

logger = logging.getLogger(__name__)


class PipelineQueueServiceAdapter(IPipelineQueue):
    """Adapts IPipelineQueueService to provide IPipelineQueue interface."""

    def __init__(self, queue_service: IPipelineQueueService):
        self._queue_service = queue_service

    def _parse_queue_key(self, queue_key: str) -> tuple[str, str]:
        parts = queue_key.split(":", 1)
        if len(parts) != 2:
            msg = f"Invalid queue_key format: {queue_key}, expected '{{project_id}}:{{board_id}}'"
            raise ValueError(msg)
        return parts[0], parts[1]

    async def enqueue(self, queue_key: str, entry: QueueEntry) -> EnqueueResult:
        """Add an entry to the queue.

        Delegates to IPipelineQueueService.enqueue_item(), parsing queue_key
        to extract project_id and board_id.
        """
        try:
            project_id, board_id = self._parse_queue_key(queue_key)
        except ValueError as e:
            logger.error(f"Invalid queue_key in enqueue: {e}")
            raise

        try:
            await self._queue_service.enqueue_item(
                project_id=project_id,
                board_id=board_id,
                work_item_id=entry.work_item_id,
                position_in_column=entry.board_position,
                timestamp=entry.enqueued_at,
            )
            return EnqueueResult(position=entry.board_position, already_present=False)
        except DuplicateQueueEntryError:
            return EnqueueResult(position=entry.board_position, already_present=True)

    async def peek(self, queue_key: str) -> QueueEntry | None:
        try:
            project_id, board_id = self._parse_queue_key(queue_key)
        except ValueError as e:
            logger.error(f"Invalid queue_key in peek: {e}")
            raise

        entry = await self._queue_service.get_next_waiting_item(project_id, board_id)
        if entry is None:
            return None

        return QueueEntry(
            work_item_id=entry.work_item_id,
            stage_name="",
            board_position=entry.position_in_column,
            enqueued_at=entry.queued_at,
            metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
        )

    async def pop(self, queue_key: str) -> QueueEntry | None:
        """Remove and return the head entry. None if empty or removal fails.

        Note: This delegates to two separate service calls (get_next_waiting_item,
        then remove_from_queue) and is not atomic. In concurrent scenarios,
        another caller may remove the item between these calls.
        """
        try:
            project_id, board_id = self._parse_queue_key(queue_key)
        except ValueError as e:
            logger.error(f"Invalid queue_key in pop: {e}")
            raise

        entry = await self._queue_service.get_next_waiting_item(project_id, board_id)
        if entry is None:
            return None

        removed = await self._queue_service.remove_from_queue(entry.work_item_id)
        if not removed:
            return None

        return QueueEntry(
            work_item_id=entry.work_item_id,
            stage_name="",
            board_position=entry.position_in_column,
            enqueued_at=entry.queued_at,
            metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
        )

    async def contains(self, queue_key: str, work_item_id: str) -> bool:
        return await self._queue_service.is_item_in_queue(work_item_id)

    async def remove(self, queue_key: str, work_item_id: str) -> bool:
        return await self._queue_service.remove_from_queue(work_item_id)

    async def length(self, queue_key: str) -> int:
        """Return queue depth.

        Delegates to IPipelineQueueService to get all queue entries and
        returns the count.
        """
        try:
            project_id, board_id = self._parse_queue_key(queue_key)
        except ValueError as e:
            logger.error(f"Invalid queue_key in length: {e}")
            raise

        entries = await self._queue_service.get_queue_entries(project_id, board_id)
        return len(entries)

    async def list(self, queue_key: str) -> list[QueueEntry]:
        """Return all entries in FIFO order.

        Delegates to IPipelineQueueService to get all queue entries and
        converts them to IPipelineQueue.QueueEntry format.
        """
        try:
            project_id, board_id = self._parse_queue_key(queue_key)
        except ValueError as e:
            logger.error(f"Invalid queue_key in list: {e}")
            raise

        service_entries = await self._queue_service.get_queue_entries(project_id, board_id)
        return [
            QueueEntry(
                work_item_id=entry.work_item_id,
                stage_name="",
                board_position=entry.position_in_column,
                enqueued_at=entry.queued_at,
                metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
            )
            for entry in service_entries
        ]

    async def position_of(self, queue_key: str, work_item_id: str) -> int | None:
        """Return 0-indexed position of work_item_id, or None if not present.

        Delegates to IPipelineQueueService to get all queue entries and
        searches for the requested work item's position.
        """
        try:
            project_id, board_id = self._parse_queue_key(queue_key)
        except ValueError as e:
            logger.error(f"Invalid queue_key in position_of: {e}")
            raise

        service_entries = await self._queue_service.get_queue_entries(project_id, board_id)
        for index, entry in enumerate(service_entries):
            if entry.work_item_id == work_item_id:
                return index
        return None
