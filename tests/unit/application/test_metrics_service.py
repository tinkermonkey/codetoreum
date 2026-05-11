"""
Unit tests for MetricsService.

Tests cover:
- System health status calculation
- Performance metrics aggregation
- Error handling with graceful degradation
- Component health checking
- Integration status reporting
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from codetoreum.application.metrics_service import MetricsService
from codetoreum.ports.exceptions import ComponentNotFoundError
from codetoreum.ports.input.metrics_query import ComponentHealth
from codetoreum.ports.output.event_store import IEventStore


class MockEvent:
    """Mock domain event for testing."""

    def __init__(self, event_type: str, payload: dict[str, Any], occurred_at: datetime | None = None):
        self.event_type = event_type
        self.event_id = uuid4()
        self.aggregate_id = "test-aggregate-id"
        self.aggregate_type = "TestAggregate"
        self.occurred_at = occurred_at or datetime.now(UTC)
        self.payload = payload
        # Expose payload keys as direct attributes to match modern CodetoreumEvent interface
        for key, val in payload.items():
            setattr(self, key, val)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload,
        }


class MockEventStore(IEventStore):
    """Mock event store for testing."""

    def __init__(self):
        self.events: list = []
        self.should_fail = False
        self.fail_on_type: str | None = None

    async def append(
        self,
        stream_id: str,
        events: list,
        expected_version: int | None = None,
    ) -> None:
        if self.should_fail:
            raise Exception("Event store failure")
        self.events.extend(events)

    async def get_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: int | None = None,
    ) -> list:
        return self.events

    async def get_events_since(
        self,
        since: datetime,
        stream_id: str | None = None,
    ) -> list:
        # Handle both naive and aware datetimes
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)
        return [e for e in self.events if e.occurred_at >= since]

    async def stream_events(
        self,
        stream_id: str | None = None,
        from_version: int = 0,
    ):
        for event in self.events:
            yield event

    async def get_stream_version(self, stream_id: str) -> int:
        return len(self.events)

    async def stream_exists(self, stream_id: str) -> bool:
        return True

    async def save_snapshot(
        self,
        stream_id: str,
        version: int,
        snapshot: dict[str, Any],
    ) -> None:
        pass

    async def get_latest_snapshot(
        self,
        stream_id: str,
    ) -> dict[str, Any] | None:
        return None

    async def delete_stream(self, stream_id: str) -> None:
        self.events.clear()

    async def get_all_stream_ids(
        self,
        aggregate_type: str | None = None,
    ) -> list[str]:
        return ["test-stream"]

    async def get_events_by_type(self, event_type: str, since: datetime | None = None, limit: int = 1000) -> list:
        events = [e for e in self.events if e.event_type == event_type]

        if since:
            # Normalize both datetimes to naive UTC for comparison
            since_naive = since.replace(tzinfo=None) if since.tzinfo else since
            events = [
                e
                for e in events
                if (e.occurred_at.replace(tzinfo=None) if e.occurred_at.tzinfo else e.occurred_at) >= since_naive
            ]

        if limit:
            events = events[:limit]

        if self.fail_on_type and self.fail_on_type == event_type:
            raise Exception(f"Failed to retrieve {event_type} events")

        return events

    async def get_events_by_correlation_id(
        self,
        correlation_id: str,
    ) -> list:
        return []

    async def replay_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: int | None = None,
    ):
        for event in self.events:
            yield event

    async def get_statistics(self) -> dict[str, Any]:
        if self.should_fail:
            raise Exception("Failed to get statistics")
        return {
            "total_events": len(self.events),
            "event_types": len(set(e.event_type for e in self.events)),
        }

    async def clear(self) -> None:
        self.events.clear()


class TestMetricsServiceHealthCheck:
    """Tests for system health checking."""

    @pytest.mark.asyncio
    async def test_get_system_health_all_healthy(self):
        """Test system health returns healthy when all components are working."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(),  # Use naive datetime like the service does
            version="1.0.0",
        )

        health = await metrics_service.get_system_health()

        assert health.status == ComponentHealth.HEALTHY
        assert len(health.components) > 0
        assert all(c.status == ComponentHealth.HEALTHY for c in health.components)
        assert health.version == "1.0.0"
        assert health.uptime_seconds >= 0

    @pytest.mark.asyncio
    async def test_get_system_health_event_store_unhealthy(self):
        """Test system health reflects unhealthy event store."""
        event_store = MockEventStore()
        event_store.should_fail = True

        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now() - timedelta(hours=1),  # Use naive datetime
            version="1.0.0",
        )

        health = await metrics_service.get_system_health()

        assert health.status == ComponentHealth.UNHEALTHY
        event_store_health = next((c for c in health.components if c.component_name == "event_store"), None)
        assert event_store_health is not None
        assert event_store_health.status == ComponentHealth.UNHEALTHY

    @pytest.mark.asyncio
    async def test_get_component_health_event_store(self):
        """Test getting health for specific component."""
        event_store = MockEventStore()
        start_time = datetime.now(UTC)
        metrics_service = MetricsService(event_store=event_store, start_time=start_time, version="1.0.0")

        health = await metrics_service.get_component_health("event_store")

        assert health.component_name == "event_store"
        assert health.status == ComponentHealth.HEALTHY
        assert health.response_time_ms >= 0

    @pytest.mark.asyncio
    async def test_get_component_health_unknown_component(self):
        """Test requesting unknown component raises error."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        with pytest.raises(ComponentNotFoundError):
            await metrics_service.get_component_health("unknown_component")


class TestMetricsServicePerformance:
    """Tests for performance metrics."""

    @pytest.mark.asyncio
    async def test_get_performance_metrics_no_events(self):
        """Test performance metrics with no events."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        start = datetime.now(UTC) - timedelta(hours=1)
        end = datetime.now(UTC)

        metrics = await metrics_service.get_performance_metrics(start, end)

        assert metrics.active_executions == 0
        assert metrics.completed_executions_total == 0
        assert metrics.failed_executions_total == 0
        assert metrics.avg_execution_duration_seconds == 0.0

    @pytest.mark.asyncio
    async def test_get_performance_metrics_with_executions(self):
        """Test performance metrics aggregation."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        # Create test events
        now = datetime.now(UTC)
        started_event = MockEvent("AgentExecutionStarted", {"agent_name": "test_agent"}, now)
        completed_event = MockEvent(
            "AgentExecutionCompleted",
            {"agent_name": "test_agent", "duration_seconds": 45.5},
            now + timedelta(seconds=45),
        )

        await event_store.append("stream-1", [started_event])
        await event_store.append("stream-1", [completed_event])

        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)

        metrics = await metrics_service.get_performance_metrics(start, end)

        assert metrics.completed_executions_total == 1
        assert metrics.avg_execution_duration_seconds == 45.5

    @pytest.mark.asyncio
    async def test_get_performance_metrics_active_executions(self):
        """Test calculation of active executions."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # 3 started, 1 completed, 1 failed = 1 active
        await event_store.append("stream-1", [MockEvent("AgentExecutionStarted", {"agent_name": "a1"}, now)])
        await event_store.append("stream-1", [MockEvent("AgentExecutionStarted", {"agent_name": "a2"}, now)])
        await event_store.append("stream-1", [MockEvent("AgentExecutionStarted", {"agent_name": "a3"}, now)])
        await event_store.append("stream-1", [MockEvent("AgentExecutionCompleted", {"agent_name": "a1"}, now)])
        await event_store.append("stream-1", [MockEvent("AgentExecutionFailed", {"agent_name": "a2"}, now)])

        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)

        metrics = await metrics_service.get_performance_metrics(start, end)

        assert metrics.active_executions == 1


class TestMetricsServiceAgentMetrics:
    """Tests for agent execution metrics."""

    @pytest.mark.asyncio
    async def test_get_agent_execution_metrics_all_agents(self):
        """Test aggregation of metrics for all agents."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Create test events
        await event_store.append("stream-1", [MockEvent("AgentExecutionStarted", {"agent_name": "agent_a"}, now)])
        await event_store.append("stream-1", [MockEvent("AgentExecutionStarted", {"agent_name": "agent_b"}, now)])
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "AgentExecutionCompleted",
                    {"agent_name": "agent_a", "duration_seconds": 30.0},
                    now + timedelta(seconds=30),
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionFailed", {"agent_name": "agent_b"}, now + timedelta(seconds=10))],
        )

        metrics = await metrics_service.get_agent_execution_metrics(
            start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=1)
        )

        assert metrics["agent_name"] == "all"
        assert metrics["total_executions"] == 2
        assert metrics["completed"] == 1
        assert metrics["failed"] == 1
        assert metrics["success_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_get_agent_execution_metrics_specific_agent(self):
        """Test filtering metrics by specific agent."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Create test events
        await event_store.append("stream-1", [MockEvent("AgentExecutionStarted", {"agent_name": "agent_a"}, now)])
        await event_store.append("stream-1", [MockEvent("AgentExecutionStarted", {"agent_name": "agent_b"}, now)])
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "AgentExecutionCompleted",
                    {"agent_name": "agent_a", "duration_seconds": 25.0},
                    now + timedelta(seconds=25),
                )
            ],
        )

        metrics = await metrics_service.get_agent_execution_metrics(
            agent_name="agent_a",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert metrics["agent_name"] == "agent_a"
        assert metrics["total_executions"] == 1
        assert metrics["completed"] == 1

    @pytest.mark.asyncio
    async def test_get_agent_execution_metrics_duration_stats(self):
        """Test duration statistics calculation."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Create multiple executions with different durations
        for i in range(3):
            await event_store.append(
                "stream-1",
                [
                    MockEvent(
                        "AgentExecutionStarted",
                        {"agent_name": "test"},
                        now + timedelta(seconds=i * 50),
                    )
                ],
            )
            await event_store.append(
                "stream-1",
                [
                    MockEvent(
                        "AgentExecutionCompleted",
                        {"agent_name": "test", "duration_seconds": 10.0 + i * 5},
                        now + timedelta(seconds=i * 50 + 10 + i * 5),
                    )
                ],
            )

        metrics = await metrics_service.get_agent_execution_metrics(
            agent_name="test",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        # Durations: 10, 15, 20
        assert metrics["min_duration_seconds"] == 10.0
        assert metrics["max_duration_seconds"] == 20.0
        assert metrics["avg_duration_seconds"] == 15.0


class TestMetricsServiceActiveAgents:
    """Tests for active agent tracking."""

    @pytest.mark.asyncio
    async def test_get_active_agents_empty(self):
        """Test active agents list when empty."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        result = await metrics_service.get_active_agents()

        assert result["count"] == 0
        assert result["agents"] == []

    @pytest.mark.asyncio
    async def test_get_active_agents_with_active_executions(self):
        """Test active agents list includes only incomplete executions."""
        event_store = MockEventStore()
        start_time = datetime.now()  # Use naive datetime
        metrics_service = MetricsService(event_store=event_store, start_time=start_time, version="1.0.0")

        now = datetime.now()  # Use naive datetime to match service usage

        # Create test events - one active, one completed
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "AgentExecutionStarted",
                    {"execution_id": "exec_1", "agent_name": "agent_a", "work_item_id": "wi_1"},
                    now - timedelta(hours=12),
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "AgentExecutionStarted",
                    {"execution_id": "exec_2", "agent_name": "agent_b", "work_item_id": "wi_2"},
                    now - timedelta(hours=6),
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionCompleted", {"execution_id": "exec_1"}, now - timedelta(hours=10))],
        )

        result = await metrics_service.get_active_agents()

        assert result["count"] == 1
        assert len(result["agents"]) == 1
        assert result["agents"][0]["execution_id"] == "exec_2"
        assert result["agents"][0]["agent_name"] == "agent_b"


class TestMetricsServiceIntegrationStatus:
    """Tests for integration status reporting."""

    @pytest.mark.asyncio
    async def test_get_integration_status_event_store_healthy(self):
        """Test integration status with healthy event store."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        status = await metrics_service.get_integration_status()

        assert status.event_store_connected is True
        assert status.event_store_latency_ms is not None
        assert status.event_store_latency_ms >= 0

    @pytest.mark.asyncio
    async def test_get_integration_status_event_store_unhealthy(self):
        """Test integration status with unhealthy event store."""
        event_store = MockEventStore()
        event_store.should_fail = True

        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        status = await metrics_service.get_integration_status()

        assert status.event_store_connected is False
        assert status.event_store_latency_ms is None


class TestMetricsServiceErrorHandling:
    """Tests for error handling and graceful degradation."""

    @pytest.mark.asyncio
    async def test_metrics_with_missing_event_fields(self):
        """Test metrics calculation handles missing event fields gracefully."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Event missing duration_seconds field
        incomplete_event = MockEvent(
            "AgentExecutionCompleted",
            {"agent_name": "test"},  # No duration_seconds
            now,
        )
        await event_store.append("stream-1", [incomplete_event])

        # Should not raise, just handle gracefully
        metrics = await metrics_service.get_performance_metrics(now - timedelta(hours=1), now + timedelta(hours=1))

        assert metrics.avg_execution_duration_seconds == 0.0


class TestMetricsServiceEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_performance_metrics_with_zero_duration(self):
        """Test handling of executions with zero duration."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)
        await event_store.append("stream-1", [MockEvent("AgentExecutionCompleted", {"duration_seconds": 0.0}, now)])

        metrics = await metrics_service.get_performance_metrics(now - timedelta(hours=1), now + timedelta(hours=1))

        assert metrics.avg_execution_duration_seconds == 0.0


class TestMetricsServiceResilienceMetrics:
    """Tests for resilience infrastructure metrics."""

    @pytest.mark.asyncio
    async def test_get_resilience_metrics_no_events(self):
        """Test resilience metrics with no events."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)
        metrics = await metrics_service.get_resilience_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metrics.retry_attempts_total == 0
        assert metrics.retry_successes_total == 0
        assert metrics.retry_failures_total == 0
        assert metrics.timeout_count == 0
        assert metrics.avg_timeout_duration_ms == 0.0

    @pytest.mark.asyncio
    async def test_get_resilience_metrics_with_retries(self):
        """Test resilience metrics with retry events."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add retry events - some successful, some failed
        await event_store.append(
            "stream-1",
            [MockEvent("ExecutionRetried", {"success": True}, now)],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("ExecutionRetried", {"success": True}, now + timedelta(seconds=5))],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("ExecutionRetried", {"success": False}, now + timedelta(seconds=10))],
        )

        metrics = await metrics_service.get_resilience_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert metrics.retry_attempts_total == 3
        assert metrics.retry_successes_total == 2
        assert metrics.retry_failures_total == 1

    @pytest.mark.asyncio
    async def test_get_resilience_metrics_with_timeouts(self):
        """Test resilience metrics with timeout events."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add timeout events
        await event_store.append(
            "stream-1",
            [MockEvent("ExecutionTimeout", {"duration_ms": 5000}, now)],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("ExecutionTimeout", {"duration_ms": 3000}, now + timedelta(seconds=5))],
        )

        metrics = await metrics_service.get_resilience_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert metrics.timeout_count == 2
        assert metrics.avg_timeout_duration_ms == 4000.0

    @pytest.mark.asyncio
    async def test_get_resilience_metrics_filters_by_time_range(self):
        """Test resilience metrics respects end_time boundary."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add events inside and outside time range
        await event_store.append(
            "stream-1",
            [MockEvent("ExecutionRetried", {"success": True}, now - timedelta(hours=2))],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("ExecutionRetried", {"success": True}, now - timedelta(minutes=30))],
        )

        metrics = await metrics_service.get_resilience_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now - timedelta(minutes=15),
        )

        # Only the middle event should be included (after start, before end)
        assert metrics.retry_attempts_total == 1


class TestMetricsServiceSimulationMode:
    """Tests for simulation mode information."""

    @pytest.mark.asyncio
    async def test_get_simulation_mode_info_default(self):
        """Test simulation mode returns default when no config exists."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        info = await metrics_service.get_simulation_mode_info()

        assert info.enabled is False
        assert info.time_multiplier == 1.0
        assert info.deterministic_responses is False
        assert info.mock_external_services is False
        assert info.event_replay_enabled is False

    @pytest.mark.asyncio
    async def test_get_simulation_mode_info_from_config(self):
        """Test simulation mode reads from SimulationConfigured event."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)
        config_event = MockEvent(
            "SimulationConfigured",
            {
                "enabled": True,
                "time_multiplier": 100.0,
                "deterministic_responses": True,
                "mock_external_services": True,
                "event_replay_enabled": True,
                "current_simulation_time": now.isoformat(),
                "started_at": now.isoformat(),
            },
            now,
        )
        await event_store.append("stream-1", [config_event])

        info = await metrics_service.get_simulation_mode_info()

        assert info.enabled is True
        assert info.time_multiplier == 100.0
        assert info.deterministic_responses is True
        assert info.mock_external_services is True
        assert info.event_replay_enabled is True

    @pytest.mark.asyncio
    async def test_get_simulation_mode_info_handles_query_errors(self):
        """Test simulation mode handles errors gracefully."""
        event_store = MockEventStore()
        event_store.fail_on_type = "SimulationConfigured"
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        info = await metrics_service.get_simulation_mode_info()

        # Should return default config on error
        assert info.enabled is False


class TestMetricsServiceTimeSeries:
    """Tests for metric time series queries."""

    @pytest.mark.asyncio
    async def test_get_metric_time_series_execution_count(self):
        """Test time series query for execution count metric."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add execution events
        for i in range(3):
            await event_store.append(
                "stream-1",
                [MockEvent("AgentExecutionStarted", {"agent_name": f"agent_{i}"}, now + timedelta(seconds=i))],
            )

        series = await metrics_service.get_metric_time_series(
            metric_name="execution_count",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert series.metric_name == "execution_count"
        assert len(series.data_points) == 1
        assert series.data_points[0].value == 3.0

    @pytest.mark.asyncio
    async def test_get_metric_time_series_execution_success_rate(self):
        """Test time series query for success rate metric."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # 2 started, 1 completed = 50% success rate
        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionStarted", {"agent_name": "a1"}, now)],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionStarted", {"agent_name": "a2"}, now + timedelta(seconds=1))],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionCompleted", {"agent_name": "a1"}, now + timedelta(seconds=10))],
        )

        series = await metrics_service.get_metric_time_series(
            metric_name="execution_success_rate",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert series.metric_name == "execution_success_rate"
        assert len(series.data_points) == 1
        assert series.data_points[0].value == 50.0

    @pytest.mark.asyncio
    async def test_get_metric_time_series_error_rate(self):
        """Test time series query for error rate metric."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # 3 started, 1 failed = 33.33% error rate
        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionStarted", {"agent_name": "a1"}, now)],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionStarted", {"agent_name": "a2"}, now + timedelta(seconds=1))],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionStarted", {"agent_name": "a3"}, now + timedelta(seconds=2))],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionFailed", {"agent_name": "a1"}, now + timedelta(seconds=10))],
        )

        series = await metrics_service.get_metric_time_series(
            metric_name="error_rate",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert series.metric_name == "error_rate"
        assert len(series.data_points) == 1
        assert abs(series.data_points[0].value - 33.33) < 0.1

    @pytest.mark.asyncio
    async def test_get_metric_time_series_execution_avg_duration(self):
        """Test time series query for average execution duration."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add completed events with durations
        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionCompleted", {"duration_seconds": 10.0}, now)],
        )
        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionCompleted", {"duration_seconds": 20.0}, now + timedelta(seconds=1))],
        )

        series = await metrics_service.get_metric_time_series(
            metric_name="execution_avg_duration",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert series.metric_name == "execution_avg_duration"
        assert len(series.data_points) == 1
        assert series.data_points[0].value == 15.0

    @pytest.mark.asyncio
    async def test_get_metric_time_series_invalid_metric(self):
        """Test time series query with invalid metric name."""
        from codetoreum.ports.exceptions import MetricNotFoundError

        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        with pytest.raises(MetricNotFoundError):
            await metrics_service.get_metric_time_series(
                metric_name="invalid_metric",
                start_time=now - timedelta(hours=1),
                end_time=now,
            )

    @pytest.mark.asyncio
    async def test_get_metric_time_series_with_labels(self):
        """Test time series query with label filters."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        await event_store.append(
            "stream-1",
            [MockEvent("AgentExecutionStarted", {"agent_name": "a1"}, now)],
        )

        labels = {"environment": "test", "region": "us-west"}
        series = await metrics_service.get_metric_time_series(
            metric_name="execution_count",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            labels=labels,
        )

        assert len(series.data_points) == 1
        assert series.data_points[0].labels == labels

    @pytest.mark.asyncio
    async def test_list_metric_names_all(self):
        """Test listing all available metric names."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        names = await metrics_service.list_metric_names()

        assert "execution_count" in names
        assert "execution_success_rate" in names
        assert "execution_avg_duration" in names
        assert "error_rate" in names

    @pytest.mark.asyncio
    async def test_list_metric_names_with_prefix(self):
        """Test listing metric names with prefix filter."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        names = await metrics_service.list_metric_names(prefix="execution")

        assert "execution_count" in names
        assert "execution_success_rate" in names
        assert "execution_avg_duration" in names
        assert "error_rate" not in names


class TestMetricsServiceAPIMetrics:
    """Tests for API endpoint and usage metrics."""

    @pytest.mark.asyncio
    async def test_get_api_endpoint_metrics_empty(self):
        """Test API endpoint metrics with no events."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)
        metrics = await metrics_service.get_api_endpoint_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metrics == {}

    @pytest.mark.asyncio
    async def test_get_api_endpoint_metrics_aggregation(self):
        """Test API endpoint metrics aggregation."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add API request events
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "APIRequestProcessed",
                    {"endpoint_path": "/api/work-items", "latency_ms": 100, "error": False},
                    now,
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "APIRequestProcessed",
                    {"endpoint_path": "/api/work-items", "latency_ms": 200, "error": False},
                    now + timedelta(seconds=1),
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "APIRequestProcessed",
                    {"endpoint_path": "/api/work-items", "latency_ms": 300, "error": True},
                    now + timedelta(seconds=2),
                )
            ],
        )

        metrics = await metrics_service.get_api_endpoint_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert "/api/work-items" in metrics
        endpoint_stats = metrics["/api/work-items"]
        assert endpoint_stats["requests"] == 3
        assert endpoint_stats["errors"] == 1
        assert endpoint_stats["avg_latency_ms"] == 200.0
        assert endpoint_stats["error_rate"] == pytest.approx(1 / 3)
        assert endpoint_stats["min_latency_ms"] == 100
        assert endpoint_stats["max_latency_ms"] == 300

    @pytest.mark.asyncio
    async def test_get_api_endpoint_metrics_filter_by_endpoint(self):
        """Test API endpoint metrics with endpoint filter."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add events for different endpoints
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "APIRequestProcessed",
                    {"endpoint_path": "/api/agents", "latency_ms": 100, "error": False},
                    now,
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "APIRequestProcessed",
                    {"endpoint_path": "/api/work-items", "latency_ms": 200, "error": False},
                    now + timedelta(seconds=1),
                )
            ],
        )

        metrics = await metrics_service.get_api_endpoint_metrics(
            endpoint_path="/api/agents",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert "/api/agents" in metrics
        assert "/api/work-items" not in metrics
        assert metrics["/api/agents"]["requests"] == 1

    @pytest.mark.asyncio
    async def test_get_api_usage_no_executions(self):
        """Test API usage with no execution events."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        usage = await metrics_service.get_api_usage()

        assert usage["claude_api"]["requests_today"] == 0
        assert usage["claude_api"]["tokens_input_today"] == 0
        assert usage["claude_api"]["tokens_output_today"] == 0
        assert usage["claude_api"]["tokens_total_today"] == 0
        assert usage["claude_api"]["estimated_cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_get_api_usage_with_token_data(self):
        """Test API usage calculation with token data."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        # Add execution events with token data
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "AgentExecutionCompleted",
                    {"input_tokens": 1000, "output_tokens": 500},
                    today + timedelta(hours=1),
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "AgentExecutionCompleted",
                    {"input_tokens": 2000, "output_tokens": 1000},
                    today + timedelta(hours=2),
                )
            ],
        )

        usage = await metrics_service.get_api_usage()

        assert usage["claude_api"]["requests_today"] == 2
        assert usage["claude_api"]["tokens_input_today"] == 3000
        assert usage["claude_api"]["tokens_output_today"] == 1500
        assert usage["claude_api"]["tokens_total_today"] == 4500
        # Cost: (3000/1000 * 0.003) + (1500/1000 * 0.015) = 0.009 + 0.0225 = 0.0315
        assert usage["claude_api"]["estimated_cost_usd"] == pytest.approx(0.0315, abs=0.0001)


class TestMetricsServiceRepairCycleMetrics:
    """Tests for repair cycle metrics."""

    @pytest.mark.asyncio
    async def test_get_repair_cycle_metrics_no_events(self):
        """Test repair cycle metrics with no events."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)
        metrics = await metrics_service.get_repair_cycle_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert metrics["cycles_started"] == 0
        assert metrics["cycles_completed"] == 0
        assert metrics["cycles_successful"] == 0
        assert metrics["cycles_failed"] == 0
        assert metrics["cycles_fast_failed"] == 0

    @pytest.mark.asyncio
    async def test_get_repair_cycle_metrics_full_cycle(self):
        """Test repair cycle metrics with complete cycle."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add repair cycle events
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "repair_cycle.started",
                    {"agent_name": "test_agent"},
                    now,
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "repair_cycle.test_execution_completed",
                    {"agent_name": "test_agent", "test_type": "unit_test"},
                    now + timedelta(seconds=10),
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "repair_cycle.file_fix_completed",
                    {"agent_name": "test_agent", "file_path": "src/test.py", "fixed": True},
                    now + timedelta(seconds=20),
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "repair_cycle.completed",
                    {
                        "agent_name": "test_agent",
                        "overall_success": True,
                        "duration_seconds": 30,
                        "total_agent_calls": 5,
                        "total_iterations": 2,
                    },
                    now + timedelta(seconds=30),
                )
            ],
        )

        metrics = await metrics_service.get_repair_cycle_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert metrics["cycles_started"] == 1
        assert metrics["cycles_completed"] == 1
        assert metrics["cycles_successful"] == 1
        assert metrics["cycles_failed"] == 0
        assert metrics["test_types"]["unit_test"]["executions"] == 1
        assert metrics["files_fixed"]["src/test.py"] == 1
        assert metrics["files_fixed_total"] == 1
        assert metrics["avg_duration_seconds"] == 30.0
        assert metrics["avg_agent_calls_per_cycle"] == 5.0

    @pytest.mark.asyncio
    async def test_get_repair_cycle_metrics_fast_fail(self):
        """Test repair cycle metrics with fast fail events."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add fast fail events
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "repair_cycle.started",
                    {"agent_name": "test_agent"},
                    now,
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "repair_cycle.fast_fail",
                    {"agent_name": "test_agent"},
                    now + timedelta(seconds=5),
                )
            ],
        )

        metrics = await metrics_service.get_repair_cycle_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert metrics["cycles_started"] == 1
        assert metrics["cycles_fast_failed"] == 1

    @pytest.mark.asyncio
    async def test_get_repair_cycle_metrics_filter_by_agent(self):
        """Test repair cycle metrics filtering by agent name."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add events for multiple agents
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "repair_cycle.started",
                    {"agent_name": "agent_a"},
                    now,
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "repair_cycle.started",
                    {"agent_name": "agent_b"},
                    now + timedelta(seconds=1),
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "repair_cycle.completed",
                    {"agent_name": "agent_a", "overall_success": True, "duration_seconds": 10},
                    now + timedelta(seconds=10),
                )
            ],
        )

        metrics = await metrics_service.get_repair_cycle_metrics(
            agent_name="agent_a",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert metrics["cycles_started"] == 1
        assert metrics["cycles_completed"] == 1
        assert metrics["agents"]["agent_a"]["started"] == 1
        assert metrics["agents"]["agent_a"]["successful"] == 1

    @pytest.mark.asyncio
    async def test_get_repair_cycle_metrics_warning_review(self):
        """Test repair cycle metrics with warning review events."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add warning review events
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "repair_cycle.warning_review_completed",
                    {"agent_name": "test_agent", "warnings_reviewed": 5},
                    now,
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "repair_cycle.warning_review_completed",
                    {"agent_name": "test_agent", "warnings_reviewed": 3},
                    now + timedelta(seconds=5),
                )
            ],
        )

        metrics = await metrics_service.get_repair_cycle_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert metrics["warnings_reviewed_total"] == 8


class TestMetricsServiceGitHubIntegration:
    """Tests for GitHub integration status."""

    @pytest.mark.asyncio
    async def test_get_integration_status_github_connected(self):
        """Test integration status shows GitHub as connected."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add GitHub adapter events
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "GitHubAdapterEvent",
                    {"success": True, "operation": "fetch_pull_requests"},
                    now - timedelta(minutes=30),
                )
            ],
        )

        status = await metrics_service.get_integration_status()

        assert status.github_connected is True
        assert status.github_webhook_health == ComponentHealth.HEALTHY

    @pytest.mark.asyncio
    async def test_get_integration_status_github_degraded(self):
        """Test integration status shows GitHub as degraded."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add GitHub adapter events with failures
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "GitHubAdapterEvent",
                    {"success": False, "error": "rate_limit_exceeded"},
                    now - timedelta(minutes=30),
                )
            ],
        )

        status = await metrics_service.get_integration_status()

        assert status.github_connected is True
        assert status.github_webhook_health == ComponentHealth.DEGRADED

    @pytest.mark.asyncio
    async def test_get_integration_status_docker_connected(self):
        """Test integration status shows Docker as connected."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add Docker container events
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "ContainerStarted",
                    {"container_id": "container_1"},
                    now - timedelta(minutes=30),
                )
            ],
        )

        status = await metrics_service.get_integration_status()

        assert status.docker_connected is True
        assert status.docker_containers_running == 1

    @pytest.mark.asyncio
    async def test_get_integration_status_docker_container_lifecycle(self):
        """Test Docker container tracking across start/stop."""
        event_store = MockEventStore()
        metrics_service = MetricsService(event_store=event_store, start_time=datetime.now(UTC), version="1.0.0")

        now = datetime.now(UTC)

        # Add Docker lifecycle events
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "ContainerStarted",
                    {"container_id": "container_1"},
                    now - timedelta(minutes=30),
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "ContainerStarted",
                    {"container_id": "container_2"},
                    now - timedelta(minutes=25),
                )
            ],
        )
        await event_store.append(
            "stream-1",
            [
                MockEvent(
                    "ContainerStopped",
                    {"container_id": "container_1"},
                    now - timedelta(minutes=10),
                )
            ],
        )

        status = await metrics_service.get_integration_status()

        # Only container_2 should be running
        assert status.docker_containers_running == 1
