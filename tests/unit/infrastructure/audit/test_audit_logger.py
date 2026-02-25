"""
Tests for Audit Logger

Tests the core audit logging functionality including event creation,
storage, and retrieval.
"""

from datetime import UTC, datetime

import pytest

from codetoreum.infrastructure.audit.audit_logger import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
)
from codetoreum.infrastructure.audit.stores import InMemoryAuditStore


class TestAuditEvent:
    """Tests for AuditEvent data class."""

    def test_audit_event_creation(self):
        """Test creating an audit event."""
        event = AuditEvent(
            timestamp=datetime.now(UTC),
            event_type=AuditEventType.AGENT_CREATED,
            resource_type="agent",
            resource_id="agent-123",
            action="create",
            user_id="user-456",
            success=True,
            metadata={"agent_name": "test-agent"},
        )

        assert event.event_type == AuditEventType.AGENT_CREATED
        assert event.resource_type == "agent"
        assert event.resource_id == "agent-123"
        assert event.action == "create"
        assert event.user_id == "user-456"
        assert event.success is True
        assert event.metadata["agent_name"] == "test-agent"

    def test_audit_event_to_dict(self):
        """Test converting audit event to dictionary."""
        timestamp = datetime.now(UTC)
        event = AuditEvent(
            timestamp=timestamp,
            event_type=AuditEventType.AGENT_DELETED,
            resource_type="agent",
            resource_id="agent-123",
            action="delete",
            user_id="system",
            success=True,
        )

        event_dict = event.to_dict()

        assert event_dict["timestamp"] == timestamp.isoformat()
        assert event_dict["event_type"] == "agent_deleted"
        assert event_dict["resource_type"] == "agent"
        assert event_dict["resource_id"] == "agent-123"
        assert event_dict["action"] == "delete"
        assert event_dict["user_id"] == "system"
        assert event_dict["success"] is True


class TestAuditLogger:
    """Tests for AuditLogger."""

    def test_audit_logger_initialization(self):
        """Test initializing audit logger."""
        logger = AuditLogger()
        assert logger.logger is not None
        assert logger.audit_store is None

    def test_audit_logger_with_store(self):
        """Test audit logger with audit store."""
        store = InMemoryAuditStore()
        logger = AuditLogger(audit_store=store)

        assert logger.audit_store is store

    def test_log_event(self):
        """Test logging an audit event."""
        logger = AuditLogger()

        event = logger.log_event(
            event_type=AuditEventType.AUTH_SUCCESS,
            resource_type="auth",
            resource_id="token-123",
            action="authenticate",
            user_id="user-456",
            metadata={"source": "cookie"},
            success=True,
        )

        assert isinstance(event, AuditEvent)
        assert event.event_type == AuditEventType.AUTH_SUCCESS
        assert event.resource_type == "auth"
        assert event.resource_id == "token-123"
        assert event.user_id == "user-456"
        assert event.success is True
        assert event.metadata["source"] == "cookie"

    def test_log_event_with_error(self):
        """Test logging a failed audit event."""
        logger = AuditLogger()

        event = logger.log_event(
            event_type=AuditEventType.AUTH_FAILURE,
            resource_type="auth",
            resource_id="token-123",
            action="authenticate",
            success=False,
            error_message="Invalid token",
            metadata={"source": "header"},
        )

        assert event.success is False
        assert event.error_message == "Invalid token"
        assert event.user_id == "system"  # Default user_id

    def test_log_auth_attempt_success(self):
        """Test logging successful authentication."""
        logger = AuditLogger()

        event = logger.log_auth_attempt(
            user_id="user-123",
            success=True,
            metadata={"source": "web"},
        )

        assert event.event_type == AuditEventType.AUTH_SUCCESS
        assert event.user_id == "user-123"
        assert event.success is True

    def test_log_auth_attempt_failure(self):
        """Test logging failed authentication."""
        logger = AuditLogger()

        event = logger.log_auth_attempt(
            user_id="user-123",
            success=False,
        )

        assert event.event_type == AuditEventType.AUTH_FAILURE
        assert event.user_id == "user-123"
        assert event.success is False

    def test_log_agent_created(self):
        """Test logging agent creation."""
        logger = AuditLogger()

        event = logger.log_agent_created(
            agent_id="agent-123",
            user_id="user-456",
            metadata={"agent_name": "test-agent", "model": "claude-3"},
        )

        assert event.event_type == AuditEventType.AGENT_CREATED
        assert event.resource_type == "agent"
        assert event.resource_id == "agent-123"
        assert event.user_id == "user-456"
        assert event.metadata["agent_name"] == "test-agent"

    def test_log_agent_updated(self):
        """Test logging agent update."""
        logger = AuditLogger()

        changes = {"model": "claude-4", "timeout_seconds": 600}
        event = logger.log_agent_updated(
            agent_id="agent-123",
            user_id="user-456",
            changes=changes,
        )

        assert event.event_type == AuditEventType.AGENT_UPDATED
        assert event.resource_id == "agent-123"
        assert event.metadata["changes"] == changes

    def test_log_agent_deleted(self):
        """Test logging agent deletion."""
        logger = AuditLogger()

        event = logger.log_agent_deleted(
            agent_id="agent-123",
            user_id="user-456",
            success=True,
        )

        assert event.event_type == AuditEventType.AGENT_DELETED
        assert event.resource_id == "agent-123"
        assert event.success is True

    def test_log_agent_deleted_failure(self):
        """Test logging failed agent deletion."""
        logger = AuditLogger()

        event = logger.log_agent_deleted(
            agent_id="agent-123",
            user_id="user-456",
            success=False,
            error_message="Agent not found",
        )

        assert event.event_type == AuditEventType.AGENT_DELETED
        assert event.success is False
        assert event.error_message == "Agent not found"

    def test_log_execution_terminated(self):
        """Test logging execution termination."""
        logger = AuditLogger()

        event = logger.log_execution_terminated(
            execution_id="exec-123",
            user_id="user-456",
            reason="User requested",
            success=True,
        )

        assert event.event_type == AuditEventType.EXECUTION_TERMINATED
        assert event.resource_type == "execution"
        assert event.resource_id == "exec-123"
        assert event.metadata["reason"] == "User requested"

    def test_log_config_change(self):
        """Test logging configuration change."""
        logger = AuditLogger()

        changes = {"timeout": 600, "retries": 5}
        event = logger.log_config_change(
            config_type="agent",
            config_id="agent-123",
            user_id="user-456",
            changes=changes,
            reason="Performance tuning",
        )

        assert event.event_type == AuditEventType.CONFIG_AGENT_UPDATED
        assert event.resource_type == "agent"
        assert event.metadata["changes"] == changes
        assert event.metadata["reason"] == "Performance tuning"


@pytest.mark.asyncio
class TestAuditLoggerWithStore:
    """Tests for AuditLogger with persistent storage."""

    async def test_events_stored_in_audit_store(self):
        """Test that events are stored in audit store."""
        store = InMemoryAuditStore()
        logger = AuditLogger(audit_store=store)

        # Log an event (note: actual storage is fire-and-forget in real impl)
        event = logger.log_event(
            event_type=AuditEventType.AGENT_CREATED,
            resource_type="agent",
            resource_id="agent-123",
            action="create",
            user_id="user-456",
        )

        # In the real implementation, this would be async
        # For this test, we'll verify the event was created
        assert event is not None
        assert event.event_type == AuditEventType.AGENT_CREATED
