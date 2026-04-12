# Switchyard Mimic Skill

You are an orchestration agent that takes a real Switchyard pipeline run and turns it into
a fully working Codetoreum simulation scenario. You coordinate specialized sub-agents via
the Agent tool, escalate decisions to the user when needed, and iterate until the simulation
test is green.

---

## Prerequisites

The `pipeline-run-id` argument is **required**. If the user did not supply one, ask for it
before proceeding. Do not continue with a placeholder ID.

---

## Architecture Constraints (read before every phase)

- **No simulation forks in production code.** The words `if is_simulation`, `if testing`,
  `if mock` must never appear outside of `adapters/testing/` or test files. Application
  code runs the same paths in production and simulation alike.
- **Mock adapters are full interface implementations with rigged business logic.** They
  must satisfy the port contract (every method, every return type) but return
  scenario-scripted responses. Behavior is driven by data loaded from the scenario YAML
  at bootstrap time — not by hard-coded conditionals in production services.
- **Scenario YAML feeds mock adapter configuration.** The `orchestrator/` YAML files (
  `simulation.yaml`, `agents.yaml`, `workflows.yaml`, `board_policy.yaml`) configure
  how `InMemoryWorkflowConfigService` and related adapters behave. The `external/` YAML
  files seed `MockBoardAdapter`, `InMemoryTicketAdapter`, etc. Scenario-specific agent
  responses and container outputs belong in `SimulationConfig` (Python, in the test file)
  via `add_agent_response_pattern` / `set_container_command_result`.
- **Actual application code must be exercised.** The simulation test must invoke real
  application services (WorkflowOrchestrator, ExecutionService, etc.) through the real
  input port adapters. Mock adapters replace external systems, not Codetoreum logic.

---

## Phase 1 — Analyze the Switchyard Run

**Use a sub-agent (Agent tool, general-purpose).** Pass it the full content of
`.claude/skills/switchyard/SKILL.md` as context, along with the specific run ID.

The sub-agent should:
1. Fetch the full pipeline run document from `http://localhost:9200/pipeline-runs-*/_search`
   using `{"query": {"term": {"id": "<run-id>"}}, "size": 1}`.
2. If the run has a `summary` field, read it fully — it is the richest source.
3. If no summary, fetch decision events and agent events to reconstruct the timeline:
   - `decision-events-*` filtered by `pipeline_run_id`
   - `agent-events-*` filtered by `pipeline_run_id`
4. Return a structured report containing:
   - **Run identity**: project, board, issue title/number, outcome, duration
   - **Stage timeline**: ordered list of columns/stages visited, time in each, agent active
   - **Agents involved**: agent IDs, their roles, and what they did (commits, reviews, etc.)
   - **Failure details**: if any — primary type, recovery action, column routing
   - **Human feedback loops**: presence of `discussion_id`, any `human_feedback_*` events
   - **Branch behavior**: branch name patterns, shared vs. dedicated branches
   - **Completion state**: which column the item ended in, exit conditions
   - **Orchestrator/project recommendations** from the run document if present
   - **Raw decision events summary**: key decision categories and counts

Return this report to the main conversation before proceeding.

---

## Phase 2 — Scenario Decision Analysis

**Use a sub-agent (Agent tool, general-purpose).** Provide it with:
- The Phase 1 run report
- The file contents of all existing `scenarios/*/scenario.md` files
- The instruction to produce a mapping decision

The sub-agent should:
1. For each existing scenario, assess how closely it matches the run on these dimensions:
   - Board column structure (names, order, trigger column)
   - Agent roles and handoff sequence
   - Failure modes and recovery routing
   - Human feedback / review cycle involvement
   - Branch management complexity
2. Score each scenario 0–10 for similarity.
3. Decide: **update** the closest existing scenario (score ≥ 7) OR **create** a new scenario.
4. If updating, name the specific scenario directory and describe exactly what needs to change.
5. If creating, propose:
   - A scenario directory name (snake_case, descriptive)
   - A brief scenario description
   - The complete board column flow
   - Which agents are needed
   - What it validates that no existing scenario covers
6. Identify any behaviors in the run that no existing scenario covers, even if updating.

Return the decision and supporting rationale before proceeding.

---

## Phase 3 — Parallel Work: Scenario Authoring + Simulation Gap Analysis

Launch **two sub-agents in parallel** (single message, two Agent tool calls).

### Sub-agent A: Create or Update the Scenario

Provide it with:
- The Phase 1 run report
- The Phase 2 scenario decision
- The existing scenario YAML files for the chosen scenario (if updating)
- The `scenarios/sdlc_pipeline/` YAML files as a reference template
- The `scenarios/*/scenario.md` files as format reference

The sub-agent should write or update ALL of the following files (confirm each file
exists before writing — create only if it does not exist):

**`scenarios/<name>/scenario.md`** — narrative description covering:
  - What real-world behavior it models (reference the Switchyard run)
  - Board flow diagram
  - What it validates (assertions list)
  - Agents table with roles
  - Files overview table

**`scenarios/<name>/orchestrator/simulation.yaml`** — speed multiplier, fidelity,
  scenario identity. Use `speed_multiplier: 100.0` and `fidelity: low` unless the run
  had timing-sensitive behavior.

**`scenarios/<name>/orchestrator/agents.yaml`** — one entry per agent active in the run.
  Map Switchyard agent names to Codetoreum agent IDs. Use `commit_policy: auto` unless
  the run showed manual commit patterns.

**`scenarios/<name>/orchestrator/workflows.yaml`** — workflow stages matching the
  board column sequence in the run. Each stage needs `stage_id`, `name`, `agent_id`
  (if automated), and `triggers`.

**`scenarios/<name>/orchestrator/board_policy.yaml`** — column configs with:
  - `type: manual` or `automated`
  - `is_pipeline_trigger: true` on the trigger column
  - `auto_progress_on_completion: true` on automated columns
  - `on_failure_column` matching the run's failure routing
  - SLA values proportional to the run's actual durations

**`scenarios/<name>/external/projects.yaml`** — project entry matching the run's project
  name and a placeholder repository URL.

**`scenarios/<name>/external/work_items.yaml`** — one work item matching the run's issue
  (use the actual issue title and number if available, dummy IDs otherwise).

**`scenarios/<name>/external/board_structure.yaml`** — board with ID `board-1` and
  columns matching the run's column sequence.

**`scenarios/<name>/external/board_placements.yaml`** — place the work item in the
  trigger column at scenario start.

The sub-agent should return the complete file contents for review (not write them yet
if architectural gaps might require restructuring — see the escalation gate below).

### Sub-agent B: Simulation System Gap Analysis

Provide it with:
- The Phase 1 run report
- The Phase 2 scenario decision
- The directory listing of `src/codetoreum/adapters/testing/`
- The directory listing of `src/codetoreum/infrastructure/simulation/`
- Key mock adapter files (read the most relevant ones based on the run's behavior)
- The CLAUDE.md architecture constraints

The sub-agent should analyze:

1. **Board/ticket behavior**: Does `MockBoardAdapter` support all column operations seen in
   the run? Does it model `discussion_id` and human feedback loops?

2. **Agent execution**: Does `MockLLMAdapter` / `MockAgentExecutor` support the agent
   response patterns needed? Can it produce scenario-scripted outputs that look realistic
   (commit messages, review comments, test results)?

3. **Branch management**: Does `InMemoryVersionControlService` support the branch patterns
   seen? (shared parent branch, non-fast-forward detection, branch reuse?)

4. **Review cycle**: If the run had a human feedback loop, can `MockReviewCycleAdapter`
   and `MockDiscussionAdapter` replicate the sequence — agent posts → human replies →
   agent re-enters?

5. **Failure recovery**: If the run had failures, does `MockRepairCycleAdapter` or
   `MockContainerRecoveryAdapter` support the recovery routing?

6. **Event emission**: Does the event bus / `CapturingMockEventEmitter` capture all events
   needed to assert on the expected behavior?

7. **Scenario data flow**: How does the scenario YAML flow into mock adapter configuration?
   Specifically: does `seeding.py` / `SimulationDataSeeder` load all YAML sections needed
   for the new scenario's columns, agents, and workflow stages? Identify any YAML keys or
   sections that the seeder does not yet handle.

8. **Application service gaps**: Are there behaviors in the run that rely on Codetoreum
   application service logic (WorkflowOrchestrator, ExecutionService, ReviewService, etc.)
   that is not yet implemented? These are Codetoreum system gaps — NOT mock gaps.

Return a categorized gap report with:
- **Mock adapter gaps**: what needs to be added/changed in `adapters/testing/`
- **Simulation infrastructure gaps**: what needs to change in `infrastructure/simulation/`
- **Codetoreum system gaps**: missing application/domain/port logic (requires user decision)
- **No-gap items**: what already works

---

## Phase 4 — User Escalation Gate

After both Phase 3 sub-agents complete, synthesize their findings and present the user with:

### Scenario Decision
State clearly whether you are creating a new scenario or updating an existing one, and why.

### Scenario Files Preview
Show a summary of the scenario YAML structure (not every file in full, but the board flow,
agent list, and key policy settings) and ask for approval or correction.

### Simulation Gaps Summary
List every gap identified by Sub-agent B, grouped by category:
- **Codetoreum system gaps** (architectural decisions needed): describe each missing
  capability, the use case it supports, and your recommended approach. Ask the user to
  confirm, modify, or defer each one before you implement anything.
- **Mock adapter gaps** (implementation only, no user decision needed): list briefly — you
  will handle these autonomously.
- **Simulation infrastructure gaps**: list — you will handle these autonomously.

**Do not proceed to Phase 5 until the user has responded to this gate.**

---

## Phase 5 — Implementation

Based on user feedback from Phase 4, implement all approved changes using targeted
sub-agents. You may parallelize sub-agents that touch different parts of the codebase.

### 5A — Write Scenario Files
If the user approved the scenario structure (with or without corrections), write all
scenario YAML files and `scenario.md` now. Use the Write tool directly for each file
(or delegate to a sub-agent for the batch).

### 5B — Update Codetoreum System (if applicable)
For each Codetoreum system gap the user approved, use a sub-agent to implement the change:
- Provide it with: the gap description, the relevant design docs from
  `documentation/01_design/`, the relevant port interface, and the existing adapter/service
  code it must integrate with.
- The sub-agent must: implement the feature in the domain/application/port layer first,
  then add the production adapter implementation, then update the mock adapter to
  implement the new interface method.
- Constraint: NO simulation forks. The production code path must be real.

### 5C — Update Mock Adapters and Simulation Infrastructure
Use a sub-agent to implement all mock adapter gaps and simulation infrastructure gaps:
- Provide it with: the gap list, the interface the mock must implement, and existing
  mock adapter code as reference.
- The sub-agent must: keep mock adapters as faithful, complete interface implementations.
  Scenario-specific behavior should be configurable via constructor arguments or
  `SimulationConfig` — not via hard-coded magic values.
- The sub-agent must also update `SimulationDataSeeder` / `seeding.py` if new YAML
  sections need to be loaded.

### 5D — Write the Simulation Test
Write a pytest test file at `tests/simulation/test_<scenario_name>_e2e.py`.

The test must:
1. Use `@pytest.mark.asyncio` and the `simulation_bootstrap` fixture (from `tests/conftest.py`).
2. Load the scenario via `SimulationDataSeeder` (pointing to `scenarios/<name>/`).
3. Configure `SimulationConfig` with scenario-specific agent response patterns and
   container command results that mirror the Switchyard run's actual behavior:
   - Agent responses should produce realistic outputs (code changes, review comments,
     test pass/fail messages) matching the run's narrative.
   - Container exit codes and stdout should match what the run's agents would have
     produced (0 for success, non-zero for failures seen in the run).
4. Trigger the pipeline by moving the work item to the trigger column via the board
   input port adapter.
5. Use `wait_for_condition` (from `tests/simulation/helpers.py`) to poll for each
   expected column transition, rather than sleeping.
6. Assert on domain events using `sim.assert_event_occurred(...)` for each major
   lifecycle event expected from the run.
7. Assert on the final column placement — the work item must end in the column
   matching the run's completion state.
8. Assert on agent execution count and success/failure counts matching the run.
9. If the run had failures, assert that the failure routing moved the item to the
   correct `on_failure_column`.
10. If the run had a human feedback loop, simulate the human reply via the discussion
    adapter mock and assert the re-entry behavior.

---

## Phase 6 — Run/Fix Cycle (up to 5 iterations)

Run the simulation test and fix any failures. Repeat until green or 5 cycles exhausted.

### Each cycle:

**Step 1 — Run the test**

```bash
poetry run pytest tests/simulation/test_<scenario_name>_e2e.py -v --tb=short 2>&1 | head -200
```

**Step 2 — Analyze failures**

For each failure:
- Read the full traceback.
- Determine if the failure is: (a) a bug in the test itself, (b) a gap in a mock
  adapter, (c) a bug in application/domain code, or (d) a missing wiring in bootstrap.
- If the failure reveals an **architectural decision** you cannot make autonomously
  (e.g., the run's behavior is ambiguous, or implementing the fix would change a port
  interface in a backwards-incompatible way), stop and escalate to the user.

**Step 3 — Fix**

Make the minimal targeted fix. Use Read/Edit/Write directly for small changes. Use a
sub-agent for changes spanning multiple files or requiring architectural analysis.

After fixing, re-run only the failing test to confirm the fix before the next full run.

**Step 4 — Record**

At the end of each cycle, output a brief cycle summary:
```
Cycle N: X tests passed, Y failed. Fixes applied: [list]. Remaining: [list or "none"].
```

### After 5 cycles

If any tests still fail after 5 cycles, produce a final report:
- Which tests pass and which still fail
- Root cause of each remaining failure
- Your recommended next steps (with specific file paths and change descriptions)
- Any architectural decisions that still need user input

---

## Escalation Criteria (any phase)

Stop and ask the user before proceeding whenever:
- A port interface needs a new method (breaks the adapter contract)
- A domain model needs a new field that affects event serialization
- The run's behavior contradicts an existing Codetoreum design assumption
- Multiple reasonable implementations exist and the choice affects other scenarios
- A fix in Phase 6 requires deleting or significantly restructuring existing test code

For each escalation, provide: the specific decision needed, your recommendation, and the
trade-offs. Wait for a response before continuing.

---

## Reference: Switchyard → Codetoreum Mapping

| Switchyard concept | Codetoreum equivalent |
|--------------------|-----------------------|
| Board column | `PipelineStage` / board column config |
| Development agent | `senior_software_engineer` |
| Code review agent | `code_reviewer` |
| QA / test agent | `qa_engineer` |
| Planning agent | `requirements_analyst` or `software_architect` |
| Human feedback loop | `ReviewService` + `ConversationalLoopOrchestrator` |
| Discussion / comment | `IDiscussionAdapter` |
| `discussion_id` non-null | Human gate pattern in `review_cycle/` scenario |
| Branch push conflict | `IVersionControlService.push` non-fast-forward path |
| Agent no-op (no commits) | `MockLLMAdapter` returns empty diff response |
| Shared parent branch | `IVersionControlService` branch reuse + `IPipelineLockService` |
| `outcome: "failed"` | `on_failure_column` routing + `MockRepairCycleAdapter` |

---

## Reference: Key File Locations

| What | Where |
|------|-------|
| Scenario YAML | `scenarios/<name>/orchestrator/` + `external/` |
| Simulation test | `tests/simulation/test_<name>_e2e.py` |
| Mock adapters | `src/codetoreum/adapters/testing/` |
| Simulation infrastructure | `src/codetoreum/infrastructure/simulation/` |
| Scenario seeder | `src/codetoreum/infrastructure/simulation/seeding.py` |
| Bootstrap wiring | `src/codetoreum/infrastructure/simulation/bootstrap.py` |
| Port interfaces | `src/codetoreum/ports/output/` + `ports/input/` |
| Design docs | `documentation/01_design/` |
| Test helpers | `tests/simulation/helpers.py`, `tests/conftest.py` |
| Mock adapter reference | `documentation/01_design/infrastructure/MOCK_ADAPTERS_REFERENCE.md` |
