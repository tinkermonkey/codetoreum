"""Mock environment repair adapter for deterministic simulation testing.

This module provides a mock implementation of IEnvironmentRepairService that simulates
environment rebuild and verification without actual LLM calls. It supports configurable
result sequences for comprehensive simulation testing.

The mock adapter:
1. Returns pre-configured RebuildResult and VerificationResult sequences
2. Emits all 4 environment repair domain events
3. Integrates with SimulationClock for deterministic timing
4. Supports result exhaustion scenarios for testing
5. Defaults to success on first attempt
"""

import logging
from collections.abc import Sequence
from datetime import timedelta

from codetoreum.domain.events.repair_cycle_events import (
    EnvironmentRebuildCompletedEvent,
    EnvironmentRebuildStartedEvent,
    EnvironmentVerificationCompletedEvent,
    EnvironmentVerificationStartedEvent,
)
from codetoreum.domain.repair_cycle_types import (
    RebuildResult,
    RepairTestRunConfig,
    VerificationResult,
)
from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock
from codetoreum.ports.output.environment_repair_service import IEnvironmentRepairService
from codetoreum.ports.output.event_emitter import IEventEmitter
from codetoreum.ports.output.repair_cycle_service import RepairCycleContext

logger = logging.getLogger(__name__)

# Default success results for mock adapter
_DEFAULT_REBUILD_RESULT = RebuildResult(
    success=True,
    duration_seconds=30.0,
    actions_taken=("install_dependencies", "configure_environment"),
    error=None,
)

_DEFAULT_VERIFICATION_RESULT = VerificationResult(
    healthy=True,
    checks_passed=("dependencies_installed", "env_vars_set", "services_running"),
    checks_failed=(),
    duration_seconds=5.0,
)


class MockEnvironmentRepairAdapter(IEnvironmentRepairService):
    """Deterministic mock adapter for environment repair simulation testing.

    Provides:
    - Configurable rebuild result sequences
    - Configurable verification result sequences
    - SimulationClock integration for deterministic timing
    - Event emission for all 4 environment repair domain events
    - Default success behavior (first attempt succeeds)

    Example:
        clock = SimulationClock()
        adapter = MockEnvironmentRepairAdapter(clock)

        # Configure custom results
        adapter.set_rebuild_results([
            RebuildResult(success=False, ...),  # First attempt fails
            RebuildResult(success=True, ...),   # Second attempt succeeds
        ])

        # Execute and verify
        result = await adapter.rebuild_environment(
            project="my-project",
            config=test_config,
            context=context
        )
        assert result.success
    """

    def __init__(
        self,
        clock: SimulationClock | None = None,
        event_emitter: IEventEmitter | None = None,
    ) -> None:
        """Initialize mock environment repair adapter.

        Args:
            clock: SimulationClock instance for deterministic time advancement
            event_emitter: Optional event emitter for test verification
        """
        self.clock = clock or SimulationClock()
        self.event_emitter = event_emitter

        # Result sequences for rebuild and verify
        self._rebuild_results: list[RebuildResult] = []
        self._rebuild_index = 0

        self._verification_results: list[VerificationResult] = []
        self._verification_index = 0

    def set_rebuild_results(self, results: Sequence[RebuildResult]) -> None:
        """Configure the sequence of rebuild results to return.

        Args:
            results: Sequence of RebuildResult objects to return on successive calls
        """
        self._rebuild_results = list(results)
        self._rebuild_index = 0
        logger.debug(
            "Mock adapter configured with rebuild results",
            extra={"count": len(self._rebuild_results)},
        )

    def set_verification_results(self, results: Sequence[VerificationResult]) -> None:
        """Configure the sequence of verification results to return.

        Args:
            results: Sequence of VerificationResult objects to return on successive calls
        """
        self._verification_results = list(results)
        self._verification_index = 0
        logger.debug(
            "Mock adapter configured with verification results",
            extra={"count": len(self._verification_results)},
        )

    async def rebuild_environment(
        self,
        project: str,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> RebuildResult:
        """Rebuild the test environment (mock implementation).

        Returns pre-configured results from the sequence, or defaults to success
        on first attempt.

        Args:
            project: Project identifier/name
            config: Test run configuration
            context: Repair cycle execution context

        Returns:
            RebuildResult from configured sequence or default
        """
        # Emit rebuild started event
        if self.event_emitter:
            self.event_emitter.emit(
                EnvironmentRebuildStartedEvent(
                    type="repair_cycle.environment_rebuild_started",
                    timestamp=self.clock.now().isoformat(),
                    source="mock_environment_repair",
                    workflow_run_id=context.workflow_run_id,
                    test_type=config.test_type,
                    iteration=context.iteration,
                )
            )

        # Get result from sequence or use default
        if self._rebuild_index < len(self._rebuild_results):
            result = self._rebuild_results[self._rebuild_index]
            self._rebuild_index += 1
        else:
            result = _DEFAULT_REBUILD_RESULT

        # Advance clock based on result duration
        await self.clock.advance(timedelta(seconds=result.duration_seconds))

        # Emit rebuild completed event
        if self.event_emitter:
            self.event_emitter.emit(
                EnvironmentRebuildCompletedEvent(
                    type="repair_cycle.environment_rebuild_completed",
                    timestamp=self.clock.now().isoformat(),
                    source="mock_environment_repair",
                    workflow_run_id=context.workflow_run_id,
                    test_type=config.test_type,
                    iteration=context.iteration,
                    success=result.success,
                    duration_seconds=result.duration_seconds,
                    actions_taken=result.actions_taken,
                    error=result.error,
                )
            )

        logger.debug(
            "Mock rebuild_environment completed",
            extra={
                "project": project,
                "test_type": config.test_type.value,
                "success": result.success,
                "duration_seconds": result.duration_seconds,
            },
        )

        return result

    async def verify_environment(
        self,
        project: str,
        config: RepairTestRunConfig,
        context: RepairCycleContext,
    ) -> VerificationResult:
        """Verify that the rebuilt environment is ready for testing (mock implementation).

        Returns pre-configured results from the sequence, or defaults to healthy
        on first attempt.

        Args:
            project: Project identifier/name
            config: Test run configuration
            context: Repair cycle execution context

        Returns:
            VerificationResult from configured sequence or default
        """
        # Emit verification started event
        if self.event_emitter:
            self.event_emitter.emit(
                EnvironmentVerificationStartedEvent(
                    type="repair_cycle.environment_verification_started",
                    timestamp=self.clock.now().isoformat(),
                    source="mock_environment_repair",
                    workflow_run_id=context.workflow_run_id,
                    test_type=config.test_type,
                    iteration=context.iteration,
                )
            )

        # Get result from sequence or use default
        if self._verification_index < len(self._verification_results):
            result = self._verification_results[self._verification_index]
            self._verification_index += 1
        else:
            result = _DEFAULT_VERIFICATION_RESULT

        # Advance clock based on result duration
        await self.clock.advance(timedelta(seconds=result.duration_seconds))

        # Emit verification completed event
        if self.event_emitter:
            self.event_emitter.emit(
                EnvironmentVerificationCompletedEvent(
                    type="repair_cycle.environment_verification_completed",
                    timestamp=self.clock.now().isoformat(),
                    source="mock_environment_repair",
                    workflow_run_id=context.workflow_run_id,
                    test_type=config.test_type,
                    iteration=context.iteration,
                    healthy=result.healthy,
                    checks_passed=result.checks_passed,
                    checks_failed=result.checks_failed,
                    duration_seconds=result.duration_seconds,
                )
            )

        logger.debug(
            "Mock verify_environment completed",
            extra={
                "project": project,
                "test_type": config.test_type.value,
                "healthy": result.healthy,
                "duration_seconds": result.duration_seconds,
            },
        )

        return result
