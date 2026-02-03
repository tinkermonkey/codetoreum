# Phase 3: SDLC Pipeline Testing - Comprehensive Guide

## Overview

Phase 3 implements comprehensive end-to-end testing of the complete Software Development Lifecycle (SDLC) pipeline with 4 core test scenarios covering the major workflow patterns and extensive edge case coverage.

The phase introduces scenarios that test realistic, complex workflows:
- **Scenario 06**: Happy Path Full SDLC
- **Scenario 08a**: SDLC with Code Review Feedback and Revisions
- **Scenario 08b**: SDLC with Test Failures and Repair Cycle
- **Scenario 08c**: SDLC with Escalation and Human Feedback

## Quick Start

### Running Phase 3 Tests

```bash
# Run all Phase 3 tests
pytest tests/simulation/test_scenarios.py -k "phase3" -v

# Run specific scenario
pytest tests/simulation/test_scenarios.py::test_scenario_06_happy_path_full_sdlc -v

# Run all Phase 3 tests with diagnostics
pytest tests/simulation/test_scenarios.py -k "phase3" -v -s

# Run Phase 3 with coverage
pytest tests/simulation/test_scenarios.py -k "phase3" --cov=src/codetoreum --cov-report=html
```

### Running from Python

```python
from tests.simulation.scenarios.scenario_06_happy_path_full_sdlc import (
    create_config,
    run_scenario
)
from codetoreum.infrastructure.simulation import SimulationRunner

async def run_test():
    config = create_config()
    runner = SimulationRunner(config)
    result = await runner.run(run_scenario)
    print(f"Success: {result.success}")
    print(f"Speed: {result.speed_multiplier:.1f}x")
```

## Scenario Specifications

### Scenario 06: Happy Path Full SDLC

**File**: `scenarios/scenario_06_happy_path_full_sdlc.py`

**Purpose**: Complete SDLC workflow from requirements through deployment with all stages succeeding

**Pipeline Flow**:
```
Requirements Analysis (5m)
    ↓
Architecture & Design (5m)
    ↓
Implementation (8m)
    ↓
Code Review (6m) ✓ APPROVED
    ↓
Testing & QA (5m) ✓ ALL PASS
    ↓
Deployment (4m) ✓ SUCCESS
```

**Key Characteristics**:
- Single work item progresses through 6 sequential stages
- All agents execute successfully
- No rejections, failures, or escalations
- Deterministic timing and predictable outcome
- Baseline scenario for SDLC workflow testing

**Agents Involved**:
1. `requirements-analyst` - Analyzes requirements
2. `architect` - Designs solution
3. `developer` - Implements features
4. `code-reviewer` - Validates code quality
5. `test-engineer` - Validates functionality
6. `devops-engineer` - Deploys to production

**Expected Duration**:
- Simulated: ~30 minutes
- Real (100x speed): ~18 seconds

**Key Assertions**:
- ✓ All 6 stages complete successfully
- ✓ Workflow status is COMPLETED
- ✓ 1 review approval (no rejections)
- ✓ 0 test failures
- ✓ 0 escalations
- ✓ Sufficient events captured (30+)

**Edge Cases Tested**:
- Empty work item transition
- Clean state between stages
- Event ordering verification
- Artifact generation

---

### Scenario 08a: SDLC with Code Review Feedback and Revisions

**File**: `scenarios/scenario_08a_sdlc_review_feedback.py`

**Purpose**: Full SDLC with code review rejection requiring developer revision

**Pipeline Flow**:
```
Requirements Analysis (5m)
    ↓
Architecture & Design (5m)
    ↓
Implementation (8m)
    ↓
Code Review (6m) ✗ REJECTED
    ↓
Developer Revision (7m)
    ↓
Code Review (5m) ✓ APPROVED
    ↓
Testing & QA (5m) ✓ ALL PASS
    ↓
Deployment (4m) ✓ SUCCESS
```

**Key Characteristics**:
- Initial code review rejects implementation with feedback
- Developer receives feedback and creates revision
- Revised code submitted for re-review
- Code review approves revised code
- Pipeline continues successfully

**Agents Involved**:
- Same 6 agents as Scenario 06
- Developer and Code Reviewer appear twice (revision cycle)

**Expected Duration**:
- Simulated: ~45 minutes
- Real (100x speed): ~27 seconds

**Key Assertions**:
- ✓ 1 code review rejection
- ✓ Developer revision triggered
- ✓ 1 code review approval after revision
- ✓ Workflow completes successfully
- ✓ 2 review cycles recorded
- ✓ Sufficient events for feedback loop (40+)

**Edge Cases Tested**:
- Review rejection handling
- Automatic retry with modified code
- Multiple review cycles
- State persistence across revision
- Event sequencing with rejections
- Comment/feedback threading

**Typical Issues Addressed in Revision**:
- Error handling improvements
- Security enhancements (webhook validation, signature verification)
- Observability improvements (logging and monitoring)
- Test coverage increases

---

### Scenario 08b: SDLC with Test Failures and Repair Cycle

**File**: `scenarios/scenario_08b_sdlc_test_failures_repair.py`

**Purpose**: Full SDLC with test failures that require developer fixes

**Pipeline Flow**:
```
Requirements Analysis (5m)
    ↓
Architecture & Design (5m)
    ↓
Implementation (8m)
    ↓
Code Review (6m) ✓ APPROVED
    ↓
Testing & QA (6m) ✗ 3 FAILURES
    ↓
Developer Repair (8m)
    ↓
Testing & QA (5m) ✓ ALL PASS
    ↓
Deployment (4m) ✓ SUCCESS
```

**Key Characteristics**:
- Initial test run discovers 3 failed tests
- Repair cycle triggered with failure details
- Developer fixes the issues
- Testing re-runs with all tests passing
- Pipeline continues to deployment

**Agents Involved**:
- Same 6 agents as Scenario 06
- Test Engineer and Developer appear twice (repair cycle)

**Expected Duration**:
- Simulated: ~50 minutes
- Real (100x speed): ~30 seconds

**Key Assertions**:
- ✓ 3 test failures detected initially
- ✓ Repair cycle triggered
- ✓ Developer repair completed
- ✓ 18 tests passing after repair
- ✓ Workflow completes successfully
- ✓ No escalations or review rejections
- ✓ Sufficient events for repair flow (45+)

**Edge Cases Tested**:
- Test failure detection and reporting
- Repair cycle triggering
- Code fixes and re-validation
- Failure state tracking
- Multiple test run cycles
- Artifact updates during repair
- Time tracking across repair

**Typical Issues Fixed in Repair**:
- Connection timeout race conditions
- Queue persistence under failures
- Connection pooling limits
- Error handling edge cases
- Test reliability improvements

---

### Scenario 08c: SDLC with Escalation and Human Feedback

**File**: `scenarios/scenario_08c_sdlc_escalation.py`

**Purpose**: Full SDLC with escalation during implementation requiring human feedback

**Pipeline Flow**:
```
Requirements Analysis (5m)
    ↓
Architecture & Design (5m)
    ↓
Implementation (4m) ⚠ ESCALATED
    ↓
Human Feedback Collection (5m)
    ↓
Decision: Use Microservices Approach
    ↓
Implementation Resumed (9m)
    ↓
Code Review (6m) ✓ APPROVED
    ↓
Testing & QA (5m) ✓ ALL PASS
    ↓
Deployment (4m) ✓ SUCCESS
```

**Key Characteristics**:
- Implementation encounters complexity requiring human decision
- Work item escalates to product owner
- Human provides feedback/decision
- Developer resumes based on feedback
- Pipeline continues successfully

**Agents Involved**:
- All 6 SDLC agents
- Plus Human (product owner) for decision making

**Expected Duration**:
- Simulated: ~55 minutes
- Real (100x speed): ~33 seconds

**Key Assertions**:
- ✓ 1 escalation triggered
- ✓ Human feedback requested
- ✓ Human feedback received
- ✓ Pipeline resumed after feedback
- ✓ Escalation resolved
- ✓ Workflow completes successfully
- ✓ Sufficient events for escalation flow (50+)

**Edge Cases Tested**:
- Escalation triggering and context
- Human feedback queueing
- Escalation resolution and resumption
- State preservation during wait
- Time accounting during delay
- Feedback incorporation into workflow

**Typical Escalation Scenarios**:
- Architecture decision point (monolithic vs. microservices)
- Priority conflict resolution
- Resource availability decision
- Technology choice decision
- Scope change approval

---

## Performance Targets

| Scenario | Expected Duration | Real Time @ 100x | Speed | Events |
|----------|------------------|------------------|-------|--------|
| Scenario 06 | 30 min | < 20s | 100x | 30+ |
| Scenario 08a | 45 min | < 30s | 100x | 40+ |
| Scenario 08b | 50 min | < 35s | 100x | 45+ |
| Scenario 08c | 55 min | < 40s | 100x | 50+ |

**Performance Targets**:
- ✓ Speed Multiplier: ≥ 10x (target: 100x)
- ✓ Events Captured: 100%
- ✓ Determinism: 100%
- ✓ Assertion Pass Rate: 100%

## Metrics Recorded

### Common Metrics (All Scenarios)
- Stage duration (min, max, avg)
- Agent execution time
- Total events captured
- Assertion pass count
- Simulation clock advancement
- Speed multiplier achieved

### Scenario-Specific Metrics

**Scenario 06 (Happy Path)**
- 6 stage completions
- 1 workflow completion
- 0 failures or escalations

**Scenario 08a (Review Feedback)**
- 1 review rejection
- 1 review approval
- 2 review cycles
- Developer revision time

**Scenario 08b (Test Failures)**
- 3 test failures
- 1 repair cycle
- 18 tests passing after repair
- Coverage percentage improvement

**Scenario 08c (Escalation)**
- 1 escalation triggered
- 1 escalation resolved
- Human feedback wait time
- Decision impact on pipeline

## Observability and Debugging

### Event Timeline

All scenarios produce detailed event timelines showing:

```
===== Event Timeline =====
  0.0s  WorkflowStarted
  5.2s  StageStarted (Requirements Analysis)
  5.4s  AgentExecutionStarted (requirements-analyst)
 10.6s  AgentExecutionCompleted (requirements-analyst)
 10.7s  StageCompleted (Requirements Analysis)
 11.0s  StageStarted (Architecture & Design)
 ...
```

### Diagnostic Methods

```python
# Print event timeline
from tests.simulation.helpers import print_event_timeline
print_event_timeline(runner)

# Print metrics summary
from tests.simulation.helpers import print_metrics_summary
print_metrics_summary(runner)

# Print notifications
from tests.simulation.helpers import print_notifications_summary
print_notifications_summary(runner)

# Print simulation summary
runner.print_summary()
```

## Testing Strategy

### Unit Testing Pattern

Each scenario includes:

1. **Configuration Creation**
   - Agent response patterns configured
   - Container command results mocked
   - Metadata initialized

2. **Scenario Execution**
   - Time advanced sequentially through stages
   - Events captured at each step
   - Assertions verified during execution

3. **Result Verification**
   - Success status checked
   - All assertions verified
   - Performance targets validated
   - Events count verified

### Common Assertions

```python
# Event verification
runner.assert_event_occurred("EventType")
runner.assert_event_count("EventType", expected_count)

# State verification
runner.assert_equal(actual, expected, name, message)
runner.assert_true(condition, name, message)
runner.assert_false(condition, name, message)

# Completion verification
workflow_completed = runner.get_events_by_type("WorkflowCompleted")
assert len(workflow_completed) == 1
```

## Running Tests in CI/CD

### GitHub Actions Example

```yaml
- name: Run Phase 3 SDLC Tests
  run: |
    pytest tests/simulation/test_scenarios.py -k "phase3" \
      -v --tb=short --junitxml=test-results.xml
  timeout-minutes: 5
```

### Performance Validation

```bash
# Run with coverage reporting
pytest tests/simulation/test_scenarios.py -k "phase3" \
  --cov=src/codetoreum \
  --cov-report=term-missing \
  --cov-report=html

# Run with performance profiling
pytest tests/simulation/test_scenarios.py -k "phase3" \
  --durations=10
```

## Implementation Patterns

### Configuration Pattern

```python
def create_config() -> SimulationConfig:
    config = SimulationConfig.create_fast_config(
        scenario_name="scenario_name",
        speed_multiplier=100.0,
    )

    # Configure agents
    config.add_agent_response_pattern(
        agent_id="agent-id",
        pattern=r".*",
        response="Agent response"
    )

    # Configure containers
    config.set_container_command_result(
        command="command-name",
        exit_code=0,
        stdout="success output"
    )

    return config
```

### Scenario Execution Pattern

```python
async def run_scenario(runner: SimulationRunner) -> None:
    # Stage 1
    runner.assert_true(True, "stage_1_start", "Starting Stage 1")
    await runner.advance_time(timedelta(minutes=5))
    runner.assert_event_occurred("AgentExecutionCompleted")
    await runner.advance_time(timedelta(minutes=1))

    # Stage 2
    await runner.advance_time(timedelta(minutes=5))
    runner.assert_event_occurred("StageCompleted")

    # Final verification
    workflow_completed = runner.get_events_by_type("WorkflowCompleted")
    runner.assert_equal(len(workflow_completed), 1, "workflow_complete")
```

### Test Registration Pattern

```python
@pytest.mark.simulation
@pytest.mark.scenario
@pytest.mark.phase3
@pytest.mark.asyncio
async def test_scenario_XX_name():
    """Test Scenario XX: Description."""
    config = create_config()
    runner = SimulationRunner(config)

    result = await runner.run(run_scenario)

    # Assertions
    assert result.success
    assert result.speed_multiplier >= 10.0
    assert result.assertions_failed == 0
```

## Troubleshooting

### Test Fails with Timeout

**Cause**: Simulation takes too long
**Solution**:
- Verify speed_multiplier is 100.0 or higher
- Check that time advancement is using await
- Reduce execution_delay in config

### Assertions Fail

**Cause**: Events not captured as expected
**Solution**:
- Use `print_event_timeline(runner)` to see what events occurred
- Check event type names match exactly (case-sensitive)
- Verify aggregate_id filtering if used

### Events Not Captured

**Cause**: Events not being emitted
**Solution**:
- Ensure `runner.advance_time()` is called with await
- Check event types in domain events
- Verify scenario logic is correct

### Performance Below Target

**Cause**: Scenario runs slower than 10x
**Solution**:
- Increase speed_multiplier
- Reduce stage duration_minutes
- Use create_fast_config() variant

## Extensions and Enhancements

### Possible Future Enhancements

- [ ] Add Scenario 09: Parallel SDLC pipelines
- [ ] Add Scenario 11: SDLC with resource constraints
- [ ] Add Scenario 13: SDLC with cascading failures
- [ ] YAML-based scenario configuration
- [ ] Visual timeline generator (HTML report)
- [ ] Performance profiling and bottleneck detection
- [ ] Fuzzing support for robustness testing
- [ ] Integration with CI/CD metrics
- [ ] Snapshot testing for event streams

## Related Documentation

- [Phase 3 Design Document](../../documentation/01_design/phase_3_sdlc_pipeline_testing.md)
- [Simulation Testing Framework](../README.md)
- [Scenario Format Specification](../SCENARIO_FORMAT.md)
- [Domain Events Catalog](../../documentation/01_design/events/)

## Quick Reference

### File Locations

- **Scenarios**: `/workspace/tests/simulation/scenarios/scenario_*.py`
- **Tests**: `/workspace/tests/simulation/test_scenarios.py`
- **Helpers**: `/workspace/tests/simulation/helpers.py`
- **Design Doc**: `/workspace/documentation/01_design/phase_3_sdlc_pipeline_testing.md`

### Commands

```bash
# Run all Phase 3 tests
pytest tests/simulation/test_scenarios.py -k "phase3" -v

# Run single scenario
pytest tests/simulation/test_scenarios.py::test_scenario_06_happy_path_full_sdlc -v

# Run with diagnostics
pytest tests/simulation/test_scenarios.py -k "phase3" -v -s

# Run with coverage
pytest tests/simulation/test_scenarios.py -k "phase3" --cov=src/codetoreum

# Run performance validation
pytest tests/simulation/test_scenarios.py::test_all_scenarios_meet_performance_target -v
```

---

## Support and Questions

For questions or issues:
1. Check this README and related documentation
2. Review scenario implementations
3. Use `print_event_timeline()` for debugging
4. Consult design documentation

---

**Last Updated**: 2025-02-03
**Phase 3 Status**: IMPLEMENTATION COMPLETE
