"""
Metrics REST API Router

Provides RESTful endpoints for system metrics, health checks, performance statistics,
and resilience infrastructure monitoring.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from codetoreum.adapters.primary.metrics_dtos import (
    ActiveAgentResponse,
    ActiveAgentsResponse,
    AgentExecutionMetricsResponse,
    ApiUsageQuotaResponse,
    ApiUsageResponse,
    EndpointMetricsResponse,
    IntegrationStatusResponse,
    MetricNamesResponse,
    PerformanceMetricsResponse,
    RepairCycleMetricsResponse,
    ResilienceMetricsResponse,
    SimulationModeResponse,
    SystemHealthResponse,
)
from codetoreum.adapters.primary.simple_auth_dependencies import SimpleAuthDependencies
from codetoreum.config import (
    DEFAULT_METRICS_AGGREGATION_WINDOW_SECONDS,
    MAX_METRICS_AGGREGATION_WINDOW_SECONDS,
    MIN_METRICS_AGGREGATION_WINDOW_SECONDS,
)
from codetoreum.ports.input.metrics_query import IMetricsQueryPort


def create_metrics_router(
    metrics_query_port: IMetricsQueryPort,
    auth_deps: SimpleAuthDependencies | None = None,
) -> APIRouter:
    """
    Create the metrics REST API router.

    Args:
        metrics_query_port: Metrics query input port
        auth_deps: Optional authentication dependencies (health endpoint is public)

    Returns:
        Configured APIRouter for metrics
    """
    router = APIRouter(
        prefix="/api/v2/metrics",
        tags=["metrics"],
    )

    # ========================================================================
    # Health Check (Public - No Authentication)
    # ========================================================================

    @router.get(
        "/health",
        response_model=SystemHealthResponse,
        summary="System health check",
        response_description="System health status",
    )
    async def get_system_health() -> SystemHealthResponse:
        """
        Get system health status.

        This endpoint does NOT require authentication and can be used for
        monitoring and load balancer health checks.

        Checks connectivity and health of:
        - Event store (Redis/Elasticsearch)
        - Config store (database)
        - GitHub API
        - Docker runtime
        - LLM provider (if configured)

        **Returns:**
        - 200 OK: System is healthy or degraded (still functional)
        - 503 Service Unavailable: System is unhealthy (critical component down)

        **Example Response:**
        ```json
        {
          "status": "healthy",
          "components": [
            {
              "component_name": "event_store",
              "status": "healthy",
              "message": "Connected",
              "last_check": "2025-11-04T10:30:00Z",
              "response_time_ms": 5.2,
              "details": {}
            },
            ...
          ],
          "checked_at": "2025-11-04T10:30:00Z",
          "uptime_seconds": 3600.5,
          "version": "2.0.0"
        }
        ```
        """
        try:
            health_info = await metrics_query_port.get_system_health()

            response = SystemHealthResponse(
                status=health_info.status.value,
                components=[
                    {
                        "component_name": c.component_name,
                        "status": c.status.value,
                        "message": c.message,
                        "last_check": c.last_check,
                        "response_time_ms": c.response_time_ms,
                        "details": c.details,
                    }
                    for c in health_info.components
                ],
                checked_at=health_info.checked_at,
                uptime_seconds=health_info.uptime_seconds,
                version=health_info.version,
            )

            # Return 503 if system is unhealthy
            if health_info.status.value == "unhealthy":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="System unhealthy - critical component failure",
                )

            return response

        except HTTPException:
            raise
        except Exception as e:
            # If health check itself fails, return 503
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Health check failed: {e!s}",
            )

    # ========================================================================
    # Performance Metrics (Authenticated)
    # ========================================================================

    # Apply authentication to remaining endpoints if auth_deps provided
    auth_dependency = [Depends(auth_deps.require_auth)] if auth_deps else []

    @router.get(
        "",
        response_model=PerformanceMetricsResponse,
        summary="Get performance metrics",
        response_description="Aggregated performance metrics",
        dependencies=auth_dependency,
    )
    async def get_performance_metrics(
        start_time: datetime | None = Query(None, description="Start of time range (default: last hour)"),
        end_time: datetime | None = Query(None, description="End of time range (default: now)"),
        aggregation_window_seconds: int = Query(
            DEFAULT_METRICS_AGGREGATION_WINDOW_SECONDS,
            ge=MIN_METRICS_AGGREGATION_WINDOW_SECONDS,
            le=MAX_METRICS_AGGREGATION_WINDOW_SECONDS,
            description=f"Aggregation window in seconds (min {MIN_METRICS_AGGREGATION_WINDOW_SECONDS}, max {MAX_METRICS_AGGREGATION_WINDOW_SECONDS})"
        ),
    ) -> PerformanceMetricsResponse:
        """
        Get performance metrics over a time range.

        Returns aggregated metrics including:
        - API request counts and latency percentiles (p50, p95, p99)
        - Execution statistics (active, pending, completed, failed)
        - Resource usage (CPU, memory, container counts)
        - Queue depth and processing rate

        **Query Parameters:**
        - start_time: Start of time range (default: 1 hour ago)
        - end_time: End of time range (default: now)
        - aggregation_window_seconds: Aggregation window (default: 60s)

        **Returns:**
        - 200 OK: Performance metrics
        - 401 Unauthorized: Authentication required

        **Performance Targets:**
        - API latency p95 < 200ms
        - Execution queue depth < 100
        - Container CPU usage < 80%
        """
        try:
            # Default to last hour if not specified
            if not end_time:
                end_time = datetime.now(UTC)
            if not start_time:
                start_time = end_time - timedelta(hours=1)

            metrics = await metrics_query_port.get_performance_metrics(
                start_time=start_time,
                end_time=end_time,
                aggregation_window_seconds=aggregation_window_seconds,
            )

            return PerformanceMetricsResponse(
                api_request_count=metrics.api_request_count,
                api_error_count=metrics.api_error_count,
                api_latency_p50_ms=metrics.api_latency_p50_ms,
                api_latency_p95_ms=metrics.api_latency_p95_ms,
                api_latency_p99_ms=metrics.api_latency_p99_ms,
                active_executions=metrics.active_executions,
                pending_executions=metrics.pending_executions,
                completed_executions_total=metrics.completed_executions_total,
                failed_executions_total=metrics.failed_executions_total,
                avg_execution_duration_seconds=metrics.avg_execution_duration_seconds,
                active_containers=metrics.active_containers,
                container_cpu_usage_percent=metrics.container_cpu_usage_percent,
                container_memory_usage_mb=metrics.container_memory_usage_mb,
                queue_depth=metrics.queue_depth,
                queue_processing_rate=metrics.queue_processing_rate,
                start_time=metrics.start_time,
                end_time=metrics.end_time,
                aggregation_window_seconds=metrics.aggregation_window_seconds,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve performance metrics: {e!s}",
            )

    # ========================================================================
    # Resilience Metrics
    # ========================================================================

    @router.get(
        "/resilience",
        response_model=ResilienceMetricsResponse,
        summary="Get resilience infrastructure metrics",
        response_description="Circuit breaker and rate limiter stats",
        dependencies=auth_dependency,
    )
    async def get_resilience_metrics(
        start_time: datetime | None = Query(None, description="Start of time range (default: last hour)"),
        end_time: datetime | None = Query(None, description="End of time range (default: now)"),
    ) -> ResilienceMetricsResponse:
        """
        Get resilience infrastructure metrics.

        Returns circuit breaker states, rate limiter utilization,
        retry statistics, and timeout information.

        **Query Parameters:**
        - start_time: Start of time range (default: 1 hour ago)
        - end_time: End of time range (default: now)

        **Returns:**
        - 200 OK: Resilience metrics
        - 401 Unauthorized: Authentication required

        **Metrics Include:**
        - Circuit breaker states (closed, open, half_open) per service
        - Rate limiter utilization and rejection counts
        - Retry attempt success/failure rates
        - Timeout counts and average durations
        """
        try:
            # Default to last hour
            if not end_time:
                end_time = datetime.now(UTC)
            if not start_time:
                start_time = end_time - timedelta(hours=1)

            metrics = await metrics_query_port.get_resilience_metrics(
                start_time=start_time,
                end_time=end_time,
            )

            return ResilienceMetricsResponse(
                circuit_breakers=[
                    {
                        "service_name": name,
                        "state": info.get("state", "unknown"),
                        "failure_count": info.get("failure_count", 0),
                        "success_count": info.get("success_count", 0),
                        "last_failure": info.get("last_failure"),
                        "opened_at": info.get("opened_at"),
                    }
                    for name, info in metrics.circuit_breakers.items()
                ],
                rate_limiters=[
                    {
                        "resource_name": name,
                        "requests_count": info.get("requests_count", 0),
                        "limit": info.get("limit", 0),
                        "window_seconds": info.get("window_seconds", 60),
                        "utilization_percent": info.get("utilization_percent", 0.0),
                        "rejected_count": info.get("rejected_count", 0),
                    }
                    for name, info in metrics.rate_limiters.items()
                ],
                retry_attempts_total=metrics.retry_attempts_total,
                retry_successes_total=metrics.retry_successes_total,
                retry_failures_total=metrics.retry_failures_total,
                timeout_count=metrics.timeout_count,
                avg_timeout_duration_ms=metrics.avg_timeout_duration_ms,
                start_time=metrics.start_time,
                end_time=metrics.end_time,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve resilience metrics: {e!s}",
            )

    # ========================================================================
    # Integration Status
    # ========================================================================

    @router.get(
        "/integrations",
        response_model=IntegrationStatusResponse,
        summary="Get external integration status",
        response_description="Status of external system integrations",
        dependencies=auth_dependency,
    )
    async def get_integration_status() -> IntegrationStatusResponse:
        """
        Get status of external system integrations.

        Checks connectivity and health of:
        - GitHub API (rate limits, webhook health)
        - Docker runtime (version, running containers)
        - Event store (latency)
        - Config store (latency)

        **Returns:**
        - 200 OK: Integration status
        - 401 Unauthorized: Authentication required

        **Example Response:**
        ```json
        {
          "github_connected": true,
          "github_api_calls_remaining": 4500,
          "github_rate_limit_reset": "2025-11-04T11:00:00Z",
          "docker_connected": true,
          "docker_version": "24.0.7",
          "docker_containers_running": 3,
          ...
        }
        ```
        """
        try:
            status_info = await metrics_query_port.get_integration_status()

            return IntegrationStatusResponse(
                github_connected=status_info.github_connected,
                github_api_calls_remaining=status_info.github_api_calls_remaining,
                github_rate_limit_reset=status_info.github_rate_limit_reset,
                github_webhook_health=status_info.github_webhook_health.value,
                docker_connected=status_info.docker_connected,
                docker_version=status_info.docker_version,
                docker_containers_running=status_info.docker_containers_running,
                event_store_connected=status_info.event_store_connected,
                event_store_latency_ms=status_info.event_store_latency_ms,
                config_store_connected=status_info.config_store_connected,
                config_store_latency_ms=status_info.config_store_latency_ms,
                checked_at=status_info.checked_at,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve integration status: {e!s}",
            )

    # ========================================================================
    # Simulation Mode
    # ========================================================================

    @router.get(
        "/simulation",
        response_model=SimulationModeResponse,
        summary="Get simulation mode status",
        response_description="Simulation mode configuration",
        dependencies=auth_dependency,
    )
    async def get_simulation_mode_info() -> SimulationModeResponse:
        """
        Get simulation mode status and configuration.

        Simulation mode is used for testing and enables:
        - Time manipulation (fast-forward simulation)
        - Deterministic LLM responses
        - Mock external services
        - Event replay for debugging

        **Returns:**
        - 200 OK: Simulation mode information
        - 401 Unauthorized: Authentication required

        **Example Response:**
        ```json
        {
          "enabled": false,
          "time_multiplier": 1.0,
          "deterministic_responses": false,
          "mock_external_services": false,
          "event_replay_enabled": false
        }
        ```
        """
        try:
            sim_info = await metrics_query_port.get_simulation_mode_info()

            return SimulationModeResponse(
                enabled=sim_info.enabled,
                time_multiplier=sim_info.time_multiplier,
                deterministic_responses=sim_info.deterministic_responses,
                mock_external_services=sim_info.mock_external_services,
                event_replay_enabled=sim_info.event_replay_enabled,
                current_simulation_time=sim_info.current_simulation_time,
                started_at=sim_info.started_at,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve simulation mode info: {e!s}",
            )

    # ========================================================================
    # Detailed Metrics
    # ========================================================================

    @router.get(
        "/endpoints",
        response_model=EndpointMetricsResponse,
        summary="Get per-endpoint API metrics",
        response_description="API endpoint performance metrics",
        dependencies=auth_dependency,
    )
    async def get_endpoint_metrics(
        endpoint_path: str | None = Query(None, description="Filter by specific endpoint"),
        start_time: datetime | None = Query(None, description="Start of time range (default: last hour)"),
        end_time: datetime | None = Query(None, description="End of time range (default: now)"),
    ) -> EndpointMetricsResponse:
        """
        Get per-endpoint API metrics.

        Returns request counts, error rates, and latency percentiles
        for each API endpoint.

        **Query Parameters:**
        - endpoint_path: Optional filter by specific endpoint
        - start_time: Start of time range (default: 1 hour ago)
        - end_time: End of time range (default: now)

        **Returns:**
        - 200 OK: Endpoint metrics
        - 401 Unauthorized: Authentication required
        """
        try:
            # Default to last hour
            if not end_time:
                end_time = datetime.now(UTC)
            if not start_time:
                start_time = end_time - timedelta(hours=1)

            metrics_dict = await metrics_query_port.get_api_endpoint_metrics(
                endpoint_path=endpoint_path,
                start_time=start_time,
                end_time=end_time,
            )

            endpoints = []
            total_requests = 0
            total_errors = 0

            for path, metrics in metrics_dict.get("endpoints", {}).items():
                req_count = metrics.get("request_count", 0)
                err_count = metrics.get("error_count", 0)

                endpoints.append({
                    "endpoint_path": path,
                    "request_count": req_count,
                    "error_count": err_count,
                    "error_rate_percent": (err_count / req_count * 100) if req_count > 0 else 0.0,
                    "latency_p50_ms": metrics.get("latency_p50_ms", 0.0),
                    "latency_p95_ms": metrics.get("latency_p95_ms", 0.0),
                    "latency_p99_ms": metrics.get("latency_p99_ms", 0.0),
                })

                total_requests += req_count
                total_errors += err_count

            return EndpointMetricsResponse(
                endpoints=endpoints,
                total_requests=total_requests,
                total_errors=total_errors,
                overall_error_rate_percent=(total_errors / total_requests * 100) if total_requests > 0 else 0.0,
                start_time=start_time,
                end_time=end_time,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve endpoint metrics: {e!s}",
            )

    @router.get(
        "/agents",
        response_model=AgentExecutionMetricsResponse,
        summary="Get agent execution metrics",
        response_description="Per-agent execution statistics",
        dependencies=auth_dependency,
    )
    async def get_agent_execution_metrics(
        agent_name: str | None = Query(None, description="Filter by specific agent"),
        start_time: datetime | None = Query(None, description="Start of time range (default: last hour)"),
        end_time: datetime | None = Query(None, description="End of time range (default: now)"),
    ) -> AgentExecutionMetricsResponse:
        """
        Get agent execution metrics.

        Returns execution counts, success rates, and duration statistics
        for each agent.

        **Query Parameters:**
        - agent_name: Optional filter by specific agent
        - start_time: Start of time range (default: 1 hour ago)
        - end_time: End of time range (default: now)

        **Returns:**
        - 200 OK: Agent execution metrics
        - 401 Unauthorized: Authentication required
        """
        try:
            # Default to last hour
            if not end_time:
                end_time = datetime.now(UTC)
            if not start_time:
                start_time = end_time - timedelta(hours=1)

            metrics_dict = await metrics_query_port.get_agent_execution_metrics(
                agent_name=agent_name,
                start_time=start_time,
                end_time=end_time,
            )

            agents = []
            total_executions = 0
            total_successes = 0

            for name, metrics in metrics_dict.get("agents", {}).items():
                exec_count = metrics.get("execution_count", 0)
                success_count = metrics.get("success_count", 0)
                failure_count = metrics.get("failure_count", 0)

                agents.append({
                    "agent_name": name,
                    "execution_count": exec_count,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "success_rate_percent": (success_count / exec_count * 100) if exec_count > 0 else 0.0,
                    "avg_duration_seconds": metrics.get("avg_duration_seconds", 0.0),
                    "p95_duration_seconds": metrics.get("p95_duration_seconds", 0.0),
                })

                total_executions += exec_count
                total_successes += success_count

            return AgentExecutionMetricsResponse(
                agents=agents,
                total_executions=total_executions,
                overall_success_rate_percent=(total_successes / total_executions * 100) if total_executions > 0 else 0.0,
                start_time=start_time,
                end_time=end_time,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve agent execution metrics: {e!s}",
            )

    # ========================================================================
    # Metric Names
    # ========================================================================

    @router.get(
        "/names",
        response_model=MetricNamesResponse,
        summary="List available metrics",
        response_description="List of metric names",
        dependencies=auth_dependency,
    )
    async def list_metric_names(
        prefix: str | None = Query(None, description="Filter by prefix"),
    ) -> MetricNamesResponse:
        """
        List available metric names.

        Useful for discovering available metrics for custom queries.

        **Query Parameters:**
        - prefix: Optional prefix filter (e.g., "api." for API metrics)

        **Returns:**
        - 200 OK: List of metric names
        - 401 Unauthorized: Authentication required
        """
        try:
            names = await metrics_query_port.list_metric_names(prefix=prefix)

            return MetricNamesResponse(
                metric_names=names,
                total_count=len(names),
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list metric names: {e!s}",
            )

    # ========================================================================
    # Active Agents
    # ========================================================================

    @router.get(
        "/active-agents",
        response_model=ActiveAgentsResponse,
        summary="Get currently active agents",
        response_description="List of active agent executions",
        dependencies=auth_dependency,
    )
    async def get_active_agents() -> ActiveAgentsResponse:
        """
        Get list of currently active agent executions.

        Returns information about agents that are currently running,
        including their execution ID, agent name, work item, and container.

        **Returns:**
        - 200 OK: List of active agents
        - 401 Unauthorized: Authentication required

        **Example Response:**
        ```json
        {
          "agents": [
            {
              "executionId": "exec-123",
              "agentName": "developer_agent",
              "workItemId": "wi-456",
              "project": "codetoreum",
              "issueNumber": 42,
              "status": "running",
              "startedAt": "2026-02-20T10:00:00Z",
              "containerName": "claude-code-exec-123"
            }
          ],
          "count": 1
        }
        ```
        """
        try:
            # Get active executions from metrics query port
            # This would typically query the execution tracking system
            active_agents_data = await metrics_query_port.get_active_agents()

            agents = []
            for agent_data in active_agents_data.get("agents", []):
                agents.append(ActiveAgentResponse(
                    executionId=agent_data.get("execution_id", ""),
                    agentName=agent_data.get("agent_name", ""),
                    workItemId=agent_data.get("work_item_id", ""),
                    project=agent_data.get("project", ""),
                    issueNumber=agent_data.get("issue_number"),
                    status=agent_data.get("status", "unknown"),
                    startedAt=agent_data.get("started_at", datetime.now(UTC)),
                    containerName=agent_data.get("container_name"),
                ))

            return ActiveAgentsResponse(
                agents=agents,
                count=len(agents),
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve active agents: {e!s}",
            )

    # ========================================================================
    # API Usage
    # ========================================================================

    @router.get(
        "/api-usage",
        response_model=ApiUsageResponse,
        summary="Get API usage and quotas",
        response_description="API usage information for Claude and other services",
        dependencies=auth_dependency,
    )
    async def get_api_usage() -> ApiUsageResponse:
        """
        Get API usage and quota information.

        Returns usage statistics for Claude API and other external services,
        including weekly/session usage, quotas, and remaining time.

        **Returns:**
        - 200 OK: API usage information
        - 401 Unauthorized: Authentication required

        **Example Response:**
        ```json
        {
          "claude": {
            "available": true,
            "weeklyUsage": 15000000,
            "weeklyQuota": 50000000,
            "weeklyUsagePercent": 30.0,
            "sessionUsage": 2000000,
            "sessionQuota": 10000000,
            "sessionUsagePercent": 20.0,
            "sessionRemainingMinutes": 45
          }
        }
        ```
        """
        try:
            # Get API usage from metrics query port
            # This would typically query the Claude API usage tracking
            usage_data = await metrics_query_port.get_api_usage()

            claude_usage = usage_data.get("claude", {})
            weekly_usage = claude_usage.get("weekly_usage", 0)
            weekly_quota = claude_usage.get("weekly_quota", 1)
            session_usage = claude_usage.get("session_usage", 0)
            session_quota = claude_usage.get("session_quota", 1)

            return ApiUsageResponse(
                claude=ApiUsageQuotaResponse(
                    available=claude_usage.get("available", False),
                    weeklyUsage=weekly_usage,
                    weeklyQuota=weekly_quota,
                    weeklyUsagePercent=round((weekly_usage / weekly_quota) * 100, 1) if weekly_quota > 0 else 0.0,
                    sessionUsage=session_usage,
                    sessionQuota=session_quota,
                    sessionUsagePercent=round((session_usage / session_quota) * 100, 1) if session_quota > 0 else 0.0,
                    sessionRemainingMinutes=claude_usage.get("session_remaining_minutes"),
                )
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve API usage: {e!s}",
            )

    # ========================================================================
    # Repair Cycle Metrics
    # ========================================================================

    @router.get(
        "/repair-cycles",
        response_model=RepairCycleMetricsResponse,
        summary="Get repair cycle metrics",
        response_description="Repair cycle execution statistics",
        dependencies=auth_dependency,
    )
    async def get_repair_cycle_metrics(
        agent_name: str | None = Query(None, description="Filter by specific agent"),
        start_time: datetime | None = Query(None, description="Start of time range (default: last hour)"),
        end_time: datetime | None = Query(None, description="End of time range (default: now)"),
    ) -> RepairCycleMetricsResponse:
        """
        Get repair cycle metrics.

        Returns execution counts, success rates, duration statistics, and
        test-level metrics for repair cycles.

        **Query Parameters:**
        - agent_name: Optional filter by specific agent
        - start_time: Start of time range (default: 1 hour ago)
        - end_time: End of time range (default: now)

        **Returns:**
        - 200 OK: Repair cycle metrics
        - 401 Unauthorized: Authentication required

        **Metrics Include:**
        - Cycle counts (started, completed, successful, failed, fast-failed)
        - Success rates and duration statistics
        - Per-test-type execution metrics (unit, integration, e2e)
        - File fixing statistics
        - Warning review statistics
        - Per-agent metrics breakdown
        """
        try:
            # Default to last hour
            if not end_time:
                end_time = datetime.now(UTC)
            if not start_time:
                start_time = end_time - timedelta(hours=1)

            metrics_dict = await metrics_query_port.get_repair_cycle_metrics(
                agent_name=agent_name,
                start_time=start_time,
                end_time=end_time,
            )

            # Calculate per-test-type metrics
            test_type_metrics = []
            for test_type, test_data in metrics_dict.get("test_types", {}).items():
                executions = test_data.get("executions", 0)
                iterations = test_data.get("iterations", 0)
                avg_iterations = (iterations / executions) if executions > 0 else None

                test_type_metrics.append({
                    "test_type": test_type,
                    "total_executions": executions,
                    "total_iterations": iterations,
                    "avg_iterations_per_cycle": avg_iterations,
                })

            # Calculate overall success rate
            overall_success_rate = None
            completed = metrics_dict.get("cycles_completed", 0)
            successful = metrics_dict.get("cycles_successful", 0)
            if completed > 0:
                overall_success_rate = (successful / completed) * 100

            # Calculate per-agent metrics
            agent_metrics = []
            for agent_name_item, agent_data in metrics_dict.get("agents", {}).items():
                agent_completed = agent_data.get("completed", 0)
                agent_successful = agent_data.get("successful", 0)
                agent_success_rate = (agent_successful / agent_completed * 100) if agent_completed > 0 else None

                agent_metrics.append({
                    "agent_name": agent_name_item,
                    "cycles_started": agent_data.get("started", 0),
                    "cycles_completed": agent_completed,
                    "cycles_successful": agent_successful,
                    "cycles_failed": agent_data.get("failed", 0),
                    "cycles_fast_failed": agent_data.get("fast_failed", 0),
                    "success_rate_percent": agent_success_rate,
                })

            # Calculate duration statistics
            durations = metrics_dict.get("durations", [])
            avg_duration = None
            min_duration = None
            max_duration = None
            if durations:
                avg_duration = sum(durations) / len(durations)
                min_duration = min(durations)
                max_duration = max(durations)

            # Count unique files fixed
            files_fixed_dict = metrics_dict.get("files_fixed", {})
            unique_files = len(files_fixed_dict)

            return RepairCycleMetricsResponse(
                cycles_started=metrics_dict.get("cycles_started", 0),
                cycles_completed=completed,
                cycles_successful=successful,
                cycles_failed=metrics_dict.get("cycles_failed", 0),
                cycles_fast_failed=metrics_dict.get("cycles_fast_failed", 0),
                overall_success_rate_percent=overall_success_rate,
                avg_duration_seconds=avg_duration,
                min_duration_seconds=min_duration,
                max_duration_seconds=max_duration,
                test_type_metrics=test_type_metrics,
                avg_agent_calls_per_cycle=metrics_dict.get("avg_agent_calls_per_cycle"),
                files_fixed_total=metrics_dict.get("files_fixed_total", 0),
                unique_files_fixed=unique_files,
                warnings_reviewed_total=metrics_dict.get("warnings_reviewed_total", 0),
                agent_metrics=agent_metrics,
                start_time=start_time,
                end_time=end_time,
            )

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to retrieve repair cycle metrics: {e!s}",
            )

    return router
