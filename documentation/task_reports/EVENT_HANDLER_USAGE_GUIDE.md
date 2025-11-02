# Event Handler Usage Guide

## Quick Start

### 1. Set Up Event Bus

```python
from codetoreum.application.event_bus_wiring import setup_event_bus
from codetoreum.application.workflow_orchestrator import WorkflowOrchestrator
from codetoreum.application.execution_service import ExecutionService
from codetoreum.application.review_service import ReviewService

# Create your application services
orchestrator = WorkflowOrchestrator(...)
execution_svc = ExecutionService(...)
review_svc = ReviewService(...)

# Set up event bus with all handlers (one line!)
registry = setup_event_bus(
    workflow_orchestrator=orchestrator,
    execution_service=execution_svc,
    review_service=review_svc,
)

# That's it! Event handlers are now registered and ready
```

### 2. Publish Events

Events are automatically published by domain entities when state changes occur:

```python
# Domain entities emit events
work_item = WorkItem.create(
    title="Implement feature X",
    description="Description here",
    project_id="proj-123",
)

# Get pending events
events = work_item.get_pending_events()

# Publish to event bus
for event in events:
    await registry.event_bus.publish(event)

# Clear events after publishing
work_item.clear_events()
```

### 3. Access Metrics

```python
# Get execution metrics
execution_handler = registry.get_handler("execution")
metrics = execution_handler.get_metrics()
print(f"Success rate: {metrics['success_rate']}%")

# Get review metrics
review_handler = registry.get_handler("review")
metrics = review_handler.get_metrics()
print(f"Approval rate: {metrics['approval_rate']}%")

# Get event bus statistics
stats = registry.get_statistics()
print(f"Events published: {stats['events_published']}")
```

## Event Handler Details

### WorkflowEventHandler

**Handles**: Workflow lifecycle events

**Events**:
- `WorkItemCreated` - New work item added to system
- `ExecutionCompleted` - Agent execution finished successfully
- `ExecutionFailed` - Agent execution failed
- `ReviewCycleApproved` - Review cycle approved
- `ReviewCycleRejected` - Review cycle rejected (needs revision)
- `ReviewCycleEscalated` - Review cycle escalated to human

**Actions** (current):
- Logs events for debugging
- Prepares workflow progression decisions

**Actions** (future - Phase 6+):
- Move cards to next column on approval
- Queue revision tasks on rejection
- Create GitHub discussions/comments for escalation
- Add labels to work items

### ExecutionEventHandler

**Handles**: Agent execution lifecycle events

**Events**:
- `ExecutionInitialized` - Execution created
- `ExecutionStarted` - Execution started (container launched)
- `ExecutionCompleted` - Execution finished successfully
- `ExecutionFailed` - Execution failed with error
- `ExecutionTimeout` - Execution timed out

**Metrics Tracked**:
```python
{
    "total_executions": int,        # Total count
    "active_executions": int,       # Currently running
    "completed_executions": int,    # Successfully finished
    "failed_executions": int,       # Failed (including timeouts)
    "timed_out_executions": int,    # Specifically timed out
    "success_rate": float,          # % successful
    "failure_rate": float,          # % failed
    "timeout_rate": float,          # % timed out
}
```

**Active Tracking**:
```python
active_execs = execution_handler.get_active_executions()
# Returns: {"exec-123": "work-456", "exec-789": "work-012"}
```

### ReviewEventHandler

**Handles**: Review cycle events

**Events**:
- `ReviewCycleCreated` - New review cycle started
- `ReviewIterationStarted` - New iteration begun
- `ReviewFeedbackSubmitted` - Reviewer provided feedback
- `ReviewCycleApproved` - Review approved
- `ReviewCycleRejected` - Review rejected (final)
- `ReviewCycleEscalated` - Escalated to human

**Metrics Tracked**:
```python
{
    "total_reviews": int,               # Total count
    "active_reviews": int,              # Currently in progress
    "approved_reviews": int,            # Successfully approved
    "rejected_reviews": int,            # Rejected
    "escalated_reviews": int,           # Escalated to human
    "total_iterations": int,            # Total iterations across all reviews
    "approval_rate": float,             # % approved
    "rejection_rate": float,            # % rejected
    "escalation_rate": float,           # % escalated
    "avg_iterations_per_review": float, # Average iterations needed
}
```

**Active Tracking**:
```python
active_reviews = review_handler.get_active_reviews()
# Returns: {"review-123": "workflow-456", "review-789": "workflow-012"}
```

## Configuration

### Event Bus Settings

```python
# Custom retry configuration
from codetoreum.infrastructure.event_bus import EventBus

event_bus = EventBus(
    max_retries=5,              # Maximum retry attempts (default: 3)
    retry_delay_seconds=2.0,    # Delay between retries (default: 1.0)
)

# Use custom event bus with registry
from codetoreum.application.event_bus_wiring import EventBusRegistry

registry = EventBusRegistry(event_bus=event_bus)
registry.register_services(...)
registry.register_handlers(...)
```

### Selective Handler Registration

```python
# Register only specific handlers
registry = EventBusRegistry()
registry.register_services(
    execution_service=execution_svc,  # Only execution service
)
registry.register_handlers(
    register_workflow=False,  # Skip workflow handler
    register_execution=True,  # Register execution handler
    register_review=False,    # Skip review handler
)
```

## Error Handling

### Automatic Retry

Event bus automatically retries failed handlers with exponential backoff:

```
Attempt 1: Immediate
Attempt 2: Wait 1s
Attempt 3: Wait 2s
Attempt 4: Wait 3s (if max_retries=3)
```

### Error Statistics

```python
stats = registry.get_statistics()
print(f"Handler errors: {stats['handler_errors']}")
```

### Custom Error Handling

```python
from codetoreum.infrastructure.event_bus import EventHandler

class CustomHandler(EventHandler):
    async def handle(self, event):
        try:
            # Your logic here
            pass
        except SpecificError as e:
            logger.error(f"Specific error: {e}")
            # Don't raise - error is handled
        except Exception as e:
            # Raise to trigger retry
            raise
```

## Testing

### Unit Testing Handlers

```python
import pytest
from codetoreum.domain.events import ExecutionCompleted
from codetoreum.application.event_handlers import ExecutionEventHandler

@pytest.mark.asyncio
async def test_execution_completed():
    # Create handler with mock service
    handler = ExecutionEventHandler(execution_service=mock_service)

    # Create event (from domain entity)
    execution = AgentExecution.create(...)
    execution.complete(output="test", input_tokens=10, output_tokens=20)
    events = execution.get_pending_events()

    # Handle event
    await handler.handle(events[0])

    # Verify metrics
    metrics = handler.get_metrics()
    assert metrics["completed_executions"] == 1
```

### Integration Testing with Event Bus

```python
@pytest.mark.asyncio
async def test_event_flow():
    # Set up event bus
    registry = setup_event_bus(
        execution_service=mock_execution_service,
    )

    # Create and publish event
    execution = AgentExecution.create(...)
    execution.start(container_name="test-container")

    for event in execution.get_pending_events():
        await registry.event_bus.publish(event)

    # Verify handler processed event
    handler = registry.get_handler("execution")
    assert handler.get_metrics()["active_executions"] == 1
```

## Best Practices

### 1. Always Use Domain Entities

❌ **Don't**: Manually create events
```python
event = ExecutionCompleted(
    aggregate_id="exec-1",
    payload={"output": "test"},
)
```

✅ **Do**: Use domain entity methods
```python
execution = AgentExecution.create(...)
execution.complete(output="test", ...)
events = execution.get_pending_events()
```

### 2. Publish Events After State Changes

```python
# 1. Perform domain operation
work_item.start_work()

# 2. Get events
events = work_item.get_pending_events()

# 3. Persist to event store
for event in events:
    await event_store.append(event)

# 4. Publish to event bus
for event in events:
    await event_bus.publish(event)

# 5. Clear events
work_item.clear_events()
```

### 3. Use Batch Publishing

```python
# Efficient batch publishing
events = []
events.extend(work_item.get_pending_events())
events.extend(execution.get_pending_events())
events.extend(review.get_pending_events())

await event_bus.publish_batch(events)
```

### 4. Monitor Metrics

```python
# Regular metrics checks
import logging

def log_metrics(registry):
    exec_metrics = registry.get_handler("execution").get_metrics()
    review_metrics = registry.get_handler("review").get_metrics()

    logging.info(f"Execution success rate: {exec_metrics['success_rate']}%")
    logging.info(f"Review approval rate: {review_metrics['approval_rate']}%")

    if exec_metrics['failure_rate'] > 10:
        logging.warning(f"High failure rate: {exec_metrics['failure_rate']}%")
```

### 5. Clean Up Resources

```python
# Unregister handlers when done
registry.unregister_handlers()

# Reset statistics for testing
registry.reset_statistics()
```

## Troubleshooting

### Events Not Being Handled

**Check**:
1. Handler registered: `registry.get_handler("execution")` should not be None
2. Event type matches: Handler's `get_event_types()` includes event type
3. Event published: Check event bus statistics

```python
stats = registry.get_statistics()
print(f"Events published: {stats['events_published']}")
print(f"Events handled: {stats['events_handled']}")
print(f"Handler errors: {stats['handler_errors']}")
```

### Handler Errors

**Check**:
1. Event bus error statistics: `stats['handler_errors']`
2. Application logs for error details
3. Handler dependencies (services) are properly initialized

```python
# Enable debug logging
import logging
logging.getLogger("codetoreum.infrastructure.event_bus").setLevel(logging.DEBUG)
logging.getLogger("codetoreum.application.event_handlers").setLevel(logging.DEBUG)
```

### Metrics Not Updating

**Check**:
1. Events being published: `stats['events_published'] > 0`
2. Handler receiving events: Add logging to `handle()` method
3. Event types match: Handler only processes declared event types

```python
# Verify handler is receiving events
class DebugHandler(EventHandler):
    async def handle(self, event):
        print(f"Received: {event.event_type}")
        # Your logic here
```

## Advanced Usage

### Custom Event Handlers

```python
from codetoreum.infrastructure.event_bus import EventHandler, event_handler

@event_handler("CustomEvent")
class CustomEventHandler(EventHandler):
    def __init__(self, custom_service):
        self.service = custom_service
        self.metrics = {"count": 0}

    async def handle(self, event):
        self.metrics["count"] += 1
        await self.service.do_something(event)

# Register custom handler
registry.event_bus.register_handler(CustomEventHandler(custom_service))
```

### Wildcard Handlers

```python
from codetoreum.infrastructure.event_bus import EventHandler

class AuditHandler(EventHandler):
    def get_event_types(self):
        return []  # Empty list = receives ALL events

    async def handle(self, event):
        # Log all events for auditing
        logger.info(f"Event: {event.event_type} from {event.aggregate_id}")

registry.event_bus.register_handler(AuditHandler())
```

### Event Callbacks

```python
# Subscribe with callback function
async def my_callback(event):
    print(f"Received: {event.event_type}")

# Subscribe to specific event type
registry.event_bus.subscribe("ExecutionCompleted", my_callback)

# Subscribe to all events
registry.event_bus.subscribe(None, my_callback)

# Unsubscribe when done
registry.event_bus.unsubscribe("ExecutionCompleted", my_callback)
```

## Summary

The event handler system provides:

✅ **Automatic event processing** for all application services
✅ **Comprehensive metrics** for monitoring and debugging
✅ **Error handling with retry** for resilience
✅ **Easy integration** with one-line setup
✅ **Full testability** with mock adapters

For more details, see:
- [Phase 5.6 Completion Summary](PHASE_5_6_COMPLETION_SUMMARY.md)
- [Event Bus Implementation](src/codetoreum/infrastructure/event_bus.py)
- [Integration Tests](tests/integration/application/test_event_processing.py)
