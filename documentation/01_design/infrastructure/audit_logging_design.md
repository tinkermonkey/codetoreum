# Audit Logging Infrastructure Design

## Overview

The audit logging infrastructure provides comprehensive tracking of security-sensitive operations in Codetoreum. This system ensures compliance, security monitoring, and provides a complete audit trail for all critical actions.

## Purpose

The audit logging system serves several key purposes:

1. **Security Monitoring**: Track all authentication attempts and access patterns
2. **Compliance**: Maintain records for regulatory requirements
3. **Incident Response**: Provide detailed forensic data for security investigations
4. **Change Tracking**: Record all configuration and resource modifications
5. **Accountability**: Associate all actions with user identities

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     Application Layer                           │
│  (Uses audit logger for security-sensitive operations)          │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                   Audit Logging Layer                           │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ AuditLogger                                                 │ │
│  │ - Log security events with context                         │ │
│  │ - Include user ID, correlation ID, metadata                │ │
│  │ - Support convenience methods for common events            │ │
│  └─────────────────────┬──────────────────────────────────────┘ │
│                        │                                         │
│  ┌─────────────────────▼──────────────────────────────────────┐ │
│  │ IAuditStore (Interface)                                     │ │
│  │ - Store audit events                                        │ │
│  │ - Query events with filters                                │ │
│  │ - Support retention policies                               │ │
│  └─────────────────────┬──────────────────────────────────────┘ │
│                        │                                         │
│  ┌─────────────────────▼──────────────────────────────────────┐ │
│  │ Store Implementations                                       │ │
│  │ - InMemoryAuditStore (dev/testing)                         │ │
│  │ - FileAuditStore (simple persistent storage)               │ │
│  │ - PostgreSQLAuditStore (production - TODO)                 │ │
│  │ - ElasticsearchAuditStore (advanced search - TODO)         │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ RetentionPolicyManager                                      │ │
│  │ - Enforce retention policies                               │ │
│  │ - Periodic cleanup of old events                           │ │
│  │ - Configurable retention periods                           │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### Integration Points

The audit logger is integrated at the following points:

1. **Authentication Layer**: All authentication attempts (success and failure)
2. **API Routers**: Configuration changes, agent/workflow modifications
3. **Execution Control**: Execution terminations and control operations
4. **Future**: User management (when multi-user support is added)

## Audit Event Structure

### AuditEvent Data Model

```python
@dataclass
class AuditEvent:
    timestamp: datetime          # When the event occurred
    event_type: AuditEventType   # Type of event (enum)
    resource_type: str           # Type of resource (agent, workflow, config, etc.)
    resource_id: str             # ID of the resource
    action: str                  # Action performed (create, update, delete, etc.)
    user_id: str                 # User who performed the action
    correlation_id: Optional[str] # Request correlation ID
    success: bool                # Whether the action succeeded
    error_message: Optional[str] # Error message if failed
    metadata: Dict[str, Any]     # Additional context
```

### Event Types

The system tracks the following categories of events:

#### Authentication Events
- `AUTH_SUCCESS`: Successful authentication
- `AUTH_FAILURE`: Failed authentication attempt
- `AUTH_TOKEN_VALIDATED`: Token validation succeeded
- `AUTH_TOKEN_INVALID`: Invalid token format or content

#### Agent Events
- `AGENT_CREATED`: New agent created
- `AGENT_UPDATED`: Agent configuration updated
- `AGENT_DELETED`: Agent deleted
- `AGENT_CAPABILITY_MODIFIED`: Agent capabilities changed
- `AGENT_MCP_SERVER_ADDED`: MCP server added to agent
- `AGENT_MCP_SERVER_REMOVED`: MCP server removed from agent

#### Workflow Events
- `WORKFLOW_CREATED`: New workflow created
- `WORKFLOW_UPDATED`: Workflow configuration updated
- `WORKFLOW_DELETED`: Workflow deleted
- `WORKFLOW_STAGE_ADDED`: Stage added to workflow
- `WORKFLOW_STAGE_REMOVED`: Stage removed from workflow

#### Configuration Events
- `CONFIG_PROJECT_CREATED`: Project configuration created
- `CONFIG_PROJECT_UPDATED`: Project configuration updated
- `CONFIG_AGENT_UPDATED`: Agent configuration updated
- `CONFIG_PIPELINE_UPDATED`: Pipeline configuration updated
- `CONFIG_ENV_VAR_ADDED`: Environment variable added
- `CONFIG_ENV_VAR_REMOVED`: Environment variable removed
- `CONFIG_SECRET_ADDED`: Secret added
- `CONFIG_SECRET_REMOVED`: Secret removed

#### Execution Events
- `EXECUTION_STARTED`: Execution started
- `EXECUTION_TERMINATED`: Execution manually terminated
- `EXECUTION_FORCE_STOPPED`: Execution forcefully stopped
- `EXECUTION_COMPLETED`: Execution completed successfully
- `EXECUTION_FAILED`: Execution failed

## Storage Backends

### InMemoryAuditStore
- **Use Case**: Development, testing, simulation
- **Pros**: Fast, simple, no external dependencies
- **Cons**: Not persistent, lost on restart
- **Features**: Full querying, filtering, cleanup

### FileAuditStore
- **Use Case**: Small-scale deployments, proof-of-concept
- **Pros**: Simple, persistent, human-readable
- **Cons**: Not scalable, slow for large logs
- **Format**: Newline-delimited JSON (NDJSON)
- **Features**: Full querying (in-memory), filtering, cleanup

### PostgreSQLAuditStore (TODO)
- **Use Case**: Production deployments
- **Pros**: Scalable, indexed, ACID compliant
- **Cons**: Requires database setup
- **Features**:
  - Separate audit database (isolate from main DB)
  - Indexed for fast querying
  - Support for retention policies
  - Full transaction support

### ElasticsearchAuditStore (TODO)
- **Use Case**: Advanced search and analytics
- **Pros**: Full-text search, aggregations, real-time analytics
- **Cons**: Additional infrastructure
- **Features**:
  - Advanced filtering and search
  - Time-series aggregations
  - Dashboard integration

## Retention Policies

### Default Retention Periods

```python
default_retention_days: int = 90           # 3 months
authentication_events_days: int = 30       # 1 month
configuration_events_days: int = 365       # 1 year
execution_events_days: int = 60            # 2 months
security_events_days: int = 365            # 1 year
```

### Cleanup Schedule

- **Frequency**: Daily (configurable)
- **Method**: Batch deletion to avoid DB locks
- **Safety**: Never delete events less than 7 days old
- **Logging**: All cleanup operations are logged

### Configuration

```python
policy = RetentionPolicy(
    default_retention_days=90,
    authentication_events_days=30,
    cleanup_interval_hours=24,
    min_retention_days=7,
    max_batch_size=1000
)

manager = RetentionPolicyManager(audit_store, policy)
await manager.start_periodic_cleanup()
```

## Usage Examples

### Basic Event Logging

```python
from codetoreum.infrastructure.audit import get_audit_logger, AuditEventType

audit_logger = get_audit_logger()

# Log successful operation
audit_logger.log_event(
    event_type=AuditEventType.AGENT_CREATED,
    resource_type="agent",
    resource_id="agent-123",
    action="create",
    user_id="user-456",
    metadata={"agent_name": "code-reviewer", "model": "claude-3"},
    success=True
)

# Log failed operation
audit_logger.log_event(
    event_type=AuditEventType.AGENT_DELETED,
    resource_type="agent",
    resource_id="agent-123",
    action="delete",
    user_id="user-456",
    success=False,
    error_message="Agent not found"
)
```

### Convenience Methods

```python
# Log authentication
audit_logger.log_auth_attempt(
    user_id="user-123",
    success=True,
    metadata={"source": "web"}
)

# Log agent operations
audit_logger.log_agent_created(
    agent_id="agent-123",
    user_id="user-456",
    metadata={"agent_name": "test-agent"}
)

audit_logger.log_agent_updated(
    agent_id="agent-123",
    user_id="user-456",
    changes={"model": "claude-4"}
)

audit_logger.log_agent_deleted(
    agent_id="agent-123",
    user_id="user-456",
    success=True
)

# Log execution termination
audit_logger.log_execution_terminated(
    execution_id="exec-123",
    user_id="user-456",
    reason="User requested",
    success=True
)

# Log configuration changes
audit_logger.log_config_change(
    config_type="agent",
    config_id="agent-123",
    user_id="user-456",
    changes={"timeout": 600},
    reason="Performance tuning"
)
```

### Router Integration

```python
from fastapi import APIRouter
from codetoreum.infrastructure.audit import get_audit_logger

@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    audit_logger = get_audit_logger()

    try:
        await command_port.delete_agent(agent_id)

        audit_logger.log_agent_deleted(
            agent_id=agent_id,
            user_id="api-user",
            success=True
        )

        return {"status": "deleted"}

    except Exception as e:
        audit_logger.log_agent_deleted(
            agent_id=agent_id,
            user_id="api-user",
            success=False,
            error_message=str(e)
        )
        raise
```

### Authentication Integration

```python
# In authentication dependency
class SimpleAuthDependencies:
    def __init__(self, auth_manager, audit_logger):
        self.auth_manager = auth_manager
        self.audit_logger = audit_logger

    async def require_auth(self, token: str):
        if not self._validate_token_format(token):
            self.audit_logger.log_event(
                event_type=AuditEventType.AUTH_TOKEN_INVALID,
                resource_type="auth",
                resource_id="token",
                action="validate",
                success=False,
                error_message="Invalid token format"
            )
            raise HTTPException(401, "Invalid token")

        if self.auth_manager.validate_token(token):
            self.audit_logger.log_event(
                event_type=AuditEventType.AUTH_SUCCESS,
                resource_type="auth",
                resource_id="token",
                action="authenticate",
                success=True
            )
            return True

        self.audit_logger.log_event(
            event_type=AuditEventType.AUTH_FAILURE,
            resource_type="auth",
            resource_id="token",
            action="authenticate",
            success=False
        )
        raise HTTPException(401, "Invalid token")
```

## CLI Tools

### Query Audit Logs

```bash
# Query all events
python -m codetoreum.infrastructure.audit.cli query

# Filter by event type
python -m codetoreum.infrastructure.audit.cli query \
    --event-type agent_created

# Filter by user
python -m codetoreum.infrastructure.audit.cli query \
    --user-id user-123

# Filter by time range
python -m codetoreum.infrastructure.audit.cli query \
    --days-ago 7 --limit 100

# JSON output
python -m codetoreum.infrastructure.audit.cli query \
    --format json > audit_events.json
```

### Cleanup Old Logs

```bash
# Dry run (show what would be deleted)
python -m codetoreum.infrastructure.audit.cli cleanup \
    --retention-days 90 --dry-run

# Actually delete old events
python -m codetoreum.infrastructure.audit.cli cleanup \
    --retention-days 90

# Custom retention period
python -m codetoreum.infrastructure.audit.cli cleanup \
    --retention-days 30
```

### Show Statistics

```bash
# Show audit log statistics
python -m codetoreum.infrastructure.audit.cli stats

# Output:
# Audit Log Statistics:
#   Total events: 1523
#   Successful: 1498
#   Failed: 25
#   Last 24 hours: 142
```

### Get Specific Event

```bash
# Get event by ID
python -m codetoreum.infrastructure.audit.cli get <event-id>
```

## Security Considerations

### Data Protection

1. **Sensitive Data Scrubbing**: The existing `SensitiveDataFilter` from the logging infrastructure automatically scrubs sensitive data from audit logs
2. **No Credential Storage**: Never log passwords, API keys, tokens, or other credentials
3. **Metadata Sanitization**: Review metadata before logging to ensure no sensitive data

### Access Control

1. **Separate Database**: Audit logs should be stored in a separate database with restricted access
2. **Read-Only Access**: Most users should only have read-only access to audit logs
3. **Admin-Only Deletion**: Only administrators should be able to delete audit events
4. **Audit the Auditors**: Log all access to audit logs

### Compliance

1. **Retention Requirements**: Configure retention policies to meet regulatory requirements
2. **Immutability**: Once logged, events should not be modified
3. **Complete Trail**: Log both successful and failed operations
4. **User Context**: Always include user identity (preparation for multi-user)

## Performance Considerations

### Write Performance

1. **Fire-and-Forget**: Audit logging should not block main operations
2. **Async Storage**: Use background tasks for persistent storage
3. **Batching**: Consider batching writes for high-volume scenarios
4. **Circuit Breaker**: If audit store fails, log to fallback (file) but continue operation

### Query Performance

1. **Indexing**: Index commonly-queried fields (timestamp, event_type, user_id, resource_id)
2. **Pagination**: Always use pagination for large result sets
3. **Time-Based Partitioning**: Partition by month for large audit tables
4. **Archiving**: Move old events to cold storage after retention period

### Storage

1. **Compression**: Use compression for file-based storage
2. **Rotation**: Rotate log files to prevent unbounded growth
3. **Archival**: Archive old logs to cheaper storage (S3, etc.)

## Future Enhancements

### PostgreSQL Store
- Separate audit database
- Full indexing for fast queries
- Transaction support
- Bulk insert optimization

### Elasticsearch Integration
- Full-text search
- Advanced aggregations
- Real-time dashboards
- Alerting on suspicious patterns

### Multi-User Support
- User identity tracking (when multi-user is added)
- Role-based audit filtering
- Per-user audit trails

### Advanced Features
- Audit event signatures (cryptographic verification)
- Webhook notifications for critical events
- Integration with SIEM systems
- Anomaly detection
- Compliance report generation

## Testing

The audit logging system includes comprehensive tests:

- **Unit Tests**: Test individual components (logger, stores, retention)
- **Integration Tests**: Test end-to-end workflows
- **Performance Tests**: Ensure audit logging doesn't impact performance
- **Compliance Tests**: Verify retention policies work correctly

## References

- Implementation: `src/codetoreum/infrastructure/audit/`
- Tests: `tests/unit/infrastructure/audit/`
- CLI: `src/codetoreum/infrastructure/audit/cli.py`
- Logging Infrastructure: `documentation/01_design/infrastructure/logging.md` (if exists)
