# Repair Cycle Port Interface Contract

## Overview

The `IRepairCycle` port interface defines a contract that all repair cycle implementations must satisfy. This contract ensures consistent behavior across different implementations in error handling, idempotency, state consistency, and boundary conditions.

## Port Interface

Located in: `src/codetoreum/ports/output/repair_cycle_service.py`

The `IRepairCycle` protocol defines 5 core methods:

```python
async def execute(context: RepairCycleContext) -> RepairCycleResult
async def run_tests(config: RepairTestRunConfig, context: RepairCycleContext) -> RepairTestResult
async def fix_failures_by_file(grouped_failures: Dict[str, Tuple[RepairTestFailure, ...]],
                               config: RepairTestRunConfig, context: RepairCycleContext) -> int
async def handle_warnings(test_result: RepairTestResult,
                         config: RepairTestRunConfig, context: RepairCycleContext) -> int
async def checkpoint(test_type: RepairTestType, iteration: int, context: RepairCycleContext) -> None
```

## Contract Requirements

### 1. Error Handling Contract

All implementations MUST raise the same exceptions for the same error conditions:

#### Configuration Validation
- **Invalid timeout**: `RepairTestRunConfig` with `timeout <= 0` MUST raise `ValueError`
- **Invalid max_iterations**: `RepairTestRunConfig` with `max_iterations <= 0` MUST raise `ValueError`
- **Invalid max_file_iterations**: `RepairTestRunConfig` with `max_file_iterations <= 0` MUST raise `ValueError`

Error messages should clearly indicate the constraint violation.

#### Safe Operations
- **Empty failures dict**: `fix_failures_by_file({}, ...)` MUST return 0, NOT raise
- **Empty warnings**: `handle_warnings(result_with_0_warnings, ...)` MUST return 0, NOT raise
- **Empty test result**: `run_tests(...)` on test result with 0 tests MUST return valid result, NOT raise

### 2. Idempotency Contract

All implementations MUST support safe retries without side effects:

#### Checkpoint Idempotency
```python
await adapter.checkpoint(RepairTestType.UNIT, 5, context)
await adapter.checkpoint(RepairTestType.UNIT, 5, context)  # Same call - safe to retry
await adapter.checkpoint(RepairTestType.UNIT, 5, context)  # Same call - safe to retry
# No exception raised, no duplicate checkpoints created
```

#### Fix Failures Idempotency
```python
failures = {"test.py": (RepairTestFailure(...),)}
result1 = await adapter.fix_failures_by_file(failures, config, context)
result2 = await adapter.fix_failures_by_file(failures, config, context)  # Same failures
assert result1 == result2  # Same result count
```

#### State After Retries
- Retrying operations must not corrupt adapter internal state
- Retrying operations must not create duplicate records
- Retrying operations must be transparent to the rest of the system

### 3. State Consistency Contract

All implementations MUST maintain invariants:

#### File Count Consistency
```python
# If providing 5 files with failures:
failures = {
    f"test_{i}.py": (RepairTestFailure(...),) for i in range(5)
}
fixed_count = await adapter.fix_failures_by_file(failures, config, context)
assert fixed_count == 5  # Must exactly match input file count
```

#### Failure Count Consistency
```python
result = await adapter.run_tests(config, context)
assert result.failed == len(result.failures)  # Must match
```

#### Context Immutability
- Calling any adapter method MUST NOT modify the `context` object
- Context attributes (`stage_name`, `pipeline_run_id`, etc.) must remain unchanged

#### Result Completeness
- All returned results MUST have all fields populated (non-None where required)
- No partial or incomplete results
- All numeric counts >= 0

### 4. Boundary Condition Contract

All implementations MUST handle valid boundary values correctly:

#### Configuration Limits
- `max_iterations` values from 1 to 1000 MUST be accepted
- `timeout` values from 1 to 86400 (1 day) MUST be accepted
- `max_file_iterations` values from 1 to 100 MUST be accepted
- `max_total_agent_calls` values from 1 to 10000 MUST be accepted

#### Iteration Numbering
- Iterations are 1-indexed (first iteration is 1, not 0)
- No off-by-one errors when reaching max_iterations

#### Test Type Support
- All three test types MUST be supported:
  - `RepairTestType.UNIT`
  - `RepairTestType.INTEGRATION`
  - `RepairTestType.E2E`
- No exceptions for any test type

#### Circuit Breaker Enforcement
- When `context.max_total_agent_calls` is reached, execution must stop
- No silent failures or partial executions after circuit breaker

### 5. Immutability Contract

All domain types MUST be immutable (frozen dataclasses):

#### Immutable Types
- `RepairCycleResult`
- `CycleResult`
- `RepairTestResult`
- `RepairTestFailure`
- `RepairTestWarning`
- `RepairTestRunConfig`
- `RepairCycleStageConfig`

#### Enforcement
```python
result = RepairTestResult(...)
result.passed = 10  # MUST raise FrozenInstanceError or AttributeError
```

All collections (failures, warnings, results) are stored as tuples (immutable) not lists.

### 6. Event Emission Contract

Implementations that emit events MUST follow these rules:

#### Required Events
- `RepairCycleStartedEvent` when beginning execution
- `RepairCycleCompletedEvent` when cycle completes
- `RepairCycleTestExecutionCompletedEvent` after each test run
- `RepairCycleFileFixStartedEvent` and `RepairCycleFileFixCompletedEvent` for each file fix
- `RepairCycleWarningReviewStartedEvent` and `RepairCycleWarningReviewCompletedEvent` for warning reviews
- `RepairCycleFastFailEvent` when circuit breaker triggers

#### Event Timestamps
- All events MUST have valid ISO 8601 timestamps
- Timestamps MUST be monotonically increasing within an execution
- Events MUST include required context (pipeline_run_id, test_type, etc.)

## Test Coverage

Comprehensive contract tests are provided in:
`tests/unit/ports/output/test_repair_cycle_service_contract.py`

Abstract base class `TestRepairCycleServiceContract` validates all contracts.
Implementations inherit and implement `create_adapter()` and `create_context()`.

### Test Categories

1. **Error Handling Tests** (3 tests)
   - Invalid configuration detection
   - Empty input handling
   - Consistent error messages

2. **Idempotency Tests** (2 tests)
   - Checkpoint call safety
   - Fix failures retry safety
   - State preservation on retries

3. **State Consistency Tests** (3 tests)
   - File count accuracy
   - Failure count accuracy
   - Result completeness
   - Context immutability

4. **Boundary Condition Tests** (3 tests)
   - Valid configuration ranges
   - Circuit breaker enforcement
   - Test type support

5. **Immutability Tests** (5 tests)
   - Domain type immutability verification
   - FrozenInstanceError on modification attempts

## Implementation Patterns

### MockRepairCycleAdapter

The default mock implementation is located in:
`src/codetoreum/adapters/testing/mock_repair_cycle_adapter.py`

It demonstrates the contract requirements and provides:
- Deterministic test results via `set_iterations_until_success()`
- Configurable failure scenarios via `set_always_fail()`
- Event emission tracking
- SimulationClock integration for time manipulation
- Full compliance with IRepairCycle contract

### Implementing a New Adapter

To implement a new `IRepairCycle` adapter:

1. Implement all 5 methods
2. Validate all configuration values in constructors
3. Make all domain type instances immutable (use frozen dataclasses)
4. Support idempotent operations (safe to retry)
5. Maintain context object immutability
6. Emit required events with proper timestamps
7. Pass all contract tests by inheriting `TestRepairCycleServiceContract`

## Error Handling Guidelines

### No Silent Failures
All errors MUST be logged with `exc_info=True` for debugging:
```python
logger.error("Repair cycle failed", exc_info=True)
```

### Consistent Error Messages
Use specific, actionable error messages:
```python
# Good
ValueError("timeout must be > 0, got 0")
ValueError("max_iterations must be > 0, got 0")

# Avoid
ValueError("Invalid configuration")
ValueError("Config error")
```

## Design Principles

1. **Vendor-Agnostic**: Port interface hides implementation details
2. **Testability**: All implementations testable without external services
3. **Observability**: Event emission provides complete audit trail
4. **Immutability**: Domain types prevent accidental modifications
5. **Consistency**: Contract ensures all implementations behave identically

## Related Documents

- `ports/output/NEW_INTERFACES_QUICK_REFERENCE.md` - Quick port overview
- `domains/repair_cycle_domain.md` - Domain model specification
- `events/repair_cycle_events.md` - Event catalog
- `application_services/repair_cycle_orchestrator.md` - Orchestration patterns

