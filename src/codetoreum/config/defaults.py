"""
Default Configuration Values

All default values for Codetoreum configuration.
Centralizing these values eliminates magic numbers and makes the codebase more maintainable.

Usage: from codetoreum.config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
"""

# =============================================================================
# API Pagination
# =============================================================================

# Standard pagination defaults (used by most endpoints)
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_OFFSET = 0

# Endpoint-specific pagination (when different from standard)
SCHEDULER_DEFAULT_PAGE_SIZE = 50  # Scheduler endpoints handle more items
SCHEDULER_MAX_PAGE_SIZE = 100  # Scheduler max page size
EVENTS_DEFAULT_PAGE_SIZE = 50  # Event endpoints handle more items
EVENTS_MAX_PAGE_SIZE = 1000  # Event endpoints can return more historical data
AUDIT_EVENTS_MAX_PAGE_SIZE = 200  # Audit events limited to 200 for performance (see Risk Considerations)
WORKSPACE_DEFAULT_PAGE_SIZE = 50  # Workspace endpoints handle more items
WORKSPACE_MAX_PAGE_SIZE = 100

# Version history limits
VERSIONS_DEFAULT_LIMIT = 10
VERSIONS_MAX_LIMIT = 50

# =============================================================================
# Authentication
# =============================================================================

# Token expiration
DEFAULT_TOKEN_EXPIRY_DAYS = 365
MIN_TOKEN_LENGTH = 32

# Cookie settings
DEFAULT_COOKIE_MAX_AGE_SECONDS = 86400 * 365  # 1 year

# User credentials
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 50
MIN_PASSWORD_LENGTH = 8

# API keys
MIN_API_KEY_NAME_LENGTH = 1
MAX_API_KEY_NAME_LENGTH = 100

# =============================================================================
# Rate Limiting
# =============================================================================

# API rate limiting
DEFAULT_RATE_LIMIT = "100/minute"
DEFAULT_RATE_LIMIT_BY_IP = True

# External service rate limits
GITHUB_RATE_LIMIT_THRESHOLD = 10  # Remaining requests before waiting
MOCK_LLM_RATE_LIMIT_THRESHOLD = 100  # Mock LLM simulator threshold
ELASTICSEARCH_RATE_LIMIT_RPS = 100  # Requests per second

# =============================================================================
# WebSocket
# =============================================================================

DEFAULT_WS_HEARTBEAT_INTERVAL = 30  # seconds
DEFAULT_WS_HEARTBEAT_TIMEOUT = 90  # seconds
DEFAULT_WS_MAX_CONNECTIONS = 1000
DEFAULT_WS_MESSAGE_QUEUE_SIZE = 1000  # Max buffer size
DEFAULT_WS_RATE_LIMIT_MESSAGES = 100  # Max messages per client per window
DEFAULT_WS_RATE_LIMIT_WINDOW = 60  # Rate limit window in seconds

# =============================================================================
# Execution
# =============================================================================

DEFAULT_EXECUTION_TIMEOUT = 3600  # 1 hour in seconds
DEFAULT_LOG_TAIL_LIMIT = 10000

# =============================================================================
# Workspace
# =============================================================================

DEFAULT_WORKSPACE_RETENTION_DAYS = 7
DEFAULT_BRANCH_TITLE_MAX_LENGTH = 40

# =============================================================================
# Security
# =============================================================================

# Patterns that indicate sensitive configuration keys
SENSITIVE_KEY_PATTERNS = [
    "api_key",
    "token",
    "password",
    "secret",
    "credential",
    "auth",
    "private_key",
]

# =============================================================================
# Environment
# =============================================================================

VALID_ENVIRONMENTS = ["development", "staging", "production"]
DEFAULT_ENVIRONMENT = "development"

# =============================================================================
# Field Length Constraints (DTOs and Validation)
# =============================================================================

# Work items
MAX_WORK_ITEM_ID_LENGTH = 100
MAX_TITLE_LENGTH = 500
MAX_PROJECT_ID_LENGTH = 255

# Workflows
MAX_WORKFLOW_ID_LENGTH = 100
MAX_WORKFLOW_NAME_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000
MAX_STAGE_NAME_LENGTH = 100
MIN_STAGES_COUNT = 1

# Reasons and messages
MAX_REASON_LENGTH = 500
MAX_ERROR_MESSAGE_LENGTH = 500
MAX_VALIDATION_MESSAGE_LENGTH = 500

# Error types and conditions
MAX_ERROR_TYPE_LENGTH = 100
MAX_CONDITION_TYPE_LENGTH = 100

# Generic minimum
MIN_FIELD_LENGTH = 1

# =============================================================================
# Server
# =============================================================================

DEFAULT_API_PORT = 8000

# =============================================================================
# Redis
# =============================================================================

DEFAULT_REDIS_STREAM_MAX_LENGTH = 100000

# =============================================================================
# Metrics
# =============================================================================

DEFAULT_METRICS_AGGREGATION_WINDOW_SECONDS = 60
MIN_METRICS_AGGREGATION_WINDOW_SECONDS = 1
MAX_METRICS_AGGREGATION_WINDOW_SECONDS = 3600
