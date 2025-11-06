# Configuration Constants Migration - Summary

## Overview
This document summarizes the changes made to eliminate magic numbers and hardcoded configuration values throughout the Codetoreum codebase. All default values are now centralized in `src/codetoreum/config/defaults.py`.

## New Files Created

### 1. `src/codetoreum/config/defaults.py`
Central configuration file containing all default values organized by category:
- **API Pagination**: Default page sizes, limits, and offsets
- **Authentication**: Token expiry, cookie settings, credential constraints
- **Rate Limiting**: API and external service rate limits
- **WebSocket**: Connection settings, heartbeat intervals, rate limits
- **Execution**: Timeouts and log limits
- **Workspace**: Retention and branch naming limits
- **Security**: Sensitive key patterns
- **Environment**: Valid environments
- **Field Length Constraints**: Maximum lengths for DTOs
- **Server**: Default ports
- **Redis**: Stream configuration
- **Metrics**: Aggregation windows

### 2. `src/codetoreum/config/__init__.py`
Exports all constants from `defaults.py` for easy importing throughout the codebase.

## Files Modified

### Router Files
All router files updated to use configuration constants instead of magic numbers:

1. **`adapters/primary/routers/workflows.py`**
   - Replaced `Query(0, ...)` → `Query(DEFAULT_OFFSET, ...)`
   - Replaced `Query(20, ge=1, le=100)` → `Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)`
   - Replaced `Query(10, ...)` → `Query(VERSIONS_DEFAULT_LIMIT, ...)`

2. **`adapters/primary/routers/scheduler.py`**
   - Replaced `Query(50, ge=1, le=100)` → `Query(SCHEDULER_DEFAULT_PAGE_SIZE, ge=1, le=SCHEDULER_MAX_PAGE_SIZE)`

3. **`adapters/primary/routers/config/search.py`**
   - Replaced `Query(20, ge=1, le=100)` → `Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)`

4. **`adapters/primary/routers/work_items.py`**
   - Updated pagination query parameters to use constants

5. **`adapters/primary/routers/events.py`**
   - Replaced `Query(50, ge=1, le=1000)` → `Query(EVENTS_DEFAULT_PAGE_SIZE, ge=1, le=EVENTS_MAX_PAGE_SIZE)`

6. **`adapters/primary/routers/workspace.py`**
   - Updated to use `WORKSPACE_DEFAULT_PAGE_SIZE` and `WORKSPACE_MAX_PAGE_SIZE`

7. **`adapters/primary/routers/agents/list.py`**
   - Updated pagination parameters

8. **`adapters/primary/routers/executions/list.py`**
   - Updated pagination parameters

9. **`adapters/primary/routers/executions.py`**
   - Updated pagination parameters

10. **`adapters/primary/routers/config.py`**
    - Updated pagination and version limits

11. **`adapters/primary/routers/config/pipelines.py`**
    - Updated pagination parameters

12. **`adapters/primary/routers/config/projects.py`**
    - Updated pagination and version limits

13. **`adapters/primary/routers/config/agents.py`**
    - Updated pagination parameters

14. **`adapters/primary/routers/metrics.py`**
    - Replaced `Query(60, ge=1, le=3600)` → `Query(DEFAULT_METRICS_AGGREGATION_WINDOW_SECONDS, ...)`

15. **`adapters/primary/rest_api_adapter.py`**
    - Updated pagination parameters to use scheduler and workspace constants

### Authentication Files

16. **`infrastructure/auth/simple_token_auth.py`**
    - Replaced `"365"` → `str(DEFAULT_TOKEN_EXPIRY_DAYS)`
    - Replaced `86400 * 365` → `DEFAULT_COOKIE_MAX_AGE_SECONDS`
    - Updated print statement to use dynamic token expiry days

### WebSocket Files

17. **`adapters/primary/websocket_adapter.py`**
    - Replaced all hardcoded WebSocket configuration values:
      - `1000` → `DEFAULT_WS_MESSAGE_QUEUE_SIZE`
      - `30` → `DEFAULT_WS_HEARTBEAT_INTERVAL`
      - `90` → `DEFAULT_WS_HEARTBEAT_TIMEOUT`
      - `100` → `DEFAULT_WS_RATE_LIMIT_MESSAGES`
      - `60` → `DEFAULT_WS_RATE_LIMIT_WINDOW`
      - `1000` → `DEFAULT_WS_MAX_CONNECTIONS`

### DTO Files

18. **`adapters/primary/orchestration_dtos.py`**
    - Updated field length constraints to use constants:
      - `min_length=1, max_length=100` → `min_length=MIN_FIELD_LENGTH, max_length=MAX_WORK_ITEM_ID_LENGTH`
      - `min_length=1, max_length=500` → `min_length=MIN_FIELD_LENGTH, max_length=MAX_REASON_LENGTH`

19. **`adapters/primary/workflow_dtos.py`**
    - Updated all field length constraints to use constants
    - Replaced hardcoded values for workflow names, descriptions, stages, errors

20. **`adapters/primary/work_item_dtos.py`**
    - Updated field length constraints for project IDs and titles

21. **`adapters/primary/auth_api_adapter.py`**
    - Replaced username/password/API key constraints with constants:
      - `min_length=3, max_length=50` → `min_length=MIN_USERNAME_LENGTH, max_length=MAX_USERNAME_LENGTH`
      - `min_length=8` → `min_length=MIN_PASSWORD_LENGTH`

### Application Files

22. **`adapters/primary/fastapi_app.py`**
    - Replaced `"8000"` → `str(DEFAULT_API_PORT)`
    - Replaced `"100/minute"` → `DEFAULT_RATE_LIMIT`

23. **`adapters/primary/factories/lifespan.py`**
    - Replaced `"8000"` → `str(DEFAULT_API_PORT)`

### Infrastructure Files

24. **`infrastructure/redis_event_buffer.py`**
    - Replaced `100000` → `DEFAULT_REDIS_STREAM_MAX_LENGTH`

## Configuration Constants Defined

### API Pagination
- `DEFAULT_PAGE_SIZE = 20`
- `MAX_PAGE_SIZE = 100`
- `DEFAULT_OFFSET = 0`
- `SCHEDULER_DEFAULT_PAGE_SIZE = 50`
- `SCHEDULER_MAX_PAGE_SIZE = 100`
- `EVENTS_DEFAULT_PAGE_SIZE = 50`
- `EVENTS_MAX_PAGE_SIZE = 1000`
- `WORKSPACE_DEFAULT_PAGE_SIZE = 50`
- `WORKSPACE_MAX_PAGE_SIZE = 100`
- `VERSIONS_DEFAULT_LIMIT = 10`
- `VERSIONS_MAX_LIMIT = 50`

### Authentication
- `DEFAULT_TOKEN_EXPIRY_DAYS = 365`
- `MIN_TOKEN_LENGTH = 32`
- `DEFAULT_COOKIE_MAX_AGE_SECONDS = 86400 * 365  # 1 year`
- `MIN_USERNAME_LENGTH = 3`
- `MAX_USERNAME_LENGTH = 50`
- `MIN_PASSWORD_LENGTH = 8`
- `MIN_API_KEY_NAME_LENGTH = 1`
- `MAX_API_KEY_NAME_LENGTH = 100`

### Rate Limiting
- `DEFAULT_RATE_LIMIT = "100/minute"`
- `DEFAULT_RATE_LIMIT_BY_IP = True`
- `GITHUB_RATE_LIMIT_THRESHOLD = 10`
- `MOCK_LLM_RATE_LIMIT_THRESHOLD = 100`
- `ELASTICSEARCH_RATE_LIMIT_RPS = 100`

### WebSocket
- `DEFAULT_WS_HEARTBEAT_INTERVAL = 30  # seconds`
- `DEFAULT_WS_HEARTBEAT_TIMEOUT = 90  # seconds`
- `DEFAULT_WS_MAX_CONNECTIONS = 1000`
- `DEFAULT_WS_MESSAGE_QUEUE_SIZE = 1000`
- `DEFAULT_WS_RATE_LIMIT_MESSAGES = 100`
- `DEFAULT_WS_RATE_LIMIT_WINDOW = 60  # seconds`

### Field Length Constraints (DTOs)
- `MAX_WORK_ITEM_ID_LENGTH = 100`
- `MAX_WORKFLOW_ID_LENGTH = 100`
- `MAX_STAGE_NAME_LENGTH = 100`
- `MAX_REASON_LENGTH = 500`
- `MAX_TITLE_LENGTH = 500`
- `MAX_DESCRIPTION_LENGTH = 2000`
- `MAX_PROJECT_ID_LENGTH = 255`
- `MAX_WORKFLOW_NAME_LENGTH = 200`
- `MAX_ERROR_TYPE_LENGTH = 100`
- `MAX_ERROR_MESSAGE_LENGTH = 500`
- `MAX_CONDITION_TYPE_LENGTH = 100`
- `MAX_VALIDATION_MESSAGE_LENGTH = 500`
- `MIN_STAGES_COUNT = 1`
- `MIN_FIELD_LENGTH = 1`

### Other
- `DEFAULT_API_PORT = 8000`
- `DEFAULT_REDIS_STREAM_MAX_LENGTH = 100000`
- `DEFAULT_METRICS_AGGREGATION_WINDOW_SECONDS = 60`
- `MIN_METRICS_AGGREGATION_WINDOW_SECONDS = 1`
- `MAX_METRICS_AGGREGATION_WINDOW_SECONDS = 3600`

## Benefits

1. **Maintainability**: All configuration defaults are now in one place
2. **Consistency**: Same values used throughout the codebase
3. **Documentation**: Constants are clearly named and documented
4. **Testability**: Easy to override constants for testing
5. **Discoverability**: Developers can easily find what configuration options are available

## Environment Variable Compatibility

All environment variable usage remains unchanged. The constants serve as default values when environment variables are not set:
- `CODETOREUM_TOKEN_EXPIRATION_DAYS` defaults to `DEFAULT_TOKEN_EXPIRY_DAYS`
- `API_PORT` defaults to `DEFAULT_API_PORT`
- `CODETOREUM_RATE_LIMIT` defaults to `DEFAULT_RATE_LIMIT`
- WebSocket environment variables default to `DEFAULT_WS_*` constants
- etc.

## Verification

All modified files have been syntax-checked and imports verified:
```bash
python3 -m py_compile [modified files]  # All passed
python3 -c "from src.codetoreum.config import ..."  # All imports successful
```

## Next Steps

1. Run full test suite to ensure no regressions
2. Update documentation to reference the new configuration constants
3. Consider adding configuration validation on startup
4. Update deployment documentation to reference `defaults.py` for configuration options
