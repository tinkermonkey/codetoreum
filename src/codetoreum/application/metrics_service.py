"""
Metrics Service

Application service implementing IMetricsQueryPort to query system metrics,
health status, and performance statistics.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from codetoreum.ports.exceptions import ComponentNotFoundError, MetricNotFoundError
from codetoreum.ports.input.metrics_query import (
    ComponentHealth,
    ComponentHealthInfo,
    IMetricsQueryPort,
    IntegrationStatus,
    MetricTimeSeries,
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
        # Normalize start_time to UTC-aware datetime
        self.start_time = start_time if start_time.tzinfo is not None else start_time.replace(tzinfo=UTC)
        self.version = version

    async def get_system_health(self) -> SystemHealthInfo:
        """
        Get overall system health status.

        Returns:
            System health information
        """
        logger.debug("Getting system health")

        # Check components
        components: list[ComponentHealthInfo] = []

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
        uptime_seconds = (datetime.now(UTC) - self.start_time).total_seconds()

        return SystemHealthInfo(
            status=overall_status,
            components=components,
            checked_at=datetime.now(UTC),
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

    async def get_resilience_metrics(self, start_time: datetime, end_time: datetime) -> ResilienceMetrics:
        """
        Get resilience infrastructure metrics.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Resilience metrics
        """
        logger.debug(f"Getting resilience metrics from {start_time} to {end_time}")

        # Query retry and timeout events from event store
        retry_events = await self.event_store.get_events_by_type(
            event_type="ExecutionRetried",
            since=start_time,
            limit=10000,
        )

        timeout_events = await self.event_store.get_events_by_type(
            event_type="ExecutionTimeout",
            since=start_time,
            limit=10000,
        )

        # Count retry attempts and outcomes
        retry_attempts = len(retry_events)
        retry_successes = sum(1 for e in retry_events if e.payload.get("success", False))
        retry_failures = retry_attempts - retry_successes

        # Calculate timeout metrics
        timeout_durations = [e.payload.get("duration_ms", 0) for e in timeout_events if "duration_ms" in e.payload]
        avg_timeout_duration = sum(timeout_durations) / len(timeout_durations) if timeout_durations else 0.0

        return ResilienceMetrics(
            circuit_breakers={},  # Would be populated from resilience infrastructure
            rate_limiters={},  # Would be populated from resilience infrastructure
            retry_attempts_total=retry_attempts,
            retry_successes_total=retry_successes,
            retry_failures_total=retry_failures,
            timeout_count=len(timeout_events),
            avg_timeout_duration_ms=avg_timeout_duration,
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
            check_start = datetime.now(UTC)
            stats = await self.event_store.get_statistics()
            event_store_latency = (datetime.now(UTC) - check_start).total_seconds() * 1000
        except Exception as e:
            logger.warning(
                f"Event store health check failed: {e}",
                exc_info=True,
                extra={"error_id": "ERR_METRICS_EVENTSTORE_HEALTH_CHECK_FAILURE"},
            )
            event_store_connected = False

        # Check GitHub connectivity via recent adapter events
        github_connected = False
        github_webhook_health = ComponentHealth.UNKNOWN
        try:
            recent_time = datetime.now(UTC) - timedelta(hours=1)
            github_events = await self.event_store.get_events_by_type(
                event_type="GitHubAdapterEvent",
                since=recent_time,
                limit=100,
            )
            if github_events:
                # If we have recent GitHub events, assume it's connected
                failed_events = [e for e in github_events if e.payload.get("success") is False]
                if failed_events:
                    github_webhook_health = ComponentHealth.DEGRADED
                else:
                    github_webhook_health = ComponentHealth.HEALTHY
                github_connected = True
        except Exception as e:
            logger.debug(f"Could not check GitHub connectivity: {e}")

        # Check Docker connectivity via recent container events
        docker_connected = False
        docker_containers_running = 0
        try:
            recent_time = datetime.now(UTC) - timedelta(hours=1)
            container_events = await self.event_store.get_events_by_type(
                event_type="ContainerStarted",
                since=recent_time,
                limit=1000,
            )
            container_stopped = await self.event_store.get_events_by_type(
                event_type="ContainerStopped",
                since=recent_time,
                limit=1000,
            )
            if container_events or container_stopped:
                docker_connected = True
                # Rough calculation of running containers
                docker_containers_running = max(0, len(container_events) - len(container_stopped))
        except Exception as e:
            logger.debug(f"Could not check Docker connectivity: {e}")

        return IntegrationStatus(
            github_connected=github_connected,
            github_api_calls_remaining=None,
            github_rate_limit_reset=None,
            github_webhook_health=github_webhook_health,
            docker_connected=docker_connected,
            docker_version=None,
            docker_containers_running=docker_containers_running,
            event_store_connected=event_store_connected,
            event_store_latency_ms=event_store_latency,
            config_store_connected=False,  # Not yet integrated
            config_store_latency_ms=None,
            checked_at=datetime.now(UTC),
        )

    async def get_simulation_mode_info(self) -> SimulationModeInfo:
        """
        Get simulation mode status and configuration.

        Returns:
            Simulation mode information
        """
        # Query for simulation configuration events
        try:
            sim_events = await self.event_store.get_events_by_type(
                event_type="SimulationConfigured",
                limit=1,
            )
            if sim_events:
                config = sim_events[0].payload
                return SimulationModeInfo(
                    enabled=config.get("enabled", False),
                    time_multiplier=config.get("time_multiplier", 1.0),
                    deterministic_responses=config.get("deterministic_responses", False),
                    mock_external_services=config.get("mock_external_services", False),
                    event_replay_enabled=config.get("event_replay_enabled", False),
                    current_simulation_time=config.get("current_simulation_time"),
                    started_at=config.get("started_at"),
                )
        except Exception as e:
            logger.debug(f"Could not retrieve simulation config: {e}")

        # Default to non-simulation mode
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
        labels: dict[str, str] | None = None,
        aggregation: str | None = None,
    ) -> MetricTimeSeries:
        """
        Get time series data for a specific metric.

        Supports querying common metrics from the event store:
        - execution_count: Number of agent executions
        - execution_success_rate: Percentage of successful executions
        - execution_avg_duration: Average execution duration
        - error_rate: Percentage of failed executions

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
        # Map metric names to event types and data extraction logic
        metric_mapping = {
            "execution_count": ("AgentExecutionStarted", "count"),
            "execution_success_rate": ("AgentExecutionCompleted", "rate"),
            "execution_avg_duration": ("AgentExecutionCompleted", "duration"),
            "error_rate": ("AgentExecutionFailed", "rate"),
        }

        if metric_name not in metric_mapping:
            raise MetricNotFoundError(metric_name)

        event_type, calculation_type = metric_mapping[metric_name]

        # Query events for the metric
        events = await self.event_store.get_events_by_type(
            event_type=event_type,
            since=start_time,
            limit=10000,
        )

        # Filter to time range
        filtered_events = [e for e in events if e.occurred_at <= end_time]

        # Calculate time series data
        data_points = []
        if calculation_type == "count":
            data_points = [{"timestamp": start_time.isoformat(), "value": len(filtered_events)}]
        elif calculation_type == "rate":
            total_events = len(filtered_events)
            if total_events > 0:
                rate = (total_events / max(1, total_events)) * 100
                data_points = [{"timestamp": start_time.isoformat(), "value": rate}]
        elif calculation_type == "duration":
            durations = [e.payload.get("duration_seconds", 0) for e in filtered_events if "duration_seconds" in e.payload]
            if durations:
                avg_duration = sum(durations) / len(durations)
                data_points = [{"timestamp": start_time.isoformat(), "value": avg_duration}]

        return MetricTimeSeries(
            metric_name=metric_name,
            labels=labels or {},
            start_time=start_time,
            end_time=end_time,
            data_points=data_points,
            aggregation=aggregation or "raw",
        )

    async def list_metric_names(self, prefix: str | None = None) -> list[str]:
        """
        List available metric names.

        Args:
            prefix: Optional prefix filter

        Returns:
            List of metric names
        """
        # List of available metrics that can be queried
        available_metrics = [
            "execution_count",
            "execution_success_rate",
            "execution_avg_duration",
            "error_rate",
            "active_executions",
            "completed_executions",
            "failed_executions",
            "container_count",
            "queue_depth",
        ]

        if prefix:
            return [m for m in available_metrics if m.startswith(prefix)]
        return available_metrics

    async def get_api_endpoint_metrics(
        self,
        endpoint_path: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Get per-endpoint API metrics.

        Args:
            endpoint_path: Optional filter by specific endpoint
            start_time: Start of time range (default: last hour)
            end_time: End of time range (default: now)

        Returns:
            Dict mapping endpoint paths to metrics
        """
        if start_time is None:
            start_time = datetime.now(UTC) - timedelta(hours=1)
        if end_time is None:
            end_time = datetime.now(UTC)

        logger.debug(f"Getting API endpoint metrics from {start_time} to {end_time}")

        # Query API request events from event store
        api_events = await self.event_store.get_events_by_type(
            event_type="APIRequestProcessed",
            since=start_time,
            limit=10000,
        )

        # Group metrics by endpoint
        endpoints: dict[str, dict[str, Any]] = {}

        for event in api_events:
            ep = event.payload.get("endpoint_path", "unknown")

            # Filter by endpoint if specified
            if endpoint_path and ep != endpoint_path:
                continue

            if ep not in endpoints:
                endpoints[ep] = {
                    "requests": 0,
                    "errors": 0,
                    "total_latency_ms": 0,
                    "min_latency_ms": float("inf"),
                    "max_latency_ms": 0,
                }

            endpoints[ep]["requests"] += 1
            if event.payload.get("error"):
                endpoints[ep]["errors"] += 1

            latency = event.payload.get("latency_ms", 0)
            endpoints[ep]["total_latency_ms"] += latency
            endpoints[ep]["min_latency_ms"] = min(endpoints[ep]["min_latency_ms"], latency)
            endpoints[ep]["max_latency_ms"] = max(endpoints[ep]["max_latency_ms"], latency)

        # Calculate averages and error rates
        for ep_metrics in endpoints.values():
            if ep_metrics["requests"] > 0:
                ep_metrics["avg_latency_ms"] = ep_metrics["total_latency_ms"] / ep_metrics["requests"]
                ep_metrics["error_rate"] = ep_metrics["errors"] / ep_metrics["requests"]
            else:
                ep_metrics["avg_latency_ms"] = 0
                ep_metrics["error_rate"] = 0

            # Clean up temporary values
            ep_metrics.pop("total_latency_ms", None)

        return endpoints if endpoints else {}

    async def get_agent_execution_metrics(
        self,
        agent_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
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
            start_time = datetime.now(UTC) - timedelta(hours=1)
        if end_time is None:
            end_time = datetime.now(UTC)

        logger.debug(
            f"Getting agent execution metrics for {agent_name or 'all agents'} from {start_time} to {end_time}"
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
            execution_events = [e for e in execution_events if e.payload.get("agent_name") == agent_name]
            completed_events = [e for e in completed_events if e.payload.get("agent_name") == agent_name]
            failed_events = [e for e in failed_events if e.payload.get("agent_name") == agent_name]

        # Calculate metrics
        total_executions = len(execution_events)
        total_completed = len(completed_events)
        total_failed = len(failed_events)
        total_active = total_executions - total_completed - total_failed

        success_rate = total_completed / total_executions if total_executions > 0 else 0.0

        # Calculate duration stats from completed executions
        durations = [e.payload["duration_seconds"] for e in completed_events if "duration_seconds" in e.payload]

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

    async def get_active_agents(self) -> dict[str, Any]:
        """
        Get currently active agent executions.

        Returns:
            Dict containing list of active agents with execution info
        """
        logger.debug("Getting active agents")

        # Query for recent execution started events
        recent_time = datetime.now(UTC) - timedelta(hours=24)
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
                # Normalize event.occurred_at to aware datetime if needed
                occurred_at = (
                    event.occurred_at if event.occurred_at.tzinfo is not None else event.occurred_at.replace(tzinfo=UTC)
                )
                active_agents.append(
                    {
                        "execution_id": execution_id,
                        "agent_name": event.payload.get("agent_name"),
                        "work_item_id": event.payload.get("work_item_id"),
                        "started_at": occurred_at.isoformat(),
                        "duration_seconds": (datetime.now(UTC) - occurred_at).total_seconds(),
                    }
                )

        return {
            "count": len(active_agents),
            "agents": active_agents,
            "checked_at": datetime.now(UTC).isoformat(),
        }

    async def get_api_usage(self) -> dict[str, Any]:
        """
        Get API usage and quota information.

        Returns:
            Dict with usage statistics for external APIs (Claude, etc.)
        """
        logger.debug("Getting API usage")

        # Query LLM execution events to calculate token usage
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        llm_events = await self.event_store.get_events_by_type(
            event_type="AgentExecutionCompleted",
            since=today,
            limit=10000,
        )

        # Calculate token usage
        input_tokens_today = sum(e.payload.get("input_tokens", 0) for e in llm_events)
        output_tokens_today = sum(e.payload.get("output_tokens", 0) for e in llm_events)
        total_tokens_today = input_tokens_today + output_tokens_today

        # Estimate cost (simplified - $0.003 per 1K input tokens, $0.015 per 1K output tokens)
        estimated_cost = (input_tokens_today / 1000 * 0.003) + (output_tokens_today / 1000 * 0.015)

        return {
            "claude_api": {
                "requests_today": len(llm_events),
                "tokens_input_today": input_tokens_today,
                "tokens_output_today": output_tokens_today,
                "tokens_total_today": total_tokens_today,
                "quota_remaining": None,  # Would be provided by Claude API
                "quota_reset_time": None,
                "estimated_cost_usd": round(estimated_cost, 4),
            },
            "github_api": {
                "requests_remaining": None,  # Would be checked from GitHub API response headers
                "quota_limit": None,
                "quota_reset_time": None,
            },
            "checked_at": datetime.now(UTC).isoformat(),
        }

    async def get_repair_cycle_metrics(
        self,
        agent_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Get repair cycle metrics.

        Args:
            agent_name: Optional filter by specific agent
            start_time: Start of time range (default: last hour)
            end_time: End of time range (default: now)

        Returns:
            Dict with repair cycle statistics
        """
        if start_time is None:
            start_time = datetime.now(UTC) - timedelta(hours=1)
        if end_time is None:
            end_time = datetime.now(UTC)

        logger.debug(f"Getting repair cycle metrics for {agent_name or 'all agents'} from {start_time} to {end_time}")

        # Query repair cycle events
        started_events = await self.event_store.get_events_by_type(
            event_type="repair_cycle.started",
            since=start_time,
            limit=10000,
        )

        completed_events = await self.event_store.get_events_by_type(
            event_type="repair_cycle.completed",
            since=start_time,
            limit=10000,
        )

        test_execution_events = await self.event_store.get_events_by_type(
            event_type="repair_cycle.test_execution_completed",
            since=start_time,
            limit=10000,
        )

        file_fix_events = await self.event_store.get_events_by_type(
            event_type="repair_cycle.file_fix_completed",
            since=start_time,
            limit=10000,
        )

        warning_review_events = await self.event_store.get_events_by_type(
            event_type="repair_cycle.warning_review_completed",
            since=start_time,
            limit=10000,
        )

        fast_fail_events = await self.event_store.get_events_by_type(
            event_type="repair_cycle.fast_fail",
            since=start_time,
            limit=10000,
        )

        # Filter by agent if specified
        if agent_name:
            started_events = [e for e in started_events if e.payload.get("agent_name") == agent_name]
            completed_events = [e for e in completed_events if e.payload.get("agent_name") == agent_name]
            test_execution_events = [e for e in test_execution_events if e.payload.get("agent_name") == agent_name]
            file_fix_events = [e for e in file_fix_events if e.payload.get("agent_name") == agent_name]
            warning_review_events = [e for e in warning_review_events if e.payload.get("agent_name") == agent_name]
            fast_fail_events = [e for e in fast_fail_events if e.payload.get("agent_name") == agent_name]

        # Calculate basic counts
        cycles_started = len(started_events)
        cycles_completed = len(completed_events)
        cycles_fast_failed = len(fast_fail_events)

        cycles_successful = 0
        cycles_failed = 0
        durations = []
        agent_calls = []

        for event in completed_events:
            if event.payload.get("overall_success"):
                cycles_successful += 1
            else:
                cycles_failed += 1

            duration = event.payload.get("duration_seconds", 0)
            if duration:
                durations.append(duration)

            agent_calls_count = event.payload.get("total_agent_calls", 0)
            if agent_calls_count:
                agent_calls.append(agent_calls_count)

        # Calculate per-test-type metrics
        test_types: dict[str, dict[str, int]] = {}
        for event in test_execution_events:
            test_type = event.payload.get("test_type", "unknown")
            if test_type not in test_types:
                test_types[test_type] = {"executions": 0, "iterations": 0}
            test_types[test_type]["executions"] += 1

        for event in completed_events:
            # Get total iterations from the completion event
            total_iterations = event.payload.get("total_iterations", 0)
            # Distribute across test types (this is approximate)
            if total_iterations > 0 and test_types:
                iterations_per_type = total_iterations // len(test_types)
                for test_type in test_types:
                    test_types[test_type]["iterations"] += iterations_per_type

        # Calculate file fix metrics
        files_fixed: dict[str, int] = {}
        files_fixed_total = 0
        for event in file_fix_events:
            if event.payload.get("fixed"):
                file_path = event.payload.get("file_path", "unknown")
                files_fixed[file_path] = files_fixed.get(file_path, 0) + 1
                files_fixed_total += 1

        # Calculate warning metrics
        warnings_reviewed_total = sum(event.payload.get("warnings_reviewed", 0) for event in warning_review_events)

        # Calculate per-agent metrics
        agents: dict[str, dict[str, int]] = {}
        for event in started_events:
            agent = event.payload.get("agent_name", "unknown")
            if agent not in agents:
                agents[agent] = {
                    "started": 0,
                    "completed": 0,
                    "successful": 0,
                    "failed": 0,
                    "fast_failed": 0,
                }
            agents[agent]["started"] += 1

        for event in completed_events:
            agent = event.payload.get("agent_name", "unknown")
            if agent not in agents:
                agents[agent] = {
                    "started": 0,
                    "completed": 0,
                    "successful": 0,
                    "failed": 0,
                    "fast_failed": 0,
                }
            agents[agent]["completed"] += 1
            if event.payload.get("overall_success"):
                agents[agent]["successful"] += 1
            else:
                agents[agent]["failed"] += 1

        for event in fast_fail_events:
            agent = event.payload.get("agent_name", "unknown")
            if agent not in agents:
                agents[agent] = {
                    "started": 0,
                    "completed": 0,
                    "successful": 0,
                    "failed": 0,
                    "fast_failed": 0,
                }
            agents[agent]["fast_failed"] += 1

        # Calculate averages
        avg_duration = sum(durations) / len(durations) if durations else None
        avg_agent_calls = sum(agent_calls) / len(agent_calls) if agent_calls else None

        return {
            "cycles_started": cycles_started,
            "cycles_completed": cycles_completed,
            "cycles_successful": cycles_successful,
            "cycles_failed": cycles_failed,
            "cycles_fast_failed": cycles_fast_failed,
            "durations": durations,
            "test_types": test_types,
            "agents": agents,
            "files_fixed": files_fixed,
            "files_fixed_total": files_fixed_total,
            "warnings_reviewed_total": warnings_reviewed_total,
            "avg_duration_seconds": avg_duration,
            "avg_agent_calls_per_cycle": avg_agent_calls,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        }

    # Private helper methods

    async def _check_event_store_health(self) -> ComponentHealthInfo:
        """
        Check event store health.

        Returns:
            Component health info for event store
        """
        check_start = datetime.now(UTC)

        try:
            # Attempt to get stats from event store
            stats = await self.event_store.get_statistics()

            response_time_ms = (datetime.now(UTC) - check_start).total_seconds() * 1000

            return ComponentHealthInfo(
                component_name="event_store",
                status=ComponentHealth.HEALTHY,
                message="Event store is operational",
                last_check=datetime.now(UTC),
                response_time_ms=response_time_ms,
                details=stats,
            )

        except Exception as e:
            response_time_ms = (datetime.now(UTC) - check_start).total_seconds() * 1000

            return ComponentHealthInfo(
                component_name="event_store",
                status=ComponentHealth.UNHEALTHY,
                message=f"Event store health check failed: {e}",
                last_check=datetime.now(UTC),
                response_time_ms=response_time_ms,
                details={"error": str(e)},
            )
