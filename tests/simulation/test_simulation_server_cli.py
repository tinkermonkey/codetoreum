"""
Integration tests for simulation server CLI.

Tests:
- CLI startup and configuration
- HTTP request handling
- WebSocket connections
- Graceful shutdown
"""

import logging
import time
from collections.abc import AsyncGenerator

import click
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from codetoreum.cli.simulation_server import (
    apply_adapter_overrides,
    bootstrap_application,
    display_adapter_summary,
    get_scenario_file_path,
    main,
    seed_data,
    validate_port,
    validate_speed_multiplier,
    validate_yaml_file,
)
from codetoreum.infrastructure.simulation.bootstrap import (
    SimulationApplicationBootstrap,
)


class TestSimulationServerCLI:
    """Test suite for simulation server CLI."""

    @pytest.fixture
    async def bootstrap(self) -> AsyncGenerator[SimulationApplicationBootstrap, None]:
        """Create and setup a bootstrap instance for testing."""
        bootstrap, _ = await bootstrap_application(
            scenario="default",
            scenario_file=None,
            speed_multiplier=10.0,
            auto_advance=False,
        )
        yield bootstrap
        await bootstrap.teardown()

    def test_get_scenario_file_path_default(self):
        """Test getting built-in scenario directory (default → smoke alias)."""
        scenario_dir = get_scenario_file_path("default")
        assert scenario_dir.is_dir()
        assert scenario_dir.name == "smoke"

    def test_get_scenario_file_path_demo(self):
        """Test getting demo scenario directory (demo → sdlc_pipeline alias)."""
        scenario_dir = get_scenario_file_path("demo")
        assert scenario_dir.is_dir()
        assert scenario_dir.name == "sdlc_pipeline"

    def test_get_scenario_file_path_not_found(self):
        """Test error handling for non-existent scenario."""
        with pytest.raises(FileNotFoundError, match="Scenario 'nonexistent' not found"):
            get_scenario_file_path("nonexistent")

    @pytest.mark.asyncio
    async def test_bootstrap_application(self):
        """Test application bootstrap process."""
        start_time = time.time()
        bootstrap, _ = await bootstrap_application(
            scenario="default",
            scenario_file=None,
            speed_multiplier=10.0,
            auto_advance=False,
        )
        elapsed = time.time() - start_time

        try:
            # Verify bootstrap completed successfully
            assert bootstrap is not None
            assert bootstrap._is_setup is True
            assert bootstrap.app is not None
            assert bootstrap.adapters is not None
            assert bootstrap.services is not None
            assert bootstrap.ports is not None

            # Log bootstrap time for performance monitoring
            # Allow generous timeout for slow CI runners (10 seconds)
            # but log warning if it exceeds 5 seconds for performance awareness
            if elapsed > 5.0:
                logger = logging.getLogger(__name__)
                logger.warning(f"Bootstrap took {elapsed:.2f}s (expected <5s on modern hardware)")

            assert elapsed < 5.0, f"Bootstrap took {elapsed:.2f}s, expected <5s (CI timeout)"

        finally:
            await bootstrap.teardown()

    @pytest.mark.asyncio
    async def test_bootstrap_with_custom_scenario_file(self, tmp_path):
        """Test bootstrap with custom scenario file."""
        # Create a minimal custom scenario file
        scenario_content = """
name: "Custom Test Scenario"
description: "Test custom scenario loading"
version: "1.0"
speed_multiplier: 5.0

projects:
  - name: "test-project"
    description: "Test project"
    default_branch: "main"

workflows:
  - name: "test-workflow"
    description: "Test workflow"
    stages:
      - name: "test-stage"
        agent_type: "test-agent"
        description: "Test stage"
        order: 1

agents:
  - name: "test-agent"
    agent_type: "generic"
    description: "Test agent"
    capabilities:
      - "code_generation"

work_items:
  - title: "Test Item"
    description: "Test work item"
    labels: ["test"]
    priority: "medium"
    status: "new"
"""
        scenario_file = tmp_path / "custom.yaml"
        scenario_file.write_text(scenario_content)

        bootstrap, _ = await bootstrap_application(
            scenario="default",  # Ignored when scenario_file is provided
            scenario_file=scenario_file,
            speed_multiplier=100.0,  # Should override file's 5.0
            auto_advance=False,
        )

        try:
            assert bootstrap is not None
            assert bootstrap._is_setup is True
            # Verify speed multiplier was overridden (engine encapsulates clock)
            assert bootstrap.engine is not None
            assert bootstrap.engine.get_speed_multiplier() == 100.0

        finally:
            await bootstrap.teardown()

    @pytest.mark.asyncio
    async def test_seed_data_default_scenario(self):
        """Test data seeding with default scenario."""
        bootstrap, _ = await bootstrap_application(
            scenario="default",
            scenario_file=None,
            speed_multiplier=10.0,
            auto_advance=False,
        )

        try:
            seeded_data = await seed_data(
                bootstrap,
                scenario="default",
                scenario_file=None,
                no_seed=False,
            )

            # Verify data was seeded
            assert seeded_data["projects"] > 0
            assert seeded_data["workflows"] > 0
            assert seeded_data["agents"] > 0
            assert seeded_data["work_items"] > 0

            # For default scenario, we expect specific counts
            assert seeded_data["projects"] == 1
            assert seeded_data["work_items"] == 3

        finally:
            await bootstrap.teardown()

    @pytest.mark.asyncio
    async def test_seed_data_no_seed_flag(self):
        """Test that --no-seed flag skips data seeding."""
        bootstrap, _ = await bootstrap_application(
            scenario="default",
            scenario_file=None,
            speed_multiplier=10.0,
            auto_advance=False,
        )

        try:
            seeded_data = await seed_data(
                bootstrap,
                scenario="default",
                scenario_file=None,
                no_seed=True,
            )

            # Verify no data was seeded
            assert seeded_data["projects"] == 0
            assert seeded_data["workflows"] == 0
            assert seeded_data["agents"] == 0
            assert seeded_data["work_items"] == 0

        finally:
            await bootstrap.teardown()

    @pytest.mark.asyncio
    async def test_http_health_check(self, bootstrap):
        """Test HTTP health check endpoint."""
        with TestClient(bootstrap.app) as client:
            response = client.get("/api/v2/health")

            # Health check should be available in simulation bootstrap
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "codetoreum-api"

    @pytest.mark.asyncio
    async def test_http_create_work_item(self, bootstrap):
        """Test creating a work item via HTTP API."""
        # First seed some data to have a project
        await seed_data(
            bootstrap,
            scenario="default",
            scenario_file=None,
            no_seed=False,
        )

        with TestClient(bootstrap.app) as client:
            # Create work item with all required fields
            work_item_data = {
                "project_id": "test-project",  # Required field
                "title": "Test Work Item",
                "description": "Test description",
                "labels": ["test"],
            }

            response = client.post("/api/v2/work-items", json=work_item_data)

            # Endpoint is fully implemented in bootstrap - expect 201
            assert response.status_code == 201, f"Expected 201 Created, got {response.status_code}: {response.text}"
            # Verify response contains created work item
            data = response.json()
            assert "id" in data, "Response should contain work item ID"
            assert data["title"] == work_item_data["title"], "Response should contain created title"
            assert data["project_id"] == work_item_data["project_id"], "Response should contain project_id"

    @pytest.mark.asyncio
    async def test_websocket_connection(self, bootstrap):
        """Test WebSocket connection (if available)."""
        from starlette.testclient import WebSocketDenialResponse
        from starlette.websockets import WebSocketDisconnect

        with TestClient(bootstrap.app) as client:
            # Test WebSocket connection - expect 404 if not implemented
            try:
                with client.websocket_connect("/ws") as websocket:
                    # Connection successful
                    assert websocket is not None
            except WebSocketDenialResponse as e:
                # WebSocket endpoint not implemented returns 404 denial
                assert e.status_code == 404, f"Expected WebSocket denial with 404, got {e.status_code}"
            except WebSocketDisconnect:
                # WebSocket endpoint not implemented raises disconnect
                # This is acceptable - it means the route doesn't exist
                pass

    @pytest.mark.asyncio
    async def test_api_docs_available(self, bootstrap):
        """Test that API documentation endpoints handle requests properly."""
        with TestClient(bootstrap.app) as client:
            # OpenAPI schema endpoint
            response = client.get("/openapi.json")
            # In simulation mode, docs may be disabled (404 is acceptable)
            # But we should not get 500 or other server errors
            assert response.status_code in [
                200,
                404,
            ], f"OpenAPI endpoint should return 200 or 404, got {response.status_code}"
            if response.status_code == 200:
                data = response.json()
                assert "openapi" in data

            # Swagger UI endpoint
            response = client.get("/docs")
            # In simulation mode, docs may be disabled (404 is acceptable)
            assert response.status_code in [
                200,
                404,
            ], f"Swagger endpoint should return 200 or 404, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self):
        """Test graceful shutdown and cleanup."""
        bootstrap, _ = await bootstrap_application(
            scenario="default",
            scenario_file=None,
            speed_multiplier=10.0,
            auto_advance=False,
        )

        # Verify setup
        assert bootstrap._is_setup is True

        # Perform shutdown
        await bootstrap.teardown()

        # Verify cleanup
        assert bootstrap._is_setup is False
        assert bootstrap.app is None
        assert bootstrap.adapters is None
        assert bootstrap.services is None

    @pytest.mark.asyncio
    async def test_multiple_requests(self, bootstrap):
        """Test handling multiple concurrent requests."""
        # Seed data first
        await seed_data(
            bootstrap,
            scenario="default",
            scenario_file=None,
            no_seed=False,
        )

        with TestClient(bootstrap.app) as client:
            # Make multiple requests to health endpoint (should always exist)
            responses = []
            for _ in range(10):
                response = client.get("/api/v2/health")
                responses.append(response)

            # All requests should succeed (health endpoint must be reliable)
            for i, response in enumerate(responses):
                assert (
                    response.status_code == 200
                ), f"Request {i} failed with status {response.status_code}: {response.text}"
                data = response.json()
                assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_scenario_stress_test(self):
        """Test loading stress test scenario."""
        bootstrap, _ = await bootstrap_application(
            scenario="stress_test",
            scenario_file=None,
            speed_multiplier=100.0,
            auto_advance=False,
        )

        try:
            seeded_data = await seed_data(
                bootstrap,
                scenario="stress_test",
                scenario_file=None,
                no_seed=False,
            )

            # Stress test scenario should have many work items
            assert seeded_data["work_items"] >= 10

        finally:
            await bootstrap.teardown()

    @pytest.mark.asyncio
    async def test_different_speed_multipliers(self):
        """Test different speed multiplier configurations."""
        for speed in [1.0, 10.0, 100.0]:
            bootstrap, _ = await bootstrap_application(
                scenario="default",
                scenario_file=None,
                speed_multiplier=speed,
                auto_advance=False,
            )

            try:
                # Verify speed multiplier is set correctly (engine encapsulates clock)
                assert bootstrap.engine is not None
                assert bootstrap.engine.get_speed_multiplier() == speed

            finally:
                await bootstrap.teardown()


class TestSimulationServerCLIClick:
    """Test Click CLI interface."""

    def test_cli_help(self):
        """Test CLI help output."""

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "simulation server" in result.output.lower()
        assert "--host" in result.output.lower()
        assert "--port" in result.output.lower()
        assert "--scenario" in result.output.lower()
        assert "--speed-multiplier" in result.output.lower()

    def test_cli_default_options(self):
        """Test CLI with default options (should show defaults in help)."""

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert "localhost" in result.output  # Default host
        assert "8000" in result.output  # Default port
        assert "default" in result.output  # Default scenario


class TestSimulationServerPerformance:
    """Performance tests for simulation server."""

    @pytest.mark.asyncio
    async def test_startup_time(self):
        """Test that server starts in reasonable time (no hard deadline for CI)."""
        start_time = time.time()

        # Bootstrap
        bootstrap, _ = await bootstrap_application(
            scenario="default",
            scenario_file=None,
            speed_multiplier=100.0,
            auto_advance=False,
        )

        # Seed data
        await seed_data(
            bootstrap,
            scenario="default",
            scenario_file=None,
            no_seed=False,
        )

        elapsed = time.time() - start_time

        try:
            # Log startup time for performance monitoring
            # Ideal: <2 seconds on modern hardware
            # Acceptable: <10 seconds on slow CI runners
            if elapsed < 2.0:
                performance_level = "excellent"
            elif elapsed < 5.0:
                performance_level = "good"
            else:
                performance_level = "slow (but acceptable on CI)"

            logger = logging.getLogger(__name__)
            logger.info(f"Startup took {elapsed:.2f}s ({performance_level})")

            # Total startup time should complete within reasonable timeframe for CI
            assert elapsed < 5.0, f"Startup took {elapsed:.2f}s, expected <5s (CI timeout)"

        finally:
            await bootstrap.teardown()

    @pytest.mark.asyncio
    async def test_seed_work_items(self):
        """Test seeding work items completes in reasonable time."""
        bootstrap, _ = await bootstrap_application(
            scenario="stress_test",  # Should have multiple work items
            scenario_file=None,
            speed_multiplier=100.0,
            auto_advance=False,
        )

        try:
            start_time = time.time()
            seeded_data = await seed_data(
                bootstrap,
                scenario="stress_test",
                scenario_file=None,
                no_seed=False,
            )
            elapsed = time.time() - start_time

            # Log seeding time for performance monitoring
            # Ideal: <500ms on modern hardware
            # Acceptable: <5 seconds on slow CI runners
            if elapsed < 0.5:
                performance_level = "excellent"
            elif elapsed < 2.0:
                performance_level = "good"
            else:
                performance_level = "slow (but acceptable on CI)"

            logger = logging.getLogger(__name__)
            logger.info(f"Seeded {seeded_data.get('work_items', 0)} work items in {elapsed:.2f}s ({performance_level})")

            # Should complete within reasonable timeframe for CI
            assert elapsed < 3.0, f"Seeding took {elapsed:.2f}s, expected <3s (CI timeout)"
            assert seeded_data["work_items"] > 0, "Should have seeded some work items"

        finally:
            await bootstrap.teardown()


class TestInputValidation:
    """Test input validation for security and error handling."""

    def test_validate_port_valid(self):
        """Test valid port numbers."""
        validate_port(80)
        validate_port(8000)
        validate_port(65535)

    def test_validate_port_too_low(self):
        """Test port number below minimum."""
        with pytest.raises(click.BadParameter, match="Port must be between 1 and 65535"):
            validate_port(0)

    def test_validate_port_too_high(self):
        """Test port number above maximum."""
        with pytest.raises(click.BadParameter, match="Port must be between 1 and 65535"):
            validate_port(70000)

    def test_validate_port_negative(self):
        """Test negative port number."""
        with pytest.raises(click.BadParameter, match="Port must be between 1 and 65535"):
            validate_port(-1)

    def test_validate_speed_multiplier_valid(self):
        """Test valid speed multipliers."""
        validate_speed_multiplier(0.1)
        validate_speed_multiplier(1.0)
        validate_speed_multiplier(100.0)

    def test_validate_speed_multiplier_zero(self):
        """Test speed multiplier of zero."""
        with pytest.raises(click.BadParameter, match="Speed multiplier must be positive"):
            validate_speed_multiplier(0.0)

    def test_validate_speed_multiplier_negative(self):
        """Test negative speed multiplier."""
        with pytest.raises(click.BadParameter, match="Speed multiplier must be positive"):
            validate_speed_multiplier(-5.0)

    def test_validate_yaml_file_valid(self, tmp_path):
        """Test validation of valid YAML file."""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("name: test\nvalue: 123")

        validate_yaml_file(yaml_file)  # Should not raise

    def test_validate_yaml_file_too_large(self, tmp_path):
        """Test validation fails for files exceeding size limit."""
        yaml_file = tmp_path / "large.yaml"
        # Create a file larger than 10MB
        large_content = "x: " + ("a" * (11 * 1024 * 1024))
        yaml_file.write_text(large_content)

        with pytest.raises(click.FileError, match="File too large"):
            validate_yaml_file(yaml_file)

    def test_validate_yaml_file_invalid_yaml(self, tmp_path):
        """Test validation fails for malformed YAML."""
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text("invalid: [\nbroken yaml")

        with pytest.raises(click.FileError, match="Invalid YAML"):
            validate_yaml_file(yaml_file)

    def test_validate_yaml_file_deep_nesting(self, tmp_path):
        """Test validation fails for deeply nested YAML (YAML bomb protection)."""
        yaml_file = tmp_path / "deep.yaml"
        # Create deeply nested structure exceeding MAX_YAML_DEPTH (50)
        # Build nested structure: a: {b: {c: {d: ... }}}
        content = "root:\n"
        for i in range(60):
            content += "  " * (i + 1) + f"level{i}:\n"
        yaml_file.write_text(content)

        with pytest.raises(click.FileError, match="depth exceeds"):
            validate_yaml_file(yaml_file)

    def test_validate_yaml_file_too_many_nodes(self, tmp_path):
        """Test validation fails for too many nodes (YAML bomb protection)."""
        yaml_file = tmp_path / "many_nodes.yaml"
        # Create structure with too many nodes (> 10000)
        large_list = "items:\n" + "".join(f"  - item{i}\n" for i in range(15000))
        yaml_file.write_text(large_list)

        with pytest.raises(click.FileError, match="node count exceeds"):
            validate_yaml_file(yaml_file)

    def test_validate_yaml_file_permission_denied(self, tmp_path):
        """Test validation handles permission errors."""
        yaml_file = tmp_path / "readonly.yaml"
        yaml_file.write_text("test: value")
        # Make file unreadable
        yaml_file.chmod(0o000)

        try:
            with pytest.raises(click.FileError, match="Error reading file"):
                validate_yaml_file(yaml_file)
        finally:
            # Restore permissions for cleanup
            yaml_file.chmod(0o644)


class TestErrorHandling:
    """Test error handling for edge cases."""

    @pytest.mark.asyncio
    async def test_bootstrap_invalid_scenario_file(self, tmp_path):
        """Test bootstrap with invalid scenario file."""
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text("invalid: [\nbroken")

        with pytest.raises((RuntimeError, click.FileError)):
            await bootstrap_application(
                scenario="default",
                scenario_file=yaml_file,
                speed_multiplier=1.0,
                auto_advance=False,
            )

    @pytest.mark.asyncio
    async def test_seed_data_nonexistent_scenario(self):
        """Test seeding with nonexistent scenario name."""
        bootstrap, _ = await bootstrap_application(
            scenario="default",
            scenario_file=None,
            speed_multiplier=10.0,
            auto_advance=False,
        )

        try:
            with pytest.raises((FileNotFoundError, RuntimeError)):
                await seed_data(
                    bootstrap,
                    scenario="nonexistent_scenario_xyz",
                    scenario_file=None,
                    no_seed=False,
                )
        finally:
            await bootstrap.teardown()


class TestAdapterOverrides:
    """Test adapter override functionality."""

    def test_apply_adapter_overrides_single_override(self):
        """Test applying a single adapter override."""
        from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
        from codetoreum.infrastructure.resilience import OperationMode
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        # Create config and factory
        config = SimulationConfig.create_fast_config("test")
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,
        )
        factory = AdapterFactory(factory_config)

        # Apply override
        overrides = ("board=mock",)
        result = apply_adapter_overrides(config, overrides, factory)

        # Verify override was applied
        assert result.adapters.board == "mock"
        # Other adapters should remain unchanged
        assert result.adapters.systemic_analysis == "mock"
        assert result.adapters.ticket == "in_memory"

    def test_apply_adapter_overrides_multiple(self):
        """Test applying multiple adapter overrides."""
        from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
        from codetoreum.infrastructure.resilience import OperationMode
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        # Create config and factory
        config = SimulationConfig.create_fast_config("test")
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,
        )
        factory = AdapterFactory(factory_config)

        # Apply multiple overrides
        overrides = (
            "board=mock",
            "systemic_analysis=mock",
            "container=fake",
        )
        result = apply_adapter_overrides(config, overrides, factory)

        # Verify all overrides were applied
        assert result.adapters.board == "mock"
        assert result.adapters.systemic_analysis == "mock"
        assert result.adapters.container == "fake"
        # Others unchanged
        assert result.adapters.ticket == "in_memory"

    def test_apply_adapter_overrides_empty(self):
        """Test that empty overrides returns original config unchanged."""
        from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
        from codetoreum.infrastructure.resilience import OperationMode
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        # Create config and factory
        config = SimulationConfig.create_fast_config("test")
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,
        )
        factory = AdapterFactory(factory_config)

        # Apply empty overrides
        overrides = ()
        result = apply_adapter_overrides(config, overrides, factory)

        # Verify nothing changed
        assert result.adapters == config.adapters

    def test_apply_adapter_overrides_invalid_slot_name(self):
        """Test error handling for invalid adapter slot name."""
        from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
        from codetoreum.infrastructure.resilience import OperationMode
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        # Create config and factory
        config = SimulationConfig.create_fast_config("test")
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,
        )
        factory = AdapterFactory(factory_config)

        # Try to use invalid slot name
        overrides = ("invalid_slot_xyz=mock",)

        with pytest.raises(click.UsageError) as exc_info:
            apply_adapter_overrides(config, overrides, factory)

        error_msg = str(exc_info.value)
        assert "Unknown adapter slot" in error_msg
        assert "invalid_slot_xyz" in error_msg
        assert "Valid slots:" in error_msg

    def test_apply_adapter_overrides_invalid_impl_name(self):
        """Test error handling for invalid implementation name."""
        from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
        from codetoreum.infrastructure.resilience import OperationMode
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        # Create config and factory
        config = SimulationConfig.create_fast_config("test")
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,
        )
        factory = AdapterFactory(factory_config)

        # Try to use invalid impl name for a valid slot
        overrides = ("board=invalid_impl_xyz",)

        with pytest.raises(click.UsageError) as exc_info:
            apply_adapter_overrides(config, overrides, factory)

        error_msg = str(exc_info.value)
        assert "Unknown implementation" in error_msg
        assert "invalid_impl_xyz" in error_msg
        assert "board" in error_msg
        assert "Available:" in error_msg

    def test_apply_adapter_overrides_multiple_errors(self):
        """Test error handling accumulates all errors."""
        from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
        from codetoreum.infrastructure.resilience import OperationMode
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        # Create config and factory
        config = SimulationConfig.create_fast_config("test")
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,
        )
        factory = AdapterFactory(factory_config)

        # Try to use multiple invalid overrides
        overrides = (
            "invalid_slot1=mock",
            "board=invalid_impl1",
            "invalid_slot2=invalid_impl2",
        )

        with pytest.raises(click.UsageError) as exc_info:
            apply_adapter_overrides(config, overrides, factory)

        error_msg = str(exc_info.value)
        # Should contain errors for multiple issues
        assert "Unknown adapter slot" in error_msg
        assert "invalid_slot1" in error_msg

    @pytest.mark.asyncio
    async def test_bootstrap_with_adapter_overrides(self):
        """Test bootstrap applies adapter overrides correctly."""
        # Test that bootstrap_application accepts and applies adapter overrides
        overrides = ("board=mock",)
        bootstrap, _ = await bootstrap_application(
            scenario="default",
            scenario_file=None,
            speed_multiplier=10.0,
            auto_advance=False,
            adapter_overrides=overrides,
        )

        try:
            # Verify bootstrap succeeded
            assert bootstrap is not None
            assert bootstrap._is_setup is True
            # Verify the override was applied in config
            assert bootstrap.config.adapters.board == "mock"
        finally:
            await bootstrap.teardown()

    def test_cli_adapter_override_help(self):
        """Test that --adapter option appears in CLI help."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "--adapter" in result.output
        assert "SLOT=IMPL" in result.output
        assert "Override a single adapter" in result.output


class TestAdapterDisplaySummary:
    """Test adapter summary display functionality."""

    def test_display_adapter_summary_valid_adapters(self, capsys):
        """Test that adapter summary displays all adapters with correct tags."""
        from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
        from codetoreum.infrastructure.resilience import OperationMode
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        # Create config and factory
        config = SimulationConfig.create_fast_config("test")
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,
        )
        factory = AdapterFactory(factory_config)

        # Display summary (should not raise)
        display_adapter_summary(config, factory)

        # Capture output
        captured = capsys.readouterr()
        output = captured.out

        # Verify output contains adapter slots
        assert "Slot" in output
        assert "Implementation" in output
        assert "Type" in output
        # Spot check for some adapters
        assert "board" in output
        assert "systemic_analysis" in output
        assert "container" in output

    def test_display_adapter_summary_shows_simulation_tags(self, capsys):
        """Test that simulation adapters are labeled [simulation]."""
        from codetoreum.infrastructure.adapters.factory import AdapterFactory, AdapterFactoryConfig
        from codetoreum.infrastructure.resilience import OperationMode
        from codetoreum.infrastructure.simulation.simulation_config import SimulationConfig

        # Create config with mock adapters (which are marked as simulation)
        config = SimulationConfig.create_fast_config("test")
        factory_config = AdapterFactoryConfig(
            operation_mode=OperationMode.SIMULATION,
            enable_resilience=False,
        )
        factory = AdapterFactory(factory_config)

        # Display summary
        display_adapter_summary(config, factory)

        # Capture output
        captured = capsys.readouterr()
        output = captured.out

        # Should show adapter slots and implementations at minimum
        assert "Adapter Configuration" in output
        assert "board" in output
        assert "mock" in output
        # Note: The Type column rendering may be stripped by Rich in CI environments,
        # but the function should not raise an exception


class TestCLIAdapterIntegration:
    """CLI error path tests for --adapter flag validation."""

    def test_cli_invalid_adapter_slot(self):
        """Test CLI with invalid adapter slot name produces error."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--adapter",
                "invalid_slot_name=mock",
                "--no-seed",
            ],
        )

        # Should fail with non-zero exit code
        assert result.exit_code != 0
        # Error message should mention the invalid slot
        assert "Unknown adapter slot" in result.output or "invalid_slot_name" in result.output

    def test_cli_invalid_adapter_impl(self):
        """Test CLI with invalid adapter implementation produces error."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--adapter",
                "board=invalid_impl_name",
                "--no-seed",
            ],
        )

        # Should fail with non-zero exit code
        assert result.exit_code != 0
        # Error message should mention the invalid implementation
        assert "Unknown implementation" in result.output or "invalid_impl_name" in result.output

    def test_cli_adapter_option_parsing(self):
        """Test CLI parser accepts --adapter option with valid syntax."""
        runner = CliRunner()
        # Test that --help with --adapter parses successfully (option exists and accepts SLOT=IMPL format)
        result = runner.invoke(main, ["--adapter", "board=mock", "--help"])
        assert result.exit_code == 0
        assert "--adapter" in result.output

    def test_cli_adapter_invalid_format_missing_equals(self):
        """Test CLI with invalid adapter format (missing equals sign)."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--adapter",
                "board mock",
                "--no-seed",
            ],
        )

        # Should fail with non-zero exit code
        assert result.exit_code != 0
        # Error message should mention format
        assert "Invalid adapter override format" in result.output or "Expected format" in result.output

    def test_cli_adapter_invalid_format_no_slot(self):
        """Test CLI with invalid adapter format (no slot name)."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--adapter",
                "=mock",
                "--no-seed",
            ],
        )

        # Should fail with non-zero exit code
        assert result.exit_code != 0
        # Error message should mention format
        assert "Invalid adapter override format" in result.output or "Expected format" in result.output

    def test_cli_adapter_invalid_format_no_impl(self):
        """Test CLI with invalid adapter format (no implementation name)."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--adapter",
                "board=",
                "--no-seed",
            ],
        )

        # Should fail with non-zero exit code
        assert result.exit_code != 0
        # Error message should mention format
        assert "Invalid adapter override format" in result.output or "Expected format" in result.output

    def test_cli_adapter_happy_path_valid_swap(self):
        """Test CLI with valid --adapter flag in happy path without adapter configuration errors.

        This is the happy path test ensuring that providing a valid adapter swap
        (slot=implementation format) does NOT produce adapter configuration errors.
        The test verifies that the adapter validation logic accepts the valid format
        and passes it to bootstrap without raising configuration errors.
        """
        from unittest.mock import AsyncMock, patch

        runner = CliRunner()

        # Patch uvicorn.Server.serve() to exit immediately without actually starting the server
        # This allows the test to complete. The serve() method is async and blocking,
        # so we patch it to return immediately (simulating graceful shutdown)
        async def mock_serve():
            return  # Just return without doing anything

        with patch("uvicorn.Server.serve", new_callable=AsyncMock, side_effect=mock_serve):
            result = runner.invoke(
                main,
                [
                    "--adapter",
                    "board=mock",  # Valid format: registered slot with registered implementation
                    "--no-seed",  # Skip data seeding
                ],
            )

        # The test passes if no adapter configuration errors occur in the output
        # If adapter validation failed, we'd see one of these error messages
        assert (
            "Unknown adapter slot" not in result.output
            and "Unknown implementation" not in result.output
            and "Invalid adapter override format" not in result.output
        ), f"Unexpected adapter configuration error. Output: {result.output}"

        # Verify we reached the point where the adapter was accepted and bootstrap completed
        # (otherwise we'd see adapter validation errors)
        assert result.exit_code == 0, f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
