# Primary Adapters - Phase 6 Implementation

This directory contains the primary (inbound) adapters for the Codetoreum Gen 2 system, implementing Phase 6 of the implementation plan.

## Overview

Primary adapters are entry points into the system that receive external requests and translate them into domain commands through input ports. They follow the hexagonal architecture pattern, maintaining clean separation between external protocols and domain logic.

## Implemented Adapters

### 1. GitHub Webhook Adapter (`github_webhook_adapter.py`)

**Purpose**: Receives webhook events from GitHub and triggers workflows

**Features**:
- ✅ HMAC-SHA256 signature verification for security
- ✅ Webhook payload validation
- ✅ Idempotency support (prevents duplicate processing)
- ✅ Event translation to domain commands
- ✅ Support for project_card, issues, issue_comment, pull_request, and discussion events
- ✅ Repository to project mapping
- ✅ Column to pipeline stage mapping

**Endpoint**: `POST /webhooks/github`

**Headers Required**:
- `X-GitHub-Delivery`: Unique delivery ID
- `X-GitHub-Event`: Event type
- `X-Hub-Signature-256`: HMAC signature

**Status**: ✅ Complete with integration tests

---

### 2. REST API Adapter (`rest_api_adapter.py`)

**Purpose**: Provides RESTful HTTP API for programmatic access

**Features**:
- ✅ Workflow command endpoints (start, pause, resume, cancel, retry)
- ✅ Execution query endpoints (list, status, artifacts, history)
- ✅ Configuration management endpoints
- ✅ Request/response validation with Pydantic
- ✅ OpenAPI/Swagger documentation
- ✅ Pagination support
- ✅ Filtering and sorting

**Endpoints**:

**Workflow Commands**:
- `POST /api/v1/workflows` - Start workflow
- `POST /api/v1/workflows/{id}/pause` - Pause workflow
- `POST /api/v1/workflows/{id}/resume` - Resume workflow
- `POST /api/v1/workflows/{id}/cancel` - Cancel workflow
- `POST /api/v1/workflows/{id}/retry` - Retry failed stage

**Execution Queries**:
- `GET /api/v1/executions` - List executions (with filters)
- `GET /api/v1/executions/{id}` - Get execution status
- `GET /api/v1/executions/{id}/artifacts` - Get artifacts

**Configuration Commands**:
- `PATCH /api/v1/configurations/projects/{project}` - Update project config
- `POST /api/v1/configurations/projects/{project}/environment` - Add env var
- `DELETE /api/v1/configurations/projects/{project}/environment/{var}` - Remove env var

**Status**: ✅ Complete with integration tests

---

### 3. WebSocket Adapter (`websocket_adapter.py`)

**Purpose**: Real-time event streaming for workflow and execution updates

**Features**:
- ✅ Connection management with unique IDs
- ✅ Subscription-based event filtering
- ✅ Multiple subscription types (all_events, workflow_events, execution_events, logs)
- ✅ Filter by workflow_run_id, execution_id, project_name, event_types
- ✅ Broadcast events to subscribed connections
- ✅ Ping/pong keepalive support
- ✅ Error handling and graceful disconnection

**Endpoint**: `WS /ws/events`

**Message Types**:

**Subscribe**:
```json
{
  "type": "subscribe",
  "subscription_type": "workflow_events",
  "workflow_run_id": "optional-workflow-id",
  "execution_id": "optional-execution-id",
  "project_name": "optional-project-name",
  "event_types": ["optional", "list"]
}
```

**Ping/Pong**:
```json
{
  "type": "ping"
}
```

**Unsubscribe**:
```json
{
  "type": "unsubscribe"
}
```

**Status**: ✅ Complete with integration tests

---

### 4. FastAPI Application (`fastapi_app.py`)

**Purpose**: Main application setup integrating all adapters

**Features**:
- ✅ Application factory pattern
- ✅ CORS middleware configuration
- ✅ Health check endpoints (`/health`, `/health/ready`)
- ✅ OpenAPI documentation (`/api/docs`, `/api/redoc`)
- ✅ Global exception handling
- ✅ Lifecycle management (startup/shutdown)
- ✅ Development app with mock dependencies

**Status**: ✅ Complete

---

## Testing

All adapters have comprehensive integration tests:

### Test Files:
- `tests/integration/test_github_webhook_adapter.py` - 7 test cases
- `tests/integration/test_rest_api_adapter.py` - 15 test cases
- `tests/integration/test_websocket_adapter.py` - 11 test cases

### Test Coverage:
- ✅ Webhook signature verification (success and failure)
- ✅ Webhook idempotency
- ✅ Webhook payload validation
- ✅ REST API command endpoints
- ✅ REST API query endpoints with pagination
- ✅ REST API validation
- ✅ WebSocket connection management
- ✅ WebSocket subscriptions with filters
- ✅ WebSocket error handling
- ✅ Multiple concurrent connections
- ✅ Health check endpoints
- ✅ OpenAPI documentation

**Total**: 33 integration tests

### Running Tests:
```bash
# Run all primary adapter tests
pytest tests/integration/test_github_webhook_adapter.py
pytest tests/integration/test_rest_api_adapter.py
pytest tests/integration/test_websocket_adapter.py

# Or run all integration tests
pytest tests/integration/
```

---

## Usage

### Development Mode

Run the FastAPI application with mock dependencies:

```bash
cd /workspace
uvicorn codetoreum.adapters.primary.fastapi_app:app --reload --host 0.0.0.0 --port 8000
```

Access:
- API Documentation: http://localhost:8000/api/docs
- Health Check: http://localhost:8000/health
- WebSocket Test: ws://localhost:8000/ws/events

### Production Mode

Create application with real dependencies:

```python
from codetoreum.adapters.primary import create_app
from codetoreum.ports.input.workflow_command import IWorkflowCommandPort
from codetoreum.ports.input.task_query import ITaskQueryPort
from codetoreum.ports.input.config_command import IConfigurationCommandPort

# Create ports (implementations not shown)
workflow_port = WorkflowCommandPortImpl(...)
task_query_port = TaskQueryPortImpl(...)
config_port = ConfigurationCommandPortImpl(...)
event_bus = EventBusImpl(...)
config_service = ConfigurationServiceImpl(...)
logger = LoggerImpl(...)

# Create app
app = create_app(
    workflow_command_port=workflow_port,
    task_query_port=task_query_port,
    config_command_port=config_port,
    event_bus=event_bus,
    config_service=config_service,
    logger=logger,
    cors_origins=["https://codetoreum.example.com"]
)
```

---

## Architecture

### Hexagonal Architecture

```
External Systems
       ↓
Primary Adapters (This Layer)
       ↓
Input Ports (Interfaces)
       ↓
Application Services
       ↓
Domain Layer
```

### Dependencies

Primary adapters depend on:
- **Input Ports**: `IWorkflowCommandPort`, `ITaskQueryPort`, `IConfigurationCommandPort`
- **Event Bus**: For publishing observability events
- **Configuration Service**: For webhook secrets and project mappings
- **Logger**: For structured logging

### Key Design Principles

1. **Port-Adapter Pattern**: Adapters translate external protocols to domain commands
2. **Single Responsibility**: Each adapter handles one external protocol
3. **Dependency Inversion**: Adapters depend on port interfaces, not implementations
4. **Testability**: All adapters testable with mock ports
5. **Security**: HMAC verification, input validation, error handling
6. **Observability**: Structured logging, metrics, health checks

---

## Security

### GitHub Webhook
- HMAC-SHA256 signature verification
- Timing-safe comparison for signatures
- Webhook secret from environment/config
- Idempotency to prevent replay attacks

### REST API
- Request validation with Pydantic
- Input sanitization
- Rate limiting (TODO: Phase 9)
- Authentication (TODO: Phase 6.4)

### WebSocket
- Connection authentication (TODO: Phase 6.4)
- Subscription authorization (TODO: Phase 6.4)
- Error information disclosure protection

---

## Next Steps (Remaining from Phase 6)

### 6.4 Authentication & Authorization (Not Implemented)
- [ ] JWT token-based authentication
- [ ] API key support
- [ ] Role-based access control (RBAC)
- [ ] Permission checks on endpoints
- [ ] Project-level access control

### 6.5 CLI Adapter (Not Implemented)
- [ ] CLI using Click or Typer
- [ ] Command structure mirroring API
- [ ] Configuration file support
- [ ] Output formatting (tables, JSON)

### 6.6 Basic Web Dashboard (Not Implemented)
- [ ] React/Vue web UI
- [ ] Workflow list and details
- [ ] Execution list and details
- [ ] Real-time log streaming
- [ ] E2E tests with Playwright/Cypress

---

## Design Documents

Refer to the following design documents for detailed specifications:
- `documentation/01_design/primary_adapters/github_webhook_adapter_design.md`
- `documentation/01_design/primary_adapters/primary_adapters_inventory.md`
- `documentation/01_design/02_high_level_arch.md`
- `documentation/01_design/03_implementation_plan.md`

---

## Summary

This Phase 6 Part 1 implementation provides:

✅ **GitHub Webhook Adapter** - Real-time workflow triggering from GitHub events
✅ **REST API Adapter** - Complete programmatic API for workflow and configuration management
✅ **WebSocket Adapter** - Real-time event streaming with flexible filtering
✅ **FastAPI Application** - Production-ready application with OpenAPI docs
✅ **Comprehensive Tests** - 33 integration tests covering all functionality

**Status**: Phase 6.1, 6.2, and 6.3 complete. Authentication (6.4), CLI (6.5), and Web Dashboard (6.6) remain for future implementation.
