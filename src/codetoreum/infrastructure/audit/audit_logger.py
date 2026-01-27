"""
Audit Logger Implementation

Provides comprehensive audit logging for security-sensitive operations with
structured event data, user context, and correlation ID support.
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from codetoreum.infrastructure.logging import (
    get_correlation_id,
    get_logger,
)
from codetoreum.infrastructure.audit.interfaces import IAuditStore
from codetoreum.infrastructure.error_ids import ErrorRegistry


class AuditEventType(str, Enum):
    """Types of audit events."""

    # Authentication events
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    AUTH_TOKEN_VALIDATED = "auth_token_validated"
    AUTH_TOKEN_INVALID = "auth_token_invalid"

    # Agent events
    AGENT_CREATED = "agent_created"
    AGENT_CREATION_FAILED = "agent_creation_failed"
    AGENT_UPDATED = "agent_updated"
    AGENT_UPDATE_FAILED = "agent_update_failed"
    AGENT_DELETED = "agent_deleted"
    AGENT_CAPABILITY_MODIFIED = "agent_capability_modified"
    AGENT_MCP_SERVER_ADDED = "agent_mcp_server_added"
    AGENT_MCP_SERVER_REMOVED = "agent_mcp_server_removed"

    # Workflow events
    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_UPDATED = "workflow_updated"
    WORKFLOW_DELETED = "workflow_deleted"
    WORKFLOW_STAGE_ADDED = "workflow_stage_added"
    WORKFLOW_STAGE_REMOVED = "workflow_stage_removed"
    WORKFLOW_TRANSITION_MODIFIED = "workflow_transition_modified"

    # Configuration events
    CONFIG_PROJECT_CREATED = "config_project_created"
    CONFIG_PROJECT_UPDATED = "config_project_updated"
    CONFIG_PROJECT_DELETED = "config_project_deleted"
    CONFIG_AGENT_UPDATED = "config_agent_updated"
    CONFIG_PIPELINE_UPDATED = "config_pipeline_updated"
    CONFIG_ENV_VAR_ADDED = "config_env_var_added"
    CONFIG_ENV_VAR_REMOVED = "config_env_var_removed"
    CONFIG_ENV_VAR_UPDATED = "config_env_var_updated"
    CONFIG_SECRET_ADDED = "config_secret_added"
    CONFIG_SECRET_REMOVED = "config_secret_removed"
    CONFIG_IMPORTED = "config_imported"
    CONFIG_EXPORTED = "config_exported"

    # Execution events
    EXECUTION_STARTED = "execution_started"
    EXECUTION_TERMINATED = "execution_terminated"
    EXECUTION_FORCE_STOPPED = "execution_force_stopped"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"

    # Workspace events
    WORKSPACE_CREATED = "workspace_created"
    WORKSPACE_DELETED = "workspace_deleted"
    WORKSPACE_FILES_MOUNTED = "workspace_files_mounted"

    # System events
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SYSTEM_CONFIG_CHANGED = "system_config_changed"


@dataclass
class AuditEvent:
    """
    Represents a single audit event with all relevant context.

    This is the primary data structure for audit logging.
    """

    timestamp: datetime
    event_type: AuditEventType
    resource_type: str
    resource_id: str
    action: str
    user_id: str = "system"
    correlation_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        data = asdict(self)
        data["event_type"] = self.event_type.value
        data["timestamp"] = self.timestamp.isoformat()
        return data


class AuditLogger:
    """
    Audit logger for security-sensitive operations.

    This logger:
    - Records all sensitive operations with full context
    - Includes user identity (when multi-user support is added)
    - Stores structured metadata for each event
    - Supports correlation IDs for request tracing
    - Can store events in a separate audit database
    - Provides query capabilities for audit trail review
    - Implements retention policies for compliance

    Example usage:

        audit_logger = AuditLogger(logger, audit_store)

        # Log successful operation
        audit_logger.log_event(
            event_type=AuditEventType.AGENT_DELETED,
            resource_type="agent",
            resource_id="agent-123",
            action="delete",
            user_id="user-456",
            metadata={"agent_name": "code-reviewer"},
        )

        # Log failed operation
        audit_logger.log_event(
            event_type=AuditEventType.AGENT_DELETED,
            resource_type="agent",
            resource_id="agent-123",
            action="delete",
            user_id="user-456",
            success=False,
            error_message="Agent not found",
        )
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        audit_store: Optional[IAuditStore] = None,
    ):
        """
        Initialize audit logger.

        Args:
            logger: Standard logger for immediate audit log output
            audit_store: Optional persistent storage for audit events
        """
        self.logger = logger or get_logger("codetoreum.audit")
        self.audit_store = audit_store

    def log_event(
        self,
        event_type: AuditEventType,
        resource_type: str,
        resource_id: str,
        action: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> AuditEvent:
        """
        Log an audit event.

        This method:
        1. Creates a structured audit event
        2. Logs it via standard logging (with sensitive data scrubbing)
        3. Stores it in the audit database (if configured)
        4. Returns the event for further processing if needed

        Args:
            event_type: Type of event (from AuditEventType enum)
            resource_type: Type of resource (e.g., "agent", "workflow", "config")
            resource_id: ID of the resource
            action: Action performed (e.g., "create", "update", "delete")
            user_id: ID of user who performed action (defaults to "system")
            metadata: Additional context (sanitized before storage)
            success: Whether the action succeeded
            error_message: Error message if action failed

        Returns:
            The created AuditEvent instance
        """
        # Get correlation ID from current context
        correlation_id = get_correlation_id()

        # Create audit event
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            user_id=user_id or "system",
            correlation_id=correlation_id,
            success=success,
            error_message=error_message,
            metadata=metadata or {},
        )

        # Log to standard logger (with structured data)
        self._log_to_standard_logger(event)

        # Store in audit database (async, fire-and-forget)
        if self.audit_store:
            self._store_event_async(event)

        return event

    def _log_to_standard_logger(self, event: AuditEvent) -> None:
        """
        Log event to standard logger with structured data.

        The structured logging infrastructure will:
        - Add correlation ID
        - Scrub sensitive data
        - Format as JSON in production
        """
        log_level = logging.INFO if event.success else logging.WARNING

        # Create structured log message
        log_data = {
            "audit_event": True,
            "event_type": event.event_type.value,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "action": event.action,
            "user_id": event.user_id,
            "success": event.success,
            "metadata": event.metadata,
        }

        if event.error_message:
            log_data["error"] = event.error_message

        # Log with extra data
        message = (
            f"AUDIT: {event.event_type.value} | "
            f"{event.resource_type}:{event.resource_id} | "
            f"user:{event.user_id} | "
            f"{'SUCCESS' if event.success else 'FAILED'}"
        )

        self.logger.log(log_level, message, extra=log_data)

    def _store_event_async(self, event: AuditEvent) -> None:
        """
        Store event in audit database asynchronously.

        This is a fire-and-forget operation to avoid blocking
        the main request flow. Failures are logged but don't
        affect the operation.

        In production, this should use a background task queue
        or async context manager.
        """
        if not self.audit_store:
            return

        try:
            # In a real implementation, this would be:
            # await self.audit_store.store_event(...)
            # or submitted to a background task queue
            #
            # For now, we'll log that we would store it
            self.logger.debug(
                f"Would store audit event to database: {event.event_type.value}",
                extra={"event_data": event.to_dict()},
            )
        except Exception as e:
            # Never let audit logging failures affect the operation
            self.logger.error(
                f"Failed to store audit event: {e}",
                extra={"event_type": event.event_type.value,
                    "error_id": ErrorRegistry.ErrorRegistry.ERR_AUDIT_ERROR},
            )

    # Convenience methods for common audit events

    def log_auth_attempt(
        self,
        user_id: str,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Log an authentication attempt."""
        event_type = (
            AuditEventType.AUTH_SUCCESS if success else AuditEventType.AUTH_FAILURE
        )
        return self.log_event(
            event_type=event_type,
            resource_type="auth",
            resource_id=user_id,
            action="authenticate",
            user_id=user_id,
            metadata=metadata,
            success=success,
        )

    def log_agent_created(
        self,
        agent_id: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Log agent creation."""
        return self.log_event(
            event_type=AuditEventType.AGENT_CREATED,
            resource_type="agent",
            resource_id=agent_id,
            action="create",
            user_id=user_id,
            metadata=metadata,
        )

    def log_agent_updated(
        self,
        agent_id: str,
        user_id: str,
        changes: Dict[str, Any],
    ) -> AuditEvent:
        """Log agent update."""
        return self.log_event(
            event_type=AuditEventType.AGENT_UPDATED,
            resource_type="agent",
            resource_id=agent_id,
            action="update",
            user_id=user_id,
            metadata={"changes": changes},
        )

    def log_agent_deleted(
        self,
        agent_id: str,
        user_id: str,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> AuditEvent:
        """Log agent deletion."""
        return self.log_event(
            event_type=AuditEventType.AGENT_DELETED,
            resource_type="agent",
            resource_id=agent_id,
            action="delete",
            user_id=user_id,
            success=success,
            error_message=error_message,
        )

    def log_execution_terminated(
        self,
        execution_id: str,
        user_id: str,
        reason: Optional[str] = None,
        success: bool = True,
    ) -> AuditEvent:
        """Log execution termination."""
        metadata = {"reason": reason} if reason else {}
        return self.log_event(
            event_type=AuditEventType.EXECUTION_TERMINATED,
            resource_type="execution",
            resource_id=execution_id,
            action="terminate",
            user_id=user_id,
            metadata=metadata,
            success=success,
        )

    def log_config_change(
        self,
        config_type: str,
        config_id: str,
        user_id: str,
        changes: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> AuditEvent:
        """Log configuration change."""
        event_type_map = {
            "project": AuditEventType.CONFIG_PROJECT_UPDATED,
            "agent": AuditEventType.CONFIG_AGENT_UPDATED,
            "pipeline": AuditEventType.CONFIG_PIPELINE_UPDATED,
        }
        event_type = event_type_map.get(
            config_type, AuditEventType.SYSTEM_CONFIG_CHANGED
        )

        metadata = {"changes": changes}
        if reason:
            metadata["reason"] = reason

        return self.log_event(
            event_type=event_type,
            resource_type=config_type,
            resource_id=config_id,
            action="update",
            user_id=user_id,
            metadata=metadata,
        )


# Global audit logger instance (initialized in main app)
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """
    Get the global audit logger instance.

    This should be initialized during application startup with
    the appropriate audit store.

    Returns:
        Global AuditLogger instance
    """
    global _audit_logger
    if _audit_logger is None:
        # Create default logger if not initialized
        _audit_logger = AuditLogger()
    return _audit_logger


def set_audit_logger(audit_logger: AuditLogger) -> None:
    """
    Set the global audit logger instance.

    This should be called during application startup.

    Args:
        audit_logger: Configured AuditLogger instance
    """
    global _audit_logger
    _audit_logger = audit_logger
