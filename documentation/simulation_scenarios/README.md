# Simulation Scenarios Documentation

This directory contains comprehensive documentation for all Codetoreum simulation scenarios, which validate the platform's workflow execution, event handling, and performance characteristics.

## Overview

Simulation scenarios are deterministic, fully-mocked test suites that execute complete workflows without external dependencies. They enable fast, reliable validation of the entire system before production deployment.

**Key Benefits**:
- ✅ No external service dependencies
- ✅ Deterministic execution (repeatable results)
- ✅ 100x speed multiplier (100 seconds simulated = 1 second real-time)
- ✅ Complete event audit trail
- ✅ State persistence and recovery

---

## Scenario 06: Full SDLC Pipeline

**Status**: ✅ Complete and Fully Validated
**Documentation**: [SCENARIO_06_DOCUMENTATION.md](SCENARIO_06_DOCUMENTATION.md)
**Performance Report**: [SCENARIO_06_PERFORMANCE_ANALYSIS.md](SCENARIO_06_PERFORMANCE_ANALYSIS.md)

### Overview

Scenario 06 validates the complete Software Development Lifecycle pipeline from code review through testing and repair cycles. This is the most comprehensive scenario, testing:

- **Code Review Workflow**: Multiple iterations, feedback loops, escalations
- **Human Feedback Integration**: Escalation to human, feedback processing
- **State Recovery**: Persistence and recovery from orchestrator restart
- **Repair Cycle Integration**: Testing and repair automation
- **End-to-End SDLC**: Complete workflow from Development → Review → Testing → Staged

### Test Suites

#### Part 1: Review Cycle Pipeline
- **File**: `tests/simulation/scenarios/scenario_06_sdlc_pipeline.py`
- **Test Cases**: 8 comprehensive scenarios
- **Duration**: ~10.5 seconds real-time
- **Coverage**: Happy path, multiple revisions, escalations, max iterations, edge cases

#### Part 2: Full Pipeline with Repair
- **File**: `tests/simulation/scenarios/scenario_06_sdlc_pipeline_with_repair.py`
- **Test Cases**: 5 comprehensive scenarios
- **Duration**: ~0.9 seconds real-time
- **Coverage**: End-to-end workflows, test failures, recovery, bootstrap integration

### Performance Results

```
✅ Review Cycle:      10.51s (target: <15s, margin: 4.49s / 30%)
✅ Repair Cycle:       0.90s (target: <10s, margin: 9.1s / 91%)
✅ Combined:          11.41s (target: <25s, margin: 13.59s / 54%)
✅ Simulated Time:  1,140s (19 minutes of workflow)
```

### Test Execution

**Full Suite**:
```bash
pytest tests/simulation/scenarios/scenario_06_sdlc_pipeline.py \
        tests/simulation/scenarios/scenario_06_sdlc_pipeline_with_repair.py \
        -v
```

**Review Only**:
```bash
pytest tests/simulation/scenarios/scenario_06_sdlc_pipeline.py -v
```

**Repair Only**:
```bash
pytest tests/simulation/scenarios/scenario_06_sdlc_pipeline_with_repair.py -v
```

### Expected Results

```
13 tests, all PASSED
├── 8 Review Cycle Tests ✅
└── 5 Repair Cycle Tests ✅

Execution Time: ~47.95 seconds total (with pytest overhead)
Real-Time Performance: 11.41 seconds
```

---

## Scenario Documentation Structure

Each scenario has the following documentation structure:

### 1. Main Scenario Documentation
- **Overview**: High-level description
- **Architecture**: Component interactions
- **Test Cases**: Detailed scenario descriptions
- **Validation**: What's being tested and why
- **Coverage Analysis**: Feature and line coverage
- **Execution Instructions**: How to run the tests

### 2. Performance Analysis
- **Performance Results**: Real-time execution times
- **Scaling Profile**: How performance scales
- **Resource Utilization**: Memory, CPU, I/O usage
- **Bottleneck Analysis**: Identified limitations
- **Target Achievement**: vs. performance targets
- **Recommendations**: For production deployment

### 3. Implementation Details
- **Adapters Used**: Mock vs. production adapters
- **Event Processing**: Event types and flows
- **Clock Synchronization**: Time manipulation
- **State Management**: Persistence and recovery

---

## Key Concepts

### Simulation Clock

The `SimulationClock` provides time manipulation at variable speeds:

```python
# 100x speed multiplier: 100 seconds simulated = 1 second real-time
clock = SimulationClock(speed_multiplier=100.0)
```

**Benefits**:
- ✅ Execute workflows in real-time proportional to simulated duration
- ✅ Validate behavior that would normally require hours
- ✅ Deterministic execution with time control

### Mock Adapters

Scenario 06 uses fully-mocked adapters for all external interactions:

#### MockReviewCycleAdapter
- Deterministic review sequences (APPROVE, REQUEST_CHANGES, ESCALATE)
- Configurable iteration limits
- Human feedback queue simulation
- Complete event logging

#### MockRepairCycleAdapter
- Configurable test failures and successes
- Multiple test types (UNIT, INTEGRATION, E2E)
- Iteration tracking
- Recovery from failures

### Event-Driven Validation

All scenarios validate the event-driven architecture:

```python
# Events emitted for all state changes
events = review_adapter.get_all_events_log()

# Verify event types
assert any(e["type"] == "REVIEW_CYCLE_STARTED" for e in events)
assert any(e["type"] == "REVIEW_CYCLE_COMPLETED" for e in events)
assert any(e["type"] == "REVIEW_CYCLE_HUMAN_FEEDBACK_RECEIVED" for e in events)
```

---

## Performance Targets

### Review Cycle

- **Target**: <15.0 seconds real-time
- **Includes**: 4 scenarios with 1-5 iterations
- **Actual**: 10.51 seconds (4.49s under target)

### Repair Cycle

- **Target**: <10.0 seconds real-time
- **Includes**: Full SDLC workflow (review + 2-3 test types)
- **Actual**: 0.90 seconds (9.1s under target)

### Combined

- **Target**: <25.0 seconds real-time
- **Includes**: Both review and repair suites
- **Actual**: 11.41 seconds (13.59s under target)

---

## Test Case Categories

### Happy Path Tests
- First approval with no revisions
- All tests passing on first attempt
- Validates baseline functionality

### Iterative Feedback Tests
- Multiple revisions requested
- Tests failing and passing after fixes
- Validates feedback loop handling

### Escalation Tests
- Human escalation triggered
- Blocking issues requiring human input
- Multiple sequential escalations
- Validates escalation workflow

### Edge Cases
- Approved after human feedback without code changes
- Resume after orchestrator restart
- Max iterations reached
- Persistent test failures

### Performance Tests
- Multiple scenarios executed sequentially
- Total execution time measured
- Validates performance targets

---

## Integration with CI/CD

### GitHub Actions
```yaml
- name: Run Scenario 06 Tests
  run: |
    pytest tests/simulation/scenarios/scenario_06_*.py \
            -v --tb=short
```

### Pre-deployment Checklist
- ✅ All tests pass
- ✅ Performance targets met
- ✅ Coverage at expected levels
- ✅ No external API calls
- ✅ Event audit trail complete

---

## Monitoring and Alerting

### Production Metrics

Track these metrics in production:

1. **Review Cycle Time**
   - Healthy Range: 2-5 seconds
   - Alert if > 30 seconds

2. **Repair Cycle Time**
   - Healthy Range: 1-3 seconds
   - Alert if > 10 seconds

3. **Escalation Rate**
   - Healthy Range: <10%
   - Alert if > 25%

4. **Test Success Rate**
   - Healthy Range: >95%
   - Alert if < 90%

---

## Known Limitations

### Simulation Abstractions

1. **Timing Precision**: ±10% variance in simulated times
2. **Agent Behavior**: Deterministic mock responses (not stochastic)
3. **External Services**: Complete abstraction (GitHub, Docker, etc.)
4. **Parallel Execution**: Tests run serially in simulation

### Test Environment

1. **Single Project**: All tests use same project context
2. **Synthetic Data**: No production data used
3. **Linear Scaling**: Assumes linear performance with work items
4. **No Concurrency**: Doesn't test concurrent workflows

---

## Related Documentation

- **Simulation Architecture**: [Simulation Mode Architecture](../simulation_mode_architecture.md)
- **Event Handling**: [Event Handler Usage Guide](../claude_thoughts/EVENT_HANDLER_USAGE_GUIDE.md)
- **Bootstrap Integration**: [Orchestrator Startup Integration](../implementation/orchestrator_startup_integration.md)
- **Domain Events**: [Domain Events Design](../01_design/events/domain_events_design.md)

---

## Version History

### Version 1.0 (February 3, 2026)
- ✅ Scenario 06 documentation complete
- ✅ Performance validation report
- ✅ All test cases passing
- ✅ Performance targets exceeded

---

## Support

### Running Tests Locally

```bash
# Install dependencies
pip install -e .

# Run specific test
pytest tests/simulation/scenarios/scenario_06_sdlc_pipeline.py -v

# Run with coverage
pytest tests/simulation/scenarios/scenario_06_*.py --cov=codetoreum

# Run with detailed output
pytest tests/simulation/scenarios/scenario_06_*.py -vv -s
```

### Debugging Tests

```bash
# Run with asyncio debug
pytest tests/simulation/scenarios/scenario_06_*.py -v --asyncio-mode=auto

# Run single test with verbose output
pytest tests/simulation/scenarios/scenario_06_sdlc_pipeline.py::TestScenario06SDLCPipeline::test_scenario_01_happy_path_first_approval -vv -s
```

---

**Last Updated**: February 3, 2026
**Maintainer**: Senior Software Engineer
**Status**: ✅ Production Ready
