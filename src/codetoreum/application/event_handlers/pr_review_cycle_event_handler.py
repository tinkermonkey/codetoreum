"""Event handler for PR review cycle outcome events.

Handles PR review cycle completion events (approved, issues found, max cycles reached)
and moves work items to the appropriate next column based on cycle outcome.
"""

import logging

from codetoreum.domain.events import DomainEvent
from codetoreum.domain.events.pr_review_cycle_events import (
    PRReviewCycleApprovedEvent,
    PRReviewCycleIssuesFoundEvent,
    PRReviewCycleMaxCyclesReachedEvent,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventHandler, event_handler
from codetoreum.ports.exceptions import ExternalServiceError, ResourceNotFoundError
from codetoreum.ports.output.board_service import IBoardService, MovedByType

logger = logging.getLogger(__name__)


@event_handler(
    "PRReviewCycleApprovedEvent",
    "PRReviewCycleIssuesFoundEvent",
    "PRReviewCycleMaxCyclesReachedEvent",
)
class PRReviewCycleEventHandler(EventHandler):
    """
    Handles PR review cycle outcome events for column movement.

    Responds to PR review cycle completion events by moving work items to the
    appropriate next column based on cycle outcome:
    - PRReviewCycleApprovedEvent: Move to next_column (approved path)
    - PRReviewCycleIssuesFoundEvent: Move to next_column (issues found path)
    - PRReviewCycleMaxCyclesReachedEvent: Move to next_column (escalation path)

    The next_column is determined by the cycle adapter and passed in the event.

    Example:
        handler = PRReviewCycleEventHandler(board_service=board_service)
        bus.register_handler(handler)

        # When PRReviewCycleApprovedEvent is published:
        event = PRReviewCycleApprovedEvent(
            type="pr_review_cycle.approved",
            pr_id="PR-123",
            cycle_number=1,
            next_column="Done",
            workflow_run_id="item-1",
            ...
        )
        await bus.publish(event)
        # Handler moves item-1 to "Done" column
    """

    def __init__(self, board_service: IBoardService):
        """
        Initialize PR review cycle event handler.

        Args:
            board_service: Board service for moving work items between columns
        """
        self.board_service = board_service

    def get_event_types(self) -> list[str]:
        """Get list of event types this handler processes.

        Returns:
            List of event type names
        """
        return [
            "PRReviewCycleApprovedEvent",
            "PRReviewCycleIssuesFoundEvent",
            "PRReviewCycleMaxCyclesReachedEvent",
        ]

    async def handle(self, event: DomainEvent) -> None:
        """
        Handle PR review cycle outcome event and move work item to next column.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails
        """
        if isinstance(event, (PRReviewCycleApprovedEvent, PRReviewCycleIssuesFoundEvent, PRReviewCycleMaxCyclesReachedEvent)):
            await self.handle_cycle_outcome(event)
        else:
            logger.warning(f"PRReviewCycleEventHandler received unexpected event type: {type(event).__name__}")

    async def handle_cycle_outcome(
        self,
        event: PRReviewCycleApprovedEvent | PRReviewCycleIssuesFoundEvent | PRReviewCycleMaxCyclesReachedEvent,
    ) -> None:
        """
        Process PR review cycle outcome and move work item to next column.

        Extracts the work_item_id from the event and moves the work item
        to the next_column specified in the event.

        Args:
            event: PR review cycle outcome event with work_item_id and next_column
        """
        work_item_id = event.work_item_id
        next_column = event.next_column

        if not work_item_id or not next_column:
            logger.warning(
                f"Cannot move work item: missing work_item_id or next_column in {type(event).__name__}",
                extra={
                    "event_type": type(event).__name__,
                    "work_item_id": work_item_id,
                    "next_column": next_column,
                },
            )
            return

        # Log the outcome
        if isinstance(event, PRReviewCycleApprovedEvent):
            logger.info(
                f"PR review cycle approved for {work_item_id}, "
                f"moving to column '{next_column}' (cycle {event.cycle_number})"
            )
        elif isinstance(event, PRReviewCycleIssuesFoundEvent):
            logger.info(
                f"PR review cycle issues found for {work_item_id}, "
                f"moving to column '{next_column}' (cycle {event.cycle_number}, {event.total} findings)"
            )
        elif isinstance(event, PRReviewCycleMaxCyclesReachedEvent):
            logger.warning(
                f"PR review cycle max cycles reached for {work_item_id}, "
                f"escalating to column '{next_column}' (cycle {event.cycle_number}/{event.max_cycles})"
            )

        try:
            await self.board_service.move_item_to_column(work_item_id, next_column, MovedByType.ORCHESTRATOR)
            logger.info(f"Moved {work_item_id} to column '{next_column}'")
        except ResourceNotFoundError:
            logger.error(
                f"Cannot move {work_item_id} to '{next_column}': work item not found",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_PR_REVIEW_CYCLE_ITEM_NOT_FOUND,
                    "work_item_id": work_item_id,
                    "next_column": next_column,
                },
            )
            raise
        except ExternalServiceError as e:
            logger.error(
                f"Board service error while moving {work_item_id} to '{next_column}': {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_PR_REVIEW_CYCLE_BOARD_SERVICE_ERROR,
                    "work_item_id": work_item_id,
                    "next_column": next_column,
                },
            )
            raise
        except Exception as e:
            logger.error(
                f"Error moving {work_item_id} to '{next_column}': {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_PR_REVIEW_CYCLE_MOVE_FAILURE,
                    "work_item_id": work_item_id,
                    "next_column": next_column,
                },
            )
            raise
