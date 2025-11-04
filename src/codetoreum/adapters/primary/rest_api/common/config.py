"""
Configuration constants for REST API.
"""

# Pagination
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20

# Timeouts (in seconds)
DEFAULT_TIMEOUT = 300  # 5 minutes
LONG_RUNNING_TIMEOUT = 3600  # 1 hour

# Rate limiting
DEFAULT_RATE_LIMIT = 100  # requests per minute
