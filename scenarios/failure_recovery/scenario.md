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

| File              | Owns                                                       |
|-------------------|------------------------------------------------------------|
| `simulation.yaml` | Clock speed (10×), fidelity, scenario identity             |
| `projects.yaml`   | External — chaos-testing project                           |
| `work_items.yaml` | External — 5 work items covering distinct failure modes    |
| `workflows.yaml`  | Orchestrator — 2-stage resilient workflow                  |
| `agents.yaml`     | Orchestrator — flaky and recovery agent configs + metadata |
| `board.yaml`      | Both — 5-column board structure + column policy            |

> **Note**: `board.yaml` currently mixes external state (board id, column names)
> with orchestrator policy (triggers, SLAs, failure routing). These will be split
> into `external/board_structure.yaml` and `orchestrator/board_policy.yaml` when
> the `external/` / `orchestrator/` directory structure is introduced.
