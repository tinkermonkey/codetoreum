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
        with checkpoint_store properly wired and the mock coding agent factory
        properly injected during construction.
        """
        from codetoreum.adapters.testing import CapturingMockEventEmitter
        from codetoreum.infrastructure.adapters.factory import (
            AdapterFactory,
        )
        from codetoreum.infrastructure.adapters.resolver import (
            AdapterDependencies,
            AdapterResolver,
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

        # Mock coding agent factory (returns inert mock for testing)
        async def mock_coding_agent_factory(prompt_builder):
            return MockCodingAgent()

        # Custom resolver subclass that uses the mock factory
        class TestAdapterResolver(AdapterResolver):
            """Resolver that injects mock coding agent factory for testing."""

            def _create_coding_agent_factory(self):
                """Override to return mock factory instead of real one."""
                return mock_coding_agent_factory

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

        resolver = TestAdapterResolver(
            adapter_config=adapter_config,
            factory=factory,
            dependencies=adapter_deps,
        )

        # Set up required resolved dependencies
        checkpoint_store = InMemoryCheckpointStore()
        resolver._resolved["checkpoint_store"] = checkpoint_store
        resolver._resolved["systemic_analysis_service"] = None
        resolver._resolved["environment_repair_service"] = None

        # Resolve adapter through real resolver path with mock factory
        adapter = resolver.resolve_repair_cycle()

        # Verify it's the production adapter
        assert isinstance(adapter, ProductionRepairCycleAdapter)
        assert adapter.checkpoint_store is not None

        # Verify the mock factory was wired during construction (not after)
        # by checking that the adapter can execute with the mock
        # (if it were using the real factory, execution would fail due to
        # lack of Claude Code credentials)

        # Create a minimal repair-cycle context
        test_configs = (
            RepairTestRunConfig(test_type=RepairTestType.UNIT),
        )
        context = create_repair_context(
            test_configs=test_configs,
            stage_name="testing",
            max_total_agent_calls=100,
        )

        # Execute the scenario (verifies adapter can run end-to-end)
        # This exercises the production adapter's execute path with the real
        # checkpoint_store wiring, confirming Phase 1 fix works in practice,
        # and the mock coding agent factory is properly used.
        try:
            # Execute returns when the scenario completes or times out
            result = await adapter.execute(context)
            # Execution succeeded; checkpoint_store remains accessible and wired
            assert adapter.checkpoint_store is checkpoint_store
        except Exception:
            # If execution raises, checkpoint_store should still be accessible
            assert adapter.checkpoint_store is checkpoint_store
            raise

    @pytest.mark.asyncio
    async def test_resolve_all_produces_production_repair_cycle_with_dependencies(self) -> None:
        """Verify resolve_all() fully exercises the repair_cycle dependency-ordering path.

        This test validates that the repair-cycle scenario is correctly resolved through
        the full `AdapterResolver.resolve_all()` path, which validates the dependency-ordering
        machinery (steps 6, 9, 9b before step 10 in resolve_all()). This catches regressions
        where dependencies like checkpoint_store might be resolved *after* repair_cycle,
        breaking the feature silently.

        The test:
        1. Constructs a minimal AdapterResolver with production config (repair_cycle="production")
        2. Calls resolve_all() to exercise the full dependency-ordering sequence
        3. Verifies that resolve_repair_cycle() (step 10) receives all its required dependencies:
           - checkpoint_store (resolved in step 6)
           - systemic_analysis_service (resolved in step 9)
           - environment_repair_service (resolved in step 9b)
        4. Asserts the resolved adapter is ProductionRepairCycleAdapter with
           checkpoint_store properly wired (not None)

        Difference from test_adapter_resolver_resolves_production_repair_cycle:
        - That test manually populates _resolved and calls resolve_repair_cycle() in isolation
        - This test calls resolve_all() to validate the full dependency-ordering chain
        """
        # Create test adapter config with production repair_cycle
        adapter_config = AdapterSelectionConfig(
            repair_cycle="production",
            ticket="in_memory",
            version_control="in_memory",
            container="fake",
            board="mock",
            code_review="mock",
            event_store="in_memory",
        )

        # Set up resolver dependencies
        from codetoreum.adapters.testing import CapturingMockEventEmitter
        from codetoreum.infrastructure.adapters.factory import (
            AdapterFactory,
        )
        from codetoreum.infrastructure.adapters.resolver import (
            AdapterDependencies,
        )

        event_bus = EventBus()
        engine_stub = ProductionEngineStub()
        factory = AdapterFactory()
        event_emitter = CapturingMockEventEmitter()
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

        # Call resolve_all() to fully exercise the dependency-ordering machinery
        # This validates steps 6, 9, 9b execute before step 10 (repair_cycle)
        resolved_adapters = resolver.resolve_all()

        # Verify the repair_cycle adapter was resolved as part of resolve_all()
        repair_cycle_adapter = resolved_adapters.repair_cycle

        # Verify the adapter is ProductionRepairCycleAdapter (not a mock)
        assert isinstance(repair_cycle_adapter, ProductionRepairCycleAdapter)

        # Verify checkpoint_store is wired (not None) — Phase 1 fix
        # This would be None if the production branch of resolve_repair_cycle()
        # didn't properly wire checkpoint_store from _resolved["checkpoint_store"]
        assert repair_cycle_adapter.checkpoint_store is not None
        assert isinstance(
            repair_cycle_adapter.checkpoint_store, InMemoryCheckpointStore
        )

        # Verify that all upstream dependencies were resolved before repair_cycle
        # by checking that they exist in the returned adapters
        assert resolved_adapters.checkpoint_store is not None
        assert resolved_adapters.systemic_analysis_service is not None
        assert resolved_adapters.environment_repair_service is not None

        # Verify the checkpoint_store in repair_cycle is the same instance
        # resolved in step 6, demonstrating proper dependency injection
        assert (
            repair_cycle_adapter.checkpoint_store
            is resolved_adapters.checkpoint_store
        )
