# Smoke Scenario

Minimal two-agent pipeline used as the baseline validation for the board
automation engine. If this scenario fails, nothing else is worth running.

## Board flow

```
Backlog → Ready → In Progress* → Review → Done
                  (coder)        (tester)
```

`*` pipeline trigger — lock acquired here, cascade begins automatically.

## What it validates

- **Board automation cascade**: moving an item to `In Progress` acquires the
  pipeline lock, fires the coder agent, auto-progresses to `Review`, fires the
  tester agent, and auto-progresses to `Done` — all without human intervention.
- **Agent execution order**: coder always runs before tester (`agent_order ==
  ["coder", "tester"]`).
- **Workflow template registration**: `IWorkflowConfigService` has a template
  for `board-1` with the correct trigger and exit columns after seeding.
- **Board placements**: all 3 work items land in `Backlog` after seeding.
- **on_failure_column routing**: agent failure on either automated column routes
  the item back to `Backlog`.

## Agents

| Agent   | Column     | Role                        |
|---------|------------|-----------------------------|
| coder   | In Progress | Implements the work item   |
| tester  | Review      | Validates the implementation|

## Files

### `orchestrator/` — always applied (Codetoreum-owned config)

| File                 | Owns                                          |
|----------------------|-----------------------------------------------|
| `simulation.yaml`    | Clock speed, fidelity, scenario identity      |
| `agents.yaml`        | Coder and tester agent configurations         |
| `workflows.yaml`     | 2-stage workflow definition                   |
| `board_policy.yaml`  | Column triggers, SLAs, agent assignments      |

### `external/` — simulation only (data owned by external system)

| File                   | Owns                                        |
|------------------------|---------------------------------------------|
| `projects.yaml`        | Project / repo definition                   |
| `work_items.yaml`      | 3 work items seeded in Backlog              |
| `board_structure.yaml` | Board id, name, and column list             |
| `board_placements.yaml`| Initial work item column placements         |
