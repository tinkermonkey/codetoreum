"""
Integration tests for WebSocket Adapter
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from codetoreum.adapters.primary.fastapi_app import create_development_app
from codetoreum.domain.events import DomainEvent



@pytest.fixture(scope="function")
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


class TestWebSocketConnection:
    """Tests for WebSocket connection management"""

    def test_websocket_connect(self, client):
        """Test WebSocket connection establishment"""
        with client.websocket_connect("/ws/events") as websocket:
            # Receive welcome message
            data = websocket.receive_json()
            assert data["type"] == "connected"
            assert "client_id" in data
            assert "message" in data

    def test_websocket_ping_pong(self, client):
        """Test WebSocket ping/pong keepalive"""
        with client.websocket_connect("/ws/events") as websocket:
            # Receive welcome message
            websocket.receive_json()

            # Send ping
            websocket.send_json({"type": "ping"})

            # Receive pong
            data = websocket.receive_json()
            assert data["type"] == "pong"


class TestWebSocketSubscriptions:
    """Tests for WebSocket event subscriptions"""

    def test_subscribe_to_all_events(self, client):
        """Test subscribing to all events"""
        with client.websocket_connect("/ws/events") as websocket:
            # Receive welcome message
            websocket.receive_json()

            # Subscribe to all events
            websocket.send_json(
                {"type": "subscribe", "subscription_type": "all_events"}
            )

            # Receive subscription confirmation
            data = websocket.receive_json()
            assert data["type"] == "subscribed"
            assert data["subscription_type"] == "all_events"

    def test_subscribe_to_workflow_events(self, client):
        """Test subscribing to workflow events"""
        with client.websocket_connect("/ws/events") as websocket:
            # Receive welcome message
            websocket.receive_json()

            # Subscribe to workflow events
            websocket.send_json(
                {
                    "type": "subscribe",
                    "subscription_type": "workflow_events",
                    "workflow_run_id": "test-workflow-123",
                }
            )

            # Receive subscription confirmation
            data = websocket.receive_json()
            assert data["type"] == "subscribed"
            assert data["subscription_type"] == "workflow_events"
            assert data["filters"]["workflow_run_id"] == "test-workflow-123"

    def test_subscribe_to_execution_events(self, client):
        """Test subscribing to execution events"""
        with client.websocket_connect("/ws/events") as websocket:
            # Receive welcome message
            websocket.receive_json()

            # Subscribe to execution events
            websocket.send_json(
                {
                    "type": "subscribe",
                    "subscription_type": "execution_events",
                    "execution_id": "test-execution-123",
                }
            )

            # Receive subscription confirmation
            data = websocket.receive_json()
            assert data["type"] == "subscribed"
            assert data["subscription_type"] == "execution_events"
            assert data["filters"]["execution_id"] == "test-execution-123"

    def test_subscribe_with_project_filter(self, client):
        """Test subscribing with project name filter"""
        with client.websocket_connect("/ws/events") as websocket:
            # Receive welcome message
            websocket.receive_json()

            # Subscribe with project filter
            websocket.send_json(
                {
                    "type": "subscribe",
                    "subscription_type": "all_events",
                    "project_name": "test-project",
                }
            )

            # Receive subscription confirmation
            data = websocket.receive_json()
            assert data["type"] == "subscribed"
            assert data["filters"]["project_name"] == "test-project"

    def test_subscribe_with_event_types_filter(self, client):
        """Test subscribing with event types filter"""
        with client.websocket_connect("/ws/events") as websocket:
            # Receive welcome message
            websocket.receive_json()

            # Subscribe with event types filter
            websocket.send_json(
                {
                    "type": "subscribe",
                    "subscription_type": "all_events",
                    "event_types": ["WorkflowStarted", "WorkflowCompleted"],
                }
            )

            # Receive subscription confirmation
            data = websocket.receive_json()
            assert data["type"] == "subscribed"
            assert data["filters"]["event_types"] == [
                "WorkflowStarted",
                "WorkflowCompleted",
            ]

    def test_unsubscribe(self, client):
        """Test unsubscribing from events"""
        with client.websocket_connect("/ws/events") as websocket:
            # Receive welcome message
            websocket.receive_json()

            # Subscribe
            websocket.send_json(
                {"type": "subscribe", "subscription_type": "all_events"}
            )
            websocket.receive_json()

            # Unsubscribe
            websocket.send_json({"type": "unsubscribe"})

            # Receive unsubscribe confirmation
            data = websocket.receive_json()
            assert data["type"] == "unsubscribed"


class TestWebSocketErrorHandling:
    """Tests for WebSocket error handling"""

    @pytest.mark.timeout(5)
    def test_invalid_message_type(self, client):
        """Test sending invalid message type"""
        with client.websocket_connect("/ws/events") as websocket:
            # Receive welcome message
            websocket.receive_json()

            # Send invalid message type
            websocket.send_json({"type": "invalid_type"})

            # Receive error message
            data = websocket.receive_json()
            assert data["type"] == "error"
            assert data["code"] == "unknown_message_type"

            # Close connection cleanly
            websocket.close()

    @pytest.mark.timeout(5)
    def test_invalid_subscription_type(self, client):
        """Test subscribing with invalid subscription type"""
        with client.websocket_connect("/ws/events") as websocket:
            # Receive welcome message
            websocket.receive_json()

            # Send invalid subscription type
            websocket.send_json(
                {"type": "subscribe", "subscription_type": "invalid_type"}
            )

            # Receive error message
            data = websocket.receive_json()
            assert data["type"] == "error"
            assert data["code"] == "subscribe_failed"

            # Close connection cleanly
            websocket.close()


class TestWebSocketMultipleConnections:
    """Tests for multiple WebSocket connections"""

    @pytest.mark.timeout(10)
    def test_multiple_concurrent_connections(self, client):
        """Test multiple concurrent WebSocket connections"""
        with client.websocket_connect("/ws/events") as ws1:
            with client.websocket_connect("/ws/events") as ws2:
                # Receive welcome messages
                data1 = ws1.receive_json()
                data2 = ws2.receive_json()

                assert data1["type"] == "connected"
                assert data2["type"] == "connected"

                # Connection IDs should be different
                assert data1["client_id"] != data2["client_id"]

    @pytest.mark.timeout(10)
    def test_multiple_subscriptions_per_connection(self, client):
        """Test multiple subscriptions on same connection"""
        with client.websocket_connect("/ws/events") as websocket:
            # Receive welcome message
            websocket.receive_json()

            # Subscribe to workflow events
            websocket.send_json(
                {"type": "subscribe", "subscription_type": "workflow_events"}
            )
            data1 = websocket.receive_json()
            assert data1["type"] == "subscribed"

            # Subscribe to execution events
            websocket.send_json(
                {"type": "subscribe", "subscription_type": "execution_events"}
            )
            data2 = websocket.receive_json()
            assert data2["type"] == "subscribed"
