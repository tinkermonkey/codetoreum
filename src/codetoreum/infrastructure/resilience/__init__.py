"""Infrastructure resilience layer.

Provides centralized resilience patterns for all external system integrations:
- Rate limiting (TokenBucketRateLimiter, MockRateLimiter)
- Circuit breaking (CircuitBreaker, MockCircuitBreaker)
- Retry policies (ExponentialBackoffRetry, MockRetryPolicy)
- Timeouts (AsyncTimeout, MockTimeout)
- Resilient decorators (ResilientTicketSystemDecorator)
- Factory for creating resilient adapters (ResilienceFactory)
"""

from .circuit_breaker import CircuitBreaker
from .config import (
    CLAUDE_RESILIENCE_CONFIG,
    CONTAINER_RESILIENCE_CONFIG,
    GITHUB_RESILIENCE_CONFIG,
    REPOSITORY_RESILIENCE_CONFIG,
    CircuitBreakerConfig,
    OperationMode,
    RateLimitConfig,
    RetryConfig,
    ServiceResilienceConfig,
    TimeoutConfig,
)
from .decorators import (
    ResilientBoardServiceDecorator,
    ResilientTicketSystemDecorator,
)
from .exceptions import (
    CircuitBreakerOpenError,
    MaxRetriesExceededError,
    RateLimitExceededError,
    ResilienceError,
    TimeoutError,
)
from .factory import ResilienceFactory
from .interfaces import (
    CircuitBreakerStats,
    CircuitState,
    ICircuitBreaker,
    IRateLimiter,
    IRetryPolicy,
    ITimeout,
    RateLimitStats,
    RetryStats,
    TimeoutStats,
)
from .mocks import MockCircuitBreaker, MockRateLimiter, MockRetryPolicy, MockTimeout
from .rate_limiter import TokenBucketRateLimiter
from .retry_policy import ExponentialBackoffRetry
from .timeout import AsyncTimeout

__all__ = [
    # Exceptions
    "ResilienceError",
    "RateLimitExceededError",
    "CircuitBreakerOpenError",
    "MaxRetriesExceededError",
    "TimeoutError",
    # Interfaces
    "IRateLimiter",
    "ICircuitBreaker",
    "IRetryPolicy",
    "ITimeout",
    "CircuitState",
    "RateLimitStats",
    "CircuitBreakerStats",
    "RetryStats",
    "TimeoutStats",
    # Production Implementations
    "TokenBucketRateLimiter",
    "CircuitBreaker",
    "ExponentialBackoffRetry",
    "AsyncTimeout",
    # Mock Implementations
    "MockRateLimiter",
    "MockCircuitBreaker",
    "MockRetryPolicy",
    "MockTimeout",
    # Decorators
    "ResilientTicketSystemDecorator",
    "ResilientBoardServiceDecorator",
    # Factory
    "ResilienceFactory",
    # Configuration
    "OperationMode",
    "RateLimitConfig",
    "CircuitBreakerConfig",
    "RetryConfig",
    "TimeoutConfig",
    "ServiceResilienceConfig",
    "GITHUB_RESILIENCE_CONFIG",
    "CLAUDE_RESILIENCE_CONFIG",
    "CONTAINER_RESILIENCE_CONFIG",
    "REPOSITORY_RESILIENCE_CONFIG",
]
