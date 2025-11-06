"""
Integration tests for REST API Adapter
"""

import os
import pytest
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.fastapi_app import create_development_app



@pytest.fixture
def client():
    """Create test client with development app (authentication disabled for testing)"""
    # Disable authentication for integration tests
    os.environ["CODETOREUM_DISABLE_AUTH"] = "true"
    try:
        app = create_development_app()
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # Clean up environment variable
        os.environ.pop("CODETOREUM_DISABLE_AUTH", None)


class TestWorkflowEndpoints:
    """Tests for workflow command endpoints"""

    def test_start_workflow(self, client):
        """Test starting a new workflow"""
        response = client.post(
            "/api/v1/workflows",
            json={
                "project_name": "test-project",
                "work_item_id": "123",
                "pipeline_name": "test-pipeline",
                "priority": "HIGH",
            },
        )

        assert response.status_code == 202
        data = response.json()
        assert data["success"] is True
        assert "workflow_run_id" in data
        assert data["state"] == "STARTED"

    def test_pause_workflow(self, client):
        """Test pausing a workflow"""
        response = client.post(
            "/api/v1/workflows/test-workflow-123/pause",
            json={"reason": "Testing pause"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "PAUSED"

    def test_resume_workflow(self, client):
        """Test resuming a workflow"""
        response = client.post(
            "/api/v1/workflows/test-workflow-123/resume", json={}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "RESUMED"

    def test_cancel_workflow(self, client):
        """Test canceling a workflow"""
        response = client.post(
            "/api/v1/workflows/test-workflow-123/cancel",
            json={"reason": "Testing cancel"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "CANCELLED"

    def test_retry_stage(self, client):
        """Test retrying a failed stage"""
        response = client.post(
            "/api/v1/workflows/test-workflow-123/retry",
            json={"stage_name": "test-stage", "reset_state": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestExecutionQueryEndpoints:
    """Tests for execution query endpoints"""

    def test_list_executions(self, client):
        """Test listing executions"""
        response = client.get("/api/v1/executions")

        assert response.status_code == 200
        data = response.json()
        assert "executions" in data
        assert "total_count" in data
        assert "page" in data
        assert "page_size" in data
        assert "has_next" in data

    def test_list_executions_with_filters(self, client):
        """Test listing executions with filters"""
        response = client.get(
            "/api/v1/executions",
            params={
                "project_name": "test-project",
                "status": "COMPLETED",
                "page": 1,
                "page_size": 10,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10

    def test_get_execution_status(self, client):
        """Test getting execution status"""
        response = client.get("/api/v1/executions/test-execution-123")

        assert response.status_code == 200
        data = response.json()
        assert "execution_id" in data
        assert "workflow_run_id" in data
        assert "status" in data
        assert "project_name" in data

    def test_get_execution_artifacts(self, client):
        """Test getting execution artifacts"""
        response = client.get("/api/v1/executions/test-execution-123/artifacts")

        assert response.status_code == 200
        data = response.json()
        assert "artifacts" in data
        assert "total_count" in data

    def test_get_execution_artifacts_filtered(self, client):
        """Test getting execution artifacts with filter"""
        response = client.get(
            "/api/v1/executions/test-execution-123/artifacts",
            params={"artifact_type": "code"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "artifacts" in data


class TestConfigurationEndpoints:
    """Tests for configuration command endpoints"""

    def test_update_project_config(self, client):
        """Test updating project configuration"""
        response = client.patch(
            "/api/v1/configurations/projects/test-project",
            json={
                "updates": {"setting1": "value1", "setting2": "value2"},
                "user_id": "test-user",
                "reason": "Testing config update",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "config_version" in data
        assert "changes_applied" in data

    def test_add_environment_variable(self, client):
        """Test adding environment variable"""
        response = client.post(
            "/api/v1/configurations/projects/test-project/environment",
            json={
                "variable_name": "TEST_VAR",
                "variable_value": "test-value",
                "user_id": "test-user",
                "is_secret": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["config_version"] == 2

    def test_add_secret_environment_variable(self, client):
        """Test adding secret environment variable"""
        response = client.post(
            "/api/v1/configurations/projects/test-project/environment",
            json={
                "variable_name": "SECRET_KEY",
                "variable_value": "secret-value",
                "user_id": "test-user",
                "is_secret": True,
                "description": "Secret API key",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_remove_environment_variable(self, client):
        """Test removing environment variable"""
        response = client.delete(
            "/api/v1/configurations/projects/test-project/environment/TEST_VAR",
            params={"user_id": "test-user"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestAPIValidation:
    """Tests for API request validation"""

    def test_start_workflow_missing_required_fields(self, client):
        """Test starting workflow with missing required fields"""
        response = client.post(
            "/api/v1/workflows",
            json={
                "project_name": "test-project",
                # Missing work_item_id and pipeline_name
            },
        )

        assert response.status_code == 422  # Validation error

    def test_list_executions_invalid_page(self, client):
        """Test listing executions with invalid page number"""
        response = client.get("/api/v1/executions", params={"page": 0})

        assert response.status_code == 422  # Validation error

    def test_list_executions_invalid_page_size(self, client):
        """Test listing executions with invalid page size"""
        response = client.get("/api/v1/executions", params={"page_size": 200})

        assert response.status_code == 422  # Validation error (exceeds max 100)
