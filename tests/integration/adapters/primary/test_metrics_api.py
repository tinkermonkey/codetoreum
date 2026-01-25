"""Integration tests for Metrics REST API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.metrics import create_metrics_router
from codetoreum.ports.input.metrics_query import IMetricsQueryPort


class MockMetricsQueryPort(IMetricsQueryPort):
    """Mock implementation of metrics query port for testing."""

    def __init__(self):
        self._get_system_health = AsyncMock()
        self._get_component_health = AsyncMock()
        self._get_performance_metrics = AsyncMock()
        self._get_resilience_metrics = AsyncMock()
        self._get_integration_status = AsyncMock()
        self._get_simulation_mode_info = AsyncMock()
        self._get_metric_time_series = AsyncMock()
        self._list_metric_names = AsyncMock()
        self._get_api_endpoint_metrics = AsyncMock()
        self._get_agent_execution_metrics = AsyncMock()
        self._get_active_agents = AsyncMock()
        self._get_api_usage = AsyncMock()

    async def get_system_health(self):
        return await self._get_system_health()

    async def get_component_health(self, component_name):
        return await self._get_component_health(component_name)

    async def get_performance_metrics(self, start_time, end_time, aggregation_window_seconds=60):
        return await self._get_performance_metrics(start_time, end_time, aggregation_window_seconds)

    async def get_resilience_metrics(self, start_time, end_time):
        return await self._get_resilience_metrics(start_time, end_time)

    async def get_integration_status(self):
        return await self._get_integration_status()

    async def get_simulation_mode_info(self):
        return await self._get_simulation_mode_info()

    async def get_metric_time_series(self, metric_name, start_time, end_time, labels=None, aggregation=None):
        return await self._get_metric_time_series(metric_name, start_time, end_time, labels, aggregation)

    async def list_metric_names(self, prefix=None):
        return await self._list_metric_names(prefix)

    async def get_api_endpoint_metrics(self, endpoint_path=None, start_time=None, end_time=None):
        return await self._get_api_endpoint_metrics(endpoint_path, start_time, end_time)

    async def get_agent_execution_metrics(self, agent_name=None, start_time=None, end_time=None):
        return await self._get_agent_execution_metrics(agent_name, start_time, end_time)

    async def get_active_agents(self):
        return await self._get_active_agents()

    async def get_api_usage(self):
        return await self._get_api_usage()

    async def get_repair_cycle_metrics(self, agent_name=None, start_time=None, end_time=None):
        if not hasattr(self, '_get_repair_cycle_metrics'):
            self._get_repair_cycle_metrics = AsyncMock()
        return await self._get_repair_cycle_metrics(agent_name, start_time, end_time)


@pytest.fixture
def mock_query_port():
    """Fixture providing mock metrics query port."""
    return MockMetricsQueryPort()


@pytest.fixture
def app(mock_query_port):
    """Fixture providing FastAPI test application."""
    app = FastAPI()

    # Create and include metrics router (without auth for testing)
    router = create_metrics_router(
        metrics_query_port=mock_query_port,
        auth_deps=None,  # Disable auth for testing
    )
    app.include_router(router)

    return app


@pytest.fixture
def client(app):
    """Fixture providing test client."""
    with TestClient(app) as test_client:
        yield test_client


class TestActiveAgents:
    """Tests for GET /api/v2/metrics/active-agents endpoint."""

    def test_get_active_agents_success(self, client, mock_query_port):
        """Test successful active agents retrieval."""
        # Arrange
        now = datetime.now(timezone.utc)
        active_agents = {
            "agents": [
                {
                    "execution_id": "exec-123",
                    "agent_name": "developer_agent",
                    "work_item_id": "wi-456",
                    "project": "codetoreum",
                    "issue_number": 42,
                    "status": "running",
                    "started_at": now,
                    "container_name": "claude-code-exec-123",
                },
                {
                    "execution_id": "exec-124",
                    "agent_name": "reviewer_agent",
                    "work_item_id": "wi-457",
                    "project": "codetoreum",
                    "issue_number": 43,
                    "status": "running",
                    "started_at": now,
                    "container_name": "claude-code-exec-124",
                },
            ]
        }
        mock_query_port._get_active_agents.return_value = active_agents

        # Act
        response = client.get("/api/v2/metrics/active-agents")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["agents"]) == 2
        assert data["agents"][0]["executionId"] == "exec-123"
        assert data["agents"][0]["agentName"] == "developer_agent"
        assert data["agents"][1]["executionId"] == "exec-124"
        assert data["agents"][1]["agentName"] == "reviewer_agent"

        # Verify query port was called
        mock_query_port._get_active_agents.assert_called_once()

    def test_get_active_agents_empty(self, client, mock_query_port):
        """Test active agents retrieval with no active agents."""
        # Arrange
        mock_query_port._get_active_agents.return_value = {"agents": []}

        # Act
        response = client.get("/api/v2/metrics/active-agents")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["agents"] == []


class TestApiUsage:
    """Tests for GET /api/v2/metrics/api-usage endpoint."""

    def test_get_api_usage_success(self, client, mock_query_port):
        """Test successful API usage retrieval."""
        # Arrange
        api_usage = {
            "claude": {
                "available": True,
                "weekly_usage": 15000000,
                "weekly_quota": 50000000,
                "session_usage": 2000000,
                "session_quota": 10000000,
                "session_remaining_minutes": 45,
            }
        }
        mock_query_port._get_api_usage.return_value = api_usage

        # Act
        response = client.get("/api/v2/metrics/api-usage")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["claude"]["available"] is True
        assert data["claude"]["weeklyUsage"] == 15000000
        assert data["claude"]["weeklyQuota"] == 50000000
        assert data["claude"]["weeklyUsagePercent"] == 30.0
        assert data["claude"]["sessionUsage"] == 2000000
        assert data["claude"]["sessionQuota"] == 10000000
        assert data["claude"]["sessionUsagePercent"] == 20.0
        assert data["claude"]["sessionRemainingMinutes"] == 45

        # Verify query port was called
        mock_query_port._get_api_usage.assert_called_once()

    def test_get_api_usage_unavailable(self, client, mock_query_port):
        """Test API usage retrieval when API is unavailable."""
        # Arrange
        api_usage = {
            "claude": {
                "available": False,
                "weekly_usage": 0,
                "weekly_quota": 50000000,
                "session_usage": 0,
                "session_quota": 10000000,
                "session_remaining_minutes": 0,
            }
        }
        mock_query_port._get_api_usage.return_value = api_usage

        # Act
        response = client.get("/api/v2/metrics/api-usage")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["claude"]["available"] is False
        assert data["claude"]["weeklyUsagePercent"] == 0.0
        assert data["claude"]["sessionRemainingMinutes"] == 0

    def test_get_api_usage_high_usage(self, client, mock_query_port):
        """Test API usage retrieval with high usage percentage."""
        # Arrange
        api_usage = {
            "claude": {
                "available": True,
                "weekly_usage": 48000000,
                "weekly_quota": 50000000,
                "session_usage": 9500000,
                "session_quota": 10000000,
                "session_remaining_minutes": 5,
            }
        }
        mock_query_port._get_api_usage.return_value = api_usage

        # Act
        response = client.get("/api/v2/metrics/api-usage")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["claude"]["weeklyUsagePercent"] == 96.0
        assert data["claude"]["sessionUsagePercent"] == 95.0
        assert data["claude"]["sessionRemainingMinutes"] == 5
