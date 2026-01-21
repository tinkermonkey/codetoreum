"""
Unit tests for Metrics Service.

Tests the metrics service with in-memory event store to verify:
- System health checks
- Performance metrics calculations
- Component health status
- Integration status reporting
- Agent execution metrics
- Active agents tracking
- API usage reporting
- Error handling for missing components
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from codetoreum.adapters.testing.in_memory_event_store import InMemoryEventStore
from codetoreum.application.metrics_service import MetricsService
from codetoreum.domain.events import DomainEvent
from codetoreum.ports.exceptions import ComponentNotFoundError, MetricNotFoundError
from codetoreum.ports.input.metrics_query import ComponentHealth


class MockEvent(DomainEvent):
    """Mock domain event for testing."""

    def __init__(
        self,
        event_type: str,
        aggregate_id: str,
        payload: Dict[str, Any],
        occurred_at: datetime,
    ):
        self.event_type = event_type
        self.aggregate_id = aggregate_id
        self.payload = payload
        self.occurred_at = occurred_at
        self.event_id = f"mock-{aggregate_id}-{event_type}"
        self.correlation_id = "test-correlation-id"
        self.sequence_number = 1

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MockEvent":
        """Create from dict for deserialization."""
        return cls(
            event_type=data["event_type"],
            aggregate_id=data["aggregate_id"],
            payload=data.get("payload", {}),
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "payload": self.payload,
            "occurred_at": self.occurred_at.isoformat(),
        }


@pytest.fixture
async def event_store():
    """Create in-memory event store."""
    store = InMemoryEventStore()
    yield store
    store.clear()


@pytest.fixture
def start_time():
    """Fixture providing service start time."""
    # Use naive datetime to match MetricsService which uses datetime.now()
    return datetime(2024, 1, 1, 12, 0, 0)


@pytest.fixture
async def metrics_service(event_store, start_time):
    """Create metrics service with in-memory event store."""
    return MetricsService(
        event_store=event_store,
        start_time=start_time,
        version="1.0.0-test",
    )


class TestSystemHealth:
    """Tests for system health checks."""

    async def test_get_system_health_healthy(self, metrics_service, event_store):
        """Test system health when all components are healthy."""
        # Act
        health = await metrics_service.get_system_health()

        # Assert
        assert health.status == ComponentHealth.HEALTHY
        assert len(health.components) > 0
        assert health.components[0].component_name == "event_store"
        assert health.components[0].status == ComponentHealth.HEALTHY
        assert health.version == "1.0.0-test"
        assert health.uptime_seconds > 0

    async def test_get_system_health_includes_uptime(
        self, metrics_service, start_time
    ):
        """Test that system health includes correct uptime calculation."""
        # Wait a bit to ensure time has passed
        import asyncio
        await asyncio.sleep(0.1)

        # Act
        health = await metrics_service.get_system_health()

        # Assert
        assert health.uptime_seconds > 0
        # Verify uptime is calculated from start_time
        expected_min_uptime = (datetime.now() - start_time).total_seconds() - 1
        assert health.uptime_seconds >= expected_min_uptime


class TestComponentHealth:
    """Tests for component health checks."""

    async def test_get_component_health_event_store(self, metrics_service):
        """Test getting health status for event store component."""
        # Act
        health = await metrics_service.get_component_health("event_store")

        # Assert
        assert health.component_name == "event_store"
        assert health.status == ComponentHealth.HEALTHY
        assert health.message is not None
        assert health.response_time_ms >= 0

    async def test_get_component_health_not_found(self, metrics_service):
        """Test that unknown component raises ComponentNotFoundError."""
        # Act & Assert
        with pytest.raises(ComponentNotFoundError):
            await metrics_service.get_component_health("unknown_component")

    async def test_get_component_health_includes_response_time(self, metrics_service):
        """Test that component health includes response time."""
        # Act
        health = await metrics_service.get_component_health("event_store")

        # Assert
        assert health.response_time_ms is not None
        assert health.response_time_ms >= 0


class TestPerformanceMetrics:
    """Tests for performance metrics calculations."""

    async def test_get_performance_metrics_empty(
        self, metrics_service, event_store, start_time
    ):
        """Test performance metrics with no execution events."""
        # Arrange
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Act
        metrics = await metrics_service.get_performance_metrics(one_hour_ago, now)

        # Assert
        assert metrics.active_executions == 0
        assert metrics.completed_executions_total == 0
        assert metrics.failed_executions_total == 0
        assert metrics.avg_execution_duration_seconds == 0.0
        assert metrics.start_time == one_hour_ago
        assert metrics.end_time == now

    async def test_get_performance_metrics_with_executions(
        self, metrics_service, event_store, start_time
    ):
        """Test performance metrics with execution events."""
        # Arrange
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Add execution events
        exec_id = "exec-123"
        event1 = MockEvent(
            event_type="AgentExecutionStarted",
            aggregate_id=exec_id,
            payload={"agent_name": "test_agent", "execution_id": exec_id},
            occurred_at=one_hour_ago + timedelta(minutes=5),
        )
        event2 = MockEvent(
            event_type="AgentExecutionCompleted",
            aggregate_id=exec_id,
            payload={
                "agent_name": "test_agent",
                "execution_id": exec_id,
                "duration_seconds": 120.5,
            },
            occurred_at=one_hour_ago + timedelta(minutes=7),
        )
        await event_store.append(exec_id, [event1, event2])

        # Act
        metrics = await metrics_service.get_performance_metrics(one_hour_ago, now)

        # Assert
        assert metrics.active_executions == 0
        assert metrics.completed_executions_total == 1
        assert metrics.failed_executions_total == 0
        assert metrics.avg_execution_duration_seconds == 120.5

    async def test_get_performance_metrics_calculates_active_count(
        self, metrics_service, event_store, start_time
    ):
        """Test that active executions are calculated correctly."""
        # Arrange
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Add execution started events (2 total)
        for i in range(2):
            event = MockEvent(
                event_type="AgentExecutionStarted",
                aggregate_id=f"exec-{i}",
                payload={"agent_name": f"agent_{i}", "execution_id": f"exec-{i}"},
                occurred_at=one_hour_ago + timedelta(minutes=5),
            )
            await event_store.append(f"exec-{i}", [event])

        # Add one completed event
        event = MockEvent(
            event_type="AgentExecutionCompleted",
            aggregate_id="exec-0",
            payload={
                "agent_name": "agent_0",
                "execution_id": "exec-0",
                "duration_seconds": 60.0,
            },
            occurred_at=one_hour_ago + timedelta(minutes=6),
        )
        await event_store.append("exec-0", [event])

        # Act
        metrics = await metrics_service.get_performance_metrics(one_hour_ago, now)

        # Assert
        assert metrics.active_executions == 1  # One still running
        assert metrics.completed_executions_total == 1
        assert metrics.failed_executions_total == 0


class TestResilienceMetrics:
    """Tests for resilience metrics."""

    async def test_get_resilience_metrics_returns_empty(
        self, metrics_service, start_time
    ):
        """Test resilience metrics returns placeholder data."""
        # Arrange
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Act
        metrics = await metrics_service.get_resilience_metrics(one_hour_ago, now)

        # Assert
        assert metrics.circuit_breakers == {}
        assert metrics.rate_limiters == {}
        assert metrics.retry_attempts_total == 0
        assert metrics.retry_successes_total == 0
        assert metrics.retry_failures_total == 0
        assert metrics.timeout_count == 0


class TestIntegrationStatus:
    """Tests for integration status checks."""

    async def test_get_integration_status_includes_event_store(self, metrics_service):
        """Test integration status includes event store connectivity."""
        # Act
        status = await metrics_service.get_integration_status()

        # Assert
        assert status.event_store_connected is True
        assert status.event_store_latency_ms is not None
        assert status.event_store_latency_ms >= 0
        assert status.checked_at is not None

    async def test_get_integration_status_github_unchecked(self, metrics_service):
        """Test integration status for GitHub shows unchecked."""
        # Act
        status = await metrics_service.get_integration_status()

        # Assert
        assert status.github_connected is False
        assert status.github_api_calls_remaining is None

    async def test_get_integration_status_docker_unchecked(self, metrics_service):
        """Test integration status for Docker shows unchecked."""
        # Act
        status = await metrics_service.get_integration_status()

        # Assert
        assert status.docker_connected is False
        assert status.docker_version is None


class TestSimulationModeInfo:
    """Tests for simulation mode information."""

    async def test_get_simulation_mode_info_returns_disabled(self, metrics_service):
        """Test simulation mode info when simulation is not enabled."""
        # Act
        info = await metrics_service.get_simulation_mode_info()

        # Assert
        assert info.enabled is False
        assert info.time_multiplier == 1.0
        assert info.deterministic_responses is False
        assert info.mock_external_services is False
        assert info.event_replay_enabled is False
        assert info.current_simulation_time is None


class TestMetricTimeSeries:
    """Tests for metric time series queries."""

    async def test_get_metric_time_series_not_found(self, metrics_service):
        """Test that metric time series raises MetricNotFoundError."""
        # Act & Assert
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        with pytest.raises(MetricNotFoundError):
            await metrics_service.get_metric_time_series(
                "unknown_metric", one_hour_ago, now
            )

    async def test_list_metric_names_returns_empty(self, metrics_service):
        """Test that list metric names returns empty list."""
        # Act
        metrics = await metrics_service.list_metric_names()

        # Assert
        assert metrics == []

    async def test_list_metric_names_with_prefix(self, metrics_service):
        """Test that list metric names with prefix returns empty list."""
        # Act
        metrics = await metrics_service.list_metric_names(prefix="test_")

        # Assert
        assert metrics == []


class TestEndpointAndAgentMetrics:
    """Tests for endpoint and agent-specific metrics."""

    async def test_get_api_endpoint_metrics_empty(self, metrics_service):
        """Test API endpoint metrics returns empty dict."""
        # Act
        metrics = await metrics_service.get_api_endpoint_metrics()

        # Assert
        assert metrics == {}

    async def test_get_api_endpoint_metrics_with_filter(self, metrics_service):
        """Test API endpoint metrics with specific endpoint filter."""
        # Arrange
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Act
        metrics = await metrics_service.get_api_endpoint_metrics(
            endpoint_path="/api/v2/agents", start_time=one_hour_ago, end_time=now
        )

        # Assert
        assert metrics == {}

    async def test_get_agent_execution_metrics_empty(
        self, metrics_service, event_store, start_time
    ):
        """Test agent execution metrics with no events."""
        # Arrange
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Act
        metrics = await metrics_service.get_agent_execution_metrics(
            start_time=one_hour_ago, end_time=now
        )

        # Assert
        assert metrics["agent_name"] == "all"
        assert metrics["total_executions"] == 0
        assert metrics["completed"] == 0
        assert metrics["failed"] == 0
        assert metrics["active"] == 0
        assert metrics["success_rate"] == 0.0

    async def test_get_agent_execution_metrics_with_executions(
        self, metrics_service, event_store, start_time
    ):
        """Test agent execution metrics with execution events."""
        # Arrange
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Add execution events
        for i in range(3):
            exec_id = f"exec-{i}"
            event1 = MockEvent(
                event_type="AgentExecutionStarted",
                aggregate_id=exec_id,
                payload={
                    "agent_name": "test_agent",
                    "execution_id": exec_id,
                },
                occurred_at=one_hour_ago + timedelta(minutes=5),
            )
            await event_store.append(exec_id, [event1])

            if i < 2:  # 2 completed
                event2 = MockEvent(
                    event_type="AgentExecutionCompleted",
                    aggregate_id=exec_id,
                    payload={
                        "agent_name": "test_agent",
                        "execution_id": exec_id,
                        "duration_seconds": 60.0 + i * 10,
                    },
                    occurred_at=one_hour_ago + timedelta(minutes=6),
                )
                await event_store.append(exec_id, [event2])
            else:  # 1 failed
                event3 = MockEvent(
                    event_type="AgentExecutionFailed",
                    aggregate_id=exec_id,
                    payload={
                        "agent_name": "test_agent",
                        "execution_id": exec_id,
                    },
                    occurred_at=one_hour_ago + timedelta(minutes=6),
                )
                await event_store.append(exec_id, [event3])

        # Act
        metrics = await metrics_service.get_agent_execution_metrics(
            start_time=one_hour_ago, end_time=now
        )

        # Assert
        assert metrics["agent_name"] == "all"
        assert metrics["total_executions"] == 3
        assert metrics["completed"] == 2
        assert metrics["failed"] == 1
        assert metrics["active"] == 0
        assert metrics["success_rate"] == pytest.approx(2 / 3)

    async def test_get_agent_execution_metrics_filtered_by_agent_name(
        self, metrics_service, event_store, start_time
    ):
        """Test agent execution metrics filtered by agent name."""
        # Arrange
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        # Add execution events for two different agents
        for agent_idx, agent_name in enumerate(["agent_a", "agent_b"]):
            for exec_idx in range(2):
                exec_id = f"exec-{agent_idx}-{exec_idx}"
                event = MockEvent(
                    event_type="AgentExecutionStarted",
                    aggregate_id=exec_id,
                    payload={
                        "agent_name": agent_name,
                        "execution_id": exec_id,
                    },
                    occurred_at=one_hour_ago + timedelta(minutes=5),
                )
                await event_store.append(exec_id, [event])

        # Act - Filter by agent_a
        metrics = await metrics_service.get_agent_execution_metrics(
            agent_name="agent_a", start_time=one_hour_ago, end_time=now
        )

        # Assert
        assert metrics["agent_name"] == "agent_a"
        assert metrics["total_executions"] == 2

    async def test_get_agent_execution_metrics_duration_stats(
        self, metrics_service, event_store, start_time
    ):
        """Test agent execution metrics calculates duration statistics."""
        # Arrange
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        durations = [30.0, 60.0, 90.0]

        # Add execution events with specific durations
        for i, duration in enumerate(durations):
            exec_id = f"exec-{i}"
            event1 = MockEvent(
                event_type="AgentExecutionStarted",
                aggregate_id=exec_id,
                payload={
                    "agent_name": "test_agent",
                    "execution_id": exec_id,
                },
                occurred_at=one_hour_ago + timedelta(minutes=5),
            )
            event2 = MockEvent(
                event_type="AgentExecutionCompleted",
                aggregate_id=exec_id,
                payload={
                    "agent_name": "test_agent",
                    "execution_id": exec_id,
                    "duration_seconds": duration,
                },
                occurred_at=one_hour_ago + timedelta(minutes=6),
            )
            await event_store.append(exec_id, [event1, event2])

        # Act
        metrics = await metrics_service.get_agent_execution_metrics(
            start_time=one_hour_ago, end_time=now
        )

        # Assert
        assert metrics["avg_duration_seconds"] == pytest.approx(60.0)
        assert metrics["min_duration_seconds"] == 30.0
        assert metrics["max_duration_seconds"] == 90.0


class TestActiveAgents:
    """Tests for active agents reporting."""

    async def test_get_active_agents_empty(self, metrics_service):
        """Test active agents when none are running."""
        # Act
        result = await metrics_service.get_active_agents()

        # Assert
        assert result["count"] == 0
        assert result["agents"] == []
        assert "checked_at" in result

    async def test_get_active_agents_with_running_executions(
        self, metrics_service, event_store, start_time
    ):
        """Test active agents with running executions."""
        # Arrange
        now = datetime.now()
        recent_time = now - timedelta(hours=12)

        # Add a running execution
        exec_id = "exec-123"
        event = MockEvent(
            event_type="AgentExecutionStarted",
            aggregate_id=exec_id,
            payload={
                "agent_name": "developer_agent",
                "execution_id": exec_id,
                "work_item_id": "wi-456",
            },
            occurred_at=recent_time,
        )
        await event_store.append(exec_id, [event])

        # Act
        result = await metrics_service.get_active_agents()

        # Assert
        assert result["count"] == 1
        assert len(result["agents"]) == 1
        agent = result["agents"][0]
        assert agent["execution_id"] == exec_id
        assert agent["agent_name"] == "developer_agent"
        assert agent["work_item_id"] == "wi-456"
        assert agent["duration_seconds"] > 0

    async def test_get_active_agents_filters_completed(
        self, metrics_service, event_store, start_time
    ):
        """Test active agents filters out completed executions."""
        # Arrange
        now = datetime.now()
        recent_time = now - timedelta(hours=12)

        # Add execution that is completed
        exec_id = "exec-123"
        event1 = MockEvent(
            event_type="AgentExecutionStarted",
            aggregate_id=exec_id,
            payload={
                "agent_name": "test_agent",
                "execution_id": exec_id,
            },
            occurred_at=recent_time,
        )
        event2 = MockEvent(
            event_type="AgentExecutionCompleted",
            aggregate_id=exec_id,
            payload={
                "agent_name": "test_agent",
                "execution_id": exec_id,
                "duration_seconds": 60.0,
            },
            occurred_at=recent_time + timedelta(minutes=1),
        )
        await event_store.append(exec_id, [event1, event2])

        # Act
        result = await metrics_service.get_active_agents()

        # Assert
        assert result["count"] == 0
        assert result["agents"] == []

    async def test_get_active_agents_multiple_executions(
        self, metrics_service, event_store, start_time
    ):
        """Test active agents with multiple executions."""
        # Arrange
        now = datetime.now()
        recent_time = now - timedelta(hours=12)

        # Add multiple executions
        for i in range(3):
            exec_id = f"exec-{i}"
            event = MockEvent(
                event_type="AgentExecutionStarted",
                aggregate_id=exec_id,
                payload={
                    "agent_name": f"agent_{i}",
                    "execution_id": exec_id,
                    "work_item_id": f"wi-{i}",
                },
                occurred_at=recent_time + timedelta(minutes=i),
            )
            await event_store.append(exec_id, [event])

        # Act
        result = await metrics_service.get_active_agents()

        # Assert
        assert result["count"] == 3
        assert len(result["agents"]) == 3


class TestApiUsage:
    """Tests for API usage reporting."""

    async def test_get_api_usage_returns_placeholder(self, metrics_service):
        """Test API usage returns placeholder data."""
        # Act
        usage = await metrics_service.get_api_usage()

        # Assert
        assert "claude_api" in usage or "checked_at" in usage
        assert usage.get("checked_at") is not None

    async def test_get_api_usage_structure(self, metrics_service):
        """Test API usage response has expected structure."""
        # Act
        usage = await metrics_service.get_api_usage()

        # Assert
        assert "claude_api" in usage
        assert "github_api" in usage
        assert "checked_at" in usage
        assert usage["claude_api"]["requests_today"] >= 0
        assert usage["claude_api"]["tokens_input_today"] >= 0
        assert usage["claude_api"]["tokens_output_today"] >= 0
