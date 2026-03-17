"""
Tests for the simulation clock control REST API router.

Tests the endpoints:
- GET /api/v2/sim/clock: Query current clock state
- POST /api/v2/sim/clock/advance: Manually advance the clock
- POST /api/v2/sim/clock/pause: Pause automatic advancement
- POST /api/v2/sim/clock/resume: Resume automatic advancement
"""

import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient

from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig


@pytest.mark.asyncio
class TestSimulationClockRouter:
    """Test the simulation clock control router endpoints."""

    @pytest.fixture
    async def bootstrap(self):
        """Create a bootstrap instance with simulation."""
        config = SimulationConfig.create_fast_config("test_clock_router")
        bootstrap = SimulationApplicationBootstrap(config)
        await bootstrap.setup()
        yield bootstrap
        await bootstrap.teardown()

    @pytest.fixture
    def app(self, bootstrap):
        """Get the FastAPI app from the bootstrap."""
        return bootstrap.app

    async def test_clock_router_get_state(self, app):
        """Test GET /api/v2/sim/clock returns current clock state."""
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/clock")

        assert response.status_code == 200
        data = response.json()

        assert "current_time" in data
        assert "speed_multiplier" in data
        assert "auto_advance_active" in data
        assert isinstance(data["current_time"], str)  # ISO format
        assert isinstance(data["speed_multiplier"], (int, float))
        assert isinstance(data["auto_advance_active"], bool)

    async def test_clock_router_advance_by_seconds(self, app, bootstrap):
        """Test POST /api/v2/sim/clock/advance advances the clock."""
        # Pause auto-advance first
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            pause_response = await client.post("/api/v2/sim/clock/pause")
            assert pause_response.status_code == 200
            assert pause_response.json()["status"] == "paused"

        # Get initial time
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            state_before = await client.get("/api/v2/sim/clock")
            time_before = datetime.fromisoformat(state_before.json()["current_time"])

        # Advance by 30 seconds
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            advance_response = await client.post(
                "/api/v2/sim/clock/advance",
                json={"seconds": 30.0},
            )

        assert advance_response.status_code == 200
        data = advance_response.json()
        assert data["seconds_advanced"] == 30.0
        assert "previous_time" in data
        assert "current_time" in data

        # Verify time was advanced
        time_after = datetime.fromisoformat(data["current_time"])
        time_delta = (time_after - time_before).total_seconds()
        assert 29.9 < time_delta < 30.1  # Allow small floating-point variance

    async def test_clock_router_advance_rejected_while_running(self, app, bootstrap):
        """Test POST /api/v2/sim/clock/advance returns 409 when auto-advance is active."""
        # Resume auto-advance (should be running after bootstrap)
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            await client.post("/api/v2/sim/clock/resume")

        # Try to advance while auto-advance is running
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.post(
                "/api/v2/sim/clock/advance",
                json={"seconds": 10.0},
            )

        assert response.status_code == 409
        assert "auto-advance" in response.json()["detail"].lower()

    async def test_clock_router_pause_stops_auto_advance(self, app, bootstrap):
        """Test POST /api/v2/sim/clock/pause stops auto-advance."""
        # Pause
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.post("/api/v2/sim/clock/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"

        # Verify auto-advance is now inactive
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            state = await client.get("/api/v2/sim/clock")

        assert state.json()["auto_advance_active"] is False

    async def test_clock_router_resume_starts_auto_advance(self, app, bootstrap):
        """Test POST /api/v2/sim/clock/resume starts auto-advance."""
        # First pause
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            await client.post("/api/v2/sim/clock/pause")

        # Verify paused
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            state = await client.get("/api/v2/sim/clock")
        assert state.json()["auto_advance_active"] is False

        # Resume
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.post("/api/v2/sim/clock/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"

        # Verify auto-advance is now active
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            state = await client.get("/api/v2/sim/clock")
        assert state.json()["auto_advance_active"] is True

    async def test_clock_router_endpoints_tagged(self, app):
        """Test that endpoints are properly tagged for Swagger UI."""
        # Get OpenAPI schema
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/openapi.json")

        assert response.status_code == 200
        schema = response.json()

        # Find the simulation-clock tagged endpoints
        paths = schema["paths"]
        clock_endpoints = [p for p in paths.keys() if "/sim/clock" in p]

        assert len(clock_endpoints) > 0, "No clock endpoints found in OpenAPI schema"

        # Verify tags
        for path in clock_endpoints:
            for method in paths[path]:
                if method in ["get", "post"]:
                    operation = paths[path][method]
                    assert "tags" in operation
                    assert "simulation-clock" in operation["tags"]

    async def test_clock_router_state_response_model(self, app):
        """Test GET /api/v2/sim/clock response matches ClockStateResponse model."""
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/clock")

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present
        required_fields = {"current_time", "speed_multiplier", "auto_advance_active"}
        assert set(data.keys()) >= required_fields

        # Verify field types
        assert isinstance(data["current_time"], str)  # ISO datetime
        assert isinstance(data["speed_multiplier"], (int, float))
        assert data["speed_multiplier"] > 0
        assert isinstance(data["auto_advance_active"], bool)

    async def test_clock_router_advance_response_model(self, app, bootstrap):
        """Test POST /api/v2/sim/clock/advance response matches AdvanceClockResponse model."""
        # Pause first
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            await client.post("/api/v2/sim/clock/pause")

        # Advance
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.post(
                "/api/v2/sim/clock/advance",
                json={"seconds": 60.0},
            )

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present
        required_fields = {"previous_time", "current_time", "seconds_advanced"}
        assert set(data.keys()) >= required_fields

        # Verify field types
        assert isinstance(data["previous_time"], str)  # ISO datetime
        assert isinstance(data["current_time"], str)  # ISO datetime
        assert isinstance(data["seconds_advanced"], (int, float))
        assert data["seconds_advanced"] == 60.0

    async def test_clock_router_pause_response_model(self, app):
        """Test POST /api/v2/sim/clock/pause response matches PauseClockResponse model."""
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.post("/api/v2/sim/clock/pause")

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present
        required_fields = {"status", "current_time"}
        assert set(data.keys()) >= required_fields

        # Verify field types
        assert isinstance(data["status"], str)
        assert data["status"] == "paused"
        assert isinstance(data["current_time"], str)  # ISO datetime

    async def test_clock_router_resume_response_model(self, app):
        """Test POST /api/v2/sim/clock/resume response matches ResumeClockResponse model."""
        # Pause first
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            await client.post("/api/v2/sim/clock/pause")

        # Resume
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.post("/api/v2/sim/clock/resume")

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present
        required_fields = {"status", "current_time"}
        assert set(data.keys()) >= required_fields

        # Verify field types
        assert isinstance(data["status"], str)
        assert data["status"] == "running"
        assert isinstance(data["current_time"], str)  # ISO datetime

    async def test_clock_router_multiple_advances(self, app, bootstrap):
        """Test multiple clock advances in sequence."""
        # Pause auto-advance
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            await client.post("/api/v2/sim/clock/pause")

        # Advance three times
        times = []
        for i in range(3):
            async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
                response = await client.post(
                    "/api/v2/sim/clock/advance",
                    json={"seconds": 30.0},
                )
            assert response.status_code == 200
            times.append(datetime.fromisoformat(response.json()["current_time"]))

        # Verify times are strictly increasing
        for i in range(1, len(times)):
            assert times[i] > times[i - 1]

    async def test_clock_router_router_not_in_production_app(self):
        """Verify that simulation clock router is NOT mounted in production create_app."""
        from codetoreum.adapters.primary.fastapi_app import create_app
        from codetoreum.adapters.primary.input_port_adapters.mock import (
            MockWorkflowCommandAdapter,
            MockTaskQueryAdapter,
            MockConfigCommandAdapter,
            MockConfigQueryAdapter,
            MockMetricsQueryAdapter,
            MockWorkspaceQueryAdapter,
            MockWorkItemCommandAdapter,
            MockWorkItemQueryAdapter,
            MockWorkflowQueryAdapter,
            MockAgentCommandAdapter,
            MockAgentQueryAdapter,
            MockExecutionCommandAdapter,
            MockExecutionQueryAdapter,
            MockWorkflowDefinitionCommandAdapter,
            MockOrchestrationCommandAdapter,
            MockLoggerAdapter,
        )
        from codetoreum.infrastructure.event_bus import EventBus
        from codetoreum.adapters.testing import InMemoryEventStore

        # Create production app with mock ports
        event_bus = EventBus()
        event_store = InMemoryEventStore()

        app = create_app(
            workflow_command_port=MockWorkflowCommandAdapter(),
            task_query_port=MockTaskQueryAdapter(),
            config_command_port=MockConfigCommandAdapter(),
            config_query_port=MockConfigQueryAdapter(),
            metrics_query_port=MockMetricsQueryAdapter(),
            workspace_query_port=MockWorkspaceQueryAdapter(),
            work_item_command_port=MockWorkItemCommandAdapter(),
            work_item_query_port=MockWorkItemQueryAdapter(),
            workflow_query_port=MockWorkflowQueryAdapter(),
            workflow_run_query_port=MockWorkflowQueryAdapter(),
            workflow_definition_command_port=MockWorkflowDefinitionCommandAdapter(),
            orchestration_command_port=MockOrchestrationCommandAdapter(),
            agent_command_port=MockAgentCommandAdapter(),
            agent_query_port=MockAgentQueryAdapter(),
            execution_command_port=MockExecutionCommandAdapter(),
            execution_query_port=MockExecutionQueryAdapter(),
            event_store=event_store,
            event_bus=event_bus,
            config_service=None,
            logger=MockLoggerAdapter(),
            disable_auth=True,
        )

        # Check that simulation clock endpoints are NOT in the production app
        routes = [route.path for route in app.routes]
        clock_routes = [r for r in routes if "/sim/clock" in r]

        assert len(clock_routes) == 0, f"Clock routes found in production app: {clock_routes}"
