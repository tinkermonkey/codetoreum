# Agent Execution Recovery Service - Error Handling & Recovery Design

## Overview

The **AgentExecutionRecoveryService** handles recovery from agent execution failures in two critical scenarios:

1. **Completion Callback Failures** (auto-progression stuck): When the completion callback fails, the work item cannot progress to the next column despite successful agent execution
2. **Agent Execution Failures** (lock release failures): When agent execution fails synchronously (before task creation), the pipeline lock must be released to unblock queued work items

This service ensures work items don't remain stuck indefinitely and provides observability for manual intervention when needed.

## Problem Statements

### Issue #371 - Part 1: Completion Callback Failures

**Location**: `adapters/testing/execution_service_agent_executor.py:400-412`

**Problem**: The `_call_completion` method catches exceptions from the completion callback (`handle_agent_completion`) and only logs them, continuing execution. If auto-progression fails, the work item is permanently stuck in its current column with no recovery mechanism.

**Failure Mode**:
```
Work Item State: "In Development" (complete, awaiting auto-progression)
Agent Execution: Success ✓
Completion Callback: Raises RuntimeError("Auto-progression failed")
Result: Work item remains in "In Development" forever, pipeline blocked
```

### Issue #371 - Part 2: Lock Release Failures

**Location**: `application/event_handlers/board_event_handler.py:656-668`

**Problem**: The `_trigger_agent` method catches exceptions from `agent_executor.execute()` and logs them, but doesn't release the pipeline lock. A synchronous exception before task creation (e.g., VCS clone fails during workspace preparation) leaves the lock held indefinitely.

**Failure Mode**:
```
Workflow Run: Acquired pipeline lock
Agent Execution: Fails before task creation (exception in execute())
Lock Release: Never called
Result: Pipeline lock stuck, next queued work items blocked indefinitely
```

## Architecture

### Service Dependencies

```
AgentExecutionRecoveryService
├── IActiveWorkflowRunRegistry (optional)
│   └── For failing workflow runs on callback/execution failures
├── IEventStore (optional)
│   └── For persisting WorkflowFailed events
└── IBoardService (optional)
    └── For querying work item positions during DLQ enqueue
```

### Integration Points

**ExecutionServiceAgentExecutor** (`_call_completion`):
- Catches completion callback exceptions
- Invokes recovery service to handle callback failures
- Queues work item in dead letter queue for manual recovery
- Fails workflow run to signal pipeline blockage

**BoardColumnEventHandler** (`_trigger_agent`):
- Catches agent execution exceptions
- Invokes recovery service to handle execution failures
- Releases pipeline lock to unblock queued items
- Emits LockStuckEvent if lock release fails
- Fails workflow run to mark pipeline as broken

## Core Mechanisms

### 1. Completion Callback Failure Recovery

**Triggered By**: ExecutionServiceAgentExecutor._call_completion exception

**Recovery Flow**:
```
Agent execution succeeds → completion_callback() raises RuntimeError
    ↓
Log error with context (execution_success=True)
    ↓
Queue work item in dead letter queue (DLQ)
    ├── from_column: Current work item column
    ├── reason: Callback failure description
    ├── attempt_count: For tracking retry attempts
    └── Note: Admin/batch process must handle manual progression
    ↓
Fail workflow run via WorkflowFailed event
    ├── reason: "Completion callback failure: {error}"
    ├── failed_stage: Current pipeline stage
    └── Event persisted to event store for audit trail
    ↓
DLQ Processing (async, out-of-band):
    - Manual admin intervention
    - Automated retry with exponential backoff
    - Progress to next column via board service
    - Clear DLQ entry after successful progression
```

**Key Properties**:
- Work item remains in current column (safe state)
- No data loss (DLQ preserves intent to progress)
- Full audit trail (WorkflowFailed event)
- Observability (metrics on DLQ size, oldest item age)

### 2. Agent Execution Failure Recovery (Lock Release)

**Triggered By**: BoardColumnEventHandler._trigger_agent exception

**Recovery Flow**:
```
_trigger_agent() raises exception (before completion callback)
    ↓
Log error with context (work_item_id, board_id)
    ↓
Fail workflow run via WorkflowFailed event (optional, if run tracking available)
    ├── reason: "Agent execution failure: {error}"
    ├── failed_stage: Current pipeline stage
    └── Event persisted to event store
    ↓
Release pipeline lock (CRITICAL):
    ├── release_lock(project_id, board_id, work_item_id)
    ├── Next queued item acquires lock immediately
    ├── If next item has agent, re-trigger execution
    └── Log lock release success/failure clearly
    ↓
If lock release fails (critical):
    - Log CRITICAL error
    - Emit LockStuckEvent for manual intervention
    - Pipeline is blocked — requires admin action
    - No automatic recovery possible
```

**Key Properties**:
- Lock release is the critical recovery step
- Next queued items unblocked promptly
- Current work item stays in current column (failed state)
- LockStuckEvent alerts ops team for investigation

### 3. Dead Letter Queue (DLQ)

**Purpose**: Track work items stuck due to completion callback failures

**Data Structure**:
```python
@dataclass
class FailedAutoProgression:
    work_item_id: str          # Unique identifier
    board_id: str              # Board context
    from_column: str           # Current stuck column
    to_column: str             # Intended destination (may be UNKNOWN)
    reason: str                # Callback error message
    failed_at: datetime        # When failure occurred
    attempt_count: int         # Retry attempts (default: 1)
```

**Query Interface**:
```python
service.dead_letter_queue          # List all DLQ items
service.get_stuck_work_items()     # List just work item IDs
service.clear_dead_letter_queue()  # Manual cleanup after processing
```

## Error Handling Guarantees

### Completion Callback Failure

| Scenario | Guarantee |
|----------|-----------|
| Callback succeeds | Work item progresses normally |
| Callback fails (execution success) | Queued in DLQ, workflow failed, logged |
| Callback fails (execution failure) | Same as above + no DLQ (already failed) |
| Registry unavailable | Error logged, DLQ not updated (non-blocking) |
| Event store unavailable | Error logged, DLQ still used (in-memory fallback) |

### Agent Execution Failure

| Scenario | Guarantee |
|----------|-----------|
| Execution succeeds | Completion callback invoked |
| Execution fails (before task) | Lock released, next item unblocked, workflow failed |
| Lock release fails | LockStuckEvent emitted, ops alerted, manual intervention required |
| Registry unavailable | Execution still fails, lock still released (decoupled) |

## Integration with ExecutionServiceAgentExecutor

**Constructor Changes**:
```python
def __init__(
    self,
    # ... existing parameters ...
    recovery_service: AgentExecutionRecoveryService | None = None,
):
    self._recovery_service = recovery_service
```

**_call_completion Update**:
```python
async def _call_completion(self, work_item_id: str, board_id: str, success: bool):
    if self._completion_callback:
        try:
            await self._completion_callback(...)
        except Exception as e:
            logger.error(f"Completion callback failed: {e}", exc_info=True)
            # NEW: Use recovery service to handle the failure
            if self._recovery_service:
                await self._recovery_service.handle_completion_callback_failure(
                    work_item_id=work_item_id,
                    board_id=board_id,
                    success=success,
                    error=e,
                )
```

## Integration with BoardColumnEventHandler

**Constructor Changes**:
```python
def __init__(
    self,
    # ... existing parameters ...
    recovery_service: AgentExecutionRecoveryService | None = None,
):
    self.recovery_service = recovery_service
```

**_trigger_agent Update**:
```python
async def _trigger_agent(self, work_item_id: str, column_config: ColumnTemplate, board_id: str):
    try:
        await self.agent_executor.execute(...)
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)

        # NEW: Fail workflow run via recovery service
        if self.recovery_service:
            await self.recovery_service.handle_agent_execution_failure(
                work_item_id=work_item_id,
                board_id=board_id,
                error=e,
            )

        # NEW: CRITICAL — Release lock to unblock pipeline
        if work_item_id in self._active_runs:
            run_info = self._active_runs[work_item_id]
            try:
                release_result = await self.lock_service.release_lock(
                    project_id=run_info.get("project_id", ""),
                    board_id=board_id,
                    work_item_id=work_item_id,
                )
                logger.info(f"Lock released for {work_item_id} after execution failure")
            except Exception as lock_err:
                logger.critical(f"Failed to release lock for {work_item_id}: {lock_err}")
                # Emit LockStuckEvent for manual intervention
                if self.event_emitter:
                    try:
                        self.event_emitter.emit(LockStuckEvent(...))
                    except Exception as emit_err:
                        logger.error(f"Failed to emit LockStuckEvent: {emit_err}")
```

## Testing Strategy

### Unit Tests

**AgentExecutionRecoveryService** (`test_agent_execution_recovery_service.py`):
- Completion callback failure → DLQ enqueue
- Completion callback failure → WorkflowFailed event
- Agent execution failure → WorkflowFailed event
- DLQ operations (clear, query)
- FailedAutoProgression serialization

**ExecutionServiceAgentExecutor** (`test_execution_service_agent_executor.py`):
- Completion callback failure with recovery service
- Completion callback failure without recovery service (graceful degradation)
- Verify recovery service invoked with correct parameters

**BoardColumnEventHandler** (`test_board_event_handler.py`):
- Agent execution failure releases lock
- Agent execution failure fails workflow run
- Lock release failure emits LockStuckEvent
- Recovery service invoked on execution failure

### Integration Tests

- Full workflow with completion callback failure recovery
- Full workflow with agent execution failure and lock release
- DLQ processing and retry scenarios
- Metrics on DLQ size and oldest item age

## Observability

### Logging

**Completion Callback Failure**:
```
error: Completion callback failed for work item 'wi-1': RuntimeError(...)
  error_id: ERR_AGENT_EXECUTION_COMPLETION_CALLBACK_FAILURE
  execution_success: True

warning: Work item 'wi-1' queued in dead letter queue for manual progression
  error_id: ERR_AGENT_EXECUTION_DLQ_ENQUEUED
```

**Agent Execution Failure**:
```
error: Agent execution failed for work item 'wi-1': RuntimeError(...)
  error_id: ERR_AGENT_EXECUTION_FAILURE

info: Released lock for work item 'wi-1' due to execution failure
  error_id: INFO_BOARD_EVENT_LOCK_RELEASED_AFTER_FAILURE

critical: Failed to release lock for work item 'wi-1': RuntimeError(...)
  error_id: ERR_BOARD_EVENT_LOCK_RELEASE_CRITICAL_FAILURE
```

### Events

**WorkflowFailed**:
```python
WorkflowFailed(
    aggregate_id=run_id,
    payload={
        "failed_at": "2026-03-15T12:00:00Z",
        "reason": "Completion callback failure: RuntimeError(...)",
        "failed_stage": "code-review",
        "work_item_id": "wi-1",
    }
)
```

**LockStuckEvent**:
```python
LockStuckEvent(
    type="lock.stuck",
    timestamp="2026-03-15T12:00:00Z",
    source="board_event_handler._trigger_agent",
    project_id="proj-1",
    board_id="board-1",
    work_item_id="wi-1",
    reason="Failed to release lock after execution failure: RuntimeError(...)"
)
```

### Metrics

- `agent_execution_completion_callback_failures` (counter)
- `agent_execution_failures_with_lock_release` (counter)
- `agent_execution_failures_with_lock_stuck` (counter)
- `dead_letter_queue_size` (gauge)
- `dead_letter_queue_oldest_item_age_seconds` (gauge)

## Deployment Considerations

### Production Setup

1. **Recovery Service Injection**:
   - Create recovery service in bootstrap with real dependencies
   - Inject into ExecutionServiceAgentExecutor and BoardColumnEventHandler
   - Event store required for audit trail
   - Run registry recommended for workflow failure tracking

2. **Dead Letter Queue Processing**:
   - Implement async batch job to process DLQ items
   - Attempt automatic retry with exponential backoff (3 attempts)
   - Fall back to manual admin action after retries exhausted
   - Log all DLQ operations for audit

3. **Alerting**:
   - Alert on WorkflowFailed events (execution or callback failure)
   - Alert on LockStuckEvent (pipeline blocked)
   - Alert when DLQ size exceeds threshold
   - Alert when oldest DLQ item age exceeds SLA

### Simulation Mode

Recovery service works seamlessly in simulation:
- DLQ stays in-memory (no persistence needed)
- Mock event store captures WorkflowFailed events
- Mock event emitter captures LockStuckEvent
- Tests verify recovery behavior without external services

## Migration Path

### From Legacy Code

Legacy code probably had:
- Silent failures (exceptions logged, work item stuck forever)
- No observability (no DLQ, no workflow failure tracking)
- No lock release on execution failure

**Migration Steps**:
1. Inject recovery service into executors/handlers
2. Add WorkflowFailed event persistence (event store required)
3. Add DLQ query endpoints for admin dashboard
4. Add metrics and alerting for DLQ and lock stuck events
5. Implement async DLQ processor job

## Key Design Decisions

1. **DLQ is in-memory by default**: Allows graceful degradation if persistence unavailable. In production, process DLQ items promptly before restart.

2. **Lock release is critical**: Failure to release lock is logged as CRITICAL and emits alert. This is non-recoverable without manual intervention.

3. **Recovery service is optional**: Both ExecutionServiceAgentExecutor and BoardColumnEventHandler continue functioning if recovery_service=None, but without the recovery mechanisms.

4. **Completion callback failure doesn't block execution**: The execution already completed successfully; the failure is in the subsequent progression step. We queue for retry, not re-execute the agent.

5. **Separate concerns**: Recovery service handles persistence (DLQ, WorkflowFailed events). Lock release is handled by the handler itself because it's critical to pipeline unblocking.

## See Also

- [ExecutionServiceAgentExecutor Design](./agent_executor_design.md)
- [BoardColumnEventHandler Design](../application_services/application_services_inventory.md)
- [Pipeline Lock Service Design](./pipeline_lock_service_design.md)
- [Resilience Infrastructure Design](../infrastructure/resilience_infrastructure_design.md)
