# IAuditor Output Port Design

## Overview

The `IAuditor` port provides an abstraction for audit logging and compliance tracking. This port enables recording of all security-relevant events, configuration changes, and access patterns for compliance and forensic purposes.

## Port Interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class AuditEventType(Enum):
    """Audit event types."""
    ACCESS = "access"
    MODIFICATION = "modification"
    DELETION = "deletion"
    CONFIGURATION_CHANGE = "configuration_change"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    EXECUTION = "execution"

class AuditSeverity(Enum):
    """Audit event severity."""
    INFO = 1
    WARNING = 2
    CRITICAL = 3

class IAuditor(ABC):
    """Interface for audit logging."""

    @abstractmethod
    async def record_event(self,
                          event_type: AuditEventType,
                          resource_type: str,
                          resource_id: str,
                          action: str,
                          actor: str,
                          severity: AuditSeverity = AuditSeverity.INFO,
                          details: Optional[Dict[str, Any]] = None,
                          outcome: str = "success") -> AuditEvent:
        """
        Record an audit event.

        Args:
            event_type: Type of audit event
            resource_type: Type of resource affected
            resource_id: Resource identifier
            action: Action performed
            actor: Who performed the action
            severity: Event severity
            details: Additional event details
            outcome: Outcome (success, failure, etc.)

        Returns:
            AuditEvent: Recorded audit event
        """
        pass

    @abstractmethod
    async def query_events(self,
                          start_time: datetime,
                          end_time: datetime,
                          event_type: Optional[AuditEventType] = None,
                          resource_type: Optional[str] = None,
                          actor: Optional[str] = None,
                          limit: int = 100) -> List[AuditEvent]:
        """Query audit events."""
        pass

    @abstractmethod
    async def generate_audit_report(self,
                                   start_time: datetime,
                                   end_time: datetime,
                                   report_type: str = "compliance") -> AuditReport:
        """Generate audit report."""
        pass

    @abstractmethod
    async def get_resource_history(self,
                                   resource_type: str,
                                   resource_id: str) -> List[AuditEvent]:
        """Get complete audit history for a resource."""
        pass
```

## Data Models

```python
@dataclass
class AuditEvent:
    """Audit event record."""
    event_id: str
    timestamp: datetime
    event_type: AuditEventType
    resource_type: str
    resource_id: str
    action: str
    actor: str
    severity: AuditSeverity
    outcome: str
    details: Dict[str, Any]
    client_ip: Optional[str]
    user_agent: Optional[str]

@dataclass
class AuditReport:
    """Audit report."""
    report_id: str
    generated_at: datetime
    start_time: datetime
    end_time: datetime
    total_events: int
    events_by_type: Dict[str, int]
    critical_events: List[AuditEvent]
    summary: str
```

## Adapter Implementations

### Elasticsearch Auditor

```python
class ElasticsearchAuditor(IAuditor):
    """Elasticsearch-based audit logging."""

    def __init__(self,
                 es_client,
                 index_prefix: str = "audit"):
        self.es = es_client
        self.index_prefix = index_prefix

    async def record_event(self,
                          event_type: AuditEventType,
                          resource_type: str,
                          resource_id: str,
                          action: str,
                          actor: str,
                          severity: AuditSeverity = AuditSeverity.INFO,
                          details: Optional[Dict[str, Any]] = None,
                          outcome: str = "success") -> AuditEvent:
        """Record to Elasticsearch."""
        event = AuditEvent(
            event_id=str(uuid4()),
            timestamp=datetime.utcnow(),
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            actor=actor,
            severity=severity,
            outcome=outcome,
            details=details or {},
            client_ip=None,
            user_agent=None
        )

        # Store in daily index
        await self.es.index(
            index=f"{self.index_prefix}-{event.timestamp:%Y.%m.%d}",
            id=event.event_id,
            document=asdict(event)
        )

        return event
```

### File Auditor

```python
class FileAuditor(IAuditor):
    """File-based audit logging."""

    def __init__(self, audit_directory: Path):
        self.audit_dir = audit_directory
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    async def record_event(self,
                          event_type: AuditEventType,
                          resource_type: str,
                          resource_id: str,
                          action: str,
                          actor: str,
                          severity: AuditSeverity = AuditSeverity.INFO,
                          details: Optional[Dict[str, Any]] = None,
                          outcome: str = "success") -> AuditEvent:
        """Append to audit file."""
        event = AuditEvent(
            event_id=str(uuid4()),
            timestamp=datetime.utcnow(),
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            actor=actor,
            severity=severity,
            outcome=outcome,
            details=details or {},
            client_ip=None,
            user_agent=None
        )

        # Append to daily audit file
        audit_file = self.audit_dir / f"audit-{event.timestamp:%Y%m%d}.jsonl"
        with audit_file.open('a') as f:
            f.write(json.dumps(asdict(event)) + '\n')

        return event
```

### In-Memory Auditor (Testing)

```python
class InMemoryAuditor(IAuditor):
    """In-memory audit logging for testing."""

    def __init__(self):
        self.events: List[AuditEvent] = []

    async def record_event(self,
                          event_type: AuditEventType,
                          resource_type: str,
                          resource_id: str,
                          action: str,
                          actor: str,
                          severity: AuditSeverity = AuditSeverity.INFO,
                          details: Optional[Dict[str, Any]] = None,
                          outcome: str = "success") -> AuditEvent:
        """Store in memory."""
        event = AuditEvent(
            event_id=str(uuid4()),
            timestamp=datetime.utcnow(),
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            actor=actor,
            severity=severity,
            outcome=outcome,
            details=details or {},
            client_ip=None,
            user_agent=None
        )

        self.events.append(event)
        return event

    def clear(self) -> None:
        """Clear all events (testing only)."""
        self.events.clear()
```

## Common Audit Events

### Configuration Changes
- Project configuration updates
- Agent configuration modifications
- Workflow template changes

### Access Events
- API authentication
- Configuration access
- Data export

### Execution Events
- Agent execution start/end
- Container creation/deletion
- Git operations

### Security Events
- Authentication failures
- Authorization denials
- Suspicious activity

## Integration Points

### Used By
- Configuration Management Service
- Authentication/Authorization Middleware
- All sensitive operations

### Dependencies
- None (standalone port)

## Implementation Notes

1. **Immutability**: Audit logs must be append-only
2. **Retention**: Configure long retention periods
3. **Integrity**: Consider cryptographic signatures for events
4. **Performance**: Async logging to avoid blocking
5. **Compliance**: Ensure logs meet regulatory requirements (GDPR, SOC 2, etc.)
6. **Privacy**: Redact sensitive data while maintaining auditability
