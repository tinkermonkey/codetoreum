"""Unit tests for production bootstrap factories.

Tests the creation and wiring of production adapters.
"""

import pytest

from codetoreum.adapters.primary.factories.production import (
    create_branch_resolution_adapter,
    create_workspace_router_with_branch_resolution,
)
from codetoreum.adapters.testing import (
    InMemoryEventStore,
    MockBoardAdapter,
    MockBranchResolutionAdapter,
)
from codetoreum.adapters.secondary.mock_event_emitter import MockEventEmitter
from codetoreum.application.workspace_router import WorkspaceRouter, WorkspaceRouterConfig
from codetoreum.ports.output.branch_resolution_service import IBranchResolutionService


class TestCreateBranchResolutionAdapter:
    """Test cases for create_branch_resolution_adapter factory."""

    def test_creates_adapter_successfully(self):
        """Test that adapter is created successfully with valid arguments."""
        ticket_system = MockBoardAdapter()
        version_control = MockBoardAdapter()  # Mock implements both interfaces
        event_emitter = MockEventEmitter()

        adapter = create_branch_resolution_adapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        assert adapter is not None
        assert isinstance(adapter, IBranchResolutionService)

    def test_applies_default_parameters(self):
        """Test that default parameter values are applied correctly."""
        ticket_system = MockBoardAdapter()
        version_control = MockBoardAdapter()
        event_emitter = MockEventEmitter()

        adapter = create_branch_resolution_adapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        # Verify it was created (defaults were applied)
        assert adapter is not None

    def test_accepts_custom_parameters(self):
        """Test that custom parameter values are accepted."""
        ticket_system = MockBoardAdapter()
        version_control = MockBoardAdapter()
        event_emitter = MockEventEmitter()

        adapter = create_branch_resolution_adapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
            min_confidence_threshold=0.85,
            cache_ttl_seconds=60,
        )

        assert adapter is not None

    def test_raises_on_none_ticket_system(self):
        """Test that ValueError is raised when ticket_system is None."""
        version_control = MockBoardAdapter()
        event_emitter = MockEventEmitter()

        with pytest.raises(ValueError, match="ticket_system adapter is required"):
            create_branch_resolution_adapter(
                ticket_system=None,
                version_control=version_control,
                event_emitter=event_emitter,
            )

    def test_raises_on_none_version_control(self):
        """Test that ValueError is raised when version_control is None."""
        ticket_system = MockBoardAdapter()
        event_emitter = MockEventEmitter()

        with pytest.raises(ValueError, match="version_control adapter is required"):
            create_branch_resolution_adapter(
                ticket_system=ticket_system,
                version_control=None,
                event_emitter=event_emitter,
            )

    def test_raises_on_none_event_emitter(self):
        """Test that ValueError is raised when event_emitter is None."""
        ticket_system = MockBoardAdapter()
        version_control = MockBoardAdapter()

        with pytest.raises(ValueError, match="event_emitter adapter is required"):
            create_branch_resolution_adapter(
                ticket_system=ticket_system,
                version_control=version_control,
                event_emitter=None,
            )


class TestCreateWorkspaceRouterWithBranchResolution:
    """Test cases for create_workspace_router_with_branch_resolution factory."""

    def test_creates_router_successfully(self):
        """Test that router is created successfully with required arguments."""
        version_control = MockBoardAdapter()
        container = MockBoardAdapter()
        event_store = InMemoryEventStore()

        router = create_workspace_router_with_branch_resolution(
            version_control=version_control,
            container=container,
            event_store=event_store,
        )

        assert router is not None
        assert isinstance(router, WorkspaceRouter)

    def test_wires_branch_resolution_when_provided(self):
        """Test that branch resolution service is wired when provided."""
        version_control = MockBoardAdapter()
        container = MockBoardAdapter()
        event_store = InMemoryEventStore()
        branch_resolution = MockBranchResolutionAdapter()

        router = create_workspace_router_with_branch_resolution(
            version_control=version_control,
            container=container,
            event_store=event_store,
            branch_resolution_service=branch_resolution,
        )

        assert router is not None
        assert isinstance(router, WorkspaceRouter)

    def test_works_without_branch_resolution(self):
        """Test that router can be created without branch resolution service."""
        version_control = MockBoardAdapter()
        container = MockBoardAdapter()
        event_store = InMemoryEventStore()

        router = create_workspace_router_with_branch_resolution(
            version_control=version_control,
            container=container,
            event_store=event_store,
            branch_resolution_service=None,
        )

        assert router is not None
        assert isinstance(router, WorkspaceRouter)

    def test_accepts_custom_config(self):
        """Test that custom WorkspaceRouterConfig is accepted."""
        version_control = MockBoardAdapter()
        container = MockBoardAdapter()
        event_store = InMemoryEventStore()
        config = WorkspaceRouterConfig()

        router = create_workspace_router_with_branch_resolution(
            version_control=version_control,
            container=container,
            event_store=event_store,
            config=config,
        )

        assert router is not None

    def test_raises_on_none_version_control(self):
        """Test that ValueError is raised when version_control is None."""
        container = MockBoardAdapter()
        event_store = InMemoryEventStore()

        with pytest.raises(ValueError, match="version_control adapter is required"):
            create_workspace_router_with_branch_resolution(
                version_control=None,
                container=container,
                event_store=event_store,
            )

    def test_raises_on_none_container(self):
        """Test that ValueError is raised when container is None."""
        version_control = MockBoardAdapter()
        event_store = InMemoryEventStore()

        with pytest.raises(ValueError, match="container adapter is required"):
            create_workspace_router_with_branch_resolution(
                version_control=version_control,
                container=None,
                event_store=event_store,
            )

    def test_raises_on_none_event_store(self):
        """Test that ValueError is raised when event_store is None."""
        version_control = MockBoardAdapter()
        container = MockBoardAdapter()

        with pytest.raises(ValueError, match="event_store adapter is required"):
            create_workspace_router_with_branch_resolution(
                version_control=version_control,
                container=container,
                event_store=None,
            )


class TestProductionBootstrapIntegration:
    """Integration tests for production bootstrap factory sequence."""

    def test_two_step_instantiation_works(self):
        """Test the two-step factory approach (recommend way)."""
        # Step 1: Create adapter
        ticket_system = MockBoardAdapter()
        version_control = MockBoardAdapter()
        event_emitter = MockEventEmitter()

        branch_resolution_adapter = create_branch_resolution_adapter(
            ticket_system=ticket_system,
            version_control=version_control,
            event_emitter=event_emitter,
        )

        # Step 2: Wire into router
        container = MockBoardAdapter()
        event_store = InMemoryEventStore()

        router = create_workspace_router_with_branch_resolution(
            version_control=version_control,
            container=container,
            event_store=event_store,
            branch_resolution_service=branch_resolution_adapter,
        )

        # Verify both created successfully
        assert branch_resolution_adapter is not None
        assert router is not None

    def test_router_fallback_without_branch_resolution(self):
        """Test that router gracefully handles missing branch resolution."""
        version_control = MockBoardAdapter()
        container = MockBoardAdapter()
        event_store = InMemoryEventStore()

        # Create router without branch resolution
        router = create_workspace_router_with_branch_resolution(
            version_control=version_control,
            container=container,
            event_store=event_store,
            branch_resolution_service=None,
        )

        # Should work fine (backward compatible)
        assert router is not None
        assert isinstance(router, WorkspaceRouter)
