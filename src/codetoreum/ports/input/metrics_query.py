"""
Metrics Query Input Port

This module defines the input port interface for querying system metrics,
health status, performance statistics, and resilience information.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ComponentHealth(str, Enum):
    """Health status of a component"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealthInfo:
    """Health information for a system component"""
    component_name: str
    status: ComponentHealth
    message: Optional[str]
    last_check: datetime
    response_time_ms: Optional[float]
    details: Dict[str, Any]


@dataclass
class SystemHealthInfo:
    """Overall system health"""
    status: ComponentHealth
    components: List[ComponentHealthInfo]
    checked_at: datetime
    uptime_seconds: float
    version: str


@dataclass
class PerformanceMetrics:
    """Performance metrics for the system"""
    # API metrics
    api_request_count: int
    api_error_count: int
    api_latency_p50_ms: float
    api_latency_p95_ms: float
    api_latency_p99_ms: float

    # Execution metrics
    active_executions: int
    pending_executions: int
    completed_executions_total: int
    failed_executions_total: int
    avg_execution_duration_seconds: float

    # Resource metrics
    active_containers: int
    container_cpu_usage_percent: float
    container_memory_usage_mb: float

    # Queue metrics
    queue_depth: int
    queue_processing_rate: float  # items per second

    # Time range for aggregation
    start_time: datetime
    end_time: datetime
    aggregation_window_seconds: int


@dataclass
class ResilienceMetrics:
    """Resilience infrastructure metrics"""
    # Circuit breaker stats
    circuit_breakers: Dict[str, Dict[str, Any]]  # {service_name: {state, failure_count, ...}}

    # Rate limiter stats
    rate_limiters: Dict[str, Dict[str, Any]]  # {resource_name: {requests, limit, utilization}}

    # Retry stats
    retry_attempts_total: int
    retry_successes_total: int
    retry_failures_total: int

    # Timeout stats
    timeout_count: int
    avg_timeout_duration_ms: float

    # Time range
    start_time: datetime
    end_time: datetime


@dataclass
class IntegrationStatus:
    """Status of external system integrations"""
    # GitHub integration
    github_connected: bool
    github_api_calls_remaining: Optional[int]
    github_rate_limit_reset: Optional[datetime]
    github_webhook_health: ComponentHealth

    # Docker integration
    docker_connected: bool
    docker_version: Optional[str]
    docker_containers_running: int

    # Event store integration
    event_store_connected: bool
    event_store_latency_ms: Optional[float]

    # Config store integration
    config_store_connected: bool
    config_store_latency_ms: Optional[float]

    checked_at: datetime


@dataclass
class SimulationModeInfo:
    """Simulation mode status and configuration"""
    enabled: bool
    time_multiplier: float  # Speed multiplier for simulation
    deterministic_responses: bool
    mock_external_services: bool
    event_replay_enabled: bool
    current_simulation_time: Optional[datetime]
    started_at: Optional[datetime]


@dataclass
class MetricTimeSeriesPoint:
    """Single data point in a time series"""
    timestamp: datetime
    value: float
    labels: Dict[str, str]


@dataclass
class MetricTimeSeries:
    """Time series data for a metric"""
    metric_name: str
    data_points: List[MetricTimeSeriesPoint]
    aggregation: Optional[str]  # sum, avg, min, max, p95, p99
    start_time: datetime
    end_time: datetime


class IMetricsQueryPort(ABC):
    """
    Input port for metrics queries.

    This port provides read-only access to system metrics, health status,
    and performance statistics for monitoring and observability.
    """

    @abstractmethod
    async def get_system_health(self) -> SystemHealthInfo:
        """
        Get overall system health status.

        This checks connectivity and health of all system components:
        - Event store (Redis/Elasticsearch)
        - Config store (database)
        - GitHub API
        - Docker runtime
        - LLM provider

        Returns:
            System health information
        """
        pass

    @abstractmethod
    async def get_component_health(
        self,
        component_name: str
    ) -> ComponentHealthInfo:
        """
        Get health status for a specific component.

        Args:
            component_name: Name of component to check

        Returns:
            Component health information

        Raises:
            ComponentNotFoundError: If component doesn't exist
        """
        pass

    @abstractmethod
    async def get_performance_metrics(
        self,
        start_time: datetime,
        end_time: datetime,
        aggregation_window_seconds: int = 60
    ) -> PerformanceMetrics:
        """
        Get performance metrics over a time range.

        Args:
            start_time: Start of time range
            end_time: End of time range
            aggregation_window_seconds: Aggregation window (default: 60s)

        Returns:
            Aggregated performance metrics
        """
        pass

    @abstractmethod
    async def get_resilience_metrics(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> ResilienceMetrics:
        """
        Get resilience infrastructure metrics.

        Returns circuit breaker states, rate limiter utilization,
        retry statistics, and timeout information.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Resilience metrics
        """
        pass

    @abstractmethod
    async def get_integration_status(self) -> IntegrationStatus:
        """
        Get status of external system integrations.

        Checks connectivity and health of:
        - GitHub API
        - Docker runtime
        - Event store
        - Config store

        Returns:
            Integration status information
        """
        pass

    @abstractmethod
    async def get_simulation_mode_info(self) -> SimulationModeInfo:
        """
        Get simulation mode status and configuration.

        Returns:
            Simulation mode information
        """
        pass

    @abstractmethod
    async def get_metric_time_series(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        labels: Optional[Dict[str, str]] = None,
        aggregation: Optional[str] = None
    ) -> MetricTimeSeries:
        """
        Get time series data for a specific metric.

        Args:
            metric_name: Name of metric to query
            start_time: Start of time range
            end_time: End of time range
            labels: Optional label filters
            aggregation: Optional aggregation function (sum, avg, min, max, p95, p99)

        Returns:
            Time series data

        Raises:
            MetricNotFoundError: If metric doesn't exist
        """
        pass

    @abstractmethod
    async def list_metric_names(
        self,
        prefix: Optional[str] = None
    ) -> List[str]:
        """
        List available metric names.

        Args:
            prefix: Optional prefix filter

        Returns:
            List of metric names
        """
        pass

    @abstractmethod
    async def get_api_endpoint_metrics(
        self,
        endpoint_path: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get per-endpoint API metrics.

        Args:
            endpoint_path: Optional filter by specific endpoint
            start_time: Start of time range (default: last hour)
            end_time: End of time range (default: now)

        Returns:
            Dict mapping endpoint paths to metrics (request count, error rate, latency percentiles)
        """
        pass

    @abstractmethod
    async def get_agent_execution_metrics(
        self,
        agent_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get agent execution metrics.

        Args:
            agent_name: Optional filter by specific agent
            start_time: Start of time range (default: last hour)
            end_time: End of time range (default: now)

        Returns:
            Dict with execution counts, success rates, duration stats per agent
        """
        pass

    @abstractmethod
    async def get_active_agents(self) -> Dict[str, Any]:
        """
        Get currently active agent executions.

        Returns:
            Dict containing list of active agents with execution info
        """
        pass

    @abstractmethod
    async def get_api_usage(self) -> Dict[str, Any]:
        """
        Get API usage and quota information.

        Returns:
            Dict with usage statistics for external APIs (Claude, etc.)
        """
        pass
