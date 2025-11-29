"""
Metrics Service

Application service implementing IMetricsQueryPort to query system metrics,
health status, and performance statistics.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from codetoreum.ports.exceptions import ComponentNotFoundError, MetricNotFoundError
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
from codetoreum.ports.output.event_store import IEventStore

logger = logging.getLogger(__name__)


class MetricsService(IMetricsQueryPort):
    """
    Metrics query service providing observability into system health and performance.

    This service implements the IMetricsQueryPort interface and provides access to:
    - System health status
    - Performance metrics
    - Active agent executions
    - API usage statistics
    - Integration status

    **Note**: This is a basic implementation that queries the event store for
    metrics. In a production system, this would integrate with proper metrics
    infrastructure (Prometheus, Elasticsearch, etc.).
    """

    def __init__(
        self,
        event_store: IEventStore,
        start_time: datetime,
        version: str = "1.0.0",
    ):
        """
        Initialize metrics service.

        Args:
            event_store: Event store for querying execution events
            start_time: System start time (for uptime calculation)
            version: System version string
        """
        self.event_store = event_store
        self.start_time = start_time
        self.version = version

    async def get_system_health(self) -> SystemHealthInfo:
        """
        Get overall system health status.

        Returns:
            System health information
        """
        logger.debug("Getting system health")

        # Check components
        components: List[ComponentHealthInfo] = []

        # Event store health
        event_store_health = await self._check_event_store_health()
        components.append(event_store_health)

        # Determine overall status
        if all(c.status == ComponentHealth.HEALTHY for c in components):
            overall_status = ComponentHealth.HEALTHY
        elif any(c.status == ComponentHealth.UNHEALTHY for c in components):
            overall_status = ComponentHealth.UNHEALTHY
        else:
            overall_status = ComponentHealth.DEGRADED

        # Calculate uptime
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()

        return SystemHealthInfo(
            status=overall_status,
            components=components,
            checked_at=datetime.now(),
            uptime_seconds=uptime_seconds,
            version=self.version,
        )

    async def get_component_health(self, component_name: str) -> ComponentHealthInfo:
        """
        Get health status for a specific component.

        Args:
            component_name: Name of component to check

        Returns:
            Component health information

        Raises:
            ComponentNotFoundError: If component doesn't exist
        """
        if component_name == "event_store":
            return await self._check_event_store_health()
        else:
            raise ComponentNotFoundError(component_name)

    async def get_performance_metrics(
        self,
        start_time: datetime,
        end_time: datetime,
        aggregation_window_seconds: int = 60,
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
        logger.debug(f"Getting performance metrics from {start_time} to {end_time}")

        # Query execution events
        execution_events = await self.event_store.get_events_by_type(
            event_type="AgentExecutionStarted",
            since=start_time,
            limit=10000,
        )

        completed_events = await self.event_store.get_events_by_type(
            event_type="AgentExecutionCompleted",
            since=start_time,
            limit=10000,
        )

        failed_events = await self.event_store.get_events_by_type(
            event_type="AgentExecutionFailed",
            since=start_time,
            limit=10000,
        )

        # Calculate metrics
        active_executions = len(execution_events) - len(completed_events) - len(failed_events)
        active_executions = max(0, active_executions)  # Ensure non-negative

        # Calculate average duration from completed executions
        total_duration = 0.0
        duration_count = 0
        for event in completed_events:
            if "duration_seconds" in event.payload:
                total_duration += event.payload["duration_seconds"]
                duration_count += 1

        avg_duration = total_duration / duration_count if duration_count > 0 else 0.0

        return PerformanceMetrics(
            api_request_count=0,  # TODO: Integrate with API metrics
            api_error_count=0,
            api_latency_p50_ms=0.0,
            api_latency_p95_ms=0.0,
            api_latency_p99_ms=0.0,
            active_executions=active_executions,
            pending_executions=0,  # TODO: Query from queue
            completed_executions_total=len(completed_events),
            failed_executions_total=len(failed_events),
            avg_execution_duration_seconds=avg_duration,
            active_containers=0,  # TODO: Query from container runtime
            container_cpu_usage_percent=0.0,
            container_memory_usage_mb=0.0,
            queue_depth=0,  # TODO: Query from queue
            queue_processing_rate=0.0,
            start_time=start_time,
            end_time=end_time,
            aggregation_window_seconds=aggregation_window_seconds,
        )

    async def get_resilience_metrics(
        self, start_time: datetime, end_time: datetime
    ) -> ResilienceMetrics:
        """
        Get resilience infrastructure metrics.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Resilience metrics
        """
        logger.debug(f"Getting resilience metrics from {start_time} to {end_time}")

        # TODO: Integrate with resilience infrastructure to get real metrics
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

    async def get_integration_status(self) -> IntegrationStatus:
        """
        Get status of external system integrations.

        Returns:
            Integration status information
        """
        logger.debug("Getting integration status")

        # Check event store connectivity
        event_store_connected = True
        event_store_latency = None
        try:
            check_start = datetime.now()
            await self.event_store.get_statistics()
            event_store_latency = (datetime.now() - check_start).total_seconds() * 1000
        except Exception as e:
            logger.warning(f"Event store health check failed: {e}")
            event_store_connected = False

        return IntegrationStatus(
            github_connected=False,  # TODO: Check GitHub connection
            github_api_calls_remaining=None,
            github_rate_limit_reset=None,
            github_webhook_health=ComponentHealth.UNKNOWN,
            docker_connected=False,  # TODO: Check Docker connection
            docker_version=None,
            docker_containers_running=0,
            event_store_connected=event_store_connected,
            event_store_latency_ms=event_store_latency,
            config_store_connected=False,  # TODO: Check config store connection
            config_store_latency_ms=None,
            checked_at=datetime.now(),
        )

    async def get_simulation_mode_info(self) -> SimulationModeInfo:
        """
        Get simulation mode status and configuration.

        Returns:
            Simulation mode information
        """
        # TODO: Integrate with simulation infrastructure
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
        """
        Get time series data for a specific metric.

        Args:
            metric_name: Name of metric to query
            start_time: Start of time range
            end_time: End of time range
            labels: Optional label filters
            aggregation: Optional aggregation function

        Returns:
            Time series data

        Raises:
            MetricNotFoundError: If metric doesn't exist
        """
        # TODO: Integrate with time series database (Prometheus, InfluxDB, etc.)
        raise MetricNotFoundError(metric_name)

    async def list_metric_names(self, prefix: Optional[str] = None) -> List[str]:
        """
        List available metric names.

        Args:
            prefix: Optional prefix filter

        Returns:
            List of metric names
        """
        # TODO: Integrate with metrics infrastructure
        return []

    async def get_api_endpoint_metrics(
        self,
        endpoint_path: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get per-endpoint API metrics.

        Args:
            endpoint_path: Optional filter by specific endpoint
            start_time: Start of time range (default: last hour)
            end_time: End of time range (default: now)

        Returns:
            Dict mapping endpoint paths to metrics
        """
        # TODO: Integrate with API monitoring
        return {}

    async def get_agent_execution_metrics(
        self,
        agent_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
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
        if start_time is None:
            start_time = datetime.now() - timedelta(hours=1)
        if end_time is None:
            end_time = datetime.now()

        logger.debug(
            f"Getting agent execution metrics for {agent_name or 'all agents'} "
            f"from {start_time} to {end_time}"
        )

        # Query execution events from event store
        execution_events = await self.event_store.get_events_by_type(
            event_type="AgentExecutionStarted",
            since=start_time,
            limit=10000,
        )

        completed_events = await self.event_store.get_events_by_type(
            event_type="AgentExecutionCompleted",
            since=start_time,
            limit=10000,
        )

        failed_events = await self.event_store.get_events_by_type(
            event_type="AgentExecutionFailed",
            since=start_time,
            limit=10000,
        )

        # Filter by agent name if specified
        if agent_name:
            execution_events = [
                e for e in execution_events if e.payload.get("agent_name") == agent_name
            ]
            completed_events = [
                e for e in completed_events if e.payload.get("agent_name") == agent_name
            ]
            failed_events = [
                e for e in failed_events if e.payload.get("agent_name") == agent_name
            ]

        # Calculate metrics
        total_executions = len(execution_events)
        total_completed = len(completed_events)
        total_failed = len(failed_events)
        total_active = total_executions - total_completed - total_failed

        success_rate = (
            total_completed / total_executions if total_executions > 0 else 0.0
        )

        # Calculate duration stats from completed executions
        durations = [
            e.payload["duration_seconds"]
            for e in completed_events
            if "duration_seconds" in e.payload
        ]

        avg_duration = sum(durations) / len(durations) if durations else 0.0
        min_duration = min(durations) if durations else 0.0
        max_duration = max(durations) if durations else 0.0

        return {
            "agent_name": agent_name or "all",
            "total_executions": total_executions,
            "completed": total_completed,
            "failed": total_failed,
            "active": total_active,
            "success_rate": success_rate,
            "avg_duration_seconds": avg_duration,
            "min_duration_seconds": min_duration,
            "max_duration_seconds": max_duration,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        }

    async def get_active_agents(self) -> Dict[str, Any]:
        """
        Get currently active agent executions.

        Returns:
            Dict containing list of active agents with execution info
        """
        logger.debug("Getting active agents")

        # Query for recent execution started events
        recent_time = datetime.now() - timedelta(hours=24)
        execution_events = await self.event_store.get_events_by_type(
            event_type="AgentExecutionStarted",
            since=recent_time,
            limit=10000,
        )

        # Query for completed events
        completed_events = await self.event_store.get_events_by_type(
            event_type="AgentExecutionCompleted",
            since=recent_time,
            limit=10000,
        )

        failed_events = await self.event_store.get_events_by_type(
            event_type="AgentExecutionFailed",
            since=recent_time,
            limit=10000,
        )

        # Build set of completed/failed execution IDs
        finished_ids = set()
        for event in completed_events + failed_events:
            if "execution_id" in event.payload:
                finished_ids.add(event.payload["execution_id"])

        # Filter to only active executions
        active_agents = []
        for event in execution_events:
            execution_id = event.payload.get("execution_id")
            if execution_id and execution_id not in finished_ids:
                active_agents.append(
                    {
                        "execution_id": execution_id,
                        "agent_name": event.payload.get("agent_name"),
                        "work_item_id": event.payload.get("work_item_id"),
                        "started_at": event.occurred_at.isoformat(),
                        "duration_seconds": (datetime.now() - event.occurred_at).total_seconds(),
                    }
                )

        return {
            "count": len(active_agents),
            "agents": active_agents,
            "checked_at": datetime.now().isoformat(),
        }

    async def get_api_usage(self) -> Dict[str, Any]:
        """
        Get API usage and quota information.

        Returns:
            Dict with usage statistics for external APIs (Claude, etc.)
        """
        logger.debug("Getting API usage")

        # TODO: Integrate with actual Claude API usage tracking
        # This would typically query usage metrics from the LLM provider adapter
        # or from a dedicated usage tracking service

        # Query for recent LLM API calls from events
        recent_time = datetime.now() - timedelta(days=1)

        # For now, return placeholder data
        return {
            "claude_api": {
                "requests_today": 0,
                "tokens_input_today": 0,
                "tokens_output_today": 0,
                "quota_remaining": None,
                "quota_reset_time": None,
                "estimated_cost_usd": 0.0,
            },
            "github_api": {
                "requests_remaining": None,
                "quota_limit": None,
                "quota_reset_time": None,
            },
            "checked_at": datetime.now().isoformat(),
        }

    # Private helper methods

    async def _check_event_store_health(self) -> ComponentHealthInfo:
        """
        Check event store health.

        Returns:
            Component health info for event store
        """
        check_start = datetime.now()

        try:
            # Attempt to get stats from event store
            stats = await self.event_store.get_statistics()

            response_time_ms = (datetime.now() - check_start).total_seconds() * 1000

            return ComponentHealthInfo(
                component_name="event_store",
                status=ComponentHealth.HEALTHY,
                message="Event store is operational",
                last_check=datetime.now(),
                response_time_ms=response_time_ms,
                details=stats,
            )

        except Exception as e:
            response_time_ms = (datetime.now() - check_start).total_seconds() * 1000

            return ComponentHealthInfo(
                component_name="event_store",
                status=ComponentHealth.UNHEALTHY,
                message=f"Event store health check failed: {e}",
                last_check=datetime.now(),
                response_time_ms=response_time_ms,
                details={"error": str(e)},
            )
