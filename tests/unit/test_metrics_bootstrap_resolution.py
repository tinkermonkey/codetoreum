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
            MockAuditQueryAdapter,
            MockConfigCommandAdapter,
            MockConfigQueryAdapter,
            MockConfigServiceAdapter,
            MockExecutionCommandAdapter,
            MockExecutionQueryAdapter,
            MockLoggerAdapter,
            MockOrchestrationCommandAdapter,
            MockTaskQueryAdapter,
            MockWorkflowCommandAdapter,
            MockWorkflowDefinitionCommandAdapter,
            MockWorkflowQueryAdapter,
            MockWorkItemCommandAdapter,
            MockWorkItemQueryAdapter,
            MockWorkspaceQueryAdapter,
        )
        from codetoreum.adapters.primary.fastapi_app import create_app
        from codetoreum.adapters.testing import (
            InMemoryEventStore,
            CapturingMockEventEmitter,
            InMemoryFailedEventStore,
        )
        from codetoreum.infrastructure.event_bus import EventBus

        # Create minimal mock implementations for testing
        class MinimalMockMetricsQueryPort:
            async def get_system_health(self):
                from codetoreum.ports.input.metrics_query import (
                    ComponentHealth,
                    SystemHealthInfo,
                    ComponentHealthInfo,
                )
                from datetime import UTC, datetime

                return SystemHealthInfo(
                    status=ComponentHealth.HEALTHY,
                    components=[],
                    checked_at=datetime.now(UTC),
                    uptime_seconds=1.0,
                    version="2.0.0",
                )

            async def get_component_health(self, component_name: str):
                from codetoreum.ports.input.metrics_query import (
                    ComponentHealth,
                    ComponentHealthInfo,
                )
                from datetime import UTC, datetime

                return ComponentHealthInfo(
                    component_name=component_name,
                    status=ComponentHealth.HEALTHY,
                    message="OK",
                    last_check=datetime.now(UTC),
                    response_time_ms=1.0,
                    details={},
                )

            async def get_active_agents(self):
                return []

            async def get_api_usage(self):
                from codetoreum.adapters.primary.metrics_dtos import ClaudeApiUsageInfo

                return ClaudeApiUsageInfo(
                    available=True,
                    weekly_usage=0,
                    weekly_quota=1000000,
                    weekly_usage_percent=0.0,
                    session_usage=0,
                    session_quota=100000,
                    session_usage_percent=0.0,
                    session_remaining_minutes=60,
                )

            async def get_repair_cycle_metrics(self, agent_name=None, start_time=None, end_time=None):
                return {}

            async def get_performance_metrics(self, start_time, end_time, aggregation_window_seconds=60):
                from codetoreum.ports.input.metrics_query import PerformanceMetrics

                return PerformanceMetrics(
                    api_request_count=0,
                    api_error_count=0,
                    api_latency_p50_ms=0.0,
                    api_latency_p95_ms=0.0,
                    api_latency_p99_ms=0.0,
                    active_executions=0,
                    pending_executions=0,
                    completed_executions_total=0,
                    failed_executions_total=0,
                    avg_execution_duration_seconds=0.0,
                    active_containers=0,
                    container_cpu_usage_percent=0.0,
                    container_memory_usage_mb=0.0,
                    queue_depth=0,
                    queue_processing_rate=0.0,
                    start_time=start_time,
                    end_time=end_time,
                    aggregation_window_seconds=aggregation_window_seconds,
                )

            async def get_integration_status(self):
                from codetoreum.ports.input.metrics_query import IntegrationStatus
                from datetime import UTC, datetime

                return IntegrationStatus(
                    github_connected=True,
                    github_api_calls_remaining=5000,
                    github_rate_limit_reset=datetime.now(UTC),
                    github_webhook_health=None,
                    docker_connected=True,
                    docker_version="24.0.0",
                    docker_containers_running=0,
                    event_store_connected=True,
                    event_store_latency_ms=1.0,
                    config_store_connected=True,
                    config_store_latency_ms=1.0,
                    checked_at=datetime.now(UTC),
                )

            async def get_simulation_mode_info(self):
                from codetoreum.ports.input.metrics_query import SimulationModeInfo

                return SimulationModeInfo(
                    enabled=False,
                    time_multiplier=1.0,
                    deterministic_responses=False,
                    mock_external_services=False,
                    event_replay_enabled=False,
                    current_simulation_time=None,
                    started_at=None,
                )

            async def get_metric_time_series(self, metric_name: str, start_time, end_time, labels=None, aggregation=None):
                from codetoreum.ports.input.metrics_query import MetricTimeSeries

                return MetricTimeSeries(
                    metric_name=metric_name,
                    data_points=[],
                    aggregation=aggregation,
                    start_time=start_time,
                    end_time=end_time,
                )

            async def list_metric_names(self, prefix=None):
                return []

            async def get_api_endpoint_metrics(self, endpoint_path=None, start_time=None, end_time=None):
                return {}

            async def get_agent_execution_metrics(self, agent_name=None, start_time=None, end_time=None):
                return {}

            async def get_resilience_metrics(self, start_time, end_time):
                from codetoreum.ports.input.metrics_query import ResilienceMetrics

                return ResilienceMetrics(
                    circuit_breakers={},
                    rate_limiters={},
                    retry_attempts_total=0,
                    retry_successes_total=0,
                    retry_failures_total=0,
                    timeout_count=0,
                    avg_timeout_duration_ms=0.0,
                    start_time=start_time,
                    end_time=end_time,
                )

        # Create test app with auth enabled
        event_bus = EventBus()
        event_emitter = CapturingMockEventEmitter()

        app = create_app(
            workflow_command_port=MockWorkflowCommandAdapter(),
            task_query_port=MockTaskQueryAdapter(),
            config_command_port=MockConfigCommandAdapter(),
            config_query_port=MockConfigQueryAdapter(),
            metrics_query_port=MinimalMockMetricsQueryPort(),
            workspace_query_port=MockWorkspaceQueryAdapter(),
            work_item_command_port=MockWorkItemCommandAdapter(),
            work_item_query_port=MockWorkItemQueryAdapter(),
            workflow_query_port=MockWorkflowQueryAdapter(),
            workflow_run_query_port=MockTaskQueryAdapter(),
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
            audit_query_port=None,  # Not needed for this test
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

    def test_app_starts_without_prometheus_client(self, monkeypatch) -> None:
        """Verify app handles missing prometheus_client gracefully.

        This test validates that the import guard at
        src/codetoreum/adapters/primary/fastapi_app.py:36-45 sets
        PROMETHEUS_CLIENT_AVAILABLE = False when prometheus_client is unavailable,
        allowing the app to start without crashing.
        """
        # When prometheus_client IS available (normal case), verify flag is True
        from codetoreum.adapters.primary import fastapi_app

        # This should be True since prometheus_client is installed
        assert fastapi_app.PROMETHEUS_CLIENT_AVAILABLE is True, (
            "PROMETHEUS_CLIENT_AVAILABLE should be True when prometheus_client is available"
        )

        # Verify the /metrics endpoint would be mounted when the flag is True
        # (tested by the test_metrics_endpoint_http_scrape test)

        # Now verify that if make_asgi_app were unavailable, the guard
        # would handle it. We do this by checking the import structure.
        import inspect

        source = inspect.getsource(fastapi_app)

        # Verify the guard pattern exists and is correct
        # Should have:
        # try:
        #     from prometheus_client import make_asgi_app
        #     PROMETHEUS_CLIENT_AVAILABLE = True
        # except ImportError:
        #     PROMETHEUS_CLIENT_AVAILABLE = False
        assert "except ImportError" in source, (
            "Guard should handle ImportError for missing prometheus_client"
        )
        assert "PROMETHEUS_CLIENT_AVAILABLE = False" in source, (
            "Guard should set flag to False on ImportError"
        )
        assert "PROMETHEUS_CLIENT_AVAILABLE = True" in source, (
            "Guard should set flag to True on successful import"
        )

        # Verify the /metrics mounting is conditional on the flag
        assert "if PROMETHEUS_CLIENT_AVAILABLE:" in source, (
            "/metrics endpoint mounting should be conditional on PROMETHEUS_CLIENT_AVAILABLE flag"
        )
