---
name: project-execution-chain-gaps
description: Critical and major gaps in the agent execution call chain discovered by tracing smoke and SDLC pipeline scenarios
metadata:
  type: project
---

# Agent Execution Call Chain — Known Gaps

Discovered by tracing `scenarios/smoke/` and `scenarios/sdlc_pipeline/` against
actual source code in May 2026. See `scenarios/smoke/call_chain.md` and
`scenarios/sdlc_pipeline/call_chain.md` for full diagrams.

## CRITICAL: `execute_with_llm` missing from `ExecutionService`

`ExecutionServiceAgentExecutor._run_execution()` (line 394,
`src/codetoreum/adapters/secondary/execution_service_agent_executor.py`) calls
`self._execution_service.execute_with_llm(execution, context)`.

The knowledge graph of `src/codetoreum/application/execution_service.py` has no
`execute_with_llm` method. The methods present are `__init__`,
`_build_container_labels`, `_commit_workspace`, and log helpers. This call will
raise `AttributeError` at runtime — **no agent execution can complete.**

**Why:** The method is either not yet implemented, lives on a different class, or
was removed without updating the call site.

**How to apply:** Before any test or review of the execution path, verify this
method exists. If absent, implementing it is a blocker for all execution scenarios.

## MAJOR: `AgentScheduler` queue consumer not implemented

When multiple items enter the pipeline trigger column, items 2+ receive
`LockStatus.QUEUED`. `_handle_exit_column` calls `lock_service.release_lock()`
which returns `next_work_item_id`, but nothing acts on that return value to
trigger the next item's pipeline. The second and third work items are permanently
stuck. See [[project-simulation-server-bug-fix]] for related wiring gaps.

**Why:** Queue consumer was explicitly deferred; documented as a known gap.

**How to apply:** When reviewing concurrency, ordering, or multi-item scenarios,
flag that only one item can flow through the pipeline at a time.

## MAJOR: Webhook adapter cannot map GitHub column ID to board_id

`GitHubWebhookAdapter._map_column_to_stage()` unconditionally returns `None`
with a `TODO #370` comment. Production GitHub webhook events cannot trigger
board automation. Simulation sidesteps this by calling
`MockBoardAdapter.move_item_to_column()` directly.

## MAJOR: Simulation tests do not exercise the board automation path

Neither the smoke scenario simulation test (`scenario_01_simple_workflow.py`)
nor the SDLC pipeline simulation test (`scenario_06_sdlc_pipeline.py`) uses
`MockBoardAdapter.move_item_to_column()` or exercises `BoardColumnEventHandler`.
Both manually fire events or test adapters in isolation. The complete call chain
from board move → domain event → event handler → lock → agent execution has no
integration test coverage.

## MINOR: Run registry stage names don't align with workflow stage names

The board column name (e.g. `"In Progress"`) is stored as `stage_name` in the
run registry, but the workflow YAML uses a different name (`"implementation"`).
Stage-based audit queries will return mismatched results.

## MINOR: SLA escalation column has no wired implementation

`Testing` column defines `sla_seconds=3600, sla_escalation_column="Backlog"`.
`MockBoardAdapter` records `_item_column_entries` timestamps but no monitor
service is wired to act on them. SLA breach routing is documented in config but
not implemented in the call chain.
