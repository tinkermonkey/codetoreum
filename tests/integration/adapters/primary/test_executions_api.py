"""Integration tests for Executions REST API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.executions import create_executions_router
from codetoreum.domain.agent_execution import ExecutionStatus
from codetoreum.ports.input.execution_command import (
    ExecutionCommandResult,
    IExecutionCommandPort,
    TerminateExecutionCommand,
)
from codetoreum.ports.input.execution_query import (
    ContainerStatus,
    ErrorType,
    ExecutionErrorDetail,
    ExecutionFilters,
    ExecutionInfo,
    ExecutionPaginationParams,
    ExecutionSortField,
    IExecutionQueryPort,
    LogEntry,
    SortOrder,
)


# ============================================================================
# Mock Implementations
# ============================================================================


class MockExecutionCommandPort(IExecutionCommandPort):
    """Mock implementation of execution command port for testing."""

    def __init__(self):
        self._terminate_execution = AsyncMock()
        self._pause_execution = AsyncMock()
        self._resume_execution = AsyncMock()

    async def terminate_execution(self, command):
        return await self._terminate_execution(command)

    async def pause_execution(self, command):
        return await self._pause_execution(command)

    async def resume_execution(self, command):
        return await self._resume_execution(command)


class MockExecutionQueryPort(IExecutionQueryPort):
    """Mock implementation of execution query port for testing."""

    def __init__(self):
        self._get_execution = AsyncMock()
        self._list_executions = AsyncMock()
        self._get_execution_logs = AsyncMock()
        self._get_execution_history = AsyncMock()
        self._count_executions = AsyncMock()

    async def get_execution(self, execution_id):
        return await self._get_execution(execution_id)

    async def list_executions(self, filters=None, pagination=None):
        return await self._list_executions(filters, pagination)

    async def get_execution_logs(self, execution_id, stage=None, tail=None):
        return await self._get_execution_logs(execution_id, stage, tail)

    async def get_execution_history(self, execution_id, limit=None):
        return await self._get_execution_history(execution_id, limit)

    async def count_executions(self, filters=None):
        return await self._count_executions(filters)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_command_port():
    """Fixture providing mock execution command port."""
    return MockExecutionCommandPort()


@pytest.fixture
def mock_query_port():
    """Fixture providing mock execution query port."""
    return MockExecutionQueryPort()


@pytest.fixture
def app(mock_command_port, mock_query_port):
    """Fixture providing FastAPI test application."""
    app = FastAPI()

    # Create and include executions router (without auth for testing)
    router = create_executions_router(
        command_port=mock_command_port,
        query_port=mock_query_port,
        auth_deps=None,  # Disable auth for testing
    )
    app.include_router(router)

    return app


@pytest.fixture
def client(app):
    """Fixture providing test client."""
    return TestClient(app)


@pytest.fixture
def sample_execution_info():
    """Fixture providing a sample execution info."""
    now = datetime.now(timezone.utc)
    return ExecutionInfo(
        id="exec-123",
        agent_id="agent-123",
        agent_name="test-agent",
        work_item_id="wi-123",
        workflow_id="wf-123",
        stage_name="development",
        status=ExecutionStatus.COMPLETED,
        container_name="test-container",
        container_id="container-123",
        output="Test output",
        error_message=None,
        error_detail=None,
        exit_code=0,
        input_tokens=1000,
        output_tokens=500,
        duration_seconds=120.5,
        initialized_at=now,
        started_at=now,
        completed_at=now,
        elapsed_time_seconds=120.5,
        current_stage="development",
    )


@pytest.fixture
def failed_execution_info():
    """Fixture providing a failed execution info."""
    now = datetime.now(timezone.utc)
    return ExecutionInfo(
        id="exec-failed",
        agent_id="agent-123",
        agent_name="test-agent",
        work_item_id="wi-123",
        workflow_id="wf-123",
        stage_name="testing",
        status=ExecutionStatus.FAILED,
        container_name="test-container",
        container_id="container-456",
        output="Partial output",
        error_message="Agent logic error",
        error_detail=ExecutionErrorDetail(
            error_type=ErrorType.AGENT_FAILURE,
            message="Test suite failed with 3 failures",
            partial_logs_available=False,
        ),
        exit_code=1,
        input_tokens=800,
        output_tokens=200,
        duration_seconds=45.2,
        initialized_at=now,
        started_at=now,
        completed_at=now,
        elapsed_time_seconds=45.2,
        current_stage="testing",
    )


@pytest.fixture
def crashed_execution_info():
    """Fixture providing a container crash execution info."""
    now = datetime.now(timezone.utc)
    return ExecutionInfo(
        id="exec-crashed",
        agent_id="agent-123",
        agent_name="test-agent",
        work_item_id="wi-123",
        workflow_id="wf-123",
        stage_name="development",
        status=ExecutionStatus.FAILED,
        container_name="crashed-container",
        container_id="container-789",
        output="Partial output before crash",
        error_message="Container exited unexpectedly",
        error_detail=ExecutionErrorDetail(
            error_type=ErrorType.CONTAINER_CRASHED,
            message="Container crashed with exit code 137 (OOM)",
            container_status=ContainerStatus(
                container_id="container-789",
                container_name="crashed-container",
                last_known_status="running",
                exit_code=137,
            ),
            partial_logs_available=True,
        ),
        exit_code=137,
        input_tokens=500,
        output_tokens=100,
        duration_seconds=10.5,
        initialized_at=now,
        started_at=now,
        completed_at=now,
        elapsed_time_seconds=10.5,
        current_stage="development",
    )


# ============================================================================
# Test Cases
# ============================================================================


class TestListExecutions:
    """Tests for GET /api/v2/executions endpoint."""

    def test_list_executions_success(
        self, client, mock_query_port, sample_execution_info
    ):
        """Test successful executions listing."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionListResult

        mock_query_port._list_executions.return_value = ExecutionListResult(
            executions=[sample_execution_info],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get("/api/v2/executions")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["executions"]) == 1
        assert data["executions"][0]["id"] == "exec-123"
        assert data["executions"][0]["status"] == "completed"
        assert data["has_next"] is False

    def test_list_executions_with_status_filter(
        self, client, mock_query_port, failed_execution_info
    ):
        """Test executions listing with status filter."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionListResult

        mock_query_port._list_executions.return_value = ExecutionListResult(
            executions=[failed_execution_info],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get("/api/v2/executions?status=failed")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert data["executions"][0]["status"] == "failed"

        # Verify filters were applied
        mock_query_port._list_executions.assert_called_once()
        call_args = mock_query_port._list_executions.call_args[0]
        filters = call_args[0]
        assert filters.status == ExecutionStatus.FAILED

    def test_list_executions_with_invalid_status(self, client):
        """Test executions listing with invalid status filter."""
        # Act
        response = client.get("/api/v2/executions?status=invalid_status")

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "Invalid status" in data["detail"]

    def test_list_executions_with_multiple_filters(
        self, client, mock_query_port, sample_execution_info
    ):
        """Test executions listing with multiple filters."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionListResult

        mock_query_port._list_executions.return_value = ExecutionListResult(
            executions=[sample_execution_info],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get(
            "/api/v2/executions?status=completed&work_item_id=wi-123&workflow_id=wf-123&stage_name=development"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1

        # Verify filters were applied
        mock_query_port._list_executions.assert_called_once()
        call_args = mock_query_port._list_executions.call_args[0]
        filters = call_args[0]
        assert filters.status == ExecutionStatus.COMPLETED
        assert filters.work_item_id == "wi-123"
        assert filters.workflow_id == "wf-123"
        assert filters.stage_name == "development"

    def test_list_executions_with_date_range(
        self, client, mock_query_port, sample_execution_info
    ):
        """Test executions listing with date range filter."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionListResult

        mock_query_port._list_executions.return_value = ExecutionListResult(
            executions=[sample_execution_info],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get(
            "/api/v2/executions?start_date=2025-01-01&end_date=2025-01-31"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1

        # Verify filters were applied
        mock_query_port._list_executions.assert_called_once()
        call_args = mock_query_port._list_executions.call_args[0]
        filters = call_args[0]
        assert filters.start_date is not None
        assert filters.end_date is not None

    def test_list_executions_with_invalid_date_format(self, client):
        """Test executions listing with invalid date format."""
        # Act
        response = client.get("/api/v2/executions?start_date=invalid-date")

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "Invalid start_date format" in data["detail"]

    def test_list_executions_with_invalid_date_range(self, client):
        """Test executions listing with invalid date range (start > end)."""
        # Act
        response = client.get(
            "/api/v2/executions?start_date=2025-01-31&end_date=2025-01-01"
        )

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "Invalid date range" in data["detail"]

    def test_list_executions_with_pagination(
        self, client, mock_query_port, sample_execution_info
    ):
        """Test executions listing with pagination."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionListResult

        mock_query_port._list_executions.return_value = ExecutionListResult(
            executions=[sample_execution_info],
            total_count=100,
            offset=20,
            limit=50,
            has_next=True,
        )

        # Act
        response = client.get("/api/v2/executions?offset=20&limit=50")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 100
        assert data["page"] == 1  # (offset=20 / limit=50) + 1 = 1
        assert data["page_size"] == 50
        assert data["has_next"] is True

    def test_list_executions_with_sorting(
        self, client, mock_query_port, sample_execution_info
    ):
        """Test executions listing with sorting."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionListResult

        mock_query_port._list_executions.return_value = ExecutionListResult(
            executions=[sample_execution_info],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get(
            "/api/v2/executions?sort_by=duration_seconds&sort_order=asc"
        )

        # Assert
        assert response.status_code == 200

        # Verify sorting was applied
        mock_query_port._list_executions.assert_called_once()
        call_args = mock_query_port._list_executions.call_args[0]
        pagination = call_args[1]
        assert pagination.sort_by == ExecutionSortField.DURATION
        assert pagination.sort_order == SortOrder.ASC

    def test_list_executions_with_invalid_sort_field(self, client):
        """Test executions listing with invalid sort field."""
        # Act
        response = client.get("/api/v2/executions?sort_by=invalid_field")

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "Invalid sort field" in data["detail"]

    def test_list_executions_empty_result(self, client, mock_query_port):
        """Test executions listing with no results."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionListResult

        mock_query_port._list_executions.return_value = ExecutionListResult(
            executions=[],
            total_count=0,
            offset=0,
            limit=20,
            has_next=False,
        )

        # Act
        response = client.get("/api/v2/executions")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0
        assert len(data["executions"]) == 0


class TestGetExecution:
    """Tests for GET /api/v2/executions/{id} endpoint."""

    def test_get_execution_success(
        self, client, mock_query_port, sample_execution_info
    ):
        """Test successful execution retrieval."""
        # Arrange
        mock_query_port._get_execution.return_value = sample_execution_info

        # Act
        response = client.get("/api/v2/executions/exec-123")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "exec-123"
        assert data["agent_name"] == "test-agent"
        assert data["status"] == "completed"
        assert data["duration_seconds"] == 120.5
        assert data["input_tokens"] == 1000
        assert data["output_tokens"] == 500

    def test_get_execution_with_agent_failure(
        self, client, mock_query_port, failed_execution_info
    ):
        """Test execution retrieval with agent failure error detail."""
        # Arrange
        mock_query_port._get_execution.return_value = failed_execution_info

        # Act
        response = client.get("/api/v2/executions/exec-failed")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "exec-failed"
        assert data["status"] == "failed"
        assert data["error_message"] == "Agent logic error"
        assert data["error_detail"] is not None
        assert data["error_detail"]["error_type"] == "AGENT_FAILURE"
        assert data["error_detail"]["message"] == "Test suite failed with 3 failures"
        assert data["error_detail"]["partial_logs_available"] is False

    def test_get_execution_with_container_crash(
        self, client, mock_query_port, crashed_execution_info
    ):
        """Test execution retrieval with container crash error detail."""
        # Arrange
        mock_query_port._get_execution.return_value = crashed_execution_info

        # Act
        response = client.get("/api/v2/executions/exec-crashed")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "exec-crashed"
        assert data["status"] == "failed"
        assert data["error_message"] == "Container exited unexpectedly"
        assert data["error_detail"] is not None
        assert data["error_detail"]["error_type"] == "CONTAINER_CRASHED"
        assert data["error_detail"]["container_status"] is not None
        assert data["error_detail"]["container_status"]["exit_code"] == 137
        assert data["error_detail"]["partial_logs_available"] is True

    def test_get_execution_with_timeout(self, client, mock_query_port):
        """Test execution retrieval with timeout error."""
        # Arrange
        now = datetime.now(timezone.utc)
        timeout_execution = ExecutionInfo(
            id="exec-timeout",
            agent_id="agent-123",
            agent_name="test-agent",
            work_item_id="wi-123",
            workflow_id="wf-123",
            stage_name="development",
            status=ExecutionStatus.TIMEOUT,
            container_name="timeout-container",
            container_id="container-999",
            output="Partial output before timeout",
            error_message="Execution exceeded timeout",
            error_detail=ExecutionErrorDetail(
                error_type=ErrorType.EXECUTION_TIMEOUT,
                message="Execution timed out after 300 seconds",
                partial_logs_available=True,
            ),
            exit_code=None,
            input_tokens=1500,
            output_tokens=300,
            duration_seconds=300.0,
            initialized_at=now,
            started_at=now,
            completed_at=now,
            elapsed_time_seconds=300.0,
            current_stage="development",
        )
        mock_query_port._get_execution.return_value = timeout_execution

        # Act
        response = client.get("/api/v2/executions/exec-timeout")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "exec-timeout"
        assert data["status"] == "timeout"
        assert data["error_detail"]["error_type"] == "EXECUTION_TIMEOUT"
        assert data["error_detail"]["partial_logs_available"] is True

    def test_get_execution_not_found(self, client, mock_query_port):
        """Test execution retrieval when not found."""
        # Arrange
        mock_query_port._get_execution.side_effect = ValueError(
            "Execution with ID 'exec-nonexistent' not found"
        )

        # Act
        response = client.get("/api/v2/executions/exec-nonexistent")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "Execution not found" in data["detail"]


class TestGetExecutionLogs:
    """Tests for GET /api/v2/executions/{id}/logs endpoint."""

    def test_get_execution_logs_success(self, client, mock_query_port):
        """Test successful execution logs retrieval."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionLogs

        now = datetime.now(timezone.utc)
        mock_query_port._get_execution_logs.return_value = ExecutionLogs(
            execution_id="exec-123",
            logs=[
                LogEntry(
                    timestamp=now,
                    level="INFO",
                    message="Starting execution",
                    stage="initialization",
                ),
                LogEntry(
                    timestamp=now,
                    level="INFO",
                    message="Running tests",
                    stage="development",
                ),
                LogEntry(
                    timestamp=now,
                    level="INFO",
                    message="Execution completed",
                    stage="development",
                ),
            ],
            total_lines=3,
            has_more=False,
            stage=None,
        )

        # Act
        response = client.get("/api/v2/executions/exec-123/logs")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == "exec-123"
        assert len(data["logs"]) == 3
        assert data["logs"][0]["message"] == "Starting execution"
        assert data["logs"][0]["stage"] == "initialization"
        assert data["total_lines"] == 3
        assert data["has_more"] is False

    def test_get_execution_logs_with_tail(self, client, mock_query_port):
        """Test execution logs retrieval with tail parameter."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionLogs

        now = datetime.now(timezone.utc)
        mock_query_port._get_execution_logs.return_value = ExecutionLogs(
            execution_id="exec-123",
            logs=[
                LogEntry(
                    timestamp=now,
                    level="INFO",
                    message="Last log entry",
                    stage="development",
                ),
            ],
            total_lines=1,
            has_more=True,
            stage=None,
        )

        # Act
        response = client.get("/api/v2/executions/exec-123/logs?tail=1")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) == 1
        assert data["has_more"] is True

        # Verify tail was applied
        mock_query_port._get_execution_logs.assert_called_once()
        call_args = mock_query_port._get_execution_logs.call_args[0]
        # Args are: execution_id, stage, tail
        assert call_args[2] == 1

    def test_get_execution_logs_with_stage_filter(self, client, mock_query_port):
        """Test execution logs retrieval with stage filter."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionLogs

        now = datetime.now(timezone.utc)
        mock_query_port._get_execution_logs.return_value = ExecutionLogs(
            execution_id="exec-123",
            logs=[
                LogEntry(
                    timestamp=now,
                    level="INFO",
                    message="Running tests",
                    stage="development",
                ),
            ],
            total_lines=1,
            has_more=False,
            stage="development",
        )

        # Act
        response = client.get("/api/v2/executions/exec-123/logs?stage=development")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) == 1
        assert data["logs"][0]["stage"] == "development"

        # Verify stage filter was applied
        mock_query_port._get_execution_logs.assert_called_once()
        call_args = mock_query_port._get_execution_logs.call_args[0]
        # Args are: execution_id, stage, tail
        assert call_args[1] == "development"

    def test_get_execution_logs_not_found(self, client, mock_query_port):
        """Test execution logs retrieval when execution not found."""
        # Arrange
        mock_query_port._get_execution_logs.side_effect = ValueError(
            "Execution with ID 'exec-nonexistent' not found"
        )

        # Act
        response = client.get("/api/v2/executions/exec-nonexistent/logs")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "Execution not found" in data["detail"]


class TestGetExecutionHistory:
    """Tests for GET /api/v2/executions/{id}/history endpoint."""

    def test_get_execution_history_success(self, client, mock_query_port):
        """Test successful execution history retrieval."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionHistory, ExecutionHistoryEntry

        now = datetime.now(timezone.utc)
        mock_query_port._get_execution_history.return_value = ExecutionHistory(
            execution_id="exec-123",
            events=[
                ExecutionHistoryEntry(
                    event_type="ExecutionInitialized",
                    occurred_at=now,
                    payload={"agent_id": "agent-123"},
                ),
                ExecutionHistoryEntry(
                    event_type="ExecutionStarted",
                    occurred_at=now,
                    payload={"container_id": "container-123"},
                ),
                ExecutionHistoryEntry(
                    event_type="ExecutionCompleted",
                    occurred_at=now,
                    payload={"duration_seconds": 120.5},
                ),
            ],
            total_events=3,
        )

        # Act
        response = client.get("/api/v2/executions/exec-123/history")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == "exec-123"
        assert len(data["events"]) == 3
        assert data["events"][0]["event_type"] == "ExecutionInitialized"
        assert data["events"][1]["event_type"] == "ExecutionStarted"
        assert data["events"][2]["event_type"] == "ExecutionCompleted"
        assert data["total_events"] == 3

    def test_get_execution_history_with_limit(self, client, mock_query_port):
        """Test execution history retrieval with limit."""
        # Arrange
        from codetoreum.ports.input.execution_query import ExecutionHistory, ExecutionHistoryEntry

        now = datetime.now(timezone.utc)
        mock_query_port._get_execution_history.return_value = ExecutionHistory(
            execution_id="exec-123",
            events=[
                ExecutionHistoryEntry(
                    event_type="ExecutionCompleted",
                    occurred_at=now,
                    payload={"duration_seconds": 120.5},
                ),
            ],
            total_events=10,
        )

        # Act
        response = client.get("/api/v2/executions/exec-123/history?limit=1")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1
        assert data["total_events"] == 10

        # Verify limit was applied
        mock_query_port._get_execution_history.assert_called_once()
        call_args = mock_query_port._get_execution_history.call_args[0]
        # Args are: execution_id, limit
        assert call_args[1] == 1

    def test_get_execution_history_not_found(self, client, mock_query_port):
        """Test execution history retrieval when execution not found."""
        # Arrange
        mock_query_port._get_execution_history.side_effect = ValueError(
            "Execution with ID 'exec-nonexistent' not found"
        )

        # Act
        response = client.get("/api/v2/executions/exec-nonexistent/history")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "Execution not found" in data["detail"]


class TestTerminateExecution:
    """Tests for POST /api/v2/executions/{id}/terminate endpoint."""

    def test_terminate_execution_success(self, client, mock_command_port):
        """Test successful execution termination."""
        # Arrange
        mock_command_port._terminate_execution.return_value = ExecutionCommandResult(
            success=True,
            execution_id="exec-123",
            message="Execution terminated successfully",
            new_status="cancelled",
        )

        request_data = {
            "reason": "User requested termination",
        }

        # Act
        response = client.post(
            "/api/v2/executions/exec-123/terminate", json=request_data
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["execution_id"] == "exec-123"
        assert data["message"] == "Execution terminated successfully"
        assert data["new_status"] == "cancelled"

        # Verify command port was called
        mock_command_port._terminate_execution.assert_called_once()
        call_args = mock_command_port._terminate_execution.call_args[0][0]
        assert isinstance(call_args, TerminateExecutionCommand)
        assert call_args.execution_id == "exec-123"
        assert call_args.reason == "User requested termination"

    def test_terminate_execution_without_reason(self, client, mock_command_port):
        """Test execution termination without reason."""
        # Arrange
        mock_command_port._terminate_execution.return_value = ExecutionCommandResult(
            success=True,
            execution_id="exec-123",
            message="Execution terminated successfully",
            new_status="cancelled",
        )

        # Act
        response = client.post("/api/v2/executions/exec-123/terminate", json={})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_terminate_execution_not_found(self, client, mock_command_port):
        """Test execution termination when execution not found."""
        # Arrange
        mock_command_port._terminate_execution.side_effect = ValueError(
            "Execution with ID 'exec-nonexistent' not found"
        )

        # Act
        response = client.post(
            "/api/v2/executions/exec-nonexistent/terminate", json={}
        )

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "Execution not found" in data["detail"]

    def test_terminate_execution_already_completed(self, client, mock_command_port):
        """Test execution termination when already completed."""
        # Arrange
        mock_command_port._terminate_execution.side_effect = ValueError(
            "Execution already completed"
        )

        # Act
        response = client.post("/api/v2/executions/exec-123/terminate", json={})

        # Assert
        assert response.status_code == 409
        data = response.json()
        assert "Cannot terminate execution" in data["detail"]

    def test_terminate_execution_invalid_state(self, client, mock_command_port):
        """Test execution termination in invalid state."""
        # Arrange
        mock_command_port._terminate_execution.side_effect = ValueError(
            "Invalid state transition"
        )

        # Act
        response = client.post("/api/v2/executions/exec-123/terminate", json={})

        # Assert
        assert response.status_code == 409
        data = response.json()
        assert "Cannot terminate execution" in data["detail"]
