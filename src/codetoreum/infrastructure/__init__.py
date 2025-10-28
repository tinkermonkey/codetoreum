"""Infrastructure layer for Codetoreum.

This package contains cross-cutting concerns and infrastructure components:
- Event sourcing infrastructure (serialization, buffering, persistence)
- Event bus for real-time event handling
- Event replayer for debugging and recovery
- Configuration caching with Redis
- Resilience patterns (circuit breakers, rate limiting, retries, timeouts)
"""

from codetoreum.infrastructure.event_bus import EventBus, EventHandler, event_handler
from codetoreum.infrastructure.event_replayer import EventReplayer
from codetoreum.infrastructure.event_serialization import (
    EventSerializer,
    auto_register_event_types,
)
from codetoreum.infrastructure.redis_config_cache import RedisConfigCache
from codetoreum.infrastructure.redis_event_buffer import RedisEventBuffer

__all__ = [
    "EventSerializer",
    "auto_register_event_types",
    "EventBus",
    "EventHandler",
    "event_handler",
    "EventReplayer",
    "RedisConfigCache",
    "RedisEventBuffer",
]
