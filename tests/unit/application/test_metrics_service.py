"""
Unit tests for MetricsService.

Tests cover:
- System health status calculation
- Performance metrics aggregation
- Error handling with graceful degradation
- Component health checking
- Integration status reporting
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from codetoreum.application.metrics_service import MetricsService
from codetoreum.domain.events import DomainEvent
from codetoreum.ports.exceptions import ComponentNotFoundError, MetricNotFoundError
from codetoreum.ports.input.metrics_query import ComponentHealth
from codetoreum.ports.output.event_store import IEventStore


class MockEvent(DomainEvent):
    """Mock domain event for testing."""

    def __init__(self, event_type: str, payload: Dict[str, Any], occurred_at: Optional[datetime] = None):
        self.event_type = event_type
        self.event_id = "test-event-id"
        self.aggregate_id = "test-aggregate-id"
        self.aggregate_type = "TestAggregate"
        self.occurred_at = occurred_at or datetime.now(timezone.utc)
        self.payload = payload

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload
        }


class MockEventStore(IEventStore):
    """Mock event store for testing."""

    def __init__(self):
        self.events: List[DomainEvent] = []
        self.should_fail = False
        self.fail_on_type: Optional[str] = None

    async def append(
        self,
        stream_id: str,
        events: List[DomainEvent],
        expected_version: Optional[int] = None,
    ) -> None:
        if self.should_fail:
            raise Exception("Event store failure")
        self.events.extend(events)

    async def get_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None,
    ) -> List[DomainEvent]:
        return self.events

    async def get_events_since(
        self,
        since: datetime,
        stream_id: Optional[str] = None,
    ) -> List[DomainEvent]:
        # Handle both naive and aware datetimes
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        return [e for e in self.events if e.occurred_at >= since]

    async def stream_events(
        self,
        stream_id: Optional[str] = None,
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
        snapshot: Dict[str, Any],
    ) -> None:
        pass

    async def get_latest_snapshot(
        self,
        stream_id: str,
    ) -> Optional[Dict[str, Any]]:
        return None

    async def delete_stream(self, stream_id: str) -> None:
        self.events.clear()

    async def get_all_stream_ids(
        self,
        aggregate_type: Optional[str] = None,
    ) -> List[str]:
        return ["test-stream"]

    async def get_events_by_type(
        self, event_type: str, since: Optional[datetime] = None, limit: int = 1000
    ) -> List[DomainEvent]:
        events = [e for e in self.events if e.event_type == event_type]

        if since:
            # Normalize both datetimes to naive UTC for comparison
            since_naive = since.replace(tzinfo=None) if since.tzinfo else since
            events = [
                e for e in events
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
    ) -> List[DomainEvent]:
        return []

    async def replay_events(
        self,
        stream_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None,
    ):
        for event in self.events:
            yield event

    async def get_statistics(self) -> Dict[str, Any]:
        if self.should_fail:
            raise Exception("Failed to get statistics")
        return {
            "total_events": len(self.events),
            "event_types": len(set(e.event_type for e in self.events))
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
            version="1.0.0"
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
            version="1.0.0"
        )

        health = await metrics_service.get_system_health()

        assert health.status == ComponentHealth.UNHEALTHY
        event_store_health = next(
            (c for c in health.components if c.component_name == "event_store"), None
        )
        assert event_store_health is not None
        assert event_store_health.status == ComponentHealth.UNHEALTHY

    @pytest.mark.asyncio
    async def test_get_component_health_event_store(self):
        """Test getting health for specific component."""
        event_store = MockEventStore()
        start_time = datetime.now(timezone.utc)
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=start_time,
            version="1.0.0"
        )

        health = await metrics_service.get_component_health("event_store")

        assert health.component_name == "event_store"
        assert health.status == ComponentHealth.HEALTHY
        assert health.response_time_ms >= 0

    @pytest.mark.asyncio
    async def test_get_component_health_unknown_component(self):
        """Test requesting unknown component raises error."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        with pytest.raises(ComponentNotFoundError):
            await metrics_service.get_component_health("unknown_component")

    @pytest.mark.asyncio
    async def test_uptime_calculation(self):
        """Test uptime is calculated correctly."""
        start_time = datetime.now() - timedelta(hours=2)  # Use naive datetime
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=start_time,
            version="1.0.0"
        )

        health = await metrics_service.get_system_health()

        # Should be approximately 2 hours (allow 1 second variance)
        assert 7199 <= health.uptime_seconds <= 7201


class TestMetricsServicePerformance:
    """Tests for performance metrics."""

    @pytest.mark.asyncio
    async def test_get_performance_metrics_no_events(self):
        """Test performance metrics with no events."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc)

        metrics = await metrics_service.get_performance_metrics(start, end)

        assert metrics.active_executions == 0
        assert metrics.completed_executions_total == 0
        assert metrics.failed_executions_total == 0
        assert metrics.avg_execution_duration_seconds == 0.0

    @pytest.mark.asyncio
    async def test_get_performance_metrics_with_executions(self):
        """Test performance metrics aggregation."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        # Create test events
        now = datetime.now(timezone.utc)
        started_event = MockEvent("AgentExecutionStarted", {"agent_name": "test_agent"}, now)
        completed_event = MockEvent(
            "AgentExecutionCompleted",
            {"agent_name": "test_agent", "duration_seconds": 45.5},
            now + timedelta(seconds=45)
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
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        now = datetime.now(timezone.utc)

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
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        now = datetime.now(timezone.utc)

        # Create test events
        await event_store.append("stream-1", [MockEvent("AgentExecutionStarted", {"agent_name": "agent_a"}, now)])
        await event_store.append("stream-1", [MockEvent("AgentExecutionStarted", {"agent_name": "agent_b"}, now)])
        await event_store.append("stream-1", [
            MockEvent("AgentExecutionCompleted", {"agent_name": "agent_a", "duration_seconds": 30.0}, now + timedelta(seconds=30))
        ])
        await event_store.append("stream-1", [
            MockEvent("AgentExecutionFailed", {"agent_name": "agent_b"}, now + timedelta(seconds=10))
        ])

        metrics = await metrics_service.get_agent_execution_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1)
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
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        now = datetime.now(timezone.utc)

        # Create test events
        await event_store.append("stream-1", [MockEvent("AgentExecutionStarted", {"agent_name": "agent_a"}, now)])
        await event_store.append("stream-1", [MockEvent("AgentExecutionStarted", {"agent_name": "agent_b"}, now)])
        await event_store.append("stream-1", [
            MockEvent("AgentExecutionCompleted", {"agent_name": "agent_a", "duration_seconds": 25.0}, now + timedelta(seconds=25))
        ])

        metrics = await metrics_service.get_agent_execution_metrics(
            agent_name="agent_a",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1)
        )

        assert metrics["agent_name"] == "agent_a"
        assert metrics["total_executions"] == 1
        assert metrics["completed"] == 1

    @pytest.mark.asyncio
    async def test_get_agent_execution_metrics_duration_stats(self):
        """Test duration statistics calculation."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        now = datetime.now(timezone.utc)

        # Create multiple executions with different durations
        for i in range(3):
            await event_store.append("stream-1", [
                MockEvent("AgentExecutionStarted", {"agent_name": "test"}, now + timedelta(seconds=i*50))
            ])
            await event_store.append("stream-1", [
                MockEvent(
                    "AgentExecutionCompleted",
                    {"agent_name": "test", "duration_seconds": 10.0 + i*5},
                    now + timedelta(seconds=i*50 + 10 + i*5)
                )
            ])

        metrics = await metrics_service.get_agent_execution_metrics(
            agent_name="test",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1)
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
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        result = await metrics_service.get_active_agents()

        assert result["count"] == 0
        assert result["agents"] == []

    @pytest.mark.asyncio
    async def test_get_active_agents_with_active_executions(self):
        """Test active agents list includes only incomplete executions."""
        event_store = MockEventStore()
        start_time = datetime.now()  # Use naive datetime
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=start_time,
            version="1.0.0"
        )

        now = datetime.now()  # Use naive datetime to match service usage

        # Create test events - one active, one completed
        await event_store.append("stream-1", [
            MockEvent(
                "AgentExecutionStarted",
                {"execution_id": "exec_1", "agent_name": "agent_a", "work_item_id": "wi_1"},
                now - timedelta(hours=12)
            )
        ])
        await event_store.append("stream-1", [
            MockEvent(
                "AgentExecutionStarted",
                {"execution_id": "exec_2", "agent_name": "agent_b", "work_item_id": "wi_2"},
                now - timedelta(hours=6)
            )
        ])
        await event_store.append("stream-1", [
            MockEvent(
                "AgentExecutionCompleted",
                {"execution_id": "exec_1"},
                now - timedelta(hours=10)
            )
        ])

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
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        status = await metrics_service.get_integration_status()

        assert status.event_store_connected is True
        assert status.event_store_latency_ms is not None
        assert status.event_store_latency_ms >= 0

    @pytest.mark.asyncio
    async def test_get_integration_status_event_store_unhealthy(self):
        """Test integration status with unhealthy event store."""
        event_store = MockEventStore()
        event_store.should_fail = True

        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        status = await metrics_service.get_integration_status()

        assert status.event_store_connected is False
        assert status.event_store_latency_ms is None


class TestMetricsServiceErrorHandling:
    """Tests for error handling and graceful degradation."""

    @pytest.mark.asyncio
    async def test_metrics_with_missing_event_fields(self):
        """Test metrics calculation handles missing event fields gracefully."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        now = datetime.now(timezone.utc)

        # Event missing duration_seconds field
        incomplete_event = MockEvent(
            "AgentExecutionCompleted",
            {"agent_name": "test"},  # No duration_seconds
            now
        )
        await event_store.append("stream-1", [incomplete_event])

        # Should not raise, just handle gracefully
        metrics = await metrics_service.get_performance_metrics(
            now - timedelta(hours=1),
            now + timedelta(hours=1)
        )

        assert metrics.avg_execution_duration_seconds == 0.0

    @pytest.mark.asyncio
    async def test_get_metric_time_series_not_implemented(self):
        """Test unimplemented metric time series raises appropriate error."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        with pytest.raises(MetricNotFoundError):
            await metrics_service.get_metric_time_series(
                metric_name="unknown_metric",
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc)
            )

    @pytest.mark.asyncio
    async def test_get_resilience_metrics_placeholder(self):
        """Test resilience metrics returns placeholder values."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        now = datetime.now(timezone.utc)

        metrics = await metrics_service.get_resilience_metrics(
            start_time=now - timedelta(hours=1),
            end_time=now
        )

        # Currently returns placeholder data
        assert metrics.retry_attempts_total == 0
        assert metrics.timeout_count == 0

    @pytest.mark.asyncio
    async def test_get_simulation_mode_info(self):
        """Test simulation mode info returns expected structure."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        info = await metrics_service.get_simulation_mode_info()

        assert info.enabled is False
        assert info.time_multiplier == 1.0
        assert info.deterministic_responses is False


class TestMetricsServiceEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_performance_metrics_with_zero_duration(self):
        """Test handling of executions with zero duration."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        now = datetime.now(timezone.utc)
        await event_store.append("stream-1", [
            MockEvent("AgentExecutionCompleted", {"duration_seconds": 0.0}, now)
        ])

        metrics = await metrics_service.get_performance_metrics(
            now - timedelta(hours=1),
            now + timedelta(hours=1)
        )

        assert metrics.avg_execution_duration_seconds == 0.0

    @pytest.mark.asyncio
    async def test_get_api_usage_placeholder(self):
        """Test API usage returns placeholder structure."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        usage = await metrics_service.get_api_usage()

        assert "claude_api" in usage
        assert "github_api" in usage
        assert "checked_at" in usage
        assert usage["claude_api"]["requests_today"] == 0

    @pytest.mark.asyncio
    async def test_list_metric_names_placeholder(self):
        """Test metric names list returns empty placeholder."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        names = await metrics_service.list_metric_names()

        assert isinstance(names, list)
        assert names == []

    @pytest.mark.asyncio
    async def test_get_api_endpoint_metrics_placeholder(self):
        """Test endpoint metrics returns empty placeholder."""
        event_store = MockEventStore()
        metrics_service = MetricsService(
            event_store=event_store,
            start_time=datetime.now(timezone.utc),
            version="1.0.0"
        )

        metrics = await metrics_service.get_api_endpoint_metrics()

        assert isinstance(metrics, dict)
        assert metrics == {}
