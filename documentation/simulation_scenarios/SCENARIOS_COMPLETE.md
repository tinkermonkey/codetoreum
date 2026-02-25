# Complete Simulation Scenarios Reference

**Current Status**: 13 scenarios implemented, all documented

## Overview

This document provides complete specifications for all simulation scenarios. Each scenario tests a specific workflow behavior or system capability using fast, deterministic testing.

## Quick Reference

| # | Name | Focus | Simulated Time | Real Time | Status |
|---|------|-------|---|---|---|
| 01 | Simple Workflow | Basic 3-stage execution | 16 min | ~10s | ✅ Complete |
| 02 | Parallel Executions | Multi-item concurrency | 15 min | ~9s | ✅ Complete |
| 03 | Review Cycle | Maker-checker loop | 16 min | ~10s | ✅ Complete |
| 04 | Execution Failure | Error handling & retry | 11 min | ~7s | ✅ Complete |
| 05 | Complex Workflow | Multi-stage with branches | 28 min | ~17s | ✅ Complete |
| 06 | SDLC Pipeline | Full lifecycle workflow | 45 min | ~27s | ✅ Complete |
| 06b | SDLC + Repair | SDLC with test failures | 60 min | ~36s | ✅ Complete |
| 07 | Repair Cycle | Test-fix-validate loop | 20 min | ~12s | ✅ Complete |
| 09 | Queue Position | Priority queue ordering | 10 min | ~6s | ✅ Complete |
| 10 | Agent Execution | Agent context & output | 12 min | ~7s | ✅ Complete |
| 10b | Conversational | Multi-turn agent dialogue | 15 min | ~9s | ✅ Complete |
| 12 | Container Recovery | Failure recovery | 18 min | ~11s | ✅ Complete |
| 13 | Multi-Project | Multi-project orchestration | 10 min | ~5s | ✅ Complete |

---

## Scenario Details

### Scenario 01: Simple Workflow

**File**: `scenario_01_simple_workflow.py`
**Purpose**: Basic test of 3-stage sequential workflow

**What It Tests**:
- ✅ Workflow initialization
- ✅ Sequential stage transitions
- ✅ Agent execution in each stage
- ✅ Event capture (start, progress, completion)
- ✅ Workflow completion detection

**Workflow Stages**:
1. **Analysis** (5 min) - Agent analyzes work item
2. **Implementation** (5 min) - Agent implements solution
3. **Testing** (6 min) - Agent runs tests

**Expected Events**:
```
WorkflowStarted
├── AgentExecutionStarted (Analysis)
├── AgentExecutionCompleted (Analysis)
├── StageTransitioned (→ Implementation)
├── AgentExecutionStarted (Implementation)
├── AgentExecutionCompleted (Implementation)
├── StageTransitioned (→ Testing)
├── AgentExecutionStarted (Testing)
├── AgentExecutionCompleted (Testing)
└── WorkflowCompleted
```

**Metrics**:
- Simulated Duration: ~16 minutes
- Real Duration: ~10 seconds
- Events: 8-10 total
- Agents Invoked: 3 (sequential)

**Assertions to Verify**:
- All 3 stages executed sequentially
- Each stage completed successfully
- Final workflow status is "completed"
- No retries occurred

**Use Case**: Regression testing, smoke test suite

---

### Scenario 02: Parallel Executions

**File**: `scenario_02_parallel_executions.py`
**Purpose**: Multiple work items executing concurrently

**What It Tests**:
- ✅ Concurrent work item processing
- ✅ Resource contention handling
- ✅ Queue management across multiple items
- ✅ Lock acquisition and release
- ✅ Independent execution isolation

**Workflow Setup**:
- 3 concurrent work items in pipeline
- Each item has identical 3-stage workflow
- Stages execute in parallel (simulation time, concurrent real time)
- Shared pipeline lock prevents interference

**Execution Pattern**:
```
Item 1: Analysis ──→ Implementation ──→ Testing ──→ Done
Item 2:  Analysis ──→ Implementation ──→ Testing ──→ Done  (concurrent)
Item 3:   Analysis ──→ Implementation ──→ Testing ──→ Done (concurrent)
```

**Expected Behaviors**:
- All 3 items start nearly simultaneously
- Each maintains independent state
- Pipeline lock prevents step overlap
- Total time ~= single item (due to lock serialization)
- All complete successfully

**Metrics**:
- Simulated Duration: ~15 minutes
- Real Duration: ~9 seconds
- Events: 25-30 total
- Concurrency: 3 items, serialized stages

**Assertions**:
- 3 workflow started events
- 3 workflow completed events
- No lock conflicts detected
- All items completed in order

**Use Case**: Testing concurrent item handling, lock correctness

---

### Scenario 03: Review Cycle

**File**: `scenario_03_review_cycle.py`
**Purpose**: Maker-checker pattern with feedback and revisions

**What It Tests**:
- ✅ Review request creation
- ✅ Review rejection with feedback
- ✅ Revision workflow
- ✅ Re-submission for review
- ✅ Final approval
- ✅ Event sequence for review state changes

**Workflow Stages**:
1. **Code Generation** (5 min) - Agent creates initial code
2. **Code Review** (5 min) - Human/bot reviews, may reject
   - If rejected: Loop back to revision
   - If approved: Proceed
3. **Testing** (6 min) - Agent runs tests

**Review Cycle Pattern**:
```
Submit for Review
    ↓
Review: Changes Requested (feedback: "Add error handling")
    ↓
Revision: Implement feedback (5 min)
    ↓
Re-submit for Review
    ↓
Review: Approved ✓
    ↓
Proceed to Testing
```

**Expected Events**:
```
WorkflowStarted
├── ReviewRequestedEvent
├── ReviewRejectedEvent (with feedback)
├── RevisionStartedEvent
├── RevisionCompletedEvent
├── ReviewRequestedEvent (resubmission)
├── ReviewApprovedEvent
└── WorkflowCompleted
```

**Metrics**:
- Simulated Duration: ~16 minutes
- Real Duration: ~10 seconds
- Review Cycles: 2 (initial + revision)
- Feedback Iterations: 1

**Assertions**:
- Initial review requested
- Review rejected with feedback message
- Revision executed (agent re-ran)
- Resubmitted for review
- Final approval obtained
- Correct event sequence

**Use Case**: QA workflow testing, approval workflows

---

### Scenario 04: Execution Failure

**File**: `scenario_04_execution_failure.py`
**Purpose**: Error handling, retry logic, and failure recovery

**What It Tests**:
- ✅ Agent execution failure detection
- ✅ Automatic retry mechanism
- ✅ Retry count limits
- ✅ Error logging and context
- ✅ Repair cycle triggering
- ✅ Circuit breaker activation

**Failure Injection Pattern**:
```
Attempt 1: Implementation stage fails (timeout)
    ↓ [Wait: exponential backoff]
    ↓
Attempt 2: Implementation stage fails (timeout)
    ↓ [Wait: exponential backoff]
    ↓
Attempt 3: Implementation stage succeeds ✓
    ↓
Continue to Testing
```

**Expected Events**:
```
WorkflowStarted
├── AgentExecutionStarted (Analysis)
├── AgentExecutionCompleted (Analysis)
├── StageTransitioned (→ Implementation)
├── AgentExecutionStarted (Implementation)
├── AgentExecutionFailed (attempt 1)
├── RetryScheduled (backoff: 30s)
├── AgentExecutionStarted (Implementation - retry 1)
├── AgentExecutionFailed (attempt 2)
├── RetryScheduled (backoff: 60s)
├── AgentExecutionStarted (Implementation - retry 2)
├── AgentExecutionCompleted (Implementation) ✓
└── ...continues to completion
```

**Failure Scenarios Covered**:
1. Transient timeout (succeeds on retry)
2. Persistent error (eventually succeeds)
3. Max retries exceeded (circuit breaks, workflow fails)

**Metrics**:
- Simulated Duration: ~11 minutes
- Real Duration: ~7 seconds
- Retry Attempts: 2 successful
- Backoff Strategy: Exponential (30s, 60s, 120s)

**Assertions**:
- Initial attempt logged as failed
- Retry scheduled with correct backoff
- Successful retry logged
- Workflow continues after recovery
- Event sequence shows failure → retry → success

**Use Case**: Resilience testing, failure recovery verification

---

### Scenario 05: Complex Workflow

**File**: `scenario_05_complex_workflow.py`
**Purpose**: Multi-stage with conditional branches and decision points

**What It Tests**:
- ✅ Conditional stage branching
- ✅ Decision gate evaluation
- ✅ Parallel vs. sequential execution
- ✅ Branch convergence/merge
- ✅ Complex event sequences
- ✅ State management across branches

**Workflow Structure**:
```
Analysis (5 min)
    ↓
├─→ [Decision] Is Large Feature? ──→ YES ──→ Design Document (5 min)
│                                      ↓
│                                   Implementation (7 min)
│
└─→ NO ──→ Implementation (5 min)
           ↓
[Merge]
   ↓
Testing (6 min)
   ↓
Complete
```

**Branch Scenarios**:
- **Large Feature Path**: Analysis → Design → Implementation → Testing
  - Additional design phase adds 5 minutes
  - More detailed implementation (7 min instead of 5)
- **Small Feature Path**: Analysis → Implementation → Testing
  - Skips design, faster implementation

**Expected Decision Logic**:
- Decision evaluated after Analysis completes
- Based on feature complexity (e.g., story points > 13)
- Routes to appropriate implementation path

**Metrics**:
- Simulated Duration: ~28 minutes (long path) or ~16 minutes (short path)
- Real Duration: ~17 seconds
- Stages: 4-5 depending on path
- Branch Coverage: Both paths tested

**Assertions**:
- Decision gate evaluated correctly
- Correct branch taken based on input
- Branch execution completed successfully
- All stages in branch executed
- Merge point reached
- Total workflow completed

**Use Case**: Complex workflow testing, branching logic validation

---

### Scenario 06: SDLC Pipeline (Full Lifecycle)

**File**: `scenario_06_sdlc_pipeline.py`
**Purpose**: Complete software development lifecycle workflow

**What It Tests**:
- ✅ Complete SDLC workflow (7 stages)
- ✅ Code generation from requirements
- ✅ Code review approval workflow
- ✅ Unit test execution and validation
- ✅ Integration test validation
- ✅ E2E test validation
- ✅ Release preparation
- ✅ Full end-to-end pipeline coordination

**Workflow Stages** (Sequential):
1. **Requirements** (3 min) - Parse and understand requirements
2. **Design** (5 min) - Create design document
3. **Implementation** (7 min) - Generate code
4. **Code Review** (5 min) - Review approval
5. **Testing** (10 min) - Run UNIT → INTEGRATION → E2E tests
6. **Integration** (5 min) - Merge to main branch
7. **Release** (3 min) - Prepare release notes

**Key Features**:
- All stages execute sequentially
- Repair cycle in Testing stage (test failures trigger retry)
- Code review gate (approval required to continue)
- Test suite with early termination (if UNIT fails, skip INTEGRATION/E2E)
- Final release artifacts generated

**Expected Timeline**:
```
Requirements (3)
    ↓
Design (5)
    ↓
Implementation (7)
    ↓
Code Review (5) [Approval gate]
    ↓
Testing:
  - Unit Tests (3) ✓
  - Integration Tests (3) ✓
  - E2E Tests (4) ✓
    ↓
Integration/Merge (5)
    ↓
Release (3)
────────────
Total: 45 minutes simulated
```

**Critical Path**:
- Code review gate: Can delay pipeline if rejections require revisions
- Testing failures: Trigger repair cycle (test-fix-validate)
- Early termination: If unit tests fail, integration/E2E skipped

**Metrics**:
- Simulated Duration: ~45 minutes
- Real Duration: ~27 seconds
- Stages: 7
- Decision Points: 2 (review approval, test results)
- Events: 30-40

**Assertions**:
- All 7 stages executed in correct order
- Code review requested and approved
- All test types executed (UNIT, INTEGRATION, E2E)
- Tests passed without failures
- Integration completed successfully
- Release stage finalized
- Workflow marked complete

**Documentation**: See `SCENARIO_06_DOCUMENTATION.md` for detailed specification

**Use Case**: Full lifecycle validation, performance baseline, regression testing

---

### Scenario 06b: SDLC with Repair Cycle

**File**: `scenario_06_sdlc_pipeline_with_repair.py`
**Purpose**: SDLC pipeline with test failures triggering repair

**What It Tests**:
- ✅ All SDLC pipeline stages (same as Scenario 06)
- ✅ Test failure detection during Testing stage
- ✅ Repair cycle triggering
- ✅ Test-fix-validate loop
- ✅ Recovery from failures
- ✅ Extended timeline with repairs

**Differences from Scenario 06**:
- **Test Failures**: Some tests fail initially
  - Unit Test: 1 failure in first run
  - Integration Test: Passes (test-fix-validate ran)
  - E2E Test: Passes (test-fix-validate ran)
- **Repair Cycle**: Automatically triggered by test failures
  - Agent attempts fix
  - Re-runs tests
  - Continues until passing or max retries

**Testing Stage Flow**:
```
Testing:
  Unit Tests:
    Run 1: ❌ Failure (assertion error)
    Repair triggered → Agent fixes code
    Run 2: ✓ Passes

  Integration Tests:
    Run 1: ✓ Passes

  E2E Tests:
    Run 1: ✓ Passes
```

**Expected Timeline**:
```
Requirements through Implementation: 15 min (same as 06)

Code Review: 5 min (same as 06)

Testing: 20 min (extended due to repairs)
  - Unit Tests Run 1: 3 min (FAIL)
  - Repair Cycle: 5 min (fix code)
  - Unit Tests Run 2: 3 min (PASS)
  - Integration Tests: 3 min (PASS)
  - E2E Tests: 4 min (PASS)
    → Total Testing: 18 min

Integration/Merge: 5 min (same as 06)

Release: 3 min (same as 06)
────────────
Total: 60 minutes simulated (vs 45 in Scenario 06)
```

**Repair Cycle Details**:
- Triggered when test results show failures
- Agent receives:
  - Test output (assertion failures)
  - Code to fix
  - Previous attempts (for learning)
- Agent provides:
  - Fixed code
  - Explanation of fix
- Loop continues until:
  - Tests pass ✓
  - Max repair attempts exceeded ❌

**Metrics**:
- Simulated Duration: ~60 minutes
- Real Duration: ~36 seconds
- Additional Time vs Scenario 06: +15 minutes
- Repair Cycles: 1 (unit tests)
- Test Failures: 1 (handled and recovered)

**Assertions**:
- All 7 stages executed
- Test failures detected
- Repair cycle triggered for unit tests
- Agent fix applied
- Retests passed
- Pipeline continued to completion
- Final workflow success

**Use Case**: Testing repair mechanisms, failure recovery, extended workflows

---

### Scenario 07: Repair Cycle

**File**: `scenario_07_repair_cycle.py`
**Purpose**: Test-fix-validate repair loop in isolation (not part of SDLC)

**What It Tests**:
- ✅ Isolated repair cycle mechanics
- ✅ Test type sequence (UNIT → INTEGRATION → E2E)
- ✅ Fast-fail behavior (if UNIT fails, skip INTEGRATION/E2E)
- ✅ Iterative fix-and-retest
- ✅ Repair warnings and completion
- ✅ Circuit breaker (max iterations)

**Repair Cycle Stages**:
1. **Unit Tests**: Basic code correctness (3 min per iteration)
2. **Integration Tests**: Module interaction (3 min, only if UNIT passed)
3. **E2E Tests**: End-to-end functionality (4 min, only if UNIT+INTEGRATION passed)

**Example Scenarios**:

**Scenario A: Happy Path (Immediate Success)**
```
UNIT Tests: Run 1 ✓ PASSED
INTEGRATION Tests: Run 1 ✓ PASSED
E2E Tests: Run 1 ✓ PASSED
────────────
Result: SUCCESS (all tests passed)
Time: 10 minutes
```

**Scenario B: Multiple Iterations**
```
UNIT Tests:
  Run 1: ❌ FAILED
  [Repair: Agent fixes code]
  Run 2: ✓ PASSED

INTEGRATION Tests:
  Run 1: ✓ PASSED

E2E Tests:
  Run 1: ✓ PASSED
────────────
Result: SUCCESS (after 1 repair)
Time: 15 minutes
```

**Scenario C: Fast-Fail Behavior**
```
UNIT Tests:
  Run 1: ❌ FAILED
  [Repair: Agent fixes code]
  Run 2: ❌ FAILED (persistent issue)
  Run 3: ❌ FAILED
  [Circuit breaker: max iterations reached]

INTEGRATION Tests: SKIPPED (because UNIT didn't pass)
E2E Tests: SKIPPED (because UNIT didn't pass)
────────────
Result: FAILED (max iterations, UNIT didn't pass)
Time: 9 minutes
```

**Scenario D: Warnings**
```
UNIT Tests: ✓ PASSED
INTEGRATION Tests: ✓ PASSED (with 2 warnings: deprecation)
E2E Tests: ✓ PASSED
────────────
Result: SUCCESS with WARNINGS
Time: 12 minutes (includes review of warnings)
```

**Key Features**:
- **Sequential test types**: UNIT → INTEGRATION → E2E (if all pass)
- **Early termination**: Skip downstream tests if upstream fails
- **Iterative repair**: Loop on failure until success or max attempts
- **Checkpoints**: Save repair state for resume on restart
- **Circuit breaker**: Stop after N failed iterations (e.g., 5)

**Metrics**:
- Simulated Duration: ~20 minutes (varies by scenario)
- Real Duration: ~12 seconds
- Test Types: 3 (UNIT, INTEGRATION, E2E)
- Repair Iterations: 0-5 (varies by scenario)

**Assertions** (verified in each sub-scenario):
- Correct test sequence followed
- Fast-fail behavior respected
- Repair iterations logged
- Circuit breaker activated at limit
- Final status matches expected outcome

**Use Case**: Isolated repair cycle testing, test execution validation

---

### Scenario 09: Queue Position Ordering

**File**: `scenario_09_queue_position_ordering.py`
**Purpose**: Work item queue with board position-based ordering

**What It Tests**:
- ✅ Queue entry creation with board position tracking
- ✅ Position-based queue ordering (lowest position = highest priority)
- ✅ Queue synchronization with board changes
- ✅ Status management (waiting vs. active)
- ✅ Queue reordering when board changes
- ✅ Next item retrieval by position

**Queue Scenario**:
```
Board Layout:
  In Progress
  ├─ item-1 [position: 0] ← highest priority
  ├─ item-2 [position: 1]
  ├─ item-3 [position: 2]
  └─ item-4 [position: 3] ← lowest priority

Pipeline Queue (by position):
  [1] item-1 (position 0)
  [2] item-2 (position 1)
  [3] item-3 (position 2)
  [4] item-4 (position 3)
```

**Operations Tested**:
1. **Add items to queue**: Multiple items added to In Progress column
2. **Verify ordering**: Queue maintained in position order
3. **Reorder on board**: User reorders items on board
4. **Queue updates**: Queue reflects new positions
5. **Dequeue**: Next item retrieved (lowest position)
6. **Requeue**: Item moved to back after processing

**Execution Flow**:
```
Setup:
  Create board with columns [Backlog, In Progress, In Review, Done]

Add items:
  item-1 → In Progress [position: 0]
  item-2 → In Progress [position: 1]
  item-3 → In Progress [position: 2]

Verify:
  Queue order: [item-1, item-2, item-3] ✓

Manual reorder on board:
  User moves item-3 to position 1 (between item-1 and item-2)
  New board order: [item-1, item-3, item-2]

Verify queue update:
  Queue order: [item-1, item-3, item-2] ✓

Dequeue:
  Next item: item-1 [position: 0] ✓

Requeue item-1:
  item-1 moved to back
  Queue order: [item-3, item-2, item-1]
  Next item: item-3 ✓
```

**Key Behaviors**:
- Positions used directly for ordering (no separate priority field)
- Queue automatically syncs when board is modified
- Dequeue returns item with lowest position
- Requeue moves item to back (highest position)

**Metrics**:
- Simulated Duration: ~10 minutes
- Real Duration: ~6 seconds
- Items in queue: 4
- Operations: Add, Verify, Reorder, Dequeue, Requeue

**Assertions**:
- Queue order matches board positions
- Lowest position returned first by dequeue
- Queue syncs after board reorder
- Requeue moves item to back
- All items tracked correctly

**Use Case**: Queue ordering logic validation, FIFO priority queue testing

---

### Scenario 10: Agent Execution

**File**: `scenario_10_agent_execution.py`
**Purpose**: Agent execution with context files and output capture

**What It Tests**:
- ✅ Context file preparation (issue details, code snippets)
- ✅ Agent execution in container
- ✅ Output capture and parsing
- ✅ Error detection and logging
- ✅ Multi-step agent workflows
- ✅ Tool usage and responses

**Execution Flow**:
```
Setup:
  Create work item with description
  Create code files to analyze
  Prepare context directory

Context Files:
  /context/issue.txt           [Work item details]
  /context/code/main.py        [Source code]
  /context/code/tests.py       [Test code]
  /context/previous_stage.txt  [Earlier output]

Agent Execution:
  Agent receives context path
  Agent reads context files
  Agent analyzes and generates output
  Agent writes output to /output/result.txt
  Container returns exit code + stdout

Output Capture:
  Parse agent output
  Extract key results
  Verify success criteria

Event Emission:
  AgentExecutionStarted
  → Agent working...
  → AgentExecutionCompleted (success/failure)
```

**Agent Interaction Pattern**:
```
Orchestrator:
  1. Write context files to /context
  2. Start agent container with:
     - Image: claude-code or mock
     - Mounts: /context (read-only), /output (read-write)
     - Env: WORK_ITEM_ID, STAGE, etc.
  3. Wait for completion
  4. Read /output files
  5. Parse results
  6. Emit completion event

Agent (in container):
  1. Read /context files
  2. Perform work (coding, analysis, etc.)
  3. Write results to /output
  4. Exit with status code (0 = success)
```

**Test Scenarios**:

**Scenario A: Simple Analysis**
```
Context: Source code + requirements
Agent Task: Analyze code for bugs
Output: List of bugs found
Status: Success ✓
Duration: 4 minutes
```

**Scenario B: Code Generation**
```
Context: Requirements + design document
Agent Task: Generate implementation
Output: Generated code file
Status: Success ✓
Duration: 6 minutes
```

**Scenario C: Test Generation**
```
Context: Source code + requirements
Agent Task: Generate unit tests
Output: Test file with test cases
Status: Success ✓
Duration: 5 minutes
```

**Scenario D: Error Handling**
```
Context: Malformed code file
Agent Task: Parse and analyze
Output: Error message
Status: Failure (container exit code 1)
Duration: 2 minutes
Retry: Yes
```

**Metrics**:
- Simulated Duration: ~12 minutes
- Real Duration: ~7 seconds
- Context files: 3-5 files
- Agent invocations: 3-4
- Output files: 1-2 per execution

**Assertions**:
- Context files created with correct paths
- Agent execution started and completed
- Output files present and readable
- Exit code indicates success/failure
- Event timeline shows execution stages
- Output content valid (parseable)

**Use Case**: Agent integration testing, context/output handling validation

---

### Scenario 10b: Conversational Modes

**File**: `scenario_10_conversational_modes.py`
**Purpose**: Multi-turn agent dialogue and iterative refinement

**What It Tests**:
- ✅ Multi-turn conversation between orchestrator and agent
- ✅ State preservation across turns
- ✅ Iterative refinement based on feedback
- ✅ Tool usage and response handling
- ✅ Conversation context management
- ✅ Early termination (goal met)

**Conversation Pattern**:
```
Turn 1: Orchestrator → Agent
  Prompt: "Generate function to sort array"
  Agent: "Here's a quick sort implementation"
  Status: Intermediate (more refinement needed)

Turn 2: Orchestrator → Agent
  Prompt: "Add error handling for empty array"
  Context: [Previous function, error cases]
  Agent: "Updated function with error checks"
  Status: Intermediate (review iteration)

Turn 3: Orchestrator → Agent
  Prompt: "Add docstring and type hints"
  Context: [Previous function with errors]
  Agent: "Final function with documentation"
  Status: Complete ✓

Result: Function fully implemented and documented
Total turns: 3
```

**Turn Mechanics**:
1. **Setup Turn**: Initialize conversation, provide requirements
2. **Iteration Turns**: Provide feedback, refine output
3. **Final Turn**: Verify completion, extract final output

**State Preservation**:
```
Turn 1 Output:
  function sort(arr):
    ...

Turn 2 Input:
  Function from Turn 1 (for context)
  + Feedback: "Add error handling"

Turn 2 Output:
  function sort(arr):
    if not arr:
      raise ValueError("empty array")
    ...

Turn 3 Input:
  Function from Turn 2
  + Feedback: "Add docstring"

Turn 3 Output:
  def sort(arr: List[int]) -> List[int]:
    """Sort array in ascending order.

    Args:
        arr: Input array to sort

    Returns:
        Sorted array

    Raises:
        ValueError: If array is empty
    """
    ...
```

**Conversation Types**:

**Type A: Refinement-Based**
- Turn 1: Generate initial solution
- Turn 2: Add features (error handling, logging, etc.)
- Turn 3: Polish (docs, tests, etc.)

**Type B: Debugging-Based**
- Turn 1: Generate code
- Turn 2: Agent reports error
- Turn 3: Orchestrator provides error output
- Turn 4: Agent fixes bug

**Type C: Exploratory**
- Turn 1: Generate multiple options
- Turn 2: User selects preferred option
- Turn 3: Refine selected option

**Key Behaviors**:
- Conversation context grows with each turn (previous turns included)
- Agent can indicate completion or request clarification
- Early termination when goal satisfied
- Token usage tracked across turns
- Each turn logged for audit trail

**Metrics**:
- Simulated Duration: ~15 minutes
- Real Duration: ~9 seconds
- Conversation Turns: 3-5
- Total Tokens: 5000-10000
- Refinement Iterations: 2-3

**Assertions**:
- Correct number of turns executed
- Context preserved across turns
- Each turn output present
- Final output meets requirements
- Conversation history complete
- Early termination respected if triggered

**Use Case**: Iterative agent workflows, multi-turn refinement testing

---

### Scenario 12: Container Recovery

**File**: `scenario_12_container_recovery.py`
**Purpose**: Handle container failure and recovery

**What It Tests**:
- ✅ Container crash detection
- ✅ Crash analysis and assessment
- ✅ Recovery strategy selection
- ✅ Retry with different configuration
- ✅ Resource cleanup
- ✅ Success after recovery or failure escalation

**Failure Scenarios**:

**Scenario A: OOM (Out of Memory) - Recoverable**
```
Execution Attempt 1:
  Container: Running agent task
  Status: ❌ Killed (OOM)
  Error: "Cannot allocate memory"

Recovery Assessment:
  Cause: Task memory intensive
  Solution: Increase memory limit
  Retry: Yes

Execution Attempt 2:
  Container: Running agent task (memory: 4GB)
  Status: ✓ Success
  Duration: Additional 3 minutes (less efficient)

Result: Recovered and succeeded
```

**Scenario B: Network Timeout - Transient**
```
Execution Attempt 1:
  Container: Running agent task
  Status: ❌ Timeout (network error)
  Error: "Connection lost"

Recovery Assessment:
  Cause: Transient network issue
  Solution: Retry without changes
  Retry: Yes

Execution Attempt 2:
  Container: Running agent task (same config)
  Status: ✓ Success
  Duration: Same as attempt 1

Result: Recovered (transient issue)
```

**Scenario C: Disk Full - Requires Action**
```
Execution Attempt 1:
  Container: Writing output files
  Status: ❌ Failure (disk full)
  Error: "No space left on device"

Recovery Assessment:
  Cause: Persistent disk issue
  Solution: Cannot recover automatically
  Retry: No

Result: Failed, escalated to operator
```

**Recovery Assessment Process**:
```
1. Analyze container logs
2. Identify likely cause
   - OOM → increase memory
   - Timeout → retry with backoff
   - Disk full → manual intervention needed
3. Determine if recoverable
4. If yes: Select new strategy and retry
5. If no: Report failure and escalate
```

**Recovery Strategies**:
- **Resource Increase**: Add CPU, memory, disk
- **Retry with Backoff**: Wait and retry same config
- **Alternative Node**: Try different container host
- **Escalation**: Report for manual intervention

**Metrics**:
- Simulated Duration: ~18 minutes
- Real Duration: ~11 seconds
- Failure Types Tested: 2-3
- Recovery Successes: 1-2
- Manual Escalations: 0-1

**Assertions**:
- Crash detected and logged
- Recovery assessment performed
- Appropriate strategy selected
- Retry executed for recoverable failures
- Final status correct (success or escalated)
- Resource cleanup completed

**Use Case**: Failure recovery testing, reliability validation

---

### Scenario 13: Multi-Project Orchestration

**File**: `scenario_13_multi_project.py`
**Purpose**: Multi-project orchestration within single orchestration cycle

**What It Tests**:
- ✅ Multi-project configuration loading and reloading
- ✅ Repository cloning for multiple projects
- ✅ Per-project workflow orchestration delegation
- ✅ Work item processing across multiple projects
- ✅ Project isolation (no cross-project contamination)
- ✅ Aggregated orchestration cycle metrics
- ✅ Event emission for observability

**Scenario Setup**:
Three independent projects processed in single orchestration cycle:

1. **api-service** (Backend)
   - Repository: `https://github.com/acme/api-service.git`
   - Branch: `main`
   - Board: `backend-pipeline`
   - Work Items: 5
   - Agents: code-generator, code-reviewer, test-runner

2. **web-app** (Frontend)
   - Repository: `https://github.com/acme/web-app.git`
   - Branch: `develop`
   - Board: `frontend-pipeline`
   - Work Items: 7
   - Agents: ui-generator, qa-tester

3. **data-service** (Data/Analytics)
   - Repository: `https://github.com/acme/data-service.git`
   - Branch: `main`
   - Board: `data-pipeline`
   - Work Items: 6
   - Agents: data-engineer, data-validator

**Orchestration Flow**:
```
OrchestrationCycleStarted
├── ReloadProjectConfiguration
│   └── Detect 3 enabled projects
│
├── For each project (api-service, web-app, data-service):
│   ├── EnsureRepositoryCloned
│   │   └── ProjectClonedEvent emitted
│   │
│   └── OrchestrationDelegated to WorkflowOrchestrator
│       └── Process all work items in project board
│           ├── CardMovedEvent (Backlog → In Progress)
│           ├── AgentExecutionStarted
│           ├── AgentExecutionCompleted
│           └── ...repeat for all work items
│
└── OrchestrationCycleCompletedEvent
    ├── projects_processed: 3
    ├── boards_processed: 3
    ├── total_actions: 18
    └── cycle_duration_ms: ~1000
```

**Expected Events**:
- 3 `ProjectClonedEvent` (one per project)
- 18 `CardMovedEvent` (one per work item)
- 18 `AgentExecutionStarted` events
- 18 `AgentExecutionCompleted` events
- 1 `OrchestrationCycleCompletedEvent` (with aggregated metrics)

**Key Behaviors Validated**:

1. **Project Isolation**
   - Each project maintains separate state
   - No cross-project pipeline lock conflicts
   - No shared queues or resources
   - Independent workflow execution

2. **Configuration Management**
   - Configuration loaded at cycle start
   - Projects detected as enabled/disabled
   - Project metadata (repos, branches) loaded correctly

3. **Repository Management**
   - Each project repository cloned to workspace
   - Correct branch checked out
   - Repository state independent per project

4. **Work Item Processing**
   - All 18 work items processed across projects
   - Agent diversity (different agents per project)
   - Sequential processing per project (no inter-project parallelism in simulation)

5. **Cycle Completion**
   - Aggregated metrics calculated correctly
   - All events captured and sequenced
   - Cycle duration measured accurately

**Metrics**:
- Simulated Duration: ~10 minutes (across all projects)
- Real Duration: ~0.05 seconds
- Projects Processed: 3
- Work Items Processed: 18
- Events Emitted: 40+ (clones, moves, executions, completion)
- Speed Multiplier: 10,000x+ (very fast)

**Assertions Verified**:
- 3 projects loaded
- 18 total work items
- 3 clone events (one per project)
- 1 cycle completion event
- All assertions in scenario passed
- No assertion failures

**Use Case**: Multi-project support validation, multi-tenancy testing, orchestrator scalability

---

## Scenario Maintenance and Extension

### Adding New Scenarios

When creating new scenarios:

1. **Create file**: `tests/simulation/scenarios/scenario_NN_name.py`
2. **Define config**: `create_config()` function
3. **Define scenario**: `async def run_scenario(runner: SimulationRunner)`
4. **Write test**: `@pytest.mark.asyncio async def test_scenario_NN_name()`
5. **Document**: Add entry to this file

### Template

```python
"""Simulation Scenario NN: Description.

Tests:
- Key behavior 1
- Key behavior 2
- Key behavior 3
"""

from codetoreum.infrastructure.simulation import SimulationConfig, SimulationRunner

def create_config() -> SimulationConfig:
    """Create scenario configuration."""
    config = SimulationConfig.create_fast_config(
        scenario_name="scenario_NN_name",
        speed_multiplier=100.0,
    )
    return config

async def run_scenario(runner: SimulationRunner) -> None:
    """Execute scenario."""
    # Simulate events and advance time
    pass

@pytest.mark.asyncio
async def test_scenario_NN_name():
    """Test scenario execution."""
    config = create_config()
    runner = SimulationRunner(config)
    result = await runner.run(run_scenario)
    assert result.success
```

### Documentation Guidelines

- Focus on what is tested, not implementation details
- Include expected timeline and metrics
- Show key event sequences
- Provide multiple sub-scenarios for complex behaviors
- Include assertions that verify behavior

---

## Performance Baselines

All scenarios target:
- **Speed**: 10-100x faster than real time
- **Determinism**: Same input → same output always
- **Isolation**: No external service dependencies
- **Repeatability**: Can run thousands of times in CI/CD

---

## Regression Testing

Use scenarios in this order for CI/CD:
1. **Fast** (< 5s): 01, 09, 13
2. **Standard** (5-15s): 02, 03, 04, 05, 10
3. **Extended** (15-40s): 06, 06b, 07, 10b, 12
4. **Full Suite**: All scenarios (< 3 minutes total)

---

## References

- `tests/simulation/README.md` - Framework overview
- `src/codetoreum/infrastructure/simulation/` - Implementation
- `SCENARIO_06_DOCUMENTATION.md` - Detailed Scenario 06 spec
