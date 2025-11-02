"""Infrastructure layer for Codetoreum.

This package contains cross-cutting concerns and infrastructure components:
- Event sourcing infrastructure (serialization, buffering, persistence)
- Event bus for real-time event handling
- Event replayer for debugging and recovery
- Configuration caching with Redis
- Resilience patterns (circuit breakers, rate limiting, retries, timeouts)
- Health checks (liveness, readiness, dependency monitoring)
- Dead letter queue for failed event handling
"""

from codetoreum.infrastructure.event_bus import EventBus, EventHandler, event_handler
from codetoreum.infrastructure.event_replayer import EventReplayer
from codetoreum.infrastructure.event_serialization import (
    EventSerializer,
    auto_register_event_types,
)
from codetoreum.infrastructure.redis_config_cache import RedisConfigCache
from codetoreum.infrastructure.redis_event_buffer import RedisEventBuffer
from codetoreum.infrastructure.dead_letter_queue import (
    DeadLetterQueue,
    FailedEvent,
    FailureReason,
    DeadLetterQueueStats,
)
from codetoreum.infrastructure.mock_dead_letter_queue import MockDeadLetterQueue
from codetoreum.infrastructure.health.interfaces import (
    IHealthCheck,
    HealthCheckResult,
    HealthStatus,
    DependencyHealth,
)
from codetoreum.infrastructure.health.health_checker import (
    HealthChecker,
    CompositeHealthCheck,
    ConnectionHealthCheck,
    DatabaseHealthCheck,
    RedisHealthCheck,
    EventStoreHealthCheck,
    CircuitBreakerHealthCheck,
    RateLimiterHealthCheck,
)

__all__ = [
    # Event infrastructure
    "EventSerializer",
    "auto_register_event_types",
    "EventBus",
    "EventHandler",
    "event_handler",
    "EventReplayer",
    "RedisConfigCache",
    "RedisEventBuffer",
    # Dead letter queue
    "DeadLetterQueue",
    "FailedEvent",
    "FailureReason",
    "DeadLetterQueueStats",
    "MockDeadLetterQueue",
    # Health checks
    "IHealthCheck",
    "HealthCheckResult",
    "HealthStatus",
    "DependencyHealth",
    "HealthChecker",
    "CompositeHealthCheck",
    "ConnectionHealthCheck",
    "DatabaseHealthCheck",
    "RedisHealthCheck",
    "EventStoreHealthCheck",
    "CircuitBreakerHealthCheck",
    "RateLimiterHealthCheck",
]
