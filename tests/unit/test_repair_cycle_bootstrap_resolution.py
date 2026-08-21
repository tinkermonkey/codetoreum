"""Unit test for repair-cycle adapter resolution through bootstrap/resolver.

Validates that the ProductionRepairCycleAdapter is correctly resolved and wired
through the real AdapterResolver with production configuration, and that the
resolved adapter can execute repair-cycle scenarios end-to-end.
"""

import pytest

from codetoreum.adapters.secondary.production_repair_cycle_adapter import (
    ProductionRepairCycleAdapter,
    RepairCycleConfig,
)
from codetoreum.adapters.testing.in_memory_checkpoint_store import (
    InMemoryCheckpointStore,
)
from codetoreum.domain.repair_cycle_types import (
    RepairTestRunConfig,
    RepairTestType,
)
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
from tests.simulation.scenarios.scenario_07_repair_cycle import (
    create_repair_context,
)


class MockCodingAgent:
    """Mock coding agent that simulates successful test execution."""

    async def __call__(self, *args, **kwargs):
        """Return mock success response."""
        return MockAgentResponse(
            stdout='{"passed": 10, "failed": 0, "warnings": [], "failures": []}',
            stderr="",
            exit_code=0,
        )


class MockAgentResponse:
    """Mock response from coding agent."""

    def __init__(self, stdout: str, stderr: str, exit_code: int):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code


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
        from codetoreum.infrastructure.adapters.factory import (
            AdapterFactory,
        )
        from codetoreum.infrastructure.adapters.resolver import (
            AdapterDependencies,
        )
        from codetoreum.adapters.testing import CapturingMockEventEmitter

        # Create minimal dependencies for resolver
        event_bus = EventBus()
        engine_stub = ProductionEngineStub()
        factory = AdapterFactory()
        event_emitter = CapturingMockEventEmitter()

        # Create a minimal failed event store (required by resolver)
        class SimpleFailedEventStore:
            """Minimal implementation for testing."""

            async def record_failed_event(self, event):
                pass

        failed_event_store = SimpleFailedEventStore()

        adapter_deps = AdapterDependencies(
            event_bus=event_bus,
            event_emitter=event_emitter,
            logger=None,  # type: ignore
            engine=engine_stub,
            config=None,  # type: ignore
            failed_event_store=failed_event_store,  # type: ignore
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
        from codetoreum.infrastructure.adapters.factory import (
            AdapterFactory,
        )
        from codetoreum.infrastructure.adapters.resolver import (
            AdapterDependencies,
        )
        from codetoreum.adapters.testing import CapturingMockEventEmitter

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

        class SimpleFailedEventStore:
            async def record_failed_event(self, event):
                pass

        failed_event_store = SimpleFailedEventStore()

        adapter_deps = AdapterDependencies(
            event_bus=event_bus,
            event_emitter=event_emitter,
            logger=None,  # type: ignore
            engine=engine_stub,
            config=None,  # type: ignore
            failed_event_store=failed_event_store,  # type: ignore
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
