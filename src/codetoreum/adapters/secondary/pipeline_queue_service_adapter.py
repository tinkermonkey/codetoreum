"""Adapter translating IPipelineQueueService to IPipelineQueue interface."""

import logging

from codetoreum.ports.output.pipeline_queue import (
    EnqueueResult,
    IPipelineQueue,
    QueueEntry,
)
from codetoreum.ports.output.pipeline_queue_service import IPipelineQueueService

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
        msg = "PipelineQueueServiceAdapter.enqueue() not implemented - use IPipelineQueueService.enqueue_item() instead"
        raise NotImplementedError(msg)

    async def peek(self, queue_key: str) -> QueueEntry | None:
        try:
            project_id, board_id = self._parse_queue_key(queue_key)
        except ValueError as e:
            logger.error(f"Invalid queue_key in peek: {e}")
            raise

        entry = await self._queue_service.get_next_waiting_item(project_id, board_id)
        if entry is None:
            return None

        from types import MappingProxyType

        return QueueEntry(
            work_item_id=entry.work_item_id,
            stage_name="",
            board_position=entry.position_in_column,
            enqueued_at=entry.queued_at,
            metadata=MappingProxyType({"project_id": project_id, "board_id": board_id}),
        )

    async def pop(self, queue_key: str) -> QueueEntry | None:
        msg = "PipelineQueueServiceAdapter.pop() not implemented - use remove() instead"
        raise NotImplementedError(msg)

    async def contains(self, queue_key: str, work_item_id: str) -> bool:
        return await self._queue_service.is_item_in_queue(work_item_id)

    async def remove(self, queue_key: str, work_item_id: str) -> bool:
        return await self._queue_service.remove_from_queue(work_item_id)

    async def length(self, queue_key: str) -> int:
        msg = "PipelineQueueServiceAdapter.length() not implemented"
        raise NotImplementedError(msg)

    async def list(self, queue_key: str) -> list[QueueEntry]:
        msg = "PipelineQueueServiceAdapter.list() not implemented"
        raise NotImplementedError(msg)

    async def position_of(self, queue_key: str, work_item_id: str) -> int | None:
        msg = "PipelineQueueServiceAdapter.position_of() not implemented"
        raise NotImplementedError(msg)
