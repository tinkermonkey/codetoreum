# Phase 3 SDLC Pipeline Test Execution Guide

## Test Coverage Summary

Phase 3 implements 4 core SDLC pipeline test scenarios with comprehensive edge case coverage:

### Scenario 06: Happy Path Full SDLC
- **Purpose**: Complete SDLC workflow from requirements through deployment
- **Duration**: ~30 min simulated (18s real @ 100x)
- **Key Tests**: 6 stages, all successful, no failures or escalations
- **File**: `scenarios/scenario_06_happy_path_full_sdlc.py`
- **Test**: `test_scenario_06_happy_path_full_sdlc()`

### Scenario 08a: SDLC with Code Review Feedback
- **Purpose**: Code review rejection and developer revision
- **Duration**: ~45 min simulated (27s real @ 100x)
- **Key Tests**: 1 rejection, 1 approval, successful completion
- **File**: `scenarios/scenario_08a_sdlc_review_feedback.py`
- **Test**: `test_scenario_08a_sdlc_review_feedback()`

### Scenario 08b: SDLC with Test Failures and Repair
- **Purpose**: Test failures triggering developer repairs
- **Duration**: ~50 min simulated (30s real @ 100x)
- **Key Tests**: 3 failures detected, repair cycle, all tests pass
- **File**: `scenarios/scenario_08b_sdlc_test_failures_repair.py`
- **Test**: `test_scenario_08b_sdlc_test_failures_repair()`

### Scenario 08c: SDLC with Escalation
- **Purpose**: Implementation escalation requiring human feedback
- **Duration**: ~55 min simulated (33s real @ 100x)
- **Key Tests**: Escalation triggered, human feedback received, resumed
- **File**: `scenarios/scenario_08c_sdlc_escalation.py`
- **Test**: `test_scenario_08c_sdlc_escalation()`

## Running Tests

### Quick Start

```bash
# Run all Phase 3 tests
pytest tests/simulation/test_scenarios.py -k "phase3" -v

# Total expected time: ~2 minutes
# All scenarios should pass with speed multiplier ≥ 100x
```

### Detailed Execution

```bash
# Run with output/diagnostics
pytest tests/simulation/test_scenarios.py -k "phase3" -v -s

# Run with coverage
pytest tests/simulation/test_scenarios.py -k "phase3" \
  --cov=src/codetoreum \
  --cov-report=term-missing

# Run with JUnit XML output
pytest tests/simulation/test_scenarios.py -k "phase3" \
  --junitxml=test-results.xml \
  -v
```

### Individual Scenario Tests

```bash
# Scenario 06: Happy Path
pytest tests/simulation/test_scenarios.py::test_scenario_06_happy_path_full_sdlc -v

# Scenario 08a: Review Feedback
pytest tests/simulation/test_scenarios.py::test_scenario_08a_sdlc_review_feedback -v

# Scenario 08b: Test Failures
pytest tests/simulation/test_scenarios.py::test_scenario_08b_sdlc_test_failures_repair -v

# Scenario 08c: Escalation
pytest tests/simulation/test_scenarios.py::test_scenario_08c_sdlc_escalation -v
```

## Edge Cases Covered

### Scenario 06 (Happy Path)
- Empty work item transition verification ✓
- Clean state between stages ✓
- Event ordering verification ✓
- Artifact generation ✓

### Scenario 08a (Review Feedback)
- Review rejection handling ✓
- Automatic retry with modified code ✓
- Multiple review cycles ✓
- State persistence across revision ✓
- Event sequencing with rejections ✓
- Comment/feedback threading ✓

### Scenario 08b (Test Failures)
- Test failure detection ✓
- Repair cycle triggering ✓
- Code fixes and re-validation ✓
- Failure state tracking ✓
- Multiple test run cycles ✓
- Artifact updates during repair ✓
- Time tracking across repair ✓

### Scenario 08c (Escalation)
- Escalation triggering logic ✓
- Human feedback queueing ✓
- Escalation resolution and resumption ✓
- State preservation during escalation ✓
- Time accounting during delay ✓
- Multiple escalation scenarios ✓

## Expected Outcomes

### All Tests Should Pass

```
test_scenario_06_happy_path_full_sdlc PASSED                    [  25%]
test_scenario_08a_sdlc_review_feedback PASSED                    [  50%]
test_scenario_08b_sdlc_test_failures_repair PASSED               [  75%]
test_scenario_08c_sdlc_escalation PASSED                         [ 100%]

======================== 4 passed in ~2m ========================
```

### Performance Metrics

| Scenario | Expected | Achieved | Status |
|----------|----------|----------|--------|
| 06: Happy Path | 100x | ✓ | ✓ PASS |
| 08a: Review | 100x | ✓ | ✓ PASS |
| 08b: Test Failures | 100x | ✓ | ✓ PASS |
| 08c: Escalation | 100x | ✓ | ✓ PASS |

### Event Capture

| Scenario | Expected | Status |
|----------|----------|--------|
| 06: Happy Path | 30+ | ✓ PASS |
| 08a: Review | 40+ | ✓ PASS |
| 08b: Test Failures | 45+ | ✓ PASS |
| 08c: Escalation | 50+ | ✓ PASS |

## Diagnostic Output

When running tests with `-s` flag, you'll see event timelines:

```
===== Event Timeline =====
  0.0s  WorkflowStarted
  5.2s  StageStarted (Requirements Analysis)
  5.4s  AgentExecutionStarted (requirements-analyst)
 10.6s  AgentExecutionCompleted (requirements-analyst)
 10.7s  StageCompleted (Requirements Analysis)
 11.0s  StageStarted (Architecture & Design)
  ...
 30.0s  WorkflowCompleted
```

## Integration with CI/CD

### GitHub Actions

```yaml
- name: Phase 3 SDLC Tests
  run: |
    pytest tests/simulation/test_scenarios.py -k "phase3" \
      -v --tb=short \
      --junitxml=test-results.xml \
      --cov=src/codetoreum \
      --cov-report=xml
  timeout-minutes: 5

- name: Upload Results
  if: always()
  uses: actions/upload-artifact@v2
  with:
    name: phase-3-test-results
    path: test-results.xml
```

### GitLab CI

```yaml
phase-3-tests:
  script:
    - pytest tests/simulation/test_scenarios.py -k "phase3"
        -v --tb=short --junitxml=test-results.xml
  timeout: 5 minutes
  artifacts:
    reports:
      junit: test-results.xml
```

## Troubleshooting

### All Tests Timeout

**Solution**: Increase simulation speed multiplier or reduce stage durations

```python
config = SimulationConfig.create_fast_config(
    scenario_name="scenario_name",
    speed_multiplier=200.0,  # Increase from 100.0
)
```

### Specific Test Fails

**Solution**: Run with diagnostics to see event timeline

```bash
pytest tests/simulation/test_scenarios.py::test_scenario_06_happy_path_full_sdlc -v -s
```

### Memory Issues with Long Simulations

**Solution**: Reduce the number of events captured

```python
config.max_events_to_capture = 1000
```

## Next Steps

### Phase 3 Complete ✓

- ✓ 4 core test scenarios implemented
- ✓ Comprehensive edge case coverage
- ✓ Performance validation (100x speedup)
- ✓ Integration tests passing
- ✓ Documentation complete

### Phase 4 Considerations

- [ ] Additional workflow patterns (e.g., parallel workflows)
- [ ] Stress testing with many work items
- [ ] Performance optimization opportunities
- [ ] Integration with real adapters

## Documentation

- **Design Document**: `/workspace/documentation/01_design/phase_3_sdlc_pipeline_testing.md`
- **Phase 3 README**: `/workspace/tests/simulation/PHASE_3_README.md`
- **Scenario Format**: `/workspace/tests/simulation/SCENARIO_FORMAT.md`
- **Simulation Framework**: `/workspace/tests/simulation/README.md`

---

**Status**: Phase 3 Implementation Complete
**Last Updated**: 2025-02-03
