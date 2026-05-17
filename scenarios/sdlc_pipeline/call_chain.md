# SDLC Pipeline Scenario — Execution Call Chain

## What This Scenario Tests

The SDLC pipeline scenario is the canonical full software-development lifecycle
test. It exercises three consecutive automated columns across a six-column board,
with a manual human gate (`Ready`) that acquires the pipeline lock before any
automation begins:

```
Backlog → Ready* → In Progress → Code Review → Testing → Done
                   (senior_se)   (code_reviewer) (qa_engineer)
```

`Ready` is the pipeline trigger column with no agent assigned — a human (or
test harness) places an item there to acquire the lock. Automated work begins
only when the item enters `In Progress`. Each automated column hands off to the
next via `auto_progress_on_completion`. Failures route back to `In Progress`
(rework, not abandon) for Code Review and Testing; `In Progress` failures route
to `Backlog`. The `Testing` column has an SLA escalation to `Backlog` if the
1-hour SLA is exceeded.

**Simulation parameters:**
- Speed multiplier: 100×
- 3 work items seeded in `Backlog` (auth, notifications, perf)
- Board: `board-1` ("SDLC Board"), Project: `web-app-project`
- Repository: `https://github.com/demo-org/web-app.git`
- 7 agents registered: `requirements_analyst`, `software_architect`,
  `senior_software_engineer`, `code_reviewer`, `qa_engineer`,
  `devops_engineer`, `release_manager`
- Only 3 agents are board-column-assigned; 4 are workflow-definition-only

---

## Mermaid Sequence Diagram

```mermaid
sequenceDiagram
    autonumber

    participant Human as Human / Test Harness
    participant MBA as MockBoardAdapter<br/>(IBoardService)
    participant EB as EventBus
    participant BCEH as BoardColumnEventHandler
    participant WCS as IWorkflowConfigService
    participant LS as IPipelineLockService
    participant RR as IRunRegistry
    participant AR as IAgentRepository
    participant CF as IConfigStore
    participant ESAE as ExecutionServiceAgentExecutor<br/>(IAgentExecutor)
    participant ES as ExecutionService
    participant WR as WorkspaceRouter
    participant VCS as IVersionControlService
    participant CCA as ClaudeCodeAdapter<br/>(ILLMProvider)
    participant Claude as claude --print<br/>(subprocess)

    Note over Human,MBA: SETUP: SimulationApplicationBootstrap seeds board, work items,<br/>7 agents, workflow config, and board policy

    %% ─── PHASE 1: Human moves item to Ready (pipeline trigger, no agent) ───

    Human->>MBA: move_item_to_column("item-1", "Ready", HUMAN)
    Note over MBA: item-1 = "Add user authentication system"<br/>Emits WorkItemColumnChangedEvent outside lock

    MBA->>EB: emit_async(WorkItemColumnChangedEvent)<br/>work_item_id="item-1", from="Backlog", to="Ready",<br/>board_id="board-1", project_id="web-app-project"

    EB->>BCEH: dispatch → handle(WorkItemColumnChangedEvent)
    BCEH->>BCEH: handle_column_change(event)
    BCEH->>WCS: get_board_workflow_template("board-1")
    WCS-->>BCEH: BoardWorkflowTemplate (6 columns configured)
    BCEH->>WCS: get_column_config("Ready")
    WCS-->>BCEH: ColumnTemplate(type=manual, agent_id=None,<br/>is_pipeline_trigger=True, sla_seconds=86400)

    Note over BCEH: is_pipeline_trigger=True → _handle_pipeline_trigger<br/>agent_id is None → lock acquired but NO agent fired

    BCEH->>MBA: board_service.get_item_position("item-1")
    MBA-->>BCEH: ItemPosition(position=0)

    BCEH->>LS: try_acquire_lock(project_id="web-app-project",<br/>board_id="board-1", work_item_id="item-1", board_position=0)
    LS-->>BCEH: LockResult(status=ACQUIRED)

    BCEH->>RR: _start_workflow_run("item-1", "web-app-project",<br/>"board-1", column_config, workflow_config)
    Note over RR: run_id generated, stage_name="Ready"<br/>project_id="web-app-project" recorded

    Note over BCEH: column_config.agent_id is None<br/>→ no _trigger_agent call<br/>Pipeline lock held; item waits in Ready

    %% ─── PHASE 2: Human (or auto-advance) moves item to In Progress ───

    Human->>MBA: move_item_to_column("item-1", "In Progress", HUMAN)
    Note over MBA: Emits WorkItemColumnChangedEvent outside lock

    MBA->>EB: emit_async(WorkItemColumnChangedEvent)<br/>from="Ready", to="In Progress"

    EB->>BCEH: dispatch → handle(WorkItemColumnChangedEvent)
    BCEH->>WCS: get_column_config("In Progress")
    WCS-->>BCEH: ColumnTemplate(type=AUTOMATED,<br/>agent_id="senior_software_engineer",<br/>is_pipeline_trigger=False,<br/>auto_progress_on_completion=True,<br/>on_failure_column="Backlog")

    Note over BCEH: NOT pipeline_trigger, NOT exit_column<br/>type=AUTOMATED, agent_id set,<br/>not repair/conversational/PR-review<br/>→ _trigger_agent("item-1", column_config, "board-1")

    BCEH->>RR: run_registry.set_active_run("item-1",<br/>run_id, stage_name="In Progress",<br/>project_id="web-app-project")

    BCEH->>ESAE: agent_executor.execute("item-1",<br/>"senior_software_engineer", "board-1")

    Note over ESAE: asyncio.create_task(_run_execution)<br/>Caller returns immediately

    %% ─── PHASE 3: ExecutionServiceAgentExecutor._run_execution ───

    ESAE->>RR: get_active_run("item-1")
    RR-->>ESAE: RunInfo(run_id, stage_name="In Progress",<br/>project_id="web-app-project")

    ESAE->>AR: get_by_id("senior_software_engineer")
    AR-->>ESAE: Agent(llm_model="claude-sonnet-4-6",<br/>max_tokens=8192, timeout_seconds=1800,<br/>requires_docker=False)

    ESAE->>ES: get_work_item(WorkItemId("item-1"))
    ES-->>ESAE: WorkItem(title="Add user authentication system",<br/>description="OAuth2 with JWT...",<br/>project_id="web-app-project")

    ESAE->>CF: get_project_config("web-app-project")
    CF-->>ESAE: ProjectConfig(github_org="demo-org",<br/>github_repo="web-app",<br/>tech_stacks={"react": ..., "fastapi": ...})

    Note over ESAE: repo_url = "https://github.com/demo-org/web-app.git"<br/>ProjectContext(repository_url, default_branch="main",<br/>test_command from testing config)

    ESAE->>VCS: clone_repository("https://github.com/demo-org/web-app.git",<br/>"/workspace/item-1")
    VCS-->>ESAE: ok (mock: no-op in simulation)

    ESAE->>WR: route_workspace(work_item, agent, project_context)
    WR-->>ESAE: Workspace(branch_name="feature/item-1",<br/>mount_path="/workspace/item-1")

    ESAE->>ESAE: branch_tracker.set_branch("item-1", "feature/item-1")

    ESAE->>WR: prepare_workspace(workspace, project_context,<br/>work_item, "/workspace/item-1")
    WR-->>ESAE: PrepResult(success=True)
    Note over WR: Writes context files:<br/>/context/issue.txt ← work item description<br/>/context/code/ ← relevant source files<br/>/context/previous_stage.txt ← prior stage output

    ESAE->>ESAE: ExecutionContextBuilder.build_context(work_item,<br/>workflow_id, stage_name="In Progress",<br/>agent, project, workspace,<br/>repository_path="/workspace/item-1")
    Note over ESAE: ExecutionContext.working_directory = Path("/workspace/item-1")<br/>ExecutionContext.model = "claude-sonnet-4-6"<br/>ExecutionContext.timeout_seconds = 1800

    ESAE->>ES: create_execution(agent, work_item, workflow_id,<br/>stage_name="In Progress", prompt="Process work item item-1:<br/>Add user authentication system — stage: In Progress")
    ES-->>ESAE: AgentExecution(id, status=PENDING)

    ESAE->>ES: start_execution(execution, context)
    ES-->>ESAE: StartResult(success=True)

    Note over ESAE: agent.requires_docker == False → execute_with_llm

    ESAE->>ES: execute_with_llm(execution, context)
    ES->>CCA: llm_provider.execute(prompt, context)

    Note over CCA: _build_command builds:<br/>["claude", "--print", "--output-format", "stream-json",<br/>"--permission-mode", "default",<br/>"--model", "claude-sonnet-4-6", "--verbose",<br/>"Process work item item-1: Add user authentication system..."]

    CCA->>Claude: asyncio.create_subprocess_exec(*cmd,<br/>cwd="/workspace/item-1", shell=False)

    Note over Claude: Full agentic loop (autonomous):<br/>reads /context/issue.txt → understands OAuth2/JWT requirements<br/>reads /context/code/ → understands existing codebase<br/>edits source files (auth module, routes, tests)<br/>runs bash (pytest, linting)<br/>produces implementation

    Claude-->>CCA: stdout NDJSON stream<br/>(type: assistant|usage|session_id events)
    CCA->>CCA: Accumulate text, track tokens,<br/>capture session_id for conversation continuity
    CCA->>CCA: await asyncio.wait_for(read_stream(), timeout=1800)
    CCA->>CCA: await process.wait() — exit code 0

    CCA-->>ES: ExecutionResult(content="Implementation complete...",<br/>model="claude-sonnet-4-6",<br/>conversation_id=session_id,<br/>metadata={exit_code: 0, working_directory: "/workspace/item-1"})

    ES-->>ESAE: ExecutionServiceResult(success=True)

    ESAE->>WR: finalize_workspace(workspace, project_context,<br/>{success: True, output: "..."}, "/workspace/item-1")
    Note over WR: Orchestrator commits and pushes branch<br/>Agents have NO git credentials; orchestrator owns all VCS ops

    ESAE->>RR: clear_run("item-1")
    ESAE->>ESAE: branch_tracker.clear("item-1")
    ESAE->>ESAE: _call_completion("item-1", "board-1", success=True)

    ESAE->>MBA: completion_callback → move_item_to_column("item-1",<br/>"Code Review", ORCHESTRATOR)
    Note over MBA: auto_progress_on_completion=True<br/>Emits WorkItemColumnChangedEvent(to="Code Review")

    %% ─── PHASE 4: Code Review column ───

    MBA->>EB: emit_async(WorkItemColumnChangedEvent)<br/>from="In Progress", to="Code Review"

    EB->>BCEH: dispatch → handle(WorkItemColumnChangedEvent)
    BCEH->>WCS: get_column_config("Code Review")
    WCS-->>BCEH: ColumnTemplate(type=AUTOMATED, agent_id="code_reviewer",<br/>auto_progress_on_completion=True,<br/>on_failure_column="In Progress")

    Note over BCEH: AUTOMATED, not pipeline_trigger<br/>→ _trigger_agent("item-1", code_reviewer_config, "board-1")

    BCEH->>ESAE: agent_executor.execute("item-1", "code_reviewer", "board-1")
    Note over ESAE: Full _run_execution chain for code_reviewer<br/>timeout_seconds=1200, max_tokens=4096<br/>ClaudeCodeAdapter reviews implementation in /workspace/item-1

    Note over CCA,Claude: code_reviewer agent:<br/>reads implementation files<br/>checks for correctness, security, style<br/>produces review output

    ESAE->>ESAE: _call_completion("item-1", "board-1", success=True)
    ESAE->>MBA: move_item_to_column("item-1", "Testing", ORCHESTRATOR)

    %% ─── PHASE 5: Testing column ───

    MBA->>EB: emit_async(WorkItemColumnChangedEvent)<br/>from="Code Review", to="Testing"

    EB->>BCEH: dispatch → handle(WorkItemColumnChangedEvent)
    BCEH->>WCS: get_column_config("Testing")
    WCS-->>BCEH: ColumnTemplate(type=AUTOMATED, agent_id="qa_engineer",<br/>auto_progress_on_completion=True,<br/>on_failure_column="In Progress", sla_seconds=3600,<br/>sla_escalation_column="Backlog")

    Note over BCEH: AUTOMATED, not pipeline_trigger<br/>→ _trigger_agent("item-1", qa_engineer_config, "board-1")

    BCEH->>ESAE: agent_executor.execute("item-1", "qa_engineer", "board-1")
    Note over ESAE: Full _run_execution chain for qa_engineer<br/>timeout_seconds=2400, max_tokens=6144

    Note over CCA,Claude: qa_engineer agent:<br/>reads implementation + review output from context<br/>writes unit, integration, and E2E tests<br/>runs pytest, captures results

    ESAE->>ESAE: _call_completion("item-1", "board-1", success=True)
    ESAE->>MBA: move_item_to_column("item-1", "Done", ORCHESTRATOR)

    %% ─── PHASE 6: Done column (exit) ───

    MBA->>EB: emit_async(WorkItemColumnChangedEvent)<br/>from="Testing", to="Done"

    EB->>BCEH: dispatch → handle(WorkItemColumnChangedEvent)
    BCEH->>WCS: get_column_config("Done")
    WCS-->>BCEH: ColumnTemplate(type=manual, is_exit_column=True)

    Note over BCEH: is_exit_column=True → _handle_exit_column

    BCEH->>LS: lock_service.release_lock("web-app-project",<br/>"board-1", "item-1")
    LS-->>BCEH: ReleaseResult(next_work_item_id="item-2" or None)
    Note over BCEH: Pipeline lock released.<br/>If item-2 is queued, lock is granted and<br/>_start_workflow_run is called for item-2.
```

---

## Key Data Flowing Through Each Step

| Step | Data |
|------|------|
| Initial trigger | Human moves `item-1` to `Ready`; `project_id="web-app-project"`, `board_id="board-1"` |
| Lock acquired at | `Ready` column entry — no agent fires yet |
| Lock held through | `In Progress` → `Code Review` → `Testing` (entire automated sequence) |
| Project config | `github_org="demo-org"`, `github_repo="web-app"` → `repo_url` |
| Repo clone path | `/workspace/item-1` (per work item, not per agent) |
| senior_se context | `working_directory="/workspace/item-1"`, `model="claude-sonnet-4-6"`, `timeout=1800s` |
| code_reviewer context | same `working_directory`, `timeout=1200s`, `max_tokens=4096` |
| qa_engineer context | same `working_directory`, `timeout=2400s`, `max_tokens=6144` |
| Failure routing | `In Progress` failure → `Backlog`; `Code Review` / `Testing` failure → `In Progress` |
| SLA escalation | `Testing` > 3600s → item routed to `Backlog` (SLA monitor, separate from board event handler) |
| Lock release | Only at `Done` (exit column) — not at intermediate columns |

---

## Workflow Stages vs Board Columns

The 7-stage SDLC workflow definition (`orchestrator/workflows.yaml`) and the
board column policy (`orchestrator/board_policy.yaml`) are **not directly
coupled**. The workflow YAML registers 7 stages including `requirements`,
`design`, `integration`, and `release`. Only 3 of these map to board columns:

| Workflow stage | Board column | Agent |
|---|---|---|
| `implementation` | `In Progress` | `senior_software_engineer` |
| `code-review` | `Code Review` | `code_reviewer` |
| `testing` | `Testing` | `qa_engineer` |

The `requirements_analyst`, `software_architect`, `devops_engineer`, and
`release_manager` agents are registered in `IAgentRepository` and available for
execution but are not assigned to any board column in this scenario. They would
be invoked via a workflow orchestrator that chains stages explicitly, not by
board column movement. The board automation engine drives only the three
board-column-assigned agents.

---

## Known Gaps

**GAP 1: `execute_with_llm` missing from `ExecutionService`**
`ExecutionServiceAgentExecutor._run_execution()` calls
`self._execution_service.execute_with_llm(execution, context)` at step 10. The
knowledge graph index of `ExecutionService` (`src/codetoreum/application/execution_service.py`)
shows no `execute_with_llm` method — only `__init__`, `_build_container_labels`,
`_commit_workspace`, and log helpers. This call will raise `AttributeError` in
production. This is a critical blocking gap for all agent execution paths.

**GAP 2: `AgentScheduler` queue consumer not implemented**
When multiple work items are placed in `Ready` before the first completes,
items 2 and 3 receive `LockStatus.QUEUED`. The queue consumer that dequeues
them after the lock is released does not yet exist. `_handle_exit_column`
calls `lock_service.release_lock()` which returns `next_work_item_id`, but
nothing acts on that value to start the next item's pipeline. The second and
third work items in this scenario will be permanently stuck after the first
completes.

**GAP 3: Webhook adapter cannot map GitHub column ID to `board_id`**
`GitHubWebhookAdapter._map_column_to_stage()` returns `None` unconditionally
due to a `TODO #370`. In production, a human moving a card in GitHub Projects
will not trigger the automation. The simulation sidesteps this by calling
`MockBoardAdapter.move_item_to_column()` directly.

**GAP 4: Workflow stage config and board column config are not unified**
The `Ready` column acquires the pipeline lock but the run registry
`stage_name` is set to `"Ready"` (the column name), not to a workflow stage
name. When `In Progress` triggers the agent, `set_active_run` is called with
`stage_name="In Progress"`. The workflow YAML names the corresponding stage
`"implementation"`. This mismatch means the run registry stage names do not
align with the workflow definition stage names, which may cause stage-based
metrics and audit queries to return incorrect results.

**GAP 5: 4 workflow-only agents never execute in board automation**
The `requirements_analyst`, `software_architect`, `devops_engineer`, and
`release_manager` agents are defined in `agents.yaml` and the 7-stage workflow
definition. They are not assigned to any board column. In this scenario, as run
by the board automation engine, these agents never execute. To invoke them, a
separate workflow orchestration path (not the board column event handler) would
need to be implemented. This scenario's simulation test (`scenario_06_sdlc_pipeline.py`)
validates `MockReviewCycleAdapter` in isolation and does not exercise the board
automation path at all.

**GAP 6: Simulation test does not exercise the full board pipeline**
`tests/simulation/scenarios/scenario_06_sdlc_pipeline.py` tests the
`MockReviewCycleAdapter` review cycle in isolation (approve/changes-requested/
blocked sequences). It does not use `MockBoardAdapter.move_item_to_column()`,
`BoardColumnEventHandler`, `IPipelineLockService`, or
`ExecutionServiceAgentExecutor`. The actual SDLC pipeline board automation
call chain has no simulation integration test coverage.

**GAP 7: SLA escalation has no event-driven implementation traced**
The `Testing` column has `sla_seconds=3600, sla_escalation_column="Backlog"`.
The call chain above does not include an SLA monitor service — no component
in the traced path observes `_item_column_entries` timestamps and routes the
item to `Backlog` on SLA breach. The `MockBoardAdapter` records the entry time
(`_item_column_entries`) but no handler is wired to act on it.
