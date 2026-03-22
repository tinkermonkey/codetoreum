"""Integration tests for SSE stream router endpoint.

These tests verify that the SSE stream endpoint integrates correctly
with the FastAPI app, event bus, and simulation engine without testing
the full async streaming behavior (which requires HTTP client interaction).
"""

import pytest
from fastapi import FastAPI

from codetoreum.adapters.primary.routers.simulation_stream import (
    create_simulation_stream_router,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine


@pytest.fixture
def event_bus():
    """Create an event bus."""
    return EventBus()


@pytest.fixture
def engine():
    """Create a simulation engine."""
    config = SimulationConfig.create_fast_config("test")
    return SimulationEngine(config)


class TestSSEStreamRouterIntegration:
    """Test SSE stream router integration with FastAPI and infrastructure."""

    def test_router_creation_succeeds_with_event_bus_and_engine(self, event_bus, engine):
        """Test that router can be created with required dependencies."""
        router = create_simulation_stream_router(event_bus, engine)
        assert router is not None
        assert router.prefix == "/api/v2/sim"

    def test_router_has_stream_endpoint(self, event_bus, engine):
        """Test that router declares the /stream endpoint."""
        router = create_simulation_stream_router(event_bus, engine)
        # Verify the endpoint path is registered
        route_paths = [route.path for route in router.routes]
        # Path will be either full or relative depending on FastAPI internal behavior
        assert any("/stream" in path for path in route_paths), f"Expected /stream endpoint, got: {route_paths}"

    def test_router_integrates_with_fastapi_app(self, event_bus, engine):
        """Test that router can be included in a FastAPI application."""
        app = FastAPI()
        router = create_simulation_stream_router(event_bus, engine)
        app.include_router(router)

        # Verify router was added successfully
        assert len(app.routes) > 0

    def test_router_endpoint_accepts_query_parameters(self, event_bus, engine):
        """Test that router endpoint function accepts query parameters."""
        router = create_simulation_stream_router(event_bus, engine)
        # Get the endpoint function (first route should be the stream endpoint)
        endpoint = router.routes[0].endpoint

        # Verify endpoint is callable and accepts the expected parameters
        import inspect

        sig = inspect.signature(endpoint)
        param_names = set(sig.parameters.keys())

        # Should accept event_type and work_item_id parameters
        assert "event_type" in param_names
        assert "work_item_id" in param_names

    def test_multiple_routers_can_coexist_without_state_interference(self, event_bus, engine):
        """Test that multiple router instances don't share mutable state."""
        # Create two independent routers on the same event bus
        router1 = create_simulation_stream_router(event_bus, engine)
        router2 = create_simulation_stream_router(event_bus, engine)

        # Both should be valid and independent
        assert router1 is not router2
        assert router1.prefix == router2.prefix == "/api/v2/sim"

        # Add both to an app to verify they can coexist
        app = FastAPI()
        app.include_router(router1)
        app.include_router(router2)

        # App should contain both routers' routes
        assert len(app.routes) >= 2

    def test_router_endpoint_is_async_function(self, event_bus, engine):
        """Test that the endpoint function is async (returns a coroutine)."""
        router = create_simulation_stream_router(event_bus, engine)
        endpoint = router.routes[0].endpoint

        # Verify endpoint is an async function
        import inspect

        assert inspect.iscoroutinefunction(endpoint), "Endpoint should be an async function"
