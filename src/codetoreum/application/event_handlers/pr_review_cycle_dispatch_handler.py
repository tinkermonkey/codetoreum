"""Event handler for PR review cycle dispatch.

Listens for WorkItemColumnChangedEvent and initiates PR review cycles
for columns configured with pr_review_cycle_config. Handles cycle number
derivation, max cycles validation, and cycle initiation.

Outcome routing (column movement after cycle completion) is handled
separately by PRReviewCycleEventHandler, which listens for outcome events.
"""

import logging
from datetime import UTC, datetime

from codetoreum.domain.events import DomainEvent
from codetoreum.domain.events.board_events import WorkItemColumnChangedEvent
from codetoreum.domain.types import WorkItemId
from codetoreum.infrastructure.event_bus import EventHandler, event_handler
from codetoreum.ports.exceptions import ExternalServiceError, ResourceNotFoundError
from codetoreum.ports.output.active_workflow_run_registry import (
    IActiveWorkflowRunRegistry,
)
from codetoreum.ports.output.pr_review_cycle_service import (
    IPRReviewCycle,
    PRReviewCycleRequest,
)
from codetoreum.ports.output.work_item_service import IWorkItemService
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


@event_handler("WorkItemColumnChangedEvent")
class PRReviewCycleDispatchHandler(EventHandler):
    """
    Handles WorkItemColumnChangedEvent for PR review cycle dispatch.

    Responds to work item column movements by:
    1. Checking if column has pr_review_cycle_config
    2. Deriving cycle number from existing state
    3. Checking max cycles limit
    4. Initiating the PR review cycle

    Column movement after cycle completion is driven by outcome events,
    not the synchronous return value from start_pr_review_cycle().

    Example:
        handler = PRReviewCycleDispatchHandler(
            pr_review_cycle=cycle_service,
            workflow_config=config_service,
            work_item_service=item_service,
            active_workflow_run_registry=run_registry,
        )
        bus.register_handler(handler)

        # When a WorkItemColumnChangedEvent is published for a PR review column:
        event = WorkItemColumnChangedEvent(
            work_item_id="item-1",
            board_id="board-1",
            project_id="proj-1",
            from_column="In Development",
            to_column="PR Review",
            moved_by="human"
        )
        await bus.publish(event)
        # Handler initiates PR review cycle and emits outcome events
    """

    def __init__(
        self,
        pr_review_cycle: IPRReviewCycle,
        workflow_config: IWorkflowConfigService,
        work_item_service: IWorkItemService,
        active_workflow_run_registry: IActiveWorkflowRunRegistry,
    ):
        """
        Initialize PR review cycle dispatch handler.

        Args:
            pr_review_cycle: PR review cycle service for initiating cycles
            workflow_config: Configuration service for workflow templates
            work_item_service: Work item service for retrieving work item details
            active_workflow_run_registry: Registry for retrieving active workflow run IDs
        """
        self.pr_review_cycle = pr_review_cycle
        self.workflow_config = workflow_config
        self.work_item_service = work_item_service
        self.active_workflow_run_registry = active_workflow_run_registry

    def get_event_types(self) -> list[str]:
        """Get list of event types this handler processes.

        Returns:
            List of event type names
        """
        return ["WorkItemColumnChangedEvent"]

    async def handle(self, event: DomainEvent) -> None:
        """
        Handle column change event and dispatch PR review cycle if applicable.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails
        """
        if not isinstance(event, WorkItemColumnChangedEvent):
            logger.warning(f"PRReviewCycleDispatchHandler received unexpected event type: {event.event_type}")
            return

        try:
            await self.handle_pr_review_column_change(event)
        except Exception as e:
            logger.error(
                f"Error handling PR review cycle dispatch for {event.work_item_id}: {e}",
                exc_info=True,
                extra={"error_id": "ERR_PR_REVIEW_CYCLE_DISPATCH_FAILURE"},
            )
            raise

    async def handle_pr_review_column_change(self, event: WorkItemColumnChangedEvent) -> None:
        """
        Process column movement and dispatch PR review cycle if applicable.

        If the target column has pr_review_cycle_config:
        1. Retrieve workflow configuration
        2. Derive cycle number from existing state
        3. Check max cycles limit
        4. Initiate the cycle

        Args:
            event: WorkItemColumnChangedEvent with column movement details
        """
        work_item_id: str = event.work_item_id or ""
        board_id: str = event.board_id or ""
        project_id: str = event.project_id or ""
        to_column: str = event.to_column or ""

        logger.info(f"Checking PR review cycle for {work_item_id} in column '{to_column}'")

        # Get workflow configuration for this board
        config = await self.workflow_config.get_board_workflow_template(board_id)

        if not config:
            logger.debug(f"No workflow config found for board {board_id}")
            return

        column_config = config.get_column_config(to_column)

        if not column_config:
            logger.debug(f"Column '{to_column}' not found in board {board_id} config")
            return

        # Dispatch PR review cycle only if column has pr_review_cycle_config set
        if not column_config.pr_review_cycle_config:
            logger.debug(f"Column '{to_column}' has no pr_review_cycle_config")
            return

        logger.info(f"Initiating PR review cycle for {work_item_id} in column '{column_config.name}'")

        try:
            # Retrieve current cycle state to derive next cycle number
            try:
                current_state = await self.pr_review_cycle.get_cycle_state(work_item_id, project_id)
            except Exception as e:
                logger.error(
                    f"Failed to retrieve cycle state for {work_item_id}: {e}",
                    exc_info=True,
                    extra={
                        "error_id": "ERR_PR_REVIEW_CYCLE_STATE_RETRIEVAL_FAILURE",
                        "work_item_id": work_item_id,
                        "project_id": project_id,
                    },
                )
                raise

            # Derive cycle_number: None → 1, existing state → state.cycle_number + 1
            if current_state is None:
                cycle_number = 1
            else:
                cycle_number = current_state.cycle_number + 1

            # Check max cycles limit before proceeding
            max_outer_cycles = column_config.pr_review_cycle_config.max_outer_cycles
            if cycle_number > max_outer_cycles:
                logger.info(
                    f"PR review cycle {cycle_number} exceeds max_outer_cycles ({max_outer_cycles}) "
                    f"for {work_item_id}, will be escalated by adapter"
                )
                # The adapter will emit PRReviewCycleMaxCyclesReachedEvent
                # which will be handled by PRReviewCycleEventHandler for column routing

            # Retrieve work item to get pr_id, pr_url, and discussion_id
            try:
                work_item = await self.work_item_service.get_work_item(WorkItemId(work_item_id))
            except Exception as e:
                logger.error(
                    f"Failed to retrieve work item {work_item_id}: {e}",
                    exc_info=True,
                    extra={
                        "error_id": "ERR_PR_REVIEW_CYCLE_WORK_ITEM_RETRIEVAL_FAILURE",
                        "work_item_id": work_item_id,
                    },
                )
                raise

            # Retrieve active workflow run ID
            try:
                active_run = await self.active_workflow_run_registry.get_active_run(work_item_id)
                if not active_run:
                    logger.error(
                        f"No active workflow run found for {work_item_id}",
                        exc_info=False,
                        extra={
                            "error_id": "ERR_PR_REVIEW_CYCLE_NO_ACTIVE_RUN",
                            "work_item_id": work_item_id,
                        },
                    )
                    raise RuntimeError(f"No active workflow run for {work_item_id}")
                workflow_run_id = active_run.run_id
            except Exception as e:
                logger.error(
                    f"Failed to retrieve active workflow run for {work_item_id}: {e}",
                    exc_info=True,
                    extra={
                        "error_id": "ERR_PR_REVIEW_CYCLE_ACTIVE_RUN_RETRIEVAL_FAILURE",
                        "work_item_id": work_item_id,
                    },
                )
                raise

            # Construct PR review cycle request
            pr_review_config = column_config.pr_review_cycle_config
            assert pr_review_config is not None  # For mypy type narrowing
            request = PRReviewCycleRequest(
                work_item_id=work_item_id,
                project_id=project_id,
                board_id=board_id,
                pr_id=work_item.pr_id,
                pr_url=work_item.external_url,  # Use external_url for pr_url
                discussion_id=work_item.discussion_id,
                cycle_number=cycle_number,
                config=pr_review_config,
                workflow_run_id=workflow_run_id,
            )

            # Initiate PR review cycle
            # The cycle will run (synchronously in mock, potentially async in real adapters)
            # and emit outcome events (PRReviewCycleApprovedEvent, PRReviewCycleIssuesFoundEvent, etc.)
            # with `next_column` information.
            #
            # DESIGN: Column movement is driven by outcome events, not by the synchronous
            # return value from start_pr_review_cycle(). The port interface returns PRReviewCycleResult
            # which includes next_column and outcome, but the outcome domain events are the canonical
            # source for column transitions. Event handlers for PRReviewCycleApprovedEvent,
            # PRReviewCycleIssuesFoundEvent, and PRReviewCycleMaxCyclesReachedEvent (in
            # PRReviewCycleEventHandler) handle the actual column movements.
            result = await self.pr_review_cycle.start_pr_review_cycle(request)

            logger.info(
                f"PR review cycle {cycle_number} started for {work_item_id} with outcome: {result.outcome.value}"
            )

        except Exception as e:
            logger.error(
                f"PR review cycle initiation failed for {work_item_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": "ERR_PR_REVIEW_CYCLE_DISPATCH_START_FAILURE",
                    "work_item_id": work_item_id,
                },
            )
            raise
