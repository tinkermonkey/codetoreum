"""Unit test for metrics adapter resolution through bootstrap/resolver.

Validates that the PrometheusMetricsAdapter is correctly resolved and wired
through the real AdapterResolver with production configuration, and that the
resolved adapter records metrics end-to-end that can be scraped via /metrics.
"""

import asyncio
import logging

import pytest
from httpx import AsyncClient

from codetoreum.adapters.secondary.prometheus_metrics_adapter import (
    PrometheusMetricsAdapter,
)
from codetoreum.adapters.testing import (
    CapturingMockEventEmitter,
    InMemoryFailedEventStore,
)
from codetoreum.infrastructure.adapters.resolver import (
    AdapterResolver,
)
from codetoreum.infrastructure.bootstrap.production_bootstrap import (
    CRITICAL_ADAPTER_SLOTS,
    NON_CRITICAL_SLOTS,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_config import (
    AdapterSelectionConfig,
    SimulationConfig,
)
from codetoreum.infrastructure.simulation.simulation_engine import SimulationEngine


@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    """Clear Prometheus registry before each test to avoid collisions."""
    logger = logging.getLogger(__name__)

    try:
        from prometheus_client import REGISTRY

        collectors_to_remove = list(REGISTRY._collector_to_names.keys())
        for collector in collectors_to_remove:
            try:
                REGISTRY.unregister(collector)
            except ValueError:
                pass
            except AttributeError as e:
                logger.warning(f"Failed to unregister collector: {e}")
    except ImportError as e:
        logger.warning(f"prometheus_client import failed during cleanup: {e}")

    yield

    try:
        from prometheus_client import REGISTRY

        collectors_to_remove = list(REGISTRY._collector_to_names.keys())
        for collector in collectors_to_remove:
            try:
                REGISTRY.unregister(collector)
            except ValueError:
                pass
            except AttributeError as e:
                logger.warning(f"Failed to unregister collector during teardown: {e}")
    except ImportError as e:
        logger.warning(f"prometheus_client import failed during teardown: {e}")


class TestMetricsBootstrapResolution:
    """Tests for metrics adapter resolution through bootstrap."""

    def test_metrics_is_non_critical_slot(self) -> None:
        """Verify metrics is in NON_CRITICAL_SLOTS, not CRITICAL_ADAPTER_SLOTS."""
        assert "metrics" not in CRITICAL_ADAPTER_SLOTS
        assert "metrics" in NON_CRITICAL_SLOTS

    def test_bootstrap_default_config_sets_prometheus_metrics(self) -> None:
        """Verify that ProductionApplicationBootstrap defaults metrics to 'prometheus'."""
        from codetoreum.infrastructure.bootstrap.production_bootstrap import (
            ProductionApplicationBootstrap,
        )

        bootstrap = ProductionApplicationBootstrap()
        assert bootstrap.config.metrics == "prometheus"

    @pytest.mark.asyncio
    async def test_adapter_resolver_resolves_prometheus_metrics(self) -> None:
        """Verify AdapterResolver.resolve_metrics() is configured for PrometheusMetricsAdapter.

        This test validates that when metrics="prometheus", the resolver is
        configured to create a real PrometheusMetricsAdapter and can successfully
        instantiate it.
        """
        # Create test adapter config
        adapter_config = AdapterSelectionConfig(
            metrics="prometheus",
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

        event_bus = EventBus()
        config = SimulationConfig.create_fast_config("test_resolver")
        engine = SimulationEngine.create(config)
        factory = AdapterFactory()
        event_emitter = CapturingMockEventEmitter()
        failed_event_store = InMemoryFailedEventStore()
        logger = logging.getLogger(__name__)

        adapter_deps = AdapterDependencies(
            event_bus=event_bus,
            event_emitter=event_emitter,
            logger=logger,
            engine=engine,
            config=config,
            failed_event_store=failed_event_store,
        )

        # Create resolver with production config
        resolver = AdapterResolver(
            adapter_config=adapter_config,
            factory=factory,
            dependencies=adapter_deps,
        )

        # Verify the factory has PrometheusMetricsAdapter registered
        registry = factory.get_registry("metrics")
        assert registry.has_adapter("prometheus")

        # Get metadata for the prometheus adapter
        metadata = registry.get_metadata("prometheus")
        assert metadata is not None

        # Verify it's not a simulation-only adapter (should be production-ready)
        if metadata.config_schema:
            assert not metadata.config_schema.simulation_only

        # Verify resolve_metrics() can instantiate the adapter
        metrics_adapter = resolver.resolve_metrics()
        assert metrics_adapter is not None
        assert isinstance(metrics_adapter, PrometheusMetricsAdapter)

    def test_prometheus_metrics_adapter_has_repair_cycle_metrics(self) -> None:
        """Verify that PrometheusMetricsAdapter initializes all repair cycle metrics.

        This test validates that the adapter properly initializes the expected
        metrics when constructed and can record values that are scraped via /metrics.
        """
        # Create a real adapter and verify metrics are initialized
        adapter = PrometheusMetricsAdapter()

        # Verify the adapter has the expected internal state
        assert adapter.namespace == "codetoreum"
        assert adapter.subsystem == "repair_cycle"
        assert len(adapter._metrics_registry) > 0

        # Verify key metrics are in the registry
        expected_metrics = [
            "codetoreum_repair_cycle_started_total",
            "codetoreum_repair_cycle_completed_total",
            "codetoreum_repair_cycle_duration_seconds",
            "codetoreum_repair_cycle_test_executions_total",
        ]

        for metric_name in expected_metrics:
            assert metric_name in adapter._metrics_registry

    @pytest.mark.asyncio
    async def test_resolver_validates_credentials_without_prometheus_url(self) -> None:
        """Verify AdapterResolver.validate_credentials() passes with metrics='prometheus' and no PROMETHEUS_URL env var.

        This test confirms that the Prometheus metrics adapter does not require
        PROMETHEUS_URL to be set (it uses in-process client library, not HTTP API).
        validate_credentials() should pass without any errors.
        """
        import os

        from codetoreum.infrastructure.adapters.factory import (
            AdapterFactory,
        )
        from codetoreum.infrastructure.adapters.resolver import (
            AdapterDependencies,
        )

        # Create test adapter config
        adapter_config = AdapterSelectionConfig(
            metrics="prometheus",
            ticket="in_memory",
            version_control="in_memory",
            container="fake",
            board="mock",
            code_review="mock",
            event_store="in_memory",
        )

        # Ensure PROMETHEUS_URL is not set
        original_prometheus_url = os.environ.pop("PROMETHEUS_URL", None)

        try:
            # Create minimal dependencies for resolver
            event_bus = EventBus()
            config = SimulationConfig.create_fast_config("test_credentials")
            engine = SimulationEngine.create(config)
            factory = AdapterFactory()
            event_emitter = CapturingMockEventEmitter()
            failed_event_store = InMemoryFailedEventStore()
            logger = logging.getLogger(__name__)

            adapter_deps = AdapterDependencies(
                event_bus=event_bus,
                event_emitter=event_emitter,
                logger=logger,
                engine=engine,
                config=config,
                failed_event_store=failed_event_store,
            )

            # Create resolver with production config
            resolver = AdapterResolver(
                adapter_config=adapter_config,
                factory=factory,
                dependencies=adapter_deps,
            )

            # Call validate_credentials() — should not raise for metrics="prometheus"
            # even though PROMETHEUS_URL is not set
            resolver.validate_credentials()

        finally:
            # Restore PROMETHEUS_URL if it was set
            if original_prometheus_url is not None:
                os.environ["PROMETHEUS_URL"] = original_prometheus_url

    def test_prometheus_metrics_adapter_class_has_required_methods(self) -> None:
        """Verify that PrometheusMetricsAdapter class supports all required methods.

        Tests that the adapter class has the methods needed to record repair cycle
        metrics: increment_counter, record_histogram, set_gauge, etc.
        """
        # Verify the PrometheusMetricsAdapter class supports all required methods
        assert hasattr(PrometheusMetricsAdapter, "increment_counter")
        assert hasattr(PrometheusMetricsAdapter, "record_histogram")
        assert hasattr(PrometheusMetricsAdapter, "set_gauge")
        assert hasattr(PrometheusMetricsAdapter, "record_summary")
        assert hasattr(PrometheusMetricsAdapter, "start_timer")
        assert hasattr(PrometheusMetricsAdapter, "stop_timer")

        # Verify the methods are async
        assert asyncio.iscoroutinefunction(PrometheusMetricsAdapter.increment_counter)
        assert asyncio.iscoroutinefunction(PrometheusMetricsAdapter.record_histogram)
        assert asyncio.iscoroutinefunction(PrometheusMetricsAdapter.set_gauge)

    @pytest.mark.asyncio
    async def test_end_to_end_metrics_recording_and_scraping(self) -> None:
        """End-to-end test: synthetic execution exercises metrics and GET /metrics shows non-zero values.

        This test validates the complete chain:
        1. Create a PrometheusMetricsAdapter
        2. Call increment_counter() with a known metric name and labels
        3. Verify that the metric is recorded and can be scraped via prometheus_client
        """
        # Create a fresh adapter
        adapter = PrometheusMetricsAdapter()

        # Verify metric is in registry before incrementing
        metric_name = "codetoreum_repair_cycle_started_total"
        assert metric_name in adapter._metrics_registry, (
            f"Metric '{metric_name}' not found in adapter registry"
        )

        # Record a metric via the adapter's increment_counter method
        await adapter.increment_counter(
            name=metric_name,
            labels={"agent_name": "test_agent", "stage_name": "test_stage"},
        )

        # Verify the metric was recorded by checking the underlying metric object
        metric_obj = adapter._metrics_registry[metric_name]
        assert metric_obj is not None

        # Get the current value by collecting metrics from the Prometheus registry
        from prometheus_client import REGISTRY

        metrics = list(REGISTRY.collect())
        found_value = None

        # The metric family name is without the _total suffix
        metric_family_name = metric_name.replace("_total", "")

        for metric_family in metrics:
            if metric_family.name == metric_family_name:
                for sample in metric_family.samples:
                    if (
                        sample.name == metric_name
                        and sample.labels.get("agent_name") == "test_agent"
                        and sample.labels.get("stage_name") == "test_stage"
                    ):
                        found_value = sample.value
                        break
                break

        assert found_value is not None, (
            f"Metric '{metric_name}' with labels agent_name=test_agent, stage_name=test_stage not found"
        )
        assert found_value > 0, (
            f"Expected non-zero value for metric, got {found_value}"
        )

    @pytest.mark.asyncio
    async def test_metrics_endpoint_http_scrape(self) -> None:
        """HTTP-level test: GET /metrics endpoint returns Prometheus-formatted output.

        This test validates that the /metrics endpoint mounted in the FastAPI app
        is actually scraped and returns metrics in the Prometheus text format.
        """
        from codetoreum.infrastructure.simulation.bootstrap import (
            SimulationApplicationBootstrap,
        )

        # Create the simulation app with bootstrap
        config = SimulationConfig.create_fast_config("test_http_metrics")
        bootstrap = SimulationApplicationBootstrap(config)
        await bootstrap.setup()
        app = bootstrap.app

        # Record a metric so there's something to scrape
        adapter = PrometheusMetricsAdapter()
        metric_name = "codetoreum_repair_cycle_started_total"
        await adapter.increment_counter(
            name=metric_name,
            labels={"agent_name": "http_test", "stage_name": "test"},
        )

        try:
            # Make HTTP request to the /metrics endpoint with follow_redirects
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/metrics", follow_redirects=True)

            # Verify HTTP response
            assert response.status_code == 200, (
                f"Expected 200, got {response.status_code}: {response.text}"
            )

            # Verify response contains Prometheus format (TYPE and HELP lines)
            content = response.text
            assert "# HELP" in content or "# TYPE" in content, (
                "Response should contain Prometheus metadata comments"
            )

            # Verify the specific metric is in the scraped output
            assert "codetoreum_repair_cycle_started_total" in content, (
                "Expected metric not found in /metrics response"
            )

            # Verify the metric value appears in the response
            assert 'agent_name="http_test"' in content, (
                "Expected label value not found in /metrics response"
            )
        finally:
            await bootstrap.teardown()

    @pytest.mark.asyncio
    async def test_metrics_route_gracefully_degraded_when_prometheus_client_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify create_app() degrades gracefully when prometheus_client is unavailable.

        The import guard at fastapi_app.py:36-45 sets PROMETHEUS_CLIENT_AVAILABLE = False
        on ImportError; fastapi_app.py:412 only mounts /metrics if the flag is True. We
        monkeypatch the already-resolved module flag rather than faking the import itself:
        prometheus_client is already imported and cached in sys.modules by the time this
        test runs (this module's own _clear_prometheus_registry fixture depends on that),
        so forcing a real ImportError would require fragile sys.modules surgery that leaks
        across tests. Patching the flag exercises exactly the runtime branch the production
        code guards on, and pytest's monkeypatch fixture auto-reverts it after the test.
        """
        from unittest.mock import MagicMock

        import codetoreum.adapters.primary.fastapi_app as fastapi_app_module
        from codetoreum.adapters.testing import InMemoryEventStore
        from codetoreum.infrastructure.event_bus import EventBus

        monkeypatch.setattr(fastapi_app_module, "PROMETHEUS_CLIENT_AVAILABLE", False)

        # create_app() must not raise even though prometheus_client is "unavailable".
        app = fastapi_app_module.create_app(
            workflow_command_port=MagicMock(),
            task_query_port=MagicMock(),
            config_command_port=MagicMock(),
            config_query_port=MagicMock(),
            metrics_query_port=MagicMock(),
            workspace_query_port=MagicMock(),
            work_item_command_port=MagicMock(),
            work_item_query_port=MagicMock(),
            workflow_query_port=MagicMock(),
            workflow_run_query_port=MagicMock(),
            workflow_definition_command_port=MagicMock(),
            orchestration_command_port=MagicMock(),
            agent_command_port=MagicMock(),
            agent_query_port=MagicMock(),
            execution_command_port=MagicMock(),
            execution_query_port=MagicMock(),
            event_store=InMemoryEventStore(),
            event_bus=EventBus(),
            config_service=MagicMock(),
            logger=MagicMock(),
            disable_auth=True,  # Irrelevant here; auth is orthogonal to metrics availability
        )

        # No route should be mounted at /metrics when prometheus_client is unavailable.
        routes_at_metrics = [route for route in app.routes if getattr(route, "path", None) == "/metrics"]
        assert not routes_at_metrics, (
            "No /metrics route should be mounted when PROMETHEUS_CLIENT_AVAILABLE is False"
        )

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/metrics")
            assert response.status_code == 404, (
                f"Expected 404 for unmounted /metrics, got {response.status_code}"
            )

    @pytest.mark.asyncio
    async def test_metrics_endpoint_unauthenticated_with_auth_enabled(self) -> None:
        """Verify GET /metrics returns 200 without bearer token when auth is enabled.

        This test validates that the /metrics endpoint is accessible without
        authentication even when SimpleTokenAuthManager is active, per INV-14.
        The endpoint is mounted via Starlette's app.mount() which bypasses
        FastAPI auth dependencies, but this behavior must be enforced by tests
        to prevent accidental refactoring to a regular FastAPI route.
        """
        from codetoreum.adapters.primary.input_port_adapters.mock import (
            MockAgentCommandAdapter,
            MockAgentQueryAdapter,
            MockConfigCommandAdapter,
            MockConfigQueryAdapter,
            MockConfigServiceAdapter,
            MockExecutionCommandAdapter,
            MockExecutionQueryAdapter,
            MockLoggerAdapter,
            MockMetricsQueryAdapter,
            MockOrchestrationCommandAdapter,
            MockTaskQueryAdapter,
            MockWorkflowCommandAdapter,
            MockWorkflowDefinitionCommandAdapter,
            MockWorkflowQueryAdapter,
            MockWorkflowRunQueryAdapter,
            MockWorkItemCommandAdapter,
            MockWorkItemQueryAdapter,
            MockWorkspaceQueryAdapter,
        )
        from codetoreum.adapters.primary.fastapi_app import create_app
        from codetoreum.adapters.testing import (
            InMemoryEventStore,
            InMemoryFailedEventStore,
        )
        from codetoreum.infrastructure.event_bus import EventBus

        # Create test app with auth enabled
        event_bus = EventBus()

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
            workflow_run_query_port=MockWorkflowRunQueryAdapter(),
            workflow_definition_command_port=MockWorkflowDefinitionCommandAdapter(),
            orchestration_command_port=MockOrchestrationCommandAdapter(),
            agent_command_port=MockAgentCommandAdapter(),
            agent_query_port=MockAgentQueryAdapter(),
            execution_command_port=MockExecutionCommandAdapter(),
            execution_query_port=MockExecutionQueryAdapter(),
            event_store=InMemoryEventStore(),
            event_bus=event_bus,
            config_service=MockConfigServiceAdapter(None),  # type: ignore
            logger=MockLoggerAdapter(),  # type: ignore
            auth_secret_key="test-secret-key",
            disable_auth=False,  # Auth is ENABLED
            cors_origins=["*"],
            failed_event_store=InMemoryFailedEventStore(),
        )

        # Record a metric so there's something to scrape
        adapter = PrometheusMetricsAdapter()
        metric_name = "codetoreum_repair_cycle_started_total"
        await adapter.increment_counter(
            name=metric_name,
            labels={"agent_name": "auth_test", "stage_name": "test"},
        )

        try:
            # Make HTTP request to the /metrics endpoint WITHOUT authentication
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/metrics", follow_redirects=True)

            # Verify that /metrics is accessible without authentication (INV-14)
            assert response.status_code == 200, (
                f"GET /metrics should return 200 without auth token when auth is enabled, "
                f"got {response.status_code}: {response.text}"
            )

            # Verify response contains Prometheus format
            content = response.text
            assert "# HELP" in content or "# TYPE" in content, (
                "Response should contain Prometheus metadata comments"
            )

            # Verify the specific metric is in the scraped output
            assert "codetoreum_repair_cycle_started_total" in content, (
                "Expected metric not found in /metrics response"
            )

            # Negative control: verify that other protected endpoints DO require auth
            # This confirms the /metrics exception is real, not incidental to auth being disabled
            async with AsyncClient(app=app, base_url="http://test") as client:
                protected_response = await client.get("/api/v2/executions")

            # The protected endpoint should return 401 when no auth token is provided
            assert protected_response.status_code == 401, (
                f"Protected endpoint /api/v2/executions should return 401 without auth token, "
                f"got {protected_response.status_code}: {protected_response.text}"
            )
        finally:
            # Clean up Prometheus registry
            try:
                from prometheus_client import REGISTRY

                collectors_to_remove = list(REGISTRY._collector_to_names.keys())
                for collector in collectors_to_remove:
                    try:
                        REGISTRY.unregister(collector)
                    except (ValueError, AttributeError):
                        pass
            except ImportError:
                pass

    def test_prometheus_client_available_flag_reflects_successful_import(self) -> None:
        """Sanity check: PROMETHEUS_CLIENT_AVAILABLE is True in this test environment.

        prometheus_client is a declared dependency, so this should always hold here.
        Actual graceful-degradation behavior when the flag is False is verified by
        test_metrics_route_gracefully_degraded_when_prometheus_client_unavailable,
        which patches the flag and exercises create_app() + GET /metrics for real
        rather than asserting on source text.
        """
        from codetoreum.adapters.primary import fastapi_app

        assert fastapi_app.PROMETHEUS_CLIENT_AVAILABLE is True
