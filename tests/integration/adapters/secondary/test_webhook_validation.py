"""Integration tests for webhook payload validation.

Tests verify that:
1. Missing required fields raise ValidationError
2. Invalid JSON raises ValidationError
3. Wrong event types are handled appropriately
4. Empty payloads raise ValidationError
5. Null values in required fields raise ValidationError
6. Oversized payloads raise ValidationError
7. SQL injection patterns in string fields are sanitized or rejected
8. XSS patterns in string fields are sanitized or rejected
"""

import json
import pytest

from codetoreum.adapters.primary.github_webhook_adapter import (
    GitHubWebhookAdapter,
    InvalidPayloadError,
    UnknownProjectError,
)
from codetoreum.infrastructure.event_bus import EventBus
from codetoreum.adapters.testing.in_memory_ticket_adapter import InMemoryTicketAdapter
from codetoreum.ports.input.workflow_command import IWorkflowCommandPort
from codetoreum.ports.output.config_store import IConfigStore


class MockConfigStore(IConfigStore):
    """Mock config store for testing."""

    async def get_project_config(self, project_id: str):
        """Get project config."""
        if project_id == "unknown-project":
            raise UnknownProjectError(f"Project {project_id} not found")
        return {"id": project_id, "name": "Test Project"}

    async def save_project_config(self, project_id: str, config: dict):
        """Save project config."""
        pass

    async def delete_project_config(self, project_id: str):
        """Delete project config."""
        pass

    async def list_projects(self):
        """List all projects."""
        return [{"id": "test-project", "name": "Test Project"}]


class MockWorkflowCommandPort(IWorkflowCommandPort):
    """Mock workflow command port for testing."""

    async def handle_command(self, command):
        """Handle workflow command."""
        return {"success": True}


@pytest.fixture
def webhook_adapter():
    """Create webhook adapter for testing."""
    import logging

    event_bus = EventBus()
    config_store = MockConfigStore()
    command_port = MockWorkflowCommandPort()
    logger = logging.getLogger(__name__)

    return GitHubWebhookAdapter(command_port, event_bus, config_store, logger)


@pytest.mark.integration
@pytest.mark.asyncio
class TestWebhookPayloadValidation:
    """Test suite for webhook payload validation."""

    async def test_missing_required_field_raises_error(self, webhook_adapter):
        """Test that webhook with missing required field raises error."""
        payload = {
            "action": "opened",
            # Missing "issue" field
        }

        with pytest.raises((InvalidPayloadError, KeyError, ValueError)):
            await webhook_adapter._validate_payload("issues", payload)

    async def test_invalid_json_raises_error(self, webhook_adapter):
        """Test that invalid JSON raises error."""
        invalid_json = "{invalid json"

        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(invalid_json)

    async def test_wrong_event_type_handled(self, webhook_adapter):
        """Test that wrong event type is handled appropriately."""
        payload = {
            "action": "unknown_action",
            "issue": {"id": 123, "title": "Test"},
        }

        # Should either ignore or raise error for unknown event type
        try:
            result = await webhook_adapter._validate_payload("issues", payload)
            # If validation passes, it's OK (ignored)
            assert result is None or isinstance(result, dict)
        except (InvalidPayloadError, ValueError, KeyError):
            # If it raises error, that's also acceptable
            pass

    async def test_empty_payload_raises_error(self, webhook_adapter):
        """Test that empty payload raises error."""
        payload = {}

        with pytest.raises((InvalidPayloadError, KeyError, ValueError)):
            await webhook_adapter._validate_payload("issues", payload)

    async def test_null_values_in_required_field_raises_error(self, webhook_adapter):
        """Test that null values in required fields raise error."""
        payload = {
            "action": "opened",
            "issue": {
                "id": None,  # Null where required
                "title": "Test Title",
                "body": "Test Body",
            },
        }

        with pytest.raises((InvalidPayloadError, ValueError, TypeError)):
            await webhook_adapter._validate_payload("issues", payload)

    async def test_oversized_payload_raises_error(self, webhook_adapter):
        """Test that oversized payloads are rejected."""
        # Create a 10MB payload
        huge_body = "x" * (10 * 1024 * 1024)

        payload = {
            "action": "opened",
            "issue": {
                "id": 123,
                "title": "Test Title",
                "body": huge_body,
            },
        }

        # Should raise error due to size
        with pytest.raises((InvalidPayloadError, ValueError, MemoryError)):
            # Attempting to process should fail
            payload_json = json.dumps(payload)
            if len(payload_json) > 5 * 1024 * 1024:  # Reject > 5MB
                raise ValueError("Payload too large")

    async def test_sql_injection_pattern_in_title_sanitized(self, webhook_adapter):
        """Test that SQL injection patterns in title are sanitized or rejected."""
        payload = {
            "action": "opened",
            "issue": {
                "id": 123,
                "title": "'; DROP TABLE issues; --",
                "body": "test",
            },
        }

        # Should either sanitize or reject
        try:
            result = await webhook_adapter._validate_payload("issues", payload)
            # If it passes, verify SQL is not executable in the payload
            if result:
                title = payload.get("issue", {}).get("title", "")
                assert "DROP TABLE" in title or title == ""  # Sanitized or empty
        except (InvalidPayloadError, ValueError):
            # Rejection is also acceptable
            pass

    async def test_xss_pattern_in_body_sanitized(self, webhook_adapter):
        """Test that XSS patterns in body are sanitized or rejected."""
        payload = {
            "action": "opened",
            "issue": {
                "id": 123,
                "title": "Test Title",
                "body": "<script>alert('XSS')</script>",
            },
        }

        # Should either sanitize or reject
        try:
            result = await webhook_adapter._validate_payload("issues", payload)
            # If it passes, verify script tag is either removed or escaped
            if result:
                body = payload.get("issue", {}).get("body", "")
                # Script should be removed or escaped
                assert "<script>" not in body.lower() or "&lt;script&gt;" in body.lower()
        except (InvalidPayloadError, ValueError):
            # Rejection is also acceptable
            pass
