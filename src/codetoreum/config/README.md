# Codetoreum Configuration Constants

This module contains all default configuration values for the Codetoreum application.

## Quick Start

```python
from codetoreum.config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, DEFAULT_TOKEN_EXPIRY_DAYS

# Use in FastAPI Query parameters
limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)

# Use in environment variable defaults
token_expiry = int(os.getenv("TOKEN_EXPIRY_DAYS", str(DEFAULT_TOKEN_EXPIRY_DAYS)))

# Use in Pydantic field constraints
title: str = Field(..., max_length=MAX_TITLE_LENGTH)
```

## Available Constants

### API Pagination
- `DEFAULT_PAGE_SIZE` - Default items per page (20)
- `MAX_PAGE_SIZE` - Maximum items per page (100)
- `DEFAULT_OFFSET` - Default pagination offset (0)
- `SCHEDULER_DEFAULT_PAGE_SIZE` - Scheduler default page size (50)
- `SCHEDULER_MAX_PAGE_SIZE` - Scheduler max page size (100)
- `EVENTS_DEFAULT_PAGE_SIZE` - Events default page size (50)
- `EVENTS_MAX_PAGE_SIZE` - Events max page size (1000)
- `WORKSPACE_DEFAULT_PAGE_SIZE` - Workspace default page size (50)
- `WORKSPACE_MAX_PAGE_SIZE` - Workspace max page size (100)
- `VERSIONS_DEFAULT_LIMIT` - Version history default limit (10)
- `VERSIONS_MAX_LIMIT` - Version history max limit (50)

### Authentication
- `DEFAULT_TOKEN_EXPIRY_DAYS` - Token expiration in days (365)
- `MIN_TOKEN_LENGTH` - Minimum token length (32)
- `DEFAULT_COOKIE_MAX_AGE_SECONDS` - Cookie max age (1 year)
- `MIN_USERNAME_LENGTH` - Minimum username length (3)
- `MAX_USERNAME_LENGTH` - Maximum username length (50)
- `MIN_PASSWORD_LENGTH` - Minimum password length (8)
- `MIN_API_KEY_NAME_LENGTH` - Minimum API key name length (1)
- `MAX_API_KEY_NAME_LENGTH` - Maximum API key name length (100)

### Rate Limiting
- `DEFAULT_RATE_LIMIT` - API rate limit ("100/minute")
- `DEFAULT_RATE_LIMIT_BY_IP` - Rate limit by IP (True)
- `GITHUB_RATE_LIMIT_THRESHOLD` - GitHub API threshold (10)
- `MOCK_LLM_RATE_LIMIT_THRESHOLD` - Mock LLM threshold (100)
- `ELASTICSEARCH_RATE_LIMIT_RPS` - Elasticsearch requests per second (100)

### WebSocket
- `DEFAULT_WS_HEARTBEAT_INTERVAL` - Heartbeat interval in seconds (30)
- `DEFAULT_WS_HEARTBEAT_TIMEOUT` - Heartbeat timeout in seconds (90)
- `DEFAULT_WS_MAX_CONNECTIONS` - Max concurrent connections (1000)
- `DEFAULT_WS_MESSAGE_QUEUE_SIZE` - Max message queue size (1000)
- `DEFAULT_WS_RATE_LIMIT_MESSAGES` - Max messages per client (100)
- `DEFAULT_WS_RATE_LIMIT_WINDOW` - Rate limit window in seconds (60)

### Field Length Constraints
- `MAX_WORK_ITEM_ID_LENGTH` - Max work item ID length (100)
- `MAX_WORKFLOW_ID_LENGTH` - Max workflow ID length (100)
- `MAX_STAGE_NAME_LENGTH` - Max stage name length (100)
- `MAX_REASON_LENGTH` - Max reason text length (500)
- `MAX_TITLE_LENGTH` - Max title length (500)
- `MAX_DESCRIPTION_LENGTH` - Max description length (2000)
- `MAX_PROJECT_ID_LENGTH` - Max project ID length (255)
- `MAX_WORKFLOW_NAME_LENGTH` - Max workflow name length (200)
- `MAX_ERROR_TYPE_LENGTH` - Max error type length (100)
- `MAX_ERROR_MESSAGE_LENGTH` - Max error message length (500)
- `MAX_CONDITION_TYPE_LENGTH` - Max condition type length (100)
- `MAX_VALIDATION_MESSAGE_LENGTH` - Max validation message length (500)
- `MIN_STAGES_COUNT` - Minimum stages in workflow (1)
- `MIN_FIELD_LENGTH` - Minimum generic field length (1)

### Other
- `DEFAULT_API_PORT` - Default API server port (8000)
- `DEFAULT_REDIS_STREAM_MAX_LENGTH` - Redis stream max length (100000)
- `DEFAULT_METRICS_AGGREGATION_WINDOW_SECONDS` - Metrics aggregation window (60)
- `MIN_METRICS_AGGREGATION_WINDOW_SECONDS` - Min metrics window (1)
- `MAX_METRICS_AGGREGATION_WINDOW_SECONDS` - Max metrics window (3600)
- `DEFAULT_EXECUTION_TIMEOUT` - Execution timeout in seconds (3600)
- `DEFAULT_LOG_TAIL_LIMIT` - Log tail limit (10000)
- `DEFAULT_WORKSPACE_RETENTION_DAYS` - Workspace retention in days (7)
- `DEFAULT_BRANCH_TITLE_MAX_LENGTH` - Branch title max length (40)
- `SENSITIVE_KEY_PATTERNS` - List of sensitive key patterns
- `VALID_ENVIRONMENTS` - List of valid environments
- `DEFAULT_ENVIRONMENT` - Default environment ("development")

## Usage Examples

### In Router Files
```python
from codetoreum.config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, DEFAULT_OFFSET

@router.get("/items")
async def list_items(
    offset: int = Query(DEFAULT_OFFSET, ge=0, description="Offset for pagination"),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE,
                      description=f"Limit for pagination (max {MAX_PAGE_SIZE})"),
):
    ...
```

### In DTO Files
```python
from codetoreum.config import MAX_WORKFLOW_NAME_LENGTH, MAX_DESCRIPTION_LENGTH

class CreateWorkflowRequest(BaseModel):
    name: str = Field(..., max_length=MAX_WORKFLOW_NAME_LENGTH)
    description: str = Field(..., max_length=MAX_DESCRIPTION_LENGTH)
```

### In Configuration Classes
```python
from codetoreum.config import DEFAULT_WS_HEARTBEAT_INTERVAL, DEFAULT_WS_MAX_CONNECTIONS

@dataclass
class WebSocketConfig:
    heartbeat_interval: int = DEFAULT_WS_HEARTBEAT_INTERVAL
    max_connections: int = DEFAULT_WS_MAX_CONNECTIONS
```

### With Environment Variables
```python
from codetoreum.config import DEFAULT_TOKEN_EXPIRY_DAYS, DEFAULT_API_PORT

# Use as default when env var not set
token_expiry = int(os.getenv("TOKEN_EXPIRY_DAYS", str(DEFAULT_TOKEN_EXPIRY_DAYS)))
port = int(os.getenv("API_PORT", str(DEFAULT_API_PORT)))
```

## Design Principles

1. **Single Source of Truth**: All default values defined in one place
2. **Clear Naming**: Constants use descriptive, self-documenting names
3. **Categorization**: Constants grouped by functional area
4. **Documentation**: Each constant includes a comment explaining its purpose
5. **Type Safety**: All constants properly typed
6. **Environment Variable Compatible**: Constants serve as defaults for env vars

## Modifying Configuration

To change a default value:
1. Update the constant in `src/codetoreum/config/defaults.py`
2. Ensure the constant is exported in `src/codetoreum/config/__init__.py`
3. Update any documentation that references the old value
4. Run tests to ensure no regressions

## Testing

All constants can be imported and used in tests:

```python
from codetoreum.config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

def test_pagination():
    assert DEFAULT_PAGE_SIZE < MAX_PAGE_SIZE
    assert DEFAULT_PAGE_SIZE > 0
```

## Environment Variables

The following environment variables override these defaults:
- `CODETOREUM_TOKEN_EXPIRATION_DAYS` → `DEFAULT_TOKEN_EXPIRY_DAYS`
- `API_PORT` → `DEFAULT_API_PORT`
- `CODETOREUM_RATE_LIMIT` → `DEFAULT_RATE_LIMIT`
- `WEBSOCKET_MAX_BUFFER_SIZE` → `DEFAULT_WS_MESSAGE_QUEUE_SIZE`
- `WEBSOCKET_HEARTBEAT_INTERVAL` → `DEFAULT_WS_HEARTBEAT_INTERVAL`
- (and many more - see individual files for complete list)

## Migration from Magic Numbers

All magic numbers and hardcoded values have been replaced with constants from this module. For example:

**Before:**
```python
limit: int = Query(20, ge=1, le=100)
```

**After:**
```python
from codetoreum.config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
```

See `CONFIGURATION_CONSTANTS_CHANGES.md` in the project root for a complete migration guide.
