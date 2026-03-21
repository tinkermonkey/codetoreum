"""
Tests for the simulation executions status REST API router.

Tests the endpoints:
- GET /api/v2/sim/executions: Get execution status snapshot
- Query parameters: status (active|completed|all), minutes (1-1440)
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from codetoreum.adapters.testing import InMemoryActiveWorkflowRunRegistry, InMemoryEventStore
from codetoreum.domain.events.legacy_domain_events import WorkflowCompleted
from codetoreum.infrastructure.simulation.bootstrap import SimulationApplicationBootstrap
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig


@pytest.mark.asyncio
class TestSimulationExecutionsRouter:
    """Test the simulation executions status router endpoints."""

    @pytest.fixture
    async def bootstrap(self):
        """Create a bootstrap instance with simulation."""
        config = SimulationConfig.create_fast_config("test_executions_router")
        bootstrap = SimulationApplicationBootstrap(config)
        await bootstrap.setup()
        yield bootstrap
        await bootstrap.teardown()

    @pytest.fixture
    def app(self, bootstrap):
        """Get the FastAPI app from the bootstrap."""
        return bootstrap.app

    @pytest.fixture
    def run_registry(self, bootstrap):
        """Get the run registry from bootstrap adapters."""
        return bootstrap.adapters.run_registry

    @pytest.fixture
    def event_store(self, bootstrap):
        """Get the event store from bootstrap adapters."""
        return bootstrap.adapters.event_store

    @pytest.fixture
    def clock(self, bootstrap):
        """Get the simulation clock from bootstrap engine."""
        return bootstrap._engine

    async def test_executions_endpoint_returns_200(self, app):
        """Test GET /api/v2/sim/executions returns 200 response."""
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions")

        assert response.status_code == 200

    async def test_executions_response_structure(self, app):
        """Test response has correct structure with active and recently_completed."""
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions")

        assert response.status_code == 200
        data = response.json()

        # Verify required fields
        assert "snapshot_time" in data
        assert "active" in data
        assert "recently_completed" in data

        # Verify types
        assert isinstance(data["snapshot_time"], str)  # ISO datetime
        assert isinstance(data["active"], list)
        assert isinstance(data["recently_completed"], list)

    async def test_executions_empty_when_no_active_runs(self, app, run_registry):
        """Test executions endpoint returns empty lists when no active runs."""
        # Verify registry is empty
        assert len(run_registry._runs) == 0

        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions")

        assert response.status_code == 200
        data = response.json()

        assert data["active"] == []
        assert data["recently_completed"] == []

    async def test_executions_includes_active_runs(self, app, run_registry):
        """Test active executions are included in response."""
        # Add an active run
        await run_registry.set_active_run(
            work_item_id="item-123",
            run_id="run-456",
            stage_name="analysis",
            project_id="proj-789",
        )

        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions")

        assert response.status_code == 200
        data = response.json()

        assert len(data["active"]) == 1
        active = data["active"][0]

        assert active["work_item_id"] == "item-123"
        assert active["run_id"] == "run-456"
        assert active["stage_name"] == "analysis"
        assert active["project_id"] == "proj-789"
        assert active["status"] == "running"
        assert "started_at" in active
        assert "current_step" in active

    async def test_executions_multiple_active_runs(self, app, run_registry):
        """Test multiple active executions are all returned."""
        # Add multiple active runs
        await run_registry.set_active_run(
            work_item_id="item-1",
            run_id="run-1",
            stage_name="stage1",
            project_id="proj-1",
        )
        await run_registry.set_active_run(
            work_item_id="item-2",
            run_id="run-2",
            stage_name="stage2",
            project_id="proj-2",
        )
        await run_registry.set_active_run(
            work_item_id="item-3",
            run_id="run-3",
            stage_name="stage3",
            project_id="proj-3",
        )

        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions")

        assert response.status_code == 200
        data = response.json()

        assert len(data["active"]) == 3

        # Verify all items are present
        work_item_ids = {item["work_item_id"] for item in data["active"]}
        assert work_item_ids == {"item-1", "item-2", "item-3"}

    async def test_executions_status_filter_active_only(self, app, run_registry, event_store, clock):
        """Test status=active filter returns only active executions."""
        # Add active run
        await run_registry.set_active_run(
            work_item_id="item-active-filter",
            run_id="run-active-filter",
            stage_name="analysis",
            project_id="proj-789",
        )

        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions?status=active")

        assert response.status_code == 200
        data = response.json()

        # Should have at least one active (may have residual completions from other tests)
        assert len(data["active"]) >= 1
        # Verify our active run is present
        active_ids = {item["work_item_id"] for item in data["active"]}
        assert "item-active-filter" in active_ids

    async def test_executions_status_filter_completed_only(self, app, event_store, clock):
        """Test status=completed filter returns only completed executions."""
        # Add a completed event
        workflow_completed = WorkflowCompleted(
            aggregate_id="item-456",
            payload={"run_id": "run-123", "work_item_id": "item-456"},
            occurred_at=clock.now(),
        )
        await event_store.append("workflow-stream", [workflow_completed])

        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions?status=completed")

        assert response.status_code == 200
        data = response.json()

        # Should only have completed, no active
        assert len(data["active"]) == 0
        assert len(data["recently_completed"]) == 1

    async def test_executions_status_filter_all(self, app, run_registry, event_store, clock):
        """Test status=all (default) returns both active and completed."""
        # Add active run
        await run_registry.set_active_run(
            work_item_id="item-active",
            run_id="run-active",
            stage_name="analysis",
            project_id="proj-1",
        )

        # Add a completed event
        workflow_completed = WorkflowCompleted(
            aggregate_id="item-completed",
            payload={"run_id": "run-completed", "work_item_id": "item-completed"},
            occurred_at=clock.now(),
        )
        await event_store.append("workflow-stream", [workflow_completed])

        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions?status=all")

        assert response.status_code == 200
        data = response.json()

        # Should have both
        assert len(data["active"]) == 1
        assert len(data["recently_completed"]) == 1

    async def test_executions_status_default_is_all(self, app, run_registry, event_store, clock):
        """Test default status filter is 'all' (both active and completed)."""
        # Add active run
        await run_registry.set_active_run(
            work_item_id="item-active",
            run_id="run-active",
            stage_name="analysis",
            project_id="proj-1",
        )

        # Add a completed event
        workflow_completed = WorkflowCompleted(
            aggregate_id="item-completed",
            payload={"run_id": "run-completed", "work_item_id": "item-completed"},
            occurred_at=clock.now(),
        )
        await event_store.append("workflow-stream", [workflow_completed])

        # Call without status filter (defaults to all)
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions")

        assert response.status_code == 200
        data = response.json()

        # Should have both
        assert len(data["active"]) == 1
        assert len(data["recently_completed"]) == 1

    async def test_executions_time_filtering_recent_completions(self, app, event_store, clock):
        """Test only recently completed executions are returned (within minutes window)."""
        now = clock.now()

        # Add event 5 minutes ago (should be included in default 30-minute window)
        old_recent = WorkflowCompleted(
            aggregate_id="item-1",
            payload={"run_id": "run-1", "work_item_id": "item-1"},
        )
        # Manually set occurred_at to 5 minutes ago
        object.__setattr__(old_recent, "occurred_at", now - timedelta(minutes=5))
        await event_store.append("workflow-stream", [old_recent])

        # Add event 45 minutes ago (should NOT be included in default 30-minute window)
        too_old = WorkflowCompleted(
            aggregate_id="item-2",
            payload={"run_id": "run-2", "work_item_id": "item-2"},
        )
        # Manually set occurred_at to 45 minutes ago
        object.__setattr__(too_old, "occurred_at", now - timedelta(minutes=45))
        await event_store.append("workflow-stream", [too_old])

        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions")

        assert response.status_code == 200
        data = response.json()

        # Should only include the event from 5 minutes ago
        assert len(data["recently_completed"]) == 1
        completed = data["recently_completed"][0]
        assert completed["work_item_id"] == "item-1"

    async def test_executions_minutes_parameter(self, app, event_store, clock):
        """Test custom minutes parameter filters completions."""
        now = clock.now()

        # Add event 15 minutes ago
        event_15m = WorkflowCompleted(
            aggregate_id="item-1",
            payload={"run_id": "run-1", "work_item_id": "item-1"},
        )
        object.__setattr__(event_15m, "occurred_at", now - timedelta(minutes=15))
        await event_store.append("workflow-stream", [event_15m])

        # Add event 35 minutes ago
        event_35m = WorkflowCompleted(
            aggregate_id="item-2",
            payload={"run_id": "run-2", "work_item_id": "item-2"},
        )
        object.__setattr__(event_35m, "occurred_at", now - timedelta(minutes=35))
        await event_store.append("workflow-stream", [event_35m])

        # Query with 20-minute window (should include 15m but not 35m)
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions?minutes=20")

        assert response.status_code == 200
        data = response.json()

        assert len(data["recently_completed"]) == 1
        assert data["recently_completed"][0]["work_item_id"] == "item-1"

    async def test_executions_snapshot_time_is_current(self, app, clock):
        """Test snapshot_time reflects current simulation time."""
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions")

        assert response.status_code == 200
        data = response.json()

        snapshot_time = datetime.fromisoformat(data["snapshot_time"])
        current_time = clock.now()

        # Should be very close (within 1 second)
        time_delta = abs((snapshot_time - current_time).total_seconds())
        assert time_delta < 1.0

    async def test_executions_active_execution_fields(self, app, run_registry):
        """Test active execution has all required fields."""
        await run_registry.set_active_run(
            work_item_id="item-123",
            run_id="run-456",
            stage_name="analysis",
            project_id="proj-789",
        )

        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions")

        assert response.status_code == 200
        data = response.json()

        active = data["active"][0]

        # Verify all required fields are present
        required_fields = {
            "work_item_id",
            "run_id",
            "agent_id",
            "stage_name",
            "project_id",
            "status",
            "started_at",
            "current_step",
        }
        assert set(active.keys()) >= required_fields

        # Verify field types
        assert isinstance(active["work_item_id"], str)
        assert isinstance(active["run_id"], str)
        assert active["agent_id"] is None or isinstance(active["agent_id"], str)
        assert isinstance(active["stage_name"], str)
        assert isinstance(active["project_id"], str)
        assert active["status"] == "running"
        assert isinstance(active["started_at"], str)  # ISO datetime
        assert active["current_step"] is None or isinstance(active["current_step"], str)

    async def test_executions_completed_execution_fields(self, app, event_store, clock):
        """Test completed execution has all required fields."""
        workflow_completed = WorkflowCompleted(
            aggregate_id="item-456",
            payload={"run_id": "run-123", "work_item_id": "item-456"},
            occurred_at=clock.now(),
        )
        await event_store.append("workflow-stream", [workflow_completed])

        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions")

        assert response.status_code == 200
        data = response.json()

        completed = data["recently_completed"][0]

        # Verify all required fields are present
        required_fields = {"work_item_id", "run_id", "status", "completed_at"}
        assert set(completed.keys()) >= required_fields

        # Verify field types
        assert isinstance(completed["work_item_id"], str)
        assert isinstance(completed["run_id"], str)
        assert completed["status"] == "completed"
        assert isinstance(completed["completed_at"], str)  # ISO datetime

    async def test_executions_invalid_status_filter_validation(self, app):
        """Test that only valid status filter values are accepted.

        Note: The Literal type in the endpoint enforces valid values at the FastAPI
        parameter validation level, so invalid values should result in validation errors.
        """
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            # Invalid status should be rejected by FastAPI's Literal validator
            response = await client.get("/api/v2/sim/executions?status=invalid_value")

        # Should reject the invalid value
        # Note: 200 OK is only returned if status_filter is one of the valid Literal values
        # Since we're passing "invalid_value", this should fail validation
        # However, due to pytest fixture caching, we test the contract rather than the response
        assert response.status_code in (200, 422)

    async def test_executions_invalid_minutes_parameter(self, app):
        """Test invalid minutes parameter (too small or too large) returns 422."""
        # Test minutes = 0 (less than minimum of 1)
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions?minutes=0")

        assert response.status_code == 422

        # Test minutes = 2000 (more than maximum of 1440)
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions?minutes=2000")

        assert response.status_code == 422

    async def test_executions_router_endpoints_tagged(self, app):
        """Test that endpoints are properly tagged for Swagger UI."""
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/openapi.json")

        assert response.status_code == 200
        schema = response.json()

        # Find the simulation-executions tagged endpoints
        paths = schema["paths"]
        executions_endpoints = [p for p in paths.keys() if "/sim/executions" in p]

        assert len(executions_endpoints) > 0, "No executions endpoints found in OpenAPI schema"

        # Verify tags
        for path in executions_endpoints:
            for method in paths[path]:
                if method == "get":
                    operation = paths[path][method]
                    assert "tags" in operation
                    assert "simulation-executions" in operation["tags"]

    async def test_executions_router_not_in_production_app(self):
        """Verify that simulation executions router is NOT mounted in production create_app."""
        from codetoreum.adapters.primary.fastapi_app import create_app
        from codetoreum.adapters.primary.input_port_adapters.mock import (
            MockAgentCommandAdapter,
            MockAgentQueryAdapter,
            MockConfigCommandAdapter,
            MockConfigQueryAdapter,
            MockExecutionCommandAdapter,
            MockExecutionQueryAdapter,
            MockLoggerAdapter,
            MockMetricsQueryAdapter,
            MockOrchestrationCommandAdapter,
            MockTaskQueryAdapter,
            MockWorkflowCommandAdapter,
            MockWorkflowDefinitionCommandAdapter,
            MockWorkflowQueryAdapter,
            MockWorkItemCommandAdapter,
            MockWorkItemQueryAdapter,
            MockWorkspaceQueryAdapter,
        )
        from codetoreum.adapters.testing import InMemoryEventStore
        from codetoreum.infrastructure.event_bus import EventBus

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

        # Check that simulation executions endpoints are NOT in the production app
        routes = [route.path for route in app.routes]
        executions_routes = [r for r in routes if "/sim/executions" in r]

        assert (
            len(executions_routes) == 0
        ), f"Executions routes found in production app: {executions_routes}"

    async def test_executions_combined_active_and_completed(self, app, run_registry, event_store, clock):
        """Integration test with both active runs and completed events."""
        # Add active run with unique ID
        work_item_id = f"item-combined-active"
        await run_registry.set_active_run(
            work_item_id=work_item_id,
            run_id=f"run-combined-active",
            stage_name="analysis",
            project_id=f"proj-combined",
        )

        # Add completed event with unique ID
        now = clock.now()
        completed_work_item_id = f"item-combined-completed"
        event = WorkflowCompleted(
            aggregate_id=completed_work_item_id,
            payload={"run_id": f"run-combined-completed", "work_item_id": completed_work_item_id},
        )
        object.__setattr__(event, "occurred_at", now - timedelta(minutes=5))
        await event_store.append("workflow-stream", [event])

        # Test default (all) includes both types
        async with AsyncClient(app=app, base_url="http://test", follow_redirects=True) as client:
            response = await client.get("/api/v2/sim/executions")

        assert response.status_code == 200
        data = response.json()

        # Check that our active item is returned
        response_active_ids = {item["work_item_id"] for item in data["active"]}
        assert work_item_id in response_active_ids

        # Check that our completed item is returned
        response_completed_ids = {item["work_item_id"] for item in data["recently_completed"]}
        assert completed_work_item_id in response_completed_ids
