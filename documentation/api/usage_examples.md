# API Usage Examples - Agents & Executions

Quick reference guide for testing the new agent and execution REST API endpoints.

## Prerequisites

1. **Start the server**:
```bash
python -m uvicorn codetoreum.adapters.primary.fastapi_app:app --reload
```

2. **Get authentication token** from server startup logs:
```
============================================================
Codetoreum API Server
============================================================

Server URL: http://localhost:8000

Authentication token: a1b2c3d4-e5f6-7890-abcd-1234567890ab

Access URL: http://localhost:8000/?token=a1b2c3d4-e5f6-7890-abcd-1234567890ab
...
============================================================
```

3. **Set token as environment variable**:
```bash
export TOKEN="a1b2c3d4-e5f6-7890-abcd-1234567890ab"
```

---

## Agent Registry Endpoints

### 1. List All Agents

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/agents
```

**Response**:
```json
{
  "agents": [
    {
      "id": "agent-123",
      "name": "software_engineer",
      "display_name": "Software Engineer",
      "agent_type": "developer",
      "model": "claude-sonnet-4-5",
      "capabilities": ["python", "javascript", "testing"],
      "total_executions": 42,
      "successful_executions": 38,
      "created_at": "2025-11-01T10:00:00Z",
      "updated_at": "2025-11-03T15:30:00Z"
    }
  ],
  "total_count": 1,
  "offset": 0,
  "limit": 20,
  "page": 1,
  "has_next": false
}
```

### 2. Filter Agents by Capability

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v2/agents?capability=code_review"
```

### 3. Get Agent Details

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/agents/agent-123
```

**Response**:
```json
{
  "id": "agent-123",
  "name": "software_engineer",
  "display_name": "Software Engineer",
  "agent_type": "developer",
  "role_description": "Writes clean, maintainable code with proper testing",
  "model": "claude-sonnet-4-5",
  "timeout_seconds": 1800,
  "max_retries": 3,
  "requires_docker": true,
  "requires_dev_container": false,
  "makes_code_changes": true,
  "filesystem_write_allowed": true,
  "mcp_servers": ["filesystem", "git"],
  "capabilities": {
    "python": 0.95,
    "javascript": 0.85,
    "testing": 0.90,
    "code_review": 0.88
  },
  "created_at": "2025-11-01T10:00:00Z",
  "updated_at": "2025-11-03T15:30:00Z",
  "execution_stats": {
    "total_executions": 42,
    "successful_executions": 38,
    "failed_executions": 3,
    "timeout_executions": 1,
    "average_duration_seconds": 245.5,
    "last_execution_at": "2025-11-03T15:30:00Z"
  }
}
```

### 4. Create New Agent

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test_engineer",
    "display_name": "Test Engineer",
    "agent_type": "tester",
    "role_description": "Writes comprehensive test suites with high coverage",
    "model": "claude-sonnet-4-5",
    "capabilities": {
      "unit_testing": {
        "skill": "unit_testing",
        "proficiency": 0.95,
        "description": "Expert in unit test development"
      },
      "integration_testing": {
        "skill": "integration_testing",
        "proficiency": 0.90
      },
      "test_automation": {
        "skill": "test_automation",
        "proficiency": 0.88
      }
    },
    "timeout_seconds": 600,
    "max_retries": 2,
    "requires_docker": true,
    "makes_code_changes": true,
    "mcp_servers": ["filesystem"]
  }' \
  http://localhost:8000/api/v2/agents
```

### 5. Update Agent Configuration

```bash
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "timeout_seconds": 900,
    "max_retries": 3
  }' \
  http://localhost:8000/api/v2/agents/agent-123
```

### 6. Add Capability to Agent

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "capability": {
      "skill": "rust",
      "proficiency": 0.75,
      "description": "Growing Rust expertise"
    }
  }' \
  http://localhost:8000/api/v2/agents/agent-123/capabilities
```

### 7. Update Capability Proficiency

```bash
curl -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "proficiency": 0.80
  }' \
  http://localhost:8000/api/v2/agents/agent-123/capabilities/rust
```

### 8. Delete Agent

```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/agents/agent-123
```

---

## Execution Monitoring Endpoints

### 1. List All Executions

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions
```

**Response**:
```json
{
  "executions": [
    {
      "id": "exec-123",
      "agent_name": "software_engineer",
      "work_item_id": "wi-456",
      "workflow_id": "wf-789",
      "stage_name": "development",
      "status": "completed",
      "initialized_at": "2025-11-03T10:00:00Z",
      "started_at": "2025-11-03T10:00:05Z",
      "completed_at": "2025-11-03T10:15:30Z",
      "duration_seconds": 925.0,
      "error_type": null
    }
  ],
  "total_count": 1,
  "offset": 0,
  "limit": 20,
  "page": 1,
  "has_next": false
}
```

### 2. Filter Executions by Status

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v2/executions?status=failed"
```

### 3. Filter Executions by Date Range

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v2/executions?start_date=2025-01-01&end_date=2025-01-31"
```

### 4. Get Execution Status (Normal Completion)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-123
```

**Response**:
```json
{
  "id": "exec-123",
  "agent_id": "agent-123",
  "agent_name": "software_engineer",
  "work_item_id": "wi-456",
  "workflow_id": "wf-789",
  "stage_name": "development",
  "status": "completed",
  "container_name": "codetoreum-exec-123",
  "container_id": "abc123def456",
  "output": "Implementation completed successfully. Added 3 new features with tests.",
  "error_message": null,
  "error_detail": null,
  "exit_code": 0,
  "input_tokens": 5420,
  "output_tokens": 2180,
  "duration_seconds": 925.0,
  "initialized_at": "2025-11-03T10:00:00Z",
  "started_at": "2025-11-03T10:00:05Z",
  "completed_at": "2025-11-03T10:15:30Z",
  "elapsed_time_seconds": 925.0,
  "current_stage": "development"
}
```

### 5. Get Execution Status (Container Crash)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-crashed
```

**Response**:
```json
{
  "id": "exec-crashed",
  "agent_id": "agent-123",
  "agent_name": "software_engineer",
  "work_item_id": "wi-456",
  "workflow_id": "wf-789",
  "stage_name": "development",
  "status": "failed",
  "container_name": "codetoreum-exec-crashed",
  "container_id": "xyz789abc123",
  "output": null,
  "error_message": "Container exited unexpectedly",
  "error_detail": {
    "error_type": "CONTAINER_CRASHED",
    "message": "Container crashed with exit code 137 (OOM killed)",
    "container_status": {
      "container_id": "xyz789abc123",
      "container_name": "codetoreum-exec-crashed",
      "last_known_status": "running",
      "exit_code": 137
    },
    "partial_logs_available": true
  },
  "exit_code": 137,
  "input_tokens": 3200,
  "output_tokens": 0,
  "duration_seconds": 180.5,
  "initialized_at": "2025-11-03T11:00:00Z",
  "started_at": "2025-11-03T11:00:05Z",
  "completed_at": "2025-11-03T11:03:05Z"
}
```

### 6. Get Execution Status (Timeout)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-timeout
```

**Response**:
```json
{
  "id": "exec-timeout",
  "status": "timeout",
  "error_message": "Execution exceeded timeout",
  "error_detail": {
    "error_type": "EXECUTION_TIMEOUT",
    "message": "Execution timed out after 300 seconds",
    "partial_logs_available": true
  },
  "duration_seconds": 300.0
}
```

### 7. Get Execution Status (Agent Failure)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-failed
```

**Response**:
```json
{
  "id": "exec-failed",
  "status": "failed",
  "error_message": "Agent logic error",
  "error_detail": {
    "error_type": "AGENT_FAILURE",
    "message": "Test suite failed with 3 failures",
    "partial_logs_available": false
  },
  "exit_code": 1,
  "duration_seconds": 125.5
}
```

### 8. Get Execution Logs

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-123/logs
```

**Response**:
```json
{
  "execution_id": "exec-123",
  "logs": [
    {
      "timestamp": "2025-11-03T10:00:10Z",
      "level": "INFO",
      "message": "Starting code implementation",
      "stage": "development"
    },
    {
      "timestamp": "2025-11-03T10:05:30Z",
      "level": "INFO",
      "message": "Running tests",
      "stage": "development"
    },
    {
      "timestamp": "2025-11-03T10:15:25Z",
      "level": "INFO",
      "message": "All tests passed",
      "stage": "development"
    }
  ],
  "total_lines": 3,
  "stage": null,
  "has_more": false
}
```

### 9. Get Execution Logs (Filtered)

```bash
# Get last 100 lines from test stage
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v2/executions/exec-123/logs?stage=test&tail=100"
```

### 10. Get Execution History

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-123/history
```

**Response**:
```json
{
  "execution_id": "exec-123",
  "events": [
    {
      "event_type": "ExecutionInitialized",
      "occurred_at": "2025-11-03T10:00:00Z",
      "payload": {
        "agent_id": "agent-123",
        "work_item_id": "wi-456",
        "workflow_id": "wf-789",
        "stage_name": "development"
      }
    },
    {
      "event_type": "ExecutionStarted",
      "occurred_at": "2025-11-03T10:00:05Z",
      "payload": {
        "container_name": "codetoreum-exec-123"
      }
    },
    {
      "event_type": "ExecutionCompleted",
      "occurred_at": "2025-11-03T10:15:30Z",
      "payload": {
        "duration_seconds": 925.0,
        "input_tokens": 5420,
        "output_tokens": 2180
      }
    }
  ],
  "total_events": 3
}
```

### 11. Terminate Running Execution

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "User requested cancellation"
  }' \
  http://localhost:8000/api/v2/executions/exec-running/terminate
```

**Response**:
```json
{
  "success": true,
  "execution_id": "exec-running",
  "message": "Execution terminated successfully",
  "new_status": "cancelled"
}
```

### 12. Terminate Already Completed Execution (409 Conflict)

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-123/terminate
```

**Response** (409):
```json
{
  "detail": "Cannot terminate execution: Execution already completed"
}
```

---

## Error Responses

### 401 Unauthorized (Missing Token)

```bash
curl http://localhost:8000/api/v2/agents
```

**Response**:
```json
{
  "detail": "Missing authorization header"
}
```

### 404 Not Found

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/agents/nonexistent-id
```

**Response**:
```json
{
  "detail": "Agent not found: Agent with ID 'nonexistent-id' does not exist"
}
```

### 400 Bad Request (Validation Error)

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Invalid Name With Spaces",
    "display_name": "Test Agent"
  }' \
  http://localhost:8000/api/v2/agents
```

**Response**:
```json
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "string does not match regex \"^[a-z0-9_]+$\"",
      "type": "value_error.str.regex"
    }
  ]
}
```

---

## OpenAPI Documentation

### Swagger UI
Open in browser: `http://localhost:8000/api/docs`

Interactive API documentation with:
- Try-it-out functionality
- Request/response schemas
- Example values
- Authentication support

### ReDoc
Open in browser: `http://localhost:8000/api/redoc`

Clean, readable API documentation with:
- Table of contents
- Detailed descriptions
- Code examples
- Schema definitions

### OpenAPI Spec
Download JSON: `http://localhost:8000/api/openapi.json`

Use with tools like:
- Postman (import OpenAPI spec)
- Insomnia (import OpenAPI spec)
- Code generators (openapi-generator, swagger-codegen)

---

## Testing with Postman

1. **Import OpenAPI Spec**:
   - Open Postman
   - File → Import → Link
   - Enter: `http://localhost:8000/api/openapi.json`

2. **Set up Authentication**:
   - Create environment variable `TOKEN` with your auth token
   - Postman will automatically use `Bearer {{TOKEN}}` for all requests

3. **Run Collection**:
   - All endpoints available in organized folders
   - Pre-configured headers and authentication
   - Example request bodies included

---

## Common Workflows

### 1. Create and Configure Agent

```bash
# Create agent
AGENT_ID=$(curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "reviewer", "display_name": "Code Reviewer", ...}' \
  http://localhost:8000/api/v2/agents | jq -r '.id')

# Add capability
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"capability": {"skill": "security_review", "proficiency": 0.90}}' \
  http://localhost:8000/api/v2/agents/$AGENT_ID/capabilities

# Verify
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/agents/$AGENT_ID
```

### 2. Monitor Execution Lifecycle

```bash
# Get execution status
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-123

# Stream logs
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v2/executions/exec-123/logs?tail=50"

# Check history
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-123/history
```

### 3. Troubleshoot Failed Execution

```bash
# Get execution details with error type
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-failed

# Get full logs
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-failed/logs

# Get event timeline
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v2/executions/exec-failed/history
```

---

## Tips

- **Use `jq`** for JSON formatting: `curl ... | jq`
- **Save token** to avoid repeated typing: `export TOKEN="..."`
- **Use `-v`** flag for verbose output including headers
- **Use Postman** for interactive testing with saved requests
- **Check OpenAPI docs** for complete request/response schemas
