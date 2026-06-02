"""PipelineOrchestrator — event-driven orchestrator for lock + queue coordination.

Subscribes to PipelineLockAcquiredEvent and PipelineLockReleasedEvent to:
1. Maintain the "lock holder is not in queue" invariant
2. Auto-trigger the next queued work item on lock release
3. Detect and release orphaned locks on startup

This replaces the queue-handoff orchestration that was embedded in the old
RedisPipelineLockService.
"""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from codetoreum.domain.events import CodetoreumEvent
from codetoreum.domain.events.lock_events import (
    PipelineLockAcquiredEvent,
    PipelineLockReleasedEvent,
)
from codetoreum.infrastructure.event_bus import EventHandler, event_handler
from codetoreum.ports.output.active_workflow_run_registry import (
    IActiveWorkflowRunRegistry,
)
from codetoreum.ports.output.distributed_lock import IDistributedLock
from codetoreum.ports.output.pipeline_queue import IPipelineQueue

if TYPE_CHECKING:
    from codetoreum.ports.output.workflow_orchestrator import IWorkflowOrchestrator

logger = logging.getLogger(__name__)


@event_handler("PipelineLockAcquiredEvent", "PipelineLockReleasedEvent")
class PipelineOrchestrator(EventHandler):
    """Orchestrates pipeline lock and queue coordination via events.

    Subscribers to:
    - PipelineLockAcquiredEvent: maintains lock/queue invariant, triggers next WI
    - PipelineLockReleasedEvent: grants lock to next queued work item

    Also performs startup orphan-recovery scan: any lock held without an active
    workflow run in the registry is released (triggering PipelineLockReleasedEvent).
    """

    def __init__(
        self,
        distributed_lock: IDistributedLock,
        pipeline_queue: IPipelineQueue,
        run_registry: IActiveWorkflowRunRegistry,
        workflow_orchestrator: "IWorkflowOrchestrator | None" = None,
    ):
        """Initialize the pipeline orchestrator.

        Args:
            distributed_lock: IDistributedLock port for lock operations
            pipeline_queue: IPipelineQueue port for queue operations
            run_registry: IActiveWorkflowRunRegistry for tracking active runs
            workflow_orchestrator: Optional IWorkflowOrchestrator to trigger next WI
        """
        self.distributed_lock = distributed_lock
        self.pipeline_queue = pipeline_queue
        self.run_registry = run_registry
        self.workflow_orchestrator = workflow_orchestrator

    def get_event_types(self) -> list[str]:
        """Return event types this handler processes."""
        return ["PipelineLockAcquiredEvent", "PipelineLockReleasedEvent"]

    async def handle(self, event: CodetoreumEvent) -> None:
        """Dispatch to appropriate handler based on event type."""
        if isinstance(event, PipelineLockAcquiredEvent):
            await self.on_lock_acquired(event)
        elif isinstance(event, PipelineLockReleasedEvent):
            await self.on_lock_released(event)
        else:
            logger.warning(f"PipelineOrchestrator received unexpected event type: {event.event_type}")

    async def on_lock_acquired(self, event: PipelineLockAcquiredEvent) -> None:
        """Handle lock acquisition.

        Maintains the "lock holder is not in queue" invariant:
        - Remove the holder from the queue if present
        - Trigger workflow run setup and agent execution if needed
        """
        lock_key = self._construct_lock_key(event.holder_metadata)
        if not lock_key:
            logger.warning(
                f"Cannot construct lock_key from event metadata for work_item_id={event.work_item_id}",
                extra={"work_item_id": event.work_item_id},
            )
            return

        queue_key = lock_key  # Same key per spec

        try:
            # Remove holder from queue if present (idempotent)
            in_queue = await self.pipeline_queue.contains(queue_key, event.holder_id)
            if in_queue:
                await self.pipeline_queue.remove(queue_key, event.holder_id)
                logger.info(
                    f"Removed {event.holder_id} from queue (now holds lock)",
                    extra={"work_item_id": event.holder_id},
                )

            # Trigger workflow setup and agent execution
            # (This is where the handler would call workflow_orchestrator to start
            # the workflow run and trigger the agent. For now, log as placeholder.)
            if self.workflow_orchestrator:
                # TODO: Call workflow_orchestrator.start_workflow_for_locked_item(...)
                pass

        except Exception:
            logger.error(
                f"Error handling lock acquisition for {event.holder_id}",
                exc_info=True,
            )

    async def on_lock_released(self, event: PipelineLockReleasedEvent) -> None:
        """Handle lock release.

        Grants the lock to the next queued work item.
        """
        lock_key = self._construct_lock_key(event.holder_metadata)
        if not lock_key:
            logger.warning(
                f"Cannot construct lock_key from event metadata for released_holder_id={event.released_holder_id}",
                extra={"released_holder_id": event.released_holder_id},
            )
            return

        queue_key = lock_key

        try:
            # Get next queued item
            next_entry = await self.pipeline_queue.peek(queue_key)
            if next_entry is None:
                logger.info(f"No queued items after {event.released_holder_id} released lock")
                return

            # Try to acquire lock for next item
            result = await self.distributed_lock.try_acquire(
                lock_key=lock_key,
                holder_id=next_entry.work_item_id,
                ttl_seconds=7200,  # Default TTL
                holder_metadata=next_entry.metadata,
            )

            if result.status.value == "acquired":
                # Lock granted; next handler will trigger the workflow
                logger.info(
                    f"Granted lock to next queued item {next_entry.work_item_id}",
                    extra={"work_item_id": next_entry.work_item_id},
                )
            else:
                # Lock held by someone else (race condition)
                logger.warning(
                    f"Failed to grant lock to {next_entry.work_item_id}: {result.status.value}",
                    extra={"work_item_id": next_entry.work_item_id},
                )

        except Exception:
            logger.error(
                f"Error handling lock release for {event.released_holder_id}",
                exc_info=True,
            )

    async def on_startup(self) -> None:
        """Perform orphan-recovery scan on startup.

        Scan all locks; any lock held without an active workflow run in the
        registry is released (triggering PipelineLockReleasedEvent).
        """
        try:
            all_holders = await self.distributed_lock.get_all_holders()
            logger.info(f"Starting orphan-recovery scan: {len(all_holders)} locks held")

            for holder in all_holders:
                # Check if holder has an active workflow run
                active_run = await self.run_registry.get_active_run(holder.holder_id)
                if active_run is None:
                    # Orphaned lock — release it
                    logger.warning(
                        f"Orphaned lock detected for {holder.holder_id} (no active run)",
                        extra={"work_item_id": holder.holder_id},
                    )
                    result = await self.distributed_lock.release(
                        lock_key=holder.lock_key,
                        holder_id=holder.holder_id,
                    )
                    if result.released:
                        logger.info(f"Released orphaned lock for {holder.holder_id}")

        except Exception:
            logger.error(
                "Error during orphan-recovery startup scan",
                exc_info=True,
            )

    def _construct_lock_key(self, holder_metadata: dict[str, str] | None) -> str | None:
        """Construct lock key from holder metadata.

        Expects metadata to contain 'project_id' and 'board_id'.
        Returns f"{project_id}:{board_id}" or None if missing.
        """
        if not holder_metadata:
            return None

        project_id = holder_metadata.get("project_id")
        board_id = holder_metadata.get("board_id")

        if not project_id or not board_id:
            return None

        return f"{project_id}:{board_id}"
