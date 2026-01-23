# Repair Cycle Port Interface Contract

## Overview

The `IRepairCycle` port interface defines a contract that all repair cycle implementations must satisfy. This contract ensures consistent behavior across different implementations in error handling, idempotency, state consistency, and boundary conditions.

**Note on Testing**: This document describes the complete contract. Current test coverage focuses on
**domain-level contracts** (domain type validation, immutability, data structure consistency).
Adapter method execution contracts require SimulationClock infrastructure fixes to test without hanging.

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

Abstract base class `TestRepairCycleDomainTypesContract` validates domain-level contracts.
Implementations inherit and implement `create_context()` to provide test context.

**Important**: Current tests focus on **domain-level contracts** (domain types, data structures,
validation rules). Adapter method contracts (that would test `run_tests()`, `fix_failures_by_file()`,
etc. execution behavior) require resolution of SimulationClock infrastructure issues - see
"Adapter Method Testing" section below.

### Test Categories

1. **Error Handling Tests** (4 tests)
   - Configuration validation (timeout > 0, max_iterations > 0)
   - Valid domain type construction
   - Empty input handling (empty failures dict, empty warnings list)

2. **Idempotency Tests** (2 tests)
   - Checkpoint context structure for idempotent retry semantics
   - Failures dict immutability for safe reuse

3. **State Consistency Tests** (3 tests)
   - Failures dict file count consistency
   - Failure count vs failures tuple length consistency
   - Warning count vs warning_list tuple length consistency

4. **Partial Failure & Boundary Tests** (4 tests)
   - Partial failure state consistency (RepairTestResult with mixed pass/fail)
   - Circuit breaker boundary value handling
   - max_iterations valid value ranges (1-100)
   - test_type support (UNIT, INTEGRATION, E2E)

5. **Thread Safety Tests** (3 tests)
   - Sequential operation context independence
   - Immutable config frozen dataclass enforcement
   - Immutable failure collection tuple enforcement

6. **Immutability Tests** (5 tests)
   - RepairCycleResult immutability
   - RepairTestResult immutability
   - RepairTestFailure immutability
   - CycleResult immutability
   - Domain type modification attempts raise FrozenInstanceError

### Adapter Method Testing

**Current Status**: Tests that would invoke adapter methods (like `run_tests()`,
`fix_failures_by_file()`, `handle_warnings()`) hang due to SimulationClock
infrastructure issues in those methods.

**Workaround**: Domain-level contract tests currently focus on testing:
- Domain type construction and validation
- Data structure consistency
- Immutability guarantees

**TODO**: Adapter method contracts require:
1. Fixing SimulationClock.advance() hanging issue
2. Adding separate adapter integration tests
3. Testing actual adapter method behavior (not just domain types)

**For now**: All 21 domain-level contract tests pass and validate:
- All domain types can be constructed safely
- All validation rules are enforced
- All data structures maintain consistency
- All collections are immutable
- Configuration boundaries are respected

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
7. Pass domain-level contract tests by inheriting `TestRepairCycleDomainTypesContract`
   - Note: Full adapter method testing requires SimulationClock infrastructure fixes

### Verifying Contract Compliance

Run domain-level contract tests:
```bash
pytest tests/unit/ports/output/test_repair_cycle_service_contract.py -v
```

All 21 tests should pass, verifying:
- Domain types validation rules
- Immutability enforcement
- Data structure consistency
- Configuration boundary handling
- Thread-safety via immutability

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

