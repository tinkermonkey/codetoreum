"""Event handler for repair cycle automation.

Subscribes to workitem.column_changed events and orchestrates:
- Detection of work items entering the configured repair cycle stage
- Invocation of the repair cycle (test-fix-validate loop)
- Coordination with repair cycle adapters for test execution
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from codetoreum.domain.events import DomainEvent, WorkItemColumnChanged
from codetoreum.domain.events.repair_cycle_events import RepairCycleCompletedEvent
from codetoreum.domain.repair_cycle_types import (
    EnvironmentRepairConfig,
    RepairCycleAgentConfig,
    RepairCycleStageConfig,
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.infrastructure.event_bus import EventBus, EventHandler, event_handler
from codetoreum.infrastructure.event_types import EventTypes
from codetoreum.infrastructure.observability.instrumentation import (
    instrument_async_function,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.repair_cycle_service import IRepairCycle
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


@dataclass
class RepairCycleEventContext:
    """Context for repair cycle execution from column change event."""

    stage_name: str
    workflow_run_id: str
    work_item_id: str
    test_configs: tuple[RepairTestRunConfig, ...]
    agent_name: str
    max_total_agent_calls: int
    checkpoint_interval: int
    stage_config: RepairCycleStageConfig
    agent_config: RepairCycleAgentConfig | None = None
    systemic_fix_failure_ceiling: int = 50
    iteration: int = 0
    prior_fix_attempts: tuple[str, ...] = ()
    prior_classifications: tuple = ()


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
        workflow_config: IWorkflowConfigService | None = None,
        clock: SimulationClock | None = None,
        event_bus: EventBus | None = None,
    ):
        """
        Initialize repair cycle event handler.

        Args:
            repair_cycle: Repair cycle adapter (usually MockRepairCycleAdapter)
            workflow_config: Workflow config service to retrieve column templates
            clock: Optional simulation clock for deterministic test execution
            event_bus: Event bus for publishing events
        """
        self._repair_cycle = repair_cycle
        self._workflow_config = workflow_config
        self._clock = clock
        self._event_bus = event_bus

    @property
    def repair_cycle(self) -> IRepairCycle:
        """Get the repair cycle adapter."""
        return self._repair_cycle

    @property
    def clock(self) -> SimulationClock | None:
        """Get the simulation clock if configured."""
        return self._clock

    @property
    def event_bus(self) -> EventBus | None:
        """Get the event bus if configured."""
        return self._event_bus

    def get_event_types(self) -> list[str]:
        """Get list of event types this handler processes.

        Returns:
            List of event type names
        """
        return ["WorkItemColumnChanged"]

    @instrument_async_function(
        name="repair_cycle_event_handler.handle",
        attributes={
            "component": "repair_cycle",
            "layer": "application",
        },
    )
    async def handle(self, event: DomainEvent) -> None:
        """
        Handle column change event and trigger repair cycle if appropriate.

        Args:
            event: Domain event to handle

        Raises:
            Exception: If handling fails (logged but not re-raised)
        """
        if not isinstance(event, WorkItemColumnChanged):
            logger.warning(f"RepairCycleEventHandler received unexpected event type: {event.event_type}")
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

    @instrument_async_function(
        name="repair_cycle_event_handler.handle_column_change",
        attributes={
            "component": "repair_cycle",
            "layer": "application",
        },
    )
    async def handle_column_change(self, event: WorkItemColumnChanged) -> None:
        """
        Process column movement and trigger repair cycle if entering configured repair stage.

        The repair cycle is initiated when a work item enters the configured repair cycle stage.
        The cycle executes test types sequentially (UNIT → INTEGRATION → E2E) with
        fast-fail behavior.

        Args:
            event: WorkItemColumnChanged event with column movement details
        """
        work_item_id: str = event.payload.get("work_item_id") or ""
        board_id: str = event.payload.get("board_id") or ""
        project_id: str = event.payload.get("project_id") or ""
        to_column: str = event.payload.get("to_column") or ""

        # Retrieve column template to check if this column triggers a repair cycle
        # (columns with repair_cycle_agents configured are repair cycle columns)
        column = None
        if self._workflow_config:
            template = await self._workflow_config.get_board_workflow_template(board_id)
            if template:
                column = template.get_column_config(to_column)

        # Only process if the column has repair_cycle_agents configured
        if column is None or not column.repair_cycle_agents:
            return

        logger.info(f"Work item {work_item_id} entered configured repair cycle stage, initiating repair cycle")

        try:
            # Extract repair_cycle_agents from column config (checked non-None above)
            agent_config = column.repair_cycle_agents
            assert agent_config is not None
            logger.info(
                f"Using specialized repair cycle agents for column '{to_column}': "
                f"test_execution={agent_config.test_execution}, "
                f"code_fix={agent_config.code_fix}, "
                f"systemic_analysis={agent_config.systemic_analysis}, "
                f"systemic_fix={agent_config.systemic_fix}, "
                f"env_rebuild={agent_config.env_rebuild}, "
                f"env_verification={agent_config.env_verification}"
            )

            # Build test configs: use column's configured types, or fall back to default
            if column.repair_cycle_test_types:
                test_configs = tuple(RepairTestRunConfig(test_type=t) for t in column.repair_cycle_test_types)
            else:
                test_configs = (
                    RepairTestRunConfig(test_type=RepairTestType.UNIT),
                    RepairTestRunConfig(test_type=RepairTestType.INTEGRATION),
                    RepairTestRunConfig(test_type=RepairTestType.E2E),
                )

            stage_config = RepairCycleStageConfig(
                name=to_column,
                test_configs=test_configs,
                agent_name="senior_software_engineer",
                max_total_agent_calls=100,
                checkpoint_interval=5,
                agent_config=agent_config,
                systemic_fix_failure_ceiling=50,
                environment_repair_config=EnvironmentRepairConfig(),
            )
            context = RepairCycleEventContext(
                stage_name=to_column,
                workflow_run_id=work_item_id,  # TODO: derive actual workflow_run_id once pipeline run tracking is available
                work_item_id=work_item_id,
                test_configs=test_configs,
                agent_name="senior_software_engineer",
                max_total_agent_calls=100,
                checkpoint_interval=5,
                stage_config=stage_config,
                agent_config=agent_config,
            )

            # Execute repair cycle
            result = await self._repair_cycle.execute(context)

            logger.info(
                f"Repair cycle completed for {work_item_id}: "
                f"success={result.overall_success}, "
                f"iterations={sum(tr.iterations for tr in result.test_results)}"
            )

            # Emit RepairCycleCompletedEvent on both success and failure paths
            completed_event = RepairCycleCompletedEvent(
                type=EventTypes.REPAIR_CYCLE_COMPLETED,
                timestamp=datetime.now(UTC).isoformat(),
                source="repair_cycle_event_handler",
                overall_success=result.overall_success,
                test_results=result.test_results,
                total_agent_calls=result.total_agent_calls,
                duration_seconds=result.duration_seconds,
                workflow_run_id=work_item_id,
                commit_history=result.commit_history,
                work_item_id=work_item_id,
                board_id=board_id,
            )
            if self._event_bus:
                await self._event_bus.publish(completed_event)  # type: ignore[arg-type]

            if result.overall_success:
                logger.info(f"Repair cycle succeeded for {work_item_id}, moving to next column")
            else:
                logger.warning(f"Repair cycle failed for {work_item_id}, escalating for human review")

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
