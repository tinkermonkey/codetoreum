# Infrastructure Layer

The infrastructure layer provides cross-cutting concerns that support the entire system. These foundational systems handle event distribution, resilience patterns, and observability without being part of core business logic.

## Contents

### event-bus.md (Phase 5)
**Event Distribution, Persistence, and Replay**

The event bus is the central nervous system of the event-driven architecture. It handles:

- **Event Publication**: Emitted events are submitted to the bus
- **Event Persistence**: Events are stored in Redis for audit trail and replay
- **Event Serialization**: Domain events are serialized to JSON for storage
- **Subscriber Management**: Event handlers register for events of interest
- **Async Delivery**: Handlers are invoked asynchronously
- **Failed Events**: Exceptions during handler execution are captured
- **Dead Letter Queue**: Persistently failed events are recorded for investigation

Key components:
- `IEventEmitter` — Output port for publishing events
- `IEventStore` — Output port for persisting events
- `IFailedEventStore` — Output port for tracking failures
- `event_bus.py` — Central event distribution
- `event_bus_wiring.py` — Event-to-handler registration

### resilience.md (Phase 5)
**Circuit Breakers, Rate Limiting, Retries, and Decorators**

Resilience patterns protect the system from cascading failures when external systems are unavailable or degraded. The system uses infrastructure-level decorators rather than embedding resilience logic in adapters.

Key patterns:
- **Circuit Breaker**: Fail fast when external system is down
- **Rate Limiting**: Respect API rate limits
- **Retries**: Automatic retry with exponential backoff
- **Timeouts**: Bound how long to wait for responses
- **Bulkheads**: Isolate failure domains

Key components:
- `ResilientBoardServiceDecorator` — Example: wraps IBoardService
- `ResilientCodeReviewServiceDecorator` — Wraps ICodeReviewService
- Decorator factory functions
- Configuration for timeouts, retry counts, circuit thresholds

Benefits of the decorator pattern:
- Adapters remain pure (no resilience logic embedded)
- Resilience policies centralized and reusable
- Production and mock implementations can have different policies
- Testable in isolation from core logic

### observability.md (Phase 5)
**Structured Logging, Metrics, Tracing, and Audit Trail**

Observability systems enable visibility into system behavior for debugging, monitoring, and compliance.

Key components:

- **Structured Logging** (`observability/logging/`): Context-aware logs with event_id, correlation_id, project_id
- **Metrics** (`observability/metrics/`): Prometheus-compatible metrics collection (events emitted, handler errors, latency)
- **Tracing** (OpenTelemetry/Jaeger): Distributed request tracing across service boundaries
- **Audit Logging** (`observability/audit/`): Immutable record of sensitive operations
- **Dead Letter Queue** (`dead_letter_queue.py`): Capture and track persistently failed events

Each observability component is designed to:
- Provide complete visibility without impacting performance
- Support compliance and forensics requirements
- Enable root cause analysis of failures
- Track system health and performance

## Architecture

Infrastructure is consumed by:
- **Application Services**: Use event bus, logging, metrics
- **Adapters**: Use resilience decorators, tracing
- **Domain Events**: Emitted to event bus for distribution
- **External Systems**: Wrapped in resilience decorators

```
             Event Bus (Central)
                    ↓
    Resilience ← Event Distribution → Observability
      Patterns      & Logging          & Metrics
```

## Key Principles

1. **Non-Intrusive**: Infrastructure doesn't change application logic
2. **Transparent**: Implemented via decorators, middleware, and logging
3. **Auditable**: All significant operations are logged
4. **Observable**: Complete visibility into system state and behavior
5. **Resilient**: Failures are handled gracefully with retry and fallback logic

## Configuration

Infrastructure behavior is configured through:
- Environment variables (timeouts, retry counts)
- Configuration database entries (resilience policies)
- Feature flags (enable/disable specific patterns)

The system distinguishes between:
- **Production Infrastructure**: Real implementations with real timeouts and rate limits
- **Simulation Infrastructure**: Mock/fast implementations for testing

## Phase Delivery

- **Phase 5**: Complete infrastructure documentation
- **Phase 6+**: Infrastructure configurations become part of implementation tier documentation

## See Also

- [Application Services](../application-services/)
- [Domain Layer](../domain/)
- [Port Layer](../ports/)
