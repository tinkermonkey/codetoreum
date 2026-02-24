# Codetoreum API Documentation

Comprehensive API documentation, examples, and SDK clients for the Codetoreum AI Agent Orchestration Platform.

## Contents

- [OpenAPI Specification](#openapi-specification)
- [Code Examples](#code-examples)
- [SDK Clients](#sdk-clients)
- [Postman Collection](#postman-collection)
- [Authentication](#authentication)
- [Security Best Practices](#security-best-practices)
- [Quick Start](#quick-start)

## OpenAPI Specification

The OpenAPI specification is available in multiple formats:

- **YAML**: [`openapi.yaml`](openapi.yaml)
- **JSON**: [`openapi.json`](openapi.json)
- **Generator Script**: [`generate_openapi.py`](generate_openapi.py)

### Viewing the Spec

**Swagger UI** (Interactive Documentation):
```
http://localhost:8000/api/docs
```

**ReDoc** (Clean Reference):
```
http://localhost:8000/api/redoc
```

**Raw JSON**:
```
http://localhost:8000/api/openapi.json
```

### Generating the Spec

```bash
cd documentation/api
python generate_openapi.py
```

This will create enhanced `openapi.yaml` and `openapi.json` files with:
- Comprehensive authentication documentation
- Request/response examples for all endpoints
- Error response examples
- Detailed descriptions

## Code Examples

### Python Examples

Located in [`examples/python/`](examples/python/):

| File | Description |
|------|-------------|
| `create_agent.py` | Create agents with capabilities and MCP servers |
| `list_executions.py` | List and monitor agent executions |
| `start_workflow.py` | Create work items and start workflows |

**Running Python Examples**:
```bash
# Set your API token
export API_TOKEN="your_token_here"

# Run examples
python examples/python/create_agent.py
python examples/python/list_executions.py
python examples/python/start_workflow.py
```

### TypeScript Examples

Located in [`examples/typescript/`](examples/typescript/):

| File | Description |
|------|-------------|
| `create_agent.ts` | Create agents with TypeScript |
| `list_executions.ts` | Monitor executions with TypeScript |
| `websocket_events.ts` | WebSocket event streaming with TypeScript |

**Running TypeScript Examples**:
```bash
# Install dependencies
npm install ws @types/ws

# Set your API token
export API_TOKEN="your_token_here"

# Run with ts-node
npx ts-node examples/typescript/create_agent.ts
npx ts-node examples/typescript/list_executions.ts
npx ts-node examples/typescript/websocket_events.ts
```

### cURL Examples

Located in [`examples/curl/`](examples/curl/):

| File | Description |
|------|-------------|
| `authentication.sh` | Authentication methods and best practices |
| `create_agent.sh` | Create agents with cURL |
| `list_executions.sh` | Monitor executions with cURL |
| `start_workflow.sh` | Start workflows with cURL |

**Running cURL Examples**:
```bash
# Set your API token
export API_TOKEN="your_token_here"

# Run scripts
./examples/curl/authentication.sh
./examples/curl/create_agent.sh
./examples/curl/list_executions.sh
./examples/curl/start_workflow.sh
```

## SDK Clients

### Python SDK

**Installation**:
```bash
pip install codetoreum-client
```

**Quick Start**:
```python
from codetoreum_client import CodetoreumClient

client = CodetoreumClient(
    base_url="http://localhost:8000",
    api_token="your_token_here"
)

# Create a work item
work_item = client.work_items.create(
    title="Implement feature X",
    description="Add feature X to the system",
    project_id="my-project",
    labels=["feature"]
)

# Start a workflow
workflow_run = client.orchestrator.start_workflow(work_item.id)

# Monitor execution
for execution in client.executions.list(status="running").items:
    print(f"{execution.id}: {execution.status}")
```

**Documentation**: See [`sdk/python/README.md`](sdk/python/README.md)

**Source Code**: [`sdk/python/codetoreum_client/`](sdk/python/codetoreum_client/)

### TypeScript SDK

**Status**: Coming soon

The TypeScript SDK is planned and will provide similar functionality to the Python SDK with full TypeScript type definitions.

## Postman Collection

**File**: [`postman_collection.json`](postman_collection.json)

### Importing into Postman

1. Open Postman
2. Click "Import" button
3. Select `postman_collection.json`
4. Create an environment with these variables:
   - `base_url`: `http://localhost:8000`
   - `api_token`: Your authentication token

### Collection Features

- **80+ API endpoints** organized by resource
- **Example requests** with sample data
- **Example responses** showing expected output
- **Environment variables** for easy configuration
- **Bearer token authentication** pre-configured

### Collection Structure

```
Codetoreum API/
├── Health & Authentication
├── Work Items
│   ├── Create Work Item
│   ├── List Work Items
│   ├── Get Work Item
│   └── ...
```

## Security Best Practices

**IMPORTANT**: Before using the API in production, read the comprehensive security guide:

**📖 [SECURITY.md](SECURITY.md)** - Complete security best practices including:

- **Token Management**: Secure storage, rotation strategies, and lifecycle management
- **Secret Storage**: Environment variables, AWS Secrets Manager, HashiCorp Vault, Azure Key Vault
- **Production Deployment**: Kubernetes secrets, Docker secrets, monitoring, and incident response
- **Network Security**: SSL/TLS verification, rate limiting, timeout configuration
- **Environment Configuration**: Development vs staging vs production setup

### Quick Security Checklist

- ✅ Never commit API tokens to version control
- ✅ Use environment variables or secret management services
- ✅ Enable SSL/TLS verification in production
- ✅ Implement token rotation (recommended: 90-day cycle)
- ✅ Use least-privilege token scopes
- ✅ Configure appropriate request timeouts
- ✅ Implement rate limiting and retry logic
- ✅ Never log tokens or sensitive data
- ✅ Revoke compromised tokens immediately

**Example - Secure Token Loading**:

```python
# ✅ GOOD: Load from environment
import os
from codetoreum_client import CodetoreumClient

client = CodetoreumClient(
    api_token=os.getenv("CODETOREUM_API_TOKEN"),
    base_url=os.getenv("CODETOREUM_API_URL", "http://localhost:8000"),
    verify_ssl=True,  # Always True in production
    timeout=30
)
```

```python
# ❌ BAD: Hardcoded token
client = CodetoreumClient(api_token="ct_live_abc123...")  # NEVER DO THIS
```

### Postman Collection Organization

```
Codetoreum API/
├── Agents
│   ├── Create Agent
│   ├── List Agents
│   └── ...
├── Workflows
├── Orchestrator
├── Executions
├── Configuration
├── Metrics
└── Workspaces
```

## Authentication

Codetoreum uses **JWT-based single-token authentication** similar to JupyterLab.

### Getting Your Token

The authentication token is printed to the console when the server starts:

```
[Codetoreum] Access token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Using the Token

#### Method 1: Authorization Header (Recommended)

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v2/work-items/
```

```python
headers = {"Authorization": f"Bearer {API_TOKEN}"}
requests.get(url, headers=headers)
```

#### Method 2: Query Parameter

```bash
curl "http://localhost:8000/api/v2/work-items/?token=YOUR_TOKEN"
```

**Note**: Query parameter auth is primarily for WebSocket connections.

#### Method 3: Cookie

After initial authentication, the token is stored in a cookie and automatically sent with requests.

### Token Information

Check token validity and expiration:

```bash
curl "http://localhost:8000/api/v2/auth/token-info?token=YOUR_TOKEN"
```

Response:
```json
{
  "valid": true,
  "expires_at": "2025-12-31T23:59:59Z",
  "issued_at": "2025-11-05T10:00:00Z"
}
```

### Logout

Clear authentication cookie:

```bash
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v2/auth/logout
```

### Best Practices

1. **Store tokens securely** (environment variables, secret managers)
2. **Never commit tokens** to version control
3. **Use Authorization header** for API clients
4. **Use HTTPS in production** to prevent token interception
5. **Regenerate tokens** if compromised

## Quick Start

### 1. Start the Codetoreum Server

```bash
cd codetoreum
python -m codetoreum.adapters.primary.fastapi_app
```

Note the authentication token printed to the console.

### 2. Set Environment Variables

```bash
export CODETOREUM_BASE_URL="http://localhost:8000"
export CODETOREUM_API_TOKEN="your_token_here"
```

### 3. Test the API

**Using cURL**:
```bash
curl -H "Authorization: Bearer $CODETOREUM_API_TOKEN" \
  "$CODETOREUM_BASE_URL/api/v2/health"
```

**Using Python SDK**:
```python
from codetoreum_client import CodetoreumClient
import os

client = CodetoreumClient(
    base_url=os.getenv("CODETOREUM_BASE_URL"),
    api_token=os.getenv("CODETOREUM_API_TOKEN")
)

print(client.health_check())
```

**Using Postman**:
1. Import [`postman_collection.json`](postman_collection.json)
2. Set `base_url` and `api_token` environment variables
3. Send "Health Check" request

### 4. Create Your First Workflow

```python
# Create an agent
agent = client.agents.create(
    name="my-agent",
    description="My first agent",
    agent_type="claude_code",
    capabilities=["python"]
)

# Create a work item
work_item = client.work_items.create(
    title="My first task",
    description="Test task",
    project_id="test-project"
)

# Start workflow
workflow_run = client.orchestrator.start_workflow(work_item.id)

# Monitor progress
for event in client.events.stream():
    print(f"{event['type']}: {event['data']}")
```

## API Endpoints Overview

### Core Resources

| Resource | Base Path | Description |
|----------|-----------|-------------|
| Work Items | `/api/v2/work-items/` | Issues, tasks, and work items |
| Agents | `/api/v2/agents/` | AI agent management |
| Workflows | `/api/v2/workflows/` | Workflow definitions |
| Orchestrator | `/api/v2/orchestrator/` | Workflow execution control |
| Executions | `/api/v2/executions/` | Agent execution monitoring |
| Configuration | `/api/v2/config/` | Project and agent configuration |
| Metrics | `/api/v2/metrics/` | Performance and health metrics |
| Workspaces | `/api/v2/workspace/` | Container workspace management |

### Special Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/health` | GET | Health check (no auth) |
| `/api/v2/health/ready` | GET | Readiness check (no auth) |
| `/api/v2/auth/token-info` | GET | Get token information |
| `/api/v2/auth/logout` | POST | Logout and clear cookie |
| `/api/v2/events/stream` | WebSocket | Real-time event streaming |
| `/webhooks/github` | POST | GitHub webhook receiver |

### Pagination

List endpoints support pagination:

**Query Parameters**:
- `offset`: Number of items to skip (default: 0)
- `limit`: Maximum items to return (default: 50, max: 100)
- `sort_by`: Field to sort by
- `sort_order`: `asc` or `desc`

**Response Format**:
```json
{
  "items": [...],
  "total": 150,
  "offset": 0,
  "limit": 50
}
```

### Filtering

Most list endpoints support filtering:

**Work Items**:
```
GET /api/v2/work-items/?status=pending&labels=feature&priority=high
```

**Executions**:
```
GET /api/v2/executions/?status=running&agent_id=agent_abc
```

**Agents**:
```
GET /api/v2/agents/?active=true&capability=python
```

## Rate Limiting

Default: **100 requests per minute** per IP address

**Headers**:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1699200000
```

**429 Error Response**:
```json
{
  "detail": "Rate limit exceeded. Try again in 60 seconds.",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "timestamp": "2025-11-05T12:00:00Z"
}
```

## Error Handling

All API errors follow a consistent format:

```json
{
  "detail": "Error message",
  "error_code": "ERROR_CODE",
  "timestamp": "2025-11-05T12:00:00Z"
}
```

**Common Status Codes**:
- `400`: Bad Request - Invalid input
- `401`: Unauthorized - Missing or invalid token
- `403`: Forbidden - Insufficient permissions
- `404`: Not Found - Resource doesn't exist
- `422`: Unprocessable Entity - Validation error
- `429`: Too Many Requests - Rate limit exceeded
- `500`: Internal Server Error

## WebSocket Events

Real-time event streaming via WebSocket:

**Endpoint**: `ws://localhost:8000/api/v2/events/stream?token=YOUR_TOKEN`

**Event Types**:
- `workflow.started`
- `workflow.completed`
- `workflow.failed`
- `execution.started`
- `execution.progress`
- `execution.completed`
- `execution.failed`
- `work_item.updated`

**Example Event**:
```json
{
  "type": "execution.started",
  "timestamp": "2025-11-05T12:00:00Z",
  "data": {
    "execution_id": "exec_abc123",
    "agent_id": "agent_xyz789",
    "work_item_id": "wi_def456",
    "stage_name": "development"
  }
}
```

For WebSocket event streaming implementation details, refer to the API endpoint specification above.

## Contributing

Contributions are welcome! Please see the main project README for contribution guidelines.

### Adding Examples

1. Create example files in the appropriate language directory
2. Follow existing code style and structure
3. Include comprehensive comments and documentation
4. Test examples before submitting

### Improving Documentation

1. Update relevant README files
2. Enhance OpenAPI spec with better examples
3. Add missing endpoint documentation
4. Improve error response examples

## Support

- **Documentation**: https://docs.codetoreum.com
- **Issues**: https://github.com/codetoreum/codetoreum/issues
- **Discussions**: https://github.com/codetoreum/codetoreum/discussions

## License

MIT License - see LICENSE file for details
