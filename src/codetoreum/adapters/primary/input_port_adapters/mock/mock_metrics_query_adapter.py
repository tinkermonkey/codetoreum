"""
Mock Metrics Query Adapter

In-memory implementation of IMetricsQueryPort for development and testing.
Integrates with InMemoryMetricsAdapter for actual metrics storage.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from threading import RLock

from codetoreum.ports.input.metrics_query import (
    ComponentHealth,
    ComponentHealthInfo,
    IMetricsQueryPort,
    IntegrationStatus,
    MetricTimeSeries,
    MetricTimeSeriesPoint,
    PerformanceMetrics,
    ResilienceMetrics,
    SimulationModeInfo,
    SystemHealthInfo,
)

if TYPE_CHECKING:
    from codetoreum.adapters.testing.in_memory_metrics_adapter import InMemoryMetricsAdapter
    from codetoreum.ports.output.event_store import IEventStore
    from codetoreum.infrastructure.simulation.simulation_clock import SimulationClock


class MockMetricsQueryAdapter(IMetricsQueryPort):
    """
    Mock implementation of IMetricsQueryPort using in-memory storage.

    Integrates with:
    - InMemoryMetricsAdapter for metrics data
    - IEventStore for event-based metrics
    - SimulationClock for time-based queries
    """

    def __init__(
        self,
        metrics_adapter: Optional["InMemoryMetricsAdapter"] = None,
        event_store: Optional["IEventStore"] = None,
        clock: Optional["SimulationClock"] = None,
    ):
        """
        Initialize the mock metrics query adapter.

        Args:
            metrics_adapter: Optional metrics storage adapter
            event_store: Optional event store for event-based metrics
            clock: Optional simulation clock for time-based queries
        """
        self._metrics_adapter = metrics_adapter
        self._event_store = event_store
        self._clock = clock
        self._component_health: Dict[str, ComponentHealthInfo] = {}
        self._metrics_data: Dict[str, List[MetricTimeSeriesPoint]] = {}
        self._integration_status: Optional[IntegrationStatus] = None
        self._simulation_mode: Optional[SimulationModeInfo] = None
        self._lock = RLock()
        self._start_time = datetime.now(timezone.utc)

    async def get_system_health(self) -> SystemHealthInfo:
        """Get overall system health status."""
        with self._lock:
            components = list(self._component_health.values()) or self._default_components()

            # Determine overall status
            if any(c.status == ComponentHealth.UNHEALTHY for c in components):
                overall_status = ComponentHealth.UNHEALTHY
            elif any(c.status == ComponentHealth.DEGRADED for c in components):
                overall_status = ComponentHealth.DEGRADED
            else:
                overall_status = ComponentHealth.HEALTHY

            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()

            return SystemHealthInfo(
                status=overall_status,
                components=components,
                checked_at=datetime.now(timezone.utc),
                uptime_seconds=uptime,
                version="1.0.0-dev",
            )

    async def get_component_health(self, component_name: str) -> ComponentHealthInfo:
        """Get health status for a specific component."""
        with self._lock:
            if component_name in self._component_health:
                return self._component_health[component_name]

            # Return default healthy status
            return ComponentHealthInfo(
                component_name=component_name,
                status=ComponentHealth.HEALTHY,
                message=None,
                last_check=datetime.now(timezone.utc),
                response_time_ms=10.0,
                details={},
            )

    async def get_performance_metrics(
        self,
        start_time: datetime,
        end_time: datetime,
        aggregation_window_seconds: int = 60,
    ) -> PerformanceMetrics:
        """Get performance metrics over a time range."""
        # Return mock data
        return PerformanceMetrics(
            api_request_count=1000,
            api_error_count=10,
            api_latency_p50_ms=50.0,
            api_latency_p95_ms=200.0,
            api_latency_p99_ms=500.0,
            active_executions=5,
            pending_executions=10,
            completed_executions_total=100,
            failed_executions_total=5,
            avg_execution_duration_seconds=120.0,
            active_containers=5,
            container_cpu_usage_percent=30.0,
            container_memory_usage_mb=512.0,
            queue_depth=10,
            queue_processing_rate=2.5,
            start_time=start_time,
            end_time=end_time,
            aggregation_window_seconds=aggregation_window_seconds,
        )

    async def get_resilience_metrics(
        self, start_time: datetime, end_time: datetime
    ) -> ResilienceMetrics:
        """Get resilience infrastructure metrics."""
        return ResilienceMetrics(
            circuit_breakers={
                "github_api": {"state": "closed", "failure_count": 0},
                "llm_provider": {"state": "closed", "failure_count": 0},
            },
            rate_limiters={
                "github_api": {"requests": 100, "limit": 5000, "utilization": 0.02},
                "llm_provider": {"requests": 50, "limit": 600, "utilization": 0.083},
            },
            retry_attempts_total=25,
            retry_successes_total=20,
            retry_failures_total=5,
            timeout_count=2,
            avg_timeout_duration_ms=30000.0,
            start_time=start_time,
            end_time=end_time,
        )

    async def get_integration_status(self) -> IntegrationStatus:
        """Get status of external system integrations."""
        if self._integration_status:
            return self._integration_status

        # Return default healthy status
        return IntegrationStatus(
            github_connected=True,
            github_api_calls_remaining=4500,
            github_rate_limit_reset=datetime.now(timezone.utc) + timedelta(hours=1),
            github_webhook_health=ComponentHealth.HEALTHY,
            docker_connected=True,
            docker_version="20.10.0",
            docker_containers_running=5,
            event_store_connected=True,
            event_store_latency_ms=5.0,
            config_store_connected=True,
            config_store_latency_ms=3.0,
            checked_at=datetime.now(timezone.utc),
        )

    async def get_simulation_mode_info(self) -> SimulationModeInfo:
        """Get simulation mode status and configuration."""
        # If clock is available, return simulation mode info
        if self._clock:
            return SimulationModeInfo(
                enabled=True,
                time_multiplier=self._clock._speed_multiplier,
                deterministic_responses=True,
                mock_external_services=True,
                event_replay_enabled=True,
                current_simulation_time=self._clock.now(),
                started_at=self._clock._current_time,
            )

        if self._simulation_mode:
            return self._simulation_mode

        # Return default (simulation disabled)
        return SimulationModeInfo(
            enabled=False,
            time_multiplier=1.0,
            deterministic_responses=False,
            mock_external_services=False,
            event_replay_enabled=False,
            current_simulation_time=None,
            started_at=None,
        )

    async def get_metric_time_series(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        labels: Optional[Dict[str, str]] = None,
        aggregation: Optional[str] = None,
    ) -> MetricTimeSeries:
        """Get time series data for a specific metric."""
        # If metrics adapter is available, query it directly
        if self._metrics_adapter:
            # Query metrics from the adapter
            metrics = await self._metrics_adapter.query_metrics(
                name=metric_name,
                start_time=start_time,
                end_time=end_time,
                labels=labels,
                aggregation=aggregation,
            )

            # Convert to MetricTimeSeriesPoint format
            data_points = []
            for metric in metrics:
                data_points.append(
                    MetricTimeSeriesPoint(
                        timestamp=metric.timestamp,
                        value=metric.value,
                        labels=metric.labels or {},
                    )
                )

            return MetricTimeSeries(
                metric_name=metric_name,
                data_points=data_points,
                aggregation=aggregation,
                start_time=start_time,
                end_time=end_time,
            )

        # Fallback to local storage
        with self._lock:
            data_points = self._metrics_data.get(metric_name, [])

            # Filter by time range
            data_points = [
                dp for dp in data_points if start_time <= dp.timestamp <= end_time
            ]

            # Filter by labels if provided
            if labels:
                data_points = [
                    dp
                    for dp in data_points
                    if all(dp.labels.get(k) == v for k, v in labels.items())
                ]

            return MetricTimeSeries(
                metric_name=metric_name,
                data_points=data_points,
                aggregation=aggregation,
                start_time=start_time,
                end_time=end_time,
            )

    async def list_metric_names(self, prefix: Optional[str] = None) -> List[str]:
        """List available metric names."""
        # If metrics adapter is available, query it
        if self._metrics_adapter:
            metric_names = await self._metrics_adapter.get_metric_names(prefix=prefix)
            return sorted(metric_names)

        # Fallback to local storage
        with self._lock:
            metric_names = list(self._metrics_data.keys())

            if prefix:
                metric_names = [m for m in metric_names if m.startswith(prefix)]

            return sorted(metric_names)

    async def get_api_endpoint_metrics(
        self,
        endpoint_path: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get per-endpoint API metrics."""
        return {
            "endpoints": {
                "/api/v1/agents": {
                    "request_count": 100,
                    "error_count": 2,
                    "latency_p50_ms": 25.0,
                    "latency_p95_ms": 100.0,
                    "latency_p99_ms": 250.0,
                },
                "/api/v1/executions": {
                    "request_count": 200,
                    "error_count": 5,
                    "latency_p50_ms": 50.0,
                    "latency_p95_ms": 200.0,
                    "latency_p99_ms": 500.0,
                },
            }
        }

    async def get_agent_execution_metrics(
        self,
        agent_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get agent execution metrics."""
        return {
            "agents": {
                "developer_agent": {
                    "execution_count": 50,
                    "success_count": 45,
                    "failure_count": 5,
                    "avg_duration_seconds": 180.0,
                    "p95_duration_seconds": 300.0,
                },
                "reviewer_agent": {
                    "execution_count": 30,
                    "success_count": 28,
                    "failure_count": 2,
                    "avg_duration_seconds": 120.0,
                    "p95_duration_seconds": 200.0,
                },
            }
        }

    async def get_active_agents(self) -> Dict[str, Any]:
        """
        Get currently active agent executions.

        Returns:
            Dict containing list of active agents with execution info
        """
        # Return empty list in mock implementation
        # Real implementation would query execution tracking system
        return {
            "agents": []
        }

    async def get_api_usage(self) -> Dict[str, Any]:
        """
        Get API usage and quota information.

        Returns:
            Dict with usage statistics for external APIs (Claude, etc.)
        """
        # Return mock usage data
        return {
            "claude": {
                "available": True,
                "weekly_usage": 15000000,
                "weekly_quota": 50000000,
                "session_usage": 2000000,
                "session_quota": 10000000,
                "session_remaining_minutes": 45,
            }
        }

    def set_component_health(self, component_name: str, health_info: ComponentHealthInfo):
        """Helper method to set component health (for testing)."""
        with self._lock:
            self._component_health[component_name] = health_info

    def record_metric(
        self,
        metric_name: str,
        value: float,
        timestamp: datetime,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Helper method to record a metric data point (for testing)."""
        with self._lock:
            if metric_name not in self._metrics_data:
                self._metrics_data[metric_name] = []

            data_point = MetricTimeSeriesPoint(
                timestamp=timestamp, value=value, labels=labels or {}
            )
            self._metrics_data[metric_name].append(data_point)

    def set_integration_status(self, status: IntegrationStatus):
        """Helper method to set integration status (for testing)."""
        with self._lock:
            self._integration_status = status

    def set_simulation_mode(self, mode_info: SimulationModeInfo):
        """Helper method to set simulation mode (for testing)."""
        with self._lock:
            self._simulation_mode = mode_info

    def clear(self):
        """Clear all data (useful for testing)."""
        with self._lock:
            self._component_health.clear()
            self._metrics_data.clear()
            self._integration_status = None
            self._simulation_mode = None

    def _default_components(self) -> List[ComponentHealthInfo]:
        """Return default component health info."""
        now = datetime.now(timezone.utc)
        return [
            ComponentHealthInfo(
                component_name="event_store",
                status=ComponentHealth.HEALTHY,
                message=None,
                last_check=now,
                response_time_ms=5.0,
                details={},
            ),
            ComponentHealthInfo(
                component_name="config_store",
                status=ComponentHealth.HEALTHY,
                message=None,
                last_check=now,
                response_time_ms=3.0,
                details={},
            ),
            ComponentHealthInfo(
                component_name="github_api",
                status=ComponentHealth.HEALTHY,
                message=None,
                last_check=now,
                response_time_ms=100.0,
                details={},
            ),
            ComponentHealthInfo(
                component_name="docker_runtime",
                status=ComponentHealth.HEALTHY,
                message=None,
                last_check=now,
                response_time_ms=10.0,
                details={},
            ),
        ]
