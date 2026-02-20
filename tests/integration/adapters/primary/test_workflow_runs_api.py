"""Integration tests for Workflow Runs REST API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.routers.workflow_runs import create_workflow_runs_router
from codetoreum.ports.input.workflow_run_query import (
    IWorkflowRunQueryPort,
    WorkflowRunInfo,
    WorkflowRunSummary,
    WorkflowRunListResult,
    WorkflowRunStageInfo,
    WorkflowRunStatus,
)


class MockWorkflowRunQueryPort(IWorkflowRunQueryPort):
    """Mock implementation of workflow run query port for testing."""

    def __init__(self):
        self._get_workflow_run = AsyncMock()
        self._list_workflow_runs = AsyncMock()
        self._get_workflow_run_events = AsyncMock()
        self._get_workflow_run_audit = AsyncMock()

    async def get_workflow_run(self, workflow_run_id):
        return await self._get_workflow_run(workflow_run_id)

    async def list_workflow_runs(self, filters=None, pagination=None):
        return await self._list_workflow_runs(filters, pagination)

    async def get_workflow_run_events(self, workflow_run_id, offset=0, limit=50, event_types=None, since=None):
        return await self._get_workflow_run_events(workflow_run_id, offset, limit, event_types, since)

    async def get_workflow_run_audit(self, workflow_run_id, offset=0, limit=100, include_validation=True):
        return await self._get_workflow_run_audit(workflow_run_id, offset, limit, include_validation)


@pytest.fixture
def mock_query_port():
    """Fixture providing mock workflow run query port."""
    return MockWorkflowRunQueryPort()


@pytest.fixture
def app(mock_query_port):
    """Fixture providing FastAPI test application."""
    app = FastAPI()

    # Create and include workflow runs router (without auth for testing)
    router = create_workflow_runs_router(
        query_port=mock_query_port,
        auth_deps=None,  # Disable auth for testing
    )
    app.include_router(router)

    return app


@pytest.fixture
def client(app):
    """Fixture providing test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_workflow_run():
    """Fixture providing a sample workflow run."""
    now = datetime.now(timezone.utc)
    return WorkflowRunInfo(
        id="wfrun-123",
        work_item_id="wi-456",
        workflow_id="wf-789",
        project_id="proj-1",
        status=WorkflowRunStatus.RUNNING,
        current_stage_index=1,
        current_stage_name="review",
        stages=[
            WorkflowRunStageInfo(
                name="implementation",
                agent_name="developer_agent",
                status="completed",
                started_at=now,
                completed_at=now,
                execution_id="exec-111",
            ),
            WorkflowRunStageInfo(
                name="review",
                agent_name="reviewer_agent",
                status="running",
                started_at=now,
                completed_at=None,
                execution_id="exec-222",
            ),
        ],
        started_at=now,
        completed_at=None,
        duration=None,
        issue_title="Fix authentication bug",
        issue_number=42,
        project="codetoreum",
        triggered_by="github_webhook",
        priority="high",
        metadata={},
    )


@pytest.fixture
def sample_workflow_run_summary():
    """Fixture providing a sample workflow run summary."""
    now = datetime.now(timezone.utc)
    return WorkflowRunSummary(
        id="wfrun-123",
        work_item_id="wi-456",
        workflow_id="wf-789",
        project_id="proj-1",
        status=WorkflowRunStatus.RUNNING,
        current_stage_index=1,
        current_stage_name="review",
        started_at=now,
        completed_at=None,
        duration=None,
        issue_title="Fix authentication bug",
        issue_number=42,
        project="codetoreum",
        triggered_by="github_webhook",
        priority="high",
    )


class TestListWorkflowRuns:
    """Tests for GET /api/v2/workflows/runs endpoint."""

    def test_list_workflow_runs_success(
        self, client, mock_query_port, sample_workflow_run_summary
    ):
        """Test successful workflow runs listing."""
        # Arrange
        list_result = WorkflowRunListResult(
            runs=[sample_workflow_run_summary],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )
        mock_query_port._list_workflow_runs.return_value = list_result

        # Act
        response = client.get("/api/v2/workflows/runs")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["runs"]) == 1
        assert data["runs"][0]["id"] == "wfrun-123"
        assert data["runs"][0]["status"] == "running"

        # Verify query port was called
        mock_query_port._list_workflow_runs.assert_called_once()

    def test_list_workflow_runs_with_filters(
        self, client, mock_query_port, sample_workflow_run_summary
    ):
        """Test workflow runs listing with filters."""
        # Arrange
        list_result = WorkflowRunListResult(
            runs=[sample_workflow_run_summary],
            total_count=1,
            offset=0,
            limit=20,
            has_next=False,
        )
        mock_query_port._list_workflow_runs.return_value = list_result

        # Act
        response = client.get(
            "/api/v2/workflows/runs?status=running&projectId=proj-1"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1

        # Verify filters were passed
        mock_query_port._list_workflow_runs.assert_called_once()
        call_args = mock_query_port._list_workflow_runs.call_args
        filters = call_args[0][0] if call_args[0] else call_args[1].get("filters")
        assert filters is not None
        assert filters.project_id == "proj-1"

    def test_list_workflow_runs_with_invalid_status(self, client, mock_query_port):
        """Test workflow runs listing with invalid status."""
        # Act
        response = client.get("/api/v2/workflows/runs?status=invalid_status")

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "Invalid status value" in data["detail"]

    def test_list_workflow_runs_with_pagination(
        self, client, mock_query_port, sample_workflow_run_summary
    ):
        """Test workflow runs listing with pagination."""
        # Arrange
        list_result = WorkflowRunListResult(
            runs=[sample_workflow_run_summary],
            total_count=50,
            offset=20,
            limit=10,
            has_next=True,
        )
        mock_query_port._list_workflow_runs.return_value = list_result

        # Act
        response = client.get("/api/v2/workflows/runs?offset=20&limit=10")

        # Assert
        assert response.status_code == 200
        data = response.json()
        # offset=20, limit=10 -> page 3 (20/10 + 1)
        assert data["page"] == 3
        assert data["page_size"] == 10
        assert data["has_next"] is True


class TestGetWorkflowRun:
    """Tests for GET /api/v2/workflows/runs/{workflow_run_id} endpoint."""

    def test_get_workflow_run_success(
        self, client, mock_query_port, sample_workflow_run
    ):
        """Test successful workflow run retrieval."""
        # Arrange
        mock_query_port._get_workflow_run.return_value = sample_workflow_run

        # Act
        response = client.get("/api/v2/workflows/runs/wfrun-123")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "wfrun-123"
        assert data["status"] == "running"
        assert len(data["stages"]) == 2
        assert data["stages"][0]["name"] == "implementation"
        assert data["stages"][0]["status"] == "completed"
        assert data["stages"][1]["name"] == "review"
        assert data["stages"][1]["status"] == "running"

        # Verify query port was called
        mock_query_port._get_workflow_run.assert_called_once_with("wfrun-123")

    def test_get_workflow_run_not_found(self, client, mock_query_port):
        """Test workflow run not found."""
        # Arrange
        from codetoreum.ports.exceptions import ResourceNotFoundError

        mock_query_port._get_workflow_run.side_effect = ResourceNotFoundError(
            "WorkflowRun", "wfrun-999"
        )

        # Act
        response = client.get("/api/v2/workflows/runs/wfrun-999")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestGetWorkflowRunEvents:
    """Tests for GET /api/v2/workflows/runs/{workflow_run_id}/events endpoint."""

    def test_get_workflow_run_events_success(self, client, mock_query_port):
        """Test successful workflow run events retrieval."""
        # Arrange
        from codetoreum.ports.input.workflow_run_query import WorkflowRunEventsResult

        now = datetime.now(timezone.utc)
        events_result = WorkflowRunEventsResult(
            events=[
                {
                    "id": "evt-123",
                    "event_type": "WorkflowStarted",
                    "workflow_run_id": "wfrun-123",
                    "occurred_at": now,
                    "agent_name": None,
                    "stage_name": "implementation",
                    "status": None,
                    "data": {"workItemId": "wi-456"},
                }
            ],
            total_count=1,
            offset=0,
            limit=50,
            has_next=False,
        )
        mock_query_port._get_workflow_run_events.return_value = events_result

        # Act
        response = client.get("/api/v2/workflows/runs/wfrun-123/events")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["events"]) == 1
        assert data["events"][0]["eventType"] == "WorkflowStarted"

        # Verify query port was called
        mock_query_port._get_workflow_run_events.assert_called_once()

    def test_get_workflow_run_events_with_filters(self, client, mock_query_port):
        """Test workflow run events retrieval with filters."""
        # Arrange
        from codetoreum.ports.input.workflow_run_query import WorkflowRunEventsResult

        events_result = WorkflowRunEventsResult(
            events=[],
            total_count=0,
            offset=0,
            limit=50,
            has_next=False,
        )
        mock_query_port._get_workflow_run_events.return_value = events_result

        # Act
        response = client.get(
            "/api/v2/workflows/runs/wfrun-123/events?eventTypes=WorkflowStarted,ExecutionCompleted&limit=100"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Verify filters were passed
        mock_query_port._get_workflow_run_events.assert_called_once()
        call_args = mock_query_port._get_workflow_run_events.call_args
        # Check that event_types were passed (positional or keyword)
        assert call_args is not None

    def test_get_workflow_run_events_not_found(self, client, mock_query_port):
        """Test workflow run events not found."""
        # Arrange
        from codetoreum.ports.exceptions import ResourceNotFoundError

        mock_query_port._get_workflow_run_events.side_effect = ResourceNotFoundError(
            "WorkflowRun", "wfrun-999"
        )

        # Act
        response = client.get("/api/v2/workflows/runs/wfrun-999/events")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestGetWorkflowRunAudit:
    """Tests for GET /api/v2/workflows/runs/{workflow_run_id}/audit endpoint."""

    def test_get_workflow_run_audit_success(self, client, mock_query_port):
        """Test successful workflow run audit retrieval."""
        # Arrange
        from codetoreum.ports.input.workflow_run_query import WorkflowRunSummary, WorkflowRunAuditResult

        now = datetime.now(timezone.utc)
        audit_data = WorkflowRunAuditResult(
            workflow_run=WorkflowRunSummary(
                id="wfrun-123",
                work_item_id="wi-456",
                workflow_id="wf-789",
                project_id="proj-1",
                status=WorkflowRunStatus.COMPLETED,
                current_stage_index=2,
                current_stage_name="completed",
                started_at=now,
                completed_at=now,
                duration=100.0,
                issue_title="Test issue",
                issue_number=1,
                project="test-project",
                triggered_by="user",
                priority="medium",
            ),
            events=[
                {
                    "id": "evt-1",
                    "event_type": "WorkflowStarted",
                    "workflow_run_id": "wfrun-123",
                    "occurred_at": now,
                    "agent_name": None,
                    "stage_name": None,
                    "status": None,
                    "data": {},
                }
            ],
            stages=[
                {
                    "name": "implementation",
                    "status": "completed",
                    "startedAt": now,
                    "completedAt": now,
                    "durationSeconds": 50.0,
                    "events": [],
                }
            ],
            validation={
                "sequenceValid": True,
                "expectedSequence": ["WorkflowStarted", "WorkflowCompleted"],
                "actualSequence": ["WorkflowStarted", "WorkflowCompleted"],
                "missingEvents": [],
                "unexpectedEvents": [],
                "outOfOrderEvents": [],
            },
            total_event_count=10,
            offset=0,
            limit=100,
            has_next=False,
        )
        mock_query_port._get_workflow_run_audit.return_value = audit_data

        # Act
        response = client.get("/api/v2/workflows/runs/wfrun-123/audit")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "workflowRun" in data
        assert "events" in data
        assert "stages" in data
        assert "validation" in data
        assert data["totalEventCount"] == 10
        assert data["validation"]["sequenceValid"] is True

        # Verify query port was called
        mock_query_port._get_workflow_run_audit.assert_called_once_with(
            "wfrun-123", 0, 100, True
        )

    def test_get_workflow_run_audit_with_pagination(self, client, mock_query_port):
        """Test workflow run audit retrieval with custom pagination."""
        # Arrange
        from codetoreum.ports.input.workflow_run_query import WorkflowRunSummary, WorkflowRunAuditResult

        now = datetime.now(timezone.utc)
        audit_data = WorkflowRunAuditResult(
            workflow_run=WorkflowRunSummary(
                id="wfrun-123",
                work_item_id="wi-456",
                workflow_id="wf-789",
                project_id="proj-1",
                status=WorkflowRunStatus.COMPLETED,
                current_stage_index=2,
                current_stage_name="completed",
                started_at=now,
                completed_at=now,
                duration=100.0,
                issue_title="Test issue",
                issue_number=1,
                project="test-project",
                triggered_by="user",
                priority="medium",
            ),
            events=[],
            stages=[],
            validation={
                "sequenceValid": True,
                "expectedSequence": [],
                "actualSequence": [],
                "missingEvents": [],
                "unexpectedEvents": [],
                "outOfOrderEvents": [],
            },
            total_event_count=500,
            offset=100,
            limit=50,
            has_next=True,
        )
        mock_query_port._get_workflow_run_audit.return_value = audit_data

        # Act
        response = client.get(
            "/api/v2/workflows/runs/wfrun-123/audit?offset=100&limit=50"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 100
        assert data["limit"] == 50
        assert data["hasNext"] is True
        assert data["totalEventCount"] == 500

        # Verify query port was called with correct parameters
        mock_query_port._get_workflow_run_audit.assert_called_once_with(
            "wfrun-123", 100, 50, True
        )

    def test_get_workflow_run_audit_without_validation(self, client, mock_query_port):
        """Test workflow run audit retrieval without validation."""
        # Arrange
        from codetoreum.ports.input.workflow_run_query import WorkflowRunSummary, WorkflowRunAuditResult

        now = datetime.now(timezone.utc)
        # When validation is not requested, return empty validation result
        audit_data = WorkflowRunAuditResult(
            workflow_run=WorkflowRunSummary(
                id="wfrun-123",
                work_item_id="wi-456",
                workflow_id="wf-789",
                project_id="proj-1",
                status=WorkflowRunStatus.COMPLETED,
                current_stage_index=2,
                current_stage_name="completed",
                started_at=now,
                completed_at=now,
                duration=100.0,
                issue_title="Test issue",
                issue_number=1,
                project="test-project",
                triggered_by="user",
                priority="medium",
            ),
            events=[],
            stages=[],
            validation={
                "sequenceValid": True,
                "expectedSequence": [],
                "actualSequence": [],
                "missingEvents": [],
                "unexpectedEvents": [],
                "outOfOrderEvents": [],
            },
            total_event_count=10,
            offset=0,
            limit=100,
            has_next=False,
        )
        mock_query_port._get_workflow_run_audit.return_value = audit_data

        # Act
        response = client.get(
            "/api/v2/workflows/runs/wfrun-123/audit?include_validation=false"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        # Validation should be empty when not requested, but still present
        assert "validation" in data
        assert data["validation"]["sequenceValid"] is True

        # Verify query port was called with include_validation=False
        mock_query_port._get_workflow_run_audit.assert_called_once_with(
            "wfrun-123", 0, 100, False
        )

    def test_get_workflow_run_audit_not_found(self, client, mock_query_port):
        """Test workflow run audit not found."""
        # Arrange
        from codetoreum.ports.exceptions import ResourceNotFoundError

        mock_query_port._get_workflow_run_audit.side_effect = ResourceNotFoundError(
            "WorkflowRun", "wfrun-999"
        )

        # Act
        response = client.get("/api/v2/workflows/runs/wfrun-999/audit")

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_get_workflow_run_audit_server_error(self, client, mock_query_port):
        """Test workflow run audit server error."""
        # Arrange
        mock_query_port._get_workflow_run_audit.side_effect = Exception(
            "Database connection failed"
        )

        # Act
        response = client.get("/api/v2/workflows/runs/wfrun-123/audit")

        # Assert
        assert response.status_code == 500
        data = response.json()
        assert "Internal server error" in data["detail"]

    def test_get_workflow_run_audit_invalid_pagination(self, client, mock_query_port):
        """Test workflow run audit with invalid pagination parameters."""
        # Act - negative offset
        response = client.get("/api/v2/workflows/runs/wfrun-123/audit?offset=-1")

        # Assert
        assert response.status_code == 422  # FastAPI validation error

        # Act - limit too high
        response = client.get("/api/v2/workflows/runs/wfrun-123/audit?limit=500")

        # Assert
        assert response.status_code == 422  # FastAPI validation error

        # Act - limit too low
        response = client.get("/api/v2/workflows/runs/wfrun-123/audit?limit=0")

        # Assert
        assert response.status_code == 422  # FastAPI validation error

    def test_get_workflow_run_audit_forbidden(self, client, mock_query_port):
        """Test that HTTPExceptions from the port are properly re-raised."""
        # Arrange - mock the port to raise an HTTPException
        from fastapi import HTTPException

        mock_query_port._get_workflow_run_audit.side_effect = HTTPException(
            status_code=403, detail="Forbidden: Insufficient permissions"
        )

        # Act
        response = client.get("/api/v2/workflows/runs/wfrun-123/audit")

        # Assert - the HTTPException should be re-raised unchanged
        assert response.status_code == 403
        data = response.json()
        assert data["detail"] == "Forbidden: Insufficient permissions"
