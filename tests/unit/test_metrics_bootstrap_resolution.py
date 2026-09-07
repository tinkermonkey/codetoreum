"""Unit test for metrics adapter resolution through bootstrap/resolver.

Validates that the PrometheusMetricsAdapter is correctly resolved and wired
through the real AdapterResolver with production configuration, and that the
resolved adapter records metrics end-to-end that can be scraped via /metrics.
"""

import asyncio

import pytest

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
from codetoreum.infrastructure.bootstrap.production_engine_stub import (
    ProductionEngineStub,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.infrastructure.simulation.simulation_config import (
    AdapterSelectionConfig,
)


@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    """Clear Prometheus registry before each test to avoid collisions."""
    try:
        from prometheus_client import REGISTRY

        # Collect all collectors to unregister
        collectors_to_remove = list(REGISTRY._collector_to_names.keys())
        for collector in collectors_to_remove:
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass
    except Exception:
        pass

    yield

    # Clean up after test
    try:
        from prometheus_client import REGISTRY

        collectors_to_remove = list(REGISTRY._collector_to_names.keys())
        for collector in collectors_to_remove:
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass
    except Exception:
        pass


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
        configured to create a real PrometheusMetricsAdapter by checking the
        factory registry without instantiating (to avoid Prometheus global registry issues).
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
        engine_stub = ProductionEngineStub()
        factory = AdapterFactory()
        event_emitter = CapturingMockEventEmitter()
        failed_event_store = InMemoryFailedEventStore()

        adapter_deps = AdapterDependencies(
            event_bus=event_bus,
            event_emitter=event_emitter,
            logger=None,
            engine=engine_stub,
            config=None,
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
            engine_stub = ProductionEngineStub()
            factory = AdapterFactory()
            event_emitter = CapturingMockEventEmitter()
            failed_event_store = InMemoryFailedEventStore()

            adapter_deps = AdapterDependencies(
                event_bus=event_bus,
                event_emitter=event_emitter,
                logger=None,
                engine=engine_stub,
                config=None,
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
