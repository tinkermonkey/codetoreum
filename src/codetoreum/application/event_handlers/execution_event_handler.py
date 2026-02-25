"""Event handler for execution-related events."""

import logging

from codetoreum.application.execution_service import ExecutionService
from codetoreum.domain.events import (
    DomainEvent,
    ExecutionCompleted,
    ExecutionFailed,
    ExecutionInitialized,
    ExecutionStarted,
    ExecutionTimeout,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventHandler, event_handler

logger = logging.getLogger(__name__)


@event_handler(
    "ExecutionInitialized",
    "ExecutionStarted",
    "ExecutionCompleted",
    "ExecutionFailed",
    "ExecutionTimeout",
)
class ExecutionEventHandler(EventHandler):
    """
    Event handler for agent execution lifecycle events.

    Handles events for:
    - ExecutionInitialized: Log execution creation
    - ExecutionStarted: Track active executions
    - ExecutionCompleted: Update metrics, trigger next steps
    - ExecutionFailed: Handle failures, track errors
    - ExecutionTimeout: Handle timeout scenarios
    """

    def __init__(self, execution_service: ExecutionService):
        """
        Initialize handler.

        Args:
            execution_service: Execution service
        """
        self.execution_service = execution_service

        # Track execution metrics
        self._metrics: dict[str, int] = {
            "total_executions": 0,
            "active_executions": 0,
            "completed_executions": 0,
            "failed_executions": 0,
            "timed_out_executions": 0,
        }

        # Track active executions by ID
        self._active_executions: dict[str, str] = {}  # execution_id -> work_item_id

    async def handle(self, event: DomainEvent) -> None:
        """
        Handle execution-related events.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails
        """
        if isinstance(event, ExecutionInitialized):
            await self._handle_execution_initialized(event)
        elif isinstance(event, ExecutionStarted):
            await self._handle_execution_started(event)
        elif isinstance(event, ExecutionCompleted):
            await self._handle_execution_completed(event)
        elif isinstance(event, ExecutionFailed):
            await self._handle_execution_failed(event)
        elif isinstance(event, ExecutionTimeout):
            await self._handle_execution_timeout(event)
        else:
            logger.warning(
                f"ExecutionEventHandler received unexpected event type: {event.event_type}"
            )

    async def _handle_execution_initialized(self, event: ExecutionInitialized) -> None:
        """
        Handle execution initialization.

        Args:
            event: ExecutionInitialized event
        """
        self._metrics["total_executions"] += 1

        logger.info(
            f"Execution initialized: {event.aggregate_id} "
            f"(agent: {event.payload.get('agent_id')}, work_item: {event.payload.get('work_item_id')}, "
            f"workflow: {event.payload.get('workflow_id')}, stage: {event.payload.get('stage_name')})"
        )

        logger.debug(
            f"Total executions: {self._metrics['total_executions']}, "
            f"Active: {self._metrics['active_executions']}"
        )

    async def _handle_execution_started(self, event: ExecutionStarted) -> None:
        """
        Handle execution start - track active executions.

        Args:
            event: ExecutionStarted event
        """
        self._metrics["active_executions"] += 1
        self._active_executions[event.aggregate_id] = event.aggregate_id  # Track by execution ID

        logger.info(
            f"Execution started: {event.aggregate_id} "
            f"(container: {event.payload.get('container_name') or 'none'})"
        )

        logger.debug(
            f"Active executions: {self._metrics['active_executions']}, "
            f"Total: {self._metrics['total_executions']}"
        )

        # Note: In a full implementation, this would:
        # 1. Start monitoring execution health
        # 2. Set up timeout watchdog
        # 3. Stream logs to subscribers
        # 4. Update execution dashboard

    async def _handle_execution_completed(self, event: ExecutionCompleted) -> None:
        """
        Handle execution completion - update metrics, trigger next steps.

        Args:
            event: ExecutionCompleted event
        """
        self._metrics["completed_executions"] += 1
        self._metrics["active_executions"] -= 1
        self._active_executions.pop(event.aggregate_id, None)

        input_tokens = event.payload.get("input_tokens", 0)
        output_tokens = event.payload.get("output_tokens", 0)
        logger.info(
            f"Execution completed: {event.aggregate_id} "
            f"(tokens: input={input_tokens}, output={output_tokens}, "
            f"total={input_tokens + output_tokens})"
        )

        logger.debug(
            f"Completion rate: {self._metrics['completed_executions']}/{self._metrics['total_executions']} "
            f"({self._get_success_rate():.1f}%)"
        )

        # Note: In a full implementation, this would:
        # 1. Calculate cost from token usage
        # 2. Update agent performance metrics
        # 3. Store execution artifacts
        # 4. Trigger workflow progression (handled by WorkflowEventHandler)
        # 5. Send completion notifications

    async def _handle_execution_failed(self, event: ExecutionFailed) -> None:
        """
        Handle execution failure - track errors, trigger retry or escalation.

        Args:
            event: ExecutionFailed event
        """
        self._metrics["failed_executions"] += 1
        self._metrics["active_executions"] -= 1
        self._active_executions.pop(event.aggregate_id, None)

        logger.error(
            f"Execution failed: {event.aggregate_id}, "
            f"error: {event.payload.get('error_message')}",
            extra={"error_id": "ERR_EXECUTION_FAILED"}
        )

        exit_code = event.payload.get("exit_code")
        if exit_code:
            logger.error(f"Exit code: {exit_code}", extra={"error_id": ErrorRegistry.ERR_EXECUTION_ERROR})

        logger.warning(
            f"Failure rate: {self._metrics['failed_executions']}/{self._metrics['total_executions']} "
            f"({self._get_failure_rate():.1f}%)"
        )

        # Note: In a full implementation, this would:
        # 1. Analyze failure reason (timeout, rate limit, validation, etc.)
        # 2. Determine if retry is appropriate
        # 3. Queue retry task or escalate to human
        # 4. Update agent reliability metrics
        # 5. Send failure notifications
        # 6. Store failure diagnostics

    async def _handle_execution_timeout(self, event: ExecutionTimeout) -> None:
        """
        Handle execution timeout.

        Args:
            event: ExecutionTimeout event
        """
        self._metrics["timed_out_executions"] += 1
        self._metrics["failed_executions"] += 1
        self._metrics["active_executions"] -= 1
        self._active_executions.pop(event.aggregate_id, None)

        logger.error(
            f"Execution timed out: {event.aggregate_id}",
            extra={"error_id": ErrorRegistry.ERR_EXECUTION_TIMEOUT}
        )

        logger.warning(
            f"Timeout rate: {self._metrics['timed_out_executions']}/{self._metrics['total_executions']} "
            f"({self._get_timeout_rate():.1f}%)"
        )

        # Note: In a full implementation, this would:
        # 1. Clean up container resources
        # 2. Analyze timeout cause (stuck process, infinite loop, etc.)
        # 3. Adjust timeout settings if appropriate
        # 4. Queue retry with longer timeout or escalate
        # 5. Send timeout alerts
        # 6. Update agent timeout metrics

    def _get_success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self._metrics["total_executions"] == 0:
            return 0.0
        return (
            self._metrics["completed_executions"]
            / self._metrics["total_executions"]
            * 100
        )

    def _get_failure_rate(self) -> float:
        """Calculate failure rate percentage."""
        if self._metrics["total_executions"] == 0:
            return 0.0
        return (
            self._metrics["failed_executions"] / self._metrics["total_executions"] * 100
        )

    def _get_timeout_rate(self) -> float:
        """Calculate timeout rate percentage."""
        if self._metrics["total_executions"] == 0:
            return 0.0
        return (
            self._metrics["timed_out_executions"]
            / self._metrics["total_executions"]
            * 100
        )

    def get_metrics(self) -> dict[str, float]:
        """
        Get execution metrics.

        Returns:
            Dictionary of execution metrics
        """
        return {
            **self._metrics,
            "success_rate": self._get_success_rate(),
            "failure_rate": self._get_failure_rate(),
            "timeout_rate": self._get_timeout_rate(),
        }

    def get_active_executions(self) -> dict[str, str]:
        """
        Get currently active executions.

        Returns:
            Dictionary mapping execution_id to work_item_id
        """
        return dict(self._active_executions)
