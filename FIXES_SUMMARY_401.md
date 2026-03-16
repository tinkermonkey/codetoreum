# PR #401 Fixes - SimulationApplicationBootstrap

## Overview
This document summarizes the three critical fixes applied to `SimulationApplicationBootstrap` in `src/codetoreum/infrastructure/simulation/bootstrap.py` based on PR review feedback.

## Issue 1: failed_event_store Type Leaks Infrastructure Concerns

### Problem
Line 279: `failed_event_store: DeadLetterQueueFailedEventStoreAdapter` was typed as the concrete adapter instead of the port interface. This enabled calling infrastructure-specific lifecycle methods (`start_retry_processor()`, `stop_retry_processor()`) at the bootstrap level (lines 390, 424), violating the hexagonal architecture principle that the application layer should depend on port interfaces, not concrete implementations.

### Fix Applied
- Changed type annotation from `DeadLetterQueueFailedEventStoreAdapter` to `"IFailedEventStore"` (line 280)
- Added import for `IFailedEventStore` port interface (line 174)
- Updated `setup()` method (line 392-394) to cast to concrete adapter when accessing infrastructure-specific lifecycle methods:
  ```python
  dlq_adapter = self.infrastructure.failed_event_store
  if isinstance(dlq_adapter, DeadLetterQueueFailedEventStoreAdapter):
      await dlq_adapter.start_retry_processor(...)
  ```
- Updated `teardown()` method (line 433-435) similarly for `stop_retry_processor()` call

### Benefits
- Enforces port interface boundaries at the type level
- Makes infrastructure concerns explicit through runtime type checking
- Maintains hexagonal architecture: application layer uses ports, infrastructure details hidden
- Enables future adapter swapping without bootstrap changes

### Test Coverage
- `TestBootstrapFailedEventStoreTyping::test_failed_event_store_typed_as_port_interface` - Verifies type is `IFailedEventStore`
- `TestBootstrapFailedEventStoreTyping::test_failed_event_store_lifecycle_methods_accessible` - Verifies adapter methods accessible via instance check

---

## Issue 2: teardown() Swallows Exceptions Without Re-raising

### Problem
Lines 451-456: The `teardown()` method caught all exceptions but did not re-raise them. If DLQ `stop_retry_processor()` (line 424) or engine `stop()` (line 428) failed, the caller (typically a test fixture) never learned that teardown was incomplete. The `_is_setup` flag remained `True`, but references were partially cleared, leaving inconsistent state.

### Fix Applied
- Added `raise` statement at line 469 to re-raise caught exceptions
- Updated docstring (lines 420-423) to document that teardown re-raises exceptions
- Exception logging still occurs for visibility, but exception is not swallowed

```python
except Exception as e:
    logger.error(...)
    # Re-raise to ensure caller (typically test fixture) knows teardown failed
    raise
```

### Behavior Changes
- **Before**: Teardown failures were logged but not raised; caller unaware of incomplete cleanup
- **After**: Teardown failures are logged AND raised; caller can handle incomplete cleanup

### State Management
- If teardown fails, `_is_setup` remains `True` and state is preserved, allowing retry or manual cleanup
- Only successful teardown clears the `_is_setup` flag (line 459)
- This ensures reliable state tracking even on failure

### Test Coverage
- `TestBootstrapTeardownExceptionHandling::test_teardown_reraises_engine_stop_failure` - Verifies engine stop failures are re-raised
- `TestBootstrapTeardownExceptionHandling::test_teardown_reraises_dlq_stop_failure` - Verifies DLQ stop failures are re-raised
- `TestBootstrapTeardownExceptionHandling::test_teardown_state_preserved_on_failure` - Verifies state not cleared on failure
- `TestBootstrapTeardownExceptionHandling::test_teardown_is_noop_when_not_setup` - Verifies teardown is safe when never set up

---

## Issue 3: DLQ Retry Handler Silently Deletes Unknown Event Types

### Problem
Lines 791-800: When the DLQ retry handler encountered an unknown event type, it logged a warning and returned successfully (no exception). The DLQ interpreted this successful return as a successful retry and permanently removed the event from the queue. If a new event type was added but the handler mapping not updated, failed events of that type were silently purged.

### Fix Applied
- Changed handler behavior to raise `ValueError` for unknown event types (lines 804-816)
- Descriptive error message indicates handler mapping is not updated
- Exception is logged as ERROR (not warning) before raising

```python
else:
    # For unknown event types, raise exception to prevent silent deletion
    # This ensures the DLQ doesn't remove events of unmapped types on first retry.
    # The retry processor will treat this as a processing failure and retry with backoff.
    message = f"Unknown event type '{event_type}' in dead letter queue - handler mapping not updated"
    logger.error(message, ...)
    raise ValueError(message)
```

### DLQ Behavior
- DLQ treats exception as processing failure (not permanent failure)
- Event remains in queue for retry with exponential backoff
- Operator/developer must update handler mapping and deploy to resolve
- Failed events are never silently deleted

### Test Coverage
- `TestBootstrapDLQRetryHandlerUnknownEventType::test_dlq_retry_handler_raises_on_unknown_event_type` - Verifies ValueError raised for unknown types
- `TestBootstrapDLQRetryHandlerUnknownEventType::test_dlq_retry_handler_succeeds_for_known_event_types` - Verifies known types work correctly
- `TestBootstrapIntegrationFixes::test_setup_and_teardown_with_all_fixes` - Integration test combining all fixes

---

## Files Changed

### Modified Files
1. **src/codetoreum/infrastructure/simulation/bootstrap.py**
   - Added import: `IFailedEventStore` (line 174)
   - Changed `SimulationInfrastructure.failed_event_store` type (line 280)
   - Updated `setup()` DLQ start logic with adapter type check (lines 392-394)
   - Updated `teardown()` DLQ stop logic with adapter type check (lines 433-435)
   - Updated `teardown()` to re-raise exceptions (line 469)
   - Updated `teardown()` docstring to document exception re-raising (lines 420-423)
   - Updated DLQ retry handler to raise on unknown event types (lines 804-816)

### New Test File
1. **tests/simulation/test_bootstrap_fixes.py** (10 comprehensive tests)
   - Port interface typing verification
   - Exception handling and state preservation
   - Unknown event type handling
   - Integration tests

---

## Test Results

All tests pass (34 total):
- Existing bootstrap tests: 24 passed
- New PR #401 fix tests: 10 passed

```
tests/simulation/test_bootstrap.py (24 tests) ✓
tests/simulation/test_bootstrap_fixes.py (10 tests) ✓
```

---

## Architectural Impact

### Hexagonal Architecture Compliance
✅ **Port Interface Boundaries Enforced**: Application layer now explicitly depends on `IFailedEventStore` port, not concrete adapter

### Reliability Improvements
✅ **No Silent Failures**: DLQ retry handler now raises exceptions for unmapped events instead of silently deleting them
✅ **Proper Error Propagation**: Teardown failures are now visible to callers through re-raised exceptions
✅ **State Consistency**: Failed teardowns preserve state for recovery attempts

### Maintainability
✅ **Future-Proof Event Handling**: Adding new event types requires updating handler mapping (enforced by exception)
✅ **Clear Failure Modes**: All failure scenarios (unknown events, teardown errors) now explicitly raise exceptions

---

## Migration Notes

### For Framework Users
- Tests using `bootstrap.teardown()` should now expect exceptions if cleanup fails
- Teardown fixtures should now have exception handling if they need to proceed despite cleanup failure
- This is typically the desired behavior (fail the test if cleanup fails)

### For Handler Development
- New domain event types MUST be added to the DLQ retry handler mapping in `_create_dlq_retry_handler()`
- Failure to do so will cause exceptions (not silent deletion)
- Check error logs for "Unknown event type in dead letter queue" to identify unmapped types

---

## Related Issues
- Issue #371: Event bridge reliability (addresses silent DLQ deletion)
- Issue #403: Board Event Handler interaction (related cleanup concerns)
- Issue #402: ExecutionServiceAgentExecutor error handling (related failure handling)
