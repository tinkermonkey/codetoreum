# SDLC Pipeline Scenario

Canonical full software-development lifecycle scenario. Exercises the complete
agent sequence from requirements through release across a six-column board.
Corresponds to Scenario 06 in `SCENARIOS_COMPLETE.md`.

## Board flow

```
Backlog → Ready* → In Progress → Code Review → Testing → Done
                   (senior_se)   (code_reviewer) (qa_engineer)
```

`*` pipeline trigger — `Ready` is the manual staging column where a human (or
test harness) places an item to start the pipeline. The lock is acquired on
entry to `Ready`; automated work begins at `In Progress`.

## What it validates

- **Multi-stage automated pipeline**: three consecutive automated columns each
  hand off to the next via `auto_progress_on_completion`.
- **on_failure_column routing**: `In Progress` failure routes to `Backlog`;
  `Code Review` and `Testing` failures route back to `In Progress` (re-work,
  not abandon).
- **SLA escalation**: `Testing` column has `sla_escalation_column: Backlog` —
  an item that exceeds the 1-hour SLA is automatically returned to `Backlog`.
- **Manual trigger / human gate pattern**: `Ready` column with
  `is_pipeline_trigger: true` and no `agent_id` demonstrates that a human move
  can acquire the lock without immediately executing an agent.
- **7-agent registry**: all seven specialist agents are registered in
  `IAgentRepository` and available for execution.

## Agents

| Agent                   | Column       | Role                             |
|-------------------------|--------------|----------------------------------|
| requirements_analyst    | (workflow)   | Parses and structures requirements |
| software_architect      | (workflow)   | Designs system architecture      |
| senior_software_engineer| In Progress  | Implements features              |
| code_reviewer           | Code Review  | Reviews code quality             |
| qa_engineer             | Testing      | Runs unit / integration / E2E tests |
| devops_engineer         | (workflow)   | Merges branches, manages CI/CD   |
| release_manager         | (workflow)   | Prepares release notes           |

## Files

| File              | Owns                                                   |
|-------------------|--------------------------------------------------------|
| `simulation.yaml` | Clock speed (100×), fidelity, scenario identity        |
| `projects.yaml`   | External — web-app project with repository URL         |
| `work_items.yaml` | External — 3 work items (auth, notifications, perf)    |
| `workflows.yaml`  | Orchestrator — 7-stage SDLC workflow definition        |
| `agents.yaml`     | Orchestrator — 7 specialist agent configurations       |
| `board.yaml`      | Both — 6-column board structure + column policy        |

> **Note**: `board.yaml` currently mixes external state (board id, column names)
> with orchestrator policy (triggers, SLAs, failure routing). These will be split
> into `external/board_structure.yaml` and `orchestrator/board_policy.yaml` when
> the `external/` / `orchestrator/` directory structure is introduced.
