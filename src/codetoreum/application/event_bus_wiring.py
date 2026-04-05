"""Wire up event bus to application services and handlers."""

import logging

from codetoreum.application.event_handlers import (
    BranchResolutionEventHandler,
    ExecutionEventHandler,
    RepairCycleEventHandler,
    ReviewEventHandler,
    WorkflowEventHandler,
)
from codetoreum.application.execution_service import ExecutionService
from codetoreum.application.review_service import ReviewService
from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output import IRepairCycle
from codetoreum.ports.output.branch_resolution_service import IBranchResolutionService

logger = logging.getLogger(__name__)


class EventBusWiringError(Exception):
    """Raised when event bus wiring fails."""


class EventBusRegistry:
    """
    Registry for event bus and handlers.

    Manages the lifecycle of:
    - Event bus instance
    - Event handlers
    - Handler registration
    - Dependencies between handlers and services
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ):
        """
        Initialize event bus registry.

        Args:
            event_bus: Optional event bus instance (creates new if not provided)
            max_retries: Maximum retry attempts for failed handlers
            retry_delay_seconds: Delay between retries
        """
        self.event_bus = event_bus or EventBus(
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
        )

        # Track registered handlers
        self._handlers: dict = {}
        self._services: dict = {}

    def register_services(
        self,
        workflow_orchestrator: WorkflowOrchestrator | None = None,
        execution_service: ExecutionService | None = None,
        review_service: ReviewService | None = None,
        repair_cycle: IRepairCycle | None = None,
        branch_resolution_service: IBranchResolutionService | None = None,
        clock: SimulationClock | None = None,
    ) -> None:
        """
        Register application services.

        Args:
            workflow_orchestrator: Workflow orchestrator service
            execution_service: Execution service
            review_service: Review service
            repair_cycle: Repair cycle adapter (for repair cycle automation)
            branch_resolution_service: Branch resolution service (for branch resolution events)
            clock: Simulation clock (for repair cycle)

        Raises:
            EventBusWiringError: If registration fails
        """
        try:
            if workflow_orchestrator:
                self._services["workflow_orchestrator"] = workflow_orchestrator
                logger.info("Registered workflow orchestrator service")

            if execution_service:
                self._services["execution_service"] = execution_service
                logger.info("Registered execution service")

            if review_service:
                self._services["review_service"] = review_service
                logger.info("Registered review service")

            if repair_cycle:
                self._services["repair_cycle"] = repair_cycle
                logger.info("Registered repair cycle adapter")

            if branch_resolution_service:
                self._services["branch_resolution_service"] = branch_resolution_service
                logger.info("Registered branch resolution service")

            if clock:
                self._services["clock"] = clock
                logger.info("Registered simulation clock")

        except Exception as e:
            message = f"Failed to register services: {e}"
            raise EventBusWiringError(message) from e

    def register_handlers(
        self,
        register_workflow: bool = True,
        register_execution: bool = True,
        register_review: bool = True,
        register_repair_cycle: bool = False,
        register_branch_resolution: bool = False,
    ) -> None:
        """
        Register event handlers with the event bus.

        Args:
            register_workflow: Register workflow event handler
            register_execution: Register execution event handler
            register_review: Register review event handler
            register_repair_cycle: Register repair cycle event handler
            register_branch_resolution: Register branch resolution event handler

        Raises:
            EventBusWiringError: If handler registration fails
        """
        try:
            if register_workflow:
                self._register_workflow_handler()

            if register_execution:
                self._register_execution_handler()

            if register_review:
                self._register_review_handler()

            if register_repair_cycle:
                self._register_repair_cycle_handler()

            if register_branch_resolution:
                self._register_branch_resolution_handler()

            logger.info(f"Registered {len(self._handlers)} event handlers with event bus")

        except Exception as e:
            message = f"Failed to register handlers: {e}"
            raise EventBusWiringError(message) from e

    def _register_workflow_handler(self) -> None:
        """Register workflow event handler."""
        if "workflow_orchestrator" not in self._services:
            logger.warning(
                "Skipping workflow handler registration: orchestrator not registered",
                extra={"error_id": "ERR_EVENTBUS_WORKFLOW_SERVICE_NOT_FOUND"},
            )
            return

        handler = WorkflowEventHandler(orchestrator=self._services["workflow_orchestrator"])

        self.event_bus.register_handler(handler)
        self._handlers["workflow"] = handler

        logger.info("Registered WorkflowEventHandler")

    def _register_execution_handler(self) -> None:
        """Register execution event handler."""
        if "execution_service" not in self._services:
            logger.warning(
                "Skipping execution handler registration: service not registered",
                extra={"error_id": "ERR_EVENTBUS_EXECUTION_SERVICE_NOT_FOUND"},
            )
            return

        handler = ExecutionEventHandler(execution_service=self._services["execution_service"])

        self.event_bus.register_handler(handler)
        self._handlers["execution"] = handler

        logger.info("Registered ExecutionEventHandler")

    def _register_review_handler(self) -> None:
        """Register review event handler."""
        if "review_service" not in self._services:
            logger.warning(
                "Skipping review handler registration: service not registered",
                extra={"error_id": "ERR_EVENTBUS_REVIEW_SERVICE_NOT_FOUND"},
            )
            return

        handler = ReviewEventHandler(review_service=self._services["review_service"])

        self.event_bus.register_handler(handler)
        self._handlers["review"] = handler

        logger.info("Registered ReviewEventHandler")

    def _register_repair_cycle_handler(self) -> None:
        """Register repair cycle event handler."""
        if "repair_cycle" not in self._services:
            logger.warning(
                "Skipping repair cycle handler registration: adapter not registered",
                extra={"error_id": "ERR_EVENTBUS_REPAIR_CYCLE_NOT_FOUND"},
            )
            return

        clock = self._services.get("clock")
        handler = RepairCycleEventHandler(
            repair_cycle=self._services["repair_cycle"],
            clock=clock,
            event_bus=self.event_bus,
        )

        self.event_bus.register_handler(handler)
        self._handlers["repair_cycle"] = handler

        logger.info("Registered RepairCycleEventHandler")

    def _register_branch_resolution_handler(self) -> None:
        """Register branch resolution event handler."""
        handler = BranchResolutionEventHandler(
            event_bus=self.event_bus,
        )

        self.event_bus.register_handler(handler)
        self._handlers["branch_resolution"] = handler

        logger.info("Registered BranchResolutionEventHandler")

    def unregister_handlers(self) -> None:
        """Unregister all handlers from the event bus."""
        for handler_name, handler in self._handlers.items():
            self.event_bus.unregister_handler(handler)
            logger.info(f"Unregistered {handler_name} handler")

        self._handlers.clear()

    def get_handler(self, handler_name: str) -> object:
        """
        Get a registered handler by name.

        Args:
            handler_name: Name of handler ("workflow", "execution", "review")

        Returns:
            Event handler instance or None if not registered
        """
        return self._handlers.get(handler_name)

    def get_statistics(self) -> dict:
        """
        Get event bus statistics.

        Returns:
            Dictionary with event bus statistics
        """
        return self.event_bus.get_statistics()

    def reset_statistics(self) -> None:
        """Reset event bus statistics."""
        self.event_bus.reset_statistics()


def setup_event_bus(
    workflow_orchestrator: WorkflowOrchestrator | None = None,
    execution_service: ExecutionService | None = None,
    review_service: ReviewService | None = None,
    repair_cycle: IRepairCycle | None = None,
    branch_resolution_service: IBranchResolutionService | None = None,
    clock: SimulationClock | None = None,
    max_retries: int = 3,
    retry_delay_seconds: float = 1.0,
) -> EventBusRegistry:
    """
    Convenience function to set up event bus with all handlers.

    Args:
        workflow_orchestrator: Workflow orchestrator service
        execution_service: Execution service
        review_service: Review service
        repair_cycle: Repair cycle adapter (for repair cycle automation)
        branch_resolution_service: Branch resolution service (for branch resolution events)
        clock: Simulation clock (for repair cycle)
        max_retries: Maximum retry attempts for failed handlers
        retry_delay_seconds: Delay between retries

    Returns:
        EventBusRegistry with all handlers registered

    Raises:
        EventBusWiringError: If setup fails

    Example:
        ```python
        # Create services
        orchestrator = WorkflowOrchestrator(...)
        execution_svc = ExecutionService(...)
        review_svc = ReviewService(...)
        repair_cycle = MockRepairCycleAdapter(clock)
        branch_resolution = MockBranchResolutionAdapter(clock)

        # Set up event bus
        registry = setup_event_bus(
            workflow_orchestrator=orchestrator,
            execution_service=execution_svc,
            review_service=review_svc,
            repair_cycle=repair_cycle,
            branch_resolution_service=branch_resolution,
            clock=clock,
        )

        # Publish events
        await registry.event_bus.publish(WorkItemCreated(...))
        ```
    """
    registry = EventBusRegistry(
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds,
    )

    # Register services
    registry.register_services(
        workflow_orchestrator=workflow_orchestrator,
        execution_service=execution_service,
        review_service=review_service,
        repair_cycle=repair_cycle,
        branch_resolution_service=branch_resolution_service,
        clock=clock,
    )

    # Register handlers
    registry.register_handlers(
        register_workflow=workflow_orchestrator is not None,
        register_execution=execution_service is not None,
        register_review=review_service is not None,
        register_repair_cycle=repair_cycle is not None,
        register_branch_resolution=branch_resolution_service is not None,
    )

    logger.info("Event bus setup complete")

    return registry
