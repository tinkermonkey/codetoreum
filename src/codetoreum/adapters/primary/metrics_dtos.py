"""
Metrics DTOs

Data Transfer Objects for metrics and system health API endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Request DTOs
# ============================================================================


class MetricsQueryRequest(BaseModel):
    """Request to query metrics"""
    start_time: Optional[datetime] = Field(None, description="Start of time range (default: last hour)")
    end_time: Optional[datetime] = Field(None, description="End of time range (default: now)")
    aggregation_window_seconds: int = Field(60, ge=1, le=3600, description="Aggregation window in seconds")


class TimeSeriesQueryRequest(BaseModel):
    """Request to query time series data"""
    metric_name: str = Field(..., description="Metric name to query")
    start_time: datetime = Field(..., description="Start of time range")
    end_time: datetime = Field(..., description="End of time range")
    labels: Optional[Dict[str, str]] = Field(None, description="Optional label filters")
    aggregation: Optional[str] = Field(None, description="Aggregation function (sum, avg, min, max, p95, p99)")


# ============================================================================
# Response DTOs
# ============================================================================


class ComponentHealthResponse(BaseModel):
    """Component health information"""
    component_name: str
    status: str  # healthy, degraded, unhealthy, unknown
    message: Optional[str]
    last_check: datetime
    response_time_ms: Optional[float]
    details: Dict[str, Any]


class SystemHealthResponse(BaseModel):
    """System health response"""
    status: str  # healthy, degraded, unhealthy
    components: List[ComponentHealthResponse]
    checked_at: datetime
    uptime_seconds: float
    version: str


class PerformanceMetricsResponse(BaseModel):
    """Performance metrics response"""
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
    queue_processing_rate: float

    # Time range
    start_time: datetime
    end_time: datetime
    aggregation_window_seconds: int


class CircuitBreakerInfo(BaseModel):
    """Circuit breaker status"""
    service_name: str
    state: str  # closed, open, half_open
    failure_count: int
    success_count: int
    last_failure: Optional[datetime]
    opened_at: Optional[datetime]


class ActiveAgentResponse(BaseModel):
    """Active agent execution information"""
    executionId: str = Field(..., description="Execution ID", serialization_alias="executionId")
    agentName: str = Field(..., description="Agent name", serialization_alias="agentName")
    workItemId: str = Field(..., description="Work item ID", serialization_alias="workItemId")
    project: str = Field(..., description="Project name")
    issueNumber: Optional[int] = Field(None, description="Issue number", serialization_alias="issueNumber")
    status: str = Field(..., description="Execution status")
    startedAt: datetime = Field(..., description="Start time", serialization_alias="startedAt")
    containerName: Optional[str] = Field(None, description="Container name", serialization_alias="containerName")


class ActiveAgentsResponse(BaseModel):
    """Active agents list response"""
    agents: List[ActiveAgentResponse] = Field(..., description="List of active agents")
    count: int = Field(..., description="Total count of active agents")


class ApiUsageQuotaResponse(BaseModel):
    """API usage quota information"""
    available: bool = Field(..., description="Whether API is available")
    weeklyUsage: int = Field(..., description="Weekly usage in tokens", serialization_alias="weeklyUsage")
    weeklyQuota: int = Field(..., description="Weekly quota in tokens", serialization_alias="weeklyQuota")
    weeklyUsagePercent: float = Field(..., description="Weekly usage percentage", serialization_alias="weeklyUsagePercent")
    sessionUsage: int = Field(..., description="Session usage in tokens", serialization_alias="sessionUsage")
    sessionQuota: int = Field(..., description="Session quota in tokens", serialization_alias="sessionQuota")
    sessionUsagePercent: float = Field(..., description="Session usage percentage", serialization_alias="sessionUsagePercent")
    sessionRemainingMinutes: Optional[int] = Field(None, description="Session remaining minutes", serialization_alias="sessionRemainingMinutes")


class ApiUsageResponse(BaseModel):
    """API usage response"""
    claude: ApiUsageQuotaResponse = Field(..., description="Claude API usage")


class RateLimitInfo(BaseModel):
    """Rate limit information"""
    remaining: int = Field(..., description="Remaining requests")
    limit: int = Field(..., description="Request limit")
    percentageUsed: float = Field(..., description="Percentage used", serialization_alias="percentageUsed")


class CircuitBreakerStatusResponse(BaseModel):
    """Circuit breaker status"""
    name: str = Field(..., description="Circuit breaker name")
    state: str = Field(..., description="State (closed, open, half_open)")
    failureCount: int = Field(..., description="Failure count", serialization_alias="failureCount")
    successCount: int = Field(..., description="Success count", serialization_alias="successCount")
    totalRejected: int = Field(..., description="Total rejected requests", serialization_alias="totalRejected")
    lastFailure: Optional[datetime] = Field(None, description="Last failure time", serialization_alias="lastFailure")
    rateLimit: Optional[RateLimitInfo] = Field(None, description="Rate limit information", serialization_alias="rateLimit")


class ComponentHealthCheck(BaseModel):
    """Component health check result"""
    healthy: bool = Field(..., description="Health status")
    message: str = Field(..., description="Status message")
    lastCheck: datetime = Field(..., description="Last check time", serialization_alias="lastCheck")
    freeGb: Optional[float] = Field(None, description="Free GB (for disk)", serialization_alias="freeGb")
    usagePercent: Optional[float] = Field(..., description="Usage percentage", serialization_alias="usagePercent")
    availableGb: Optional[float] = Field(None, description="Available GB (for memory)", serialization_alias="availableGb")


class HealthCheckResponse(BaseModel):
    """Enhanced health check response"""
    status: str = Field(..., description="Overall health status")
    checks: Dict[str, ComponentHealthCheck] = Field(..., description="Component health checks")
    circuitBreakers: List[CircuitBreakerStatusResponse] = Field(default_factory=list, description="Circuit breaker statuses", serialization_alias="circuitBreakers")


class RateLimiterInfo(BaseModel):
    """Rate limiter status"""
    resource_name: str
    requests_count: int
    limit: int
    window_seconds: int
    utilization_percent: float
    rejected_count: int


class ResilienceMetricsResponse(BaseModel):
    """Resilience metrics response"""
    circuit_breakers: List[CircuitBreakerInfo]
    rate_limiters: List[RateLimiterInfo]
    retry_attempts_total: int
    retry_successes_total: int
    retry_failures_total: int
    timeout_count: int
    avg_timeout_duration_ms: float
    start_time: datetime
    end_time: datetime


class IntegrationStatusResponse(BaseModel):
    """Integration status response"""
    # GitHub
    github_connected: bool
    github_api_calls_remaining: Optional[int]
    github_rate_limit_reset: Optional[datetime]
    github_webhook_health: str

    # Docker
    docker_connected: bool
    docker_version: Optional[str]
    docker_containers_running: int

    # Event store
    event_store_connected: bool
    event_store_latency_ms: Optional[float]

    # Config store
    config_store_connected: bool
    config_store_latency_ms: Optional[float]

    checked_at: datetime


class SimulationModeResponse(BaseModel):
    """Simulation mode information"""
    enabled: bool
    time_multiplier: float
    deterministic_responses: bool
    mock_external_services: bool
    event_replay_enabled: bool
    current_simulation_time: Optional[datetime]
    started_at: Optional[datetime]


class MetricTimeSeriesPoint(BaseModel):
    """Time series data point"""
    timestamp: datetime
    value: float
    labels: Dict[str, str]


class MetricTimeSeriesResponse(BaseModel):
    """Time series response"""
    metric_name: str
    data_points: List[MetricTimeSeriesPoint]
    aggregation: Optional[str]
    start_time: datetime
    end_time: datetime


class MetricNamesResponse(BaseModel):
    """List of metric names"""
    metric_names: List[str]
    total_count: int


class EndpointMetricsItem(BaseModel):
    """Per-endpoint metrics"""
    endpoint_path: str
    request_count: int
    error_count: int
    error_rate_percent: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float


class EndpointMetricsResponse(BaseModel):
    """API endpoint metrics response"""
    endpoints: List[EndpointMetricsItem]
    total_requests: int
    total_errors: int
    overall_error_rate_percent: float
    start_time: datetime
    end_time: datetime


class AgentExecutionMetricsItem(BaseModel):
    """Per-agent execution metrics"""
    agent_name: str
    execution_count: int
    success_count: int
    failure_count: int
    success_rate_percent: float
    avg_duration_seconds: float
    p95_duration_seconds: float


class AgentExecutionMetricsResponse(BaseModel):
    """Agent execution metrics response"""
    agents: List[AgentExecutionMetricsItem]
    total_executions: int
    overall_success_rate_percent: float
    start_time: datetime
    end_time: datetime
