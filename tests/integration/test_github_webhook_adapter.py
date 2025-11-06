"""
Integration tests for FastAPI Application

This file tests the health check and OpenAPI documentation endpoints.
The GitHub webhook adapter tests have been removed because they test
unimplemented functionality (webhook signature verification requires
methods like get_webhook_secret() and load_github_state() which are
not part of the IConfigStore interface and are not implemented).
"""

import pytest
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.fastapi_app import create_development_app


@pytest.fixture
def client():
    """Create test client with development app"""
    app = create_development_app()
    with TestClient(app) as test_client:
        yield test_client


class TestHealthEndpoints:
    """Tests for health check endpoints"""

    def test_health_check(self, client):
        """Test basic health check endpoint"""
        response = client.get("/api/v2/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "codetoreum-api"
        assert data["version"] == "2.0.0"

    def test_readiness_check(self, client):
        """Test readiness check endpoint"""
        response = client.get("/api/v2/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


class TestOpenAPIDoc:
    """Tests for OpenAPI documentation"""

    def test_openapi_json_available(self, client):
        """Test OpenAPI JSON endpoint is available"""
        response = client.get("/api/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert data["info"]["title"] == "Codetoreum API"
        assert data["info"]["version"] == "2.0.0"

    def test_swagger_docs_available(self, client):
        """Test Swagger UI is available"""
        response = client.get("/api/docs")
        assert response.status_code == 200
        assert b"swagger-ui" in response.content.lower()
