"""Wiring module for connecting adapters to the central event bus.

This module provides functions to wire event-emitting adapters to the central
event bus, enabling the event-driven orchestrator architecture.

The wiring connects:
- Board service events to the event bus
- Discussion adapter events to the event bus
- Lock service events to the event bus
- Review service events to the event bus

All adapters emit their events to the event bus via handlers registered here.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.event_bus_protocols import (
    IBoardService,
    ICodeReviewService,
    IDiscussionAdapter,
    IPipelineLockService,
)

logger = logging.getLogger(__name__)


class EventBusWiring:
    """Manages wiring of adapters to the central event bus."""

    def __init__(self, event_bus: EventBus):
        """
        Initialize event bus wiring.

        Args:
            event_bus: Central event bus for all event routing
        """
        self._event_bus = event_bus
        self._wired_adapters = set()
        self._pending_tasks: set = set()  # Track background tasks for cleanup

    def wire_board_service(self, board_service: IBoardService) -> None:
        """
        Wire a board service to the event bus.

        The board service should have an `on()` method for registering event handlers.

        Args:
            board_service: Board service adapter implementing event emission
        """
        if not self._has_event_method(board_service):
            logger.warning("Board service does not implement on() method, skipping")
            return

        # Wire board events
        board_service.on("workitem.column_changed", self._create_event_publisher())
        board_service.on("board.reconciled", self._create_event_publisher())

        self._wired_adapters.add("board_service")
        logger.info("Wired board service to event bus")

    def wire_discussion_adapter(self, discussion_adapter: IDiscussionAdapter) -> None:
        """
        Wire a discussion adapter to the event bus.

        The discussion adapter should have an `on()` method for registering event handlers.

        Args:
            discussion_adapter: Discussion adapter implementing event emission
        """
        if not self._has_event_method(discussion_adapter):
            logger.warning("Discussion adapter does not implement on() method, skipping")
            return

        # Wire discussion events
        discussion_adapter.on("comment.needs_response", self._create_event_publisher())
        discussion_adapter.on("comment.posted", self._create_event_publisher())

        self._wired_adapters.add("discussion_adapter")
        logger.info("Wired discussion adapter to event bus")

    def wire_lock_service(self, lock_service: IPipelineLockService) -> None:
        """
        Wire a lock service to the event bus.

        The lock service should have an `on()` method for registering event handlers.

        Args:
            lock_service: Lock service implementing event emission
        """
        if not self._has_event_method(lock_service):
            logger.warning("Lock service does not implement on() method, skipping")
            return

        # Wire lock events
        lock_service.on("lock.acquired", self._create_event_publisher())
        lock_service.on("lock.released", self._create_event_publisher())
        lock_service.on("lock.stale_detected", self._create_event_publisher())

        self._wired_adapters.add("lock_service")
        logger.info("Wired lock service to event bus")

    def wire_review_service(self, review_service: ICodeReviewService) -> None:
        """
        Wire a code review service to the event bus.

        The review service should have an `on()` method for registering event handlers.

        Args:
            review_service: Code review service implementing event emission
        """
        if not self._has_event_method(review_service):
            logger.warning("Review service does not implement on() method, skipping")
            return

        # Wire review events
        review_service.on("review.status_changed", self._create_event_publisher())
        review_service.on("review.comment_added", self._create_event_publisher())

        self._wired_adapters.add("review_service")
        logger.info("Wired review service to event bus")

    def wire_all_adapters(
        self,
        board_service: IBoardService | None = None,
        discussion_adapter: IDiscussionAdapter | None = None,
        lock_service: IPipelineLockService | None = None,
        review_service: ICodeReviewService | None = None,
    ) -> None:
        """
        Wire all provided adapters to the event bus.

        Args:
            board_service: Board service adapter (optional)
            discussion_adapter: Discussion adapter (optional)
            lock_service: Lock service (optional)
            review_service: Code review service (optional)
        """
        if board_service:
            self.wire_board_service(board_service)

        if discussion_adapter:
            self.wire_discussion_adapter(discussion_adapter)

        if lock_service:
            self.wire_lock_service(lock_service)

        if review_service:
            self.wire_review_service(review_service)

        logger.info(f"Wired {len(self._wired_adapters)} adapters to event bus")

    def get_wired_adapters(self) -> set:
        """
        Get set of wired adapter names.

        Returns:
            Set of wired adapter names
        """
        return self._wired_adapters.copy()

    def _has_event_method(self, adapter: Any) -> bool:
        """
        Check if adapter has event emission method.

        Args:
            adapter: Adapter to check

        Returns:
            True if adapter has on() method
        """
        return hasattr(adapter, "on") and callable(adapter.on)

    def _create_event_publisher(self) -> Callable:
        """
        Create an event publisher callback for adapters.

        The publisher handles both sync and async event emission to the bus,
        with proper error handling and task tracking.

        Returns:
            Callback function to publish events
        """

        def publisher(event) -> None:
            """Publish event to the event bus."""
            # Schedule async publish as a background task with error handling
            task = asyncio.create_task(self._event_bus.publish(event))

            # Track the task and remove it when done
            self._pending_tasks.add(task)
            task.add_done_callback(lambda t: self._handle_task_done(t))

        return publisher

    def _handle_task_done(self, task) -> None:
        """Handle completion of a background task and log any errors."""
        self._pending_tasks.discard(task)
        try:
            task.result()
        except Exception as e:
            logger.error(
                f"Error publishing event in background task: {e}",
                exc_info=True,
                extra={"task_id": id(task), "error_id": ErrorRegistry.ERR_EVENT_BUS_ERROR}
            )
            # TODO: Track metric for background task failures
            # TODO: Consider emitting system event for monitoring


def wire_adapters_to_event_bus(
    event_bus: EventBus,
    board_service: IBoardService | None = None,
    discussion_adapter: IDiscussionAdapter | None = None,
    lock_service: IPipelineLockService | None = None,
    review_service: ICodeReviewService | None = None,
) -> EventBusWiring:
    """
    Wire adapter event emitters to the central event bus.

    This is the main entry point for setting up event-driven adapter integration.

    Args:
        event_bus: Central event bus for routing
        board_service: Board service adapter (optional)
        discussion_adapter: Discussion adapter (optional)
        lock_service: Lock service (optional)
        review_service: Code review service (optional)

    Returns:
        EventBusWiring instance managing the wired adapters

    Example:
        ```python
        # Create event bus
        event_bus = EventBus()

        # Create adapters
        board_service = GitHubBoardAdapter(...)
        discussion_adapter = GitHubDiscussionAdapter(...)

        # Wire adapters to event bus
        wiring = wire_adapters_to_event_bus(
            event_bus,
            board_service=board_service,
            discussion_adapter=discussion_adapter
        )

        # Adapters now emit events to the event bus
        ```
    """
    wiring = EventBusWiring(event_bus)
    wiring.wire_all_adapters(
        board_service=board_service,
        discussion_adapter=discussion_adapter,
        lock_service=lock_service,
        review_service=review_service,
    )
    return wiring
