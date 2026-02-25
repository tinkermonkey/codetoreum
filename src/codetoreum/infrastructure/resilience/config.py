"""Resilience configuration.

Provides dataclasses for configuring resilience components and
predefined service-specific configurations.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class OperationMode(Enum):
    """System operation mode."""
    PRODUCTION = "production"
    SIMULATION = "simulation"
    INTEGRATION_TEST = "integration_test"


@dataclass
class RateLimitConfig:
    """Rate limiter configuration."""
    max_requests: int
    window_seconds: int = 60
    max_tokens: int | None = None
    max_wait_seconds: float | None = None


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    timeout_seconds: int = 60
    success_threshold: int = 2


@dataclass
class RetryConfig:
    """Retry policy configuration."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class TimeoutConfig:
    """Timeout configuration."""
    default_timeout_seconds: float = 30.0


@dataclass
class ServiceResilienceConfig:
    """Complete resilience configuration for a service."""
    service_name: str
    rate_limit: RateLimitConfig | None = None
    circuit_breaker: CircuitBreakerConfig | None = None
    retry: RetryConfig | None = None
    timeout: TimeoutConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {"service_name": self.service_name}

        if self.rate_limit:
            result["rate_limit"] = {
                "max_requests": self.rate_limit.max_requests,
                "window_seconds": self.rate_limit.window_seconds,
                "max_tokens": self.rate_limit.max_tokens,
                "max_wait_seconds": self.rate_limit.max_wait_seconds
            }

        if self.circuit_breaker:
            result["circuit_breaker"] = {
                "failure_threshold": self.circuit_breaker.failure_threshold,
                "timeout_seconds": self.circuit_breaker.timeout_seconds,
                "success_threshold": self.circuit_breaker.success_threshold
            }

        if self.retry:
            result["retry"] = {
                "max_retries": self.retry.max_retries,
                "base_delay": self.retry.base_delay,
                "max_delay": self.retry.max_delay,
                "exponential_base": self.retry.exponential_base,
                "jitter": self.retry.jitter
            }

        if self.timeout:
            result["timeout"] = {
                "default_timeout_seconds": self.timeout.default_timeout_seconds
            }

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServiceResilienceConfig":
        """Create from dictionary."""
        rate_limit = None
        if "rate_limit" in data:
            rl = data["rate_limit"]
            rate_limit = RateLimitConfig(
                max_requests=rl["max_requests"],
                window_seconds=rl.get("window_seconds", 60),
                max_tokens=rl.get("max_tokens"),
                max_wait_seconds=rl.get("max_wait_seconds")
            )

        circuit_breaker = None
        if "circuit_breaker" in data:
            cb = data["circuit_breaker"]
            circuit_breaker = CircuitBreakerConfig(
                failure_threshold=cb.get("failure_threshold", 5),
                timeout_seconds=cb.get("timeout_seconds", 60),
                success_threshold=cb.get("success_threshold", 2)
            )

        retry = None
        if "retry" in data:
            r = data["retry"]
            retry = RetryConfig(
                max_retries=r.get("max_retries", 3),
                base_delay=r.get("base_delay", 1.0),
                max_delay=r.get("max_delay", 60.0),
                exponential_base=r.get("exponential_base", 2.0),
                jitter=r.get("jitter", True)
            )

        timeout = None
        if "timeout" in data:
            t = data["timeout"]
            timeout = TimeoutConfig(
                default_timeout_seconds=t.get("default_timeout_seconds", 30.0)
            )

        return cls(
            service_name=data["service_name"],
            rate_limit=rate_limit,
            circuit_breaker=circuit_breaker,
            retry=retry,
            timeout=timeout
        )


# ============================================================================
# Predefined Service Configurations
# ============================================================================

# GitHub API configuration
GITHUB_RESILIENCE_CONFIG = ServiceResilienceConfig(
    service_name="github",
    rate_limit=RateLimitConfig(
        max_requests=5000,
        window_seconds=3600,  # GitHub: 5000 req/hour
        max_wait_seconds=60
    ),
    circuit_breaker=CircuitBreakerConfig(
        failure_threshold=5,
        timeout_seconds=60,
        success_threshold=2
    ),
    retry=RetryConfig(
        max_retries=3,
        base_delay=1.0,
        max_delay=30.0
    ),
    timeout=TimeoutConfig(
        default_timeout_seconds=30.0
    )
)

# Claude API configuration
CLAUDE_RESILIENCE_CONFIG = ServiceResilienceConfig(
    service_name="claude",
    rate_limit=RateLimitConfig(
        max_requests=50,
        window_seconds=60,  # Claude: ~50 req/min
        max_tokens=40000,   # Claude: 40k tokens/min
        max_wait_seconds=120
    ),
    circuit_breaker=CircuitBreakerConfig(
        failure_threshold=3,  # Fail faster for expensive LLM calls
        timeout_seconds=120,
        success_threshold=2
    ),
    retry=RetryConfig(
        max_retries=2,  # Less aggressive for expensive operations
        base_delay=2.0,
        max_delay=30.0
    ),
    timeout=TimeoutConfig(
        default_timeout_seconds=300.0  # 5 minutes for LLM
    )
)

# Docker/Container configuration
CONTAINER_RESILIENCE_CONFIG = ServiceResilienceConfig(
    service_name="container",
    rate_limit=RateLimitConfig(
        max_requests=100,
        window_seconds=60,
        max_wait_seconds=30
    ),
    circuit_breaker=CircuitBreakerConfig(
        failure_threshold=5,
        timeout_seconds=60,
        success_threshold=2
    ),
    retry=RetryConfig(
        max_retries=3,
        base_delay=1.0,
        max_delay=30.0
    ),
    timeout=TimeoutConfig(
        default_timeout_seconds=60.0
    )
)

# Git/Repository configuration
REPOSITORY_RESILIENCE_CONFIG = ServiceResilienceConfig(
    service_name="repository",
    rate_limit=RateLimitConfig(
        max_requests=200,
        window_seconds=60,
        max_wait_seconds=30
    ),
    circuit_breaker=CircuitBreakerConfig(
        failure_threshold=5,
        timeout_seconds=60,
        success_threshold=2
    ),
    retry=RetryConfig(
        max_retries=3,
        base_delay=1.0,
        max_delay=30.0
    ),
    timeout=TimeoutConfig(
        default_timeout_seconds=45.0
    )
)
