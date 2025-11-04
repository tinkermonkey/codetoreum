"""
Integration tests for metrics REST API endpoints.

Tests system metrics, execution metrics, agent performance metrics, error rate tracking,
custom metrics, and real-time metrics streaming.
"""

import pytest
from datetime import datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.metrics import create_metrics_router
from codetoreum.ports.input.metrics_query import IMetricsQueryPort


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_metrics_query_port() -> AsyncMock:
    """Create mock metrics query port for testing."""
    return AsyncMock(spec=IMetricsQueryPort)


@pytest.fixture
def test_app(mock_metrics_query_port: AsyncMock) -> FastAPI:
    """Create test FastAPI application with metrics router."""
    app = FastAPI()

    # Create router without authentication for testing
    router = create_metrics_router(
        query_port=mock_metrics_query_port,
        auth_deps=None,
    )

    app.include_router(router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Create test client for making HTTP requests."""
    return TestClient(test_app)


# ============================================================================
# System Metrics Tests
# ============================================================================

class TestSystemMetrics:
    """Tests for system metrics endpoints."""

    @pytest.mark.asyncio
    async def test_get_system_metrics_current(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving current system metrics."""
        # Arrange
        mock_metrics_query_port.get_system_metrics.return_value = {
            "timestamp": datetime.utcnow().isoformat(),
            "cpu_usage_percent": 45.2,
            "memory_usage_percent": 62.8,
            "disk_usage_percent": 38.5,
            "network_rx_bytes": 1024000,
            "network_tx_bytes": 512000,
            "active_executions": 3,
            "queued_executions": 7,
        }

        # Act
        response = client.get("/api/v2/metrics/system")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["cpu_usage_percent"] == 45.2
        assert data["memory_usage_percent"] == 62.8
        assert data["active_executions"] == 3

    @pytest.mark.asyncio
    async def test_get_system_metrics_time_range(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving system metrics over time range."""
        # Arrange
        now = datetime.utcnow()
        mock_metrics_query_port.get_system_metrics_time_series.return_value = {
            "metrics": [
                {
                    "timestamp": (now - timedelta(minutes=5)).isoformat(),
                    "cpu_usage_percent": 40.0,
                    "memory_usage_percent": 60.0,
                },
                {
                    "timestamp": now.isoformat(),
                    "cpu_usage_percent": 45.0,
                    "memory_usage_percent": 62.0,
                },
            ],
            "start_time": (now - timedelta(hours=1)).isoformat(),
            "end_time": now.isoformat(),
            "interval_seconds": 300,
        }

        # Act
        response = client.get(
            "/api/v2/metrics/system/time-series"
            f"?start_time={(now - timedelta(hours=1)).isoformat()}"
            f"&end_time={now.isoformat()}"
            "&interval=5m"
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["metrics"]) == 2
        assert data["interval_seconds"] == 300

    @pytest.mark.asyncio
    async def test_get_system_metrics_aggregated(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving aggregated system metrics."""
        # Arrange
        mock_metrics_query_port.get_system_metrics_aggregated.return_value = {
            "cpu_usage": {
                "min": 20.5,
                "max": 85.2,
                "avg": 45.3,
                "p50": 42.0,
                "p95": 75.0,
                "p99": 82.0,
            },
            "memory_usage": {
                "min": 50.0,
                "max": 90.0,
                "avg": 65.2,
                "p50": 64.0,
                "p95": 85.0,
                "p99": 88.0,
            },
        }

        # Act
        response = client.get("/api/v2/metrics/system/aggregated?period=1h")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["cpu_usage"]["avg"] == 45.3
        assert data["memory_usage"]["p95"] == 85.0


# ============================================================================
# Execution Metrics Tests
# ============================================================================

class TestExecutionMetrics:
    """Tests for execution metrics endpoints."""

    @pytest.mark.asyncio
    async def test_get_execution_metrics_all(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving execution metrics for all executions."""
        # Arrange
        mock_metrics_query_port.get_execution_metrics.return_value = {
            "total_executions": 150,
            "successful_executions": 135,
            "failed_executions": 15,
            "success_rate": 0.90,
            "avg_duration_seconds": 245.5,
            "median_duration_seconds": 220.0,
            "p95_duration_seconds": 450.0,
        }

        # Act
        response = client.get("/api/v2/metrics/executions")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_executions"] == 150
        assert data["success_rate"] == 0.90
        assert data["avg_duration_seconds"] == 245.5

    @pytest.mark.asyncio
    async def test_get_execution_metrics_filtered_by_agent(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving execution metrics filtered by agent."""
        # Arrange
        mock_metrics_query_port.get_execution_metrics.return_value = {
            "total_executions": 50,
            "successful_executions": 48,
            "failed_executions": 2,
            "success_rate": 0.96,
            "agent_id": "agent-123",
        }

        # Act
        response = client.get("/api/v2/metrics/executions?agent_id=agent-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["agent_id"] == "agent-123"
        assert data["success_rate"] == 0.96

    @pytest.mark.asyncio
    async def test_get_execution_metrics_time_range(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving execution metrics within time range."""
        # Arrange
        now = datetime.utcnow()
        start_time = (now - timedelta(days=7)).isoformat()
        end_time = now.isoformat()

        mock_metrics_query_port.get_execution_metrics.return_value = {
            "total_executions": 200,
            "start_time": start_time,
            "end_time": end_time,
        }

        # Act
        response = client.get(
            f"/api/v2/metrics/executions?start_time={start_time}&end_time={end_time}"
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_executions"] == 200

    @pytest.mark.asyncio
    async def test_get_execution_metrics_by_status(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving execution metrics grouped by status."""
        # Arrange
        mock_metrics_query_port.get_execution_metrics_by_status.return_value = {
            "completed": {"count": 135, "avg_duration": 240.5},
            "failed": {"count": 15, "avg_duration": 180.0},
            "timeout": {"count": 5, "avg_duration": 600.0},
            "cancelled": {"count": 3, "avg_duration": 120.0},
        }

        # Act
        response = client.get("/api/v2/metrics/executions/by-status")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["completed"]["count"] == 135
        assert data["failed"]["count"] == 15


# ============================================================================
# Agent Performance Metrics Tests
# ============================================================================

class TestAgentPerformanceMetrics:
    """Tests for agent performance metrics endpoints."""

    @pytest.mark.asyncio
    async def test_get_agent_performance_metrics(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving performance metrics for specific agent."""
        # Arrange
        mock_metrics_query_port.get_agent_performance.return_value = {
            "agent_id": "agent-123",
            "total_executions": 75,
            "success_rate": 0.94,
            "avg_duration_seconds": 210.0,
            "avg_tokens_used": 3500,
            "avg_cost_usd": 0.15,
            "capability_performance": {
                "code_analysis": {"success_rate": 0.95, "avg_duration": 180.0},
                "bug_fix": {"success_rate": 0.92, "avg_duration": 240.0},
            },
        }

        # Act
        response = client.get("/api/v2/metrics/agents/agent-123/performance")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["agent_id"] == "agent-123"
        assert data["success_rate"] == 0.94
        assert "code_analysis" in data["capability_performance"]

    @pytest.mark.asyncio
    async def test_get_agent_performance_leaderboard(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving agent performance leaderboard."""
        # Arrange
        mock_metrics_query_port.get_agent_leaderboard.return_value = {
            "agents": [
                {
                    "agent_id": "agent-123",
                    "name": "Agent A",
                    "success_rate": 0.95,
                    "total_executions": 100,
                    "rank": 1,
                },
                {
                    "agent_id": "agent-456",
                    "name": "Agent B",
                    "success_rate": 0.90,
                    "total_executions": 80,
                    "rank": 2,
                },
            ],
            "metric": "success_rate",
        }

        # Act
        response = client.get("/api/v2/metrics/agents/leaderboard?metric=success_rate")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["agents"]) == 2
        assert data["agents"][0]["rank"] == 1

    @pytest.mark.asyncio
    async def test_get_agent_resource_usage(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving agent resource usage metrics."""
        # Arrange
        mock_metrics_query_port.get_agent_resource_usage.return_value = {
            "agent_id": "agent-123",
            "avg_cpu_usage_percent": 55.0,
            "avg_memory_usage_mb": 512,
            "avg_execution_time_seconds": 220.0,
            "total_compute_hours": 15.5,
        }

        # Act
        response = client.get("/api/v2/metrics/agents/agent-123/resources")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["avg_cpu_usage_percent"] == 55.0


# ============================================================================
# Workflow Metrics Tests
# ============================================================================

class TestWorkflowMetrics:
    """Tests for workflow metrics endpoints."""

    @pytest.mark.asyncio
    async def test_get_workflow_metrics(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving metrics for specific workflow."""
        # Arrange
        mock_metrics_query_port.get_workflow_metrics.return_value = {
            "workflow_id": "workflow-123",
            "total_executions": 45,
            "successful_completions": 40,
            "success_rate": 0.89,
            "avg_duration_seconds": 1200.0,
            "stage_metrics": {
                "analysis": {"avg_duration": 300.0, "success_rate": 0.95},
                "implementation": {"avg_duration": 600.0, "success_rate": 0.90},
                "review": {"avg_duration": 300.0, "success_rate": 0.92},
            },
        }

        # Act
        response = client.get("/api/v2/metrics/workflows/workflow-123")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["workflow_id"] == "workflow-123"
        assert data["success_rate"] == 0.89
        assert "stage_metrics" in data

    @pytest.mark.asyncio
    async def test_get_workflow_stage_bottlenecks(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test identifying workflow stage bottlenecks."""
        # Arrange
        mock_metrics_query_port.get_workflow_bottlenecks.return_value = {
            "workflow_id": "workflow-123",
            "bottlenecks": [
                {
                    "stage": "implementation",
                    "avg_duration": 900.0,
                    "p95_duration": 1800.0,
                    "failure_rate": 0.15,
                },
            ],
        }

        # Act
        response = client.get("/api/v2/metrics/workflows/workflow-123/bottlenecks")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["bottlenecks"]) == 1
        assert data["bottlenecks"][0]["stage"] == "implementation"


# ============================================================================
# Error Rate Tracking Tests
# ============================================================================

class TestErrorRateTracking:
    """Tests for error rate tracking endpoints."""

    @pytest.mark.asyncio
    async def test_get_error_rates_overall(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving overall error rates."""
        # Arrange
        mock_metrics_query_port.get_error_rates.return_value = {
            "total_errors": 25,
            "error_rate": 0.10,
            "errors_by_type": {
                "agent_failure": 10,
                "container_crash": 8,
                "timeout": 5,
                "network_error": 2,
            },
            "errors_by_agent": {
                "agent-123": 15,
                "agent-456": 10,
            },
        }

        # Act
        response = client.get("/api/v2/metrics/errors")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_errors"] == 25
        assert data["error_rate"] == 0.10

    @pytest.mark.asyncio
    async def test_get_error_rates_time_series(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving error rate time series."""
        # Arrange
        now = datetime.utcnow()
        mock_metrics_query_port.get_error_rate_time_series.return_value = {
            "data_points": [
                {
                    "timestamp": (now - timedelta(hours=2)).isoformat(),
                    "error_rate": 0.08,
                    "error_count": 4,
                },
                {
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                    "error_rate": 0.12,
                    "error_count": 6,
                },
            ],
            "interval_seconds": 3600,
        }

        # Act
        response = client.get("/api/v2/metrics/errors/time-series?interval=1h")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["data_points"]) == 2

    @pytest.mark.asyncio
    async def test_get_error_details_by_type(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving detailed error information by type."""
        # Arrange
        mock_metrics_query_port.get_error_details.return_value = {
            "error_type": "agent_failure",
            "total_count": 10,
            "recent_errors": [
                {
                    "execution_id": "exec-123",
                    "timestamp": datetime.utcnow().isoformat(),
                    "error_message": "Model API rate limit exceeded",
                },
            ],
            "common_causes": [
                {"cause": "rate_limit", "count": 6},
                {"cause": "invalid_response", "count": 4},
            ],
        }

        # Act
        response = client.get("/api/v2/metrics/errors/agent_failure")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["error_type"] == "agent_failure"
        assert len(data["common_causes"]) == 2


# ============================================================================
# Custom Metrics Tests
# ============================================================================

class TestCustomMetrics:
    """Tests for custom metrics recording and retrieval."""

    @pytest.mark.asyncio
    async def test_record_custom_metric(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test recording a custom metric."""
        # Act - Note: This would typically use a command port
        response = client.post(
            "/api/v2/metrics/custom",
            json={
                "name": "code_quality_score",
                "value": 85.5,
                "tags": {"project": "proj-123", "agent": "agent-analyzer"},
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_get_custom_metric_values(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test retrieving custom metric values."""
        # Arrange
        mock_metrics_query_port.get_custom_metric.return_value = {
            "name": "code_quality_score",
            "values": [
                {"timestamp": datetime.utcnow().isoformat(), "value": 85.5},
                {
                    "timestamp": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
                    "value": 82.0,
                },
            ],
            "aggregations": {"min": 82.0, "max": 85.5, "avg": 83.75},
        }

        # Act
        response = client.get("/api/v2/metrics/custom/code_quality_score")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "code_quality_score"
        assert len(data["values"]) == 2


# ============================================================================
# Metric Aggregation Tests
# ============================================================================

class TestMetricAggregation:
    """Tests for metric aggregation endpoints."""

    @pytest.mark.asyncio
    async def test_aggregate_metrics_hourly(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test hourly metric aggregation."""
        # Arrange
        mock_metrics_query_port.aggregate_metrics.return_value = {
            "aggregation_period": "hourly",
            "data_points": [
                {
                    "timestamp": datetime.utcnow().replace(minute=0, second=0).isoformat(),
                    "total_executions": 25,
                    "successful_executions": 23,
                    "avg_duration": 230.5,
                }
            ],
        }

        # Act
        response = client.get("/api/v2/metrics/aggregate?period=hourly&metric=executions")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["aggregation_period"] == "hourly"

    @pytest.mark.asyncio
    async def test_aggregate_metrics_daily(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test daily metric aggregation."""
        # Arrange
        mock_metrics_query_port.aggregate_metrics.return_value = {
            "aggregation_period": "daily",
            "data_points": [
                {
                    "date": datetime.utcnow().date().isoformat(),
                    "total_executions": 150,
                    "successful_executions": 135,
                }
            ],
        }

        # Act
        response = client.get("/api/v2/metrics/aggregate?period=daily&metric=executions")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["aggregation_period"] == "daily"


# ============================================================================
# Real-time Metrics Streaming Tests
# ============================================================================

class TestRealTimeMetricsStreaming:
    """Tests for real-time metrics streaming via WebSocket."""

    @pytest.mark.asyncio
    async def test_subscribe_to_metrics_stream(
        self,
        client: TestClient,
    ):
        """Test subscribing to real-time metrics stream."""
        # Note: WebSocket testing requires special setup
        # This is a placeholder showing the endpoint structure

        # WebSocket endpoint would be at ws://host/api/v2/metrics/stream
        # Clients would connect and receive real-time metric updates
        pass

    @pytest.mark.asyncio
    async def test_metrics_stream_filtering(
        self,
        client: TestClient,
    ):
        """Test filtering metrics stream by metric type."""
        # WebSocket connection with filter parameter:
        # ws://host/api/v2/metrics/stream?metrics=system,executions
        pass


# ============================================================================
# Health Check Tests
# ============================================================================

class TestMetricsHealth:
    """Tests for metrics system health endpoints."""

    @pytest.mark.asyncio
    async def test_metrics_health_check(
        self,
        client: TestClient,
        mock_metrics_query_port: AsyncMock,
    ):
        """Test metrics system health check."""
        # Arrange
        mock_metrics_query_port.health_check.return_value = {
            "status": "healthy",
            "metrics_collection_running": True,
            "last_collection_time": datetime.utcnow().isoformat(),
            "storage_available": True,
        }

        # Act
        response = client.get("/api/v2/metrics/health")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
