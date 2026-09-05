# Smoke Scenario — Execution Call Chain

## What This Scenario Tests

The smoke scenario is the baseline validation for the board automation engine.
It exercises a two-agent pipeline — `coder` then `tester` — triggered by moving
a work item to the `In Progress` column on a five-column board:

```
Backlog → Ready → In Progress* → Review → Done
                  (coder)        (tester)
```

`In Progress` is the pipeline trigger column. Moving a work item there acquires
the pipeline lock, fires the coder agent, auto-progresses the item to `Review`,
fires the tester agent, and auto-progresses to `Done` — all without human
intervention. If this scenario fails, no other scenario is worth running.

**Simulation parameters:**
- Speed multiplier: 100×
- 3 work items seeded in `Backlog`
- Board: `board-1`
- Project: `default-project`
- Agents: `coder` (claude-sonnet-4-6), `tester` (claude-sonnet-4-6)

---

## Mermaid Sequence Diagram

```mermaid
sequenceDiagram
    autonumber

    participant Test as Test Harness / Human
    participant MBA as MockBoardAdapter<br/>(IBoardService)
    participant EB as EventBus
    participant BCEH as BoardColumnEventHandler
    participant WCS as IWorkflowConfigService<br/>(InMemoryWorkflowConfigService)
    participant LS as IPipelineLockService
    participant RR as IRunRegistry
    participant AR as IAgentRepository
    participant ESAE as ExecutionServiceAgentExecutor<br/>(IAgentExecutor)
    participant ES as ExecutionService
    participant WR as WorkspaceRouter
    participant VCS as IVersionControlService
    participant CF as IConfigStore
    participant CCA as ClaudeCodeAdapter<br/>(ILLMProvider)
    participant Claude as claude --print<br/>(subprocess)

    Note over Test,MBA: SETUP: SimulationApplicationBootstrap seeds board,<br/>work items, agents, workflow config, and board policy

    Test->>MBA: move_item_to_column("item-1", "In Progress", HUMAN)
    Note over MBA: Removes item from "Ready"<br/>Updates _item_positions<br/>Appends to "In Progress"

    MBA->>MBA: Collect WorkItemColumnChangedEvent(frozen)
    Note over MBA: Emitted OUTSIDE lock to prevent<br/>asyncio.Lock deadlock with event handlers

    MBA->>EB: emit_async(WorkItemColumnChangedEvent)<br/>work_item_id="item-1", from="Ready", to="In Progress",<br/>board_id="board-1", project_id="default-project"

    EB->>BCEH: dispatch → handle(WorkItemColumnChangedEvent)
    Note over BCEH: isinstance check passes

    BCEH->>BCEH: handle_column_change(event)
    BCEH->>WCS: get_board_workflow_template("board-1")
    WCS-->>BCEH: BoardWorkflowTemplate (5 columns configured)

    BCEH->>WCS: config.get_column_config("In Progress")
    WCS-->>BCEH: ColumnTemplate(type=AUTOMATED, agent_id="coder",<br/>is_pipeline_trigger=True, auto_progress_on_completion=True,<br/>on_failure_column="Backlog")

    Note over BCEH: column_config.is_pipeline_trigger == True<br/>→ routes to _handle_pipeline_trigger

    BCEH->>MBA: board_service.get_item_position("item-1")
    MBA-->>BCEH: ItemPosition(position=0)

    BCEH->>LS: lock_service.try_acquire_lock(project_id, board_id,<br/>work_item_id="item-1", board_position=0)
    LS-->>BCEH: LockResult(status=ACQUIRED)

    Note over BCEH: Lock ACQUIRED → start workflow run lifecycle

    BCEH->>RR: _start_workflow_run("item-1", project_id, board_id,<br/>column_config, workflow_config)
    RR-->>BCEH: run_info recorded (run_id, stage_name="In Progress")

    Note over BCEH: column_config.agent_id="coder" set<br/>execution_type != "conversational"<br/>no pr_review_cycle_config<br/>→ calls _trigger_agent

    BCEH->>RR: run_registry.set_active_run(work_item_id="item-1",<br/>run_id=run_info.run_id, stage_name="In Progress",<br/>project_id="default-project")
    RR-->>BCEH: ok

    BCEH->>ESAE: agent_executor.execute(work_item_id="item-1",<br/>agent_id="coder", board_id="board-1")

    Note over ESAE: Fire-and-forget: asyncio.create_task(_run_execution)
    ESAE-->>BCEH: returns immediately (task scheduled)

    Note over ESAE: === Background task: _run_execution ===

    ESAE->>RR: _run_registry.get_active_run("item-1")
    RR-->>ESAE: RunInfo(run_id, stage_name="In Progress",<br/>project_id="default-project")

    ESAE->>AR: _agent_repository.get_by_id("coder")
    AR-->>ESAE: Agent(id="coder", llm_model="claude-sonnet-4-6",<br/>timeout_seconds=3600, requires_docker=False)

    ESAE->>ES: _work_item_service.get_work_item(WorkItemId("item-1"))
    ES-->>ESAE: WorkItem(id="item-1", title="Implement login page",<br/>project_id="default-project")

    ESAE->>CF: _config_store.get_project_config("default-project")
    CF-->>ESAE: ProjectConfig(github_org="demo-org",<br/>github_repo="default-project",<br/>tech_stacks={...})

    Note over ESAE: repo_url = "https://github.com/demo-org/default-project.git"<br/>ProjectContext built from ProjectConfig

    ESAE->>VCS: _vcs.clone_repository(repo_url,<br/>"/workspace/item-1")
    VCS-->>ESAE: ok (mock: no-op, returns success)

    ESAE->>WR: _workspace_router.route_workspace(work_item, agent,<br/>project_context)
    WR-->>ESAE: Workspace(branch_name="feature/item-1",<br/>mount_path="/workspace/item-1", ...)

    ESAE->>ESAE: _branch_tracker.set_branch("item-1", "feature/item-1")

    ESAE->>WR: _workspace_router.prepare_workspace(workspace,<br/>project_context, work_item, "/workspace/item-1")
    WR-->>ESAE: PrepResult(success=True)
    Note over WR: Writes context files:<br/>/context/issue.txt, /context/code/, etc.

    ESAE->>ESAE: ExecutionContextBuilder.build_context(work_item,<br/>workflow_id, stage_name="In Progress",<br/>agent, project, workspace,<br/>repository_path="/workspace/item-1")
    Note over ESAE: ExecutionContext.working_directory = Path("/workspace/item-1")<br/>ExecutionContext.model = "claude-sonnet-4-6"<br/>ExecutionContext.timeout_seconds = 3600

    ESAE->>ES: _execution_service.create_execution(agent, work_item,<br/>workflow_id, stage_name="In Progress",<br/>prompt="Process work item item-1: Implement login page — stage: In Progress")
    ES-->>ESAE: AgentExecution(id=exec-id, status=PENDING)

    ESAE->>ES: _execution_service.start_execution(execution, context)
    ES-->>ESAE: StartResult(success=True)

    Note over ESAE: agent.requires_docker == False<br/>→ execute_with_llm path

    ESAE->>ES: _execution_service.execute_with_llm(execution, context)
    ES->>CCA: llm_provider.execute(prompt, context)

    Note over CCA: _build_command(prompt, context)<br/>→ ["claude", "--print", "--output-format", "stream-json",<br/>   "--permission-mode", "default",<br/>   "--model", "claude-sonnet-4-6", "--verbose",<br/>   "Process work item item-1: ..."]

    CCA->>Claude: asyncio.create_subprocess_exec(*cmd,<br/>cwd="/workspace/item-1", shell=False)
    Note over Claude: Full agentic loop:<br/>reads /context/issue.txt<br/>edits code files<br/>runs bash commands<br/>produces implementation

    Claude-->>CCA: stdout stream (NDJSON: assistant/usage/session_id events)
    CCA->>CCA: Parse stream: accumulate text,<br/>track token usage, capture session_id
    CCA->>CCA: await process.wait() (exit code check)

    Claude-->>CCA: exit code 0
    CCA-->>ES: ExecutionResult(content="...", model="claude-sonnet-4-6",<br/>duration_ms=N, conversation_id=session_id,<br/>metadata={exit_code: 0, working_directory: "/workspace/item-1"})

    ES-->>ESAE: ExecutionServiceResult(success=True, execution=...)

    ESAE->>WR: _workspace_router.finalize_workspace(workspace,<br/>project_context, {success: True, output: "..."},<br/>"/workspace/item-1")
    Note over WR: Commits code changes to branch,<br/>orchestrator handles git push (agents have no git creds)

    ESAE->>RR: _run_registry.clear_run("item-1")
    ESAE->>ESAE: _branch_tracker.clear("item-1")

    ESAE->>ESAE: _call_completion("item-1", "board-1", success=True)
    Note over ESAE: Calls _completion_callback<br/>(wired by set_completion_handler at bootstrap)

    ESAE->>MBA: _completion_callback → move_item_to_column("item-1",<br/>"Review", ORCHESTRATOR)
    Note over MBA: auto_progress_on_completion=True<br/>Emits WorkItemColumnChangedEvent(to="Review")

    MBA->>EB: emit_async(WorkItemColumnChangedEvent)<br/>work_item_id="item-1", from="In Progress", to="Review"

    EB->>BCEH: dispatch → handle(WorkItemColumnChangedEvent)
    Note over BCEH: to="Review": type=AUTOMATED, agent_id="tester"<br/>is_pipeline_trigger=False, is_exit_column=False<br/>→ AUTOMATED path (not pipeline trigger)<br/>→ _trigger_agent("item-1", tester_config, "board-1")

    BCEH->>ESAE: agent_executor.execute("item-1", "tester", "board-1")
    Note over ESAE: Fire-and-forget: asyncio.create_task<br/>Full _run_execution chain repeats for "tester" agent

    Note over CCA,Claude: ClaudeCodeAdapter launches second subprocess<br/>cwd="/workspace/item-1"<br/>tester agent validates the implementation

    ESAE->>ESAE: _call_completion("item-1", "board-1", success=True)

    ESAE->>MBA: move_item_to_column("item-1", "Done", ORCHESTRATOR)
    Note over MBA: auto_progress_on_completion=True for Review<br/>Emits WorkItemColumnChangedEvent(to="Done")

    MBA->>EB: emit_async(WorkItemColumnChangedEvent)<br/>work_item_id="item-1", from="Review", to="Done"

    EB->>BCEH: dispatch → handle(WorkItemColumnChangedEvent)
    Note over BCEH: to="Done": is_exit_column=True<br/>→ _handle_exit_column: releases pipeline lock

    BCEH->>LS: lock_service.release_lock(project_id, board_id, "item-1")
    LS-->>BCEH: ReleaseResult(next_work_item_id=None)
    Note over BCEH: Pipeline lock released.<br/>Next queued item (if any) would be granted the lock.
```

---

## Key Data Flowing Through Each Step

| Step | Data |
|------|------|
| Trigger | `work_item_id="item-1"`, `from_column="Ready"`, `to_column="In Progress"`, `board_id="board-1"`, `project_id="default-project"` |
| Lock acquisition | `board_position=0` (item's position in column) |
| Run registry | `run_id`, `stage_name="In Progress"`, `project_id="default-project"` |
| Project config lookup | `project_id="default-project"` → `github_org="demo-org"`, `github_repo="default-project"` |
| Repo clone path | `/workspace/item-1` |
| ExecutionContext | `working_directory=Path("/workspace/item-1")`, `model="claude-sonnet-4-6"`, `timeout_seconds=3600` |
| Claude CLI command | `["claude", "--print", "--output-format", "stream-json", "--permission-mode", "default", "--model", "claude-sonnet-4-6", "--verbose", "<prompt>"]` |
| Completion callback | `success=True` → `move_item_to_column("item-1", "Review", ORCHESTRATOR)` |
| Second agent | `agent_id="tester"` — same full chain, same working directory |
| Exit column | `to="Done"` → lock released |

---

## Known Gaps

**GAP 1: `AgentScheduler` queue consumer for QUEUED items**
The `AgentScheduler` is wired and consumes `WorkItemColumnChangedEvent` via
`WorkflowOrchestrator`, but the queue-dequeue path when a lock comes back as
`LockStatus.QUEUED` is not yet covered by simulation tests. When multiple items
move to the pipeline trigger column concurrently, the second item is queued; the
consumer that grants the lock and retriggers execution after the first item exits
has not been exercised end-to-end. In this scenario only one item is in the
trigger column at a time, so this gap does not affect smoke test outcomes.

> **Note on double-dispatch in tests:** Both `BoardColumnEventHandler` (BCEH) and
> `WorkflowOrchestrator` subscribe to `WorkItemColumnChangedEvent`. BCEH calls
> `execute()` directly; WO enqueues to `AgentScheduler` → `execute()`. In
> simulation fixtures the `AgentScheduler` is stopped after seeding so that only
> BCEH's direct execution path runs. In production the AgentScheduler's deferred
> call arrives after BCEH has already cleared the run registry, logs "No active
> run found", and silently no-ops — correct behaviour but noisy.

**GAP 2: GitHub board column → `board_id` mapping in webhook adapter**
`GitHubWebhookAdapter._map_column_to_stage()` contains a documented `TODO #370`:
it cannot reliably map GitHub project column IDs to internal board IDs. In
simulation, the trigger is issued directly via `MockBoardAdapter.move_item_to_column()`
and emits `WorkItemColumnChangedEvent` with the correct `board_id`. In
production, this mapping must be resolved before the board automation cascade
fires.
