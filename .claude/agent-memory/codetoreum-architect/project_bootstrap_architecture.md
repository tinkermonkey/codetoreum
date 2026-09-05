---
name: project-bootstrap-architecture
description: Bootstrap use case architecture — configuration sources, phase annotations, runtime flow, invariants, and deficiency log
metadata:
  type: project
---

Bootstrap (`/run-bootstrap` skill + `bootstrap/rounds.json`) exercises the production code path against real GitHub, Elasticsearch, and Claude Code.

**Why:** Simulation cannot detect integration defects: missing index init, misconfigured credentials, adapter wiring gaps, incorrect API call patterns.

Key facts:
- `bootstrap/register_project.py` persists ProjectConfig + AgentConfig to ES BEFORE server starts
- Phase 5c (`_load_bootstrap_projects`) loads rounds.json into IAgentRepository + IWorkflowConfigService + IConfigStore
- Phase 5c then calls `raw_adapter.register_project_repo(project_id, github_repo)` using `self._raw_ticket_adapter` (captured in Phase 4 before resilience wrapping)
- Phase 5d wires `WorkItemService` (ES-backed) to the executor's `_work_item_service`, replacing the placeholder created mid-Phase 5
- `CRITICAL_ADAPTER_SLOTS = {"board", "ticket", "llm", "version_control", "container", "code_review"}` — Phase 3 enforces no mocks
- `dispatch_via_task_queue=False` on WorkflowOrchestrator — BoardColumnEventHandler owns dispatch in production
- `ExecutionServiceAgentExecutor._executing_work_items` guards against duplicate dispatch

Deficiencies fixed (visible in recent git commits):
- DEF-003: register_project_repo() not called → ticket adapter had no repo mapping
- DEF-002: duplicate execution guard missing → double-dispatch race condition
- DEF-001: WorkItemService not wired to executor → ES-created work items invisible to executor

**How to apply:** When reviewing bootstrap-related code changes, check INV-01 through INV-12 in `bootstrap/ARCHITECTURE.md`. When adding new adapters or services, check whether Phase 5c/5d wiring needs updating.
