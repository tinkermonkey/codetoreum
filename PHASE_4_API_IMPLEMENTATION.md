# Phase 4 Backend APIs Implementation Summary

## Overview

This document summarizes the implementation of the Phase 4 backend APIs to support the new UX migration from `/legacy_ux` to `/frontend`.

## Implemented Endpoints

### 1. Workflow Runs API

**Base Path:** `/api/v2/workflows/runs`

#### 1.1 List Workflow Runs
- **Endpoint:** `GET /api/v2/workflows/runs`
- **Authentication:** Required
- **Query Parameters:**
  - `status` (optional): Filter by status (comma-separated: running, completed, failed, cancelled)
  - `projectId` (optional): Filter by project ID
  - `workItemId` (optional): Filter by work item ID
  - `workflowId` (optional): Filter by workflow template ID
  - `offset` (optional): Pagination offset (default: 0)
  - `limit` (optional): Pagination limit (default: 20, max: 100)
  - `sortBy` (optional): Sort field (startedAt, completedAt, duration)
  - `sortOrder` (optional): Sort order (asc, desc)

**Response Example:**
```json
{
  "runs": [
    {
      "id": "wfrun-123",
      "workItemId": "wi-456",
      "workflowId": "wf-789",
      "projectId": "proj-1",
      "status": "running",
      "currentStageIndex": 2,
      "currentStageName": "review",
      "startedAt": "2025-11-08T10:00:00Z",
      "completedAt": null,
      "duration": null,
      "issueTitle": "Fix authentication bug",
      "issueNumber": 42,
      "project": "codetoreum",
      "triggeredBy": "github_webhook",
      "priority": "high"
    }
  ],
  "totalCount": 150,
  "offset": 0,
  "limit": 20,
  "hasNext": true
}
```

#### 1.2 Get Workflow Run Details
- **Endpoint:** `GET /api/v2/workflows/runs/:id`
- **Authentication:** Required
- **Path Parameters:**
  - `id`: Workflow run ID

**Response Example:**
```json
{
  "id": "wfrun-123",
  "workItemId": "wi-456",
  "workflowId": "wf-789",
  "projectId": "proj-1",
  "status": "running",
  "stages": [
    {
      "name": "implementation",
      "agentName": "developer_agent",
      "status": "completed",
      "startedAt": "2025-11-08T10:00:00Z",
      "completedAt": "2025-11-08T10:15:00Z",
      "executionId": "exec-111"
    },
    {
      "name": "review",
      "agentName": "reviewer_agent",
      "status": "running",
      "startedAt": "2025-11-08T10:15:00Z",
      "completedAt": null,
      "executionId": "exec-222"
    }
  ],
  "metadata": {}
}
```

#### 1.3 Get Workflow Run Events
- **Endpoint:** `GET /api/v2/workflows/runs/:id/events`
- **Authentication:** Required
- **Path Parameters:**
  - `id`: Workflow run ID
- **Query Parameters:**
  - `offset` (optional): Pagination offset (default: 0)
  - `limit` (optional): Pagination limit (default: 50, max: 200)
  - `eventTypes` (optional): Filter by event types (comma-separated)
  - `since` (optional): ISO timestamp - events after this time

**Response Example:**
```json
{
  "events": [
    {
      "id": "evt-123",
      "eventType": "WorkflowStarted",
      "workflowRunId": "wfrun-123",
      "timestamp": "2025-11-08T10:00:00Z",
      "agentName": null,
      "stageName": "implementation",
      "status": null,
      "data": {
        "workItemId": "wi-456",
        "triggeredBy": "github_webhook"
      }
    }
  ],
  "totalCount": 42,
  "offset": 0,
  "limit": 50,
  "hasNext": false
}
```

### 2. System Metrics API

**Base Path:** `/api/v2/metrics`

#### 2.1 Get Active Agents
- **Endpoint:** `GET /api/v2/metrics/active-agents`
- **Authentication:** Required

**Response Example:**
```json
{
  "agents": [
    {
      "executionId": "exec-123",
      "agentName": "developer_agent",
      "workItemId": "wi-456",
      "project": "codetoreum",
      "issueNumber": 42,
      "status": "running",
      "startedAt": "2025-11-08T10:00:00Z",
      "containerName": "claude-code-exec-123"
    }
  ],
  "count": 1
}
```

#### 2.2 Get API Usage
- **Endpoint:** `GET /api/v2/metrics/api-usage`
- **Authentication:** Required

**Response Example:**
```json
{
  "claude": {
    "available": true,
    "weeklyUsage": 15000000,
    "weeklyQuota": 50000000,
    "weeklyUsagePercent": 30.0,
    "sessionUsage": 2000000,
    "sessionQuota": 10000000,
    "sessionUsagePercent": 20.0,
    "sessionRemainingMinutes": 45
  }
}
```

### 3. Enhanced Health Check

**Note:** The `/api/v2/health` endpoint was mentioned in the requirements for circuit breaker information. This functionality should be added to the existing health check endpoint to include circuit breaker statuses.

## Implementation Details

### New Files Created

1. **Port Interface:**
   - `src/codetoreum/ports/input/workflow_run_query.py`
     - Defines `IWorkflowRunQueryPort` interface
     - Data classes for workflow run queries

2. **DTOs:**
   - `src/codetoreum/adapters/primary/workflow_run_dtos.py`
     - Request and response models for workflow runs API
   - `src/codetoreum/adapters/primary/metrics_dtos.py` (updated)
     - Added `ActiveAgentResponse`, `ActiveAgentsResponse`
     - Added `ApiUsageQuotaResponse`, `ApiUsageResponse`
     - Added circuit breaker and health check DTOs

3. **Mappers:**
   - `src/codetoreum/adapters/primary/workflow_run_mappers.py`
     - Mappers between domain models and DTOs

4. **Routers:**
   - `src/codetoreum/adapters/primary/routers/workflow_runs.py`
     - REST API router for workflow runs

### Updated Files

1. **Metrics Router:**
   - `src/codetoreum/adapters/primary/routers/metrics.py`
     - Added `/active-agents` endpoint
     - Added `/api-usage` endpoint

2. **Metrics Query Port:**
   - `src/codetoreum/ports/input/metrics_query.py`
     - Added `get_active_agents()` method
     - Added `get_api_usage()` method

3. **FastAPI App:**
   - `src/codetoreum/adapters/primary/fastapi_app.py`
     - Added `workflow_run_query_port` parameter
     - Included workflow runs router
     - Added mock implementations for development

## Architecture Compliance

The implementation follows the Hexagonal Architecture pattern:

- **Input Ports:** `IWorkflowRunQueryPort` defines the contract for workflow run queries
- **DTOs:** Clean separation between API contracts and domain models
- **Mappers:** Transform domain objects to DTOs without mixing concerns
- **Routers:** FastAPI routers use ports, not direct repository access
- **Mock Implementations:** Full mock support for development and testing

## Testing Support

The implementation includes:

1. **Mock Port Implementations:** `MockWorkflowRunQueryPort` for development
2. **Mock Metrics Methods:** `get_active_agents()` and `get_api_usage()` in `MockMetricsQueryPort`
3. **Development App:** All new endpoints available in development mode

## WebSocket Support (Deferred)

The WebSocket event subscription for workflow events was mentioned in the requirements but not implemented in this phase. This should be addressed in a follow-up task by:

1. Extending the WebSocket adapter to support workflow-specific event subscriptions
2. Adding filtering logic for workflow run events
3. Testing real-time event delivery for workflow state changes

## Next Steps

To complete the Phase 4 implementation:

1. **Implement Backend Services:**
   - Create application service implementations for `IWorkflowRunQueryPort`
   - Implement `get_active_agents()` in the metrics service
   - Implement `get_api_usage()` in the metrics service

2. **Add Event Store Queries:**
   - Extend event store to query workflow run events efficiently
   - Add indexes for workflow run queries

3. **Add WebSocket Event Subscriptions:**
   - Extend WebSocket adapter for workflow event filtering
   - Test real-time updates

4. **Update Health Endpoint:**
   - Add circuit breaker status to `/api/v2/health`
   - Include rate limit information
   - Add disk and memory checks

5. **Integration Testing:**
   - Test all new endpoints end-to-end
   - Verify pagination works correctly
   - Test filtering and sorting

6. **Documentation:**
   - Update OpenAPI/Swagger documentation
   - Add usage examples
   - Document authentication requirements

## API Design Decisions

1. **Camel Case for JSON:** Used camelCase for JSON keys (e.g., `workItemId`) to match frontend conventions
2. **Pagination:** Standard offset/limit pagination with `hasNext` indicator
3. **Filtering:** Multiple filters combined with AND logic
4. **Status Enum:** String-based status values for easier frontend consumption
5. **Authentication:** All endpoints require authentication except health checks
6. **Error Handling:** Standard HTTP status codes with detailed error messages

## Files Reference

All code changes were made to maintain backward compatibility and follow the existing patterns in the codebase:

- Port interfaces in: `src/codetoreum/ports/input/`
- DTOs in: `src/codetoreum/adapters/primary/`
- Routers in: `src/codetoreum/adapters/primary/routers/`
- Main app integration in: `src/codetoreum/adapters/primary/fastapi_app.py`
