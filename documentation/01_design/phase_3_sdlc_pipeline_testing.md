# Phase 3: SDLC Pipeline Testing - 4 Core Scenarios and Edge Cases

## Overview

Phase 3 implements comprehensive end-to-end testing of the complete Software Development Lifecycle (SDLC) pipeline with 4 core test scenarios covering the major workflow patterns and extensive edge case coverage.

## SDLC Pipeline Architecture

The complete SDLC pipeline consists of sequential stages:

1. **Requirements Analysis** → Requirements agent analyzes and clarifies requirements
2. **Architecture/Design** → Architecture agent designs the solution
3. **Implementation** → Developer agent implements the solution
4. **Code Review** → Code reviewer validates implementation quality
5. **Testing & QA** → Test agent validates functionality
6. **Deployment** (optional) → Deployment agent handles release

### Stage Outputs
- **Requirements**: Analysis document, acceptance criteria
- **Architecture**: Design document, component diagrams
- **Implementation**: Code implementation, documentation
- **Code Review**: Review feedback, approval/rejection
- **Testing**: Test report, coverage metrics, pass/fail status
- **Deployment**: Deployment status, release notes

## 4 Core Test Scenarios

### Scenario 06: Happy Path Full SDLC
**Purpose**: Complete workflow from requirements through deployment with all stages succeeding

**Description**:
- Single work item (`ISSUE-300`) progresses through all 6 SDLC stages
- All agents complete successfully in sequence
- No rejections, failures, or escalations
- Demonstrates deterministic happy path execution

**Flow**:
```
Requirements → Architecture → Implementation → Code Review → Testing → Deployment ✓
(All succeed)
```

**Agents Involved**:
1. Requirements Analyst - Analyzes requirements, produces analysis document
2. Architect - Designs solution, produces architecture document
3. Developer - Implements features, produces code
4. Code Reviewer - Validates code quality, approves
5. Test Engineer - Validates functionality, approves
6. DevOps Engineer - Deploys to production

**Expected Duration**: ~30 minutes simulated time (18 seconds real time at 100x speed)

**Assertions**:
- ✓ All 6 stages execute in sequence
- ✓ 6 agent executions complete successfully
- ✓ Workflow completes with status COMPLETED
- ✓ All artifacts are generated (documents, code, tests, deployment logs)
- ✓ No failures, rejections, or retries
- ✓ Timeline shows linear progression with minimal time gaps
- ✓ Metrics record correct stage durations

**Edge Cases Tested**:
- Empty pipeline before start
- Proper state transitions between stages
- Event ordering across all stages
- Artifact generation from each stage

---

### Scenario 08a: SDLC with Code Review Feedback and Revisions
**Purpose**: Full SDLC pipeline with code review rejection requiring developer revision

**Description**:
- Work item (`ISSUE-301`) progresses through requirements, architecture, and implementation
- Code review stage rejects the implementation (first attempt)
- Developer revises the code and resubmits (second attempt)
- Code review approves the revised code
- Pipeline continues to testing and deployment

**Flow**:
```
Requirements → Architecture → Implementation →
    Code Review (REJECTED) ↓
         Developer Revision
             ↓
    Code Review (APPROVED) → Testing → Deployment ✓
```

**Agents Involved**:
- Same 6 agents as Scenario 06
- Developer appears twice (initial implementation + revision)
- Code Reviewer appears twice (rejection + approval)

**Expected Duration**: ~45 minutes simulated time (27 seconds real time at 100x speed)

**Assertions**:
- ✓ Code review rejection event emitted
- ✓ Developer revision triggered automatically
- ✓ Revised code submitted for re-review
- ✓ Code review approval after revision
- ✓ Pipeline continues to testing after approval
- ✓ Final workflow status is COMPLETED
- ✓ 2 code review attempts recorded
- ✓ Revision feedback is captured in comments

**Edge Cases Tested**:
- Review rejection handling
- Automatic retry with modified code
- Multiple review cycles
- State persistence across revision
- Event sequencing with rejections
- Comment/feedback threading between agents

---

### Scenario 08b: SDLC with Test Failures and Repair Cycle
**Purpose**: Full SDLC with test failures during QA that require developer fixes

**Description**:
- Work item (`ISSUE-302`) completes requirements through code review successfully
- Testing stage discovers 3 failed tests (first test run)
- Developer fixes the issues in the code
- Testing stage re-runs tests and validates all tests pass
- Pipeline completes with deployment

**Flow**:
```
Requirements → Architecture → Implementation → Code Review (✓) →
    Testing (FAILED: 3 failures) ↓
         Developer Repair
             ↓
    Testing (PASSED: all tests) → Deployment ✓
```

**Agents Involved**:
- Same 6 agents as Scenario 06
- Test Engineer appears twice (initial run with failures + validation run)
- Developer appears twice (implementation + repair)

**Expected Duration**: ~50 minutes simulated time (30 seconds real time at 100x speed)

**Assertions**:
- ✓ Testing stage reports failures (3 failed tests)
- ✓ Repair cycle triggered with specific failure information
- ✓ Developer modifies code to fix failures
- ✓ Testing stage re-runs with all tests passing
- ✓ Pipeline continues to deployment after fix
- ✓ Final workflow status is COMPLETED
- ✓ Repair metrics captured (failures → fixes → success)
- ✓ Test reports include before/after comparison

**Edge Cases Tested**:
- Test failure detection and reporting
- Repair cycle triggering
- Code fixes and re-validation
- Failure state tracking
- Multiple test run cycles
- Artifact updates during repair
- Time tracking across repair cycles

---

### Scenario 08c: SDLC with Escalation and Human Feedback
**Purpose**: Full SDLC with escalation during review requiring human feedback

**Description**:
- Work item (`ISSUE-303`) completes requirements and architecture successfully
- Implementation stage encounters complexity requiring clarification
- Escalation to human (product owner) for requirements clarification
- Human provides feedback and decision
- Developer continues implementation based on feedback
- Pipeline resumes through code review, testing, and deployment

**Flow**:
```
Requirements → Architecture →
    Implementation (ESCALATED - needs clarification) ↓
         Human Feedback Collection
             ↓
         Decision: Use Option A
             ↓
    Implementation (resumed) → Code Review → Testing → Deployment ✓
```

**Agents Involved**:
- Requirements Analyst, Architect, Developer (multiple times)
- Code Reviewer, Test Engineer, DevOps Engineer
- Human (product owner) for feedback

**Expected Duration**: ~55 minutes simulated time (33 seconds real time at 100x speed)

**Assertions**:
- ✓ Implementation escalates with specific question/issue
- ✓ Escalation event includes context for human decision
- ✓ Human feedback is captured and queued
- ✓ Developer receives and acknowledges feedback
- ✓ Implementation resumes with updated requirements
- ✓ Downstream stages execute normally after resumption
- ✓ Final workflow status is COMPLETED
- ✓ Timeline shows escalation wait time
- ✓ Feedback is recorded in work item comments

**Edge Cases Tested**:
- Escalation triggering logic
- Human feedback queueing
- Escalation resolution and resumption
- State preservation during escalation wait
- Time accounting during escalation delay
- Multiple escalation scenarios
- Escalation within escalation (nested)

---

## Edge Case Testing Coverage

### Common Edge Cases (All Scenarios)

#### 1. Time Advancement
- Proper clock advancement during execution
- Correct duration tracking across agents
- Time gap detection between stages
- Stage timeout handling

#### 2. Event Ordering
- Events emitted in correct sequence despite async operations
- No out-of-order stage transitions
- Complete event trail for each work item
- Event aggregation across multiple agents

#### 3. Concurrent Operations
- Multiple work items in pipeline simultaneously
- Resource allocation fairness
- Queue management and ordering
- Agent availability detection

#### 4. State Persistence
- Work item state survives failures
- Stage history preserved across restarts
- Agent outputs persisted
- Metadata maintained through pipeline

#### 5. Failure Scenarios
- Agent timeout during stage execution
- Network failures between adapters
- Container failures and recovery
- Partial stage completion

#### 6. Data Validation
- Artifact generation and format validation
- Comments and feedback capture
- Metrics accuracy
- Event payload validation

#### 7. Metrics and Observability
- Stage duration accuracy
- Agent execution time
- Retry attempt counting
- Success/failure rate tracking

#### 8. WebSocket Streaming
- Real-time event delivery
- Subscription filtering
- Connection stability through long workflows
- Event batching and buffering

### Scenario-Specific Edge Cases

#### Scenario 06 (Happy Path)
- Empty work item transition verification
- Clean state between stages
- No false failures or escalations
- Deterministic timing

#### Scenario 08a (Code Review with Revisions)
- Multiple review cycles without infinite loops
- Feedback correlation between review attempts
- Revision metadata tracking
- Code diff generation

#### Scenario 08b (Test Failures and Repair)
- Failure classification (compilation vs. runtime vs. assertion)
- Partial test suite execution
- Test output parsing and analysis
- Coverage change detection

#### Scenario 08c (Escalation)
- Escalation reason capture
- Human feedback queuing with TTL
- Escalation timeout handling
- Feedback expiry and default actions

---

## Test Implementation Guidelines

### Configuration Setup Pattern
```python
def create_config() -> SimulationConfig:
    config = SimulationConfig.create_fast_config(
        scenario_name="scenario_name",
        speed_multiplier=100.0,
    )

    # Configure each agent with realistic responses
    config.add_agent_response_pattern(
        agent_id="agent-id",
        pattern=r".*",  # Matching pattern
        response="Agent response output"
    )

    # Configure container results for test execution
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
    """Execute scenario logic."""
    # Stage 1
    runner.assert_event_occurred("Stage1Started")
    await runner.advance_time(timedelta(minutes=5))
    runner.assert_event_occurred("Stage1Completed")

    # Stage 2
    runner.assert_event_occurred("Stage2Started")
    await runner.advance_time(timedelta(minutes=5))
    runner.assert_event_occurred("Stage2Completed")

    # Final assertions
    runner.assert_equal(
        len(runner.get_events_by_type("WorkflowCompleted")),
        1,
        "workflow_completion"
    )
```

### Test Registration Pattern
```python
@pytest.mark.simulation
@pytest.mark.scenario
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

---

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Scenario 06 Duration | < 20s real time | 30 min simulated @ 100x |
| Scenario 08a Duration | < 30s real time | 45 min simulated @ 100x |
| Scenario 08b Duration | < 35s real time | 50 min simulated @ 100x |
| Scenario 08c Duration | < 40s real time | 55 min simulated @ 100x |
| Speed Multiplier | ≥ 10x | Minimum acceptable speedup |
| Events Captured | 100% | All domain events recorded |
| Determinism | 100% | Same config → same results |
| Assertion Pass Rate | 100% | No test flakiness |

---

## Metrics and Observability

### Events Tracked Per Scenario

#### Scenario 06 (Happy Path)
- WorkflowStarted
- StageStarted (6 times)
- AgentExecutionStarted (6 times)
- AgentExecutionCompleted (6 times)
- StageCompleted (6 times)
- WorkflowCompleted
- ArtifactGenerated (6 times)
- MetricsRecorded

#### Scenario 08a (Code Review with Revisions)
- All Scenario 06 events plus:
- ReviewRejected
- DeveloperRevisionStarted
- StageRestarted
- ReviewApproved
- RetryScheduled

#### Scenario 08b (Test Failures and Repair)
- All Scenario 06 events plus:
- TestExecutionStarted
- TestFailed (3x)
- RepairCycleStarted
- DeveloperRepairStarted
- TestExecutionRestarted
- TestSucceeded

#### Scenario 08c (Escalation)
- All Scenario 06 events plus:
- EscalationTriggered
- HumanFeedbackRequested
- HumanFeedbackReceived
- PipelineResumed
- EscalationResolved

### Metrics Recorded
- Stage duration (min, max, avg)
- Agent execution time
- Retry count per stage
- Escalation wait time
- Test coverage percentage
- Code review feedback count

---

## Related Documentation

- [Simulation Testing Framework](../infrastructure/simulation_design.md)
- [Domain Events Catalog](../events/events_design.md)
- [SDLC Pipeline Workflow](../domains/workflow_design.md)
- [Application Services](../application_services/orchestration_design.md)

---

## Implementation Status

- [ ] Scenario 06: Happy Path Full SDLC
- [ ] Scenario 08a: Code Review with Revisions
- [ ] Scenario 08b: Test Failures and Repair
- [ ] Scenario 08c: Escalation and Human Feedback
- [ ] Edge case test suite
- [ ] Performance validation
- [ ] Documentation completion

---

## Next Steps

1. Implement 4 core scenarios in Python
2. Create comprehensive edge case test suite
3. Validate all assertions pass
4. Measure performance against targets
5. Integrate into CI/CD pipeline
6. Document lessons learned

