"""Agent Execution Recovery Service - handles recovery from agent execution failures.

This service provides recovery mechanisms for:
1. Auto-progression failures (completion callback failures)
2. Lock release failures (execution failures during agent run)

Recovery strategies:
- Dead letter queue: Failed auto-progressions queued for manual/async retry
- Lock stuck detection: Fails workflow run, emits alert for manual intervention
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codetoreum.ports.output.board_service import IBoardService
    from codetoreum.ports.output.event_store import IEventStore
    from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry

logger = logging.getLogger(__name__)


@dataclass
class FailedAutoProgression:
    """Record of a failed auto-progression for recovery."""

    work_item_id: str
    board_id: str
    from_column: str
    to_column: str
    reason: str
    failed_at: datetime
    attempt_count: int = 1

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "work_item_id": self.work_item_id,
            "board_id": self.board_id,
            "from_column": self.from_column,
            "to_column": self.to_column,
            "reason": self.reason,
            "failed_at": self.failed_at.isoformat(),
            "attempt_count": self.attempt_count,
        }


class AgentExecutionRecoveryService:
    """Handles recovery from agent execution failures.

    Responsibilities:
    1. Track failed auto-progressions in dead letter queue
    2. Detect and log lock stuck conditions
    3. Fail workflow runs when recovery is impossible
    4. Provide observability for stuck work items

    This service is injected into:
    - ExecutionServiceAgentExecutor (completion callback failures)
    - BoardColumnEventHandler (agent execution failures)
    """

    def __init__(
        self,
        board_service: IBoardService | None = None,
        event_store: IEventStore | None = None,
        run_registry: IActiveWorkflowRunRegistry | None = None,
    ) -> None:
        """Initialize recovery service.

        Args:
            board_service: Optional board service for querying work items
            event_store: Optional event store for persisting recovery events
            run_registry: Optional registry for failing workflow runs
        """
        self._board_service = board_service
        self._event_store = event_store
        self._run_registry = run_registry
        self._dead_letter_queue: list[FailedAutoProgression] = []

    @property
    def dead_letter_queue(self) -> list[FailedAutoProgression]:
        """Return dead letter queue for test assertions."""
        return list(self._dead_letter_queue)

    async def handle_completion_callback_failure(
        self,
        work_item_id: str,
        board_id: str,
        success: bool,
        error: Exception,
    ) -> None:
        """Handle failure of completion callback (auto-progression).

        When the completion callback (handle_agent_completion) fails, the work
        item is stuck in its current column and won't progress. This method:
        1. Logs the failure with full context
        2. Queues for dead letter queue for manual/async recovery
        3. Fails the workflow run if tracking is available
        4. Emits observability event for alerting

        Args:
            work_item_id: Work item that completed but failed to progress
            board_id: Board containing the work item
            success: Whether the agent execution succeeded
            error: Exception from completion callback
        """
        logger.error(
            f"Completion callback failed for work item '{work_item_id}' "
            f"on board '{board_id}' (execution success={success}): {error}",
            exc_info=True,
            extra={
                "error_id": "ERR_AGENT_EXECUTION_COMPLETION_CALLBACK_FAILURE",
                "work_item_id": work_item_id,
                "board_id": board_id,
                "execution_success": success,
            },
        )

        # If agent execution succeeded but auto-progression failed, queue for recovery
        if success:
            try:
                # Get current position to determine intended progression
                current_position = await self._board_service.get_item_position(work_item_id)
                next_column = None
                # Note: We don't have workflow config here, so we can't determine next column
                # This will be handled by admin/recovery process
                failed_progression = FailedAutoProgression(
                    work_item_id=work_item_id,
                    board_id=board_id,
                    from_column=current_position.column_name,
                    to_column=next_column or "UNKNOWN",
                    reason=f"Auto-progression callback failed: {error}",
                    failed_at=datetime.now(UTC),
                    attempt_count=1,
                )
                self._dead_letter_queue.append(failed_progression)
                logger.warning(
                    f"Work item '{work_item_id}' queued in dead letter queue for manual progression",
                    extra={
                        "error_id": "ERR_AGENT_EXECUTION_DLQ_ENQUEUED",
                        "work_item_id": work_item_id,
                    },
                )
            except Exception as queue_err:
                logger.error(
                    f"Failed to queue work item '{work_item_id}' to dead letter queue: {queue_err}",
                    exc_info=True,
                    extra={"error_id": "ERR_AGENT_EXECUTION_DLQ_FAILURE"},
                )

        # Fail workflow run if tracking is available
        if self._run_registry:
            try:
                run_info = await self._run_registry.get_active_run(work_item_id)
                if run_info:
                    # Mark workflow as failed due to completion callback error
                    logger.critical(
                        f"Failing workflow run for '{work_item_id}' due to completion callback failure",
                        extra={
                            "error_id": "ERR_AGENT_EXECUTION_WORKFLOW_FAILED",
                            "work_item_id": work_item_id,
                            "run_id": run_info.run_id,
                        },
                    )
                    if self._event_store:
                        try:
                            from codetoreum.domain.events import WorkflowFailed

                            workflow_failed = WorkflowFailed(
                                aggregate_id=run_info.run_id,
                                payload={
                                    "failed_at": datetime.now(UTC).isoformat(),
                                    "reason": f"Completion callback failure: {error}",
                                    "failed_stage": run_info.stage_name,
                                    "work_item_id": work_item_id,
                                },
                            )
                            await self._event_store.append(run_info.run_id, [workflow_failed])
                        except Exception as persist_err:
                            logger.error(
                                f"Failed to persist WorkflowFailed event for '{work_item_id}': {persist_err}",
                                exc_info=True,
                                extra={"error_id": "ERR_AGENT_EXECUTION_PERSIST_FAILURE"},
                            )
            except Exception as registry_err:
                logger.error(
                    f"Failed to query/update run registry for '{work_item_id}': {registry_err}",
                    exc_info=True,
                    extra={"error_id": "ERR_AGENT_EXECUTION_REGISTRY_FAILURE"},
                )

    async def handle_agent_execution_failure(
        self,
        work_item_id: str,
        board_id: str,
        error: Exception,
    ) -> None:
        """Handle failure during agent execution (before completion callback).

        When agent execution fails (e.g., before creating task), the lock may
        not be released properly. This method:
        1. Logs the failure
        2. Fails the workflow run
        3. Provides observability for stuck lock detection

        Note: Lock release should be handled by the caller before invoking this.

        Args:
            work_item_id: Work item that failed during execution
            board_id: Board containing the work item
            error: Exception from agent execution
        """
        logger.error(
            f"Agent execution failed for work item '{work_item_id}': {error}",
            exc_info=True,
            extra={
                "error_id": "ERR_AGENT_EXECUTION_FAILURE",
                "work_item_id": work_item_id,
                "board_id": board_id,
            },
        )

        # Fail workflow run if available
        if self._run_registry:
            try:
                run_info = await self._run_registry.get_active_run(work_item_id)
                if run_info:
                    logger.critical(
                        f"Failing workflow run for '{work_item_id}' due to execution failure",
                        extra={
                            "error_id": "ERR_AGENT_EXECUTION_WORKFLOW_FAILED",
                            "work_item_id": work_item_id,
                            "run_id": run_info.run_id,
                        },
                    )
                    if self._event_store:
                        try:
                            from codetoreum.domain.events import WorkflowFailed

                            workflow_failed = WorkflowFailed(
                                aggregate_id=run_info.run_id,
                                payload={
                                    "failed_at": datetime.now(UTC).isoformat(),
                                    "reason": f"Agent execution failure: {error}",
                                    "failed_stage": run_info.stage_name,
                                    "work_item_id": work_item_id,
                                },
                            )
                            await self._event_store.append(run_info.run_id, [workflow_failed])
                        except Exception as persist_err:
                            logger.error(
                                f"Failed to persist WorkflowFailed event for '{work_item_id}': {persist_err}",
                                exc_info=True,
                                extra={"error_id": "ERR_AGENT_EXECUTION_PERSIST_FAILURE"},
                            )
            except Exception as registry_err:
                logger.error(
                    f"Failed to query/update run registry for '{work_item_id}': {registry_err}",
                    exc_info=True,
                    extra={"error_id": "ERR_AGENT_EXECUTION_REGISTRY_FAILURE"},
                )

    def clear_dead_letter_queue(self) -> None:
        """Clear dead letter queue (typically after processing)."""
        self._dead_letter_queue.clear()

    def get_stuck_work_items(self) -> list[str]:
        """Get list of work item IDs stuck in dead letter queue."""
        return [item.work_item_id for item in self._dead_letter_queue]
