"""
Tests for SimulationApplicationBootstrap.

Validates that the bootstrap correctly wires up the entire application stack.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationAdapters,
    SimulationApplicationBootstrap,
    SimulationInfrastructure,
    SimulationPorts,
    SimulationServices,
)
from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig
from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine


@pytest.mark.asyncio
class TestSimulationApplicationBootstrap:
    """Tests for bootstrap functionality."""

    async def test_bootstrap_setup_creates_all_components(self) -> None:
        """Test that setup creates all components in correct order."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        # Setup
        app = await bootstrap.setup()

        # Verify all components created
        assert bootstrap.adapters is not None
        assert isinstance(bootstrap.adapters, SimulationAdapters)

        assert bootstrap.infrastructure is not None
        assert isinstance(bootstrap.infrastructure, SimulationInfrastructure)

        assert bootstrap.services is not None
        assert isinstance(bootstrap.services, SimulationServices)

        assert bootstrap.ports is not None
        assert isinstance(bootstrap.ports, SimulationPorts)

        assert bootstrap.app is not None
        assert isinstance(bootstrap.app, FastAPI)
        assert app is bootstrap.app

        # Cleanup
        await bootstrap.teardown()

    async def test_bootstrap_creates_all_adapters(self) -> None:
        """Test that all 9 adapters are created."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        adapters = bootstrap.adapters
        assert adapters is not None

        # Verify all 9 adapters exist
        assert adapters.ticket_system is not None
        assert adapters.llm_provider is not None
        assert adapters.container is not None
        assert adapters.repository is not None
        assert adapters.event_store is not None
        assert adapters.metrics is not None
        assert adapters.storage is not None
        assert adapters.config_store is not None
        assert adapters.notifier is not None

        await bootstrap.teardown()

    async def test_bootstrap_creates_all_services(self) -> None:
        """Test that all 8 application services are created or stubbed."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        services = bootstrap.services
        assert services is not None

        # Verify services exist (some may be None stubs in simulation mode)
        # NOTE: In simulation mode, workflow_orchestrator and agent_scheduler
        # are stubbed (None) because they have complex dependencies and
        # their functionality is provided by mock port adapters instead
        assert services.execution_service is not None
        assert services.pipeline_manager is not None
        assert services.review_service is not None
        assert services.feedback_processor is not None
        assert services.workspace_router is not None
        assert services.configuration_service is not None
        assert services.work_item_service is not None

        await bootstrap.teardown()

    async def test_bootstrap_creates_all_ports(self) -> None:
        """Test that all port implementations are created."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        ports = bootstrap.ports
        assert ports is not None

        # Verify command ports
        assert ports.workflow_command is not None
        assert ports.work_item_command is not None
        assert ports.workflow_definition_command is not None
        assert ports.orchestration_command is not None
        assert ports.agent_command is not None
        assert ports.execution_command is not None
        assert ports.config_command is not None

        # Verify query ports
        assert ports.task_query is not None
        assert ports.work_item_query is not None
        assert ports.workflow_query is not None
        assert ports.agent_query is not None
        assert ports.execution_query is not None
        assert ports.config_query is not None
        assert ports.metrics_query is not None
        assert ports.workspace_query is not None

        await bootstrap.teardown()

    async def test_bootstrap_creates_fastapi_app(self) -> None:
        """Test that FastAPI app is created with all routers."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        app = bootstrap.app
        assert app is not None
        assert isinstance(app, FastAPI)

        # Verify app has routes
        assert len(app.routes) > 0

        await bootstrap.teardown()

    async def test_bootstrap_fastapi_health_check(self) -> None:
        """Test that FastAPI app responds to health check."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        try:
            # Create test client with context manager
            with TestClient(bootstrap.app) as client:
                # Test health endpoint
                response = client.get("/api/v2/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"
                assert data["service"] == "codetoreum-api"
        finally:
            await bootstrap.teardown()

    async def test_bootstrap_teardown_cleans_up(self) -> None:
        """Test that teardown properly cleans up resources."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()
        assert bootstrap._is_setup is True

        await bootstrap.teardown()

        # Verify cleanup
        assert bootstrap._is_setup is False
        assert bootstrap.app is None
        assert bootstrap.ports is None
        assert bootstrap.services is None
        assert bootstrap.infrastructure is None
        assert bootstrap.adapters is None

    async def test_bootstrap_setup_twice_raises_error(self) -> None:
        """Test that calling setup twice raises an error."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        with pytest.raises(RuntimeError, match="already set up"):
            await bootstrap.setup()

        await bootstrap.teardown()

    async def test_bootstrap_teardown_without_setup(self) -> None:
        """Test that teardown without setup does nothing."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        # Should not raise
        await bootstrap.teardown()

    async def test_multiple_bootstrap_instances(self) -> None:
        """Test that multiple bootstrap instances can coexist."""
        config1 = SimulationConfig.create_fast_config("test1")
        config2 = SimulationConfig.create_fast_config("test2")

        bootstrap1 = SimulationApplicationBootstrap(config1)
        bootstrap2 = SimulationApplicationBootstrap(config2)

        await bootstrap1.setup()
        await bootstrap2.setup()

        # Both should be independent
        assert bootstrap1.app is not bootstrap2.app
        assert bootstrap1.adapters is not bootstrap2.adapters

        await bootstrap1.teardown()
        await bootstrap2.teardown()

    async def test_bootstrap_performance(self) -> None:
        """Test that bootstrap completes in less than 1 second."""
        import time

        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        start_time = time.time()
        await bootstrap.setup()
        elapsed = time.time() - start_time

        # Should complete in under 1 second (acceptance criterion)
        assert elapsed < 1.0, f"Bootstrap took {elapsed:.2f}s, expected <1s"

        await bootstrap.teardown()

    async def test_bootstrap_uses_simulation_config(self) -> None:
        """Test that bootstrap respects simulation config settings."""
        config = SimulationConfig.create_fast_config(
            scenario_name="custom_test",
            speed_multiplier=50.0,
        )
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()

        # Verify clock uses correct multiplier (engine encapsulates clock)
        engine = bootstrap.engine
        assert engine is not None
        assert engine.get_speed_multiplier() == 50.0

        await bootstrap.teardown()


@pytest.mark.asyncio
class TestBootstrapWithFixtures:
    """Tests using pytest fixtures."""

    async def test_simulation_app_fixture(self, simulation_app: FastAPI) -> None:
        """Test that simulation_app fixture provides working app."""
        assert simulation_app is not None
        assert isinstance(simulation_app, FastAPI)

        # Test with client
        with TestClient(simulation_app) as client:
            response = client.get("/api/v2/health")
            assert response.status_code == 200

    async def test_simulation_adapters_fixture(self, simulation_adapters: SimulationAdapters) -> None:
        """Test that simulation_adapters fixture provides adapters."""
        assert simulation_adapters is not None
        assert simulation_adapters.event_store is not None
        assert simulation_adapters.llm_provider is not None

    async def test_simulation_services_fixture(self, simulation_services: SimulationServices) -> None:
        """Test that simulation_services fixture provides services."""
        assert simulation_services is not None
        assert simulation_services.execution_service is not None
        # Note: workflow_orchestrator may be stubbed (None) in simulation mode

    async def test_simulation_ports_fixture(self, simulation_ports: SimulationPorts) -> None:
        """Test that simulation_ports fixture provides ports."""
        assert simulation_ports is not None
        assert simulation_ports.work_item_command is not None
        assert simulation_ports.work_item_query is not None

    async def test_simulation_infrastructure_fixture(
        self, simulation_infrastructure: SimulationInfrastructure
    ) -> None:
        """Test that simulation_infrastructure fixture provides infrastructure."""
        assert simulation_infrastructure is not None
        assert simulation_infrastructure.event_bus is not None
        # Clock is now managed by SimulationEngine, not exposed through infrastructure


@pytest.mark.asyncio
class TestBootstrapErrorHandling:
    """Tests for bootstrap error handling and failure scenarios."""

    async def test_double_teardown_is_safe(self) -> None:
        """Test that calling teardown multiple times is safe."""
        config = SimulationConfig.create_fast_config("test")
        bootstrap = SimulationApplicationBootstrap(config)

        await bootstrap.setup()
        await bootstrap.teardown()

        # Second teardown should be a no-op, not raise
        await bootstrap.teardown()
        assert bootstrap._is_setup is False
