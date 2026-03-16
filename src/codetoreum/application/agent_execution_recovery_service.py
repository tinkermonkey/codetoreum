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
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from codetoreum.domain.events import WorkflowFailed
from codetoreum.ports.output.failed_event_store import (
    FailedEventStoreStats,
    FailureReason,
    IFailedEventStore,
)

if TYPE_CHECKING:
    from codetoreum.ports.output.active_workflow_run_registry import IActiveWorkflowRunRegistry
    from codetoreum.ports.output.board_service import IBoardService
    from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


class AgentExecutionRecoveryService:
    """Handles recovery from agent execution failures.

    Responsibilities:
    1. Track failed auto-progressions in dead letter queue (using DeadLetterQueue infrastructure)
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
        failed_event_store: IFailedEventStore | None = None,
    ) -> None:
        """Initialize recovery service.

        Args:
            board_service: Optional board service for querying work items
            event_store: Optional event store for persisting recovery events
            run_registry: Optional registry for failing workflow runs
            failed_event_store: Optional IFailedEventStore for tracking failed auto-progressions
        """
        self._board_service = board_service
        self._event_store = event_store
        self._run_registry = run_registry
        if failed_event_store is None:
            msg = "failed_event_store is required for AgentExecutionRecoveryService"
            raise ValueError(msg)
        self._failed_event_store = failed_event_store

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
                # Guard against missing board_service (e.g., in test scenarios)
                from_column = "UNKNOWN"
                if self._board_service:
                    try:
                        current_position = await self._board_service.get_item_position(work_item_id)
                        from_column = current_position.column_name
                    except Exception as pos_err:
                        logger.warning(
                            f"Could not determine current column for '{work_item_id}': {pos_err}",
                            exc_info=True,
                            extra={"error_id": "ERR_AGENT_EXECUTION_POSITION_LOOKUP_FAILURE"},
                        )

                # Queue in failed event store with event_data containing workflow context
                # Next column is unknown without workflow config; will be determined during recovery
                event_id = await self._failed_event_store.add_failed_event(
                    event_type="auto_progression_failure",
                    event_data={
                        "work_item_id": work_item_id,
                        "board_id": board_id,
                        "from_column": from_column,
                        "to_column": "UNKNOWN",  # Determined during manual recovery
                        "reason": str(error),
                    },
                    failure_reason=FailureReason.PROCESSING_ERROR,
                    error_message=f"Auto-progression callback failed: {error}",
                    metadata={
                        "error_id": "ERR_AGENT_EXECUTION_COMPLETION_CALLBACK_FAILURE",
                    },
                )
                logger.warning(
                    f"Work item '{work_item_id}' queued in dead letter queue for manual progression "
                    f"(DLQ event: {event_id})",
                    extra={
                        "error_id": "ERR_AGENT_EXECUTION_DLQ_ENQUEUED",
                        "work_item_id": work_item_id,
                        "dlq_event_id": event_id,
                    },
                )
            except Exception as queue_err:
                logger.error(
                    f"Failed to queue work item '{work_item_id}' to dead letter queue: {queue_err}",
                    exc_info=True,
                    extra={"error_id": "ERR_AGENT_EXECUTION_DLQ_FAILURE"},
                )

        # Fail workflow run if tracking is available
        await self._fail_workflow_run(
            work_item_id=work_item_id,
            reason=f"Completion callback failure: {error}",
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
        await self._fail_workflow_run(
            work_item_id=work_item_id,
            reason=f"Agent execution failure: {error}",
        )

    async def _fail_workflow_run(self, work_item_id: str, reason: str) -> None:
        """Private helper to fail a workflow run.

        Consolidates duplicate logic for failing workflow runs from both
        completion callback and execution failure paths.

        Args:
            work_item_id: Work item whose workflow should fail
            reason: Reason for workflow failure
        """
        if not self._run_registry:
            return

        try:
            run_info = await self._run_registry.get_active_run(work_item_id)
            if not run_info:
                return

            logger.critical(
                f"Failing workflow run for '{work_item_id}' due to: {reason}",
                extra={
                    "error_id": "ERR_AGENT_EXECUTION_WORKFLOW_FAILED",
                    "work_item_id": work_item_id,
                    "run_id": run_info.run_id,
                },
            )

            if not self._event_store:
                return

            try:
                workflow_failed = WorkflowFailed(
                    aggregate_id=run_info.run_id,
                    payload={
                        "failed_at": datetime.now(UTC).isoformat(),
                        "reason": reason,
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

    def get_failed_event_store_stats(self) -> FailedEventStoreStats:
        """Get statistics from the failed event store.

        Returns:
            FailedEventStoreStats with failure metrics
        """
        return self._failed_event_store.get_stats()

    def get_stuck_work_items(self) -> list[str]:
        """Get list of work item IDs stuck in failed event store.

        Returns:
            List of work item IDs with failed auto-progressions
        """
        stuck_items = []
        # All failed events in the store are auto-progression failures
        # Extract work item IDs from event data using public API
        for event in self._failed_event_store.list_events():
            if "work_item_id" in event.event_data:
                stuck_items.append(event.event_data["work_item_id"])
        return stuck_items
