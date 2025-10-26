# Primary Adapters Inventory

## Overview

Primary adapters are the entry points into the Codetoreum system. They receive external requests and translate them into domain commands that can be processed by the application core. In the hexagonal architecture, primary adapters sit at the boundary between external systems and the input ports.

## Architecture Context

```
┌─────────────────────────────────────────────────────────────────┐
│                      EXTERNAL SYSTEMS                            │
│  GitHub | Web UI | CLI | REST API | Scheduled Events            │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                     PRIMARY ADAPTERS                             │
│  ┌──────────────┐  ┌───────────┐  ┌───────────┐  ┌──────────┐ │
│  │   GitHub     │  │    Web    │  │    CLI    │  │   REST   │ │
│  │   Webhook    │  │    UI     │  │  Adapter  │  │   API    │ │
│  │   Adapter    │  │  Adapter  │  │           │  │ Adapter  │ │
│  └──────┬───────┘  └─────┬─────┘  └─────┬─────┘  └────┬─────┘ │
└─────────┼────────────────┼──────────────┼─────────────┼────────┘
          │                │              │             │
┌─────────▼────────────────▼──────────────▼─────────────▼─────────┐
│                        INPUT PORTS                               │
│  WorkflowCommandPort | TaskQueryPort | EventStreamPort          │
│  ConfigCommandPort | AgentCommandPort | MetricsQueryPort        │
└──────────────────────────────────────────────────────────────────┘
```

## Design Principles

### Separation of Concerns
- **Adapters** handle external protocol details (HTTP, webhooks, CLI)
- **Ports** define pure domain interfaces
- **Adapters** translate external formats to domain types
- **Domain core** remains ignorant of external systems

### Single Responsibility
Each adapter is responsible for:
1. Receiving requests from a specific external system
2. Authenticating and authorizing requests
3. Validating input data
4. Translating external data to domain commands
5. Invoking appropriate input ports
6. Translating domain responses back to external format

### Dependency Direction
```
External System → Primary Adapter → Input Port → Application Service → Domain
```

Dependencies flow inward. Adapters depend on ports, never vice versa.

## Inventory of Primary Adapters

### 1. GitHub Webhook Adapter
**Purpose**: Receives webhook events from GitHub and triggers workflows

**External Interface**: HTTP POST endpoint receiving GitHub webhook payloads

**Input Ports Used**:
- `WorkflowCommandPort` - Start workflows based on card movements
- `AgentCommandPort` - Trigger agent feedback loops
- `EventStreamPort` - Publish webhook processing events

**Key Responsibilities**:
- HMAC signature verification
- Webhook payload validation
- Project identification from repository
- Column-to-stage mapping
- Trigger classification (card movement, feedback, etc.)
- Command translation

**Supported GitHub Events**:
- `project_card` (moved) - Card movement between columns
- `issues` (opened, edited) - New work items
- `issue_comment` (created) - Agent feedback/questions
- `pull_request` (opened, synchronize) - Code review triggers
- `discussion` (created, answered) - Discussion-based workflows

**Configuration Required**:
- Webhook secret for signature verification
- Repository to project mapping
- Board name to pipeline mapping
- Column to stage/agent mapping

**Design Document**: [github_webhook_adapter_design.md](github_webhook_adapter_design.md)

---

### 2. Web UI Adapter (REST/WebSocket)
**Purpose**: Provides HTTP/WebSocket API for web-based user interface

**External Interface**: REST API + WebSocket connections

**Input Ports Used**:
- `TaskQueryPort` - Query task status and history
- `ProjectQueryPort` - List projects and get details
- `MetricsQueryPort` - System metrics and analytics
- `EventStreamPort` - Real-time event subscriptions
- `LogStreamPort` - Real-time log streaming
- `ConfigCommandPort` - Configuration management
- `AgentCommandPort` - Manual agent control

**Key Responsibilities**:
- HTTP request handling (FastAPI/Flask)
- WebSocket connection management
- User authentication (session/JWT)
- Authorization checks
- Request validation
- Response formatting (JSON)
- Real-time event streaming
- CORS handling

**API Endpoints**:
- `GET /api/projects` - List projects
- `GET /api/projects/{id}` - Get project details
- `GET /api/tasks` - List tasks
- `GET /api/tasks/{id}` - Get task status
- `GET /api/metrics` - System metrics
- `POST /api/workflows` - Start workflow manually
- `POST /api/agents/{id}/cancel` - Cancel agent execution
- `WS /ws/events` - Event stream subscription
- `WS /ws/logs` - Log stream subscription

**Authentication Methods**:
- Session cookies (web UI)
- JWT tokens (API clients)
- API keys (service accounts)

**Design Document**: [web_ui_adapter_design.md](web_ui_adapter_design.md)

---

### 3. CLI Adapter
**Purpose**: Command-line interface for system administration and operation

**External Interface**: Command-line arguments and interactive prompts

**Input Ports Used**:
- `ConfigCommandPort` - Configuration management
- `ProjectCommandPort` - Project CRUD operations
- `WorkflowCommandPort` - Workflow control
- `AgentCommandPort` - Agent management
- `TaskQueryPort` - Task inspection
- `MetricsQueryPort` - System health checks

**Key Responsibilities**:
- Command parsing (Click/Typer framework)
- Interactive prompts
- Output formatting (tables, JSON, YAML)
- Configuration file management
- Error reporting
- Progress indicators
- Color-coded output

**Command Groups**:
```bash
# Project management
codetoreum project list
codetoreum project create <name>
codetoreum project config <name>

# Workflow control
codetoreum workflow start <project> <issue>
codetoreum workflow status <workflow-id>
codetoreum workflow cancel <workflow-id>

# Agent management
codetoreum agent list
codetoreum agent execute <name> <project> <issue>
codetoreum agent logs <execution-id>

# Configuration
codetoreum config show
codetoreum config set <key> <value>
codetoreum config validate

# System operations
codetoreum health
codetoreum metrics
codetoreum logs --follow
```

**Configuration Sources**:
- Command-line arguments (highest priority)
- Environment variables
- Configuration files (.yaml)
- Default values (lowest priority)

**Design Document**: [cli_adapter_design.md](cli_adapter_design.md)

---

### 4. REST API Adapter
**Purpose**: Programmatic API for external integrations and automation

**External Interface**: RESTful HTTP API with JSON payloads

**Input Ports Used**:
- `WorkflowCommandPort` - Workflow operations
- `TaskQueryPort` - Task queries
- `ProjectQueryPort` - Project queries
- `MetricsQueryPort` - Metrics access
- `ConfigCommandPort` - Configuration updates
- `AgentCommandPort` - Agent control

**Key Responsibilities**:
- RESTful request handling
- API versioning (URL path: /api/v1/)
- Request/response validation (Pydantic)
- Authentication (API keys, OAuth)
- Rate limiting
- Pagination
- Filtering and sorting
- HATEOAS links
- OpenAPI/Swagger documentation

**API Design Patterns**:
```http
# Resource collections
GET /api/v1/workflows
POST /api/v1/workflows

# Individual resources
GET /api/v1/workflows/{id}
PATCH /api/v1/workflows/{id}
DELETE /api/v1/workflows/{id}

# Sub-resources
GET /api/v1/workflows/{id}/stages
GET /api/v1/workflows/{id}/events

# Actions
POST /api/v1/workflows/{id}/cancel
POST /api/v1/workflows/{id}/retry
```

**Response Format**:
```json
{
  "data": {
    "id": "workflow-123",
    "type": "workflow",
    "attributes": { ... },
    "relationships": { ... },
    "links": {
      "self": "/api/v1/workflows/workflow-123"
    }
  },
  "meta": {
    "timestamp": "2025-10-26T12:00:00Z",
    "version": "1.0"
  }
}
```

**Authentication**:
- API key header: `X-API-Key: <key>`
- OAuth 2.0 Bearer tokens
- Service account credentials

**Design Document**: [rest_api_adapter_design.md](rest_api_adapter_design.md)

---

### 5. Scheduler Adapter
**Purpose**: Triggers workflows and tasks based on time-based schedules

**External Interface**: Internal cron/scheduler system

**Input Ports Used**:
- `WorkflowCommandPort` - Start scheduled workflows
- `AgentCommandPort` - Trigger periodic agent tasks
- `ConfigCommandPort` - Schedule configuration updates

**Key Responsibilities**:
- Cron expression parsing
- Schedule evaluation
- Missed execution handling
- Timezone management
- Execution history tracking
- Schedule configuration

**Schedule Types**:
```yaml
schedules:
  # Cron-based schedules
  - name: "nightly-analysis"
    cron: "0 2 * * *"  # 2 AM daily
    workflow: "automated-analysis"
    timezone: "UTC"

  # Interval-based schedules
  - name: "health-check"
    interval: "5m"
    agent: "health_monitor"

  # One-time schedules
  - name: "deployment"
    at: "2025-10-27T10:00:00Z"
    workflow: "prod-deployment"
```

**Execution Guarantees**:
- At-least-once execution (may retry on failure)
- Idempotency required for scheduled workflows
- No guarantee of exact timing (within tolerance)
- Missed executions logged but not automatically retried

**Design Document**: [scheduler_adapter_design.md](scheduler_adapter_design.md)

---

### 6. Event Replay Adapter
**Purpose**: Replays historical events for testing and recovery

**External Interface**: Administrative API or CLI

**Input Ports Used**:
- `EventStreamPort` - Query historical events
- `WorkflowCommandPort` - Replay workflow commands
- `AgentCommandPort` - Replay agent executions

**Key Responsibilities**:
- Event store querying
- Event filtering and selection
- Replay speed control
- State snapshots
- Replay validation
- Progress tracking

**Replay Modes**:
```python
class ReplayMode(Enum):
    FULL = "full"           # Replay all events
    SELECTIVE = "selective"  # Replay filtered events
    TIME_RANGE = "time_range"  # Replay events in time range
    CHECKPOINT = "checkpoint"  # Replay from checkpoint

class ReplaySpeed(Enum):
    REALTIME = "realtime"    # Original timing
    FAST = "fast"            # 10x speed
    INSTANT = "instant"      # No delays
```

**Use Cases**:
- System recovery after failure
- Testing new features with production data
- Debugging historical issues
- Performance testing with realistic load
- Training and demonstrations

**Design Document**: [event_replay_adapter_design.md](event_replay_adapter_design.md)

---

## Adapter Comparison Matrix

| Adapter | Protocol | Synchronous | Authentication | Primary Use Case |
|---------|----------|-------------|----------------|------------------|
| GitHub Webhook | HTTP | Async | HMAC | Workflow triggering |
| Web UI | HTTP/WS | Mixed | Session/JWT | User interaction |
| CLI | Process | Sync | Config file | Administration |
| REST API | HTTP | Sync | API Key/OAuth | Integration |
| Scheduler | Internal | Async | N/A | Automation |
| Event Replay | Internal | Async | Admin | Recovery/Testing |

## Common Adapter Patterns

### 1. Request Validation Pattern
All adapters follow consistent validation:

```python
class BaseAdapter:
    async def handle_request(self, request: ExternalRequest):
        # 1. Authenticate
        auth_context = await self.authenticate(request)

        # 2. Validate input
        validation = await self.validate_input(request)
        if not validation.valid:
            raise ValidationError(validation.errors)

        # 3. Translate to domain command
        command = self.translate_to_command(request)

        # 4. Authorize
        if not await self.authorize(auth_context, command):
            raise AuthorizationError()

        # 5. Execute via port
        result = await self.port.execute(command)

        # 6. Translate response
        return self.translate_from_result(result)
```

### 2. Error Translation Pattern
Domain errors translated to external formats:

```python
class AdapterErrorHandler:
    def translate_error(self, error: DomainError) -> ExternalError:
        if isinstance(error, ValidationError):
            return HTTP400BadRequest(error.message)
        elif isinstance(error, AuthorizationError):
            return HTTP403Forbidden(error.message)
        elif isinstance(error, NotFoundError):
            return HTTP404NotFound(error.message)
        else:
            return HTTP500InternalServerError("Internal error")
```

### 3. Event Streaming Pattern
Real-time event delivery:

```python
class EventStreamingAdapter:
    def __init__(self, event_stream_port: EventStreamPort):
        self.port = event_stream_port
        self.connections: Dict[str, WebSocket] = {}

    async def subscribe(self, connection_id: str, filters: EventFilters):
        # Subscribe to event stream
        async for event in self.port.subscribe(filters):
            # Translate to external format
            external_event = self.translate_event(event)
            # Send to connection
            await self.send_to_connection(connection_id, external_event)
```

## Testing Strategies

### Unit Testing
Test adapters in isolation:
- Mock input ports
- Verify translation logic
- Test validation rules
- Test error handling

### Integration Testing
Test adapter with real ports:
- In-memory port implementations
- End-to-end request handling
- Event streaming verification

### Contract Testing
Verify adapter-port contracts:
- Port interface compliance
- Command structure validation
- Error response formats

### Simulation Testing
Test with mock external systems:
- Mock GitHub webhooks
- Simulated HTTP clients
- Fake CLI inputs
- Canned event streams

## Configuration Management

### Adapter Configuration Structure
```yaml
adapters:
  github_webhook:
    enabled: true
    port: 8080
    path: "/webhooks/github"
    secret: "${GITHUB_WEBHOOK_SECRET}"

  web_ui:
    enabled: true
    host: "0.0.0.0"
    port: 5000
    cors_origins:
      - "http://localhost:3000"
    session_secret: "${SESSION_SECRET}"

  rest_api:
    enabled: true
    base_path: "/api/v1"
    rate_limit: 100/minute
    auth_methods:
      - api_key
      - oauth

  cli:
    enabled: true
    config_file: "~/.codetoreum/config.yaml"

  scheduler:
    enabled: true
    schedules_file: "./schedules.yaml"
```

## Observability

### Adapter Metrics
Each adapter emits:
- Request count (by endpoint/command)
- Request duration (p50, p95, p99)
- Error rate (by error type)
- Active connections (for streaming)
- Authentication failures
- Validation failures

### Adapter Events
```python
# Request received
AdapterRequestReceivedEvent(
    adapter_name=str,
    request_id=str,
    timestamp=datetime
)

# Request processed
AdapterRequestProcessedEvent(
    adapter_name=str,
    request_id=str,
    duration_ms=float,
    success=bool
)

# Request failed
AdapterRequestFailedEvent(
    adapter_name=str,
    request_id=str,
    error_type=str,
    error_message=str
)
```

## Security Considerations

### Authentication
- GitHub: HMAC signature verification
- Web UI: Session cookies or JWT tokens
- CLI: Configuration file credentials
- REST API: API keys or OAuth tokens
- Scheduler: Internal (no external auth)
- Event Replay: Admin-only access

### Authorization
- Role-based access control (RBAC)
- Resource-level permissions
- Tenant isolation (multi-tenancy)

### Input Validation
- Schema validation (JSON Schema, Pydantic)
- Type checking
- Range validation
- Format validation (email, URL, etc.)

### Rate Limiting
- Per-adapter rate limits
- Per-user/tenant rate limits
- Token bucket algorithm
- Circuit breakers for external systems

## Migration from Legacy System

### Legacy Components Being Replaced

| Legacy Component | New Primary Adapter | Notes |
|------------------|---------------------|-------|
| ProjectMonitor (polling) | GitHub Webhook Adapter | Push-based instead of poll-based |
| Observability Server | Web UI Adapter | Enhanced with real-time features |
| CLI (if exists) | CLI Adapter | Standardized command structure |
| GitHub API polling | GitHub Webhook Adapter | More efficient and responsive |

### Migration Strategy
1. Deploy adapters alongside legacy system
2. Configure webhooks while maintaining polling (dual mode)
3. Verify webhook reliability
4. Disable polling once webhooks proven stable
5. Remove legacy monitoring code

### Backward Compatibility
- Maintain existing API endpoints during transition
- Provide adapter configuration for gradual rollout
- Support both old and new authentication methods
- Deprecation warnings for legacy endpoints

## Next Steps

For detailed design of each adapter, see:
1. [GitHub Webhook Adapter Design](github_webhook_adapter_design.md)
2. [Web UI Adapter Design](web_ui_adapter_design.md)
3. [CLI Adapter Design](cli_adapter_design.md)
4. [REST API Adapter Design](rest_api_adapter_design.md)
5. [Scheduler Adapter Design](scheduler_adapter_design.md)
6. [Event Replay Adapter Design](event_replay_adapter_design.md)

## Summary

Primary adapters are the entry points to the Codetoreum system, providing:
- **GitHub Webhook Adapter**: Real-time workflow triggering
- **Web UI Adapter**: Interactive user interface
- **CLI Adapter**: Command-line administration
- **REST API Adapter**: Programmatic integration
- **Scheduler Adapter**: Time-based automation
- **Event Replay Adapter**: Testing and recovery

All adapters follow hexagonal architecture principles, translating external protocols to domain commands through well-defined input ports.
