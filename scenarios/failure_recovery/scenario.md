# Failure Recovery Scenario

Tests the system's error-handling and recovery mechanics using an intentionally
unreliable agent. Validates that `on_failure_column` routing works correctly and
that a separate recovery stage can process items that have failed.

## Board flow

```
Backlog → In Progress* → (next automated column or …)
          (flaky_agent)
               │
          on_failure
               ↓
            Failed          ← manual holding column; human decides
               │
          (human moves)
               ↓
           Recovery → Done
          (recovery_agent)
```

`*` pipeline trigger. `flaky_agent` has a 50 % failure rate configured in its
metadata, simulating intermittent errors (network, timeout, invalid response).

## What it validates

- **on_failure_column routing**: when `flaky_agent` fails, the item is moved
  to `Failed` rather than being left in `In Progress` or silently dropped.
- **Manual recovery queue**: `Failed` is a manual column with no agent and no
  auto-progression. A human (or test harness) must explicitly move the item to
  `Recovery` to re-engage automation. This validates that the system does not
  automatically retry without human acknowledgement.
- **Independent recovery agent**: `recovery_agent` runs in the `Recovery`
  column with a 0 % failure rate. Its success auto-progresses the item to
  `Done`, validating that a separate recovery path can complete items that
  previously failed.
- **SLA coverage on failure column**: `In Progress` has a 30-minute SLA.
  Items that stall there (e.g. agent hung before failure was recorded) are
  caught by the watchdog.
- **Failure logging and observability**: all five work items exercise different
  failure modes (intermittent, timeout, permanent, recovery, cascading) to
  ensure each is logged and handled without silent drops.

## Agents

| Agent          | Column      | Failure rate | Role                               |
|----------------|-------------|--------------|------------------------------------|
| flaky_agent    | In Progress | 50 %         | Simulates intermittent failures    |
| recovery_agent | Recovery    | 0 %          | Validates and recovers failed work |

## Files

### `orchestrator/` — always applied (Codetoreum-owned config)

| File                 | Owns                                                  |
|----------------------|-------------------------------------------------------|
| `simulation.yaml`    | Clock speed (10×), fidelity, scenario identity        |
| `agents.yaml`        | Flaky and recovery agent configs + metadata           |
| `workflows.yaml`     | 2-stage resilient workflow                            |
| `board_policy.yaml`  | Column triggers, failure routing, SLAs                |

### `external/` — simulation only (data owned by external system)

| File                   | Owns                                              |
|------------------------|---------------------------------------------------|
| `projects.yaml`        | Chaos-testing project                             |
| `work_items.yaml`      | 5 work items covering distinct failure modes      |
| `board_structure.yaml` | 5-column board id, name, and column list          |
| `board_placements.yaml`| Initial work item column placements               |
