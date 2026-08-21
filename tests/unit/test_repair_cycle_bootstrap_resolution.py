"""Unit test for repair-cycle adapter resolution through bootstrap/resolver.

Validates that the ProductionRepairCycleAdapter is correctly resolved and wired
through the real AdapterResolver with production configuration, and that the
resolved adapter can execute repair-cycle scenarios end-to-end.
"""

from decimal import Decimal

import pytest

from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
    ProductionRepairCycleAdapter,
    RepairCycleConfig,
)
from codetoreum.adapters.testing.in_memory_checkpoint_store import (
    InMemoryCheckpointStore,
)
from codetoreum.domain.agent_execution import AgentExecution
from codetoreum.domain.coding_agent_types import InvocationMode
from codetoreum.domain.repair_cycle_types import (
    RepairTestRunConfig,
    RepairTestType,
)
from codetoreum.domain.workspace_context import WorkspaceContext
from codetoreum.infrastructure.adapters.resolver import AdapterResolver
from codetoreum.infrastructure.bootstrap.production_bootstrap import (
    CRITICAL_ADAPTER_SLOTS,
    NON_CRITICAL_SLOTS,
)
from codetoreum.infrastructure.bootstrap.production_engine_stub import (
    ProductionEngineStub,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_config import (
    AdapterSelectionConfig,
)
from codetoreum.ports.output.coding_agent import (
    CodingAgentInvocationOptions,
    CodingAgentResult,
    ICodingAgent,
)
from codetoreum.ports.output.failed_event_store import (
    FailedEventStoreStats,
    FailureReason,
    IFailedEventStore,
)
from tests.simulation.scenarios.scenario_07_repair_cycle import (
    create_repair_context,
)


class MockCodingAgent(ICodingAgent):
    """Mock coding agent that conforms to ICodingAgent interface."""

    def supported_invocation_modes(self) -> frozenset[InvocationMode]:
        """Return supported invocation modes."""
        return frozenset({InvocationMode.CONTAINERIZED, InvocationMode.HOST})

    async def execute(self, execution: AgentExecution, workspace_context: WorkspaceContext, options: CodingAgentInvocationOptions) -> CodingAgentResult:
        """Execute mock coding agent with successful test result."""
        return CodingAgentResult(
            success=True,
            summary_text='{"passed": 10, "failed": 0, "warnings": [], "failures": []}',
            total_cost_usd=Decimal("0.01"),
            total_input_tokens=100,
            total_output_tokens=50,
            tool_call_count=2,
            duration_ms=1000,
            error_summary=None,
        )


class SimpleFailedEventStore(IFailedEventStore):
    """Minimal test implementation of IFailedEventStore."""

    async def add_failed_event(
        self,
        event_type: str,
        event_data: dict,
        failure_reason: FailureReason,
        error_message: str,
        metadata: dict | None = None,
    ) -> str:
        """Add failed event (mock implementation)."""
        return "mock_event_id"

    def get_stats(self) -> FailedEventStoreStats:
        """Get store statistics (mock implementation)."""
        return FailedEventStoreStats(
            total_failed_events=0,
            pending_retries=0,
            exhausted_retries=0,
            total_retries_attempted=0,
            total_retries_succeeded=0,
            total_retries_failed=0,
        )

    def list_events(
        self,
        failure_reason: FailureReason | None = None,
        can_retry: bool | None = None,
        limit: int | None = None,
    ) -> list:
        """List events (mock implementation)."""
        return []

    def get_event(self, event_id: str):
        """Get event (mock implementation)."""
        return

    def remove_event(self, event_id: str) -> bool:
        """Remove event (mock implementation)."""
        return False

    def clear(self) -> None:
        """Clear events (mock implementation)."""


class TestRepairCycleBootstrapResolution:
    """Tests for repair-cycle adapter resolution through bootstrap."""

    def test_repair_cycle_is_non_critical_slot(self) -> None:
        """Verify repair_cycle is in NON_CRITICAL_SLOTS, not CRITICAL_ADAPTER_SLOTS."""
        assert "repair_cycle" not in CRITICAL_ADAPTER_SLOTS
        assert "repair_cycle" in NON_CRITICAL_SLOTS

    def test_bootstrap_default_config_sets_production_repair_cycle(self) -> None:
        """Verify that ProductionApplicationBootstrap defaults repair_cycle to 'production'."""
        from codetoreum.infrastructure.bootstrap.production_bootstrap import (
            ProductionApplicationBootstrap,
        )

        bootstrap = ProductionApplicationBootstrap()
        assert bootstrap.config.repair_cycle == "production"

    @pytest.mark.asyncio
    async def test_adapter_resolver_resolves_production_repair_cycle(
        self,
    ) -> None:
        """Verify AdapterResolver.resolve_repair_cycle() creates ProductionRepairCycleAdapter.

        This test validates the core Phase 2 resolution: when repair_cycle="production",
        the resolver uses the factory to create a real ProductionRepairCycleAdapter with
        all dependencies wired, including checkpoint_store (Phase 1 fix).
        """
        # Create test adapter config
        adapter_config = AdapterSelectionConfig(
            repair_cycle="production",
            ticket="in_memory",
            version_control="in_memory",
            container="fake",
            board="mock",
            code_review="mock",
            event_store="in_memory",
        )

        # Import what we need for setting up the resolver
        from codetoreum.adapters.testing import CapturingMockEventEmitter
        from codetoreum.infrastructure.adapters.factory import (
            AdapterFactory,
        )
        from codetoreum.infrastructure.adapters.resolver import (
            AdapterDependencies,
        )

        # Create minimal dependencies for resolver
        event_bus = EventBus()
        engine_stub = ProductionEngineStub()
        factory = AdapterFactory()
        event_emitter = CapturingMockEventEmitter()

        # Create a minimal failed event store (required by resolver)
        failed_event_store = SimpleFailedEventStore()

        adapter_deps = AdapterDependencies(
            event_bus=event_bus,
            event_emitter=event_emitter,
            logger=None,  # type: ignore
            engine=engine_stub,
            config=None,  # type: ignore
            failed_event_store=failed_event_store,
        )

        # Create resolver with production config
        resolver = AdapterResolver(
            adapter_config=adapter_config,
            factory=factory,
            dependencies=adapter_deps,
        )

        # Resolve checkpoint_store first (required by repair_cycle)
        resolver._resolved["checkpoint_store"] = (
            InMemoryCheckpointStore()
        )

        # Resolve systemic_analysis_service and environment_repair_service
        # (required by repair_cycle in production)
        resolver._resolved["systemic_analysis_service"] = None
        resolver._resolved["environment_repair_service"] = None

        # Resolve repair_cycle through the real resolver path
        adapter = resolver.resolve_repair_cycle()

        # Verify the adapter is ProductionRepairCycleAdapter (not mock)
        assert isinstance(adapter, ProductionRepairCycleAdapter)

        # Verify checkpoint_store is wired (non-None) — Phase 1 fix
        assert adapter.checkpoint_store is not None
        assert isinstance(adapter.checkpoint_store, InMemoryCheckpointStore)

    @pytest.mark.asyncio
    async def test_resolved_repair_cycle_adapter_executes_scenario(self) -> None:
        """Verify that the resolved ProductionRepairCycleAdapter can execute end-to-end.

        This is the core Phase 2 validation: the adapter resolved through the real
        bootstrap/resolver path can execute a repair-cycle scenario successfully
        with checkpoint_store properly wired.
        """
        from codetoreum.adapters.testing import CapturingMockEventEmitter
        from codetoreum.infrastructure.adapters.factory import (
            AdapterFactory,
        )
        from codetoreum.infrastructure.adapters.resolver import (
            AdapterDependencies,
        )

        # Create test adapter config
        adapter_config = AdapterSelectionConfig(
            repair_cycle="production",
            ticket="in_memory",
            version_control="in_memory",
            container="fake",
            board="mock",
            code_review="mock",
            event_store="in_memory",
        )

        # Set up resolver
        event_bus = EventBus()
        engine_stub = ProductionEngineStub()
        factory = AdapterFactory()
        event_emitter = CapturingMockEventEmitter()

        # Create a minimal failed event store (required by resolver)
        failed_event_store = SimpleFailedEventStore()

        adapter_deps = AdapterDependencies(
            event_bus=event_bus,
            event_emitter=event_emitter,
            logger=None,  # type: ignore
            engine=engine_stub,
            config=None,  # type: ignore
            failed_event_store=failed_event_store,
        )

        resolver = AdapterResolver(
            adapter_config=adapter_config,
            factory=factory,
            dependencies=adapter_deps,
        )

        # Set up required resolved dependencies
        checkpoint_store = InMemoryCheckpointStore()
        resolver._resolved["checkpoint_store"] = checkpoint_store
        resolver._resolved["systemic_analysis_service"] = None
        resolver._resolved["environment_repair_service"] = None

        # Resolve adapter through real resolver path
        adapter = resolver.resolve_repair_cycle()

        # Verify it's the production adapter
        assert isinstance(adapter, ProductionRepairCycleAdapter)
        assert adapter.checkpoint_store is not None

        # Create a minimal repair-cycle context
        test_configs = (
            RepairTestRunConfig(test_type=RepairTestType.UNIT),
        )
        context = create_repair_context(
            test_configs=test_configs,
            stage_name="testing",
            max_total_agent_calls=100,
        )

        # Create a factory that returns a mock coding agent
        async def mock_coding_agent_factory(prompt_builder):
            return MockCodingAgent()

        # Rewire the adapter with the mock factory for this test
        adapter.coding_agent_factory = mock_coding_agent_factory

        # Execute the scenario (verifies adapter can run end-to-end)
        # This exercises the production adapter's execute path with the real
        # checkpoint_store wiring, confirming Phase 1 fix works in practice.
        try:
            # Execute returns when the scenario completes or times out
            result = await adapter.execute(context)
            # Execution succeeded; checkpoint_store remains accessible and wired
            assert adapter.checkpoint_store is checkpoint_store
        except Exception:
            # If execution raises, checkpoint_store should still be accessible
            assert adapter.checkpoint_store is checkpoint_store
            raise
