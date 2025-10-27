# Infrastructure Resilience Layer

This module provides production-grade resilience patterns for all external system integrations in Codetoreum.

## Overview

The resilience layer ensures reliable interactions with external services (GitHub, Claude, Docker, etc.) by providing:

- **Rate Limiting**: Prevents exceeding API quotas (request-based and token-based)
- **Circuit Breaking**: Fails fast when downstream services are unhealthy
- **Retry Policies**: Handles transient errors with exponential backoff
- **Timeouts**: Prevents operations from hanging indefinitely
- **Simulation Support**: Mock implementations for fast testing without delays

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              APPLICATION LAYER                              │
│  WorkflowOrchestrator | AgentScheduler | ReviewService      │
│  (Uses ports - unaware of resilience)                       │
└─────────────────────────┬───────────────────────────────────┘
                          │ depends on
┌─────────────────────────▼───────────────────────────────────┐
│              OUTPUT PORTS (Interfaces)                      │
│  ITicketSystem | ILLMProvider | IRepository | IContainer    │
└─────────────────────────┬───────────────────────────────────┘
                          │ implemented by
┌─────────────────────────▼───────────────────────────────────┐
│          INFRASTRUCTURE RESILIENCE LAYER                    │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Resilient Decorators (composable wrappers)         │    │
│  ├────────────────────────────────────────────────────┤    │
│  │ • ResilientTicketSystemDecorator                   │    │
│  │ • ResilientLLMProviderDecorator                    │    │
│  └─────────────────┬──────────────────────────────────┘    │
│                    │ uses                                   │
│  ┌─────────────────▼──────────────────────────────────┐    │
│  │ Resilience Components                              │    │
│  │ • Rate Limiters (TokenBucketRateLimiter)          │    │
│  │ • Circuit Breakers (CircuitBreaker)                │    │
│  │ • Retry Policies (ExponentialBackoffRetry)         │    │
│  │ • Timeouts (AsyncTimeout)                          │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │ wraps
┌─────────────────────────▼───────────────────────────────────┐
│              SECONDARY ADAPTERS                             │
│  GitHubTicketAdapter | ClaudeCodeAdapter | DockerAdapter    │
│  (Pure adapter logic - no resilience code)                  │
└─────────────────────────────────────────────────────────────┘
```

## Key Principles

1. **Adapters remain pure** - No resilience logic in adapter code
2. **Resilience is injected** - Through decorators at composition time
3. **Centralized implementation** - Single implementation, reused everywhere
4. **Composable patterns** - Mix and match rate limiting, circuit breakers, retries, timeouts
5. **Mode-aware** - Production, simulation, and integration test modes

## Usage

### Production Mode

```python
from codetoreum.infrastructure.resilience import ResilienceFactory, OperationMode
from codetoreum.adapters.secondary import GitHubTicketAdapter

# Create factory in production mode
factory = ResilienceFactory(mode=OperationMode.PRODUCTION)

# Create raw adapter
github_adapter = GitHubTicketAdapter(
    owner="myorg",
    repo="myrepo",
    token=os.getenv("GITHUB_TOKEN")
)

# Wrap with resilience
resilient_github = factory.create_resilient_ticket_system(github_adapter)

# Use in application
workflow_orchestrator = WorkflowOrchestrator(
    ticket_system=resilient_github,  # Automatically gets resilience
    ...
)
```

### Simulation Mode (Fast Testing)

```python
from codetoreum.infrastructure.resilience import ResilienceFactory, OperationMode

# Create factory in simulation mode
factory = ResilienceFactory(mode=OperationMode.SIMULATION)

# Mock adapters
mock_github = InMemoryTicketAdapter()
mock_claude = MockLLMProvider()

# Wrap with mock resilience (no delays, just tracking)
resilient_github = factory.create_resilient_ticket_system(mock_github)
resilient_claude = factory.create_resilient_llm_provider(mock_claude)

# Run simulation (fast, no external calls, no delays)
await orchestrator.handle_card_movement(event)

# Assert resilience was applied
assert len(resilient_github._rate_limiter.acquire_calls) > 0
```

### Custom Configuration

```python
factory = ResilienceFactory(
    mode=OperationMode.PRODUCTION,
    config={
        "max_requests": 100,
        "window_seconds": 60,
        "max_retries": 3,
        "failure_threshold": 5
    }
)

resilient_adapter = factory.create_resilient_ticket_system(
    adapter,
    service_config={
        "max_requests": 200  # Override factory config
    }
)
```

## Components

### Rate Limiters

**TokenBucketRateLimiter** (Production)
- Sliding window rate limiting
- Request-based and token-based limiting
- Configurable max wait time
- Thread-safe async implementation

**MockRateLimiter** (Simulation)
- No delays (fast testing)
- Records all acquire calls
- Optional enforcement for integration tests

### Circuit Breakers

**CircuitBreaker** (Production)
- States: CLOSED → OPEN → HALF_OPEN
- Configurable failure threshold
- Automatic recovery testing
- Prevents cascading failures

**MockCircuitBreaker** (Simulation)
- Configurable state
- Records all calls
- Simulates failures

### Retry Policies

**ExponentialBackoffRetry** (Production)
- Exponential backoff with jitter
- Configurable max retries
- Non-retryable exception handling
- Statistics tracking

**MockRetryPolicy** (Simulation)
- No retries by default
- Optional retry simulation
- Records execution history

### Timeouts

**AsyncTimeout** (Production)
- Uses asyncio.wait_for
- Configurable per-operation timeouts
- Duration tracking

**MockTimeout** (Simulation)
- No timeout enforcement by default
- Optional simulation
- Records all executions

## Configuration

### Predefined Service Configs

```python
from codetoreum.infrastructure.resilience import (
    GITHUB_RESILIENCE_CONFIG,
    CLAUDE_RESILIENCE_CONFIG,
    CONTAINER_RESILIENCE_CONFIG
)

# GitHub: 5000 req/hour, 3 retries, 30s timeout
# Claude: 50 req/min, 40k tokens/min, 2 retries, 300s timeout
# Container: 100 req/min, 3 retries, 60s timeout
```

### Custom Service Config

```python
from codetoreum.infrastructure.resilience import ServiceResilienceConfig

config = ServiceResilienceConfig(
    service_name="custom_service",
    rate_limit=RateLimitConfig(
        max_requests=1000,
        window_seconds=60
    ),
    circuit_breaker=CircuitBreakerConfig(
        failure_threshold=5,
        timeout_seconds=60
    ),
    retry=RetryConfig(
        max_retries=3,
        base_delay=1.0
    ),
    timeout=TimeoutConfig(
        default_timeout_seconds=45.0
    )
)
```

## Testing

### Unit Tests

```bash
pytest tests/unit/infrastructure/resilience/ -v
```

- Tests for each resilience component
- Mock implementations
- Configuration and factory

### Integration Tests

```bash
pytest tests/integration/infrastructure/resilience/ -v
```

- End-to-end resilience patterns
- Flaky adapter simulations
- Mode switching (production, simulation, integration)

## Coverage

The resilience layer has comprehensive test coverage:

- **Rate Limiter**: 96%
- **Circuit Breaker**: 98%
- **Retry Policy**: 92%
- **Timeout**: 100%
- **Mocks**: 80%
- **Factory**: 80%

## Design Documentation

For detailed design specifications, see:
- `/workspace/documentation/01_design/infrastructure/resilience_infrastructure_design.md`

## Key Features

✅ **Centralized**: Single implementation, reused across all adapters
✅ **Composable**: Mix and match patterns as needed
✅ **Mode-aware**: Production, simulation, and integration test modes
✅ **Observable**: Built-in statistics and metrics
✅ **Testable**: Mock implementations for fast testing
✅ **Configurable**: Per-service and per-operation configuration
✅ **Production-ready**: Battle-tested patterns with proper state management

## Examples

See `tests/integration/infrastructure/resilience/test_decorators.py` for complete examples of:
- Retrying transient failures
- Circuit breaker opening after repeated failures
- Rate limiting enforcement
- Token-based rate limiting for LLMs
- Simulation mode performance
- End-to-end resilience stack
