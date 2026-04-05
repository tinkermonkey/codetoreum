"""
Simulation Engine - Centralizes all simulation timing and coordination.

This module provides the SimulationEngine class which:
1. Owns and fully encapsulates the simulation clock
2. Manages all time-aware simulation components through a single interface
3. Provides controlled access to time operations without exposing implementation
4. Handles automatic clock injection into components that need it
5. Is the sole external interface for simulation behavior

The engine ensures that core application components remain completely
simulation-agnostic - they never receive or use a clock directly.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

if TYPE_CHECKING:
    from codetoreum.adapters.testing.mock_metrics_query_adapter import (
        MockMetricsQueryAdapter,
    )
    from codetoreum.adapters.testing.mock_repair_cycle_adapter import (
        MockRepairCycleAdapter,
    )
    from codetoreum.adapters.testing.mock_review_cycle_adapter import (
        MockReviewCycleAdapter,
    )
    from codetoreum.application.event_handlers import RepairCycleEventHandler
    from codetoreum.ports.output.container import IContainer
    from codetoreum.ports.output.llm_provider import ILLMProvider
    from codetoreum.ports.output.repair_cycle_checkpoint_store import (
        IRepairCycleCheckpointStore,
    )

logger = logging.getLogger(__name__)


class SimulationEngine:
    """
    Encapsulates and manages all simulation timing and coordination.

    This is the single point of control for simulation clock and time-aware
    components. The engine:

    1. Creates and owns the simulation clock privately
    2. Provides public APIs for time operations (advance, wait_for, etc.)
    3. Injects clock into components that need it (adapters, handlers)
    4. Keeps all simulation internals hidden from core application
    5. Manages clock lifecycle (start, stop, reset)

    The engine ensures that core components (domain layer, application layer)
    never see or use the clock directly - they only use the engine's public API.

    For tests and simulation code that need direct clock access (e.g., to verify
    clock synchronization across components), use get_clock_for_testing().

    Usage:
        # In bootstrap:
        engine = SimulationEngine.create(config)
        repair_adapter = engine.create_repair_cycle_adapter()
        review_adapter = engine.create_review_cycle_adapter()
        metrics_adapter = engine.create_metrics_query_adapter()

        # In tests:
        await engine.advance(timedelta(hours=1))
        await engine.wait_for(timedelta(minutes=30))
        engine.now()  # Get current time
        clock = engine.get_clock_for_testing()  # For test assertions
    """

    def __init__(self, clock: SimulationClock):
        """
        Initialize the simulation engine with a clock.

        Args:
            clock: The simulation clock to manage

        Note:
            Use create() factory method instead of __init__ directly.
        """
        self._clock = clock
        logger.debug("SimulationEngine initialized")

    @staticmethod
    def create(config: SimulationConfig | None = None) -> "SimulationEngine":
        """
        Create a new simulation engine with configured clock.

        Args:
            config: Simulation configuration (uses default if None)

        Returns:
            Configured SimulationEngine instance
        """
        if config is None:
            config = SimulationConfig.create_fast_config("default")

        clock = SimulationClock(
            speed_multiplier=config.time.speed_multiplier,
            auto_advance=config.time.auto_advance,
        )

        # Set start time if configured
        if config.time.start_time:
            clock.start_at(config.time.start_time)

        logger.info(
            "Created SimulationEngine",
            extra={
                "speed_multiplier": config.time.speed_multiplier,
                "auto_advance": config.time.auto_advance,
            },
        )

        return SimulationEngine(clock)

    # =========================================================================
    # Time Operations - Public API for core application
    # =========================================================================

    def now(self) -> datetime:
        """
        Get current simulated time.

        Returns:
            Current datetime in UTC
        """
        return self._clock.now()

    def get_clock_for_testing(self) -> SimulationClock:
        """
        Get the simulation clock for testing and verification.

        This method is intended for test code that needs to verify clock
        synchronization across adapters or directly manipulate the clock.
        Application code should use the public engine APIs instead.

        Returns:
            The SimulationClock instance managed by this engine

        Note:
            This breaks encapsulation intentionally for testing purposes.
            Use sparingly and only in test/simulation code.
        """
        return self._clock

    async def advance(self, delta: timedelta) -> None:
        """
        Advance simulation time by a delta.

        Args:
            delta: Amount of time to advance

        Raises:
            ValueError: If delta is negative
        """
        await self._clock.advance(delta)

    async def advance_to(self, target_time: datetime) -> None:
        """
        Advance simulation to a specific time.

        Args:
            target_time: Target datetime

        Raises:
            ValueError: If target_time is before current time
        """
        await self._clock.advance_to(target_time)

    async def wait_for(self, delta: timedelta) -> None:
        """
        Wait for a time delta (in simulated time).

        Args:
            delta: Amount of time to wait
        """
        await self._clock.wait_for(delta)

    async def sleep(self, seconds: float) -> None:
        """
        Sleep for a number of seconds (in simulated time).

        Args:
            seconds: Number of seconds to sleep
        """
        await self._clock.sleep(seconds)

    def schedule_callback(
        self,
        callback,
        at_time: datetime | None = None,
        after_delta: timedelta | None = None,
    ) -> None:
        """
        Schedule a callback to be triggered at a specific time.

        Args:
            callback: Function to call (can be sync or async)
            at_time: Absolute time to trigger (mutually exclusive with after_delta)
            after_delta: Relative time from now (mutually exclusive with at_time)

        Raises:
            ValueError: If neither or both time parameters are provided
        """
        self._clock.schedule_callback(callback, at_time, after_delta)

    def set_speed_multiplier(self, multiplier: float) -> None:
        """
        Change the speed multiplier.

        Args:
            multiplier: New speed multiplier (must be > 0)

        Raises:
            ValueError: If multiplier is <= 0
        """
        self._clock.set_speed_multiplier(multiplier)

    def get_speed_multiplier(self) -> float:
        """Get current speed multiplier."""
        return self._clock.get_speed_multiplier()

    def is_auto_advancing(self) -> bool:
        """
        Check if automatic clock advancement is currently active.

        Returns:
            True if auto-advance is running, False otherwise
        """
        return self._clock.is_auto_advancing()

    async def start_auto_advance(self) -> None:
        """Start automatic clock advancement."""
        await self._clock.start_auto_advance()

    async def stop_auto_advance(self) -> None:
        """Stop automatic clock advancement."""
        await self._clock.stop_auto_advance()

    # =========================================================================
    # Adapter Creation - Injection of clock into time-aware components
    # =========================================================================

    def create_repair_cycle_adapter(
        self,
        llm_factory: "Callable[[str], ILLMProvider]",
        checkpoint_store: "IRepairCycleCheckpointStore | None" = None,
        container_adapter: "IContainer | None" = None,
    ) -> "MockRepairCycleAdapter":
        """
        Create mock repair cycle adapter with injected clock.

        Args:
            llm_factory: Factory callable that takes agent name and returns an ILLMProvider.
                        Required to enforce behavioral parity with production adapter's
                        agent selection and LLM instantiation for contract validation.
            checkpoint_store: Optional checkpoint store for recovery testing.
                            Stores recovery snapshots for repair cycle resumption.
            container_adapter: Optional container adapter for causal linking (FR-2/US-2.4).
                             If provided, the adapter will use actual container test results
                             instead of pre-configured sequences. This enables true causal
                             linking where container test execution results (exit codes,
                             stdout, stderr) directly influence repair decisions.

        Returns:
            MockRepairCycleAdapter instance with clock already configured
        """
        from codetoreum.adapters.testing.mock_repair_cycle_adapter import (
            MockRepairCycleAdapter,
        )

        adapter = MockRepairCycleAdapter(
            llm_factory=llm_factory,
            clock=self._clock,
            checkpoint_store=checkpoint_store,
            container_adapter=container_adapter,
        )
        logger.debug("Created MockRepairCycleAdapter via SimulationEngine")
        return adapter

    def create_review_cycle_adapter(
        self,
        llm_adapter: "ILLMProvider | None" = None,
    ) -> "MockReviewCycleAdapter":
        """
        Create mock review cycle adapter with injected clock.

        Args:
            llm_adapter: Optional LLM adapter for causal linking (FR-2/US-2.2).
                        If provided, the adapter will analyze actual LLM output
                        instead of using pre-configured sequences. This enables true
                        causal linking where LLM-generated code quality (syntax errors,
                        completeness, style issues) directly influences review decisions.

        Returns:
            MockReviewCycleAdapter instance with clock already configured
        """
        from codetoreum.adapters.testing.mock_review_cycle_adapter import (
            MockReviewCycleAdapter,
        )

        adapter = MockReviewCycleAdapter(clock=self._clock, llm_adapter=llm_adapter)
        logger.debug("Created MockReviewCycleAdapter via SimulationEngine")
        return adapter

    def create_metrics_query_adapter(
        self,
        metrics_adapter: object | None = None,
        event_store: object | None = None,
    ) -> "MockMetricsQueryAdapter":
        """
        Create mock metrics query adapter with injected clock.

        Args:
            metrics_adapter: Optional metrics storage adapter
            event_store: Optional event store for event-based metrics

        Returns:
            MockMetricsQueryAdapter instance with clock already configured
        """
        from codetoreum.adapters.primary.input_port_adapters.mock import (
            MockMetricsQueryAdapter,
        )

        adapter = MockMetricsQueryAdapter(
            metrics_adapter=metrics_adapter,
            event_store=event_store,
            clock=self._clock,
        )
        logger.debug("Created MockMetricsQueryAdapter via SimulationEngine")
        return adapter

    # =========================================================================
    # Event Handler Creation - Injection of clock into time-aware handlers
    # =========================================================================

    def create_repair_cycle_event_handler(
        self,
        repair_cycle: object,
        event_bus: object,
        workflow_config: object | None = None,
    ) -> "RepairCycleEventHandler":
        """
        Create repair cycle event handler with injected clock.

        Args:
            repair_cycle: MockRepairCycleAdapter instance
            workflow_config: WorkflowConfigService instance for retrieving column templates
            event_bus: EventBus instance

        Returns:
            RepairCycleEventHandler instance with clock already configured
        """
        from codetoreum.application.event_handlers import RepairCycleEventHandler

        handler = RepairCycleEventHandler(
            repair_cycle=repair_cycle,
            workflow_config=workflow_config,
            clock=self._clock,
            event_bus=event_bus,
        )
        logger.debug("Created RepairCycleEventHandler via SimulationEngine")
        return handler

    def create_branch_resolution_event_handler(
        self,
        event_bus: object,
    ) -> "BranchResolutionEventHandler":
        """
        Create branch resolution event handler for audit trail.

        Args:
            event_bus: EventBus instance

        Returns:
            BranchResolutionEventHandler instance
        """
        from codetoreum.application.event_handlers import BranchResolutionEventHandler

        handler = BranchResolutionEventHandler(event_bus=event_bus)
        logger.debug("Created BranchResolutionEventHandler via SimulationEngine")
        return handler

    # =========================================================================
    # Clock Lifecycle Management
    # =========================================================================

    async def stop(self) -> None:
        """
        Stop the simulation engine (stops auto-advance if running).

        Should be called during teardown to clean up clock resources.
        """
        try:
            await self._clock.stop_auto_advance()
            logger.debug("SimulationEngine stopped")
        except Exception as e:
            logger.error(f"Error stopping SimulationEngine: {e}", exc_info=True)

    def reset(self) -> None:
        """
        Reset the clock to initial state.

        Clears scheduled callbacks and resets time to current instant.
        """
        self._clock.clear_scheduled_callbacks()
        self._clock.start_at(datetime.now(UTC))
        logger.debug("SimulationEngine reset")
