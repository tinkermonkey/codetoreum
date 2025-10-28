"""
Integration tests for GitHub Webhook Adapter
"""

import hashlib
import hmac
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.fastapi_app import create_development_app


@pytest.fixture
def client():
    """Create test client with development app"""
    app = create_development_app()
    return TestClient(app)


@pytest.fixture
def webhook_secret():
    """Webhook secret for testing"""
    return "mock-secret-key"


def create_signature(payload: bytes, secret: str) -> str:
    """
    Create GitHub webhook signature.

    Args:
        payload: Request body bytes
        secret: Webhook secret

    Returns:
        HMAC signature with sha256= prefix
    """
    signature = hmac.new(
        key=secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"


class TestGitHubWebhookAdapter:
    """Tests for GitHub webhook adapter"""

    def test_webhook_signature_verification_success(self, client, webhook_secret):
        """Test successful webhook signature verification"""
        payload = {
            "action": "moved",
            "project_card": {
                "content_url": "https://api.github.com/repos/test-org/test-repo/issues/123",
                "column_id": 456,
            },
            "repository": {"full_name": "test-org/test-repo"},
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = create_signature(payload_bytes, webhook_secret)

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Delivery": "test-delivery-123",
                "X-GitHub-Event": "project_card",
                "X-Hub-Signature-256": signature,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["delivery_id"] == "test-delivery-123"

    def test_webhook_signature_verification_failure(self, client):
        """Test failed webhook signature verification"""
        payload = {
            "action": "moved",
            "project_card": {
                "content_url": "https://api.github.com/repos/test-org/test-repo/issues/123",
                "column_id": 456,
            },
            "repository": {"full_name": "test-org/test-repo"},
        }

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Delivery": "test-delivery-123",
                "X-GitHub-Event": "project_card",
                "X-Hub-Signature-256": "sha256=invalid-signature",
            },
        )

        assert response.status_code == 401

    def test_webhook_idempotency(self, client, webhook_secret):
        """Test webhook idempotency - same delivery ID processed once"""
        payload = {
            "action": "moved",
            "project_card": {
                "content_url": "https://api.github.com/repos/test-org/test-repo/issues/123",
                "column_id": 456,
            },
            "repository": {"full_name": "test-org/test-repo"},
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = create_signature(payload_bytes, webhook_secret)

        # First request
        response1 = client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Delivery": "same-delivery-id",
                "X-GitHub-Event": "project_card",
                "X-Hub-Signature-256": signature,
            },
        )

        assert response1.status_code == 200

        # Second request with same delivery ID
        response2 = client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Delivery": "same-delivery-id",
                "X-GitHub-Event": "project_card",
                "X-Hub-Signature-256": signature,
            },
        )

        assert response2.status_code == 200
        data2 = response2.json()
        assert "(cached)" in data2["message"]

    def test_webhook_invalid_payload(self, client, webhook_secret):
        """Test webhook with invalid payload structure"""
        payload = {
            "action": "moved",
            # Missing required fields
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = create_signature(payload_bytes, webhook_secret)

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Delivery": "test-delivery-456",
                "X-GitHub-Event": "project_card",
                "X-Hub-Signature-256": signature,
            },
        )

        assert response.status_code == 400

    def test_webhook_unsupported_event_type(self, client, webhook_secret):
        """Test webhook with unsupported event type"""
        payload = {
            "action": "opened",
            "repository": {"full_name": "test-org/test-repo"},
        }

        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = create_signature(payload_bytes, webhook_secret)

        response = client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Delivery": "test-delivery-789",
                "X-GitHub-Event": "unsupported_event",
                "X-Hub-Signature-256": signature,
            },
        )

        # Should accept but ignore unsupported events
        assert response.status_code == 200
        data = response.json()
        assert len(data["commands_created"]) == 0


class TestHealthEndpoints:
    """Tests for health check endpoints"""

    def test_health_check(self, client):
        """Test basic health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "codetoreum-api"
        assert data["version"] == "2.0.0"

    def test_readiness_check(self, client):
        """Test readiness check endpoint"""
        response = client.get("/health/ready")
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
