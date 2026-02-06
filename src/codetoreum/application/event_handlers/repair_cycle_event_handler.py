"""Event handler for repair cycle automation.

Subscribes to workitem.column_changed events and orchestrates:
- Detection of work items entering the configured repair cycle stage
- Invocation of the repair cycle (test-fix-validate loop)
- Coordination with repair cycle adapters for test execution
"""

import logging
from dataclasses import dataclass
from typing import Optional

from codetoreum.domain.events import DomainEvent, WorkItemColumnChanged
from codetoreum.domain.repair_cycle_types import (
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.infrastructure.event_bus import EventHandler, event_handler, EventBus
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.exceptions import ExternalServiceError
from codetoreum.ports.output.repair_cycle_service import IRepairCycle

logger = logging.getLogger(__name__)


@dataclass
class RepairCycleEventContext:
    """Context for repair cycle execution from column change event."""

    stage_name: str
    pipeline_run_id: str
    test_configs: tuple
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int


@event_handler("WorkItemColumnChanged")
class RepairCycleEventHandler(EventHandler):
    """Handles workitem.column_changed events for repair cycle automation.

    Responds to work items entering the configured repair cycle stage by initiating the
    deterministic repair cycle (test-fix-validate loop).

    Example:
        handler = RepairCycleEventHandler(
            repair_cycle=repair_adapter,
            clock=simulation_clock,
            event_bus=bus
        )
        bus.register_handler(handler)

        # When a work item moves to the configured repair cycle stage:
        event = WorkItemColumnChanged(
            aggregate_id="item-1",
            payload={
                "work_item_id": "item-1",
                "board_id": "board-1",
                "project_id": "proj-1",
                "from_column": "Code Review",
                "to_column": "Testing",
                "moved_by": "system"
            }
        )
        await bus.publish(event)
        # Handler invokes repair cycle for item
    """

    def __init__(
        self,
        repair_cycle: IRepairCycle,
        clock: Optional[SimulationClock] = None,
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize repair cycle event handler.

        Args:
            repair_cycle: Repair cycle adapter (usually MockRepairCycleAdapter)
            clock: Optional simulation clock for deterministic test execution
            event_bus: Event bus for publishing events
        """
        self.repair_cycle = repair_cycle
        self.clock = clock
        self.event_bus = event_bus

    def get_event_types(self) -> list[str]:
        """Get list of event types this handler processes.

        Returns:
            List of event type names
        """
        return ["WorkItemColumnChanged"]

    async def handle(self, event: DomainEvent) -> None:
        """
        Handle column change event and trigger repair cycle if appropriate.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails (logged but not re-raised)
        """
        if not isinstance(event, WorkItemColumnChanged):
            logger.warning(
                f"RepairCycleEventHandler received unexpected event type: {event.event_type}"
            )
            return

        try:
            await self.handle_column_change(event)
        except Exception as e:
            logger.error(
                f"Error handling repair cycle for {event.payload.get('work_item_id')}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_REPAIR_CYCLE_ERROR},
            )
            raise

    async def handle_column_change(self, event: WorkItemColumnChanged) -> None:
        """
        Process column movement and trigger repair cycle if entering configured repair stage.

        The repair cycle is initiated when a work item enters the configured repair cycle stage.
        The cycle executes test types sequentially (UNIT → INTEGRATION → E2E) with
        fast-fail behavior.

        Args:
            event: WorkItemColumnChanged event with column movement details
        """
        work_item_id = event.payload.get("work_item_id")
        board_id = event.payload.get("board_id")
        project_id = event.payload.get("project_id")
        to_column = event.payload.get("to_column")

        # Only process if work item is entering the configured repair cycle stage
        if to_column != "Testing":
            return

        logger.info(f"Work item {work_item_id} entered configured repair cycle stage, initiating repair cycle")

        try:
            # Create repair cycle context
            context = RepairCycleEventContext(
                stage_name="Testing",
                pipeline_run_id=work_item_id,
                test_configs=(
                    RepairTestRunConfig(test_type=RepairTestType.UNIT),
                    RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
                    RepairTestRunConfig(test_type=RepairTestType.E2E),
                ),
                agent_name="senior_software_engineer",
                max_total_agent_calls=100,
                checkpoint_interval=5,
            )

            # Execute repair cycle
            result = await self.repair_cycle.execute(context)

            logger.info(
                f"Repair cycle completed for {work_item_id}: "
                f"success={result.overall_success}, "
                f"iterations={sum(tr.iterations for tr in result.test_results)}"
            )

            # Emit appropriate event based on result
            if result.overall_success:
                logger.info(f"Repair cycle succeeded for {work_item_id}, moving to next column")
                # In a full implementation, this would emit an event to move the item
                # to the next column (e.g., "Staged" or "Ready for Deploy")
            else:
                logger.warning(
                    f"Repair cycle failed for {work_item_id}, escalating for human review"
                )
                # In a full implementation, this would emit an event to escalate
                # the item for human review or move to an escalation column

        except Exception as e:
            logger.error(
                f"Repair cycle execution failed for {work_item_id}: {e}",
                exc_info=True,
                extra={
                    "error_id": ErrorRegistry.ERR_REPAIR_CYCLE_STAGE_FAILURE,
                    "work_item_id": work_item_id,
                    "project_id": project_id,
                    "board_id": board_id,
                },
            )
            raise
