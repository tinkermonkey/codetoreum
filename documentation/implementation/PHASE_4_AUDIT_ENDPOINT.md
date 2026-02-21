# Phase 4: Audit Endpoint Implementation Guide

## Overview
Implementation of audit trail endpoints for workflow run and pipeline run events. Provides paginated access to complete event history with filtering and validation capabilities.

## API Endpoints

### 1. Workflow Run Events
`GET /api/workflow-runs/{workflow_run_id}/events`

Retrieves a paginated list of events for a specific workflow run with optional filtering.

**Parameters**:
- `workflow_run_id` (path, required): Unique identifier for the workflow run
- `limit` (query, optional): Number of events per page (default: 50, max: 200)
- `offset` (query, optional): Number of events to skip for pagination (default: 0)
- `eventTypes` (query, optional): Comma-separated list of event types to filter by
- `since` (query, optional): ISO 8601 timestamp - only return events after this time

**Response**: `WorkflowEventsListResponse`
```json
{
  "workflow_run_id": "wfr_abc123",
  "total": 150,
  "offset": 0,
  "limit": 50,
  "events": [
    {
      "event_id": "evt_123",
      "event_type": "WorkflowStarted",
      "timestamp": "2026-02-21T10:30:00Z",
      "data": { ... }
    }
  ]
}
```

### 2. Workflow Run Audit (Complete View)
`GET /api/workflow-runs/{workflow_run_id}/audit`

Retrieves comprehensive audit information including events, stage transitions, and optional validation.

**Parameters**:
- `workflow_run_id` (path, required): Unique identifier for the workflow run
- `limit` (query, optional): Number of events per page (default: 100, max: 200)
- `offset` (query, optional): Number of events to skip for pagination (default: 0)
- `include_validation` (query, optional): Whether to validate event sequence integrity (default: true)

**Response**: `WorkflowRunAuditResponse`
```json
{
  "workflow_run_id": "wfr_abc123",
  "workflow_id": "wf_build_test_deploy",
  "started_at": "2026-02-21T10:30:00Z",
  "completed_at": "2026-02-21T10:45:00Z",
  "status": "completed",
  "events": {
    "total": 150,
    "offset": 0,
    "limit": 100,
    "items": [ ... ]
  },
  "stages": [
    {
      "stage_name": "build",
      "entered_at": "2026-02-21T10:30:05Z",
      "exited_at": "2026-02-21T10:35:00Z",
      "status": "completed"
    }
  ],
  "validation": {
    "is_valid": true,
    "issues": []
  }
}
```

### 3. Pipeline Run Events
`GET /api/pipeline-runs/{pipeline_run_id}/events`

Retrieves a paginated list of events for a specific pipeline run.

**Parameters**:
- `pipeline_run_id` (path, required): Unique identifier for the pipeline run
- `limit` (query, optional): Number of events per page (default: 100, max: 200)
- `offset` (query, optional): Number of events to skip for pagination (default: 0)

**Response**: Paginated list of pipeline events with metadata

## Pagination

### Design Decisions

**Default Page Sizes**:
- Workflow run events: 50 events (general event listing)
- Workflow run audit: 100 events (comprehensive audit view)
- Pipeline run events: 100 events

**Maximum Page Size**: 200 events per request

**Rationale**: The 200 event maximum was chosen (vs. original 500 specification) based on Risk Considerations analysis to:
- Prevent memory exhaustion when fetching large audit trails
- Ensure responsive API performance under load
- Maintain reasonable HTTP payload sizes
- Balance between usability (fewer requests) and safety (controlled resource usage)

**Pagination Strategy**: Offset-based pagination
- Deterministic ordering by timestamp + event_id
- Predictable page boundaries for debugging
- Simple client-side implementation
- Trade-off: Less efficient for very large offsets (acceptable for audit use case)

### Usage Examples

**Fetch first page**:
```
GET /api/workflow-runs/wfr_abc123/events?limit=50&offset=0
```

**Fetch second page**:
```
GET /api/workflow-runs/wfr_abc123/events?limit=50&offset=50
```

**Filter by event types**:
```
GET /api/workflow-runs/wfr_abc123/events?eventTypes=WorkflowStarted,WorkflowCompleted
```

**Filter by time range**:
```
GET /api/workflow-runs/wfr_abc123/events?since=2026-02-21T10:00:00Z
```

## Implementation Files

### Router
- **File**: `src/codetoreum/adapters/primary/routers/workflow_runs.py`
- **Endpoints**:
  - Line 237: `get_workflow_run_events()`
  - Line 318: `get_workflow_run_audit()`

### Configuration
- **File**: `src/codetoreum/config/defaults.py`
- **Constants**:
  - `AUDIT_EVENTS_MAX_PAGE_SIZE = 200` - Maximum events per audit request

### DTOs
- **File**: `src/codetoreum/adapters/primary/workflow_run_dtos.py`
  - `WorkflowEventsListResponse` - Event list response model
- **File**: `src/codetoreum/adapters/primary/audit_dtos.py`
  - `WorkflowRunAuditResponse` - Complete audit response model

### Query Port
- **File**: `src/codetoreum/ports/input/workflow_run_query.py`
- **Interface**: `IWorkflowRunQueryPort`
  - `get_workflow_run_events()` - Event retrieval with filtering
  - `get_workflow_run_audit()` - Complete audit data

### Implementation
- **File**: `src/codetoreum/application/query_services/workflow_run_query_service.py`
- **Service**: `WorkflowRunQueryService` - Business logic for event retrieval and validation

## Testing

### Test Suite
- **File**: `tests/adapters/primary/routers/test_workflow_runs.py`

### Test Coverage
- ✅ Pagination edge cases (offset=0, offset > total, empty results)
- ✅ Invalid parameter handling (negative offset, limit > max, invalid workflow_run_id)
- ✅ Event filtering by type and timestamp
- ✅ Audit validation (sequence integrity, missing events)
- ✅ Large result sets (200+ events)
- ✅ Concurrent requests (pagination consistency)

### Example Test Cases
```python
async def test_get_workflow_run_events_with_pagination():
    """Test paginated event retrieval"""

async def test_get_workflow_run_events_with_filters():
    """Test event filtering by type and timestamp"""

async def test_get_workflow_run_audit_with_validation():
    """Test audit validation detects sequence issues"""
```

## Error Handling

### HTTP Status Codes
- `200 OK`: Successful retrieval
- `400 Bad Request`: Invalid parameters (negative offset, limit exceeds max)
- `404 Not Found`: Workflow run or pipeline run does not exist
- `422 Unprocessable Entity`: Validation errors in request format

### Error Response Format
```json
{
  "detail": "Workflow run 'wfr_invalid' not found"
}
```

## Performance Considerations

### Database Queries
- Index on `(workflow_run_id, timestamp, event_id)` for efficient pagination
- Limit + 1 query pattern to detect additional pages
- Query optimization for large event tables (10M+ events)

### Caching
- Not implemented in Phase 4 (audit data is immutable after completion)
- Future optimization: Cache completed workflow run audits

### Rate Limiting
- Standard API rate limits apply (100 requests/minute per user)
- No special rate limiting for audit endpoints

## Security

### Authorization
- Requires valid authentication token
- User must have read access to project containing workflow run
- No special permissions required for audit data (read-only)

### Data Exposure
- Event data may contain sensitive information (file paths, commit messages)
- No PII filtering in Phase 4 (assumed internal use)
- Future consideration: Redact sensitive fields for external users

## Future Enhancements

### Phase 5+ Considerations
- **Streaming Events**: WebSocket endpoint for real-time event streaming
- **Event Filtering DSL**: Advanced query language for complex filters
- **Export Formats**: CSV/JSON export for audit reports
- **Event Replay**: Reconstruct workflow state from event stream
- **Aggregated Views**: Event summaries and statistics
- **Cursor-Based Pagination**: More efficient for very large result sets

---

**Version**: Phase 4 Implementation
**Last Updated**: 2026-02-21
**Status**: ✅ Complete
