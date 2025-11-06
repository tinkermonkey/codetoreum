# Exception Handling Guide

## Overview

This guide documents the exception handling patterns implemented in Codetoreum, providing type-safe error handling from domain layer through HTTP responses.

## Architecture

### Exception Hierarchy

```
Exception (Python built-in)
│
├── DomainError (codetoreum.domain.exceptions)
│   ├── AgentNotFoundError
│   ├── WorkspaceNotFoundError
│   ├── ConfigNotFoundError
│   ├── ExecutionNotFoundError
│   ├── PipelineNotFoundError
│   ├── WorkItemNotFoundError
│   └── InvalidStateError
│
├── PortError (codetoreum.ports.exceptions)
│   ├── ResourceNotFoundError
│   ├── ValidationError
│   ├── AuthenticationError
│   ├── ConcurrencyConflictError
│   ├── RateLimitError
│   ├── TimeoutError
│   └── ExternalServiceError
│
└── PortException (codetoreum.ports.input.exceptions)
    ├── ProjectNotFoundError
    ├── WorkflowNotFoundError
    ├── AgentNotFoundError
    ├── ValidationError
    ├── PermissionError
    ├── WorkflowNotActiveError
    └── WorkflowNotPausedError
```

## Exception Mapper

The `exception_mapper` module (`src/codetoreum/adapters/primary/exception_mapper.py`) provides centralized mapping from domain/port exceptions to HTTP status codes.

### Key Functions

#### `map_exception_to_http(exc: Exception, default_detail: Optional[str] = None) -> HTTPException`

Maps domain, port, and input port exceptions to HTTP exceptions with appropriate status codes.

**Parameters:**
- `exc`: The exception to map
- `default_detail`: Optional default detail message if exception message is empty

**Returns:**
- `HTTPException` with appropriate status code and detail message

### HTTP Status Code Mapping

| Exception Type | HTTP Status Code | Notes |
|---------------|------------------|-------|
| `*NotFoundError` | 404 NOT FOUND | All "not found" exceptions from any layer |
| `ValidationError` | 400 BAD REQUEST | Validation failures |
| `InvalidStateError` | 400 BAD REQUEST | Invalid state transitions |
| `WorkflowNotActiveError` | 409 CONFLICT | State transition conflicts |
| `WorkflowNotPausedError` | 409 CONFLICT | State transition conflicts |
| `ConcurrencyConflictError` | 409 CONFLICT | Concurrent modification conflicts |
| `PermissionError` | 403 FORBIDDEN | Authorization failures |
| `AuthenticationError` | 401 UNAUTHORIZED | Authentication failures |
| `RateLimitError` | 429 TOO MANY REQUESTS | Rate limiting |
| `TimeoutError` | 504 GATEWAY TIMEOUT | Operation timeouts |
| `ExternalServiceError` | 502 BAD GATEWAY | External service failures |
| Generic `PortError` | 502 BAD GATEWAY | External system issues |
| Generic `PortException` | 500 INTERNAL SERVER ERROR | Command/query execution issues |
| Generic `DomainError` | 500 INTERNAL SERVER ERROR | Unexpected business logic errors |
| Unknown exceptions | 500 INTERNAL SERVER ERROR | Fallback for unexpected errors |

## Usage in Routers

### Pattern 1: Exception Mapping in Route Handlers

```python
from fastapi import APIRouter, HTTPException, status
from codetoreum.adapters.primary.exception_mapper import map_exception_to_http
from codetoreum.domain.exceptions import DomainError
from codetoreum.ports.exceptions import PortError
from codetoreum.ports.input.exceptions import PortException

@router.get("/{item_id}")
async def get_item(item_id: str):
    try:
        return await query_port.get_item(item_id)
    except (DomainError, PortError, PortException) as e:
        # Map domain/port exceptions to HTTP exceptions
        raise map_exception_to_http(e)
    except Exception as e:
        # Fallback for unexpected exceptions
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve item: {str(e)}",
        )
```

### Pattern 2: Optional Decorator (Future Enhancement)

```python
from codetoreum.adapters.primary.exception_mapper import with_exception_mapping

@router.get("/{item_id}")
@with_exception_mapping
async def get_item(item_id: str):
    return await query_port.get_item(item_id)
```

## Anti-Patterns to Avoid

### ❌ String Matching (OLD APPROACH)

**DO NOT DO THIS:**

```python
try:
    result = await query_port.get_item(item_id)
except Exception as e:
    if "not found" in str(e).lower():
        raise HTTPException(status_code=404, detail=str(e))
    elif "conflict" in str(e).lower():
        raise HTTPException(status_code=409, detail=str(e))
    else:
        raise HTTPException(status_code=500, detail=str(e))
```

**Problems:**
- Fragile: Breaks if error messages change
- Not type-safe: No compile-time checking
- Hard to maintain: Scattered logic across routers
- Language-dependent: Won't work with internationalization

### ✅ Type-Safe Exception Handling (NEW APPROACH)

**DO THIS INSTEAD:**

```python
try:
    result = await query_port.get_item(item_id)
except (DomainError, PortError, PortException) as e:
    raise map_exception_to_http(e)
except Exception as e:
    # Only for truly unexpected exceptions
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to retrieve item: {str(e)}",
    )
```

**Benefits:**
- Type-safe: Compiler catches missing exception types
- Maintainable: Centralized mapping logic
- Testable: Easy to test all exception mappings
- Consistent: Same behavior across all endpoints

## Best Practices

### 1. Use Specific Exception Types

Always raise specific exception types from domain/port layers:

```python
# ✅ Good
raise WorkspaceNotFoundError(workspace_id)

# ❌ Bad
raise Exception(f"Workspace {workspace_id} not found")
```

### 2. Let Exceptions Bubble Up

Don't catch and re-raise with generic exceptions:

```python
# ✅ Good
async def get_workspace(workspace_id: str):
    workspace = await repository.get(workspace_id)
    if not workspace:
        raise WorkspaceNotFoundError(workspace_id)
    return workspace

# ❌ Bad
async def get_workspace(workspace_id: str):
    try:
        workspace = await repository.get(workspace_id)
        if not workspace:
            raise WorkspaceNotFoundError(workspace_id)
        return workspace
    except WorkspaceNotFoundError:
        raise Exception(f"Workspace {workspace_id} not found")
```

### 3. Provide Meaningful Error Messages

Include identifiers in error messages for debugging:

```python
# ✅ Good
raise WorkspaceNotFoundError(f"ws-{workspace_id}")

# ❌ Bad
raise WorkspaceNotFoundError("Workspace not found")
```

### 4. Use Default Detail Messages

When exception messages might be empty, provide a default:

```python
http_exc = map_exception_to_http(exc, default_detail="Resource not available")
```

## Testing

### Unit Tests

Test exception mapping in `tests/unit/adapters/primary/test_exception_mapper.py`:

```python
def test_workspace_not_found_maps_to_404():
    exc = WorkspaceNotFoundError("ws-123")
    http_exc = map_exception_to_http(exc)

    assert http_exc.status_code == status.HTTP_404_NOT_FOUND
    assert "ws-123" in http_exc.detail
```

### Integration Tests

Test exception handling in router integration tests:

```python
async def test_get_workspace_not_found(client):
    response = await client.get("/api/v2/workspace/ws-nonexistent")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
```

## Migration Guide

### From Old Pattern to New Pattern

**Before (String Matching):**

```python
try:
    workspace = await query_port.get_workspace(workspace_id)
    return WorkspaceResponse(...)
except Exception as e:
    if "not found" in str(e).lower():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to retrieve workspace: {str(e)}",
    )
```

**After (Type-Safe):**

```python
from codetoreum.adapters.primary.exception_mapper import map_exception_to_http
from codetoreum.domain.exceptions import DomainError
from codetoreum.ports.exceptions import PortError
from codetoreum.ports.input.exceptions import PortException

try:
    workspace = await query_port.get_workspace(workspace_id)
    return WorkspaceResponse(...)
except (DomainError, PortError, PortException) as e:
    raise map_exception_to_http(e)
except Exception as e:
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to retrieve workspace: {str(e)}",
    )
```

**Steps:**
1. Import `map_exception_to_http` and exception base classes
2. Replace string matching with specific exception catching
3. Call `map_exception_to_http(e)` for domain/port exceptions
4. Keep generic `Exception` handler for truly unexpected errors

## Error Response Format

All HTTP exceptions follow the same response format (defined in `error_middleware.py`):

```json
{
  "error": "NOT_FOUND",
  "message": "Workspace ws-123 not found",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "path": "/api/v2/workspace/ws-123",
  "details": []
}
```

## Security Considerations

1. **Never expose stack traces** in API responses (handled by error_middleware)
2. **Mask sensitive data** in error messages
3. **Use correlation IDs** for tracking without exposing internal details
4. **Generic messages in production** for unexpected errors

## Related Files

- `src/codetoreum/adapters/primary/exception_mapper.py` - Exception mapping logic
- `src/codetoreum/adapters/primary/error_middleware.py` - Global error handling middleware
- `src/codetoreum/domain/exceptions.py` - Domain layer exceptions
- `src/codetoreum/ports/exceptions.py` - Port layer exceptions
- `src/codetoreum/ports/input/exceptions.py` - Input port exceptions
- `tests/unit/adapters/primary/test_exception_mapper.py` - Exception mapper tests

## Summary

The exception handling system in Codetoreum follows these principles:

1. **Type-safe**: Use specific exception types, not string matching
2. **Centralized**: All HTTP mapping logic in one place
3. **Layered**: Different exceptions for domain, port, and input port layers
4. **Consistent**: Same patterns across all routers
5. **Testable**: Easy to test and maintain

This approach eliminates the fragility of string matching while providing clear, maintainable error handling throughout the application.
