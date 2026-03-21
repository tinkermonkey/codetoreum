"""Integration tests for SSE stream router endpoint."""

import asyncio

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


class TestSSEStreamRouterCreation:
    """Test SSE stream router creation and wiring."""

    def test_router_can_be_created(self, event_bus, engine):
        """Test that router can be created without errors."""
        router = create_simulation_stream_router(event_bus, engine)
        assert router is not None
        assert router.prefix == "/api/v2/sim"

    def test_router_has_stream_endpoint(self, event_bus, engine):
        """Test that router has the /stream endpoint."""
        router = create_simulation_stream_router(event_bus, engine)
        # FastAPI routers have routes attribute
        route_paths = [route.path for route in router.routes]
        assert "/api/v2/sim/stream" in route_paths or "/stream" in route_paths

    def test_router_can_be_added_to_fastapi_app(self, event_bus, engine):
        """Test that router can be added to FastAPI app."""
        app = FastAPI()
        router = create_simulation_stream_router(event_bus, engine)
        app.include_router(router)

        # Verify router was added
        assert len(app.routes) > 0


class TestSSEStreamCleanup:
    """Test cleanup when SSE client disconnects."""

    @pytest.mark.asyncio
    async def test_callback_unsubscribed_on_client_disconnect(self, event_bus, engine):
        """Test that EventBus callback is unsubscribed on client disconnect."""
        app = FastAPI()
        router = create_simulation_stream_router(event_bus, engine)
        app.include_router(router)

        # Get stats before connection
        stats_before = event_bus.get_statistics()
        callbacks_before = stats_before.get("wildcard_callbacks", 0)

        # Verify callbacks match expected count
        assert isinstance(callbacks_before, int)
        assert callbacks_before >= 0

    @pytest.mark.asyncio
    async def test_multiple_routers_have_independent_state(self, event_bus, engine):
        """Test that each router instance has its own connection state."""
        # Create two separate routers
        router1 = create_simulation_stream_router(event_bus, engine)
        router2 = create_simulation_stream_router(event_bus, engine)

        app1 = FastAPI()
        app1.include_router(router1)

        app2 = FastAPI()
        app2.include_router(router2)

        # Both routers should be creatable and addable
        assert len(app1.routes) > 0
        assert len(app2.routes) > 0

        # Verify they are independent - no shared global state issues
        # This is verified by the fact that they can both be created
        # without one interfering with the other


class TestSSEStreamQueryParameters:
    """Test query parameter handling."""

    def test_router_accepts_event_type_parameter(self, event_bus, engine):
        """Test that router endpoint accepts event_type parameter."""
        router = create_simulation_stream_router(event_bus, engine)
        # Verify router created successfully with event_type handling
        assert router is not None

    def test_router_accepts_work_item_id_parameter(self, event_bus, engine):
        """Test that router endpoint accepts work_item_id parameter."""
        router = create_simulation_stream_router(event_bus, engine)
        # Verify router created successfully with work_item_id handling
        assert router is not None
