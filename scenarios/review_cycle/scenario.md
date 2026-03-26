# Review Cycle Scenario

Maker-checker review workflow with a human gate between implementation and
automated review. Validates the interaction between pipeline locks, manual
staging columns, SLA escalation, and feedback-routing failure columns.

## Board flow

```
Backlog → In Progress* → Awaiting Review → Review → Done
          (maker)         (human gate)      (reviewer)
                               │                │
                          sla_escalation    on_failure
                          → Backlog         → Changes Requested
                                                │
                                           sla_escalation
                                           → Backlog
```

`*` pipeline trigger — lock acquired on entry to `In Progress`. The lock spans
the entire path through to `Done`, including the manual `Awaiting Review` gate.

## What it validates

- **Lock held across a human gate**: the pipeline lock is acquired at
  `In Progress` and not released until `Done`, even though `Awaiting Review`
  is a manual column where the item can sit indefinitely.
- **SLA escalation on manual columns**: `Awaiting Review` (24 h) and
  `Changes Requested` (48 h) both have `sla_escalation_column: Backlog`. Items
  that stall are automatically returned to `Backlog` by the SLA watchdog.
- **on_failure_column as review feedback**: `Review` failure routes to
  `Changes Requested` rather than `Backlog`, modelling a "reviewer found
  problems" outcome distinct from a technical failure.
- **Iterative revision pattern**: `Changes Requested` is a manual column; the
  author can move the item back to `In Progress` to re-engage the maker.
- **maker / reviewer agent separation**: maker runs only in `In Progress`;
  reviewer runs only in `Review`. Neither column auto-progresses on the other's
  behalf.

## Agents

| Agent    | Column      | Role                                         |
|----------|-------------|----------------------------------------------|
| maker    | In Progress | Implements the change; addresses feedback    |
| reviewer | Review      | Reviews code; approves or requests changes   |

## Files

### `orchestrator/` — always applied (Codetoreum-owned config)

| File                 | Owns                                                    |
|----------------------|---------------------------------------------------------|
| `simulation.yaml`    | Clock speed (10×), fidelity, scenario identity          |
| `agents.yaml`        | Maker (thorough) and reviewer (strict) configurations   |
| `workflows.yaml`     | 2-stage maker/checker workflow                          |
| `board_policy.yaml`  | Column triggers, SLAs, failure routing                  |

### `external/` — simulation only (data owned by external system)

| File                   | Owns                                              |
|------------------------|---------------------------------------------------|
| `projects.yaml`        | Review-cycle project                              |
| `work_items.yaml`      | 5 work items requiring mandatory review           |
| `board_structure.yaml` | 6-column board id, name, and column list          |
| `board_placements.yaml`| Initial work item column placements               |
