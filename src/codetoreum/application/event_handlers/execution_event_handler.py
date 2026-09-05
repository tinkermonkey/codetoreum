"""Event handler for execution-related events."""

import logging

from codetoreum.application.execution_service import ExecutionService
from codetoreum.domain.events import (
    ExecutionCompletedEvent,
    ExecutionFailedEvent,
    ExecutionInitializedEvent,
    ExecutionStartedEvent,
    ExecutionTimedOutEvent,
)
from codetoreum.domain.events.adapter_events import CodetoreumEvent
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventHandler, event_handler

logger = logging.getLogger(__name__)


@event_handler(
    "ExecutionInitializedEvent",
    "ExecutionStartedEvent",
    "ExecutionCompletedEvent",
    "ExecutionFailedEvent",
    "ExecutionTimedOutEvent",
)
class ExecutionEventHandler(EventHandler):
    """
    Event handler for agent execution lifecycle events.

    Handles events for:
    - ExecutionInitializedEvent: Log execution creation
    - ExecutionStartedEvent: Track active executions
    - ExecutionCompletedEvent: Update metrics, trigger next steps
    - ExecutionFailedEvent: Handle failures, track errors
    - ExecutionTimedOutEvent: Handle timeout scenarios
    """

    def __init__(self, execution_service: ExecutionService):
        """
        Initialize handler.

        Args: execution_service: Execution service
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

    async def handle(self, event: CodetoreumEvent) -> None:
        """
        Handle execution-related events.

        Args: event: Domain event to handle

        Raises: Exception: If handling fails
        """
        if isinstance(event, ExecutionInitializedEvent):
            await self._handle_execution_initialized(event)
        elif isinstance(event, ExecutionStartedEvent):
            await self._handle_execution_started(event)
        elif isinstance(event, ExecutionCompletedEvent):
            await self._handle_execution_completed(event)
        elif isinstance(event, ExecutionFailedEvent):
            await self._handle_execution_failed(event)
        elif isinstance(event, ExecutionTimedOutEvent):
            await self._handle_execution_timeout(event)
        else:
            logger.warning(f"ExecutionEventHandler received unexpected event type: {event.event_type}")

    async def _handle_execution_initialized(self, event: ExecutionInitializedEvent) -> None:
        """
        Handle execution initialization.

        Args: event: ExecutionInitializedEvent event
        """
        self._metrics["total_executions"] += 1

        logger.info(
            f"Execution initialized: {event.execution_id} "
            f"(agent: {event.agent_id}, work_item: {event.work_item_id})"
        )

        logger.debug(
            f"Total executions: {self._metrics['total_executions']}, Active: {self._metrics['active_executions']}"
        )

    async def _handle_execution_started(self, event: ExecutionStartedEvent) -> None:
        """
        Handle execution start - track active executions.

        Args: event: ExecutionStartedEvent event
        """
        self._metrics["active_executions"] += 1
        self._active_executions[event.execution_id] = event.execution_id

        logger.info(f"Execution started: {event.execution_id}")

        logger.debug(
            f"Active executions: {self._metrics['active_executions']}, Total: {self._metrics['total_executions']}"
        )

        # Note: In a full implementation, this would:
        # 1. Start monitoring execution health
        # 2. Set up timeout watchdog
        # 3. Stream logs to subscribers
        # 4. Update execution dashboard

    async def _handle_execution_completed(self, event: ExecutionCompletedEvent) -> None:
        """
        Handle execution completion - update metrics, trigger next steps.

        Args: event: ExecutionCompletedEvent event
        """
        self._metrics["completed_executions"] += 1
        self._metrics["active_executions"] -= 1
        self._active_executions.pop(event.execution_id, None)

        logger.info(
            f"Execution completed: {event.execution_id} " f"(work_item: {event.work_item_id}, agent: {event.agent_id})"
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

    async def _handle_execution_failed(self, event: ExecutionFailedEvent) -> None:
        """
        Handle execution failure - track errors, trigger retry or escalation.

        Args: event: ExecutionFailedEvent event
        """
        self._metrics["failed_executions"] += 1
        self._metrics["active_executions"] -= 1
        self._active_executions.pop(event.execution_id, None)

        logger.error(
            f"Execution failed: {event.execution_id}, error: {event.error}",
            extra={"error_id": "ERR_EXECUTION_FAILED"},
        )

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

    async def _handle_execution_timeout(self, event: ExecutionTimedOutEvent) -> None:
        """
        Handle execution timeout.

        Args: event: ExecutionTimedOutEvent event
        """
        self._metrics["timed_out_executions"] += 1
        self._metrics["failed_executions"] += 1
        self._metrics["active_executions"] -= 1
        self._active_executions.pop(event.execution_id, None)

        logger.error(
            f"Execution timed out: {event.execution_id}",
            extra={"error_id": ErrorRegistry.ERR_EXECUTION_TIMEOUT},
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
        return self._metrics["completed_executions"] / self._metrics["total_executions"] * 100

    def _get_failure_rate(self) -> float:
        """Calculate failure rate percentage."""
        if self._metrics["total_executions"] == 0:
            return 0.0
        return self._metrics["failed_executions"] / self._metrics["total_executions"] * 100

    def _get_timeout_rate(self) -> float:
        """Calculate timeout rate percentage."""
        if self._metrics["total_executions"] == 0:
            return 0.0
        return self._metrics["timed_out_executions"] / self._metrics["total_executions"] * 100

    def get_metrics(self) -> dict[str, float]:
        """
        Get execution metrics.

        Returns: Dictionary of execution metrics
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

        Returns: Dictionary mapping execution_id to work_item_id
        """
        return dict(self._active_executions)
