"""Unit test for CI pipeline adapter resolution through bootstrap/resolver.

Validates that GitHubCIPipelineAdapter is correctly resolved and wired
through the AdapterResolver with GitHub configuration, and that resolution
order places ticket adapter resolution before ci_pipeline resolution.
"""

import pytest

from codetoreum.adapters.secondary.github_ci_pipeline_adapter import GitHubCIPipelineAdapter
from codetoreum.adapters.secondary.github_ticket_adapter import GitHubTicketAdapter
from codetoreum.adapters.testing import CapturingMockEventEmitter
from codetoreum.adapters.testing.mock_ci_pipeline_adapter import MockCIPipelineAdapter
from codetoreum.infrastructure.adapters.resolver import AdapterDependencies, AdapterResolver
from codetoreum.infrastructure.bootstrap.production_engine_stub import (
    ProductionEngineStub,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_config import (
    AdapterSelectionConfig,
)
from codetoreum.ports.output.failed_event_store import (
    FailedEventStoreStats,
    FailureReason,
    IFailedEventStore,
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


class TestCIPipelineBootstrapResolution:
    """Tests for CI pipeline adapter resolution through bootstrap."""

    @pytest.mark.asyncio
    async def test_adapter_resolver_resolves_github_ci_pipeline(self) -> None:
        """Verify AdapterResolver.resolve_ci_pipeline() creates GitHubCIPipelineAdapter.

        This test validates Phase 1 resolution: when ci_pipeline="github",
        the resolver constructs a real GitHubCIPipelineAdapter with proper
        dependencies (ticket_adapter and graphql_client).
        """
        # Create test adapter config with github ci_pipeline
        adapter_config = AdapterSelectionConfig(
            ci_pipeline="github",
            ticket="github",
            event_store="in_memory",
            version_control="in_memory",
            container="fake",
            board="mock",
            code_review="mock",
        )

        # Import what we need for setting up the resolver
        from codetoreum.infrastructure.adapters.factory import AdapterFactory

        # Create minimal dependencies for resolver
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

        # Create resolver
        resolver = AdapterResolver(
            adapter_config=adapter_config,
            factory=factory,
            dependencies=adapter_deps,
        )

        # Resolve ticket first (required by ci_pipeline GitHub variant)
        ticket_adapter = resolver.resolve_ticket()
        resolver._resolved["ticket"] = ticket_adapter

        # Verify ticket_adapter is available before resolve_ci_pipeline
        assert "ticket" in resolver._resolved
        assert resolver._resolved["ticket"] is not None

        # Resolve ci_pipeline through the real resolver path
        ci_pipeline_adapter = resolver.resolve_ci_pipeline()

        # Verify the adapter is GitHubCIPipelineAdapter (not Mock)
        assert isinstance(ci_pipeline_adapter, GitHubCIPipelineAdapter)

        # Verify dependencies are wired correctly
        assert ci_pipeline_adapter._ticket_adapter is not None
        assert ci_pipeline_adapter._graphql is not None

        # Verify ticket_adapter is the same instance we resolved
        assert ci_pipeline_adapter._ticket_adapter is resolver._resolved["ticket"]

    @pytest.mark.asyncio
    async def test_adapter_resolver_resolves_non_github_ci_pipeline(self) -> None:
        """Verify non-github ci_pipeline values still work through factory.

        Ensures backward compatibility: when ci_pipeline is not "github",
        the resolver falls through to the factory call unchanged.
        """
        # Create test adapter config with mock ci_pipeline
        adapter_config = AdapterSelectionConfig(
            ci_pipeline="mock",
            ticket="in_memory",
            event_store="in_memory",
            version_control="in_memory",
            container="fake",
            board="mock",
            code_review="mock",
        )

        from codetoreum.infrastructure.adapters.factory import AdapterFactory

        # Create minimal dependencies for resolver
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

        # Create resolver
        resolver = AdapterResolver(
            adapter_config=adapter_config,
            factory=factory,
            dependencies=adapter_deps,
        )

        # Set up event_emitter which is required by factory
        resolver._resolved["event_emitter"] = event_emitter

        # Resolve ci_pipeline through the real resolver path
        ci_pipeline_adapter = resolver.resolve_ci_pipeline()

        # Verify the adapter is MockCIPipelineAdapter (from factory)
        assert isinstance(ci_pipeline_adapter, MockCIPipelineAdapter)

    @pytest.mark.asyncio
    async def test_resolve_all_places_ticket_before_ci_pipeline(self) -> None:
        """Verify that resolve_all() resolves ticket before ci_pipeline.

        This validates the critical ordering fix: ci_pipeline (GitHub variant)
        depends on ticket_adapter, so ticket must be resolved first.
        """
        # Create test adapter config
        adapter_config = AdapterSelectionConfig(
            ci_pipeline="github",
            ticket="github",
            event_store="in_memory",
            version_control="in_memory",
            container="fake",
            board="mock",
            code_review="mock",
        )

        from codetoreum.infrastructure.adapters.factory import AdapterFactory

        # Create minimal dependencies
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

        # Create resolver
        resolver = AdapterResolver(
            adapter_config=adapter_config,
            factory=factory,
            dependencies=adapter_deps,
        )

        # Call resolve_all to validate ordering
        # This will fail if ci_pipeline is resolved before ticket
        adapters = resolver.resolve_all()

        # Verify both adapters are present and correctly typed
        assert adapters.ticket_system is not None
        assert adapters.ci_pipeline is not None
        assert isinstance(adapters.ci_pipeline, GitHubCIPipelineAdapter)

        # Verify the CI pipeline adapter has ticket_adapter wired
        assert adapters.ci_pipeline._ticket_adapter is not None
        assert adapters.ci_pipeline._ticket_adapter is adapters.ticket_system
